"""Acesso ao banco de dados para o histórico de movimentações e eventos."""
import sqlite3
from contextlib import closing

from estoque import conectar

FILTRO_AJUSTE_RAPIDO = "Ajuste rápido de estoque pela tela%"
FILTRO_TROCA_AUTOMATICA = "Baixa automática por troca detectada:%"

_COLUNAS_MOVIMENTACAO = """
    m.id, m.data, m.tipo, m.quantidade, m.ip_impressora, m.patrimonio,
    m.local_impressora, m.responsavel, m.observacao,
    t.marca, t.codigo, t.cor
"""


def _consultar(sql, parametros=()):
    with closing(conectar()) as conexao:
        conexao.row_factory = sqlite3.Row
        return conexao.execute(sql, parametros).fetchall()


def listar_movimentacoes(limite, offset):
    """Entradas e saídas manuais de toner, mais recentes primeiro, com o total."""
    registros = _consultar(
        f"""
        SELECT {_COLUNAS_MOVIMENTACAO}
        FROM movimentacoes m
        INNER JOIN toners t ON t.id = m.toner_id
        WHERE m.tipo IN ('ENTRADA', 'SAIDA')
          AND COALESCE(m.observacao, '') NOT LIKE ?
          AND NOT (m.tipo = 'SAIDA' AND COALESCE(m.observacao, '') LIKE ?)
        ORDER BY m.id DESC
        LIMIT ? OFFSET ?
        """,
        (FILTRO_AJUSTE_RAPIDO, FILTRO_TROCA_AUTOMATICA, limite, offset),
    )
    total = _consultar(
        """
        SELECT COUNT(*) AS total
        FROM movimentacoes
        WHERE tipo IN ('ENTRADA', 'SAIDA')
          AND COALESCE(observacao, '') NOT LIKE ?
          AND NOT (tipo = 'SAIDA' AND COALESCE(observacao, '') LIKE ?)
        """,
        (FILTRO_AJUSTE_RAPIDO, FILTRO_TROCA_AUTOMATICA),
    )[0]["total"]
    return registros, total


def listar_saidas_automaticas():
    return _consultar(
        f"""
        SELECT {_COLUNAS_MOVIMENTACAO}
        FROM movimentacoes m
        INNER JOIN toners t ON t.id = m.toner_id
        WHERE m.tipo = 'SAIDA' AND m.observacao LIKE ?
        ORDER BY m.id DESC
        """,
        (FILTRO_TROCA_AUTOMATICA,),
    )


def listar_offline_hoje():
    """Último evento OFFLINE de hoje por impressora."""
    return _consultar("""
        SELECT id, ip_impressora, patrimonio, modelo, evento,
               inicio_offline, data_registro, duracao_minutos
        FROM eventos_impressoras
        WHERE evento = 'OFFLINE'
        AND substr(data_registro, 7, 4) = strftime('%Y', 'now', 'localtime')
        AND substr(data_registro, 4, 2) = strftime('%m', 'now', 'localtime')
        AND substr(data_registro, 1, 2) = strftime('%d', 'now', 'localtime')
        AND id IN (
            SELECT MAX(id)
            FROM eventos_impressoras
            WHERE evento = 'OFFLINE'
              AND substr(data_registro, 7, 4) = strftime('%Y', 'now', 'localtime')
              AND substr(data_registro, 4, 2) = strftime('%m', 'now', 'localtime')
              AND substr(data_registro, 1, 2) = strftime('%d', 'now', 'localtime')
            GROUP BY ip_impressora, substr(data_registro, 1, 10)
        )
        ORDER BY id DESC
    """)
