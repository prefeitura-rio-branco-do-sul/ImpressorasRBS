import sqlite3
from contextlib import closing
from datetime import datetime

from estoque import conectar


def criar_tabelas_pedidos(conexao):
    conexao.executescript("""
        CREATE TABLE IF NOT EXISTS sugestoes_estoque (
            semana TEXT PRIMARY KEY,
            criada_em TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ABERTA',
            verificar_em TEXT,
            adiada_em TEXT,
            adiada_por TEXT
        );
        CREATE TABLE IF NOT EXISTS sugestoes_estoque_itens (
            semana TEXT NOT NULL,
            toner_id INTEGER NOT NULL,
            marca TEXT NOT NULL,
            codigo TEXT NOT NULL,
            cor TEXT NOT NULL,
            modelos TEXT NOT NULL,
            estoque INTEGER NOT NULL,
            minimo INTEGER NOT NULL,
            PRIMARY KEY (semana, toner_id)
        );
        CREATE TABLE IF NOT EXISTS pedidos_estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            semana TEXT NOT NULL UNIQUE,
            criado_em TEXT NOT NULL,
            responsavel TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'LEGADO',
            destinatario TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS pedidos_estoque_itens (
            pedido_id INTEGER NOT NULL,
            toner_id INTEGER NOT NULL,
            quantidade INTEGER NOT NULL CHECK (quantidade > 0),
            recebida INTEGER NOT NULL DEFAULT 0 CHECK (recebida >= 0 AND recebida <= quantidade),
            cancelada INTEGER NOT NULL DEFAULT 0 CHECK (cancelada >= 0),
            cancelada_em TEXT,
            cancelada_por TEXT,
            PRIMARY KEY (pedido_id, toner_id)
        );
    """)
    colunas_sugestao = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(sugestoes_estoque)")
    }
    if "status" not in colunas_sugestao:
        conexao.execute(
            "ALTER TABLE sugestoes_estoque ADD COLUMN status TEXT NOT NULL DEFAULT 'ABERTA'"
        )
    if "verificar_em" not in colunas_sugestao:
        conexao.execute(
            "ALTER TABLE sugestoes_estoque ADD COLUMN verificar_em TEXT"
        )
    if "adiada_em" not in colunas_sugestao:
        conexao.execute(
            "ALTER TABLE sugestoes_estoque ADD COLUMN adiada_em TEXT"
        )
    if "adiada_por" not in colunas_sugestao:
        conexao.execute(
            "ALTER TABLE sugestoes_estoque ADD COLUMN adiada_por TEXT"
        )
    colunas_pedido = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(pedidos_estoque)")
    }
    if "status" not in colunas_pedido:
        conexao.execute(
            "ALTER TABLE pedidos_estoque ADD COLUMN status TEXT NOT NULL DEFAULT 'LEGADO'"
        )
    if "destinatario" not in colunas_pedido:
        conexao.execute(
            "ALTER TABLE pedidos_estoque ADD COLUMN destinatario TEXT NOT NULL DEFAULT ''"
        )
    colunas_itens = {
        linha[1] for linha in conexao.execute("PRAGMA table_info(pedidos_estoque_itens)")
    }
    if "cancelada" not in colunas_itens:
        conexao.execute(
            "ALTER TABLE pedidos_estoque_itens ADD COLUMN cancelada INTEGER NOT NULL DEFAULT 0"
        )
    if "cancelada_em" not in colunas_itens:
        conexao.execute(
            "ALTER TABLE pedidos_estoque_itens ADD COLUMN cancelada_em TEXT"
        )
    if "cancelada_por" not in colunas_itens:
        conexao.execute(
            "ALTER TABLE pedidos_estoque_itens ADD COLUMN cancelada_por TEXT"
        )


def listar_sugestoes_e_pedidos():
    with closing(conectar()) as conexao:
        conexao.row_factory = sqlite3.Row
        sugestoes = []
        for linha in conexao.execute("""
            SELECT s.semana, s.criada_em, s.status, s.verificar_em,
                s.adiada_em, s.adiada_por
            FROM sugestoes_estoque s
            ORDER BY s.semana DESC
        """).fetchall():
            sugestao = dict(linha)
            itens = [dict(item) for item in conexao.execute("""
                SELECT i.*, t.ativo, t.estoque AS estoque_atual,
                    t.estoque_minimo AS minimo_atual,
                    COALESCE(p.quantidade_pendente, 0) AS quantidade_pendente
                FROM sugestoes_estoque_itens i
                JOIN toners t ON t.id = i.toner_id
                LEFT JOIN (
                    SELECT pi.toner_id,
                        SUM(pi.quantidade - pi.recebida - pi.cancelada) AS quantidade_pendente
                    FROM pedidos_estoque_itens pi
                    JOIN pedidos_estoque p ON p.id = pi.pedido_id
                    WHERE p.status = 'ACEITO'
                        AND pi.quantidade > pi.recebida + pi.cancelada
                    GROUP BY pi.toner_id
                ) p ON p.toner_id = i.toner_id
                WHERE i.semana = ? ORDER BY i.marca, i.codigo, i.cor
            """, (linha["semana"],))]
            for item in itens:
                item["quantidade_sugerida"] = max(
                    0,
                    item["minimo_atual"]
                    - item["estoque_atual"]
                    - item["quantidade_pendente"],
                )
            sugestao["itens"] = itens
            sugestoes.append(sugestao)
        pedidos = []
        for linha in conexao.execute(
            "SELECT id, semana, criado_em, responsavel FROM pedidos_estoque "
            "WHERE status = 'ACEITO' ORDER BY id DESC"
        ).fetchall():
            pedido = dict(linha)
            pedido["itens"] = [dict(item) for item in conexao.execute("""
                SELECT i.toner_id, i.quantidade, i.recebida, i.cancelada,
                    i.cancelada_em, i.cancelada_por,
                    t.marca, t.codigo, t.cor, t.ativo
                FROM pedidos_estoque_itens i JOIN toners t ON t.id = i.toner_id
                WHERE i.pedido_id = ? ORDER BY t.marca, t.codigo, t.cor
            """, (linha["id"],))]
            pedidos.append(pedido)
        solicitacoes = []
        for linha in conexao.execute("""
            SELECT id, semana, criado_em, responsavel, destinatario, status
            FROM pedidos_estoque
            WHERE status IN ('ENVIANDO', 'AGUARDANDO_ACEITE')
            ORDER BY id DESC
        """).fetchall():
            solicitacao = dict(linha)
            solicitacao["itens"] = [dict(item) for item in conexao.execute("""
                SELECT i.toner_id, i.quantidade, t.marca, t.codigo, t.cor
                FROM pedidos_estoque_itens i JOIN toners t ON t.id = i.toner_id
                WHERE i.pedido_id = ? ORDER BY t.marca, t.codigo, t.cor
            """, (linha["id"],))]
            solicitacoes.append(solicitacao)
    return {
        "sugestoes": sugestoes,
        "solicitacoes": solicitacoes,
        "pedidos": pedidos,
    }


def _validar_itens(itens):
    if not isinstance(itens, list) or not itens:
        raise ValueError("Informe ao menos um toner e uma quantidade.")
    resultado = {}
    for item in itens:
        if not isinstance(item, dict):
            raise ValueError("Item inválido.")
        toner_id, quantidade = item.get("toner_id"), item.get("quantidade")
        if (
            type(toner_id) is not int or toner_id <= 0
            or type(quantidade) is not int or not 0 < quantidade <= 1000000
            or toner_id in resultado
        ):
            raise ValueError("Informe quantidades inteiras positivas e toners sem repetição.")
        resultado[toner_id] = quantidade
    return resultado


def adiar_sugestao_pedido(semana, data_verificacao, responsavel, hoje=None):
    if not isinstance(data_verificacao, str):
        raise ValueError("Informe uma data válida para a nova verificação.")
    try:
        data = datetime.strptime(data_verificacao, "%Y-%m-%d").date()
    except ValueError as erro:
        raise ValueError("Informe uma data válida para a nova verificação.") from erro
    if data.isoformat() != data_verificacao:
        raise ValueError("Informe uma data válida para a nova verificação.")
    hoje = hoje or datetime.now().date()
    if data <= hoje:
        raise ValueError("A nova verificação deve ser marcada para uma data futura.")

    adiada_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        sugestao = conexao.execute(
            "SELECT status FROM sugestoes_estoque WHERE semana = ?",
            (semana,),
        ).fetchone()
        mais_recente = conexao.execute(
            "SELECT MAX(semana) FROM sugestoes_estoque"
        ).fetchone()[0]
        if not sugestao or sugestao["status"] != "ABERTA" or semana != mais_recente:
            raise ValueError("Somente a sugestão mais recente e aberta pode ser adiada.")
        if conexao.execute(
            "SELECT 1 FROM sugestoes_estoque WHERE status = 'ADIADA'"
        ).fetchone():
            raise ValueError("Já existe uma sugestão aguardando nova verificação.")
        if conexao.execute(
            "SELECT 1 FROM sugestoes_estoque WHERE semana = ?",
            (data_verificacao,),
        ).fetchone():
            raise ValueError("Já existe uma sugestão para essa data.")
        atualizada = conexao.execute("""
            UPDATE sugestoes_estoque
            SET status = 'ADIADA', verificar_em = ?, adiada_em = ?, adiada_por = ?
            WHERE semana = ? AND status = 'ABERTA'
        """, (data_verificacao, adiada_em, responsavel, semana))
        if atualizada.rowcount != 1:
            raise RuntimeError("Não foi possível adiar a sugestão.")


def criar_solicitacao_pedido(semana, itens, responsavel, destinatario):
    quantidades = _validar_itens(itens)
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        if not conexao.execute(
            "SELECT 1 FROM sugestoes_estoque WHERE semana = ? AND status = 'ABERTA'",
            (semana,),
        ).fetchone():
            raise ValueError("Sugestão não encontrada.")
        semana_mais_recente = conexao.execute(
            "SELECT MAX(semana) FROM sugestoes_estoque"
        ).fetchone()[0]
        if semana != semana_mais_recente:
            raise ValueError("Esta sugestão foi arquivada. Use a sugestão mais recente.")
        validos = {
            linha[0] for linha in conexao.execute("""
                SELECT i.toner_id FROM sugestoes_estoque_itens i
                JOIN toners t ON t.id = i.toner_id
                WHERE i.semana = ? AND t.ativo = 1
            """, (semana,))
        }
        if not quantidades.keys() <= validos:
            raise ValueError("A sugestão contém toner inválido ou inativo.")
        existente = conexao.execute(
            "SELECT id, status FROM pedidos_estoque WHERE semana = ?", (semana,)
        ).fetchone()
        criado_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        if existente:
            if existente["status"] != "LEGADO":
                raise ValueError("Esta sugestão já foi enviada ou aceita.")
            pedido_id = existente["id"]
            conexao.execute(
                "DELETE FROM pedidos_estoque_itens WHERE pedido_id = ?", (pedido_id,)
            )
            conexao.execute("""
                UPDATE pedidos_estoque
                SET criado_em = ?, responsavel = ?, status = 'ENVIANDO', destinatario = ?
                WHERE id = ?
            """, (criado_em, responsavel, destinatario, pedido_id))
        else:
            cursor = conexao.execute("""
                INSERT INTO pedidos_estoque
                    (semana, criado_em, responsavel, status, destinatario)
                VALUES (?, ?, ?, 'ENVIANDO', ?)
            """, (semana, criado_em, responsavel, destinatario))
            pedido_id = cursor.lastrowid
        conexao.executemany(
            "INSERT INTO pedidos_estoque_itens (pedido_id, toner_id, quantidade) VALUES (?, ?, ?)",
            [(pedido_id, toner_id, quantidade) for toner_id, quantidade in quantidades.items()],
        )
        conexao.execute(
            "UPDATE sugestoes_estoque SET status = 'ENVIANDO' WHERE semana = ?",
            (semana,),
        )
    return pedido_id


def marcar_solicitacao_enviada(pedido_id):
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        pedido = conexao.execute(
            "SELECT semana FROM pedidos_estoque WHERE id = ? AND status = 'ENVIANDO'",
            (pedido_id,),
        ).fetchone()
        if not pedido:
            raise ValueError("A solicitação não está aguardando envio.")
        atualizada = conexao.execute(
            "UPDATE pedidos_estoque SET status = 'AGUARDANDO_ACEITE' WHERE id = ?",
            (pedido_id,),
        )
        conexao.execute(
            "UPDATE sugestoes_estoque SET status = 'AGUARDANDO_ACEITE' WHERE semana = ?",
            (pedido["semana"],),
        )
        if atualizada.rowcount != 1:
            raise RuntimeError("Não foi possível registrar o envio da solicitação.")


def cancelar_solicitacao_envio(pedido_id):
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        pedido = conexao.execute(
            "SELECT semana FROM pedidos_estoque WHERE id = ? AND status = 'ENVIANDO'",
            (pedido_id,),
        ).fetchone()
        if not pedido:
            return
        conexao.execute(
            "DELETE FROM pedidos_estoque_itens WHERE pedido_id = ?", (pedido_id,)
        )
        conexao.execute("DELETE FROM pedidos_estoque WHERE id = ?", (pedido_id,))
        conexao.execute(
            "UPDATE sugestoes_estoque SET status = 'ABERTA' WHERE semana = ?",
            (pedido["semana"],),
        )


def decidir_solicitacao_pedido(pedido_id, decisao):
    if decisao not in ("aceitar", "recusar"):
        raise ValueError("Decisão inválida.")
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        pedido = conexao.execute(
            "SELECT semana FROM pedidos_estoque "
            "WHERE id = ? AND status = 'AGUARDANDO_ACEITE'",
            (pedido_id,),
        ).fetchone()
        if not pedido:
            raise ValueError("Solicitação não encontrada ou já decidida.")
        if decisao == "aceitar":
            atualizada = conexao.execute(
                "UPDATE pedidos_estoque SET status = 'ACEITO' WHERE id = ?",
                (pedido_id,),
            )
            conexao.execute(
                "UPDATE sugestoes_estoque SET status = 'ACEITA' WHERE semana = ?",
                (pedido["semana"],),
            )
            if atualizada.rowcount != 1:
                raise RuntimeError("Não foi possível registrar o aceite da solicitação.")
        else:
            conexao.execute(
                "DELETE FROM pedidos_estoque_itens WHERE pedido_id = ?", (pedido_id,)
            )
            conexao.execute("DELETE FROM pedidos_estoque WHERE id = ?", (pedido_id,))
            conexao.execute(
                "UPDATE sugestoes_estoque SET status = 'RECUSADA' WHERE semana = ?",
                (pedido["semana"],),
            )


def cancelar_pendencias_pedido(pedido_id, responsavel):
    cancelada_em = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        pedido = conexao.execute(
            "SELECT status FROM pedidos_estoque WHERE id = ?", (pedido_id,)
        ).fetchone()
        if not pedido or pedido["status"] not in ("ACEITO", "LEGADO"):
            raise ValueError("Somente pedidos aceitos ou legados podem ter saldo cancelado.")
        itens = conexao.execute("""
            SELECT i.toner_id, i.quantidade - i.recebida - i.cancelada AS quantidade,
                t.marca, t.codigo, t.cor
            FROM pedidos_estoque_itens i
            JOIN toners t ON t.id = i.toner_id
            WHERE i.pedido_id = ?
                AND i.quantidade > i.recebida + i.cancelada
            ORDER BY t.marca, t.codigo, t.cor
        """, (pedido_id,)).fetchall()
        if not itens:
            raise ValueError("Este pedido não tem saldo pendente para cancelar.")
        for item in itens:
            conexao.execute("""
                UPDATE pedidos_estoque_itens
                SET cancelada = cancelada + ?, cancelada_em = ?, cancelada_por = ?
                WHERE pedido_id = ? AND toner_id = ?
            """, (
                item["quantidade"],
                cancelada_em,
                responsavel,
                pedido_id,
                item["toner_id"],
            ))
    return [dict(item) for item in itens]


def receber_pedido(pedido_id, itens, responsavel):
    quantidades = _validar_itens(itens)
    data = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with closing(conectar()) as conexao, conexao:
        conexao.row_factory = sqlite3.Row
        conexao.execute("BEGIN IMMEDIATE")
        pedido = conexao.execute(
            "SELECT status FROM pedidos_estoque WHERE id = ?", (pedido_id,)
        ).fetchone()
        if not pedido or pedido["status"] != "ACEITO":
            raise ValueError("O pedido precisa ser aceito antes do recebimento.")
        existentes = {
            linha[0]: linha[1:] for linha in conexao.execute("""
                SELECT i.toner_id, i.quantidade, i.recebida, i.cancelada, t.ativo
                FROM pedidos_estoque_itens i JOIN toners t ON t.id = i.toner_id
                WHERE i.pedido_id = ?
            """, (pedido_id,))
        }
        for toner_id, quantidade in quantidades.items():
            if toner_id not in existentes:
                raise ValueError("Toner não pertence a este pedido.")
            pedido, recebida, cancelada, ativo = existentes[toner_id]
            if not ativo:
                raise ValueError("Reative o toner antes de registrar o recebimento.")
            if quantidade > pedido - recebida - cancelada:
                raise ValueError("A quantidade recebida excede o saldo pendente do pedido.")
        for toner_id, quantidade in quantidades.items():
            conexao.execute(
                "UPDATE pedidos_estoque_itens SET recebida = recebida + ? WHERE pedido_id = ? AND toner_id = ?",
                (quantidade, pedido_id, toner_id),
            )
            conexao.execute(
                "UPDATE toners SET estoque = estoque + ? WHERE id = ?", (quantidade, toner_id)
            )
            conexao.execute("""
                INSERT INTO movimentacoes (toner_id, tipo, quantidade, data, responsavel, observacao)
                VALUES (?, 'ENTRADA', ?, ?, ?, ?)
            """, (toner_id, quantidade, data, responsavel, f"Recebimento do pedido #{pedido_id}"))
