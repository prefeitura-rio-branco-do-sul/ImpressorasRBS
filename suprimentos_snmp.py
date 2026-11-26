import asyncio
import json
import logging
import openpyxl
import os
import re
import sqlite3
import smtplib
import tempfile
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv
from pysnmp.hlapi.v1arch.asyncio import *

from config.configuracoes import (
    NOME_ALERTAS_ENVIADOS,
    NOME_HISTORICO,
    NOME_IMPRESSORAS_ENCONTRADAS,
    NOME_LOG,
    NOME_OFFLINE,
    NOME_PLANILHA_ATUALIZADA,
    NOME_PLANILHA_CONSOLIDADA,
    NOME_PLANILHA_ORIGINAL,
    NOME_TONER_6,
    OID_CONTADOR_PAGINAS,
    OID_DESCRICAO_SISTEMA,
    OID_SUPRIMENTOS_CAPACIDADE,
    OID_SUPRIMENTOS_DESCRICAO,
    OID_SUPRIMENTOS_NIVEL,
    SMTP_HOST,
    SMTP_PORTA,
    SNMP_COMMUNITY_PADRAO,
    SNMP_PORTA,
)
from estoque import (
    conectar,
    registrar_evento_impressora,
    registrar_nivel_toner,
)
from utils.texto import extrair_modelo_planilha
from toners_sem_chip import TONERS_SEM_CHIP, estimar_niveis_sem_chip


# ==========================================================
# CONFIGURAÇÕES
# ==========================================================

BASE_DIR = Path(__file__).parent

ARQUIVO_OFFLINE = BASE_DIR / NOME_OFFLINE
ARQUIVO_HISTORICO = BASE_DIR / NOME_HISTORICO
ARQUIVO_TONER_6 = BASE_DIR / NOME_TONER_6

def obter_arquivo_planilha_impressoras():
    atualizada = BASE_DIR / NOME_PLANILHA_ATUALIZADA
    consolidada = BASE_DIR / NOME_PLANILHA_CONSOLIDADA
    original = BASE_DIR / NOME_PLANILHA_ORIGINAL
    if atualizada.exists():
        return atualizada
    if consolidada.exists():
        return consolidada
    return original


# ==========================================================
# CARREGA VARIÁVEIS DO .ENV
# ==========================================================

load_dotenv()

# ==========================================================
# CONFIGURAÇÃO DE LOGGING
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            BASE_DIR / NOME_LOG,
            encoding="utf-8"
        ),
    ]
)

logger = logging.getLogger(__name__)

# ==========================================================
# CONFIGURAÇÕES DE E-MAIL E SNMP
# ==========================================================

EMAIL_SEMED  = os.getenv("EMAIL_SEMED",  "")
EMAIL_OUTROS = os.getenv("EMAIL_OUTROS", "")
SNMP_COMMUNITY = os.getenv("SNMP_COMMUNITY", SNMP_COMMUNITY_PADRAO)

logger.info("Gmail configurado: %s", os.getenv("GMAIL_REMETENTE"))
logger.info("Senha de app carregada: %s", bool(os.getenv("GMAIL_SENHA_APP")))
logger.info("SNMP Community: %s", SNMP_COMMUNITY)


# ==========================================================
# CONTROLE DE ALERTAS DE TONER
# ==========================================================

def carregar_alertas_enviados():

    try:

        with open(
            BASE_DIR / NOME_ALERTAS_ENVIADOS,
            "r",
            encoding="utf-8"
        ) as arquivo:

            dados = json.load(arquivo)
            if not isinstance(dados, list) or not all(isinstance(item, str) for item in dados):
                raise ValueError("Formato inválido no controle de alertas de toner.")
            return set(dados)

    except FileNotFoundError:
        return set()
    except (OSError, ValueError, TypeError):
        logger.exception("Não foi possível carregar o controle de alertas de toner.")
        raise


def salvar_alertas_enviados(alertas):
    arquivo_temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=BASE_DIR, delete=False
        ) as arquivo:
            arquivo_temporario = arquivo.name
            json.dump(sorted(alertas), arquivo, indent=4)
        os.replace(arquivo_temporario, BASE_DIR / NOME_ALERTAS_ENVIADOS)
    finally:
        if arquivo_temporario and os.path.exists(arquivo_temporario):
            os.unlink(arquivo_temporario)


toners_alertados = carregar_alertas_enviados()

# ==========================================================
# HISTÓRICO DE TONERS EM 6%
# ==========================================================

def carregar_historico_toner_6():

    try:

        with open(
            ARQUIVO_TONER_6,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return json.load(arquivo)

    except:

        return []


def salvar_historico_toner_6(historico):

    with open(
        ARQUIVO_TONER_6,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            historico,
            arquivo,
            indent=4,
            ensure_ascii=False
        )


historico_toner_6 = carregar_historico_toner_6()

def registrar_toner_6(
    ip,
    nome_impressora,
    toner
):

    agora = datetime.now()

    # Verifica se já existe uma leitura recente
    for evento in reversed(historico_toner_6):

        if (
            evento.get("ip") == ip
            and evento.get("toner") == toner
        ):

            ultima_data = datetime.strptime(
                evento["data"],
                "%d/%m/%Y %H:%M:%S"
            )

            # Não registra novamente no mesmo dia
            if ultima_data.date() == agora.date():
                return

            break

    evento = {

        "data":
            agora.strftime(
                "%d/%m/%Y %H:%M:%S"
            ),

        "ip":
            ip,

        "impressora":
            nome_impressora,

        "toner":
            toner,

        "nivel":
            6
    }

    historico_toner_6.append(evento)

    salvar_historico_toner_6(
        historico_toner_6
    )


def limpar_historico_toner_6(ip, toner):
    global historico_toner_6

    chave_ip = str(ip).strip()
    chave_toner = str(toner).strip().casefold()
    historico_atualizado = [
        evento
        for evento in historico_toner_6
        if not (
            str(evento.get("ip", "")).strip() == chave_ip
            and str(evento.get("toner", "")).strip().casefold()
            == chave_toner
        )
    ]

    if len(historico_atualizado) != len(historico_toner_6):
        historico_toner_6 = historico_atualizado
        salvar_historico_toner_6(historico_toner_6)


# ==========================================================
# VERIFICA TONERS COM LEITURA NÃO CONFIÁVEL
# ==========================================================
# ==========================================================
# VERIFICA TONERS COM 5 DIAS CONSECUTIVOS EM 6%
# ==========================================================

def verificar_toners_nao_confiaveis():

    nao_confiaveis = {
        (ip, cor)
        for ip, configuracao in TONERS_SEM_CHIP.items()
        for cor in configuracao["cores"]
    }

    registros = {}
    hoje = datetime.now().date()

    conexao = conectar()
    try:
        niveis_atuais = {
            (ip, cor.strip().casefold()): (percentual, data_atualizacao)
            for ip, cor, percentual, data_atualizacao in conexao.execute("""
                SELECT ip_impressora, cor, percentual, atualizado_em
                FROM niveis_toner
            """).fetchall()
        }
    finally:
        conexao.close()

    for evento in historico_toner_6:

        ip = evento.get("ip")
        toner = evento.get("toner")
        data = evento.get("data")

        if not ip or not toner or not data:
            continue

        # A sequência histórica só é válida enquanto a leitura atual
        # continuar exatamente em 6%.
        leitura_atual = niveis_atuais.get(
            (ip, toner.strip().casefold())
        )
        if not leitura_atual or leitura_atual[0] != 6:
            continue

        chave = (ip, toner)

        try:

            data_registro = datetime.strptime(
                data,
                "%d/%m/%Y %H:%M:%S"
            ).date()

        except ValueError:

            continue

        if leitura_atual[1]:
            try:
                data_atualizacao = datetime.strptime(
                    leitura_atual[1],
                    "%d/%m/%Y %H:%M:%S"
                ).date()
            except ValueError:
                continue
            if data_atualizacao != hoje:
                continue

        if chave not in registros:
            registros[chave] = set()

        registros[chave].add(
            data_registro
        )

    for chave, datas in registros.items():

        datas_ordenadas = sorted(datas)

        dias_consecutivos = 1

        for i in range(1, len(datas_ordenadas)):

            diferenca = (
                datas_ordenadas[i]
                - datas_ordenadas[i - 1]
            ).days

            if diferenca == 1:

                dias_consecutivos += 1

            else:

                dias_consecutivos = 1

            if (
                datas_ordenadas[i] == hoje
                and dias_consecutivos >= 5
            ):

                nao_confiaveis.add(chave)

                break

    return nao_confiaveis
# ==========================================================
# ENVIA E-MAIL DE TONER BAIXO
# ==========================================================

def enviar_email_toner(
    destinatario,
    impressora,
    toner,
    porcentagem
):

    remetente = os.environ.get(
        "GMAIL_REMETENTE"
    )

    senha_app = os.environ.get(
        "GMAIL_SENHA_APP"
    )

    if not remetente or not senha_app or not destinatario:

        logger.error(
            "ERRO: remetente, senha ou destinatário de e-mail não configurado."
        )

        return False


    mensagem = EmailMessage()

    mensagem["Subject"] = (
        f"⚠️ Toner baixo - {impressora}"
    )

    mensagem["From"] = remetente

    mensagem["To"] = destinatario

    mensagem.set_content(
        f"""Olá,

O sistema de monitoramento identificou toner em 5% ou menos.

Impressora: {impressora}
Toner: {toner}
Nível atual: {porcentagem}

Solicita-se a verificação e substituição do toner.

Este é um aviso automático do Monitor de Impressoras.
"""
    )


    try:

        with smtplib.SMTP(
            SMTP_HOST,
            SMTP_PORTA
        ) as servidor:

            servidor.starttls()

            servidor.login(
                remetente,
                senha_app
            )

            servidor.send_message(
                mensagem
            )


        logger.info(f"E-mail enviado para: {destinatario}")
        return True


    except (OSError, smtplib.SMTPException):

        logger.exception("Erro ao enviar e-mail de toner baixo.")
        return False


def atualizar_alerta_toner(ip, impressora, toner, porcentagem, email, nao_confiaveis):
    chave_alerta = f"{ip}-{toner}"
    if porcentagem > 5:
        if chave_alerta in toners_alertados:
            restantes = toners_alertados - {chave_alerta}
            salvar_alertas_enviados(restantes)
            toners_alertados.remove(chave_alerta)
        return

    if (ip, toner) in nao_confiaveis or chave_alerta in toners_alertados:
        return

    logger.info(
        "Alerta de toner baixo: impressora %s (%s), toner %s, nível %s%%.",
        impressora, ip, toner, porcentagem,
    )
    if enviar_email_toner(email, impressora, toner, f"{porcentagem}%"):
        toners_alertados.add(chave_alerta)
        salvar_alertas_enviados(toners_alertados)


# ==========================================================
# CARREGA PLANILHA DE IMPRESSORAS
# ==========================================================

def carregar_planilha(incluir_excluidas=False):
    arquivo = obter_arquivo_planilha_impressoras()
    planilha = openpyxl.load_workbook(
        arquivo,
        data_only=True,
        read_only=True,
    )
    impressoras_planilha = []
    try:
        aba = planilha.active
        linha_cabecalho = 1
        for numero_linha, linha in enumerate(
            aba.iter_rows(min_row=1, values_only=True),
            start=1,
        ):
            if len(linha) > 1 and str(linha[1] or "").strip().casefold() in {
                "ip",
                "endereco",
                "endereço",
            }:
                linha_cabecalho = numero_linha
                break

        cabecalho = next(
            aba.iter_rows(
                min_row=linha_cabecalho,
                max_row=linha_cabecalho,
                values_only=True,
            )
        )
        novo_formato = (
            str(cabecalho[1] or "").strip().casefold() == "ip"
            and len(cabecalho) > 4
            and str(cabecalho[3] or "").strip().casefold() == "modelo"
        )

        for linha in aba.iter_rows(
            min_row=linha_cabecalho + 1,
            values_only=True,
        ):
            if novo_formato:
                ip = linha[1] if len(linha) > 1 else None
                patrimonio = linha[2] if len(linha) > 2 else None
                modelo_cadastrado = (
                    str(linha[3]).strip()
                    if len(linha) > 3 and linha[3]
                    else ""
                )
                descricao = linha[4] if len(linha) > 4 else None
                setor_cadastrado = (
                    str(descricao).split("-", 1)[0].strip()
                    if descricao and "-" in str(descricao)
                    else ""
                )
                coluna_excluida = 7
            else:
                descricao = linha[0] if linha else None
                ip = linha[1] if len(linha) > 1 else None
                patrimonio = linha[2] if len(linha) > 2 else None
                modelo_cadastrado = (
                    str(linha[5]).strip()
                    if len(linha) > 5 and linha[5]
                    else ""
                )
                setor_cadastrado = (
                    str(linha[3]).strip()
                    if len(linha) > 3 and linha[3]
                    else ""
                )
                coluna_excluida = 7

            excluida = (
                len(linha) >= coluna_excluida
                and str(linha[coluna_excluida - 1] or "").strip().casefold()
                in {"sim", "true", "1", "excluída", "excluida"}
            )
            if not ip or (excluida and not incluir_excluidas):
                continue

            ip = str(ip).strip().replace("(Network)", "").split()[0]
            correspondencia_ip = re.fullmatch(r"(.+)_\d+", ip)
            if correspondencia_ip:
                ip = correspondencia_ip.group(1)
            partes = ip.split(".")
            if (
                len(partes) != 4
                or not all(parte.isdigit() for parte in partes)
                or not all(0 <= int(parte) <= 255 for parte in partes)
            ):
                continue

            impressoras_planilha.append({
                "descricao": descricao,
                "ip": ip,
                "patrimonio": patrimonio,
                "modelo": modelo_cadastrado,
                "setor": setor_cadastrado,
                "excluida": excluida,
            })
    finally:
        planilha.close()

    return impressoras_planilha


def _qualidade_nome_cadastro(impressora):
    nome = re.sub(r"[^A-Z0-9]", "", str(impressora.get("descricao") or "").upper())
    modelo = re.sub(r"[^A-Z0-9]", "", str(impressora.get("modelo") or "").upper())
    return bool(nome and nome != modelo)


# ==========================================================
# HISTÓRICO
# ==========================================================

def registrar_evento(
    ip,
    tipo,
    mensagem
):

    try:

        with open(
            ARQUIVO_HISTORICO,
            "r",
            encoding="utf-8"
        ) as arquivo:

            historico = json.load(
                arquivo
            )

    except:

        historico = []


    evento = {

        "data":
            datetime.now().strftime(
                "%d/%m/%Y %H:%M:%S"
            ),

        "ip":
            ip,

        "tipo":
            tipo,

        "mensagem":
            mensagem

    }


    historico.append(
        evento
    )


    with open(
        ARQUIVO_HISTORICO,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            historico,
            arquivo,
            indent=4,
            ensure_ascii=False
        )


# ==========================================================
# CONTROLE DOS OFFLINES
# ==========================================================

def carregar_offline():

    try:

        with open(
            ARQUIVO_OFFLINE,
            "r",
            encoding="utf-8"
        ) as arquivo:

            return json.load(
                arquivo
            )

    except:

        return {}


def salvar_offline(dados):

    with open(
        ARQUIVO_OFFLINE,
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            dados,
            arquivo,
            indent=4,
            ensure_ascii=False
        )


# ==========================================================
# CONSULTA SNMP
# ==========================================================



async def consultar_contador_paginas(ip):

    contadores = []

    try:
        with SnmpDispatcher() as snmp:
            transporte = await UdpTransportTarget.create(
                (ip, SNMP_PORTA),
                timeout=1.5,
                retries=0
            )

            async for erro, status, indice, dados in walk_cmd(
                snmp,
                CommunityData(SNMP_COMMUNITY),
                transporte,
                (OID_CONTADOR_PAGINAS, None),
                lexicographicMode=False,
            ):
                if erro:
                    raise RuntimeError(
                        f"Falha de comunicação SNMP: {erro}"
                    )

                if status:
                    raise RuntimeError(
                        f"Erro SNMP: {status.prettyPrint()}"
                    )

                fora_do_contador = False
                for oid, valor in dados:
                    oid_texto = str(oid)

                    if not oid_texto.startswith(
                        OID_CONTADOR_PAGINAS + "."
                    ):
                        fora_do_contador = True
                        break

                    try:
                        contador = int(valor.prettyPrint())
                    except (TypeError, ValueError):
                        continue

                    if contador >= 0:
                        sufixo = oid_texto[
                            len(OID_CONTADOR_PAGINAS) + 1:
                        ]
                        indice_oid = tuple(
                            int(parte)
                            for parte in sufixo.split(".")
                            if parte.isdigit()
                        )
                        contadores.append(
                            (indice_oid, contador, oid_texto)
                        )
                if fora_do_contador:
                    break

        if not contadores:
            raise RuntimeError(
                "A impressora não disponibilizou o contador padrão de páginas via SNMP."
            )

        _, contador, oid = min(
            contadores,
            key=lambda item: item[0]
        )

        return {
            "contador": contador,
            "oid": oid
        }

    except RuntimeError:
        raise
    except Exception as erro:
        logger.exception(
            "Erro ao consultar contador de páginas via SNMP no IP %s",
            ip
        )
        raise RuntimeError(
            "Não foi possível consultar o contador de páginas via SNMP."
        ) from erro


async def consultar(
    ip,
    oid_base,
    timeout=0.3,
    retries=0,
):

    resultados = []


    try:

        with SnmpDispatcher() as snmp:

            transporte = await UdpTransportTarget.create(
                (ip, SNMP_PORTA),
                timeout=timeout,
                retries=retries
            )


            async for (
                erro,
                status,
                indice,
                dados
            ) in walk_cmd(

                snmp,

                CommunityData(
                    SNMP_COMMUNITY
                ),

                transporte,

                (
                    oid_base,
                    None
                )

            ):

                if erro or status:

                    break


                for oid, valor in dados:

                    if not str(
                        oid
                    ).startswith(
                        oid_base
                    ):

                        return resultados


                    resultados.append(
                        valor.prettyPrint()
                    )


    except Exception as erro:

        logger.error(f"Erro SNMP no IP {ip}: {erro}")


    return resultados


# ==========================================================
# CONSULTA MODELO
# ==========================================================

async def consultar_modelo(ip):

    resultados = await consultar(
        ip,
        OID_DESCRICAO_SISTEMA
    )


    if resultados:

        return resultados[0]


    return "Modelo não identificado"


async def consultar_suprimentos_e_presenca(ip):
    oid_suprimentos = OID_SUPRIMENTOS_DESCRICAO
    descricoes = await consultar(ip, oid_suprimentos)
    if descricoes:
        return descricoes, None

    modelo = await consultar(ip, OID_DESCRICAO_SISTEMA, timeout=1.5, retries=1)
    if not modelo:
        logger.warning("Impressora %s não respondeu às verificações SNMP.", ip)
        return None, None

    descricoes = await consultar(ip, oid_suprimentos, timeout=1.5, retries=1)
    if not descricoes:
        logger.warning("Impressora %s respondeu ao SNMP, mas sem dados de suprimentos.", ip)
    return descricoes, modelo[0]


# ==========================================================
# MAIN
# ==========================================================

async def main():

    dados = []

    encontradas = []


    # ------------------------------------------------------
    # CARREGA CONTROLE DE OFFLINE
    # ------------------------------------------------------

    offline = carregar_offline()

    #------------------------------------------------------ 
    # CARREGAR TONERS NÃO CONFIÁVEIS
    #------------------------------------------------------

    toners_nao_confiaveis = verificar_toners_nao_confiaveis()


    # ------------------------------------------------------
    # LISTA DE IMPRESSORAS
    # ------------------------------------------------------

    impressoras = []


    # ------------------------------------------------------
    # IPs ENCONTRADOS ANTERIORMENTE
    # ------------------------------------------------------

    try:

        with open(
            str(BASE_DIR / NOME_IMPRESSORAS_ENCONTRADAS),
            "r",
            encoding="utf-8"
        ) as arquivo:

            ips_existentes = json.load(
                arquivo
            )

    except:

        ips_existentes = []


    # ------------------------------------------------------
    # IPs DA PLANILHA
    # ------------------------------------------------------

    dados_planilha = carregar_planilha(incluir_excluidas=True)

    ips_excluidos = {
        item["ip"]
        for item in dados_planilha
        if item["excluida"]
    }
    dados_planilha = [
        item
        for item in dados_planilha
        if not item["excluida"]
    ]

    planilha_por_ip = {}
    for item in dados_planilha:
        cadastro_atual = planilha_por_ip.get(item["ip"])
        if (
            cadastro_atual is None
            or _qualidade_nome_cadastro(item)
            > _qualidade_nome_cadastro(cadastro_atual)
        ):
            planilha_por_ip[item["ip"]] = item


    ips_planilha = [

        item["ip"]

        for item in dados_planilha

    ]


    # ------------------------------------------------------
    # JUNTA OS IPS
    # ------------------------------------------------------

    ips_para_testar = list(
        (set(ips_existentes) | set(ips_planilha)) - ips_excluidos
    )


    for ip in ips_para_testar:

        impressoras.append({

            "nome":
                f"Impressora {ip}",

            "ip":
                ip

        })


    logger.info(f"TOTAL DE IPs PARA TESTAR: {len(impressoras)}")


    # ======================================================
    # TESTA CADA IMPRESSORA
    # ======================================================

    for impressora in impressoras:

        ip = impressora["ip"]


        logger.info(f"Testando impressora: {ip}")


        # --------------------------------------------------
        # DADOS DA PLANILHA
        # --------------------------------------------------

        dados_cadastro = planilha_por_ip.get(
            ip,
            {}
        )


        descricao_planilha = (
            dados_cadastro.get(
                "descricao",
                "Não cadastrado"
            )
        )


        patrimonio = (
            dados_cadastro.get(
                "patrimonio",
                "Não cadastrado"
            )
        )


        nome_impressora = descricao_planilha
        departamento = dados_cadastro.get("setor", "")

        modelo_planilha = (
            dados_cadastro.get("modelo")
            or extrair_modelo_planilha(descricao_planilha)
        )


        # --------------------------------------------------
        # DEFINE E-MAIL
        # --------------------------------------------------

        if str(
            departamento or nome_impressora
        ).upper().startswith(
            "SEMED"
        ):

            email = EMAIL_SEMED

        else:

            email = EMAIL_OUTROS


        logger.info(f"IP: {ip}")

        logger.info(f"Modelo/Descrição: {descricao_planilha}")

        logger.info(f"Modelo planilha: {modelo_planilha}")

        logger.info(f"Patrimônio: {patrimonio}")


        # ==================================================
        # CONSULTA OS SUPRIMENTOS
        # ==================================================

        descricoes, modelo_confirmado = await consultar_suprimentos_e_presenca(ip)


        # ==================================================
        # IMPRESSORA NÃO RESPONDEU
        # ==================================================

        if descricoes is None:

            logger.info(f"IMPRESSORA OFFLINE: {ip}")


            agora = datetime.now()


            # --------------------------------------------------
            # SE É A PRIMEIRA VEZ QUE ESTÁ OFFLINE,
            # COMEÇA A CONTAR O TEMPO
            # --------------------------------------------------

            if ip not in offline:

                offline[ip] = {

                    "inicio":
                        agora.strftime(
                            "%d/%m/%Y %H:%M:%S"
                        ),

                    "registrado":
                        False

                }


                salvar_offline(
                    offline
                )


            # --------------------------------------------------
            # PEGA O REGISTRO DESTE IP
            # --------------------------------------------------
# --------------------------------------------------
            # VERIFICA SE A IMPRESSORA ESTÁ OFFLINE
            # --------------------------------------------------

            dados_offline = offline[ip]


            inicio = datetime.strptime(

                dados_offline["inicio"],

                "%d/%m/%Y %H:%M:%S"

            )


            # --------------------------------------------------
            # CALCULA O TEMPO OFFLINE
            # --------------------------------------------------

            tempo_offline = (

                agora - inicio

            ).total_seconds()


            # --------------------------------------------------
            # REGISTRA NO HISTÓRICO SOMENTE APÓS 24 HORAS
            # --------------------------------------------------

            if (

                tempo_offline >= 86400

                and

                not dados_offline["registrado"]

            ):

                minutos = int(

                    tempo_offline / 60

                )


                registrar_evento_impressora(

                    ip_impressora=ip,

                    patrimonio=patrimonio,

                    modelo=descricao_planilha,

                    evento="OFFLINE",

                    inicio_offline=inicio.strftime(
                        "%d/%m/%Y %H:%M:%S"
                    ),

                    duracao_minutos=minutos

                )


                # Marca somente esta impressora
                # como já registrada

                dados_offline["registrado"] = True


                salvar_offline(

                    offline

                )


                logger.info(

                    "EVENTO OFFLINE REGISTRADO:",

                    ip

                )


            # --------------------------------------------------
            # CONTINUA APARECENDO COMO OFFLINE NA TELA
            # --------------------------------------------------

            dados.append({

                "nome":
                    impressora["nome"],

                "ip":
                    ip,

                "modelo":
                    descricao_planilha,

                "patrimonio":
                    patrimonio,

                "email":
                    email,

                "ciano":
                    "-",

                "magenta":
                    "-",

                "amarelo":
                    "-",

                "preto":
                    "-",

                "status":
                    "Offline"

            })


            continue


        # ==================================================
        # IMPRESSORA RESPONDEU
        # ==================================================

        logger.info(f"IMPRESSORA ENCONTRADA: {ip}")


        # --------------------------------------------------
        # VERIFICA SE ELA ESTAVA OFFLINE
        # --------------------------------------------------

        if ip in offline:

            dados_retorno = offline[ip]


            # --------------------------------------------------
            # SE O OFFLINE JÁ TINHA SIDO REGISTRADO,
            # REGISTRA O RETORNO ONLINE
            # --------------------------------------------------

            if dados_retorno.get(
                "registrado",
                False
            ):

                inicio = datetime.strptime(

                    dados_retorno["inicio"],

                    "%d/%m/%Y %H:%M:%S"

                )


                agora = datetime.now()


                segundos_offline = (

                    agora - inicio

                ).total_seconds()


                minutos = int(
                    segundos_offline / 60
                )


                registrar_evento(

                    ip,

                    "ONLINE",

                    (
                        "Impressora voltou a "
                        "responder ao SNMP após "
                        f"{minutos} minutos offline."
                    )

                )


                logger.info(f"EVENTO ONLINE REGISTRADO: {ip}")


            # --------------------------------------------------
            # REMOVE O CONTROLE DO OFFLINE
            # --------------------------------------------------

            del offline[ip]


            salvar_offline(offline)


        # --------------------------------------------------
        # GUARDA COMO ENCONTRADA
        # --------------------------------------------------

        encontradas.append(
            ip
        )

# ==================================================
        # CONSULTA MODELO
        # ==================================================

        modelo = modelo_confirmado or await consultar_modelo(ip)

        logger.info(f"MODELO: {modelo}")


        # ==================================================
        # CAPACIDADE DOS TONERS
        # ==================================================

        capacidades = await consultar(
            ip,
            OID_SUPRIMENTOS_CAPACIDADE
        )


        # ==================================================
        # NÍVEL ATUAL DOS TONERS
        # ==================================================

        niveis = await consultar(
            ip,
            OID_SUPRIMENTOS_NIVEL
        )


        logger.info(f"IP: {ip}")

        logger.info(f"DESCRICOES: {descricoes}")

        logger.info(f"CAPACIDADES: {capacidades}")

        logger.info(f"NIVEIS: {niveis}")


        # ==================================================
        # VALORES INICIAIS
        # ==================================================

        ciano = "-"
        magenta = "-"
        amarelo = "-"
        preto = "-"

        # ==================================================
        # MODELO DA PLANILHA
        # ==================================================

        modelo_estoque = modelo_planilha

        # Lista de cores encontradas nesta impressora
        cores_estoque = []

        # ==================================================
        # PROCESSA SUPRIMENTOS
        # ==================================================

        suprimentos_validos = []


        for i in range(
            len(descricoes)
        ):

            if (
                i >= len(capacidades)
                or
                i >= len(niveis)
            ):
                continue


            try:

                capacidade = int(
                    capacidades[i]
                )

                nivel = int(
                    niveis[i]
                )

            except (
                ValueError,
                TypeError
            ):

                continue


            # --------------------------------------------------
            # IGNORA VALORES INVÁLIDOS
            # --------------------------------------------------

            if (
                capacidade <= 0
                or
                nivel < 0
            ):

                continue


            porcentagem_numero = (
                nivel /
                capacidade
            ) * 100


            porcentagem_numero = max(
                0,
                min(
                    100,
                    porcentagem_numero
                )
            )


            porcentagem = (
                f"{porcentagem_numero:.0f}%"
            )


            descricao = str(
                descricoes[i]
            ).upper()


            suprimentos_validos.append({

                "descricao":
                    descricao,

                "porcentagem":
                    porcentagem

            })


        # ==================================================
        # IDENTIFICA CORES
        # ==================================================

        for suprimento in (
            suprimentos_validos
        ):

            descricao = (
                suprimento["descricao"]
            )

            porcentagem = (
                suprimento["porcentagem"]
            )


            if (
                descricao.endswith("C")
                or
                " CYAN" in descricao
            ):

                ciano = porcentagem
                cores_estoque.append(
                    "Ciano"
                )


            elif (
                descricao.endswith("M")
                or
                " MAGENTA" in descricao
            ):

                magenta = porcentagem
                cores_estoque.append(
                    "Magenta"
                )


            elif (
                descricao.endswith("Y")
                or
                " YELLOW" in descricao
            ):

                amarelo = porcentagem
                cores_estoque.append(
                    "Amarelo"
                )


            elif (
                descricao.endswith("K")
                or
                " BLACK" in descricao
            ):

                preto = porcentagem
                cores_estoque.append(
                    "Preto"
                )


        # ==================================================
        # SE POSSUI APENAS UM TONER,
        # CONSIDERA COMO PRETO
        # ==================================================

        if len(
            suprimentos_validos
        ) == 1:

            preto = (
                suprimentos_validos[0]
                ["porcentagem"]
            )
            if "Preto" not in cores_estoque:
              cores_estoque.append("Preto")

        # ==================================================
        # VERIFICA TONER ABAIXO DE 10%
        # ==================================================

        toners = {

            "Ciano":
                ciano,

            "Magenta":
                magenta,

            "Amarelo":
                amarelo,

            "Preto":
                preto

        }

        niveis_estimados = {}
        configuracao_sem_chip = TONERS_SEM_CHIP.get(ip)
        if configuracao_sem_chip:
            for cor in configuracao_sem_chip["cores"]:
                toners[cor] = "-"
            contador_atual = None
            oid_contador = None
            conexao = conectar()
            try:
                tem_ciclo_aberto = conexao.execute("""
                    SELECT 1 FROM trocas_toner_sem_chip
                    WHERE ip = ? AND patrimonio = ? AND encerrado_em IS NULL
                    LIMIT 1
                """, (ip, patrimonio)).fetchone()
                conexao.close()
                if tem_ciclo_aberto:
                    try:
                        leitura = await asyncio.wait_for(consultar_contador_paginas(ip), timeout=8)
                        contador_atual, oid_contador = leitura["contador"], leitura["oid"]
                    except (asyncio.TimeoutError, RuntimeError) as erro:
                        logger.warning("Não foi possível estimar os níveis da impressora %s: %s", ip, erro)
                conexao = conectar()
                niveis_estimados = estimar_niveis_sem_chip(
                    conexao.cursor(), ip, patrimonio, contador_atual, oid_contador
                )
            finally:
                conexao.close()
            for cor, estimativa in niveis_estimados.items():
                if estimativa["nivel"] is not None:
                    toners[cor] = f'{estimativa["nivel"]}%'
            ciano, magenta, amarelo, preto = (
                toners["Ciano"], toners["Magenta"], toners["Amarelo"], toners["Preto"]
            )

        for (
            nome_toner,
            nivel
        ) in toners.items():

            if configuracao_sem_chip and nome_toner in configuracao_sem_chip["cores"]:
                continue

            if (
                not nivel
                or
                nivel == "-"
            ):

                continue


            try:

                porcentagem = int(
                    str(nivel)
                    .replace("%", "")
                    .strip()
                )

            except ValueError:

                continue

            try:
                baixa_automatica = registrar_nivel_toner(
                    ip,
                    modelo_estoque,
                    nome_toner,
                    porcentagem,
                    patrimonio,
                    nome_impressora
                )
            except sqlite3.Error:
                logger.exception(
                    "Erro ao registrar nível do toner %s da impressora %s.",
                    nome_toner,
                    ip
                )
                baixa_automatica = None

            if baixa_automatica and baixa_automatica["status"] == "registrada":
                logger.info(
                    "TROCA DE TONER REGISTRADA AUTOMATICAMENTE: "
                    "%s %s (%s) na impressora %s; estoque agora %s.",
                    baixa_automatica["marca"],
                    baixa_automatica["codigo"],
                    baixa_automatica["cor"],
                    ip,
                    baixa_automatica["novo_estoque"]
                )
            elif baixa_automatica:
                logger.warning(
                    "Troca de toner detectada na impressora %s (%s), "
                    "mas a baixa não foi registrada: %s. Verifique o "
                    "modelo compatível cadastrado para o toner %s.",
                    ip,
                    descricao_planilha,
                    baixa_automatica["status"],
                    nome_toner
                )


            # Qualquer leitura diferente de 6% encerra a sequência
            # de leituras estáveis e torna o toner confiável novamente.
            if porcentagem == 6:
                registrar_toner_6(
                    ip,
                    nome_impressora,
                    nome_toner
                )
            else:
                limpar_historico_toner_6(
                    ip,
                    nome_toner
                )


            atualizar_alerta_toner(
                ip, nome_impressora, nome_toner, porcentagem, email,
                toners_nao_confiaveis,
            )


        # ==================================================
        # ADICIONA IMPRESSORA ONLINE
        # ==================================================

        dados.append({

            "nome":
                impressora["nome"],

            "ip":
                ip,

            "modelo":
                descricao_planilha,

            "patrimonio":
                patrimonio,

            "email":
                email,

            "ciano":
                ciano,

            "magenta":
                magenta,

            "amarelo":
                amarelo,

            "preto":
                preto,

            "niveis_estimados":
                niveis_estimados,

            "status":
                "Online"

        })


    # ======================================================
    # MOSTRA IMPRESSORAS ENCONTRADAS
    # ======================================================

    logger.info(
        "IMPRESSORAS ENCONTRADAS:"
    )

    logger.info(f"Encontradas: {encontradas}")



    # ======================================================
    # SALVA IPS ENCONTRADOS
    # ======================================================

    with open(
        str(BASE_DIR / NOME_IMPRESSORAS_ENCONTRADAS),
        "w",
        encoding="utf-8"
    ) as arquivo:

        json.dump(
            encontradas,
            arquivo,
            indent=4
        )


    return dados

# ==========================================================
# EXTRAI O MODELO DA IMPRESSORA DA DESCRIÇÃO DA PLANILHA
# ==========================================================

# ==========================================================
# FUNÇÃO USADA PELO FLASK
# ==========================================================

async def obter_impressoras():

    return await main()


# ==========================================================
# EXECUÇÃO DIRETA
# ==========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )