import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

import app as monitor_app


class GruposImpressorasTests(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.diretorio_temporario.name)
        self.arquivo_atual = self.base_dir / "ImpressorasRBS_atualizada.xlsx"

        original = openpyxl.Workbook()
        aba_original = original.active
        aba_original.append([None, None, None])
        aba_original.append(["Nome", "IP", "Número de série"])
        aba_original.append([
            "SECULT - Casarão Furquim (Kyocera ECOSYS M3145idn)",
            "10.56.0.1",
            "R4V8Z05352",
        ])
        aba_original.append([
            "SEMAD - Administração (Kyocera ECOSYS M3655idn)",
            "10.0.0.5",
            "R4P2Z20544",
        ])
        original.save(self.base_dir / "ImpressorasRBS.xlsx")
        original.close()

        atual = openpyxl.Workbook()
        aba_atual = atual.active
        aba_atual.append([None, None, None])
        aba_atual.append(["Nome", "IP", "Número de série", "Setor"])
        aba_atual.append(["CULTURA", "10.56.0.1", "R4V8Z05352"])
        aba_atual.append(["Novo local (M3655idn)", "10.0.0.5", "NOVA-SERIE"])
        aba_atual.append([
            "ADMINISTRAÇÃO - ARQUIVO GERAL (P311)",
            "10.16.0.2",
            "5872ZC10504",
            "SEMAD",
        ])
        aba_atual.append([
            "EMC LUIZ SEGUNDO FIO.. (ECOSYS M3145idn)",
            "10.39.0.1",
            "R4V8Y04879",
            "SEMED",
        ])
        aba_atual.append([
            "EMC SALVADOR MARIANO (Kyocera ECOSYS M2040dn)",
            "10.45.0.1",
            "VR91Z94866",
            "SEMED",
        ])
        atual.save(self.arquivo_atual)
        atual.close()

        self.patch_base_dir = patch.object(monitor_app, "BASE_DIR", self.base_dir)
        self.patch_arquivo_atual = patch.object(
            monitor_app,
            "_arquivo_lista_impressoras",
            return_value=self.arquivo_atual,
        )
        self.patch_base_dir.start()
        self.patch_arquivo_atual.start()

    def tearDown(self):
        self.patch_arquivo_atual.stop()
        self.patch_base_dir.stop()
        self.diretorio_temporario.cleanup()

    def test_preserva_setor_original_apos_correcao_do_nome(self):
        impressoras = monitor_app.carregar_lista_impressoras()

        self.assertEqual(impressoras[0]["nome"], "CULTURA")
        self.assertEqual(impressoras[0]["grupo"], "SECULT")

    def test_usa_ip_unico_quando_serie_mudou(self):
        impressoras = monitor_app.carregar_lista_impressoras()

        self.assertEqual(impressoras[1]["grupo"], "SEMAD")

    def test_setor_cadastrado_tem_precedencia_sobre_local_e_cadastro_original(self):
        impressoras = monitor_app.carregar_lista_impressoras()

        self.assertEqual(impressoras[2]["grupo"], "SEMAD")
        self.assertEqual(impressoras[3]["grupo"], "SEMED")

    def test_modelo_m2040dn_fica_no_setor_cadastrado(self):
        impressoras = monitor_app.carregar_lista_impressoras()

        self.assertEqual(impressoras[4]["grupo"], "SEMED")
        self.assertEqual(
            impressoras[4]["modelo_cadastro"],
            "Kyocera ECOSYS M2040dn",
        )

    def test_nome_local_nao_e_substituido_pelo_modelo(self):
        inventario = [
            {
                "ip": "10.45.0.1",
                "nome": "Impressora 10.45.0.1",
                "modelo": "EMC SALVADOR MARIANO (Kyocera ECOSYS M2040dn)",
            }
        ]

        resultado = monitor_app.adicionar_grupos(inventario)

        self.assertEqual(
            resultado[0]["nome_planilha"],
            "EMC SALVADOR MARIANO (Kyocera ECOSYS M2040dn)",
        )
        self.assertEqual(
            resultado[0]["modelo_cadastro"],
            "Kyocera ECOSYS M2040dn",
        )


if __name__ == "__main__":
    unittest.main()
