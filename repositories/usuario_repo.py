"""SQL de usuários, convites e presença do painel."""
import json
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from estoque import conectar
from repositories.comum import FORMATO_DATA, agora as _agora
from utils.seguranca import token_hash

VALIDADE_CONVITE_HORAS = 48


def garantir_tabelas_usuarios():
    with closing(conectar()) as conexao, conexao:
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS usuarios_painel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
                senha_hash TEXT NOT NULL,
                permissoes TEXT NOT NULL DEFAULT '[]',
                administrador INTEGER NOT NULL DEFAULT 0,
                ativo INTEGER NOT NULL DEFAULT 1,
                criado_em TEXT NOT NULL,
                ultimo_acesso TEXT
            )
        """)
        conexao.execute("""
            CREATE TABLE IF NOT EXISTS convites_painel (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                permissoes TEXT NOT NULL,
                criado_por INTEGER NOT NULL,
                criado_em TEXT NOT NULL,
                expira_em TEXT NOT NULL,
                usado_em TEXT,
                FOREIGN KEY (criado_por) REFERENCES usuarios_painel(id)
            )
        """)
        conexao.execute("BEGIN IMMEDIATE")
        administrador = conexao.execute(
            "SELECT id FROM usuarios_painel WHERE administrador = 1 LIMIT 1"
        ).fetchone()
        senha_legada = conexao.execute(
            "SELECT valor FROM configuracao_painel WHERE chave = ?",
            ("senha_hash",),
        ).fetchone()
        if not administrador and senha_legada:
            conexao.execute(
                """
                INSERT INTO usuarios_painel
                    (nome, usuario, senha_hash, permissoes, administrador, ativo, criado_em)
                VALUES (?, ?, ?, '[]', 1, 1, ?)
                """,
                ("Administradora", "admin", senha_legada[0], _agora()),
            )
            conexao.execute(
                "DELETE FROM configuracao_painel WHERE chave = ?",
                ("senha_hash",),
            )


def obter_usuario_por_id(usuario_id):
    if not usuario_id:
        return None
    with closing(conectar()) as conexao, conexao:
        linha = conexao.execute(
            """
            SELECT id, nome, usuario, senha_hash, permissoes,
                   administrador, ativo, ultimo_acesso
            FROM usuarios_painel
            WHERE id = ?
            """,
            (usuario_id,),
        ).fetchone()
    if not linha:
        return None
    return {
        "id": linha[0],
        "nome": linha[1],
        "usuario": linha[2],
        "senha_hash": linha[3],
        "permissoes": json.loads(linha[4]),
        "administrador": bool(linha[5]),
        "ativo": bool(linha[6]),
        "ultimo_acesso": linha[7],
    }


def registrar_presenca(usuario_id):
    with closing(conectar()) as conexao, conexao:
        conexao.execute(
            "UPDATE usuarios_painel SET ultimo_acesso = ? WHERE id = ?",
            (_agora(), usuario_id),
        )


def buscar_credenciais_login(usuario_login):
    """Devolve (id, senha_hash, ativo) ou None."""
    with closing(conectar()) as conexao, conexao:
        return conexao.execute(
            """
            SELECT id, senha_hash, ativo FROM usuarios_painel
            WHERE usuario = ? COLLATE NOCASE
            """,
            (usuario_login,),
        ).fetchone()


def redefinir_senha_admin(senha_hash):
    """Troca a senha da primeira conta administrativa ativa; True se houve alteração."""
    with closing(conectar()) as conexao, conexao:
        resultado = conexao.execute(
            """
            UPDATE usuarios_painel
            SET senha_hash = ?
            WHERE id = (
                SELECT id FROM usuarios_painel
                WHERE administrador = 1 AND ativo = 1
                ORDER BY id
                LIMIT 1
            )
            """,
            (senha_hash,),
        )
    return bool(resultado.rowcount)


def buscar_convite_valido(token):
    """Devolve (id, nome, permissoes) do convite ainda válido ou None."""
    with closing(conectar()) as conexao, conexao:
        return conexao.execute(
            """
            SELECT id, nome, permissoes FROM convites_painel
            WHERE token_hash = ? AND usado_em IS NULL AND expira_em > ?
            """,
            (token_hash(token), _agora()),
        ).fetchone()


def aceitar_convite(token, usuario_login, senha_hash):
    """Cria a conta do convite. Devolve (usuario_id, erro)."""
    digest = token_hash(token)
    agora = _agora()
    try:
        with closing(conectar()) as conexao, conexao:
            conexao.execute("BEGIN IMMEDIATE")
            convite = conexao.execute(
                """
                SELECT id, nome, permissoes FROM convites_painel
                WHERE token_hash = ? AND usado_em IS NULL AND expira_em > ?
                """,
                (digest, agora),
            ).fetchone()
            if not convite:
                return None, "Este convite já foi utilizado ou expirou."
            cursor = conexao.execute(
                """
                INSERT INTO usuarios_painel
                    (nome, usuario, senha_hash, permissoes,
                     administrador, ativo, criado_em)
                VALUES (?, ?, ?, ?, 0, 1, ?)
                """,
                (convite[1], usuario_login, senha_hash, convite[2], agora),
            )
            conexao.execute(
                "UPDATE convites_painel SET usado_em = ? WHERE id = ?",
                (agora, convite[0]),
            )
            return cursor.lastrowid, ""
    except sqlite3.IntegrityError:
        return None, "Esse nome de usuário já está em uso."


def listar_usuarios_e_convites():
    with closing(conectar()) as conexao, conexao:
        usuarios = conexao.execute(
            """
            SELECT id, nome, usuario, permissoes, administrador, ativo, ultimo_acesso
            FROM usuarios_painel ORDER BY administrador DESC, nome COLLATE NOCASE
            """
        ).fetchall()
        convites = conexao.execute(
            """
            SELECT id, nome, permissoes, criado_em, expira_em
            FROM convites_painel
            WHERE usado_em IS NULL AND expira_em > ?
            ORDER BY criado_em DESC
            """,
            (_agora(),),
        ).fetchall()
    return (
        [
            {
                "id": linha[0],
                "nome": linha[1],
                "usuario": linha[2],
                "permissoes": json.loads(linha[3]),
                "administrador": bool(linha[4]),
                "ativo": bool(linha[5]),
                "ultimo_acesso": linha[6],
            }
            for linha in usuarios
        ],
        [
            {
                "id": linha[0],
                "nome": linha[1],
                "permissoes": json.loads(linha[2]),
                "criado_em": linha[3],
                "expira_em": linha[4],
            }
            for linha in convites
        ],
    )


def criar_convite(nome, permissoes, criado_por):
    """Registra um convite e devolve o token (mostrado uma única vez)."""
    token = secrets.token_urlsafe(32)
    agora = datetime.now()
    with closing(conectar()) as conexao, conexao:
        conexao.execute(
            """
            INSERT INTO convites_painel
                (nome, token_hash, permissoes, criado_por, criado_em, expira_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                nome,
                token_hash(token),
                json.dumps(permissoes),
                criado_por,
                agora.strftime(FORMATO_DATA),
                (agora + timedelta(hours=VALIDADE_CONVITE_HORAS)).strftime(FORMATO_DATA),
            ),
        )
    return token


def listar_usuarios_online(minutos=2):
    limite = (datetime.now() - timedelta(minutes=minutos)).strftime(FORMATO_DATA)
    with closing(conectar()) as conexao, conexao:
        linhas = conexao.execute(
            """
            SELECT nome, usuario, ultimo_acesso
            FROM usuarios_painel
            WHERE ativo = 1 AND ultimo_acesso >= ?
            ORDER BY ultimo_acesso DESC
            """,
            (limite,),
        ).fetchall()
    return [
        {"nome": linha[0], "usuario": linha[1], "ultimo_acesso": linha[2]}
        for linha in linhas
    ]


def alterar_status_usuario(usuario_id, ativo):
    with closing(conectar()) as conexao, conexao:
        resultado = conexao.execute(
            "UPDATE usuarios_painel SET ativo = ? WHERE id = ? AND administrador = 0",
            (int(ativo), usuario_id),
        )
    return resultado.rowcount > 0


def alterar_permissoes_usuario(usuario_id, permissoes):
    with closing(conectar()) as conexao, conexao:
        resultado = conexao.execute(
            """
            UPDATE usuarios_painel SET permissoes = ?
            WHERE id = ? AND administrador = 0
            """,
            (json.dumps(permissoes), usuario_id),
        )
    return resultado.rowcount > 0


def cancelar_convite(convite_id):
    with closing(conectar()) as conexao, conexao:
        resultado = conexao.execute(
            "DELETE FROM convites_painel WHERE id = ? AND usado_em IS NULL",
            (convite_id,),
        )
    return resultado.rowcount > 0
