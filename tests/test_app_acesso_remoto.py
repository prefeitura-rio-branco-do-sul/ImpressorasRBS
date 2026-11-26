import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

import app as monitor_app
from helpers_repositorios import PatchConectarRepositorios
from werkzeug.security import generate_password_hash


class AcessoRemotoTests(unittest.TestCase):
    def setUp(self):
        self.diretorio_temporario = tempfile.TemporaryDirectory()
        self.caminho_banco = Path(self.diretorio_temporario.name) / "teste.db"
        with closing(sqlite3.connect(self.caminho_banco)) as conexao, conexao:
            conexao.executescript("""
                CREATE TABLE usuarios_painel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    senha_hash TEXT NOT NULL,
                    permissoes TEXT NOT NULL DEFAULT '[]',
                    administrador INTEGER NOT NULL DEFAULT 0,
                    ativo INTEGER NOT NULL DEFAULT 1,
                    criado_em TEXT NOT NULL,
                    ultimo_acesso TEXT
                );
                CREATE TABLE convites_painel (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    permissoes TEXT NOT NULL,
                    criado_por INTEGER NOT NULL,
                    criado_em TEXT NOT NULL,
                    expira_em TEXT NOT NULL,
                    usado_em TEXT
                );
                CREATE TABLE configuracao_painel (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );
                CREATE TABLE tokens_recuperacao_admin (
                    token_hash TEXT PRIMARY KEY,
                    expira_em TEXT NOT NULL
                );
                CREATE TABLE tokens_login (
                    token_hash TEXT PRIMARY KEY,
                    expira_em TEXT NOT NULL
                );
            """)
            conexao.execute(
                """
                INSERT INTO usuarios_painel
                    (nome, usuario, senha_hash, permissoes, administrador,
                     ativo, criado_em)
                VALUES (?, ?, ?, '[]', 1, 1, datetime('now'))
                """,
                (
                    "Administradora",
                    "admin",
                    generate_password_hash("senha-admin-teste"),
                ),
            )
            conexao.execute(
                """
                INSERT INTO usuarios_painel
                    (nome, usuario, senha_hash, permissoes, administrador,
                     ativo, criado_em)
                VALUES (?, ?, ?, ?, 0, 1, datetime('now'))
                """,
                (
                    "Pessoa do Estoque",
                    "estoque",
                    generate_password_hash("senha-estoque-teste"),
                    json.dumps(["monitor.view", "stock.view"]),
                ),
            )

        self.patch_conectar = PatchConectarRepositorios(self.caminho_banco)
        self.patch_conectar.start()
        self.patch_atualizacao = patch.object(
            monitor_app,
            "_iniciar_atualizacao_impressoras",
        )
        self.patch_atualizacao.start()
        self.ambiente = patch.dict(
            os.environ,
            {"PAINEL_REDE_LOCAL": "10.100.0.0/24"},
        )
        self.ambiente.start()
        self.cliente = monitor_app.app.test_client()

    def tearDown(self):
        self.ambiente.stop()
        self.patch_atualizacao.stop()
        self.patch_conectar.stop()
        self.diretorio_temporario.cleanup()

    def _entrar(self, cliente, usuario, senha, endereco="10.100.0.50"):
        pagina = cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": endereco},
        )
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)
        return cliente.post(
            "/entrar",
            data={
                "usuario": usuario,
                "senha": senha,
                "csrf_token": token,
            },
            environ_base={"REMOTE_ADDR": endereco},
        )

    def _csrf_da_pagina(self, cliente, caminho, endereco="10.100.0.50"):
        pagina = cliente.get(
            caminho,
            environ_base={"REMOTE_ADDR": endereco},
        )
        self.assertEqual(pagina.status_code, 200)
        return re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)

    def test_login_individual_e_painel_autenticado(self):
        resposta = self._entrar(
            self.cliente,
            "admin",
            "senha-admin-teste",
        )

        self.assertEqual(resposta.status_code, 302)
        painel = self.cliente.get(
            "/",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(painel.status_code, 200)
        self.assertNotIn("Gerenciar acessos", painel.get_data(as_text=True))

    def test_usuario_so_acessa_acoes_permitidas(self):
        resposta = self._entrar(
            self.cliente,
            "estoque",
            "senha-estoque-teste",
        )
        self.assertEqual(resposta.status_code, 302)

        estoque = self.cliente.get(
            "/estoque",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        historico = self.cliente.get(
            "/historico",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        administracao = self.cliente.get(
            "/admin/usuarios",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )

        self.assertEqual(estoque.status_code, 200)
        self.assertEqual(historico.status_code, 403)
        self.assertEqual(administracao.status_code, 403)

    def test_admin_cria_convite_individual_de_uso_unico(self):
        self._entrar(self.cliente, "admin", "senha-admin-teste")
        csrf_token = self._csrf_da_pagina(self.cliente, "/admin/usuarios")
        resposta = self.cliente.post(
            "/admin/usuarios/convites",
            data={
                "csrf_token": csrf_token,
                "nome": "Nova pessoa",
                "permissoes": ["stock.adjust"],
            },
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta.status_code, 302)
        with self.cliente.session_transaction() as sessao:
            link = sessao["convite_criado_url"]
        caminho_convite = urlsplit(link).path

        pagina = self.cliente.get(
            caminho_convite,
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(pagina.status_code, 200)
        csrf = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)
        ativacao = self.cliente.post(
            caminho_convite,
            data={
                "csrf_token": csrf,
                "usuario": "nova.pessoa",
                "senha": "senha-pessoal-segura",
                "confirmar_senha": "senha-pessoal-segura",
            },
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(ativacao.status_code, 302)

        estoque = self.cliente.get(
            "/estoque",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        historico = self.cliente.get(
            "/historico",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        convite_usado = self.cliente.get(
            caminho_convite,
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )

        self.assertEqual(estoque.status_code, 200)
        self.assertEqual(historico.status_code, 403)
        self.assertEqual(convite_usado.status_code, 404)

    def test_login_com_senha_incorreta_nao_autentica(self):
        resposta = self._entrar(self.cliente, "admin", "senha-incorreta")

        self.assertEqual(resposta.status_code, 401)
        self.assertIn(
            "Usuário ou senha incorretos",
            resposta.get_data(as_text=True),
        )

    def test_login_aceita_token_sem_cookie_de_sessao(self):
        pagina = self.cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)
        self.cliente.delete_cookie("session")

        resposta = self.cliente.post(
            "/entrar",
            data={
                "usuario": "admin",
                "senha": "senha-admin-teste",
                "csrf_token": token,
            },
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )

        self.assertEqual(resposta.status_code, 302)

    def test_login_token_permanece_valido_apos_troca_da_chave_da_sessao(self):
        pagina = self.cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        token = re.search(
            r'name="csrf_token" value="([^"]+)"',
            pagina.get_data(as_text=True),
        ).group(1)
        chave_anterior = monitor_app.app.secret_key
        try:
            monitor_app.app.secret_key = "chave-de-sessao-rotacionada"
            resposta = self.cliente.post(
                "/entrar",
                data={
                    "usuario": "admin",
                    "senha": "senha-admin-teste",
                    "csrf_token": token,
                },
                environ_base={"REMOTE_ADDR": "10.100.0.50"},
            )
        finally:
            monitor_app.app.secret_key = chave_anterior

        self.assertEqual(resposta.status_code, 302)

    def test_redefinicao_admin_somente_no_computador_local(self):
        login_local = self.cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertIn(
            "Esqueci a senha da administração",
            login_local.get_data(as_text=True),
        )

        csrf = self._csrf_da_pagina(
            self.cliente,
            "/recuperar-admin",
            endereco="127.0.0.1",
        )
        resposta = self.cliente.post(
            "/recuperar-admin",
            data={
                "csrf_token": csrf,
                "senha": "nova-senha-admin-teste",
                "confirmar_senha": "nova-senha-admin-teste",
            },
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Senha redefinida", resposta.get_data(as_text=True))

        login = self._entrar(
            self.cliente,
            "admin",
            "nova-senha-admin-teste",
        )
        self.assertEqual(login.status_code, 302)

    def test_token_recuperacao_permanece_valido_apos_troca_da_chave_da_sessao(self):
        token = self._csrf_da_pagina(
            self.cliente,
            "/recuperar-admin",
            endereco="127.0.0.1",
        )
        chave_anterior = monitor_app.app.secret_key
        try:
            monitor_app.app.secret_key = "outra-chave-de-sessao"
            resposta = self.cliente.post(
                "/recuperar-admin",
                data={
                    "csrf_token": token,
                    "senha": "senha-admin-aprovada",
                    "confirmar_senha": "senha-admin-aprovada",
                },
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )
        finally:
            monitor_app.app.secret_key = chave_anterior

        self.assertEqual(resposta.status_code, 200)
        self.assertIn("Senha redefinida", resposta.get_data(as_text=True))

    def test_chave_de_sessao_permanece_apos_reiniciar_configuracao(self):
        chave_anterior = monitor_app.app.secret_key
        try:
            with patch.dict(os.environ, {"PAINEL_SESSION_SECRET": ""}):
                monitor_app.app.secret_key = "chave-inicial-do-servidor"
                monitor_app._garantir_tabela_configuracao_painel()
                monitor_app.app.secret_key = "chave-aleatoria-depois-do-reinicio"
                monitor_app._garantir_tabela_configuracao_painel()

            self.assertEqual(
                monitor_app.app.secret_key,
                "chave-inicial-do-servidor",
            )
        finally:
            monitor_app.app.secret_key = chave_anterior

    def test_redefinicao_admin_recusada_pela_rede(self):
        resposta = self.cliente.get(
            "/recuperar-admin",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )

        self.assertEqual(resposta.status_code, 404)

    def test_login_na_rede_nao_exibe_link_de_recuperacao_local(self):
        resposta = self.cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )

        self.assertEqual(resposta.status_code, 200)
        self.assertNotIn(
            "Esqueci a senha da administração",
            resposta.get_data(as_text=True),
        )

    def test_bloqueia_dispositivo_fora_da_sub_rede_local(self):
        resposta = self.cliente.get(
            "/entrar",
            environ_base={"REMOTE_ADDR": "10.101.0.50"},
        )

        self.assertEqual(resposta.status_code, 403)

    def test_sem_sub_rede_configurada_aceita_ip_privado(self):
        with patch.dict(os.environ, {"PAINEL_REDE_LOCAL": ""}):
            resposta = self.cliente.get(
                "/entrar",
                environ_base={"REMOTE_ADDR": "10.100.0.50"},
            )

        self.assertEqual(resposta.status_code, 200)

    def test_sem_sub_rede_configurada_bloqueia_ip_publico(self):
        with patch.dict(os.environ, {"PAINEL_REDE_LOCAL": ""}):
            resposta = self.cliente.get(
                "/entrar",
                environ_base={"REMOTE_ADDR": "8.8.8.8"},
            )

        self.assertEqual(resposta.status_code, 403)

    def test_presenca_online_restrita_a_administracao(self):
        self._entrar(self.cliente, "estoque", "senha-estoque-teste")
        resposta_usuario = self.cliente.get(
            "/admin/usuarios/presenca",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta_usuario.status_code, 403)

        cliente_admin = monitor_app.app.test_client()
        self._entrar(cliente_admin, "admin", "senha-admin-teste")
        resposta_admin = cliente_admin.get(
            "/admin/usuarios/presenca",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta_admin.status_code, 200)
        self.assertTrue(
            any(
                conta["usuario"] == "estoque"
                for conta in resposta_admin.get_json()
            )
        )

    def test_conta_desativada_perde_acesso_mesmo_com_sessao_aberta(self):
        cliente_usuario = monitor_app.app.test_client()
        self._entrar(cliente_usuario, "estoque", "senha-estoque-teste")
        self.assertEqual(
            cliente_usuario.get(
                "/",
                environ_base={"REMOTE_ADDR": "10.100.0.50"},
            ).status_code,
            200,
        )

        self._entrar(self.cliente, "admin", "senha-admin-teste")
        csrf = self._csrf_da_pagina(self.cliente, "/admin/usuarios")
        resposta_admin = self.cliente.post(
            "/admin/usuarios/2/status",
            data={"csrf_token": csrf, "ativo": "0"},
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta_admin.status_code, 302)

        resposta_usuario = cliente_usuario.get(
            "/",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta_usuario.status_code, 302)
        self.assertEqual(resposta_usuario.location, "/entrar")

    def test_convite_expirado_nao_pode_ser_usado(self):
        self._entrar(self.cliente, "admin", "senha-admin-teste")
        csrf_token = self._csrf_da_pagina(self.cliente, "/admin/usuarios")
        resposta = self.cliente.post(
            "/admin/usuarios/convites",
            data={
                "csrf_token": csrf_token,
                "nome": "Convite pendente",
                "permissoes": ["stock.view"],
            },
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(resposta.status_code, 302)
        with self.cliente.session_transaction() as sessao:
            caminho = urlsplit(sessao["convite_criado_url"]).path
        token = caminho.rsplit("/", 1)[-1]
        with closing(sqlite3.connect(self.caminho_banco)) as conexao, conexao:
            conexao.execute(
                "UPDATE convites_painel SET expira_em = '2000-01-01 00:00:00'"
            )

        pagina = self.cliente.get(
            f"/convite/{token}",
            environ_base={"REMOTE_ADDR": "10.100.0.50"},
        )
        self.assertEqual(pagina.status_code, 404)


if __name__ == "__main__":
    unittest.main()
