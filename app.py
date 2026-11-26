import asyncio
import csv
import hashlib
import hmac
import ipaddress
from io import BytesIO
import json
import logging
import os
import re
import secrets
import sqlite3
import socket
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock, Thread
from time import monotonic

import openpyxl
from flask import (
    Flask,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from openpyxl.utils.exceptions import InvalidFileException
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from repositories import (
    banco_repo,
    historico_repo,
    painel_repo,
    printer_repo,
    usuario_repo,
)
from config.configuracoes import (
    HOSTS_LOCAIS,
    HOSTS_LOCAIS_URL,
    NOME_CSV_LIMPO,
    NOME_DOWNLOAD_CONSOLIDADO,
    NOME_LOCAIS_EQUIVALENTES,
    NOME_LOG,
    NOME_PLANILHA_ATUALIZADA,
    NOME_PLANILHA_ORIGINAL,
    SERVIDOR_HOST,
    SERVIDOR_PORTA,
)
from utils.rede import ip_normalizado as _ip_normalizado
from utils.texto import (
    modelo_do_nome as _modelo_do_nome,
    modelos_para_compatibilidade as _modelos_para_compatibilidade,
    normalizar_grupo as _normalizar_grupo,
    normalizar_numero_serie as _normalizar_numero_serie,
    qualidade_nome_cadastro as _qualidade_nome_cadastro,
    registro_excluido as _registro_excluido,
)
from estoque import (
    cadastrar_toner,
    atualizar_modelos_compativeis,
    listar_toners,
    reativar_toner,
    registrar_saida_toner,
    remover_toner,
    ajustar_estoque_manual,
    atualizar_estoque_minimo,
)
from suprimentos_snmp import (
    consultar_contador_paginas,
    historico_toner_6,
    obter_arquivo_planilha_impressoras,
    obter_impressoras,
    verificar_toners_nao_confiaveis,
)
from relatorio_printer import (
    RelatorioDependenciaAusente,
    RelatorioInvalido,
    comparar_equipamentos,
    criar_email,
    criar_tabela_historico_printer,
    extrair_consumo_relatorio,
    ler_relatorio_pdf,
    normalizar_local_equivalencia,
)
from email_estoque import (
    ErroEnvioEmailEstoque,
    enviar_email_solicitacao,
    iniciar_agendador_estoque,
)
from pedidos_estoque import (
    listar_sugestoes_e_pedidos,
    adiar_sugestao_pedido,
    criar_solicitacao_pedido,
    marcar_solicitacao_enviada,
    cancelar_solicitacao_envio,
    decidir_solicitacao_pedido,
    receber_pedido,
    cancelar_pendencias_pedido,
)
from relatorio_impressoes import (
    gerar_relatorio as gerar_relatorio_impressoes,
    iniciar_agendador_contadores,
    limites_mes,
)
from toners_sem_chip import TONERS_SEM_CHIP


# ==========================================================
# LOGGING
# ==========================================================

BASE_DIR = Path(__file__).parent

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
# APP FLASK
# ==========================================================

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.secret_key = (
    os.environ.get("PAINEL_SESSION_SECRET") or secrets.token_hex(32)
)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False,
    TEMPLATES_AUTO_RELOAD=True,
)
banco_repo.inicializar_tabelas(criar_tabela_historico_printer)


def _garantir_tabela_configuracao_painel():
    app.secret_key = painel_repo.garantir_tabela_configuracao(
        os.environ.get("PAINEL_SESSION_SECRET"), app.secret_key
    )


_garantir_tabela_configuracao_painel()

PERMISSOES_PAINEL = {
    "monitor.view": "Ver monitoramento e impressoras",
    "printers.edit": "Editar cadastro de impressoras",
    "printers.delete": "Excluir impressoras do painel",
    "stock.view": "Consultar estoque de toners",
    "toner.create": "Cadastrar toners",
    "stock.adjust": "Ajustar quantidades e estoque mínimo",
    "stock.issue": "Registrar saídas de toners",
    "toner.manage": "Editar compatibilidade e ativar/desativar toners",
    "history.view": "Consultar histórico",
    "report.analyze": "Analisar relatório PRINTER",
    "report.approve": "Aprovar alterações do relatório PRINTER",
}

_ENDPOINT_PERMISSOES = {
    "dados": ("monitor.view",),
    "baixar_cadastro_consolidado": ("monitor.view",),
    "cadastrar_impressora": ("printers.edit",),
    "editar_impressora": ("printers.edit",),
    "excluir_impressora": ("printers.delete",),
    "analisar_relatorio_printer": ("report.analyze",),
    "salvar_historico_printer": ("report.analyze",),
    "listar_historico_printer": ("report.analyze",),
    "baixar_historico_printer": ("report.analyze",),
    "aprovar_equivalencia_relatorio_printer": ("report.approve",),
    "aprovar_correcao_relatorio_printer": ("report.approve",),
    "aprovar_inclusao_relatorio_printer": ("report.approve",),
    "contador_paginas_impressora": ("monitor.view",),
    "toners_compativeis_impressora": ("monitor.view",),
    "relatorio_impressoes": ("monitor.view",),
    "exportar_relatorio_impressoes": ("monitor.view",),
    "estoque": (
        "stock.view",
        "toner.create",
        "stock.adjust",
        "stock.issue",
        "toner.manage",
    ),
    "compatibilidade_toners": (
        "stock.view",
        "toner.create",
        "stock.adjust",
        "stock.issue",
        "toner.manage",
    ),
    "cadastrar_toner_rota": ("toner.create",),
    "ajustar_estoque_rota": ("stock.adjust",),
    "listar_pedidos_estoque": ("stock.view", "stock.adjust", "stock.issue", "toner.create", "toner.manage"),
    "enviar_solicitacao_pedido_estoque": ("stock.adjust",),
    "decidir_solicitacao_pedido_estoque": ("stock.adjust",),
    "receber_pedido_estoque": ("stock.adjust",),
    "cancelar_pendencias_pedido_estoque": ("stock.adjust",),
    "adiar_sugestao_pedido_estoque": ("stock.adjust",),
    "remover_toner_rota": ("toner.manage",),
    "reativar_toner_rota": ("toner.manage",),
    "atualizar_modelos_compativeis_rota": ("toner.manage",),
    "atualizar_estoque_minimo_rota": ("stock.adjust",),
    "historico": ("history.view",),
    "toners_nao_confiaveis": ("monitor.view",),
    "registrar_saida_toner_rota": ("stock.issue",),
}


def _garantir_tabelas_usuarios_painel():
    usuario_repo.garantir_tabelas_usuarios()


_garantir_tabelas_usuarios_painel()

_impressoras_cache = []
_cache_lock = Lock()
_atualizacao_em_andamento = False
_ultima_atualizacao = 0.0
_INTERVALO_ATUALIZACAO = 30
_cadastro_lock = Lock()

_COLUNA_SETOR = 4
_COLUNA_MODELO = 6
_COLUNA_EXCLUIDA = 7


def _obter_usuario_por_id(usuario_id):
    return usuario_repo.obter_usuario_por_id(usuario_id)


def _obter_usuario_atual():
    return _obter_usuario_por_id(session.get("usuario_id"))


def _usuario_tem_permissao(usuario, permissao):
    return bool(
        usuario
        and (usuario["administrador"] or permissao in usuario["permissoes"])
    )


def _normalizar_permissoes(permissoes):
    selecionadas = {
        permissao
        for permissao in permissoes
        if permissao in PERMISSOES_PAINEL
    }
    if selecionadas & {
        "printers.edit",
        "printers.delete",
        "toner.create",
        "stock.adjust",
        "stock.issue",
        "toner.manage",
        "report.analyze",
        "report.approve",
    }:
        selecionadas.add("monitor.view")
    if selecionadas & {
        "toner.create",
        "stock.adjust",
        "stock.issue",
        "toner.manage",
    }:
        selecionadas.add("stock.view")
    if "report.approve" in selecionadas:
        selecionadas.add("report.analyze")
    return sorted(selecionadas)


def _token_csrf():
    if not session.get("csrf_token"):
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def _validar_csrf():
    token_sessao = session.get("csrf_token", "")
    token_formulario = request.form.get("csrf_token", "")
    return bool(
        token_sessao
        and token_formulario
        and hmac.compare_digest(token_sessao, token_formulario)
    )


def _cliente_rede_autorizada(endereco_cliente):
    try:
        ip_cliente = ipaddress.ip_address(endereco_cliente)
    except ValueError:
        return False
    if ip_cliente.is_loopback:
        return True

    rede_permitida = os.environ.get("PAINEL_REDE_LOCAL", "").strip()
    if rede_permitida:
        try:
            return ip_cliente in ipaddress.ip_network(
                rede_permitida,
                strict=False,
            )
        except ValueError:
            logger.error("A sub-rede configurada para o painel é inválida.")
            return None

    return ip_cliente.is_private


@app.before_request
def exigir_autenticacao_painel():
    endereco_cliente = request.remote_addr or ""
    permitido = _cliente_rede_autorizada(endereco_cliente)
    if permitido is None:
        return "A configuração de rede do painel é inválida.", 503
    if not permitido:
        return "Acesso permitido somente pela rede local autorizada.", 403

    if request.endpoint in {
        "login_painel",
        "recuperar_senha_admin",
        "aceitar_convite",
        "static",
    }:
        return None

    usuario = _obter_usuario_atual()
    if not usuario or not usuario["ativo"]:
        session.clear()
        return redirect(url_for("login_painel"))

    if datetime.now().timestamp() - session.get(
        "presenca_atualizada_em", 0
    ) >= 30:
        usuario_repo.registrar_presenca(usuario["id"])
        session["presenca_atualizada_em"] = datetime.now().timestamp()

    endpoint = request.endpoint or ""
    if endpoint == "index":
        if not usuario["administrador"] and not usuario["permissoes"]:
            return "Esta conta ainda não recebeu permissões.", 403
    elif endpoint in {
        "admin_usuarios",
        "criar_convite_painel",
        "presenca_usuarios_painel",
        "alterar_status_usuario_painel",
        "alterar_permissoes_usuario_painel",
        "cancelar_convite_painel",
    }:
        if not usuario["administrador"]:
            return "Apenas a administração pode gerenciar acessos.", 403
    elif endpoint == "sair_painel":
        return None
    else:
        permissoes = _ENDPOINT_PERMISSOES.get(endpoint)
        if permissoes is None:
            if not usuario["administrador"]:
                return "Sua conta não tem permissão para esta ação.", 403
        elif not usuario["administrador"] and not any(
            permissao in usuario["permissoes"]
            for permissao in permissoes
        ):
            return "Sua conta não tem permissão para esta ação.", 403
    return None


@app.route("/entrar", methods=["GET", "POST"])
def login_painel():
    erro = ""
    if request.method == "POST":
        if not painel_repo.consumir_token_login(request.form.get("csrf_token", "")):
            erro = "A página expirou. Atualize e tente novamente."
        else:
            usuario_login = request.form.get("usuario", "").strip()
            senha_informada = request.form.get("senha", "")
            linha = usuario_repo.buscar_credenciais_login(usuario_login)
            if (
                linha
                and linha[2]
                and check_password_hash(linha[1], senha_informada)
            ):
                session.clear()
                session["usuario_id"] = linha[0]
                return redirect(url_for("index"))
            erro = "Usuário ou senha incorretos."

    return render_template(
        "login.html",
        erro=erro,
        csrf_token=painel_repo.criar_token_login(),
        recuperacao_local=(request.remote_addr or "") in HOSTS_LOCAIS,
    ), (401 if erro else 200)


@app.route("/recuperar-admin", methods=["GET", "POST"])
def recuperar_senha_admin():
    if (request.remote_addr or "") not in HOSTS_LOCAIS:
        return "Redefinição permitida somente neste computador.", 404

    erro = ""
    sucesso = False
    token_recuperacao = ""
    if request.method == "POST":
        senha = request.form.get("senha", "")
        confirmacao = request.form.get("confirmar_senha", "")
        if not painel_repo.consumir_token_recuperacao_admin(
            request.form.get("csrf_token", "")
        ):
            erro = "O formulário expirou. Atualize a página e tente novamente."
        elif len(senha) < 8 or len(senha) > 128:
            erro = "A senha deve ter entre 8 e 128 caracteres."
        elif senha != confirmacao:
            erro = "As senhas não coincidem."
        else:
            if usuario_repo.redefinir_senha_admin(generate_password_hash(senha)):
                logger.info("Senha da conta administrativa redefinida localmente.")
                sucesso = True
            else:
                erro = "Não foi encontrada uma conta administrativa ativa."

    if not sucesso:
        token_recuperacao = painel_repo.criar_token_recuperacao_admin()
    return render_template(
        "recuperar_senha_admin.html",
        erro=erro,
        sucesso=sucesso,
        csrf_token=token_recuperacao,
    ), (400 if erro else 200)


@app.route("/convite/<token>", methods=["GET", "POST"])
def aceitar_convite(token):
    convite = usuario_repo.buscar_convite_valido(token)
    if not convite:
        return render_template(
            "aceitar_convite.html",
            convite_valido=False,
            erro="Este convite é inválido, expirou ou já foi utilizado.",
            csrf_token="",
        ), 404

    erro = ""
    if request.method == "POST":
        usuario_login = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        if not _validar_csrf():
            erro = "A página expirou. Atualize e tente novamente."
        elif not re.fullmatch(r"[A-Za-z0-9._-]{3,32}", usuario_login):
            erro = "Use de 3 a 32 caracteres: letras, números, ponto, _ ou -."
        elif len(senha) < 8:
            erro = "A senha precisa ter pelo menos 8 caracteres."
        elif senha != request.form.get("confirmar_senha", ""):
            erro = "As senhas não coincidem."
        else:
            usuario_id, erro = usuario_repo.aceitar_convite(
                token, usuario_login, generate_password_hash(senha)
            )
            if not erro:
                session.clear()
                session["usuario_id"] = usuario_id
                return redirect(url_for("index"))

    return render_template(
        "aceitar_convite.html",
        convite_valido=True,
        nome=convite[1],
        erro=erro,
        csrf_token=_token_csrf(),
    ), (400 if erro else 200)


@app.route("/sair", methods=["POST"])
def sair_painel():
    if not _validar_csrf():
        return "A página expirou. Atualize e tente novamente.", 400
    session.clear()
    return redirect(url_for("login_painel"))


def _url_convite_publica(token):
    base_url = os.environ.get("PAINEL_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        base_url = request.host_url.rstrip("/")
        host = request.host.split(":", 1)[0].strip("[]").lower()
        if host in HOSTS_LOCAIS_URL:
            try:
                ip_lan = socket.gethostbyname(socket.gethostname())
                if not ipaddress.ip_address(ip_lan).is_loopback:
                    base_url = f"{request.scheme}://{ip_lan}:{request.environ.get('SERVER_PORT', SERVIDOR_PORTA)}"
            except (OSError, ValueError):
                logger.exception("Não foi possível detectar o IP local do painel.")
    return f"{base_url}{url_for('aceitar_convite', token=token)}"


@app.route("/admin/usuarios")
def admin_usuarios():
    limite_online = (
        datetime.now() - timedelta(minutes=2)
    ).strftime("%Y-%m-%d %H:%M:%S")
    usuarios, convites = usuario_repo.listar_usuarios_e_convites()
    return render_template(
        "usuarios.html",
        usuarios=usuarios,
        convites=convites,
        permissoes_disponiveis=PERMISSOES_PAINEL,
        limite_online=limite_online,
        permissoes_usuario=session.pop("admin_permissoes_usuario", None),
        convite_criado=session.pop("convite_criado_url", None),
        mensagem=session.pop("admin_mensagem", None),
        csrf_token=_token_csrf(),
    )


@app.route("/admin/usuarios/convites", methods=["POST"])
def criar_convite_painel():
    if not _validar_csrf():
        session["admin_mensagem"] = "A página expirou. Atualize e tente novamente."
        return redirect(url_for("admin_usuarios"))

    nome = request.form.get("nome", "").strip()
    if not nome or len(nome) > 100:
        session["admin_mensagem"] = "Informe um nome com até 100 caracteres."
        return redirect(url_for("admin_usuarios"))

    permissoes = _normalizar_permissoes(
        request.form.getlist("permissoes")
    )
    if not permissoes:
        session["admin_mensagem"] = (
            "Selecione pelo menos uma permissão antes de gerar o convite."
        )
        return redirect(url_for("admin_usuarios"))

    token = usuario_repo.criar_convite(nome, permissoes, session["usuario_id"])
    session["convite_criado_url"] = _url_convite_publica(token)
    session["admin_mensagem"] = (
        "Convite individual criado. Copie e envie o link somente à pessoa indicada."
    )
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/presenca")
def presenca_usuarios_painel():
    return jsonify(usuario_repo.listar_usuarios_online())


@app.route("/admin/usuarios/<int:usuario_id>/status", methods=["POST"])
def alterar_status_usuario_painel(usuario_id):
    if not _validar_csrf():
        return "A página expirou. Atualize e tente novamente.", 400
    if usuario_id == session.get("usuario_id"):
        return "Não é permitido desativar a própria conta.", 400
    ativo = request.form.get("ativo") == "1"
    if not usuario_repo.alterar_status_usuario(usuario_id, ativo):
        return "A conta não foi encontrada ou não pode ser alterada.", 404
    session["admin_mensagem"] = (
        "Conta reativada." if ativo else "Conta desativada."
    )
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:usuario_id>/permissoes", methods=["POST"])
def alterar_permissoes_usuario_painel(usuario_id):
    if not _validar_csrf():
        return "A página expirou. Atualize e tente novamente.", 400
    permissoes = _normalizar_permissoes(
        request.form.getlist("permissoes")
    )
    if not permissoes:
        session["admin_mensagem"] = "Mantenha ao menos uma permissão selecionada."
        return redirect(url_for("admin_usuarios"))
    if not usuario_repo.alterar_permissoes_usuario(usuario_id, permissoes):
        return "A conta não foi encontrada ou não pode ser alterada.", 404
    session["admin_mensagem"] = "Permissões atualizadas."
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/convites/<int:convite_id>/cancelar", methods=["POST"])
def cancelar_convite_painel(convite_id):
    if not _validar_csrf():
        return "A página expirou. Atualize e tente novamente.", 400
    if not usuario_repo.cancelar_convite(convite_id):
        return "O convite não foi encontrado ou já foi utilizado.", 404
    session["admin_mensagem"] = "Convite cancelado."
    return redirect(url_for("admin_usuarios"))


def _arquivo_locais_equivalentes():
    return BASE_DIR / NOME_LOCAIS_EQUIVALENTES


def _carregar_locais_equivalentes():
    arquivo_equivalencias = _arquivo_locais_equivalentes()
    if not arquivo_equivalencias.exists():
        return {}
    with arquivo_equivalencias.open("r", encoding="utf-8") as arquivo:
        dados = json.load(arquivo)
    if not isinstance(dados, dict) or any(
        not isinstance(serie, str)
        or not isinstance(locais, list)
        or any(not isinstance(local, str) for local in locais)
        for serie, locais in dados.items()
    ):
        raise ValueError("O arquivo interno de equivalências tem formato inválido.")
    return dados


def _salvar_locais_equivalentes(dados):
    temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix=".relatorio_locais_equivalentes_",
            suffix=".json",
            dir=BASE_DIR,
            delete=False,
        ) as arquivo:
            temporario = Path(arquivo.name)
            json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
        temporario.replace(_arquivo_locais_equivalentes())
    finally:
        if temporario is not None and temporario.exists():
            try:
                temporario.unlink()
            except OSError:
                logger.exception(
                    "Não foi possível remover o arquivo temporário %s.",
                    temporario,
                )


# ==========================================================
# CARREGA A LISTA DE IMPRESSORAS E IDENTIFICA OS GRUPOS
# ==========================================================

def _arquivo_lista_impressoras():
    return obter_arquivo_planilha_impressoras()


def _linha_cabecalho_cadastro(aba):
    for numero_linha in range(1, aba.max_row + 1):
        ip_cabecalho = str(
            aba.cell(numero_linha, 2).value or ""
        ).strip().casefold()
        if ip_cabecalho in {"ip", "endereço", "endereco"}:
            return numero_linha
    return 1


def _colunas_cadastro(aba):
    linha_cabecalho = _linha_cabecalho_cadastro(aba)
    ip_cabecalho = str(
        aba.cell(linha_cabecalho, 2).value or ""
    ).strip().casefold()
    modelo_cabecalho = str(
        aba.cell(linha_cabecalho, 4).value or ""
    ).strip().casefold()
    novo_formato = ip_cabecalho == "ip" and modelo_cabecalho == "modelo"
    if novo_formato:
        return {
            "novo_formato": True,
            "cabecalho": linha_cabecalho,
            "nome": 5,
            "ip": 2,
            "patrimonio": 3,
            "modelo": 4,
            "serie": 6,
            "setor": None,
            "excluida": 7,
        }
    return {
        "novo_formato": False,
        "cabecalho": linha_cabecalho,
        "nome": 1,
        "ip": 2,
        "patrimonio": 3,
        "modelo": _COLUNA_MODELO,
        "serie": 3,
        "setor": _COLUNA_SETOR,
        "excluida": _COLUNA_EXCLUIDA,
    }


def _salvar_cadastro_atualizado(planilha):
    destino = BASE_DIR / NOME_PLANILHA_ATUALIZADA
    arquivo_temporario = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".ImpressorasRBS_",
            suffix=".xlsx",
            dir=BASE_DIR,
            delete=False,
        ) as temporario:
            arquivo_temporario = Path(temporario.name)
        planilha.save(arquivo_temporario)
        arquivo_temporario.replace(destino)
    finally:
        if arquivo_temporario is not None and arquivo_temporario.exists():
            try:
                arquivo_temporario.unlink()
            except OSError:
                logger.exception(
                    "Não foi possível remover o arquivo temporário %s.",
                    arquivo_temporario,
                )


def _carregar_grupos_cadastro_original():
    arquivo_original = BASE_DIR / NOME_PLANILHA_ORIGINAL
    if not arquivo_original.exists():
        logger.warning(
            "Cadastro original não encontrado para recuperar os setores: %s",
            arquivo_original,
        )
        return {}, {}

    try:
        planilha = openpyxl.load_workbook(
            arquivo_original,
            data_only=True,
            read_only=True,
        )
    except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception(
            "Não foi possível carregar o cadastro original para recuperar os setores."
        )
        return {}, {}

    grupos_por_serie = {}
    grupos_por_ip = {}
    try:
        for linha in planilha.active.iter_rows(values_only=True):
            if len(linha) < 3 or not linha[0]:
                continue

            grupo = _normalizar_grupo(linha[0])
            serie = _normalizar_numero_serie(linha[2])
            if serie:
                grupos_por_serie.setdefault(serie, set()).add(grupo)

            ip = str(linha[1] or "").strip().replace("(Network)", "").split()
            if ip:
                grupos_por_ip.setdefault(ip[0], set()).add(grupo)
    finally:
        planilha.close()

    grupos_por_serie = {
        serie: next(iter(grupos))
        for serie, grupos in grupos_por_serie.items()
        if len(grupos) == 1
    }
    grupos_por_ip = {
        ip: next(iter(grupos))
        for ip, grupos in grupos_por_ip.items()
        if len(grupos) == 1
    }
    return grupos_por_serie, grupos_por_ip


def carregar_lista_impressoras(incluir_excluidas=False, exigir_arquivo=False):
    arquivo = _arquivo_lista_impressoras()

    if not arquivo.exists():
        logger.warning("Arquivo de cadastro de impressoras não encontrado: %s", arquivo)
        if exigir_arquivo:
            raise FileNotFoundError(f"Arquivo de cadastro não encontrado: {arquivo}")
        return []

    try:
        planilha = openpyxl.load_workbook(arquivo, data_only=True)
    except (FileNotFoundError, OSError, ValueError):
        logger.exception("Não foi possível abrir a planilha de impressoras: %s", arquivo)
        if exigir_arquivo:
            raise
        return []
    except Exception:
        logger.exception("Erro inesperado ao carregar a planilha de impressoras: %s", arquivo)
        if exigir_arquivo:
            raise
        return []

    try:
        aba = planilha.active
        lista = []
        colunas = _colunas_cadastro(aba)
        grupos_por_serie, grupos_por_ip = _carregar_grupos_cadastro_original()

        for linha in aba.iter_rows(
            min_row=colunas["cabecalho"] + 1,
            values_only=True,
        ):
            if len(linha) < colunas["ip"]:
                continue

            ip = linha[colunas["ip"] - 1]
            nome = (
                linha[colunas["nome"] - 1]
                if len(linha) >= colunas["nome"]
                else None
            )

            if not ip or not nome:
                continue

            ip = str(ip).strip().split()[0]
            ip = _ip_normalizado(ip) or ip
            if not _ip_normalizado(ip):
                correspondencia_ip = re.fullmatch(r"(.+)_\d+", ip)
                if correspondencia_ip:
                    ip = _ip_normalizado(correspondencia_ip.group(1)) or ip
            nome = str(nome).strip()

            if not ip or not nome:
                continue

            serie = (
                str(linha[colunas["serie"] - 1] or "").strip()
                if len(linha) >= colunas["serie"]
                else ""
            )
            patrimonio = (
                str(linha[colunas["patrimonio"] - 1] or "").strip()
                if len(linha) >= colunas["patrimonio"]
                else ""
            )
            setor_cadastrado = (
                str(linha[colunas["setor"] - 1]).strip()
                if colunas["setor"]
                and len(linha) >= colunas["setor"]
                and linha[colunas["setor"] - 1]
                else ""
            )
            modelo_cadastrado = (
                str(linha[colunas["modelo"] - 1]).strip()
                if len(linha) >= colunas["modelo"]
                and linha[colunas["modelo"] - 1]
                else ""
            )
            modelo = modelo_cadastrado or _modelo_do_nome(nome)
            excluida = (
                len(linha) >= colunas["excluida"]
                and _registro_excluido(linha[colunas["excluida"] - 1])
            )
            if excluida and not incluir_excluidas:
                continue

            grupo = (
                _normalizar_grupo(setor_cadastrado)
                if setor_cadastrado
                else None
            )
            if colunas["novo_formato"] and not setor_cadastrado:
                grupo = (
                    _normalizar_grupo(nome.split("-", 1)[0])
                    if "-" in nome
                    else None
                )
            if not grupo:
                grupo = grupos_por_serie.get(
                    _normalizar_numero_serie(serie)
                )
            if not grupo:
                grupo = grupos_por_ip.get(ip)
            if not grupo:
                grupo = _normalizar_grupo(nome)

            lista.append({
                "ip": ip,
                "nome": nome,
                "grupo": grupo,
                "serie_planilha": serie,
                "patrimonio_planilha": patrimonio,
                "modelo_cadastro": modelo,
                "excluida": excluida,
                "formato_cadastro": (
                    "consolidado" if colunas["novo_formato"] else "original"
                ),
            })

        return lista
    finally:
        try:
            planilha.close()
        except Exception:
            pass


def carregar_inventario_relatorio():
    arquivo = _arquivo_lista_impressoras()
    if not arquivo.exists():
        raise FileNotFoundError(
            f"Planilha de impressoras não encontrada: {arquivo}"
        )

    planilha = openpyxl.load_workbook(
        arquivo,
        data_only=True,
        read_only=True
    )
    try:
        inventario = []
        aba = planilha.active
        colunas = _colunas_cadastro(aba)
        for linha in aba.iter_rows(
            min_row=colunas["cabecalho"] + 1,
            values_only=True,
        ):
            nome = (
                linha[colunas["nome"] - 1]
                if len(linha) >= colunas["nome"]
                else None
            )
            serie = (
                linha[colunas["serie"] - 1]
                if len(linha) >= colunas["serie"]
                else None
            )
            if not nome or not serie:
                continue
            if len(linha) >= colunas["excluida"] and _registro_excluido(
                linha[colunas["excluida"] - 1]
            ):
                continue
            inventario.append({
                "local": str(nome).strip(),
                "ip": (
                    str(linha[colunas["ip"] - 1]).strip()
                    if len(linha) >= colunas["ip"]
                    and linha[colunas["ip"] - 1]
                    else ""
                ),
                "serie": str(serie).strip(),
            })
        return inventario
    finally:
        planilha.close()


def _chave_cadastro_consolidado(nome, endereco):
    porta = str(endereco or "").strip().split()[0] if endereco else ""
    ip = _ip_normalizado(porta)
    if not ip:
        correspondencia = re.fullmatch(r"(.+)_\d+", porta)
        if correspondencia:
            ip = _ip_normalizado(correspondencia.group(1))
    if ip:
        return "ip", ip

    nome_normalizado = re.sub(r"\s+", " ", str(nome or "").strip()).casefold()
    return "porta", porta.casefold(), nome_normalizado


def _carregar_cadastro_consolidado():
    arquivo = _arquivo_lista_impressoras()
    if not arquivo.exists():
        raise FileNotFoundError(
            f"Planilha de impressoras não encontrada: {arquivo}"
        )

    cadastro = []
    chaves = set()
    planilha = openpyxl.load_workbook(arquivo, data_only=True, read_only=True)
    try:
        aba = planilha.active
        colunas = _colunas_cadastro(aba)
        for linha in aba.iter_rows(
            min_row=colunas["cabecalho"] + 1,
            values_only=True,
        ):
            endereco = (
                linha[colunas["ip"] - 1]
                if len(linha) >= colunas["ip"]
                else None
            )
            patrimonio = (
                linha[colunas["patrimonio"] - 1]
                if len(linha) >= colunas["patrimonio"]
                else None
            )
            modelo = (
                linha[colunas["modelo"] - 1]
                if len(linha) >= colunas["modelo"]
                else None
            )
            departamento_nome = (
                linha[colunas["nome"] - 1]
                if len(linha) >= colunas["nome"]
                else None
            )
            serie = (
                linha[colunas["serie"] - 1]
                if len(linha) >= colunas["serie"]
                else None
            )
            if (
                not endereco
                or not departamento_nome
            ):
                continue
            if len(linha) >= colunas["excluida"] and _registro_excluido(
                linha[colunas["excluida"] - 1]
            ):
                continue

            chave = _chave_cadastro_consolidado(departamento_nome, endereco)
            if chave in chaves:
                continue
            chaves.add(chave)
            cadastro.append({
                "endereco": str(endereco).strip(),
                "patrimonio": str(patrimonio or "").strip(),
                "modelo": str(modelo or "").strip(),
                "departamento_nome": str(departamento_nome or "").strip(),
                "serie": str(serie or "").strip(),
            })
    finally:
        planilha.close()

    arquivo_csv = BASE_DIR / NOME_CSV_LIMPO
    with arquivo_csv.open("r", encoding="utf-8-sig", newline="") as fonte:
        leitor = csv.DictReader(fonte)
        colunas = {
            str(coluna or "").strip().casefold(): coluna
            for coluna in (leitor.fieldnames or [])
        }
        if "name" not in colunas or "portname" not in colunas:
            raise ValueError(
                "O CSV de comparação precisa conter as colunas Name e PortName."
            )

        for linha in leitor:
            nome = str(linha.get(colunas["name"]) or "").strip()
            endereco = str(linha.get(colunas["portname"]) or "").strip()
            if not nome or not endereco:
                continue

            chave = _chave_cadastro_consolidado(nome, endereco)
            if chave in chaves:
                cadastro_existente = next(
                    (
                        item for item in cadastro
                        if _chave_cadastro_consolidado(
                            item["departamento_nome"],
                            item["endereco"],
                        ) == chave
                    ),
                    None,
                )
                if cadastro_existente:
                    if not cadastro_existente["departamento_nome"]:
                        cadastro_existente["departamento_nome"] = nome
                continue
            chaves.add(chave)
            cadastro.append({
                "endereco": endereco,
                "patrimonio": "",
                "modelo": "",
                "departamento_nome": nome,
                "serie": "",
            })

    return cadastro


@app.route("/api/impressoras/consolidado")
def baixar_cadastro_consolidado():
    try:
        cadastro = _carregar_cadastro_consolidado()
    except (
        OSError,
        UnicodeError,
        csv.Error,
        ValueError,
        InvalidFileException,
        zipfile.BadZipFile,
    ):
        logger.exception("Não foi possível gerar o cadastro consolidado.")
        return jsonify({
            "erro": "Não foi possível comparar as planilhas de impressoras."
        }), 500

    planilha = openpyxl.Workbook()
    aba = planilha.active
    aba.title = "Consolidado"
    aba.append([
        "IP",
        "Patrimônio",
        "Modelo",
        "Departamento e nome",
        "Número de série",
    ])
    for impressora in cadastro:
        aba.append([
            impressora["endereco"],
            impressora["patrimonio"],
            impressora["modelo"],
            impressora["departamento_nome"],
            impressora["serie"],
        ])

    arquivo = BytesIO()
    planilha.save(arquivo)
    planilha.close()
    arquivo.seek(0)
    return send_file(
        arquivo,
        mimetype=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        as_attachment=True,
        download_name=NOME_DOWNLOAD_CONSOLIDADO,
    )


# ==========================================================
# ORGANIZA OS DADOS DO SNMP COM OS GRUPOS DA PLANILHA
# ==========================================================
def _cadastros_por_ip(lista_planilha):
    por_ip = {}
    for item in lista_planilha:
        if item["excluida"]:
            continue
        cadastro_atual = por_ip.get(item["ip"])
        if (
            cadastro_atual is None
            or _qualidade_nome_cadastro(
                item["nome"],
                item["modelo_cadastro"],
            ) > _qualidade_nome_cadastro(
                cadastro_atual["nome"],
                cadastro_atual["modelo_cadastro"],
            )
        ):
            por_ip[item["ip"]] = item
    return por_ip


def _cadastros_para_relatorio_impressoes():
    return list(_cadastros_por_ip(
        carregar_lista_impressoras(exigir_arquivo=True)
    ).values())


def _dados_relatorio_impressoes(mes):
    return gerar_relatorio_impressoes(mes, _cadastros_para_relatorio_impressoes())


@app.route("/api/relatorio-impressoes")
def relatorio_impressoes():
    mes = request.args.get("mes", "")
    try:
        limites_mes(mes)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    try:
        return jsonify(_dados_relatorio_impressoes(mes))
    except (OSError, ValueError, sqlite3.Error, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível gerar o relatório de impressões.")
        return jsonify({"erro": "Não foi possível gerar o relatório de impressões."}), 503


@app.route("/api/relatorio-impressoes/excel")
def exportar_relatorio_impressoes():
    mes = request.args.get("mes", "")
    try:
        limites_mes(mes)
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    try:
        dados = _dados_relatorio_impressoes(mes)
    except (OSError, ValueError, sqlite3.Error, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível exportar o relatório de impressões.")
        return jsonify({"erro": "Não foi possível exportar o relatório de impressões."}), 503

    def texto_planilha(valor):
        texto = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(valor or ""))
        return "'" + texto if texto.lstrip().startswith(("=", "+", "-", "@")) else texto

    planilha = openpyxl.Workbook()
    aba = planilha.active
    aba.title = "Impressões"
    aba.append(["Relatório mensal de impressões", dados["mes"]])
    aba.append(["Início", dados["inicio"], "Fim", dados["fim"]])
    aba.append(["Diferença entre leituras. P&B e níveis de cor incluem cópias e impressões, sem fax; são independentes do contador geral. Confira datas e leituras ausentes."])
    aba.append(["Total calculado", dados["total_calculado"], "Equipamentos sem total", dados["sem_total"]])
    cabecalhos = [
        "Local", "Setor", "Patrimônio", "Modelo", "IP", "Contador inicial",
        "Data e hora inicial", "Contador final", "Data e hora final", "Impressões", "Situação",
        "Observação inicial", "Observação final",
        "Modelo previsto para coleta de cor", "Data e hora inicial cor", "Data e hora final cor",
        "Observação inicial cor", "Observação final cor",
    ]
    for descricao in ("P&B", "Cor nível 1", "Cor nível 2", "Cor nível 3"):
        cabecalhos.extend([f"{descricao} inicial", f"{descricao} final", f"{descricao} impressões", f"{descricao} situação"])
    aba.append(cabecalhos)
    for item in dados["itens"]:
        linha = [
            texto_planilha(item["nome"]), texto_planilha(item["grupo"]),
            texto_planilha(item["patrimonio"]), texto_planilha(item["modelo"]),
            texto_planilha(item["ip"]), item["contador_inicial"], item["coletado_inicial"],
            item["contador_final"], item["coletado_final"], item["impressoes"],
            texto_planilha(item["situacao"]), texto_planilha(item["erro_inicial"]),
            texto_planilha(item["erro_final"]),
            "Sim" if item["cor_aplicavel"] else "Não",
            item["cor_coletado_inicial"], item["cor_coletado_final"],
            texto_planilha(item["cor_erro_inicial"]), texto_planilha(item["cor_erro_final"]),
        ]
        for chave in ("preto_branco", "nivel_1", "nivel_2", "nivel_3"):
            categoria = item["categorias_cor"][chave]
            linha.extend([
                categoria["inicial"], categoria["final"], categoria["impressoes"],
                texto_planilha(categoria["situacao"] if item["cor_aplicavel"] else "Não disponível"),
            ])
        aba.append(linha)
    aba.freeze_panes = "A6"
    aba.auto_filter.ref = f"A5:{openpyxl.utils.get_column_letter(len(cabecalhos))}{max(5, aba.max_row)}"
    for celula in aba[5]:
        celula.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
        celula.fill = openpyxl.styles.PatternFill("solid", fgColor="17365D")
    for letra, largura in zip("ABCDEFGHIJKLM", (40, 18, 22, 30, 18, 18, 23, 18, 23, 16, 45, 40, 40)):
        aba.column_dimensions[letra].width = largura
    for indice in range(14, len(cabecalhos) + 1):
        aba.column_dimensions[openpyxl.utils.get_column_letter(indice)].width = 25
    arquivo = BytesIO()
    planilha.save(arquivo)
    planilha.close()
    arquivo.seek(0)
    return send_file(
        arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"impressoes_{dados['mes']}.xlsx",
    )


def adicionar_grupos(impressoras):

    lista_planilha = carregar_lista_impressoras(incluir_excluidas=True)
    por_ip = _cadastros_por_ip(lista_planilha)
    ips_excluidos = {
        item["ip"]
        for item in lista_planilha
        if item["excluida"] and item["ip"] not in por_ip
    }

    for impressora in impressoras:

        ip = str(
            impressora.get("ip", "")
        ).strip()

        # ==================================================
        # 1 - ENCONTRA PELO IP
        # ==================================================

        cadastro = por_ip.get(ip)

        if cadastro:

            # Usa exatamente o grupo vindo da planilha
            impressora["grupo"] = cadastro["grupo"]

            # Mantém o nome/local exatamente como está na planilha
            impressora["nome_planilha"] = cadastro["nome"]
            impressora["serie_planilha"] = cadastro["serie_planilha"]
            impressora["patrimonio_planilha"] = cadastro["patrimonio_planilha"]
            impressora["patrimonio"] = cadastro["patrimonio_planilha"]
            impressora["modelo_cadastro"] = cadastro["modelo_cadastro"]
            impressora["formato_cadastro"] = cadastro["formato_cadastro"]

            continue

        # ==================================================
        # 2 - NÃO ENCONTROU PELO IP
        #    TENTA PELO MODELO/NOME
        # ==================================================

        impressora["grupo"] = "OUTRAS"

    return [
        impressora
        for impressora in impressoras
        if str(impressora.get("ip", "")).strip() not in ips_excluidos
    ]


def _atualizar_cache_impressoras():
    global _impressoras_cache, _atualizacao_em_andamento

    try:
        impressoras = asyncio.run(obter_impressoras())
        impressoras = adicionar_grupos(impressoras)

        with _cache_lock:
            _impressoras_cache = impressoras
    except Exception:
        logger.exception("Falha ao atualizar os dados das impressoras.")
    finally:
        with _cache_lock:
            _atualizacao_em_andamento = False


def _iniciar_atualizacao_impressoras():
    global _atualizacao_em_andamento, _ultima_atualizacao

    with _cache_lock:
        agora = monotonic()
        if (
            _atualizacao_em_andamento
            or agora - _ultima_atualizacao < _INTERVALO_ATUALIZACAO
        ):
            return

        _atualizacao_em_andamento = True
        _ultima_atualizacao = agora
        atualizador = Thread(
            target=_atualizar_cache_impressoras,
            daemon=True
        )
        try:
            atualizador.start()
        except RuntimeError:
            _atualizacao_em_andamento = False
            logger.exception("Não foi possível iniciar a atualização das impressoras.")
            raise


# ==========================================================
# PÁGINA PRINCIPAL
# ==========================================================

@app.route("/")
def index():
    usuario = _obter_usuario_atual()
    permissoes = (
        list(PERMISSOES_PAINEL)
        if usuario["administrador"]
        else usuario["permissoes"]
    )
    grupos = []
    if "monitor.view" in permissoes:
        grupos = sorted({
            item["grupo"]
            for item in carregar_lista_impressoras()
        })
        _iniciar_atualizacao_impressoras()

    resposta = make_response(render_template(
        "index.html",
        impressoras=[],
        grupos=grupos,
        horario=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        usuario=usuario,
        permissoes=permissoes,
        administrador=usuario["administrador"],
        toner_sem_chip_ativo=True,
        csrf_token=_token_csrf(),
    ))
    resposta.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resposta.headers["Pragma"] = "no-cache"
    resposta.headers["Expires"] = "0"
    return resposta


# ==========================================================
# DADOS PARA ATUALIZAÇÃO DA TELA
# ==========================================================

@app.route("/dados")
def dados():

    _iniciar_atualizacao_impressoras()
    with _cache_lock:
        impressoras = [dict(impressora) for impressora in _impressoras_cache]
    logger.info(f"TOTAL DE IMPRESSORAS ENVIADAS AO PAINEL: {len(impressoras)}")




    return jsonify(
        impressoras
    )


def _encontrar_linha_cadastro(aba, ip, serie, patrimonio=None):
    ip_alvo = _ip_normalizado(ip)
    serie_alvo = _normalizar_numero_serie(serie)
    colunas = _colunas_cadastro(aba)
    correspondencias = []
    for numero_linha in range(colunas["cabecalho"] + 1, aba.max_row + 1):
        ip_linha = _ip_normalizado(
            aba.cell(numero_linha, colunas["ip"]).value
        )
        coluna_identificacao = colunas["serie"]
        identificacao_alvo = serie_alvo
        if patrimonio is not None:
            coluna_identificacao = colunas["patrimonio"]
            identificacao_alvo = _normalizar_numero_serie(patrimonio)
        serie_linha = _normalizar_numero_serie(
            aba.cell(numero_linha, coluna_identificacao).value
        )
        if ip_linha == ip_alvo and serie_linha == identificacao_alvo:
            correspondencias.append(numero_linha)
    return correspondencias


def _preparar_colunas_edicao(aba):
    linha_cabecalho = _linha_cabecalho_cadastro(aba)
    colunas = _colunas_cadastro(aba)
    if colunas["novo_formato"]:
        aba.cell(linha_cabecalho, colunas["serie"]).value = "Número de série"
    else:
        aba.cell(linha_cabecalho, colunas["patrimonio"]).value = "Patrimônio"
        aba.cell(linha_cabecalho, _COLUNA_SETOR).value = "Setor"
        aba.cell(linha_cabecalho, _COLUNA_MODELO).value = "Modelo"
    aba.cell(linha_cabecalho, _COLUNA_EXCLUIDA).value = "Excluída"


@app.route("/api/impressoras", methods=["POST"])
def cadastrar_impressora():
    global _ultima_atualizacao

    if not _validar_csrf():
        return jsonify({"erro": "A página expirou. Atualize e tente novamente."}), 403

    dados = request.form
    ip = dados.get("ip", "").strip()
    local = re.sub(r"\s+", " ", dados.get("nome", "").strip())
    setor = re.sub(r"\s+", " ", dados.get("setor", "").strip()).upper()
    modelo = re.sub(r"\s+", " ", dados.get("modelo", "").strip())
    patrimonio = dados.get("patrimonio", "").strip()
    serie = dados.get("serie", "").strip()

    if not ip or len(ip) > 45:
        return jsonify({"erro": "Informe o endereço IP da impressora."}), 400
    if not local or len(local) > 500:
        return jsonify({"erro": "Informe um local de até 500 caracteres."}), 400
    if not setor or len(setor) > 100:
        return jsonify({"erro": "Informe um setor de até 100 caracteres."}), 400
    if not modelo or len(modelo) > 200:
        return jsonify({"erro": "Informe um modelo de até 200 caracteres."}), 400
    if len(patrimonio) > 200 or len(serie) > 200:
        return jsonify({
            "erro": "Patrimônio e número de série devem ter até 200 caracteres."
        }), 400

    try:
        ip = str(ipaddress.IPv4Address(ip))
    except ipaddress.AddressValueError:
        return jsonify({"erro": "Informe um endereço IPv4 válido."}), 400

    identificadores = {
        identificador
        for identificador in (
            _normalizar_numero_serie(patrimonio),
            _normalizar_numero_serie(serie),
        )
        if identificador
    }
    if (patrimonio or serie) and not identificadores:
        return jsonify({
            "erro": "Informe um patrimônio ou número de série válido."
        }), 400

    arquivo = _arquivo_lista_impressoras()
    if not arquivo.exists():
        logger.error("Cadastro não encontrado para inclusão: %s", arquivo)
        return jsonify({"erro": "O cadastro de impressoras não foi encontrado."}), 500

    with _cadastro_lock:
        try:
            planilha = openpyxl.load_workbook(arquivo)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível abrir o cadastro para inclusão.")
            return jsonify({"erro": "Não foi possível abrir o cadastro atual."}), 500

        try:
            aba = planilha.active
            colunas = _colunas_cadastro(aba)
            if (
                colunas["serie"] == colunas["patrimonio"]
                and patrimonio
                and serie
            ):
                return jsonify({
                    "erro": (
                        "O cadastro atual aceita apenas um identificador. "
                        "Preencha patrimônio ou número de série, não ambos."
                    )
                }), 400

            colunas_identificadoras = {
                colunas["serie"],
                colunas["patrimonio"],
            }
            for numero_linha in range(
                colunas["cabecalho"] + 1,
                aba.max_row + 1,
            ):
                ip_cadastrado = str(
                    aba.cell(numero_linha, colunas["ip"]).value or ""
                ).replace("(Network)", "").strip().split()
                if ip_cadastrado and _ip_normalizado(ip_cadastrado[0]) == ip:
                    return jsonify({
                        "erro": "Este endereço IP já está cadastrado."
                    }), 409

                identificadores_cadastrados = {
                    _normalizar_numero_serie(
                        aba.cell(numero_linha, coluna).value
                    )
                    for coluna in colunas_identificadoras
                }
                if identificadores & identificadores_cadastrados:
                    return jsonify({
                        "erro": (
                            "O patrimônio ou número de série já está "
                            "cadastrado para outra impressora."
                        )
                    }), 409

            nome_cadastrado = (
                f"{setor} - {local}"
                if colunas["novo_formato"]
                else f"{local} ({modelo})"
            )
            if len(nome_cadastrado) > 500:
                return jsonify({
                    "erro": "A combinação de setor e local excede 500 caracteres."
                }), 400

            _preparar_colunas_edicao(aba)
            max_coluna = max(
                colunas["nome"],
                colunas["ip"],
                colunas["patrimonio"],
                colunas["modelo"],
                colunas["serie"],
                colunas["setor"] or 0,
                colunas["excluida"],
            )
            nova_linha = [None] * max_coluna
            nova_linha[colunas["nome"] - 1] = nome_cadastrado
            nova_linha[colunas["ip"] - 1] = ip
            nova_linha[colunas["modelo"] - 1] = modelo
            if colunas["novo_formato"]:
                nova_linha[colunas["patrimonio"] - 1] = patrimonio or None
                nova_linha[colunas["serie"] - 1] = serie or None
            else:
                nova_linha[colunas["patrimonio"] - 1] = patrimonio or serie or None
                nova_linha[colunas["setor"] - 1] = setor
            nova_linha[colunas["excluida"] - 1] = None
            aba.append(nova_linha)
            _salvar_cadastro_atualizado(planilha)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível cadastrar a impressora pelo painel.")
            return jsonify({
                "erro": "Não foi possível salvar a impressora no cadastro."
            }), 500
        finally:
            planilha.close()

    with _cache_lock:
        _ultima_atualizacao = 0.0

    logger.info("Impressora cadastrada pelo painel.")
    return jsonify({"sucesso": True}), 201


@app.route("/api/impressoras/editar", methods=["PUT"])
def editar_impressora():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    ip = dados.get("ip")
    serie_original = dados.get("serie_original", "")
    patrimonio_original = dados.get("patrimonio_original")
    nome = dados.get("nome")
    setor = dados.get("setor")
    serie = dados.get("serie", "")
    modelo = dados.get("modelo", "")
    patrimonio = dados.get("patrimonio", "")
    if not isinstance(ip, str) or not _ip_normalizado(ip):
        return jsonify({"erro": "O endereço IP do cadastro é inválido."}), 400
    if not isinstance(serie_original, str) or len(serie_original) > 200:
        return jsonify({"erro": "A série atual informada é inválida."}), 400
    if patrimonio_original is not None and (
        not isinstance(patrimonio_original, str)
        or len(patrimonio_original) > 200
    ):
        return jsonify({"erro": "O patrimônio atual informado é inválido."}), 400
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 500:
        return jsonify({"erro": "Informe um nome/local de até 500 caracteres."}), 400
    if not isinstance(setor, str) or not setor.strip() or len(setor.strip()) > 100:
        return jsonify({"erro": "Informe um setor de até 100 caracteres."}), 400
    if not isinstance(serie, str) or len(serie.strip()) > 200:
        return jsonify({"erro": "Informe um número de série de até 200 caracteres."}), 400
    if not isinstance(modelo, str) or len(modelo.strip()) > 200:
        return jsonify({"erro": "Informe um modelo de até 200 caracteres."}), 400
    if not isinstance(patrimonio, str) or len(patrimonio.strip()) > 200:
        return jsonify({"erro": "Informe um patrimônio de até 200 caracteres."}), 400

    ip = _ip_normalizado(ip)
    nome = nome.strip()
    setor = re.sub(r"\s+", " ", setor.strip()).upper()
    serie = serie.strip()
    modelo = modelo.strip()
    arquivo = _arquivo_lista_impressoras()
    if not arquivo.exists():
        logger.error("Cadastro não encontrado para edição: %s", arquivo)
        return jsonify({"erro": "O cadastro de impressoras não foi encontrado."}), 500

    with _cadastro_lock:
        try:
            planilha = openpyxl.load_workbook(arquivo)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível abrir o cadastro para edição.")
            return jsonify({"erro": "Não foi possível abrir o cadastro atual."}), 500

        try:
            aba = planilha.active
            colunas = _colunas_cadastro(aba)
            correspondencias = _encontrar_linha_cadastro(
                aba,
                ip,
                serie_original,
                patrimonio_original,
            )
            if len(correspondencias) != 1:
                return jsonify({
                    "erro": (
                        "A impressora não foi encontrada de forma única. "
                        "Atualize o painel e tente novamente."
                    )
                }), 409

            numero_linha = correspondencias[0]
            serie_normalizada = _normalizar_numero_serie(serie)
            if (
                colunas["serie"] != colunas["patrimonio"]
                and serie_normalizada
                and any(
                    _normalizar_numero_serie(
                        aba.cell(linha, colunas["serie"]).value
                    )
                    == serie_normalizada
                    for linha in range(
                        colunas["cabecalho"] + 1,
                        aba.max_row + 1,
                    )
                    if linha != numero_linha
                )
            ):
                return jsonify({
                    "erro": "Esse número de série já está cadastrado para outra impressora."
                }), 409

            _preparar_colunas_edicao(aba)
            if colunas["novo_formato"]:
                nome_cadastrado = nome
                aba.cell(numero_linha, colunas["nome"]).value = nome_cadastrado
                aba.cell(numero_linha, colunas["patrimonio"]).value = (
                    patrimonio.strip()
                )
            else:
                nome_cadastrado = nome
                aba.cell(numero_linha, colunas["nome"]).value = nome_cadastrado
                aba.cell(numero_linha, colunas["setor"]).value = setor
                aba.cell(numero_linha, colunas["patrimonio"]).value = (
                    patrimonio.strip() if "patrimonio" in dados else serie
                )
            if colunas["serie"] != colunas["patrimonio"]:
                aba.cell(numero_linha, colunas["serie"]).value = serie
            aba.cell(numero_linha, colunas["modelo"]).value = modelo
            aba.cell(numero_linha, colunas["excluida"]).value = None
            _salvar_cadastro_atualizado(planilha)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível salvar a edição da impressora %s.", ip)
            return jsonify({"erro": "Não foi possível salvar as alterações."}), 500
        finally:
            planilha.close()

    with _cache_lock:
        for impressora in _impressoras_cache:
            if (
                str(impressora.get("ip", "")).strip() == ip
                and (
                    _normalizar_numero_serie(
                        impressora.get("patrimonio_planilha", "")
                    ) == _normalizar_numero_serie(patrimonio_original)
                    if patrimonio_original is not None
                    else _normalizar_numero_serie(
                        impressora.get("serie_planilha", "")
                    ) == _normalizar_numero_serie(serie_original)
                )
            ):
                impressora["nome_planilha"] = nome_cadastrado
                impressora["grupo"] = setor
                patrimonio_salvo = (
                    patrimonio.strip()
                    if colunas["novo_formato"] or "patrimonio" in dados
                    else serie
                )
                impressora["serie_planilha"] = (
                    serie if colunas["novo_formato"] else patrimonio_salvo
                )
                impressora["modelo_cadastro"] = modelo
                impressora["patrimonio_planilha"] = patrimonio_salvo
                impressora["patrimonio"] = patrimonio_salvo

    logger.info("Cadastro atualizado pelo painel para a impressora %s.", ip)
    return jsonify({"sucesso": True})


@app.route("/api/impressoras/excluir", methods=["DELETE"])
def excluir_impressora():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    ip = dados.get("ip")
    serie = dados.get("serie", "")
    if not isinstance(ip, str) or not _ip_normalizado(ip):
        return jsonify({"erro": "O endereço IP do cadastro é inválido."}), 400
    if not isinstance(serie, str) or len(serie) > 200:
        return jsonify({"erro": "O número de série informado é inválido."}), 400
    ip = _ip_normalizado(ip)

    arquivo = _arquivo_lista_impressoras()
    if not arquivo.exists():
        logger.error("Cadastro não encontrado para exclusão: %s", arquivo)
        return jsonify({"erro": "O cadastro de impressoras não foi encontrado."}), 500

    with _cadastro_lock:
        try:
            planilha = openpyxl.load_workbook(arquivo)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível abrir o cadastro para exclusão.")
            return jsonify({"erro": "Não foi possível abrir o cadastro atual."}), 500

        try:
            aba = planilha.active
            colunas = _colunas_cadastro(aba)
            correspondencias = _encontrar_linha_cadastro(aba, ip, serie)
            if len(correspondencias) != 1:
                return jsonify({
                    "erro": (
                        "A impressora não foi encontrada de forma única. "
                        "Atualize o painel e tente novamente."
                    )
                }), 409
            if sum(
                _ip_normalizado(aba.cell(linha, colunas["ip"]).value) == ip
                for linha in range(colunas["cabecalho"] + 1, aba.max_row + 1)
            ) > 1:
                return jsonify({
                    "erro": (
                        "Este IP está associado a mais de um registro. "
                        "Regularize o cadastro antes de excluir pelo painel."
                    )
                }), 409

            _preparar_colunas_edicao(aba)
            aba.cell(
                correspondencias[0],
                colunas["excluida"],
            ).value = "SIM"
            _salvar_cadastro_atualizado(planilha)
        except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
            logger.exception("Não foi possível excluir a impressora %s.", ip)
            return jsonify({"erro": "Não foi possível excluir a impressora."}), 500
        finally:
            planilha.close()

    with _cache_lock:
        _impressoras_cache[:] = [
            impressora
            for impressora in _impressoras_cache
            if str(impressora.get("ip", "")).strip() != ip
        ]
        global _ultima_atualizacao
        _ultima_atualizacao = 0.0

    logger.info("Impressora %s excluída do painel.", ip)
    return jsonify({"sucesso": True})


@app.route("/api/relatorio-printer/historico", methods=["POST"])
def salvar_historico_printer():
    if not _validar_csrf():
        return jsonify({"erro": "A página expirou. Atualize e tente novamente."}), 403
    arquivo = request.files.get("relatorio")
    if not arquivo or not arquivo.filename:
        return jsonify({"erro": "Selecione um PDF do relatório PRINTER."}), 400
    nome = secure_filename(arquivo.filename.replace("\\", "/").rsplit("/", 1)[-1])
    conteudo = arquivo.read()
    if not nome.lower().endswith(".pdf") or not conteudo.startswith(b"%PDF-"):
        return jsonify({"erro": "Selecione um PDF válido."}), 400
    try:
        texto, _ = ler_relatorio_pdf(conteudo)
        dados = extrair_consumo_relatorio(texto)
    except RelatorioDependenciaAusente as erro:
        logger.error("Leitor de PDF indisponível: %s", erro)
        return jsonify({"erro": str(erro)}), 503
    except RelatorioInvalido as erro:
        return jsonify({"erro": str(erro)}), 400

    digest = hashlib.sha256(conteudo).hexdigest()
    esperado = request.form.get("substituir_sha256", "")
    try:
        resultado, sha256_existente = printer_repo.salvar_relatorio(
            dados, nome, conteudo, digest, esperado
        )
    except sqlite3.Error:
        logger.exception("Não foi possível salvar o relatório PRINTER.")
        return jsonify({"erro": "Não foi possível salvar o relatório no banco de dados."}), 500
    if resultado == printer_repo.RESULTADO_JA_SALVO:
        return jsonify({"mensagem": "Este PDF já está salvo.", "dados": dados})
    if resultado == printer_repo.RESULTADO_CONFLITO:
        return jsonify({
            "erro": "Já existe um relatório para este setor e mês.",
            "existente_sha256": sha256_existente,
            "dados": dados,
        }), 409
    if resultado == printer_repo.RESULTADO_ALTERADO:
        return jsonify({"erro": "O relatório anterior foi alterado. Atualize e tente novamente."}), 409
    return jsonify({"mensagem": "Relatório salvo com sucesso.", "dados": dados})


@app.route("/api/relatorio-printer/historico", methods=["GET"])
def listar_historico_printer():
    try:
        return jsonify({"relatorios": printer_repo.listar_relatorios()})
    except (sqlite3.Error, json.JSONDecodeError):
        logger.exception("Não foi possível consultar os relatórios PRINTER.")
        return jsonify({"erro": "Não foi possível consultar os relatórios salvos."}), 500


@app.route("/api/relatorio-printer/historico/<int:relatorio_id>/pdf")
def baixar_historico_printer(relatorio_id):
    try:
        linha = printer_repo.buscar_pdf(relatorio_id)
    except sqlite3.Error:
        logger.exception("Não foi possível baixar o relatório PRINTER.")
        return jsonify({"erro": "Não foi possível baixar o relatório."}), 500
    if not linha:
        return jsonify({"erro": "Relatório não encontrado."}), 404
    resposta = send_file(
        BytesIO(linha[1]), mimetype="application/pdf", as_attachment=True,
        download_name=linha[0], max_age=0,
    )
    resposta.headers["Cache-Control"] = "private, no-store"
    return resposta


@app.route("/api/relatorio-printer/analisar", methods=["POST"])
def analisar_relatorio_printer():
    arquivos = request.files.getlist("relatorios")
    if not arquivos:
        arquivo = request.files.get("relatorio")
        if arquivo is not None:
            arquivos = [arquivo]
    arquivos = [arquivo for arquivo in arquivos if arquivo.filename]
    if not arquivos:
        return jsonify({"erro": "Selecione pelo menos um PDF do relatório PRINTER."}), 400

    textos = []
    equipamentos_por_arquivo = []
    arquivos_com_erro = []
    for arquivo in arquivos:
        nome = Path(arquivo.filename).name
        if Path(nome).suffix.lower() != ".pdf":
            arquivos_com_erro.append({
                "arquivo": nome,
                "erro": "O arquivo não está no formato PDF.",
            })
            continue

        conteudo = arquivo.read()
        if not conteudo.startswith(b"%PDF-"):
            arquivos_com_erro.append({
                "arquivo": nome,
                "erro": "O arquivo não parece ser um PDF válido.",
            })
            continue

        try:
            texto, equipamentos = ler_relatorio_pdf(conteudo)
        except RelatorioDependenciaAusente as erro:
            logger.error("Leitor de PDF indisponível: %s", erro)
            return jsonify({"erro": str(erro)}), 503
        except RelatorioInvalido as erro:
            arquivos_com_erro.append({
                "arquivo": nome,
                "erro": str(erro),
            })
            continue

        textos.append(texto)
        equipamentos_por_arquivo.append((nome, equipamentos))

    if not equipamentos_por_arquivo:
        return jsonify({
            "erro": "Nenhum dos arquivos pôde ser analisado.",
            "arquivos_com_erro": arquivos_com_erro,
        }), 400

    try:
        inventario = carregar_inventario_relatorio()
    except (FileNotFoundError, OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível ler a planilha de cadastro para conferir o relatório.")
        return jsonify({
            "erro": "Não foi possível ler a planilha atual de impressoras. "
                    "Confira o arquivo de cadastro e tente novamente."
        }), 500

    try:
        locais_equivalentes = _carregar_locais_equivalentes()
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception("Não foi possível carregar as equivalências de locais.")
        return jsonify({
            "erro": "Não foi possível carregar as equivalências salvas dos locais."
        }), 500

    try:
        substituicoes = _resolver_substituicoes_relatorio(
            request.form.get("substituicoes", "[]"),
            equipamentos_por_arquivo,
            inventario,
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400

    equipamentos = []
    divergencias = []
    for nome, equipamentos_arquivo in equipamentos_por_arquivo:
        equipamentos_com_arquivo = [
            {**equipamento, "arquivo": nome}
            for equipamento in equipamentos_arquivo
        ]
        equipamentos.extend(equipamentos_com_arquivo)
        divergencias.extend(
            comparar_equipamentos(
                equipamentos_com_arquivo,
                inventario,
                locais_equivalentes,
                substituicoes,
            )
        )

    nomes_arquivos = [nome for nome, _ in equipamentos_por_arquivo]
    competencia = ", ".join(nomes_arquivos)
    assunto, corpo_email = criar_email(
        equipamentos,
        divergencias,
        "\n".join(textos),
        competencia,
        substituicoes,
    )

    return jsonify({
        "competencia": competencia,
        "arquivos_analisados": nomes_arquivos,
        "arquivos_com_erro": arquivos_com_erro,
        "total_analisado": len(equipamentos),
        "total_divergencias": len(divergencias),
        "total_substituicoes": len(substituicoes),
        "substituicoes": [
            {
                "ip": item["ip"],
                "serie_anterior": item["registro_anterior"]["serie"],
                "serie_nova": item["serie_nova"],
            }
            for item in substituicoes.values()
        ],
        "divergencias": divergencias,
        "assunto_email": assunto,
        "corpo_email": corpo_email,
    })


def _resolver_substituicoes_relatorio(
    substituicoes_json,
    equipamentos_por_arquivo,
    inventario,
):
    try:
        solicitadas = json.loads(substituicoes_json)
    except json.JSONDecodeError as erro:
        raise ValueError("A lista de substituições informada é inválida.") from erro
    if not isinstance(solicitadas, list):
        raise ValueError("A lista de substituições informada é inválida.")
    if not solicitadas:
        return {}

    equipamentos = [
        equipamento
        for _, itens in equipamentos_por_arquivo
        for equipamento in itens
    ]
    ocorrencias_serie = {}
    for equipamento in equipamentos:
        chave = re.sub(
            r"[^A-Z0-9]", "", str(equipamento.get("serie", "")).upper()
        )
        ocorrencias_serie[chave] = ocorrencias_serie.get(chave, 0) + 1

    cadastro_por_serie = {}
    cadastro_por_ip = {}
    for item in inventario:
        serie = re.sub(
            r"[^A-Z0-9]", "", str(item.get("serie", "")).upper()
        )
        if serie:
            cadastro_por_serie.setdefault(serie, []).append(item)

        ip_cadastrado = (
            str(item.get("ip", ""))
            .replace("(Network)", "")
            .strip()
            .split()
        )
        if ip_cadastrado:
            cadastro_por_ip.setdefault(ip_cadastrado[0], []).append(item)

    resultado = {}
    ips_utilizados = set()
    for solicitacao in solicitadas:
        if not isinstance(solicitacao, dict):
            raise ValueError("Cada substituição deve informar série e IP.")
        serie_nova = solicitacao.get("serie")
        ip = solicitacao.get("ip")
        if (
            not isinstance(serie_nova, str)
            or not serie_nova.strip()
            or not isinstance(ip, str)
            or not ip.strip()
        ):
            raise ValueError("Cada substituição deve informar série e IP.")

        chave_serie = re.sub(
            r"[^A-Z0-9]", "", serie_nova.strip().upper()
        )
        if chave_serie in resultado:
            raise ValueError("A série nova foi informada mais de uma vez.")
        if ocorrencias_serie.get(chave_serie) != 1:
            raise ValueError(
                "A série nova deve aparecer uma única vez nos relatórios enviados."
            )
        if cadastro_por_serie.get(chave_serie):
            raise ValueError(
                "A série nova já consta no cadastro; não é necessário marcá-la "
                "como substituição."
            )

        try:
            ip = str(ipaddress.IPv4Address(ip.strip()))
        except ipaddress.AddressValueError as erro:
            raise ValueError("Informe um endereço IPv4 válido para a substituição.") from erro
        if ip in ips_utilizados:
            raise ValueError("O mesmo IP não pode ser usado em duas substituições.")
        ips_utilizados.add(ip)

        registros_ip = cadastro_por_ip.get(ip, [])
        if len(registros_ip) != 1:
            raise ValueError(
                "O IP informado precisa identificar exatamente uma impressora "
                "no cadastro atual."
            )
        registro_anterior = registros_ip[0]
        serie_anterior = re.sub(
            r"[^A-Z0-9]",
            "",
            str(registro_anterior.get("serie", "")).upper(),
        )
        if not serie_anterior or len(cadastro_por_serie.get(serie_anterior, [])) != 1:
            raise ValueError(
                "A série da impressora antiga não está identificada de forma "
                "única no cadastro."
            )

        resultado[chave_serie] = {
            "ip": ip,
            "serie_nova": serie_nova.strip(),
            "serie_anterior": serie_anterior,
            "registro_anterior": registro_anterior,
        }
    return resultado


@app.route("/api/relatorio-printer/aprovar-equivalencia", methods=["POST"])
def aprovar_equivalencia_relatorio_printer():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    serie = dados.get("serie")
    local_relatorio = dados.get("local_relatorio")
    local_cadastro = dados.get("local_cadastro")
    if any(
        not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > 500
        for valor in (serie, local_relatorio, local_cadastro)
    ):
        return jsonify({
            "erro": "Informe a série e os dois nomes de local para aprovar a equivalência."
        }), 400

    chave_serie = re.sub(r"[^A-Z0-9]", "", serie.strip().upper())
    local_relatorio_normalizado = normalizar_local_equivalencia(local_relatorio)
    if not chave_serie or not local_relatorio_normalizado:
        return jsonify({"erro": "A série ou o local informado é inválido."}), 400

    try:
        inventario = carregar_inventario_relatorio()
    except (FileNotFoundError, OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível conferir o cadastro para aprovar equivalência.")
        return jsonify({
            "erro": "Não foi possível conferir a impressora no cadastro atual."
        }), 500

    correspondencias = [
        item for item in inventario
        if re.sub(
            r"[^A-Z0-9]",
            "",
            str(item.get("serie", "")).strip().upper(),
        ) == chave_serie
    ]
    if len(correspondencias) != 1:
        return jsonify({
            "erro": (
                "A série não foi encontrada de forma única no cadastro; "
                "equivalência não salva."
            )
        }), 409
    if str(correspondencias[0].get("local", "")).strip() != local_cadastro.strip():
        return jsonify({
            "erro": "O local do cadastro mudou desde a análise; atualize o relatório."
        }), 409

    try:
        equivalencias = _carregar_locais_equivalentes()
        locais_serie = equivalencias.setdefault(chave_serie, [])
        if local_relatorio_normalizado not in locais_serie:
            locais_serie.append(local_relatorio_normalizado)
        _salvar_locais_equivalentes(equivalencias)
    except (OSError, json.JSONDecodeError, ValueError):
        logger.exception(
            "Não foi possível salvar equivalência para a série %s.",
            serie,
        )
        return jsonify({
            "erro": "Não foi possível salvar a equivalência do local."
        }), 500

    logger.info(
        "Equivalência de local aprovada para série %s: %s = %s",
        serie,
        local_relatorio.strip(),
        local_cadastro.strip(),
    )
    return jsonify({"sucesso": True})


@app.route("/api/relatorio-printer/aprovar-correcao", methods=["POST"])
def aprovar_correcao_relatorio_printer():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    serie = dados.get("serie")
    local = dados.get("local")
    if (
        not isinstance(serie, str)
        or not serie.strip()
        or not isinstance(local, str)
        or not local.strip()
        or len(local.strip()) > 500
    ):
        return jsonify({
            "erro": "Informe o número de série e um local válido para a correção."
        }), 400

    chave_serie = re.sub(r"[^A-Z0-9]", "", serie.strip().upper())
    arquivo_atual = _arquivo_lista_impressoras()
    if not arquivo_atual.exists():
        logger.error("Arquivo de cadastro não encontrado para correção: %s", arquivo_atual)
        return jsonify({"erro": "O arquivo de cadastro atual não foi encontrado."}), 500

    try:
        planilha = openpyxl.load_workbook(arquivo_atual)
    except (FileNotFoundError, OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível abrir o cadastro para aplicar a correção.")
        return jsonify({"erro": "Não foi possível abrir o arquivo de cadastro atual."}), 500

    arquivo_temporario = None
    try:
        aba = planilha.active
        colunas = _colunas_cadastro(aba)
        correspondencias = [
            aba.cell(numero_linha, colunas["nome"])
            for numero_linha in range(colunas["cabecalho"] + 1, aba.max_row + 1)
            if re.sub(
                r"[^A-Z0-9]",
                "",
                str(
                    aba.cell(numero_linha, colunas["serie"]).value or ""
                ).strip().upper(),
            ) == chave_serie
        ]

        if not correspondencias:
            return jsonify({
                "erro": (
                    "O número de série não foi encontrado no cadastro atual. "
                    "Se a impressora foi trocada e o IP permaneceu igual, "
                    "use “Considerar substituição (mesmo IP)” em vez de "
                    "corrigir o local."
                )
            }), 404
        if len(correspondencias) > 1:
            return jsonify({
                "erro": "O número de série aparece mais de uma vez no cadastro; correção cancelada."
            }), 409

        celula_local = correspondencias[0]
        local_anterior = str(celula_local.value or "").strip()
        local_aprovado = local.strip()
        if colunas["novo_formato"] and " - " in local_anterior:
            departamento = local_anterior.split(" - ", 1)[0].strip()
            if not local_aprovado.casefold().startswith(
                f"{departamento} - ".casefold()
            ):
                local_aprovado = f"{departamento} - {local_aprovado}"
        if local_anterior == local_aprovado:
            return jsonify({
                "erro": "O cadastro já contém esse local; nenhuma alteração foi feita."
            }), 409

        destino = BASE_DIR / NOME_PLANILHA_ATUALIZADA
        with tempfile.NamedTemporaryFile(
            prefix=".ImpressorasRBS_",
            suffix=".xlsx",
            dir=BASE_DIR,
            delete=False,
        ) as temporario:
            arquivo_temporario = Path(temporario.name)

        celula_local.value = local_aprovado
        planilha.save(arquivo_temporario)
        arquivo_temporario.replace(destino)
    except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception(
            "Não foi possível salvar a correção aprovada para a série %s.",
            serie,
        )
        return jsonify({
            "erro": "Não foi possível salvar a correção no arquivo atualizado."
        }), 500
    finally:
        planilha.close()
        if arquivo_temporario is not None and arquivo_temporario.exists():
            try:
                arquivo_temporario.unlink()
            except OSError:
                logger.exception(
                    "Não foi possível remover o arquivo temporário %s.",
                    arquivo_temporario,
                )

    logger.info(
        "Correção de local aprovada para a série %s: %s -> %s",
        serie,
        local_anterior,
        local_aprovado,
    )
    return jsonify({"sucesso": True})


@app.route("/api/relatorio-printer/aprovar-inclusao", methods=["POST"])
def aprovar_inclusao_relatorio_printer():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    serie = dados.get("serie")
    local = dados.get("local")
    modelo = dados.get("modelo")
    ip = dados.get("ip")
    substituir_ip = dados.get("substituir_ip") is True
    if any(
        not isinstance(valor, str) or not valor.strip() or len(valor.strip()) > 500
        for valor in (serie, local, modelo, ip)
    ):
        return jsonify({
            "erro": "Informe número de série, local, modelo e IP."
        }), 400

    try:
        ip = str(ipaddress.IPv4Address(ip.strip()))
    except ipaddress.AddressValueError:
        return jsonify({"erro": "Informe um endereço IPv4 válido."}), 400

    chave_serie = re.sub(r"[^A-Z0-9]", "", serie.strip().upper())
    if not chave_serie:
        return jsonify({"erro": "O número de série informado é inválido."}), 400

    arquivo_atual = _arquivo_lista_impressoras()
    if not arquivo_atual.exists():
        logger.error(
            "Arquivo de cadastro não encontrado para inclusão: %s",
            arquivo_atual,
        )
        return jsonify({"erro": "O arquivo de cadastro atual não foi encontrado."}), 500

    try:
        planilha = openpyxl.load_workbook(arquivo_atual)
    except (FileNotFoundError, OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível abrir o cadastro para incluir a impressora.")
        return jsonify({"erro": "Não foi possível abrir o arquivo de cadastro atual."}), 500

    arquivo_temporario = None
    try:
        aba = planilha.active
        colunas = _colunas_cadastro(aba)
        linhas_ip = []
        for numero_linha in range(colunas["cabecalho"] + 1, aba.max_row + 1):
            linha = tuple(
                aba.cell(numero_linha, coluna)
                for coluna in range(1, max(
                    colunas["nome"],
                    colunas["ip"],
                    colunas["serie"],
                    colunas["modelo"],
                ) + 1)
            )
            serie_cadastrada = re.sub(
                r"[^A-Z0-9]",
                "",
                str(linha[colunas["serie"] - 1].value or "").strip().upper(),
            )
            if serie_cadastrada == chave_serie:
                return jsonify({
                    "erro": "O número de série já existe no cadastro."
                }), 409

            ip_cadastrado = str(
                linha[colunas["ip"] - 1].value or ""
            ).strip()
            ip_cadastrado = ip_cadastrado.replace("(Network)", "").strip().split()
            if ip_cadastrado and ip_cadastrado[0] == ip:
                linhas_ip.append(linha)

        if linhas_ip:
            if len(linhas_ip) > 1:
                return jsonify({
                    "erro": (
                        "O IP aparece em mais de um registro; "
                        "a substituição foi cancelada."
                    )
                }), 409
            if not substituir_ip:
                registro_existente = linhas_ip[0]
                return jsonify({
                    "codigo": "ip_ja_cadastrado",
                    "erro": "O IP já está associado a outro registro no cadastro.",
                    "registro_existente": {
                        "nome": str(
                            registro_existente[colunas["nome"] - 1].value or ""
                        ).strip(),
                        "serie": str(
                            registro_existente[colunas["serie"] - 1].value or ""
                        ).strip(),
                    },
                }), 409

            linha_existente = linhas_ip[0]
            if colunas["novo_formato"]:
                linha_existente[colunas["nome"] - 1].value = local.strip()
                linha_existente[colunas["modelo"] - 1].value = modelo.strip()
            else:
                linha_existente[colunas["nome"] - 1].value = (
                    f"{local.strip()} ({modelo.strip()})"
                )
                linha_existente[colunas["modelo"] - 1].value = modelo.strip()
            linha_existente[colunas["ip"] - 1].value = ip
            linha_existente[colunas["serie"] - 1].value = serie.strip()
            acao = "substituição"
        else:
            if substituir_ip:
                return jsonify({
                    "erro": "O registro com esse IP não foi encontrado; inclusão cancelada."
                }), 409

            if colunas["novo_formato"]:
                nova_linha = [None] * colunas["excluida"]
                nova_linha[colunas["ip"] - 1] = ip
                nova_linha[colunas["modelo"] - 1] = modelo.strip()
                nova_linha[colunas["nome"] - 1] = local.strip()
                nova_linha[colunas["serie"] - 1] = serie.strip()
                aba.append(nova_linha)
            else:
                aba.append([
                    f"{local.strip()} ({modelo.strip()})",
                    ip,
                    serie.strip(),
                    None,
                    None,
                    modelo.strip(),
                ])
            acao = "inclusão"

        destino = BASE_DIR / NOME_PLANILHA_ATUALIZADA
        with tempfile.NamedTemporaryFile(
            prefix=".ImpressorasRBS_",
            suffix=".xlsx",
            dir=BASE_DIR,
            delete=False,
        ) as temporario:
            arquivo_temporario = Path(temporario.name)

        planilha.save(arquivo_temporario)
        arquivo_temporario.replace(destino)
    except (OSError, ValueError, InvalidFileException, zipfile.BadZipFile):
        logger.exception(
            "Não foi possível salvar a inclusão aprovada para a série %s.",
            serie,
        )
        return jsonify({
            "erro": "Não foi possível salvar a impressora no arquivo atualizado."
        }), 500
    finally:
        planilha.close()
        if arquivo_temporario is not None and arquivo_temporario.exists():
            try:
                arquivo_temporario.unlink()
            except OSError:
                logger.exception(
                    "Não foi possível remover o arquivo temporário %s.",
                    arquivo_temporario,
                )

    logger.info(
        "%s aprovada para impressora %s, IP %s, local %s.",
        acao.capitalize(),
        serie,
        ip,
        local,
    )
    return jsonify({"sucesso": True})


@app.errorhandler(RequestEntityTooLarge)
def arquivo_relatorio_excede_limite(_erro):
    return jsonify({
        "erro": "O PDF excede o limite de 10 MB."
    }), 413


def _cadastro_impressora_para_ficha(ip):
    return _cadastros_por_ip(
        carregar_lista_impressoras(exigir_arquivo=True)
    ).get(ip)


def _toners_compativeis_para_ficha(cadastro):
    modelos = _modelos_para_compatibilidade(
        cadastro["modelo_cadastro"] or cadastro["nome"]
    )
    compativeis = []
    for toner in listar_toners():
        if modelos & _modelos_para_compatibilidade(toner["modelos_compativeis"] or ""):
            compativeis.append({
                "marca": toner["marca"],
                "codigo": toner["codigo"],
                "cor": toner["cor"]
            })
    return compativeis


@app.route("/api/impressoras/<ip>/toners")
def toners_compativeis_impressora(ip):
    try:
        cadastro = _cadastro_impressora_para_ficha(ip)
        if cadastro is None:
            return jsonify({"erro": "Impressora não encontrada no cadastro."}), 404
        modelos = _modelos_para_compatibilidade(cadastro["modelo_cadastro"] or cadastro["nome"])
        return jsonify({
            "toners": _toners_compativeis_para_ficha(cadastro),
            "modelo_identificado": bool(modelos),
        })
    except (OSError, ValueError, sqlite3.Error, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível consultar os toners compatíveis.")
        return jsonify({"erro": "Não foi possível carregar os toners compatíveis."}), 503


@app.route("/api/impressoras/<ip>/contador")
def contador_paginas_impressora(ip):
    try:
        cadastro = _cadastro_impressora_para_ficha(ip)
        if cadastro is None:
            return jsonify({"erro": "Impressora não encontrada no cadastro."}), 404
        toners_compativeis = _toners_compativeis_para_ficha(cadastro)
    except (OSError, ValueError, sqlite3.Error, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível consultar o cadastro da impressora.")
        return jsonify({"erro": "Não foi possível carregar o cadastro da impressora."}), 503

    try:
        contador = asyncio.run(
            asyncio.wait_for(consultar_contador_paginas(ip), timeout=8)
        )
    except asyncio.TimeoutError:
        logger.warning("Tempo esgotado ao consultar o contador SNMP da impressora %s.", ip)
        return jsonify({
            "contador": None,
            "oid": None,
            "toners": toners_compativeis,
            "erro": "A consulta do contador de páginas demorou demais. Tente novamente.",
        })
    except RuntimeError as erro:
        logger.warning(
            "Não foi possível consultar o contador SNMP da impressora %s: %s",
            ip,
            erro
        )
        return jsonify({
            "contador": None,
            "oid": None,
            "toners": toners_compativeis,
            "erro": str(erro)
        })

    return jsonify({
        "contador": contador["contador"],
        "oid": contador["oid"],
        "toners": toners_compativeis
    })


# ==========================================================
# ESTOQUE DE TONERS
# ==========================================================

@app.route("/api/pedidos-estoque")
def listar_pedidos_estoque():
    try:
        return jsonify(listar_sugestoes_e_pedidos())
    except sqlite3.Error:
        logger.exception("Erro ao consultar pedidos de estoque.")
        return jsonify({"erro": "Não foi possível consultar os pedidos."}), 500


@app.route(
    "/api/pedidos-estoque/sugestoes/<string:semana>/adiar", methods=["POST"]
)
def adiar_sugestao_pedido_estoque(semana):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("data_verificacao"), str):
        return jsonify({"erro": "Informe a data para a nova verificação."}), 400
    try:
        adiar_sugestao_pedido(
            semana,
            dados["data_verificacao"],
            _obter_usuario_atual()["nome"],
        )
        return jsonify({"sucesso": True})
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 409
    except sqlite3.Error:
        logger.exception("Erro ao adiar a sugestão de estoque.")
        return jsonify({"erro": "Não foi possível adiar a sugestão."}), 500


@app.route("/api/pedidos-estoque", methods=["POST"])
def enviar_solicitacao_pedido_estoque():
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("semana"), str):
        return jsonify({"erro": "Dados da solicitação inválidos."}), 400
    try:
        pedido_id = criar_solicitacao_pedido(
            dados["semana"],
            dados.get("itens"),
            _obter_usuario_atual()["nome"],
            os.environ.get("EMAIL_ESTOQUE_SEMANAL", ""),
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    except sqlite3.Error:
        logger.exception("Erro ao preparar solicitação de pedido de estoque.")
        return jsonify({"erro": "Não foi possível preparar a solicitação."}), 500
    try:
        enviar_email_solicitacao(pedido_id)
        marcar_solicitacao_enviada(pedido_id)
        return jsonify({"sucesso": True, "pedido_id": pedido_id}), 201
    except ErroEnvioEmailEstoque as erro:
        try:
            cancelar_solicitacao_envio(pedido_id)
        except sqlite3.Error:
            logger.exception(
                "Falha ao cancelar solicitação após erro no envio de e-mail."
            )
            return jsonify({
                "erro": "O e-mail falhou e não foi possível limpar a solicitação."
            }), 500
        return jsonify({"erro": str(erro)}), 502
    except sqlite3.Error:
        logger.exception("E-mail enviado, mas não foi possível atualizar a solicitação.")
        return jsonify({
            "erro": "O e-mail foi enviado, mas não foi possível atualizar o status."
        }), 500


@app.route(
    "/api/pedidos-estoque/<int:pedido_id>/decisao", methods=["POST"]
)
def decidir_solicitacao_pedido_estoque(pedido_id):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict) or not isinstance(dados.get("decisao"), str):
        return jsonify({"erro": "Informe aceite ou recusa."}), 400
    try:
        decidir_solicitacao_pedido(pedido_id, dados["decisao"])
        return jsonify({"sucesso": True})
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 409
    except sqlite3.Error:
        logger.exception("Erro ao registrar decisão da solicitação de estoque.")
        return jsonify({"erro": "Não foi possível registrar a decisão."}), 500


@app.route("/api/pedidos-estoque/<int:pedido_id>/receber", methods=["POST"])
def receber_pedido_estoque(pedido_id):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados do recebimento inválidos."}), 400
    try:
        receber_pedido(pedido_id, dados.get("itens"), _obter_usuario_atual()["nome"])
        return jsonify({"sucesso": True})
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 400
    except sqlite3.Error:
        logger.exception("Erro ao receber pedido de estoque.")
        return jsonify({"erro": "Não foi possível registrar o recebimento."}), 500


@app.route(
    "/api/pedidos-estoque/<int:pedido_id>/cancelar-pendentes", methods=["POST"]
)
def cancelar_pendencias_pedido_estoque(pedido_id):
    try:
        itens_cancelados = cancelar_pendencias_pedido(
            pedido_id, _obter_usuario_atual()["nome"]
        )
        return jsonify({"sucesso": True, "itens_cancelados": itens_cancelados})
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 409
    except sqlite3.Error:
        logger.exception("Erro ao cancelar saldo pendente do pedido de estoque.")
        return jsonify({"erro": "Não foi possível cancelar o saldo pendente."}), 500


@app.route("/estoque")
def estoque():

    incluir_inativos = request.args.get(
        "incluir_inativos",
        ""
    ).strip().lower() in ("1", "true", "sim")
    toners = listar_toners(incluir_inativos)

    return jsonify(toners)


@app.route("/api/toners/compatibilidade")
def compatibilidade_toners():
    try:
        cadastros = _cadastros_por_ip(
            carregar_lista_impressoras(exigir_arquivo=True)
        )
        modelos_impressoras = [
            (item, _modelos_para_compatibilidade(item["modelo_cadastro"] or item["nome"]))
            for item in cadastros.values()
        ]
        usuario = _obter_usuario_atual()
        pode_ver_impressoras = usuario["administrador"] or "monitor.view" in usuario["permissoes"]
        contagens = {}
        impressoras_por_toner = {}
        for toner in listar_toners(incluir_inativos=True):
            modelos = _modelos_para_compatibilidade(toner["modelos_compativeis"] or "")
            compativeis = [
                item for item, modelo in modelos_impressoras if modelos & modelo
            ]
            contagens[toner["id"]] = len(compativeis) if modelos else None
            if pode_ver_impressoras and modelos:
                impressoras_por_toner[toner["id"]] = [
                    {
                        "nome": item["nome"],
                        "modelo": item["modelo_cadastro"],
                        "grupo": item["grupo"],
                        "ip": item["ip"],
                        "patrimonio": item["patrimonio_planilha"],
                    }
                    for item in compativeis
                ]
        resultado = {
            "contagens": contagens,
            "modelos_nao_identificados": sum(not modelo for _, modelo in modelos_impressoras),
        }
        if pode_ver_impressoras:
            resultado["impressoras_por_toner"] = impressoras_por_toner
        return jsonify(resultado)
    except (OSError, ValueError, sqlite3.Error, InvalidFileException, zipfile.BadZipFile):
        logger.exception("Não foi possível calcular a compatibilidade dos toners.")
        return jsonify({"erro": "Não foi possível calcular as impressoras compatíveis."}), 503


@app.route("/cadastrar-toner", methods=["POST"])
def cadastrar_toner_rota():

    dados = request.get_json(silent=True)

    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    marca = dados.get("marca")
    codigo = dados.get("codigo")
    cor = dados.get("cor")
    modelos_compativeis = dados.get("modelos_compativeis", "")

    if not all(
        isinstance(valor, str) and valor.strip()
        for valor in (marca, codigo, cor)
    ):
        return jsonify({
            "erro": "Preencha marca, código e cor."
        }), 400

    if not isinstance(modelos_compativeis, str):
        return jsonify({
            "erro": "Os modelos compatíveis devem ser informados como texto."
        }), 400

    try:
        estoque_inicial = dados.get("estoque")
        estoque_minimo = dados.get("estoque_minimo")

        if isinstance(estoque_inicial, bool) or isinstance(estoque_minimo, bool):
            raise ValueError

        if (
            isinstance(estoque_inicial, float)
            and not estoque_inicial.is_integer()
        ) or (
            isinstance(estoque_minimo, float)
            and not estoque_minimo.is_integer()
        ):
            raise ValueError

        estoque_inicial = int(estoque_inicial)
        estoque_minimo = int(estoque_minimo)

        if estoque_inicial < 0 or estoque_minimo < 0:
            raise ValueError

    except (TypeError, ValueError, OverflowError):
        return jsonify({
            "erro": "Estoque e estoque mínimo devem ser números inteiros não negativos."
        }), 400

    try:
        toner_id = cadastrar_toner(
            marca.strip(),
            codigo.strip(),
            cor.strip(),
            estoque_inicial,
            estoque_minimo,
            modelos_compativeis,
        )
    except sqlite3.Error:
        logger.exception("Erro ao cadastrar toner.")
        return jsonify({
            "erro": "Não foi possível cadastrar o toner."
        }), 500

    if toner_id is None:
        return jsonify({
            "erro": "Já existe um toner cadastrado com essa marca, código e cor."
        }), 409

    return jsonify({
        "sucesso": True,
        "toner_id": toner_id,
        "mensagem": "Toner cadastrado com sucesso."
    }), 201

@app.route("/ajustar-estoque/<int:toner_id>", methods=["POST"])
def ajustar_estoque_rota(toner_id):

    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"sucesso": False, "erro": "Informe os dados do ajuste."}), 400

    try:
        novo_estoque = ajustar_estoque_manual(
            toner_id,
            dados.get("acao"),
            dados.get("quantidade", 1),
            _obter_usuario_atual()["nome"],
        )

        return jsonify({
            "sucesso": True,
            "novo_estoque": novo_estoque
        })

    except ValueError as erro:
        return jsonify({
            "sucesso": False,
            "erro": str(erro)
        }), 400
    except sqlite3.Error:
        logger.exception("Erro ao ajustar o estoque do toner %s.", toner_id)
        return jsonify({"sucesso": False, "erro": "Não foi possível registrar o ajuste."}), 500


@app.route("/remover-toner/<int:toner_id>", methods=["DELETE"])
def remover_toner_rota(toner_id):

    try:

        remover_toner(toner_id)

        return jsonify({
            "sucesso": True,
            "mensagem": "Toner removido com sucesso."
        })

    except Exception as erro:

        return jsonify({
            "sucesso": False,
            "erro": str(erro)
        }), 400


@app.route("/reativar-toner/<int:toner_id>", methods=["POST"])
def reativar_toner_rota(toner_id):

    try:
        reativar_toner(toner_id)
        return jsonify({
            "sucesso": True,
            "mensagem": "Toner reativado com sucesso."
        })
    
    except ValueError as erro:
        return jsonify({"sucesso": False, "erro": str(erro)}), 404
    except sqlite3.Error:
        logger.exception("Erro ao reativar toner %s.", toner_id)
        return jsonify({
            "sucesso": False,
            "erro": "Não foi possível reativar o toner."
        }), 500


@app.route(
    "/toner/<int:toner_id>/modelos-compativeis",
    methods=["PUT"]
)
def atualizar_modelos_compativeis_rota(toner_id):

    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    modelos_compativeis = dados.get("modelos_compativeis")
    if not isinstance(modelos_compativeis, str):
        return jsonify({
            "erro": "Informe os modelos compatíveis como texto."
        }), 400

    try:
        atualizar_modelos_compativeis(
            toner_id,
            modelos_compativeis
        )
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 404
    except sqlite3.Error:
        logger.exception(
            "Erro ao atualizar modelos compatíveis do toner %s.",
            toner_id
        )
        return jsonify({
            "erro": "Não foi possível atualizar os modelos compatíveis."
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": "Modelos compatíveis atualizados."
    })


@app.route(
    "/toner/<int:toner_id>/estoque-minimo",
    methods=["PUT"]
)
def atualizar_estoque_minimo_rota(toner_id):
    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return jsonify({"erro": "Dados inválidos."}), 400

    estoque_minimo = dados.get("estoque_minimo")
    if (
        isinstance(estoque_minimo, bool)
        or not isinstance(estoque_minimo, (int, float))
        or (
            isinstance(estoque_minimo, float)
            and not estoque_minimo.is_integer()
        )
        or estoque_minimo < 0
        or estoque_minimo > 9223372036854775807
    ):
        return jsonify({
            "erro": "O estoque mínimo deve ser um número inteiro não negativo."
        }), 400

    try:
        atualizar_estoque_minimo(toner_id, int(estoque_minimo))
    except ValueError as erro:
        return jsonify({"erro": str(erro)}), 404
    except sqlite3.Error:
        logger.exception(
            "Erro ao atualizar o estoque mínimo do toner %s.",
            toner_id
        )
        return jsonify({
            "erro": "Não foi possível atualizar o estoque mínimo."
        }), 500

    return jsonify({
        "sucesso": True,
        "mensagem": "Estoque mínimo atualizado."
    })
    
@app.route("/historico")
def historico():

    # --------------------------------------------------
    # PAGINACAO: /historico?pagina=1&limite=50
    # --------------------------------------------------

    try:
        pagina = int(request.args.get("pagina", 1))
        limite = int(request.args.get("limite", 50))
    except (ValueError, TypeError):
        pagina = 1
        limite = 50

    pagina = max(1, pagina)
    limite = max(1, min(200, limite))
    offset = (pagina - 1) * limite

    entradas = []
    saidas = []
    saidas_automaticas = []
    offline = []


    # ==================================================
    # 1 - ENTRADAS E SAÍDAS DE TONER
    # ==================================================

    registros, total_movimentacoes = historico_repo.listar_movimentacoes(limite, offset)


    for registro in registros:

        item = {

            "id":
                registro["id"],

            "data":
                registro["data"],

            "tipo":
                registro["tipo"],

            "toner":
                (
                    registro["marca"]
                    + " - "
                    + registro["codigo"]
                    + " - "
                    + registro["cor"]
                ),

            "quantidade":
                registro["quantidade"],

            "ip_impressora":
                registro["ip_impressora"] or "-",

            "patrimonio":
                registro["patrimonio"] or "-",

            "responsavel":
                registro["responsavel"] or "-",

            "observacao":
                registro["observacao"] or "-"

        }


        if registro["tipo"] == "ENTRADA":

            entradas.append(item)

        elif registro["tipo"] == "SAIDA":

            saidas.append(item)

    locais_por_ip = {
        item["ip"]: item["nome"]
        for item in carregar_lista_impressoras()
    }

    for registro in historico_repo.listar_saidas_automaticas():
        ip_impressora = str(
            registro["ip_impressora"] or ""
        ).strip()
        local_impressora = str(
            registro["local_impressora"] or ""
        ).strip()
        if local_impressora in ("", "-"):
            local_impressora = locais_por_ip.get(
                ip_impressora,
                "-"
            )

        saidas_automaticas.append({
            "id": registro["id"],
            "data": registro["data"],
            "tipo": registro["tipo"],
            "toner": (
                registro["marca"]
                + " - "
                + registro["codigo"]
                + " - "
                + registro["cor"]
            ),
            "quantidade": registro["quantidade"],
            "ip_impressora": ip_impressora or "-",
            "patrimonio": registro["patrimonio"] or "-",
            "local_impressora": local_impressora or "-",
            "responsavel": registro["responsavel"] or "-",
            "observacao": registro["observacao"] or "-"
    })


    # ==================================================
    # 2 - IMPRESSORAS OFFLINE DE HOJE, SEM DUPLICAR POR IP
    # ==================================================

    eventos = historico_repo.listar_offline_hoje()


    for evento in eventos:

        horas = evento["duracao_minutos"] // 60


        if horas == 1:

           duracao= "1 hora"

        else:

          duracao = f"{horas} horas"


        offline.append({

            "id":
                evento["id"],

            "data":
                evento["data_registro"],

            "tipo":
                "OFFLINE",

            "toner":
                "-",

            "quantidade":
                "-",

            "ip_impressora":
                evento["ip_impressora"] or "-",

            "patrimonio":
                evento["patrimonio"] or "-",

            "responsavel":
                "-",

            "modelo":
                evento["modelo"] or "-",
                "duracao":
                   duracao,

            "observacao":
                (
                    f"Modelo / Local: "
                    f"{evento['modelo'] or '-'} | "
                    f"Offline por {duracao}."
                )

        })


    # ==================================================
    # RETORNA OS HISTÓRICOS SEPARADOS
    # ==================================================

    logger.info(
        "Historico consultado: pagina=%s limite=%s",
        pagina, limite
    )

    return jsonify({

        "entradas":
            entradas,

        "saidas":
            saidas,

        "saidas_automaticas":
            saidas_automaticas,

        "offline":
            offline,

        "paginacao": {
            "pagina":  pagina,
            "limite":  limite,
            "total":   total_movimentacoes,
            "paginas": (
                (total_movimentacoes + limite - 1) // limite
                if total_movimentacoes else 1
            ),
        },

    })
# ==================================================
# TONERS NÃO CONFIÁVEIS
# ==================================================
@app.route("/toners-nao-confiaveis")
def toners_nao_confiaveis():

    nao_confiaveis = verificar_toners_nao_confiaveis()
    cadastros = _cadastros_por_ip(carregar_lista_impressoras())
    with _cache_lock:
        cache = {item["ip"]: item for item in _impressoras_cache}

    resultado = []

    for ip, toner in nao_confiaveis:

        # Procura os dados históricos para descobrir
        # o nome da impressora
        impressora_nome = "-"

        for evento in historico_toner_6:

            if (
                evento.get("ip") == ip
                and evento.get("toner") == toner
            ):
                impressora_nome = evento.get(
                    "impressora",
                    "-"
                )

                break

        if ip in TONERS_SEM_CHIP and toner in TONERS_SEM_CHIP[ip]["cores"]:
            cadastro = cadastros.get(ip, {})
            impressora_nome = cadastro.get("nome", impressora_nome)
        estimativa = cache.get(ip, {}).get("niveis_estimados", {}).get(toner)
        resultado.append({
            "ip": ip,
            "impressora": impressora_nome,
            "toner": toner,
            "status": (
                "Sem chip; nível estimado" if estimativa and estimativa["nivel"] is not None
                else "Sem chip; estimativa indisponível"
            ) if ip in TONERS_SEM_CHIP and toner in TONERS_SEM_CHIP[ip]["cores"]
            else "Toner não confiável",
            "estimativa": estimativa,
        })

    return jsonify(resultado)

# ==========================================================
# INICIA O SERVIDOR
# ==========================================================
@app.route("/registrar-saida-toner", methods=["POST"])
def registrar_saida_toner_rota():

    try:

        dados = request.get_json()

        toner_id = dados.get("toner_id")
        quantidade = dados.get("quantidade")
        ip_impressora = dados.get("ip_impressora")
        patrimonio = dados.get("patrimonio")
        responsavel = dados.get("responsavel")
        observacao = dados.get("observacao")
        registrar_troca = dados.get("troca_sem_chip", False)
        if not isinstance(registrar_troca, bool):
            raise ValueError("A confirmação da troca deve ser verdadeira ou falsa.")


        if not toner_id:

            return jsonify({
                "erro": "Selecione o toner."
            }), 400


        if not quantidade:

            return jsonify({
                "erro": "Informe a quantidade."
            }), 400


        troca = None
        if registrar_troca:
            if str(quantidade).strip() != "1":
                raise ValueError("Para registrar uma troca, informe exatamente uma unidade.")
            ip_impressora = str(ip_impressora or "").strip()
            configuracao = TONERS_SEM_CHIP.get(ip_impressora)
            if not configuracao:
                raise ValueError("Esta impressora não está configurada para acompanhamento sem chip.")
            cadastro = _cadastros_por_ip(carregar_lista_impressoras(exigir_arquivo=True)).get(ip_impressora)
            if not cadastro or cadastro.get("patrimonio_planilha") != configuracao["patrimonio"]:
                raise ValueError("O patrimônio da impressora não corresponde ao cadastro esperado.")
            if patrimonio and patrimonio.strip() != configuracao["patrimonio"]:
                raise ValueError("O patrimônio informado não corresponde à impressora.")
            patrimonio = configuracao["patrimonio"]
            try:
                leitura = asyncio.run(asyncio.wait_for(
                    consultar_contador_paginas(ip_impressora), timeout=8
                ))
            except (asyncio.TimeoutError, RuntimeError) as erro:
                logger.warning("Não foi possível registrar troca sem chip em %s: %s", ip_impressora, erro)
                raise ValueError("Não foi possível ler o contador. A saída e a troca não foram registradas.") from erro
            troca = {
                "contador": leitura["contador"],
                "oid": leitura["oid"],
                "modelo": cadastro["modelo_cadastro"],
            }

        resultado = registrar_saida_toner(

            toner_id=int(toner_id),

            quantidade=int(quantidade),

            ip_impressora=ip_impressora,

            patrimonio=patrimonio,

            responsavel=responsavel,

            observacao=observacao,
            troca_sem_chip=troca

        )


        novo_estoque, aviso = resultado if troca is not None else (resultado, None)
        return jsonify({

            "sucesso": True,

            "novo_estoque": novo_estoque,

            "mensagem":
                "Saída e troca registradas com sucesso." if troca else "Saída registrada com sucesso.",
            "aviso": aviso,

        })


    except ValueError as erro:

        return jsonify({

            "sucesso": False,

            "erro": str(erro)

        }), 400
    except (sqlite3.Error, OSError):
        logger.exception("Erro ao registrar saída de toner.")
        return jsonify({"sucesso": False, "erro": "Não foi possível registrar a saída de toner."}), 500
    
if __name__ == "__main__":

   iniciar_agendador_estoque()
   iniciar_agendador_contadores(_cadastros_para_relatorio_impressoes)
   app.run(host=SERVIDOR_HOST, port=SERVIDOR_PORTA, debug=False)
    