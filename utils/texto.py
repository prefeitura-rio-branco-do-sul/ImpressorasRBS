"""Funções puras de normalização e extração de texto."""
import re


def normalizar_grupo(nome):
    if not nome:
        return "OUTRAS"

    grupo = str(nome).strip()
    if not grupo:
        return "OUTRAS"

    if "-" in grupo:
        grupo = grupo.split("-", 1)[0].strip()

    grupo = re.sub(r"\s+", " ", grupo).upper()
    return grupo or "OUTRAS"


def normalizar_numero_serie(serie):
    return re.sub(r"[^A-Z0-9]", "", str(serie or "").upper())


def modelo_do_nome(nome):
    correspondencia = re.search(
        r"\(([^()]*(?:KYOCERA|ECOSYS|BROTHER|TASKALFA|M\d{3,}|L\d{3,}|HL-[A-Z0-9-]+)[^()]*)\)\s*$",
        str(nome or ""),
        re.IGNORECASE,
    )
    return correspondencia.group(1).strip() if correspondencia else ""


def qualidade_nome_cadastro(nome, modelo):
    nome_normalizado = re.sub(r"[^A-Z0-9]", "", str(nome or "").upper())
    modelo_normalizado = re.sub(r"[^A-Z0-9]", "", str(modelo or "").upper())
    return bool(nome_normalizado and nome_normalizado != modelo_normalizado)


def registro_excluido(valor):
    return str(valor or "").strip().casefold() in {"sim", "true", "1", "excluída", "excluida"}


def modelos_da_descricao(descricao):
    modelos = set()
    for modelo in re.findall(
        r"(?<![A-Z0-9])(?:[A-Z]{1,3}\d{3,5}[A-Z0-9]*|\d{3,5}[A-Z]{1,3}[A-Z0-9]*)(?![A-Z0-9])",
        descricao.upper()
    ):
        modelos.add(modelo)
        familia = re.match(r"([A-Z]{1,3}\d{3,5})", modelo)
        if familia:
            modelos.add(familia.group(1))

    return modelos


def modelos_para_compatibilidade(descricao):
    descricao = re.sub(
        r"\b([A-Z]{1,3})[-\s]+(?=\d{3,5}\b)",
        r"\1",
        descricao.upper(),
    )
    return modelos_da_descricao(descricao)


def extrair_modelo_planilha(descricao):
    descricao = str(descricao or "").strip()

    modelo_kyocera = re.search(
        r"(?<![A-Z0-9])(?:[A-Z]{1,3}\d{3,5}[A-Z0-9]*|\d{3,5}[A-Z]{1,3}[A-Z0-9]*)(?![A-Z0-9])",
        descricao,
        re.IGNORECASE
    )
    if modelo_kyocera:
        return modelo_kyocera.group(0)

    # Ex.: "Kyocera ECOSYS M2040dn" retorna somente "M2040dn"
    if "(" in descricao and ")" in descricao:
        modelo_completo = descricao.rsplit("(", 1)[1].split(")", 1)[0].strip()
        partes = modelo_completo.split()
        if partes:
            return partes[-1].strip()

    return "Modelo não identificado"
