from io import BytesIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

import app as monitor_app
import suprimentos_snmp
from relatorio_printer import extrair_equipamentos_relatorio


class CorrecoesRelatorioPrinterTests(unittest.TestCase):
    def setUp(self):
        self.patch_senha_painel = patch.object(
            monitor_app,
            "_obter_usuario_atual",
            return_value={
                "id": 999999,
                "nome": "Teste",
                "usuario": "teste",
                "senha_hash": "",
                "permissoes": [],
                "administrador": True,
                "ativo": True,
                "ultimo_acesso": None,
            },
        )
        self.patch_senha_painel.start()
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.diretorio_temporario.name)
        self.arquivo_original = self.base_dir / "ImpressorasRBS.xlsx"

        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append(["Nome", "IP", "Número de série"])
        aba.append(["Local antigo", "10.0.0.1", "VR91282459"])
        planilha.save(self.arquivo_original)

        self.patch_base_dir = patch.object(monitor_app, "BASE_DIR", self.base_dir)
        self.patch_arquivo_atual = patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            return_value=self.arquivo_original,
        )
        self.patch_base_dir.start()
        self.patch_arquivo_atual.start()
        self.cliente = monitor_app.app.test_client()

    def tearDown(self):
        self.patch_arquivo_atual.stop()
        self.patch_base_dir.stop()
        self.patch_senha_painel.stop()
        self.diretorio_temporario.cleanup()

    def test_approval_updates_new_workbook_and_preserves_original(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-correcao",
            json={"serie": "VR91282459", "local": "Local aprovado"},
        )

        self.assertEqual(resposta.status_code, 200)
        arquivo_atualizado = self.base_dir / "ImpressorasRBS_atualizada.xlsx"
        self.assertTrue(arquivo_atualizado.exists())

        original = openpyxl.load_workbook(self.arquivo_original, data_only=True)
        atualizado = openpyxl.load_workbook(arquivo_atualizado, data_only=True)
        try:
            self.assertEqual(original.active["A2"].value, "Local antigo")
            self.assertEqual(atualizado.active["A2"].value, "Local aprovado")
        finally:
            original.close()
            atualizado.close()

        with patch.object(suprimentos_snmp, "BASE_DIR", self.base_dir):
            self.assertEqual(
                suprimentos_snmp.obter_arquivo_planilha_impressoras(),
                arquivo_atualizado,
            )

        texto = (
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "Local aprovado C. ANT."
        )
        equipamentos = extrair_equipamentos_relatorio(texto)
        with patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            return_value=arquivo_atualizado,
        ):
            with patch.object(
                monitor_app,
                "ler_relatorio_pdf",
                return_value=(texto, equipamentos),
            ):
                resposta_analise = self.cliente.post(
                    "/api/relatorio-printer/analisar",
                    data={
                        "relatorio": (
                            BytesIO(b"%PDF-1.4 teste"),
                            "relatorio.pdf",
                        )
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(resposta_analise.status_code, 200)
        resultado = resposta_analise.get_json()
        self.assertEqual(resultado["total_divergencias"], 0)
        self.assertIn("Não foram identificadas divergências", resultado["corpo_email"])

    def test_duplicate_serial_is_not_updated(self):
        planilha = openpyxl.load_workbook(self.arquivo_original)
        planilha.active.append(
            ["Outro local", "10.0.0.2", "VR91282459"]
        )
        planilha.save(self.arquivo_original)
        planilha.close()

        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-correcao",
            json={"serie": "VR91282459", "local": "Local aprovado"},
        )

        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

    def test_correction_for_new_serial_points_to_replacement_flow(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-correcao",
            json={"serie": "VR99355944", "local": "Local aprovado"},
        )

        self.assertEqual(resposta.status_code, 404)
        self.assertIn(
            "Considerar substituição (mesmo IP)",
            resposta.get_json()["erro"],
        )
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

    def test_approved_local_equivalence_is_saved_and_used_in_future_analysis(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-equivalencia",
            json={
                "serie": "VR91282459",
                "local_relatorio": "Polo Universitário Central",
                "local_cadastro": "Local antigo",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        arquivo_equivalencias = (
            self.base_dir / ".relatorio_locais_equivalentes.json"
        )
        self.assertTrue(arquivo_equivalencias.exists())
        self.assertEqual(
            monitor_app._carregar_locais_equivalentes(),
            {"VR91282459": ["POLO UNIVERSITARIO CENTRAL"]},
        )

        texto = (
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "Polo Universitário Central C. ANT."
        )
        equipamentos = extrair_equipamentos_relatorio(texto)
        with patch.object(
            monitor_app,
            "ler_relatorio_pdf",
            return_value=(texto, equipamentos),
        ):
            resposta_analise = self.cliente.post(
                "/api/relatorio-printer/analisar",
                data={
                    "relatorio": (
                        BytesIO(b"%PDF-1.4 teste"),
                        "relatorio.pdf",
                    )
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(resposta_analise.status_code, 200)
        resultado = resposta_analise.get_json()
        self.assertEqual(resultado["total_divergencias"], 0)
        self.assertIn("Não foram identificadas divergências", resultado["corpo_email"])
        self.assertFalse((self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists())

    def test_batch_analysis_consolidates_successes_and_reports_bad_files(self):
        equipamento_1 = extrair_equipamentos_relatorio(
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "Local antigo C. ANT."
        )
        equipamento_2 = extrair_equipamentos_relatorio(
            "  4729 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "Local antigo C. ANT."
        )
        leitor_pdf = patch.object(
            monitor_app,
            "ler_relatorio_pdf",
            side_effect=[
                ("Relatório 1", equipamento_1),
                ("Relatório 2", equipamento_2),
            ],
        )
        inventario = patch.object(
            monitor_app,
            "carregar_inventario_relatorio",
            return_value=[{"serie": "VR91282459", "local": "Local antigo"}],
        )
        leitor_pdf.start()
        inventario.start()
        try:
            resposta = self.cliente.post(
                "/api/relatorio-printer/analisar",
                data={
                    "relatorios": [
                        (BytesIO(b"%PDF-1.4 um"), "relatorio-1.pdf"),
                        (BytesIO(b"%PDF-1.4 dois"), "relatorio-2.pdf"),
                        (BytesIO(b"nao e pdf"), "invalido.pdf"),
                    ]
                },
                content_type="multipart/form-data",
            )
        finally:
            leitor_pdf.stop()
            inventario.stop()

        self.assertEqual(resposta.status_code, 200)
        resultado = resposta.get_json()
        self.assertEqual(resultado["total_analisado"], 2)
        self.assertEqual(resultado["total_divergencias"], 0)
        self.assertEqual(
            resultado["arquivos_analisados"],
            ["relatorio-1.pdf", "relatorio-2.pdf"],
        )
        self.assertEqual(
            resultado["arquivos_com_erro"],
            [{
                "arquivo": "invalido.pdf",
                "erro": "O arquivo não parece ser um PDF válido.",
            }],
        )

    def test_approved_new_printer_is_added_and_disappears_from_report(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-inclusao",
            json={
                "serie": "VR99355944",
                "modelo": "Kyocera ECOSYS M2040dn",
                "local": "Novo local",
                "ip": "10.0.0.2",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        arquivo_atualizado = self.base_dir / "ImpressorasRBS_atualizada.xlsx"
        original = openpyxl.load_workbook(self.arquivo_original, data_only=True)
        atualizado = openpyxl.load_workbook(arquivo_atualizado, data_only=True)
        try:
            self.assertEqual(original.active.max_row, 2)
            self.assertEqual(atualizado.active["A3"].value,
                             "Novo local (Kyocera ECOSYS M2040dn)")
            self.assertEqual(atualizado.active["B3"].value, "10.0.0.2")
            self.assertEqual(atualizado.active["C3"].value, "VR99355944")
        finally:
            original.close()
            atualizado.close()

        texto = (
            "  4731 IMPRESSORA MONO, VR99355944, ECOSYS M2040dn, "
            "Novo local C. ANT."
        )
        equipamentos = extrair_equipamentos_relatorio(texto)
        with patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            return_value=arquivo_atualizado,
        ):
            with patch.object(
                monitor_app,
                "ler_relatorio_pdf",
                return_value=(texto, equipamentos),
            ):
                resposta_analise = self.cliente.post(
                    "/api/relatorio-printer/analisar",
                    data={
                        "relatorio": (
                            BytesIO(b"%PDF-1.4 teste"),
                            "relatorio.pdf",
                        )
                    },
                    content_type="multipart/form-data",
                )
            impressoras = monitor_app.carregar_lista_impressoras()

        self.assertEqual(resposta_analise.status_code, 200)
        resultado = resposta_analise.get_json()
        self.assertEqual(resultado["total_divergencias"], 0)
        self.assertIn("10.0.0.2", [impressora["ip"] for impressora in impressoras])

    def test_approved_new_printer_rejects_duplicate_ip(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-inclusao",
            json={
                "serie": "VR99355944",
                "modelo": "Kyocera ECOSYS M2040dn",
                "local": "Novo local",
                "ip": "10.0.0.1",
            },
        )

        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

    def test_duplicate_ip_can_be_replaced_after_explicit_confirmation(self):
        dados = {
            "serie": "VR99355944",
            "modelo": "Kyocera ECOSYS M2040dn",
            "local": "Novo local",
            "ip": "10.0.0.1",
        }
        conflito = self.cliente.post(
            "/api/relatorio-printer/aprovar-inclusao",
            json=dados,
        )
        self.assertEqual(conflito.status_code, 409)
        self.assertEqual(
            conflito.get_json()["codigo"],
            "ip_ja_cadastrado",
        )
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

        dados["substituir_ip"] = True
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-inclusao",
            json=dados,
        )

        self.assertEqual(resposta.status_code, 200)
        original = openpyxl.load_workbook(self.arquivo_original, data_only=True)
        atualizado = openpyxl.load_workbook(
            self.base_dir / "ImpressorasRBS_atualizada.xlsx",
            data_only=True,
        )
        try:
            self.assertEqual(original.active["A2"].value, "Local antigo")
            self.assertEqual(atualizado.active.max_row, 2)
            self.assertEqual(
                atualizado.active["A2"].value,
                "Novo local (Kyocera ECOSYS M2040dn)",
            )
            self.assertEqual(atualizado.active["B2"].value, "10.0.0.1")
            self.assertEqual(atualizado.active["C2"].value, "VR99355944")
        finally:
            original.close()
            atualizado.close()

    def test_approved_new_printer_rejects_invalid_ip(self):
        resposta = self.cliente.post(
            "/api/relatorio-printer/aprovar-inclusao",
            json={
                "serie": "VR99355944",
                "modelo": "Kyocera ECOSYS M2040dn",
                "local": "Novo local",
                "ip": "not-an-ip",
            },
        )

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

    def test_report_replacement_by_same_ip_does_not_change_inventory(self):
        texto = (
            "  4731 IMPRESSORA MONO, VR99355944, ECOSYS M2040dn, "
            "Local antigo C. ANT."
        )
        equipamentos = extrair_equipamentos_relatorio(texto)
        with patch.object(
            monitor_app,
            "ler_relatorio_pdf",
            return_value=(texto, equipamentos),
        ):
            resposta = self.cliente.post(
                "/api/relatorio-printer/analisar",
                data={
                    "relatorio": (
                        BytesIO(b"%PDF-1.4 teste"),
                        "relatorio.pdf",
                    ),
                    "substituicoes": (
                        '[{"serie":"VR99355944","ip":"10.0.0.1"}]'
                    ),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(resposta.status_code, 200)
        resultado = resposta.get_json()
        self.assertEqual(resultado["total_analisado"], 1)
        self.assertEqual(resultado["total_divergencias"], 0)
        self.assertEqual(resultado["total_substituicoes"], 1)
        self.assertIn("série anterior VR91282459", resultado["corpo_email"])
        self.assertIn("série VR99355944", resultado["corpo_email"])
        original = openpyxl.load_workbook(self.arquivo_original, data_only=True)
        try:
            self.assertEqual(original.active.max_row, 2)
            self.assertEqual(original.active["B2"].value, "10.0.0.1")
            self.assertEqual(original.active["C2"].value, "VR91282459")
        finally:
            original.close()
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )

    def test_report_replacement_rejects_ip_not_in_inventory(self):
        texto = (
            "  4731 IMPRESSORA MONO, VR99355944, ECOSYS M2040dn, "
            "Local antigo C. ANT."
        )
        equipamentos = extrair_equipamentos_relatorio(texto)
        with patch.object(
            monitor_app,
            "ler_relatorio_pdf",
            return_value=(texto, equipamentos),
        ):
            resposta = self.cliente.post(
                "/api/relatorio-printer/analisar",
                data={
                    "relatorio": (
                        BytesIO(b"%PDF-1.4 teste"),
                        "relatorio.pdf",
                    ),
                    "substituicoes": (
                        '[{"serie":"VR99355944","ip":"10.0.0.99"}]'
                    ),
                },
                content_type="multipart/form-data",
            )

        self.assertEqual(resposta.status_code, 400)
        self.assertIn("exatamente uma impressora", resposta.get_json()["erro"])
        self.assertFalse(
            (self.base_dir / "ImpressorasRBS_atualizada.xlsx").exists()
        )


if __name__ == "__main__":
    unittest.main()
