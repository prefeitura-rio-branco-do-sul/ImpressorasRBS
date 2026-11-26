import os
import tempfile
import unittest
from contextlib import closing
from time import time
from unittest.mock import patch

import app as monitor_app
import estoque


class HistoricoTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        patch_banco = patch.object(estoque, "BANCO", os.path.join(pasta.name, "estoque.db"))
        patch_banco.start()
        self.addCleanup(patch_banco.stop)
        estoque.criar_banco()
        self.toner_id = estoque.cadastrar_toner("Marca", "A", "Preto", 0, 1)
        usuario = {
            "id": 123, "nome": "Teste", "usuario": "teste",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        for campo, valor in [
            ("_obter_usuario_atual", lambda: usuario),
            ("carregar_lista_impressoras", lambda: []),
        ]:
            p = patch.object(monitor_app, campo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.cliente = monitor_app.app.test_client()
        with self.cliente.session_transaction() as sessao:
            sessao["presenca_atualizada_em"] = time()

    def movimentacao(self, tipo, observacao, ip=None):
        with closing(estoque.conectar()) as conexao, conexao:
            cursor = conexao.execute("""
                INSERT INTO movimentacoes (toner_id, tipo, quantidade, data, ip_impressora, observacao)
                VALUES (?, ?, 1, '16/11/2026 08:00:00', ?, ?)
            """, (self.toner_id, tipo, ip, observacao))
            return cursor.lastrowid

    def test_troca_automatica_so_aparece_uma_vez_e_nao_ocupa_pagina_manual(self):
        entrada = self.movimentacao("ENTRADA", "Reposição")
        saida = self.movimentacao("SAIDA", "Troca manual")
        automatica = self.movimentacao(
            "SAIDA", "Baixa automática por troca detectada: 5% para 100%", "10.0.0.1"
        )
        self.movimentacao("SAIDA", "Ajuste rápido de estoque pela tela")

        resposta = self.cliente.get("/historico?limite=2")
        self.assertEqual(resposta.status_code, 200)
        dados = resposta.get_json()
        self.assertEqual([item["id"] for item in dados["entradas"]], [entrada])
        self.assertEqual([item["id"] for item in dados["saidas"]], [saida])
        self.assertEqual([item["id"] for item in dados["saidas_automaticas"]], [automatica])
        self.assertEqual(dados["paginacao"]["total"], 2)
        self.assertEqual(dados["paginacao"]["paginas"], 1)

    def test_paginacao_conta_apenas_entradas_e_saidas_nao_automaticas(self):
        ids = [self.movimentacao("SAIDA", f"Manual {i}") for i in range(3)]
        for i in range(4):
            self.movimentacao("SAIDA", f"Baixa automática por troca detectada: {i}")
        pagina1 = self.cliente.get("/historico?limite=2&pagina=1").get_json()
        pagina2 = self.cliente.get("/historico?limite=2&pagina=2").get_json()
        self.assertEqual([item["id"] for item in pagina1["saidas"]], ids[::-1][:2])
        self.assertEqual([item["id"] for item in pagina2["saidas"]], ids[::-1][2:])
        self.assertEqual(pagina1["paginacao"]["total"], 3)
        self.assertEqual(pagina1["paginacao"]["paginas"], 2)
        self.assertEqual(len(pagina1["saidas_automaticas"]), 4)
        self.assertEqual(len(pagina2["saidas_automaticas"]), 4)

    def test_ajuste_em_quantidade_atualiza_saldo_e_aparece_no_historico(self):
        entrada = self.cliente.post(
            f"/ajustar-estoque/{self.toner_id}",
            json={"acao": "entrada", "quantidade": 5},
        )
        self.assertEqual(entrada.status_code, 200)
        self.assertEqual(entrada.json["novo_estoque"], 5)
        saida = self.cliente.post(
            f"/ajustar-estoque/{self.toner_id}",
            json={"acao": "saida", "quantidade": 3},
        )
        self.assertEqual(saida.status_code, 200)
        self.assertEqual(saida.json["novo_estoque"], 2)
        historico = self.cliente.get("/historico").get_json()
        self.assertEqual(historico["entradas"][0]["quantidade"], 5)
        self.assertEqual(historico["saidas"][0]["quantidade"], 3)
        self.assertEqual(historico["entradas"][0]["responsavel"], "Teste")
        self.assertEqual(historico["saidas"][0]["responsavel"], "Teste")

    def test_ajustes_invalidos_nao_alteram_saldo_nem_criam_movimentacao(self):
        self.cliente.post(f"/ajustar-estoque/{self.toner_id}", json={"acao": "entrada", "quantidade": 2})
        for quantidade in (0, -1, 1.5, True, "2", 1000001, 3):
            with self.subTest(quantidade=quantidade):
                resposta = self.cliente.post(
                    f"/ajustar-estoque/{self.toner_id}",
                    json={"acao": "saida", "quantidade": quantidade},
                )
                self.assertEqual(resposta.status_code, 400)
        with closing(estoque.conectar()) as conexao:
            saldo = conexao.execute("SELECT estoque FROM toners WHERE id = ?", (self.toner_id,)).fetchone()[0]
            registros = conexao.execute("SELECT COUNT(*) FROM movimentacoes").fetchone()[0]
        self.assertEqual(saldo, 2)
        self.assertEqual(registros, 1)

    def test_ajuste_antigo_sem_quantidade_continua_adicionando_uma_unidade(self):
        resposta = self.cliente.post(
            f"/ajustar-estoque/{self.toner_id}", json={"acao": "entrada"}
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["novo_estoque"], 1)


if __name__ == "__main__":
    unittest.main()
