import asyncio
import logging
import sqlite3
import zipfile
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta
from threading import Thread
from time import sleep
from uuid import uuid4

from openpyxl.utils.exceptions import InvalidFileException

from contadores_cor_kyocera import consultar_contadores_cor, modelo_compativel
from estoque import conectar
from suprimentos_snmp import consultar_contador_paginas
from utils.datas import limites_mes


logger = logging.getLogger(__name__)
INTERVALO_TENTATIVA = timedelta(minutes=30)
LIMITE_RESERVA = timedelta(hours=1)


def criar_tabelas_contadores(conexao):
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS leituras_contadores_mensais (
            data TEXT NOT NULL,
            chave TEXT NOT NULL,
            nome TEXT NOT NULL,
            grupo TEXT NOT NULL,
            ip TEXT NOT NULL,
            patrimonio TEXT NOT NULL,
            serie TEXT NOT NULL,
            modelo TEXT NOT NULL,
            contador INTEGER,
            oid TEXT,
            coletado_em TEXT NOT NULL,
            erro TEXT,
            PRIMARY KEY (data, chave)
        )
    """)
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS coletas_contadores_mensais (
            data TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            iniciado_em TEXT NOT NULL,
            finalizado_em TEXT
        )
    """)
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS leituras_cores_mensais (
            data TEXT NOT NULL,
            chave TEXT NOT NULL,
            nome TEXT NOT NULL,
            grupo TEXT NOT NULL,
            ip TEXT NOT NULL,
            patrimonio TEXT NOT NULL,
            serie TEXT NOT NULL,
            modelo TEXT NOT NULL,
            preto_branco INTEGER,
            nivel_1 INTEGER,
            nivel_2 INTEGER,
            nivel_3 INTEGER,
            coletado_em TEXT NOT NULL,
            erro TEXT,
            PRIMARY KEY (data, chave)
        )
    """)


def identificar_cadastros(cadastros):
    def normalizar(valor):
        return str(valor or "").strip().upper()

    patrimonios = Counter(normalizar(item.get("patrimonio_planilha")) for item in cadastros)
    series = Counter(normalizar(item.get("serie_planilha")) for item in cadastros)
    identificados = {}
    for item in cadastros:
        patrimonio = normalizar(item.get("patrimonio_planilha"))
        serie = normalizar(item.get("serie_planilha"))
        if patrimonio and patrimonios[patrimonio] == 1:
            chave = "patrimonio:" + patrimonio
        elif serie and series[serie] == 1:
            chave = "serie:" + serie
        else:
            chave = "ip:" + item["ip"]
        identificados[chave] = item
    return identificados


def _reservar(data, agora):
    token = uuid4().hex
    with closing(conectar()) as conexao, conexao:
        conexao.execute("BEGIN IMMEDIATE")
        anterior = conexao.execute(
            "SELECT iniciado_em, finalizado_em FROM coletas_contadores_mensais WHERE data = ?",
            (data,),
        ).fetchone()
        if anterior:
            iniciado, finalizado = anterior
            if finalizado:
                if datetime.fromisoformat(finalizado) > agora - INTERVALO_TENTATIVA:
                    return None
            elif datetime.fromisoformat(iniciado) > agora - LIMITE_RESERVA:
                return None
        conexao.execute("""
            INSERT INTO coletas_contadores_mensais (data, token, iniciado_em, finalizado_em)
            VALUES (?, ?, ?, NULL)
            ON CONFLICT(data) DO UPDATE SET
                token = excluded.token, iniciado_em = excluded.iniciado_em, finalizado_em = NULL
        """, (data, token, agora.isoformat()))
    return token


def _registrar_leitura(data, token, chave, item, agora, resultado, erro):
    with closing(conectar()) as conexao, conexao:
        conexao.execute("BEGIN IMMEDIATE")
        reserva = conexao.execute(
            "SELECT 1 FROM coletas_contadores_mensais WHERE data = ? AND token = ? AND finalizado_em IS NULL",
            (data, token),
        ).fetchone()
        if not reserva:
            raise RuntimeError("A reserva da coleta mensal expirou.")
        conexao.execute("""
            INSERT INTO leituras_contadores_mensais
                (data, chave, nome, grupo, ip, patrimonio, serie, modelo,
                 contador, oid, coletado_em, erro)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(data, chave) DO UPDATE SET
                nome = excluded.nome, grupo = excluded.grupo, ip = excluded.ip,
                patrimonio = excluded.patrimonio, serie = excluded.serie,
                modelo = excluded.modelo, contador = excluded.contador,
                oid = excluded.oid, coletado_em = excluded.coletado_em, erro = excluded.erro
            WHERE leituras_contadores_mensais.contador IS NULL
        """, (
            data, chave, item["nome"], item.get("grupo") or "", item["ip"],
            item.get("patrimonio_planilha") or "", item.get("serie_planilha") or "",
            item.get("modelo_cadastro") or "", resultado["contador"] if resultado else None,
            resultado["oid"] if resultado else None, agora.isoformat(timespec="seconds"), erro,
        ))


async def _consultar_pendentes(data, token, cadastros, consulta, relogio):
    limite = asyncio.Semaphore(8)

    async def consultar(chave, item):
        async with limite:
            try:
                resultado = await asyncio.wait_for(consulta(item["ip"]), timeout=8)
                contador = resultado["contador"]
                if isinstance(contador, bool) or not isinstance(contador, int) or contador < 0:
                    raise ValueError("A impressora retornou um contador inválido.")
                erro = None
            except asyncio.TimeoutError:
                resultado, erro = None, "Tempo esgotado ao consultar a impressora."
            except (RuntimeError, ValueError) as excecao:
                resultado, erro = None, str(excecao)
            agora = relogio()
            if agora.date().isoformat() != data:
                logger.warning("Leitura mensal não registrada: a consulta terminou em outro dia.")
                return
            _registrar_leitura(data, token, chave, item, agora, resultado, erro)

    await asyncio.gather(*(consultar(chave, item) for chave, item in cadastros.items()))


async def _consultar_cores_pendentes(data, token, cadastros, consulta, relogio):
    limite = asyncio.Semaphore(4)

    async def consultar(chave, item):
        async with limite:
            try:
                resultado = await asyncio.to_thread(consulta, item["ip"])
                if not isinstance(resultado, dict):
                    raise ValueError("Resposta inválida dos contadores de cor.")
                for categoria in ("preto_branco", "nivel_1", "nivel_2", "nivel_3"):
                    valor = resultado.get(categoria)
                    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
                        raise ValueError(f"Contador {categoria} inválido.")
                erro = None
            except (RuntimeError, ValueError) as excecao:
                resultado, erro = None, str(excecao)
                logger.warning("Falha na coleta de cor da impressora %s: %s", item["ip"], erro)
            agora = relogio()
            if agora.date().isoformat() != data:
                logger.warning("Leitura de cor não registrada: a consulta terminou em outro dia.")
                return
            with closing(conectar()) as conexao, conexao:
                conexao.execute("BEGIN IMMEDIATE")
                reserva = conexao.execute(
                    "SELECT 1 FROM coletas_contadores_mensais WHERE data = ? AND token = ? AND finalizado_em IS NULL",
                    (data, token),
                ).fetchone()
                if not reserva:
                    raise RuntimeError("A reserva da coleta mensal expirou.")
                conexao.execute("""
                    INSERT INTO leituras_cores_mensais
                        (data, chave, nome, grupo, ip, patrimonio, serie, modelo, preto_branco,
                         nivel_1, nivel_2, nivel_3, coletado_em, erro)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(data, chave) DO UPDATE SET
                        nome = excluded.nome, grupo = excluded.grupo, ip = excluded.ip, patrimonio = excluded.patrimonio,
                        serie = excluded.serie, modelo = excluded.modelo,
                        preto_branco = excluded.preto_branco, nivel_1 = excluded.nivel_1,
                        nivel_2 = excluded.nivel_2, nivel_3 = excluded.nivel_3,
                        coletado_em = excluded.coletado_em, erro = excluded.erro
                    WHERE leituras_cores_mensais.preto_branco IS NULL
                """, (
                    data, chave, item["nome"], item.get("grupo") or "", item["ip"], item.get("patrimonio_planilha") or "",
                    item.get("serie_planilha") or "", item.get("modelo_cadastro") or "",
                    resultado["preto_branco"] if resultado else None,
                    resultado["nivel_1"] if resultado else None,
                    resultado["nivel_2"] if resultado else None,
                    resultado["nivel_3"] if resultado else None,
                    agora.isoformat(timespec="seconds"), erro,
                ))

    await asyncio.gather(*(consultar(chave, item) for chave, item in cadastros.items()))


async def _coletar_pendentes(data, token, pendentes, cores, consulta, consulta_cor, relogio):
    await asyncio.gather(
        _consultar_pendentes(data, token, pendentes, consulta, relogio),
        _consultar_cores_pendentes(data, token, cores, consulta_cor, relogio),
    )


def verificar_coleta_mensal(obter_cadastros, agora=None, consulta=None, relogio=None, consulta_cor=None):
    agora = agora or datetime.now()
    if agora.day != 1:
        return False
    data = agora.date().isoformat()
    token = _reservar(data, agora)
    if not token:
        return False
    relogio = relogio or datetime.now
    try:
        cadastros = identificar_cadastros(obter_cadastros())
        with closing(conectar()) as conexao:
            concluidas = {
                linha[0] for linha in conexao.execute(
                    "SELECT chave FROM leituras_contadores_mensais WHERE data = ? AND contador IS NOT NULL",
                    (data,),
                )
            }
            cores_concluidas = {
                linha[0] for linha in conexao.execute(
                    "SELECT chave FROM leituras_cores_mensais WHERE data = ? AND preto_branco IS NOT NULL",
                    (data,),
                )
            }
        pendentes = {chave: item for chave, item in cadastros.items() if chave not in concluidas}
        cores = {
            chave: item for chave, item in cadastros.items()
            if chave not in cores_concluidas and modelo_compativel(item.get("modelo_cadastro"))
        }
        asyncio.run(_coletar_pendentes(
            data, token, pendentes, cores, consulta or consultar_contador_paginas,
            consulta_cor or consultar_contadores_cor, relogio,
        ))
        logger.info("Coleta mensal concluída: %s contadores gerais e %s de cor consultados.", len(pendentes), len(cores))
        return True
    finally:
        with closing(conectar()) as conexao, conexao:
            conexao.execute(
                "UPDATE coletas_contadores_mensais SET finalizado_em = ? WHERE data = ? AND token = ?",
                (relogio().isoformat(), data, token),
            )


def _executar_agendador(obter_cadastros):
    while True:
        try:
            verificar_coleta_mensal(obter_cadastros)
        except (OSError, sqlite3.Error, ValueError, RuntimeError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Falha na coleta mensal de contadores; nova tentativa será realizada.")
        sleep(60)


def iniciar_agendador_contadores(obter_cadastros):
    Thread(
        target=_executar_agendador, args=(obter_cadastros,),
        daemon=True, name="contadores-mensais",
    ).start()


def gerar_relatorio(mes, cadastros):
    inicio, fim = limites_mes(mes)
    data_inicio, data_fim = inicio.date().isoformat(), fim.date().isoformat()
    with closing(conectar()) as conexao:
        conexao.row_factory = sqlite3.Row
        leituras = conexao.execute("""
            SELECT * FROM leituras_contadores_mensais
            WHERE data IN (?, ?) ORDER BY data
        """, (data_inicio, data_fim)).fetchall()
        leituras_cor = conexao.execute("""
            SELECT * FROM leituras_cores_mensais
            WHERE data IN (?, ?) ORDER BY data
        """, (data_inicio, data_fim)).fetchall()

    por_chave = {chave: {"cadastro": item} for chave, item in identificar_cadastros(cadastros).items()}
    for leitura in leituras:
        item = por_chave.setdefault(leitura["chave"], {})
        item[leitura["data"]] = dict(leitura)
    for leitura in leituras_cor:
        item = por_chave.setdefault(leitura["chave"], {})
        item["cor_" + leitura["data"]] = dict(leitura)

    itens = []
    for chave, dados in por_chave.items():
        primeira, ultima = dados.get(data_inicio), dados.get(data_fim)
        cadastro = dados.get("cadastro")
        primeira_cor, ultima_cor = dados.get("cor_" + data_inicio), dados.get("cor_" + data_fim)
        referencia = ultima or primeira or ultima_cor or primeira_cor
        if referencia:
            nome, grupo, ip = referencia["nome"], referencia["grupo"], referencia["ip"]
            patrimonio, modelo = referencia["patrimonio"], referencia["modelo"]
        else:
            nome, grupo, ip = cadastro["nome"], cadastro.get("grupo") or "", cadastro["ip"]
            patrimonio, modelo = cadastro.get("patrimonio_planilha") or "", cadastro.get("modelo_cadastro") or ""

        valor_inicio = primeira["contador"] if primeira else None
        valor_fim = ultima["contador"] if ultima else None
        total = None
        if valor_inicio is None or valor_fim is None:
            estado = "Sem leitura de início ou fim"
        elif (
            primeira["oid"] != ultima["oid"]
            or (primeira["serie"] and ultima["serie"] and primeira["serie"].upper() != ultima["serie"].upper())
            or (primeira["patrimonio"] and ultima["patrimonio"] and primeira["patrimonio"].upper() != ultima["patrimonio"].upper())
            or (primeira["modelo"] and ultima["modelo"] and primeira["modelo"].upper() != ultima["modelo"].upper())
        ):
            estado = "Equipamento ou contador alterado; conferir"
        elif valor_fim < valor_inicio:
            estado = "Contador diminuiu; conferir"
        else:
            total = valor_fim - valor_inicio
            atrasada = any(
                datetime.fromisoformat(leitura["coletado_em"]).time() > datetime.strptime("00:15", "%H:%M").time()
                for leitura in (primeira, ultima)
            )
            if atrasada and chave.startswith("ip:"):
                estado = "Coleta tardia e identificação por IP; conferir"
            elif atrasada:
                estado = "Coleta tardia; conferir período"
            elif chave.startswith("ip:"):
                estado = "Identificação pelo IP; conferir equipamento"
            else:
                estado = "Coletado"

        categorias = {}
        identidade_cor_alterada = bool(
            primeira_cor and ultima_cor and any(
                primeira_cor[campo] and ultima_cor[campo]
                and primeira_cor[campo].strip().upper() != ultima_cor[campo].strip().upper()
                for campo in ("serie", "patrimonio", "modelo")
            )
        )
        for categoria in ("preto_branco", "nivel_1", "nivel_2", "nivel_3"):
            inicio_cor = primeira_cor[categoria] if primeira_cor else None
            fim_cor = ultima_cor[categoria] if ultima_cor else None
            diferenca = None
            if inicio_cor is None or fim_cor is None:
                situacao_cor = "Sem leitura de início ou fim"
            elif identidade_cor_alterada:
                situacao_cor = "Equipamento alterado; conferir"
            elif fim_cor < inicio_cor:
                situacao_cor = "Contador diminuiu; conferir"
            else:
                diferenca = fim_cor - inicio_cor
                tardia = any(
                    datetime.fromisoformat(leitura["coletado_em"]).time() > datetime.strptime("00:15", "%H:%M").time()
                    for leitura in (primeira_cor, ultima_cor)
                )
                avisos = []
                if tardia:
                    avisos.append("Coleta tardia")
                if chave.startswith("ip:"):
                    avisos.append("Identificação pelo IP")
                situacao_cor = "; ".join(avisos) + "; conferir" if avisos else "Coletado"
            categorias[categoria] = {
                "inicial": inicio_cor, "final": fim_cor, "impressoes": diferenca, "situacao": situacao_cor,
            }
        itens.append({
            "chave": chave, "nome": nome, "grupo": grupo, "ip": ip,
            "patrimonio": patrimonio, "modelo": modelo,
            "contador_inicial": valor_inicio, "contador_final": valor_fim,
            "coletado_inicial": primeira["coletado_em"] if primeira and valor_inicio is not None else None,
            "coletado_final": ultima["coletado_em"] if ultima and valor_fim is not None else None,
            "erro_inicial": primeira["erro"] if primeira else None,
            "erro_final": ultima["erro"] if ultima else None,
            "impressoes": total, "situacao": estado,
            "categorias_cor": categorias,
            "cor_aplicavel": bool(primeira_cor or ultima_cor or modelo_compativel(modelo)),
            "cor_coletado_inicial": primeira_cor["coletado_em"] if primeira_cor and primeira_cor["preto_branco"] is not None else None,
            "cor_coletado_final": ultima_cor["coletado_em"] if ultima_cor and ultima_cor["preto_branco"] is not None else None,
            "cor_erro_inicial": primeira_cor["erro"] if primeira_cor else None,
            "cor_erro_final": ultima_cor["erro"] if ultima_cor else None,
        })
    itens.sort(key=lambda item: (item["grupo"].casefold(), item["nome"].casefold(), item["ip"]))
    calculados = [item["impressoes"] for item in itens if item["impressoes"] is not None]
    return {
        "mes": mes, "inicio": data_inicio, "fim": data_fim, "itens": itens,
        "total_calculado": sum(calculados) if calculados else None,
        "sem_total": sum(item["impressoes"] is None for item in itens),
    }
