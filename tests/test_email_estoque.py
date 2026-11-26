import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import date, datetime
from unittest.mock import patch

import email_estoque
import pedidos_estoque
from pedidos_estoque import criar_tabelas_pedidos


class EmailEstoqueTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        self.banco = os.path.join(self.pasta.name, "estoque.db")
        with closing(sqlite3.connect(self.banco)) as conexao, conexao:
            conexao.execute("""
                CREATE TABLE toners (
                    id INTEGER PRIMARY KEY,
                    marca TEXT, codigo TEXT, cor TEXT, modelos_compativeis TEXT,
                    estoque INTEGER, estoque_minimo INTEGER, ativo INTEGER
                )
            """)
            conexao.executemany(
                "INSERT INTO toners (marca, codigo, cor, modelos_compativeis, estoque, estoque_minimo, ativo) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("Marca", "A", "Preto", "Modelo 1", 1, 4, 1),
                    ("Marca", "B", "Azul", "", 2, 2, 1),
                    ("Marca", "C", "Preto", "", 3, 2, 1),
                    ("Marca", "D", "Preto", "", 0, 3, 0),
                ],
            )
            criar_tabelas_pedidos(conexao)
        for modulo in (email_estoque, pedidos_estoque):
            conectar = patch.object(
                modulo, "conectar", side_effect=lambda: sqlite3.connect(self.banco)
            )
            conectar.start()
            self.addCleanup(conectar.stop)
        self.ambiente = patch.dict(os.environ, {
            "GMAIL_REMETENTE": "remetente@example.com",
            "GMAIL_SENHA_APP": "senha-teste",
            "EMAIL_ESTOQUE_SEMANAL": "estoque@example.com",
        })
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

    @patch("email_estoque.smtplib.SMTP")
    def test_sugestao_e_gerada_segunda_apos_oito_sem_enviar_email(self, smtp):
        self.assertFalse(email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 7, 59)))
        self.assertFalse(email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 17, 8, 0)))
        self.assertTrue(email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8, 0)))
        self.assertFalse(email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 12, 0)))
        smtp.assert_not_called()
        with closing(sqlite3.connect(self.banco)) as conexao:
            sugestao = conexao.execute(
                "SELECT status FROM sugestoes_estoque WHERE semana = ?",
                ("2026-11-16",),
            ).fetchone()
            codigos = conexao.execute(
                "SELECT codigo FROM sugestoes_estoque_itens WHERE semana = ? ORDER BY codigo",
                ("2026-11-16",),
            ).fetchall()
        self.assertEqual(sugestao, ("ABERTA",))
        self.assertEqual(codigos, [("A",), ("B",)])

    @patch("email_estoque.smtplib.SMTP")
    def test_adiamento_gera_nova_sugestao_na_data_escolhida_sem_enviar_email(self, smtp):
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8))
        pedidos_estoque.adiar_sugestao_pedido(
            "2026-11-16",
            "2026-11-25",
            "Pessoa",
            hoje=date(2026, 11, 23),
        )

        self.assertFalse(
            email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 23, 8))
        )
        self.assertTrue(
            email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 25, 8))
        )
        self.assertFalse(
            email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 25, 12))
        )
        smtp.assert_not_called()
        with closing(sqlite3.connect(self.banco)) as conexao:
            status_antiga = conexao.execute(
                "SELECT status, verificar_em, adiada_por FROM sugestoes_estoque WHERE semana = ?",
                ("2026-11-16",),
            ).fetchone()
            status_nova = conexao.execute(
                "SELECT status FROM sugestoes_estoque WHERE semana = ?",
                ("2026-11-25",),
            ).fetchone()
            data_nova = conexao.execute(
                "SELECT criada_em FROM sugestoes_estoque WHERE semana = ?",
                ("2026-11-25",),
            ).fetchone()[0]
        self.assertEqual(status_antiga, ("ARQUIVADA", "2026-11-25", "Pessoa"))
        self.assertEqual(status_nova, ("ABERTA",))
        self.assertTrue(data_nova.startswith("2026-11-25"))

    def test_adiamento_rejeita_data_atual_ou_formato_invalido(self):
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8))
        with self.assertRaisesRegex(ValueError, "data futura"):
            pedidos_estoque.adiar_sugestao_pedido(
                "2026-11-16",
                "2026-11-23",
                "Pessoa",
                hoje=date(2026, 11, 23),
            )
        with self.assertRaisesRegex(ValueError, "data válida"):
            pedidos_estoque.adiar_sugestao_pedido(
                "2026-11-16",
                "25/11/2026",
                "Pessoa",
                hoje=date(2026, 11, 23),
            )

    @patch("email_estoque.smtplib.SMTP")
    def test_email_contem_as_quantidades_editadas_e_pede_decisao(self, smtp):
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8))
        pedido_id = pedidos_estoque.criar_solicitacao_pedido(
            "2026-11-16",
            [{"toner_id": 1, "quantidade": 2}],
            "Pessoa",
            "estoque@example.com",
        )
        email_estoque.enviar_email_solicitacao(pedido_id)
        mensagem = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        corpo = mensagem.get_content()
        self.assertEqual(mensagem["To"], "estoque@example.com")
        self.assertIn("Toner Marca A (Preto) — 2 unidades", corpo)
        self.assertIn("aceita ou recusada", corpo)
        self.assertIn("Nenhuma compra foi realizada automaticamente.", corpo)
        self.assertNotIn("Toner Marca B", corpo)
        smtp.return_value.__enter__.return_value.send_message.assert_called_once()

    @patch("email_estoque.smtplib.SMTP")
    def test_falha_de_envio_e_reportada(self, smtp):
        email_estoque.gerar_sugestao_semanal(datetime(2026, 11, 16, 8))
        pedido_id = pedidos_estoque.criar_solicitacao_pedido(
            "2026-11-16",
            [{"toner_id": 1, "quantidade": 2}],
            "Pessoa",
            "estoque@example.com",
        )
        smtp.side_effect = OSError("Falha de conexão")
        with self.assertRaises(email_estoque.ErroEnvioEmailEstoque):
            email_estoque.enviar_email_solicitacao(pedido_id)


if __name__ == "__main__":
    unittest.main()
