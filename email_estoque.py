import logging
import os
import smtplib
import sqlite3
from contextlib import closing
from datetime import datetime
from email.message import EmailMessage
from threading import Thread
from time import sleep

from config.configuracoes import SMTP_HOST, SMTP_PORTA, SMTP_TIMEOUT_ESTOQUE
from estoque import conectar


logger = logging.getLogger(__name__)


class ErroEnvioEmailEstoque(RuntimeError):
    pass


def gerar_sugestao_semanal(agora=None):
    agora = agora or datetime.now()
    semana = agora.date().isoformat()
    with closing(conectar()) as conexao, conexao:
        conexao.execute("BEGIN IMMEDIATE")
        sugestao_adiada = conexao.execute("""
            SELECT 1 FROM sugestoes_estoque
            WHERE status = 'ADIADA' AND verificar_em <= ?
            LIMIT 1
        """, (semana,)).fetchone()
        if sugestao_adiada:
            conexao.execute("""
                UPDATE sugestoes_estoque SET status = 'ARQUIVADA'
                WHERE status = 'ADIADA' AND verificar_em <= ?
            """, (semana,))
            existente = conexao.execute(
                "SELECT status FROM sugestoes_estoque WHERE semana = ?", (semana,)
            ).fetchone()
            if existente and existente[0] != "ABERTA":
                raise sqlite3.IntegrityError(
                    "Já existe uma sugestão processada para a data de verificação."
                )
            if existente:
                conexao.execute(
                    "DELETE FROM sugestoes_estoque_itens WHERE semana = ?", (semana,)
                )
                conexao.execute("""
                    UPDATE sugestoes_estoque SET criada_em = ?, verificar_em = NULL,
                        adiada_em = NULL, adiada_por = NULL
                    WHERE semana = ?
                """, (agora.isoformat(), semana))
            else:
                conexao.execute(
                    "INSERT INTO sugestoes_estoque (semana, criada_em) VALUES (?, ?)",
                    (semana, agora.isoformat()),
                )
            _inserir_itens_sugestao(conexao, semana)
            logger.info("Nova sugestão gerada após adiamento para %s.", semana)
            return True

        if conexao.execute("""
            SELECT 1 FROM sugestoes_estoque
            WHERE status = 'ADIADA' AND verificar_em > ?
            LIMIT 1
        """, (semana,)).fetchone():
            return False
        if agora.weekday() != 0 or agora.hour < 8:
            return False
        if conexao.execute(
            "SELECT 1 FROM sugestoes_estoque WHERE semana = ?", (semana,)
        ).fetchone():
            return False
        conexao.execute(
            "INSERT INTO sugestoes_estoque (semana, criada_em) VALUES (?, ?)",
            (semana, agora.isoformat()),
        )
        _inserir_itens_sugestao(conexao, semana)
    logger.info("Sugestão semanal de estoque gerada para %s.", semana)
    return True


def _inserir_itens_sugestao(conexao, semana):
    conexao.execute("""
        INSERT INTO sugestoes_estoque_itens
            (semana, toner_id, marca, codigo, cor, modelos, estoque, minimo)
        SELECT ?, id, marca, codigo, cor, modelos_compativeis, estoque, estoque_minimo
        FROM toners WHERE ativo = 1 AND estoque <= estoque_minimo
    """, (semana,))


def _mensagem_solicitacao(semana, responsavel, itens, remetente, destinatario):
    mensagem = EmailMessage()
    mensagem["Subject"] = f"Solicitação de aprovação de toners — {semana}"
    mensagem["From"] = remetente
    mensagem["To"] = destinatario
    linhas = [
        "Olá!",
        "",
        f"Segue a solicitação de reposição preparada por {responsavel}:",
        "",
    ]
    for marca, codigo, cor, quantidade in itens:
        unidade = "unidade" if quantidade == 1 else "unidades"
        linhas.append(f"- Toner {marca} {codigo} ({cor}) — {quantidade} {unidade}")
    linhas.extend([
        "",
        "Por favor, informe ao responsável se esta solicitação foi aceita ou recusada.",
        "Nenhuma compra foi realizada automaticamente.",
    ])
    mensagem.set_content("\n".join(linhas))
    return mensagem


def enviar_email_solicitacao(pedido_id):
    with closing(conectar()) as conexao:
        conexao.row_factory = sqlite3.Row
        itens_db = conexao.execute("""
            SELECT p.semana, p.responsavel, p.destinatario,
                t.marca, t.codigo, t.cor, i.quantidade
            FROM pedidos_estoque p
            JOIN pedidos_estoque_itens i ON i.pedido_id = p.id
            JOIN toners t ON t.id = i.toner_id
            WHERE p.id = ? AND p.status = 'ENVIANDO'
            ORDER BY t.marca, t.codigo, t.cor
        """, (pedido_id,)).fetchall()
    if not itens_db:
        raise ValueError("Solicitação não encontrada ou não aguarda envio.")

    remetente = os.environ.get("GMAIL_REMETENTE")
    senha = os.environ.get("GMAIL_SENHA_APP")
    destinatario = itens_db[0]["destinatario"]
    if not remetente or not senha or not destinatario:
        raise ErroEnvioEmailEstoque(
            "Configure GMAIL_REMETENTE, GMAIL_SENHA_APP e EMAIL_ESTOQUE_SEMANAL."
        )
    itens = [
        (item["marca"], item["codigo"], item["cor"], item["quantidade"])
        for item in itens_db
    ]
    mensagem = _mensagem_solicitacao(
        itens_db[0]["semana"],
        itens_db[0]["responsavel"],
        itens,
        remetente,
        destinatario,
    )
    try:
        with smtplib.SMTP(
            SMTP_HOST, SMTP_PORTA, timeout=SMTP_TIMEOUT_ESTOQUE
        ) as servidor:
            servidor.starttls()
            servidor.login(remetente, senha)
            servidor.send_message(mensagem)
    except (OSError, smtplib.SMTPException) as erro:
        logger.exception("Falha ao enviar solicitação de reposição de toners.")
        raise ErroEnvioEmailEstoque(
            "Não foi possível enviar o e-mail ao responsável."
        ) from erro
    logger.info("Solicitação de reposição enviada para %s.", destinatario)


def _executar_agendador():
    while True:
        try:
            gerar_sugestao_semanal()
        except sqlite3.Error:
            logger.exception(
                "Falha ao gerar a sugestão semanal de estoque; nova tentativa em 5 minutos."
            )
            sleep(300)
        else:
            sleep(60)


def iniciar_agendador_estoque():
    Thread(
        target=_executar_agendador,
        daemon=True,
        name="sugestao-estoque-semanal",
    ).start()
