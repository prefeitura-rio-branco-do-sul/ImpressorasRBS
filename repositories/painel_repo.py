"""SQL da configuração do painel e dos tokens temporários de login/recuperação."""
import secrets
from contextlib import closing
from datetime import datetime, timedelta

from estoque import conectar
from repositories.comum import FORMATO_DATA, agora as _agora
from utils.seguranca import token_hash

VALIDADE_TOKEN_MINUTOS = 15


def garantir_tabela_configuracao(chave_ambiente, chave_atual):
    """Cria as tabelas de configuração e devolve a chave de sessão a ser usada."""
    with closing(conectar()) as conexao, conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS configuracao_painel (
                chave TEXT PRIMARY KEY,
                valor TEXT NOT NULL
            )
        """)
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS tokens_recuperacao_admin (
                token_hash TEXT PRIMARY KEY,
                expira_em TEXT NOT NULL
            )
        """)
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS tokens_login (
                token_hash TEXT PRIMARY KEY,
                expira_em TEXT NOT NULL
            )
        """)
        if chave_ambiente:
            return chave_ambiente
        chave_salva = conexao.execute(
            "SELECT valor FROM configuracao_painel WHERE chave = ?",
            ("chave_sessao",),
        ).fetchone()
        if chave_salva:
            return chave_salva[0]
        conexao.execute(
            """
            INSERT INTO configuracao_painel (chave, valor)
            VALUES (?, ?)
            """,
            ("chave_sessao", chave_atual),
        )
        return chave_atual


def _criar_token(tabela):
    token = secrets.token_urlsafe(32)
    agora = datetime.now()
    expira_em = (agora + timedelta(minutes=VALIDADE_TOKEN_MINUTOS)).strftime(FORMATO_DATA)
    with closing(conectar()) as conexao, conexao:
        conexao.execute(
            f"DELETE FROM {tabela} WHERE expira_em <= ?",
            (agora.strftime(FORMATO_DATA),),
        )
        conexao.execute(
            f"INSERT INTO {tabela} (token_hash, expira_em) VALUES (?, ?)",
            (token_hash(token), expira_em),
        )
    return token


def _consumir_token(tabela, token):
    if not token:
        return False
    digest = token_hash(token)
    with closing(conectar()) as conexao, conexao:
        conexao.execute("BEGIN IMMEDIATE")
        valido = conexao.execute(
            f"SELECT 1 FROM {tabela} WHERE token_hash = ? AND expira_em > ?",
            (digest, _agora()),
        ).fetchone()
        if not valido:
            return False
        conexao.execute(
            f"DELETE FROM {tabela} WHERE token_hash = ?",
            (digest,),
        )
    return True


def criar_token_login():
    return _criar_token("tokens_login")


def consumir_token_login(token):
    return _consumir_token("tokens_login", token)


def criar_token_recuperacao_admin():
    return _criar_token("tokens_recuperacao_admin")


def consumir_token_recuperacao_admin(token):
    return _consumir_token("tokens_recuperacao_admin", token)
