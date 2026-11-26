import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import openpyxl

import app as monitor_app
import suprimentos_snmp


class CadastroConsolidadoTests(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.diretorio_temporario.name)
        self.arquivo_atual = self.base_dir / "ImpressorasRBS_atualizada.xlsx"

        planilha = openpyxl.Workbook()
        aba = planilha.active
        aba.append([
            "IGNORAR", "IP", "Patrimônio", "Modelo", "Departamento e nome",
            "Número de série", "Excluída",
        ])
        aba.append([
            "Nome que não deve aparecer", "10.0.0.1", "PAT-1", "Modelo A",
            "SEMED - Local cadastrado", "SERIE-1", None,
        ])
        aba.append([
            "Ignorar", "10.0.0.2", "PAT-2", "Modelo B", "", "", None,
        ])
        aba.append([
            "Duplicata a ignorar", "10.0.0.1", "PAT-4", "Modelo C",
            "Outro nome", "SERIE-4", None,
        ])
        planilha.save(self.arquivo_atual)
        planilha.close()

        (self.base_dir / "Impressoras_Limpo.csv").write_text(
            "Name,PortName\n"
            "Nome atualizado,10.0.0.1\n"
            "Nome com sufixo,10.0.0.2_1\n"
            "Novo local,10.0.0.4\n"
            "Novo local repetido,10.0.0.4\n"
            "Microsoft XPS Document Writer,PORTPROMPT:\n"
            "Microsoft Print to PDF,PORTPROMPT:\n",
            encoding="utf-8",
        )

        self.patch_usuario = patch.object(
            monitor_app,
            "_obter_usuario_atual",
            return_value={
                "id": 999999,
                "nome": "Teste",
                "usuario": "teste",
                "permissoes": [],
                "administrador": True,
                "ativo": True,
            },
        )
        self.patch_base_dir = patch.object(monitor_app, "BASE_DIR", self.base_dir)
        self.patch_snmp_base_dir = patch.object(
            suprimentos_snmp,
            "BASE_DIR",
            self.base_dir,
        )
        self.patch_snmp_workbook = patch.object(
            suprimentos_snmp,
            "obter_arquivo_planilha_impressoras",
            return_value=self.arquivo_atual,
        )
        self.patch_arquivo_atual = patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            return_value=self.arquivo_atual,
        )
        self.patch_usuario.start()
        self.patch_base_dir.start()
        self.patch_snmp_base_dir.start()
        self.patch_snmp_workbook.start()
        self.patch_arquivo_atual.start()
        self.cliente = monitor_app.app.test_client()

    def tearDown(self):
        self.patch_arquivo_atual.stop()
        self.patch_base_dir.stop()
        self.patch_snmp_base_dir.stop()
        self.patch_snmp_workbook.stop()
        self.patch_usuario.stop()
        self.diretorio_temporario.cleanup()

    def test_baixa_uma_planilha_consolidada_sem_repetir_enderecos(self):
        resposta = self.cliente.get("/api/impressoras/consolidado")

        self.assertEqual(resposta.status_code, 200)
        planilha = openpyxl.load_workbook(BytesIO(resposta.data), data_only=True)
        try:
            aba = planilha.active
            self.assertEqual(planilha.sheetnames, ["Consolidado"])
            self.assertEqual(aba.max_row, 6)
            self.assertEqual(
                [aba.cell(1, coluna).value for coluna in range(1, 5)],
                ["IP", "Patrimônio", "Modelo", "Departamento e nome"],
            )
            self.assertEqual(aba["A2"].value, "10.0.0.1")
            self.assertEqual(aba["B2"].value, "PAT-1")
            self.assertEqual(aba["C2"].value, "Modelo A")
            self.assertEqual(aba["D2"].value, "SEMED - Local cadastrado")
            self.assertEqual(aba["E2"].value, "SERIE-1")
            self.assertEqual(aba["A3"].value, "10.0.0.2_1")
            self.assertEqual(aba["D3"].value, "Nome com sufixo")
            self.assertIsNone(aba["E3"].value)
            self.assertEqual(aba["A4"].value, "10.0.0.4")
            self.assertEqual(aba["D4"].value, "Novo local")
            self.assertEqual(aba["D5"].value, "Microsoft XPS Document Writer")
            self.assertEqual(aba["D6"].value, "Microsoft Print to PDF")
            self.assertEqual(
                [
                    aba.cell(row, 1).value
                    for row in range(2, aba.max_row + 1)
                ].count("10.0.0.1"),
                1,
            )
        finally:
            planilha.close()

    def test_leitura_do_monitoramento_usa_b_a_e_e_preserva_serie_em_f(self):
        lista = monitor_app.carregar_lista_impressoras()
        impressora = next(item for item in lista if item["ip"] == "10.0.0.1")

        self.assertEqual(impressora["nome"], "SEMED - Local cadastrado")
        self.assertEqual(impressora["serie_planilha"], "SERIE-1")
        self.assertEqual(impressora["patrimonio_planilha"], "PAT-1")
        self.assertEqual(impressora["modelo_cadastro"], "Modelo A")
        self.assertEqual(impressora["grupo"], "SEMED")
        self.assertEqual(impressora["formato_cadastro"], "consolidado")

        cadastro_snmp = suprimentos_snmp.carregar_planilha()
        equipamento = next(item for item in cadastro_snmp if item["ip"] == "10.0.0.1")
        self.assertEqual(equipamento["descricao"], "SEMED - Local cadastrado")
        self.assertEqual(equipamento["patrimonio"], "PAT-1")
        self.assertEqual(equipamento["modelo"], "Modelo A")
        self.assertEqual(equipamento["setor"], "SEMED")
        self.assertIn(
            "10.0.0.2",
            {item["ip"] for item in cadastro_snmp},
        )

        inventario = monitor_app.carregar_inventario_relatorio()
        registro = next(item for item in inventario if item["ip"] == "10.0.0.1")
        self.assertEqual(registro["local"], "SEMED - Local cadastrado")
        self.assertEqual(registro["serie"], "SERIE-1")

    def test_edicao_preserva_o_layout_b_e_e_e_a_serie_em_f(self):
        resposta = self.cliente.put(
            "/api/impressoras/editar",
            json={
                "ip": "10.0.0.1",
                "serie_original": "SERIE-1",
                "nome": "SEMED - Local editado",
                "setor": "SEMED",
                "serie": "SERIE-NOVA",
                "modelo": "Modelo atualizado",
                "patrimonio": "PAT-NOVO",
            },
        )

        self.assertEqual(resposta.status_code, 200)
        atualizada = openpyxl.load_workbook(
            self.base_dir / "ImpressorasRBS_atualizada.xlsx",
            data_only=True,
        )
        try:
            aba = atualizada.active
            self.assertEqual(aba["A1"].value, "IGNORAR")
            self.assertEqual(aba["B1"].value, "IP")
            self.assertEqual(aba["B2"].value, "10.0.0.1")
            self.assertEqual(aba["C2"].value, "PAT-NOVO")
            self.assertEqual(aba["D2"].value, "Modelo atualizado")
            self.assertEqual(aba["E2"].value, "SEMED - Local editado")
            self.assertEqual(aba["F2"].value, "SERIE-NOVA")
        finally:
            atualizada.close()

    def test_ip_duplicado_prefere_nome_da_coluna_e_ao_modelo(self):
        inventario = [
            {
                "ip": "10.0.0.1",
                "nome": "Impressora de rede",
                "modelo": "Modelo A",
            }
        ]

        resultado = monitor_app.adicionar_grupos(inventario)

        self.assertEqual(resultado[0]["nome_planilha"], "SEMED - Local cadastrado")
        self.assertEqual(resultado[0]["modelo_cadastro"], "Modelo A")
        self.assertEqual(resultado[0]["patrimonio_planilha"], "PAT-1")
        self.assertEqual(resultado[0]["patrimonio"], "PAT-1")
        self.assertEqual(resultado[0]["formato_cadastro"], "consolidado")

        cadastro_snmp = suprimentos_snmp.carregar_planilha()
        equipamento = next(item for item in cadastro_snmp if item["ip"] == "10.0.0.1")
        self.assertEqual(equipamento["descricao"], "SEMED - Local cadastrado")
        self.assertEqual(equipamento["modelo"], "Modelo A")


if __name__ == "__main__":
    unittest.main()
