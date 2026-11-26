import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from time import time
from unittest.mock import patch

import app
import email_estoque
import estoque
import pedidos_estoque


class PedidosEstoqueTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        banco = os.path.join(self.pasta.name, "estoque.db")
        for modulo, atributo, valor in [
            (estoque, "BANCO", banco),
            (pedidos_estoque, "conectar", lambda: sqlite3.connect(banco)),
            (email_estoque, "conectar", lambda: sqlite3.connect(banco)),
        ]:
            p = patch.object(modulo, atributo, valor)
            p.start()
            self.addCleanup(p.stop)
        estoque.criar_banco()
        with closing(estoque.conectar()) as conexao, conexao:
            pedidos_estoque.criar_tabelas_pedidos(conexao)
        self.toner = estoque.cadastrar_toner("Marca", "A", "Preto", 1, 4)
        self.outro = estoque.cadastrar_toner("Marca", "B", "Azul", 0, 3)
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8))

    def criar_solicitacao(self, itens=None):
        pedido_id = pedidos_estoque.criar_solicitacao_pedido(
            "2026-11-16",
            itens or [{"toner_id": self.toner, "quantidade": 2}],
            "Pessoa",
            "estoque@example.com",
        )
        pedidos_estoque.marcar_solicitacao_enviada(pedido_id)
        return pedido_id

    def criar_pedido_aceito(self, itens=None):
        pedido_id = self.criar_solicitacao(itens)
        pedidos_estoque.decidir_solicitacao_pedido(pedido_id, "aceitar")
        return pedido_id

    def saldo(self, toner_id):
        with closing(estoque.conectar()) as conexao:
            return conexao.execute(
                "SELECT estoque FROM toners WHERE id = ?", (toner_id,)
            ).fetchone()[0]

    def test_solicitacao_so_aparece_para_recebimento_apos_aceite(self):
        pedido_id = self.criar_solicitacao([
            {"toner_id": self.toner, "quantidade": 2}
        ])
        dados = pedidos_estoque.listar_sugestoes_e_pedidos()
        self.assertEqual(dados["pedidos"], [])
        self.assertEqual(dados["solicitacoes"][0]["id"], pedido_id)
        self.assertEqual(dados["solicitacoes"][0]["status"], "AGUARDANDO_ACEITE")
        with self.assertRaisesRegex(ValueError, "precisa ser aceito"):
            pedidos_estoque.receber_pedido(
                pedido_id, [{"toner_id": self.toner, "quantidade": 1}], "Pessoa"
            )

        pedidos_estoque.decidir_solicitacao_pedido(pedido_id, "aceitar")
        dados = pedidos_estoque.listar_sugestoes_e_pedidos()
        self.assertEqual(dados["solicitacoes"], [])
        self.assertEqual(dados["pedidos"][0]["id"], pedido_id)
        self.assertEqual(dados["pedidos"][0]["itens"][0]["quantidade"], 2)
        with self.assertRaisesRegex(ValueError, "já decidida"):
            pedidos_estoque.decidir_solicitacao_pedido(pedido_id, "aceitar")

    def test_recusa_exclui_solicitacao_e_impede_recriacao_na_mesma_semana(self):
        pedido_id = self.criar_solicitacao()
        pedidos_estoque.decidir_solicitacao_pedido(pedido_id, "recusar")
        dados = pedidos_estoque.listar_sugestoes_e_pedidos()
        self.assertEqual(dados["pedidos"], [])
        self.assertEqual(dados["solicitacoes"], [])
        self.assertEqual(dados["sugestoes"][0]["status"], "RECUSADA")
        self.assertFalse(
            email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 9))
        )
        with closing(estoque.conectar()) as conexao:
            pedido = conexao.execute(
                "SELECT COUNT(*) FROM pedidos_estoque WHERE id = ?", (pedido_id,)
            ).fetchone()[0]
            itens = conexao.execute(
                "SELECT COUNT(*) FROM pedidos_estoque_itens WHERE pedido_id = ?",
                (pedido_id,),
            ).fetchone()[0]
        self.assertEqual(pedido, 0)
        self.assertEqual(itens, 0)

    def test_sugestao_anterior_arquivada_nao_pode_ser_enviada(self):
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 23, 8))
        with self.assertRaisesRegex(ValueError, "Use a sugestão mais recente"):
            pedidos_estoque.criar_solicitacao_pedido(
                "2026-11-16",
                [{"toner_id": self.toner, "quantidade": 2}],
                "Pessoa",
                "estoque@example.com",
            )

    def test_recebimento_parcial_atualiza_saldo_historico_e_impede_excesso(self):
        pedido_id = self.criar_pedido_aceito([
            {"toner_id": self.toner, "quantidade": 4}
        ])
        pedidos_estoque.receber_pedido(
            pedido_id, [{"toner_id": self.toner, "quantidade": 2}], "Pessoa"
        )
        with self.assertRaisesRegex(ValueError, "excede"):
            pedidos_estoque.receber_pedido(
                pedido_id, [{"toner_id": self.toner, "quantidade": 3}], "Pessoa"
            )
        pedidos_estoque.receber_pedido(
            pedido_id, [{"toner_id": self.toner, "quantidade": 2}], "Pessoa"
        )
        with self.assertRaisesRegex(ValueError, "excede"):
            pedidos_estoque.receber_pedido(
                pedido_id, [{"toner_id": self.toner, "quantidade": 1}], "Pessoa"
            )
        with closing(estoque.conectar()) as conexao:
            saldo = conexao.execute(
                "SELECT estoque FROM toners WHERE id = ?", (self.toner,)
            ).fetchone()[0]
            registros = conexao.execute(
                "SELECT quantidade, responsavel FROM movimentacoes WHERE observacao = ?",
                (f"Recebimento do pedido #{pedido_id}",),
            ).fetchall()
        self.assertEqual(saldo, 5)
        self.assertEqual(registros, [(2, "Pessoa"), (2, "Pessoa")])

    def test_recebimento_invalido_nao_altera_nenhum_item(self):
        pedido_id = self.criar_pedido_aceito([
            {"toner_id": self.toner, "quantidade": 2},
            {"toner_id": self.outro, "quantidade": 2},
        ])
        with self.assertRaises(ValueError):
            pedidos_estoque.receber_pedido(pedido_id, [
                {"toner_id": self.toner, "quantidade": 1},
                {"toner_id": self.outro, "quantidade": 3},
            ], "Pessoa")
        pedido = pedidos_estoque.listar_sugestoes_e_pedidos()["pedidos"][0]
        self.assertTrue(all(item["recebida"] == 0 for item in pedido["itens"]))

    def test_cancelar_saldo_pendente_nao_altera_estoque_e_preserva_historico(self):
        pedido_id = self.criar_pedido_aceito([
            {"toner_id": self.toner, "quantidade": 4},
            {"toner_id": self.outro, "quantidade": 2},
        ])
        pedidos_estoque.receber_pedido(
            pedido_id, [{"toner_id": self.toner, "quantidade": 1}], "Pessoa"
        )
        saldo_antes = {
            toner_id: self.saldo(toner_id)
            for toner_id in (self.toner, self.outro)
        }

        itens_cancelados = pedidos_estoque.cancelar_pendencias_pedido(
            pedido_id, "Pessoa"
        )

        self.assertEqual(
            {(item["toner_id"], item["quantidade"]) for item in itens_cancelados},
            {(self.toner, 3), (self.outro, 2)},
        )
        pedido = pedidos_estoque.listar_sugestoes_e_pedidos()["pedidos"][0]
        self.assertTrue(all(
            item["recebida"] + item["cancelada"] == item["quantidade"]
            for item in pedido["itens"]
        ))
        self.assertTrue(all(item["cancelada_em"] for item in pedido["itens"]))
        self.assertTrue(all(item["cancelada_por"] == "Pessoa" for item in pedido["itens"]))
        saldo_depois = {
            toner_id: self.saldo(toner_id)
            for toner_id in (self.toner, self.outro)
        }
        self.assertEqual(saldo_depois, saldo_antes)
        with self.assertRaisesRegex(ValueError, "excede"):
            pedidos_estoque.receber_pedido(
                pedido_id, [{"toner_id": self.toner, "quantidade": 1}], "Pessoa"
            )
        with self.assertRaisesRegex(ValueError, "não tem saldo pendente"):
            pedidos_estoque.cancelar_pendencias_pedido(pedido_id, "Pessoa")

    def test_migracao_adiciona_colunas_de_cancelamento_a_tabela_existente(self):
        with closing(sqlite3.connect(":memory:")) as conexao:
            conexao.execute("""
                CREATE TABLE sugestoes_estoque (
                    semana TEXT PRIMARY KEY,
                    criada_em TEXT NOT NULL
                )
            """)
            conexao.execute("""
                CREATE TABLE pedidos_estoque_itens (
                    pedido_id INTEGER NOT NULL,
                    toner_id INTEGER NOT NULL,
                    quantidade INTEGER NOT NULL,
                    recebida INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (pedido_id, toner_id)
                )
            """)
            pedidos_estoque.criar_tabelas_pedidos(conexao)
            colunas = {
                linha[1]
                for linha in conexao.execute("PRAGMA table_info(pedidos_estoque_itens)")
            }
            colunas_sugestoes = {
                linha[1]
                for linha in conexao.execute("PRAGMA table_info(sugestoes_estoque)")
            }
        self.assertTrue({"cancelada", "cancelada_em", "cancelada_por"} <= colunas)
        self.assertTrue(
            {"status", "verificar_em", "adiada_em", "adiada_por"} <= colunas_sugestoes
        )

    def test_sugestao_preserva_snapshot_mas_exibe_saldo_atual(self):
        estoque.ajustar_estoque_manual(self.toner, "entrada")
        sugestao = pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]
        item = next(i for i in sugestao["itens"] if i["toner_id"] == self.toner)
        self.assertEqual(item["estoque"], 1)
        self.assertEqual(item["estoque_atual"], 2)
        self.assertEqual(item["quantidade_sugerida"], 2)

    def test_sugestao_desconta_somente_pedidos_aceitos_e_recebimento_parcial(self):
        pedido_id = self.criar_solicitacao([
            {"toner_id": self.toner, "quantidade": 3}
        ])
        item = next(
            i for i in pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]["itens"]
            if i["toner_id"] == self.toner
        )
        self.assertEqual(item["quantidade_pendente"], 0)
        self.assertEqual(item["quantidade_sugerida"], 3)

        pedidos_estoque.decidir_solicitacao_pedido(pedido_id, "aceitar")
        item = next(
            i for i in pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]["itens"]
            if i["toner_id"] == self.toner
        )
        self.assertEqual(item["quantidade_pendente"], 3)
        self.assertEqual(item["quantidade_sugerida"], 0)

        pedidos_estoque.receber_pedido(
            pedido_id, [{"toner_id": self.toner, "quantidade": 2}], "Pessoa"
        )
        item = next(
            i for i in pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]["itens"]
            if i["toner_id"] == self.toner
        )
        self.assertEqual(item["estoque_atual"], 3)
        self.assertEqual(item["quantidade_pendente"], 1)
        self.assertEqual(item["quantidade_sugerida"], 0)

    def test_pedido_legado_nao_aparece_nem_conta_como_aceito(self):
        with closing(estoque.conectar()) as conexao, conexao:
            cursor = conexao.execute(
                "INSERT INTO pedidos_estoque (semana, criado_em, responsavel) VALUES (?, ?, ?)",
                ("2026-11-16", "16/11/2026 08:00:00", "Legado"),
            )
            conexao.execute(
                "INSERT INTO pedidos_estoque_itens (pedido_id, toner_id, quantidade) VALUES (?, ?, ?)",
                (cursor.lastrowid, self.toner, 3),
            )
        dados = pedidos_estoque.listar_sugestoes_e_pedidos()
        item = next(i for i in dados["sugestoes"][0]["itens"] if i["toner_id"] == self.toner)
        self.assertEqual(dados["pedidos"], [])
        self.assertEqual(dados["solicitacoes"], [])
        self.assertEqual(item["quantidade_pendente"], 0)
        self.assertEqual(item["quantidade_sugerida"], 3)

    def test_saldo_de_pedido_legado_pode_ser_cancelado_sem_entrada(self):
        with closing(estoque.conectar()) as conexao, conexao:
            cursor = conexao.execute(
                "INSERT INTO pedidos_estoque (semana, criado_em, responsavel) VALUES (?, ?, ?)",
                ("2026-11-09", "09/11/2026 08:00:00", "Legado"),
            )
            pedido_id = cursor.lastrowid
            conexao.execute(
                "INSERT INTO pedidos_estoque_itens (pedido_id, toner_id, quantidade) VALUES (?, ?, ?)",
                (pedido_id, self.toner, 3),
            )
        saldo_antes = self.saldo(self.toner)

        itens_cancelados = pedidos_estoque.cancelar_pendencias_pedido(
            pedido_id, "Pessoa"
        )

        self.assertEqual(itens_cancelados[0]["quantidade"], 3)
        pedido = pedidos_estoque.listar_sugestoes_e_pedidos()["pedidos"]
        self.assertEqual(pedido, [])
        with closing(estoque.conectar()) as conexao:
            item = conexao.execute(
                "SELECT quantidade, recebida, cancelada, cancelada_por "
                "FROM pedidos_estoque_itens WHERE pedido_id = ?",
                (pedido_id,),
            ).fetchone()
        self.assertEqual(item, (3, 0, 3, "Pessoa"))
        self.assertEqual(self.saldo(self.toner), saldo_antes)

    def test_rota_exige_permissao_de_ajuste_para_enviar(self):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": False, "permissoes": ["stock.view"], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post("/api/pedidos-estoque", json={
                "semana": "2026-11-16",
                "itens": [{"toner_id": self.toner, "quantidade": 1}],
            })
        self.assertEqual(resposta.status_code, 403)

    def test_rota_adia_sugestao_com_data_e_registra_responsavel(self):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        data_verificacao = (datetime.now().date() + timedelta(days=2)).isoformat()
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post(
                "/api/pedidos-estoque/sugestoes/2026-11-16/adiar",
                json={"data_verificacao": data_verificacao},
            )
        self.assertEqual(resposta.status_code, 200)
        sugestao = pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]
        self.assertEqual(sugestao["status"], "ADIADA")
        self.assertEqual(sugestao["verificar_em"], data_verificacao)
        self.assertEqual(sugestao["adiada_por"], "Pessoa")

    def test_rota_adiamento_exige_permissao_de_ajuste(self):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": False, "permissoes": ["stock.view"], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post(
                "/api/pedidos-estoque/sugestoes/2026-11-16/adiar",
                json={"data_verificacao": "2026-11-25"},
            )
        self.assertEqual(resposta.status_code, 403)
        sugestao = pedidos_estoque.listar_sugestoes_e_pedidos()["sugestoes"][0]
        self.assertEqual(sugestao["status"], "ABERTA")

    @patch("app.enviar_email_solicitacao")
    def test_fluxo_pelas_rotas_envia_aceita_e_recebe(self, enviar_email):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post("/api/pedidos-estoque", json={
                "semana": "2026-11-16",
                "itens": [{"toner_id": self.toner, "quantidade": 3}],
            })
            self.assertEqual(resposta.status_code, 201)
            pedido_id = resposta.json["pedido_id"]
            enviar_email.assert_called_once_with(pedido_id)
            dados = cliente.get("/api/pedidos-estoque").get_json()
            self.assertEqual(dados["pedidos"], [])
            self.assertEqual(dados["solicitacoes"][0]["status"], "AGUARDANDO_ACEITE")

            resposta = cliente.post(
                f"/api/pedidos-estoque/{pedido_id}/decisao",
                json={"decisao": "aceitar"},
            )
            self.assertEqual(resposta.status_code, 200)
            resposta = cliente.post(
                f"/api/pedidos-estoque/{pedido_id}/receber",
                json={"itens": [{"toner_id": self.toner, "quantidade": 2}]},
            )
            self.assertEqual(resposta.status_code, 200)
            dados = cliente.get("/api/pedidos-estoque").get_json()
            self.assertEqual(dados["pedidos"][0]["itens"][0]["recebida"], 2)

    def test_rota_cancela_saldo_pendente_sem_entrada_de_estoque(self):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        pedido_id = self.criar_pedido_aceito([
            {"toner_id": self.toner, "quantidade": 2}
        ])
        saldo_antes = self.saldo(self.toner)
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post(
                f"/api/pedidos-estoque/{pedido_id}/cancelar-pendentes",
                json={},
            )
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["itens_cancelados"][0]["quantidade"], 2)
        self.assertEqual(self.saldo(self.toner), saldo_antes)

    def test_rota_cancelamento_exige_permissao_de_ajuste(self):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": False, "permissoes": ["stock.view"], "ativo": True,
        }
        pedido_id = self.criar_pedido_aceito([
            {"toner_id": self.toner, "quantidade": 2}
        ])
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post(
                f"/api/pedidos-estoque/{pedido_id}/cancelar-pendentes",
                json={},
            )
        self.assertEqual(resposta.status_code, 403)
        pedido = pedidos_estoque.listar_sugestoes_e_pedidos()["pedidos"][0]
        self.assertEqual(pedido["itens"][0]["cancelada"], 0)

    @patch("app.enviar_email_solicitacao")
    def test_rota_recusa_e_exclui_a_solicitacao(self, enviar_email):
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post("/api/pedidos-estoque", json={
                "semana": "2026-11-16",
                "itens": [{"toner_id": self.toner, "quantidade": 2}],
            })
            pedido_id = resposta.json["pedido_id"]
            resposta = cliente.post(
                f"/api/pedidos-estoque/{pedido_id}/decisao",
                json={"decisao": "recusar"},
            )
            self.assertEqual(resposta.status_code, 200)
            dados = cliente.get("/api/pedidos-estoque").get_json()
        enviar_email.assert_called_once_with(pedido_id)
        self.assertEqual(dados["solicitacoes"], [])
        self.assertEqual(dados["pedidos"], [])
        self.assertEqual(dados["sugestoes"][0]["status"], "RECUSADA")

    @patch("app.enviar_email_solicitacao")
    def test_falha_de_email_reabre_sugestao_e_limpa_pedido(self, enviar_email):
        from email_estoque import ErroEnvioEmailEstoque

        enviar_email.side_effect = ErroEnvioEmailEstoque("Falha de envio")
        usuario = {
            "id": 123, "nome": "Pessoa", "usuario": "pessoa",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            cliente = app.app.test_client()
            with cliente.session_transaction() as sessao:
                sessao["presenca_atualizada_em"] = time()
            resposta = cliente.post("/api/pedidos-estoque", json={
                "semana": "2026-11-16",
                "itens": [{"toner_id": self.toner, "quantidade": 2}],
            })
            self.assertEqual(resposta.status_code, 502)
            dados = cliente.get("/api/pedidos-estoque").get_json()
        self.assertEqual(dados["solicitacoes"], [])
        self.assertEqual(dados["sugestoes"][0]["status"], "ABERTA")
        with closing(estoque.conectar()) as conexao:
            pedidos = conexao.execute(
                "SELECT COUNT(*) FROM pedidos_estoque"
            ).fetchone()[0]
        self.assertEqual(pedidos, 0)


if __name__ == "__main__":
    unittest.main()
