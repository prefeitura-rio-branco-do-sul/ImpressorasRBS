import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

import app as monitor_app
import suprimentos_snmp


class EdicaoImpressorasTests(unittest.TestCase):
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
        self.arquivo_atualizado = self.base_dir / "ImpressorasRBS_atualizada.xlsx"

        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append(["Nome", "IP", "Patrimônio"])
        aba.append(["Local antigo (Kyocera ECOSYS M3655idn)", "10.0.0.1", "SERIE-1"])
        aba["E2"] = "teste@example.com"
        aba.append(["Outro equipamento", "10.0.0.1", "SERIE-2"])
        planilha.save(self.arquivo_original)
        planilha.close()

        self.patch_base_dir = patch.object(monitor_app, "BASE_DIR", self.base_dir)
        self.patch_arquivo_atual = patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            side_effect=lambda: (
                self.arquivo_atualizado
                if self.arquivo_atualizado.exists()
                else self.arquivo_original
            ),
        )
        self.patch_base_dir.start()
        self.patch_arquivo_atual.start()
        self.cliente = monitor_app.app.test_client()
        with self.cliente.session_transaction() as sessao:
            sessao["csrf_token"] = "token-teste"

    def tearDown(self):
        self.patch_arquivo_atual.stop()
        self.patch_base_dir.stop()
        self.patch_senha_painel.stop()
        self.diretorio_temporario.cleanup()

    def test_edita_patrimonio_sem_alterar_outro_registro(self):
        resposta = self.cliente.put(
            "/api/impressoras/editar",
            json={
                "ip": "10.0.0.1",
                "serie_original": "SERIE-1",
                "patrimonio_original": "SERIE-1",
                "nome": "Local atualizado",
                "setor": "SEMED",
                "serie": "",
                "modelo": "Kyocera ECOSYS M3655idn",
                "patrimonio": "PAT-NOVO",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        planilha = openpyxl.load_workbook(self.arquivo_atualizado, data_only=True)
        try:
            aba = planilha.active
            self.assertEqual(aba["A2"].value, "Local atualizado")
            self.assertEqual(aba["C1"].value, "Patrimônio")
            self.assertEqual(aba["C2"].value, "PAT-NOVO")
            self.assertEqual(aba["D2"].value, "SEMED")
            self.assertEqual(aba["E2"].value, "teste@example.com")
            self.assertEqual(aba["F2"].value, "Kyocera ECOSYS M3655idn")
            self.assertEqual(aba["A3"].value, "Outro equipamento")
            self.assertEqual(aba["C3"].value, "SERIE-2")
        finally:
            planilha.close()

        with patch.object(suprimentos_snmp, "BASE_DIR", self.base_dir):
            cadastro_snmp = suprimentos_snmp.carregar_planilha()
        self.assertEqual(cadastro_snmp[0]["modelo"], "Kyocera ECOSYS M3655idn")
        self.assertEqual(cadastro_snmp[0]["setor"], "SEMED")

    def test_permite_mudar_setor_do_modelo_m2040dn(self):
        resposta = self.cliente.put(
            "/api/impressoras/editar",
            json={
                "ip": "10.0.0.1",
                "serie_original": "SERIE-1",
                "nome": "Local",
                "setor": "SEMED",
                "serie": "SERIE-1",
                "modelo": "Kyocera ECOSYS M2040dn",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        planilha = openpyxl.load_workbook(
            self.arquivo_atualizado,
            data_only=True,
        )
        try:
            self.assertEqual(planilha.active["D2"].value, "SEMED")
        finally:
            planilha.close()

    def test_cadastra_impressora_no_formato_original(self):
        resposta = self.cliente.post(
            "/api/impressoras",
            data={
                "csrf_token": "token-teste",
                "ip": "10.0.0.8",
                "nome": "Biblioteca",
                "setor": "SEMED",
                "modelo": "Brother HL-L5212DW",
                "patrimonio": "PAT-8",
            },
        )

        self.assertEqual(resposta.status_code, 201)
        planilha = openpyxl.load_workbook(
            self.arquivo_atualizado,
            data_only=True,
        )
        try:
            aba = planilha.active
            self.assertEqual(aba["A4"].value, "Biblioteca (Brother HL-L5212DW)")
            self.assertEqual(aba["B4"].value, "10.0.0.8")
            self.assertEqual(aba["C4"].value, "PAT-8")
            self.assertEqual(aba["D4"].value, "SEMED")
            self.assertEqual(aba["F4"].value, "Brother HL-L5212DW")
            self.assertEqual(aba["E2"].value, "teste@example.com")
        finally:
            planilha.close()

        cadastro = monitor_app.carregar_lista_impressoras()
        nova_impressora = next(
            item for item in cadastro if item["ip"] == "10.0.0.8"
        )
        self.assertEqual(nova_impressora["grupo"], "SEMED")

    def test_cadastra_impressora_no_formato_consolidado(self):
        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append([
            "IGNORAR", "IP", "Patrimônio", "Modelo", "Departamento e nome",
            "Número de série", "Excluída",
        ])
        aba.append([
            "", "10.0.0.1", "PAT-1", "Modelo", "SEMED - Local 1",
            "SERIE-1", None,
        ])
        planilha.save(self.arquivo_atualizado)
        planilha.close()

        resposta = self.cliente.post(
            "/api/impressoras",
            data={
                "csrf_token": "token-teste",
                "ip": "10.0.0.8",
                "nome": "Biblioteca",
                "setor": "SEMED",
                "modelo": "Brother HL-L5212DW",
                "serie": "SERIE-8",
            },
        )

        self.assertEqual(resposta.status_code, 201)
        planilha = openpyxl.load_workbook(
            self.arquivo_atualizado,
            data_only=True,
        )
        try:
            aba = planilha.active
            self.assertEqual(aba["B3"].value, "10.0.0.8")
            self.assertEqual(aba["D3"].value, "Brother HL-L5212DW")
            self.assertEqual(aba["E3"].value, "SEMED - Biblioteca")
            self.assertEqual(aba["F3"].value, "SERIE-8")
        finally:
            planilha.close()

    def test_cadastro_rejeita_ip_duplicado_e_token_csrf_ausente(self):
        dados = {
            "csrf_token": "token-teste",
            "ip": "10.0.0.1",
            "nome": "Biblioteca",
            "setor": "SEMED",
            "modelo": "Brother HL-L5212DW",
        }
        resposta = self.cliente.post("/api/impressoras", data=dados)
        self.assertEqual(resposta.status_code, 409)
        self.assertFalse(self.arquivo_atualizado.exists())

        dados["ip"] = "10.0.0.8"
        dados.pop("csrf_token")
        resposta = self.cliente.post("/api/impressoras", data=dados)
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(self.arquivo_atualizado.exists())

    def test_cadastro_exige_permissao_de_edicao(self):
        usuario_sem_edicao = {
            "id": 999998,
            "nome": "Leitura",
            "usuario": "leitura",
            "senha_hash": "",
            "permissoes": ["monitor.view"],
            "administrador": False,
            "ativo": True,
            "ultimo_acesso": None,
        }
        with patch.object(
            monitor_app,
            "_obter_usuario_atual",
            return_value=usuario_sem_edicao,
        ):
            resposta = self.cliente.post(
                "/api/impressoras",
                data={
                    "csrf_token": "token-teste",
                    "ip": "10.0.0.8",
                    "nome": "Biblioteca",
                    "setor": "SEMED",
                    "modelo": "Brother HL-L5212DW",
                },
            )

        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(self.arquivo_atualizado.exists())

    def test_limpa_patrimonio_no_formato_original(self):
        resposta = self.cliente.put(
            "/api/impressoras/editar",
            json={
                "ip": "10.0.0.1",
                "serie_original": "SERIE-1",
                "patrimonio_original": "SERIE-1",
                "nome": "Local",
                "setor": "SEMED",
                "serie": "SERIE-1",
                "modelo": "Modelo",
                "patrimonio": "",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        planilha = openpyxl.load_workbook(self.arquivo_atualizado, data_only=True)
        try:
            self.assertIsNone(planilha.active["C2"].value)
        finally:
            planilha.close()

    def test_edita_consolidada_pelo_patrimonio_com_ip_e_serie_vazios_duplicados(self):
        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append([
            "IGNORAR", "IP", "Patrimônio", "Modelo", "Departamento e nome",
            "Número de série", "Excluída",
        ])
        aba.append([
            "", "10.0.0.1", "PAT-1", "Modelo", "Local 1", "", None,
        ])
        aba.append([
            "", "10.0.0.1", "PAT-2", "Modelo", "Local 2", "", None,
        ])
        planilha.save(self.arquivo_atualizado)
        planilha.close()

        resposta = self.cliente.put(
            "/api/impressoras/editar",
            json={
                "ip": "10.0.0.1",
                "serie_original": "",
                "patrimonio_original": "PAT-2",
                "nome": "Local 2 atualizado",
                "setor": "SEMED",
                "serie": "",
                "modelo": "Modelo",
                "patrimonio": "PAT-2-NOVO",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        planilha = openpyxl.load_workbook(
            self.arquivo_atualizado,
            data_only=True,
        )
        try:
            aba = planilha.active
            self.assertEqual(aba["C2"].value, "PAT-1")
            self.assertEqual(aba["C3"].value, "PAT-2-NOVO")
            self.assertEqual(aba["E3"].value, "Local 2 atualizado")
            self.assertIsNone(aba["F3"].value)
        finally:
            planilha.close()

    def test_patrimonio_vazio_e_atualizado_no_painel_e_apos_recarregar(self):
        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append([
            "IGNORAR", "IP", "Patrimônio", "Modelo", "Departamento e nome",
            "Número de série", "Excluída",
        ])
        aba.append(["", "10.0.0.3", None, "Modelo", "SEMED - Escola", None])
        planilha.save(self.arquivo_atualizado)
        planilha.close()

        impressora = monitor_app.adicionar_grupos([{
            "ip": "10.0.0.3",
            "patrimonio": None,
            "status": "Offline",
        }])[0]
        self.assertEqual(impressora["patrimonio_planilha"], "")
        self.assertEqual(impressora["formato_cadastro"], "consolidado")

        with patch.object(monitor_app, "_impressoras_cache", [impressora]):
            resposta = self.cliente.put(
                "/api/impressoras/editar",
                json={
                    "ip": "10.0.0.3",
                    "serie_original": "",
                    "patrimonio_original": "",
                    "nome": "SEMED - Escola",
                    "setor": "SEMED",
                    "serie": "",
                    "modelo": "Modelo",
                    "patrimonio": "PAT-NOVO",
                },
            )
            self.assertEqual(resposta.status_code, 200)
            with patch.object(monitor_app, "_iniciar_atualizacao_impressoras"):
                dados = self.cliente.get("/dados").get_json()
            self.assertEqual(dados[0]["patrimonio"], "PAT-NOVO")
            self.assertEqual(dados[0]["patrimonio_planilha"], "PAT-NOVO")

        recarregada = monitor_app.adicionar_grupos([{
            "ip": "10.0.0.3",
            "patrimonio": None,
            "status": "Offline",
        }])[0]
        self.assertEqual(recarregada["patrimonio"], "PAT-NOVO")
        self.assertEqual(recarregada["patrimonio_planilha"], "PAT-NOVO")

    def test_exclusao_oculta_impressora_do_painel_e_preserva_registro(self):
        resposta = self.cliente.delete(
            "/api/impressoras/excluir",
            json={"ip": "10.0.0.1", "serie": "SERIE-1"},
        )

        self.assertEqual(resposta.status_code, 409)

        planilha = openpyxl.load_workbook(self.arquivo_original)
        planilha.active["B3"] = "10.0.0.2"
        planilha.save(self.arquivo_original)
        planilha.close()

        resposta = self.cliente.delete(
            "/api/impressoras/excluir",
            json={"ip": "10.0.0.1", "serie": "SERIE-1"},
        )
        self.assertEqual(resposta.status_code, 200)
        cadastro_visivel = monitor_app.carregar_lista_impressoras()
        self.assertEqual(len(cadastro_visivel), 1)
        self.assertEqual(cadastro_visivel[0]["ip"], "10.0.0.2")

        impressoras = monitor_app.adicionar_grupos([
            {"ip": "10.0.0.1", "nome": "Impressora", "modelo": "Kyocera"}
        ])
        self.assertEqual(impressoras, [])

        planilha = openpyxl.load_workbook(self.arquivo_atualizado, data_only=True)
        try:
            self.assertEqual(planilha.active["G2"].value, "SIM")
            self.assertEqual(planilha.active["A2"].value, "Local antigo (Kyocera ECOSYS M3655idn)")
        finally:
            planilha.close()

        with patch.object(suprimentos_snmp, "BASE_DIR", self.base_dir):
            cadastro_snmp = suprimentos_snmp.carregar_planilha()
        self.assertEqual(
            [item["ip"] for item in cadastro_snmp],
            ["10.0.0.2"],
        )


if __name__ == "__main__":
    unittest.main()
