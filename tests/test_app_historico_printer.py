import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import app as monitor_app
from helpers_repositorios import PatchConectarRepositorios
from relatorio_printer import criar_tabela_historico_printer
from test_relatorio_printer import texto_consumo


class HistoricoPrinterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.banco = str(Path(self.temp.name) / "teste.db")
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            criar_tabela_historico_printer(conexao)
        self.conexao_patch = PatchConectarRepositorios(self.banco)
        self.usuario = {
            "id": 1, "ativo": True, "administrador": False,
            "permissoes": ["report.analyze"],
        }
        self.usuario_patch = patch.object(
            monitor_app, "_obter_usuario_atual", side_effect=lambda: self.usuario
        )
        self.pdf_patch = patch.object(
            monitor_app, "ler_relatorio_pdf", return_value=(texto_consumo(), [])
        )
        self.conexao_patch.start()
        self.usuario_patch.start()
        self.pdf_patch.start()
        self.cliente = monitor_app.app.test_client()
        with self.cliente.session_transaction() as sessao:
            sessao["csrf_token"] = "token-teste"
            sessao["presenca_atualizada_em"] = time.time()

    def tearDown(self):
        self.pdf_patch.stop()
        self.usuario_patch.stop()
        self.conexao_patch.stop()
        self.temp.cleanup()

    def enviar(self, conteudo, anterior="", token="token-teste"):
        return self.cliente.post("/api/relatorio-printer/historico", data={
            "relatorio": (BytesIO(conteudo), "relatorio.pdf"),
            "csrf_token": token,
            "substituir_sha256": anterior,
        })

    def test_salva_pdf_compara_listagem_e_exige_confirmacao_atualizada(self):
        primeiro = b"%PDF-primeiro"
        segundo = b"%PDF-segundo"
        self.assertEqual(self.enviar(primeiro).status_code, 200)
        conflito = self.enviar(segundo)
        self.assertEqual(conflito.status_code, 409)
        digest = conflito.get_json()["existente_sha256"]
        listagem = self.cliente.get("/api/relatorio-printer/historico").get_json()
        self.assertEqual(len(listagem["relatorios"]), 1)
        item = listagem["relatorios"][0]
        self.assertEqual(item["paginas"], 1284)
        self.assertEqual(item["pagina_metro_linear"], "58,90")
        url = f"/api/relatorio-printer/historico/{item['id']}/pdf"
        self.assertEqual(self.cliente.get(url).data, primeiro)
        self.assertEqual(self.enviar(segundo, "hash-antigo").status_code, 409)
        self.assertEqual(self.cliente.get(url).data, primeiro)
        self.assertEqual(self.enviar(segundo, digest).status_code, 200)
        self.assertEqual(self.cliente.get(url).data, segundo)
        self.assertEqual(self.enviar(segundo).get_json()["mensagem"], "Este PDF já está salvo.")
        self.assertEqual(len(self.cliente.get("/api/relatorio-printer/historico").get_json()["relatorios"]), 1)

    def test_nega_sem_csrf_ou_permissao(self):
        self.assertEqual(self.enviar(b"%PDF-teste", token="errado").status_code, 403)
        self.usuario["permissoes"] = []
        self.assertEqual(self.enviar(b"%PDF-teste").status_code, 403)
        self.assertEqual(self.cliente.get("/api/relatorio-printer/historico").status_code, 403)
        self.assertEqual(self.cliente.get("/api/relatorio-printer/historico/1/pdf").status_code, 403)

    def test_grafico_apenas_na_pagina_inicial_com_permissao(self):
        resposta = self.cliente.get("/")
        self.assertEqual(resposta.status_code, 200)
        html = resposta.get_data(as_text=True)
        self.assertIn('id="grafico-printer-inicio" data-permissoes="report.analyze"', html)
        self.assertIn('id="grafico-inicio-printer"', html)
        self.assertNotIn('id="grafico-historico-printer"', html)
        self.assertIn('id="dados-grafico-inicio-printer"', html)
        self.assertIn('id="comparacao-printer"', html)


if __name__ == "__main__":
    unittest.main()
