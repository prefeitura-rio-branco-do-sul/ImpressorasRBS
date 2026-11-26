import io
import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

class RelatorioInvalido(ValueError):
    pass


class RelatorioDependenciaAusente(RuntimeError):
    pass


_LINHA_EQUIPAMENTO = re.compile(
    r"^\s*(?P<codigo>\d{3,6})\s+"
    r"(?P<tipo>[^,\r\n]+),\s*"
    r"(?P<serie>[A-Z0-9]{8,14}),\s*"
    r"(?P<modelo>[^,\r\n]+),\s*"
    r"(?P<local>.*?)\s+C\.\s*ANT\.",
    re.IGNORECASE | re.MULTILINE,
)
_SCANNER = re.compile(r"\bSCANNERS?\b", re.IGNORECASE)
_PALAVRAS_GENERICAS = {
    "A", "AS", "DA", "DAS", "DE", "DO", "DOS", "E", "EM", "ESCOLA",
    "CMEI", "C", "M", "EMC", "RURAL", "SECRETARIA", "MUNICIPAL",
}

_SETORES_PRINTER = {"214": "Saúde", "114": "Tesouro", "213": "Educação"}
_SERVICOS_PAGINAS = {"353": "P&B", "355": "Cor nível 1", "356": "Cor nível 2", "357": "Cor nível 3"}
_OUTROS_SERVICOS = {
    "6": ("PAGINA", "LINEAR"),
    "40": ("SCANNER",),
    "702": ("SOFTWARES",),
    "1008": ("FRAGMENTADORA",),
    "1009": ("DIGITALIZA",),
}
_MESES = {
    nome: numero for numero, nome in enumerate(
        ("janeiro", "fevereiro", "marco", "abril", "maio", "junho",
         "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"), 1
    )
}
_INTEIRO_BR = r"(?:\d{1,3}(?:\.\d{3})+|\d+)"
_NUMERO_BR = r"(?:\d{1,3}(?:\.\d{3})+|\d+)(?:[,.]\d+)?"


def criar_tabela_historico_printer(conexao):
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS historico_relatorios_printer (
            id INTEGER PRIMARY KEY,
            setor TEXT NOT NULL,
            competencia TEXT NOT NULL,
            paginas INTEGER NOT NULL,
            categorias TEXT NOT NULL,
            pagina_metro_linear TEXT,
            nome_arquivo TEXT NOT NULL,
            arquivo_pdf BLOB NOT NULL,
            sha256 TEXT NOT NULL,
            salvo_em TEXT NOT NULL,
            UNIQUE(setor, competencia)
        )
    """)


def extrair_consumo_relatorio(texto):
    competencias = re.findall(
        r"DEMONSTRATIVO\s+DE\s+PRESTA\S{0,3}\s+DE\s+SERVI\S{0,3}\s*:\s*"
        r"([^\r\n]+)", texto, re.IGNORECASE,
    )
    centros = re.findall(
        r"^\s*CENTRO\s+DE\s+CUSTO\s*:\s*([^\r\n]*?)\s*\[(\d+)\]\s*$",
        texto, re.IGNORECASE | re.MULTILINE,
    )
    if not competencias or len(set(competencias)) != 1 or len(set(centros)) != 1:
        raise RelatorioInvalido("Não foi possível identificar uma única competência e centro de custo.")
    periodo = normalizar_local_equivalencia(competencias[0]).lower()
    match_periodo = re.fullmatch(r"([a-z]+)\s+de\s+(\d{4})", periodo)
    if not match_periodo or match_periodo.group(1) not in _MESES or int(match_periodo.group(2)) < 1:
        raise RelatorioInvalido("A competência do relatório não foi reconhecida.")
    centro_codigo = centros[0][1]
    if centro_codigo not in _SETORES_PRINTER:
        raise RelatorioInvalido("Centro de custo não reconhecido como Saúde, Tesouro ou Educação.")
    competencia = f"{match_periodo.group(2)}-{_MESES[match_periodo.group(1)]:02d}"

    cabecalhos = list(re.finditer(
        r"^.*FATURADO\s+POR.*CONSUMO.*FRANQUIA.*EXCEDENTE.*RETROATIVO.*$",
        texto, re.IGNORECASE | re.MULTILINE,
    ))
    if len(cabecalhos) != 1:
        raise RelatorioInvalido("O quadro de serviços não foi encontrado de forma única.")
    fim = re.search(r"^\s*TOTAIS\s*$", texto[cabecalhos[0].end():], re.IGNORECASE | re.MULTILINE)
    if not fim or not re.search(r"TOTAL\s+GERAL\s*:", texto[cabecalhos[0].end():], re.IGNORECASE):
        raise RelatorioInvalido("O relatório parece incompleto: faltam os totais finais.")
    resumo = texto[cabecalhos[0].end():cabecalhos[0].end() + fim.start()]
    padrao = re.compile(
        rf"^\s*(\d+)\s+(.+?)\s+({_NUMERO_BR})\s+({_NUMERO_BR})\s+"
        rf"({_NUMERO_BR})\s+({_NUMERO_BR})\s*$"
    )
    servicos = {}
    for linha in resumo.splitlines():
        if not linha.strip():
            continue
        registro = padrao.fullmatch(linha)
        if not registro or registro.group(1) in servicos:
            raise RelatorioInvalido("Há uma linha de serviço não reconhecida ou duplicada.")
        codigo, descricao, consumo = registro.group(1, 2, 3)
        servicos[codigo] = (descricao, consumo)
    if not servicos or not any(codigo in servicos for codigo in _SERVICOS_PAGINAS):
        raise RelatorioInvalido("O relatório não contém serviços de páginas reconhecidos.")

    detalhes = defaultdict(int)
    ocorrencias = Counter()
    linha_detalhe = re.compile(
        rf"^\s*(\d+)\s+.+?\s+({_INTEIRO_BR})\s+({_INTEIRO_BR})\s+"
        rf"({_INTEIRO_BR})\s+({_INTEIRO_BR})\s+({_INTEIRO_BR})\s*$"
    )
    for linha in texto[:cabecalhos[0].start()].splitlines():
        inicio = re.match(r"^\s*(\d+)\s+", linha)
        if not inicio or inicio.group(1) not in _SERVICOS_PAGINAS:
            continue
        registro = linha_detalhe.fullmatch(linha)
        if not registro:
            raise RelatorioInvalido("Uma linha de consumo de páginas não pôde ser lida.")
        detalhes[inicio.group(1)] += int(registro.group(5).replace(".", ""))
        ocorrencias[inicio.group(1)] += 1

    paginas = {}
    for codigo, (descricao, consumo) in servicos.items():
        descricao_normalizada = normalizar_local_equivalencia(descricao)
        if codigo in _SERVICOS_PAGINAS:
            if "IMPRESS" not in descricao_normalizada or not re.fullmatch(_INTEIRO_BR, consumo):
                raise RelatorioInvalido(f"O serviço de páginas {codigo} tem formato não reconhecido.")
            valor = int(consumo.replace(".", ""))
            if not ocorrencias[codigo] or detalhes[codigo] != valor:
                raise RelatorioInvalido(f"O consumo detalhado não confere com o total do serviço {codigo}.")
            paginas[_SERVICOS_PAGINAS[codigo]] = valor
        elif codigo not in _OUTROS_SERVICOS or not all(
            palavra in descricao_normalizada for palavra in _OUTROS_SERVICOS[codigo]
        ):
            raise RelatorioInvalido(f"Serviço {codigo} desconhecido; não é possível calcular o total com segurança.")
    if set(detalhes) - set(servicos):
        raise RelatorioInvalido("Há serviços de páginas detalhados que não constam no resumo.")
    return {
        "setor": _SETORES_PRINTER[centro_codigo],
        "competencia": competencia,
        "paginas": sum(paginas.values()),
        "categorias": paginas,
        "pagina_metro_linear": servicos.get("6", ("", None))[1],
    }


def extrair_equipamentos_relatorio(texto):
    equipamentos = []
    for correspondencia in _LINHA_EQUIPAMENTO.finditer(texto):
        tipo = correspondencia.group("tipo").strip()
        modelo = correspondencia.group("modelo").strip()
        if _SCANNER.search(f"{tipo} {modelo}"):
            continue

        equipamento = {
            "codigo": correspondencia.group("codigo").strip(),
            "tipo": tipo,
            "serie": correspondencia.group("serie").strip().upper(),
            "modelo": modelo,
            "local_relatorio": correspondencia.group("local").strip(),
        }
        equipamento["chave_serie"] = _normalizar_identificador(
            equipamento["serie"]
        )
        equipamentos.append(equipamento)
    return equipamentos


def ler_relatorio_pdf(conteudo):
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ModuleNotFoundError as erro:
        if erro.name != "pypdf":
            raise
        raise RelatorioDependenciaAusente(
            "O leitor de PDF não está instalado neste Python. "
            "Execute: python -m pip install -r requirements.txt"
        ) from erro

    try:
        leitor = PdfReader(io.BytesIO(conteudo), strict=False)
        if leitor.is_encrypted and not leitor.decrypt(""):
            raise RelatorioInvalido(
                "O PDF está protegido por senha. Envie uma cópia desbloqueada."
            )
        if len(leitor.pages) > 100:
            raise RelatorioInvalido(
                "O PDF excede o limite de 100 páginas."
            )
        texto = "\n".join(
            pagina.extract_text(extraction_mode="layout") or ""
            for pagina in leitor.pages
        )
    except RelatorioInvalido:
        raise
    except (PdfReadError, OSError, ValueError) as erro:
        raise RelatorioInvalido(
            "Não foi possível ler este PDF. Confira se o arquivo está íntegro."
        ) from erro

    equipamentos = extrair_equipamentos_relatorio(texto)
    if not equipamentos:
        raise RelatorioInvalido(
            "Não encontrei equipamentos no formato do relatório PRINTER. "
            "Se o PDF for uma digitalização, será necessário aplicar OCR antes."
        )
    return texto, equipamentos


def comparar_equipamentos(
    equipamentos,
    inventario,
    locais_equivalentes=None,
    substituicoes=None,
):
    locais_equivalentes = locais_equivalentes or {}
    substituicoes = substituicoes or {}
    cadastro_por_serie = defaultdict(list)
    for item in inventario:
        chave = _normalizar_identificador(item.get("serie", ""))
        if chave:
            cadastro_por_serie[chave].append(item)

    ocorrencias = Counter(
        item["chave_serie"] for item in equipamentos
    )
    divergencias = []

    for item in equipamentos:
        chave = item["chave_serie"]
        if ocorrencias[chave] > 1:
            divergencias.append({
                **item,
                "tipo_divergencia": "serie_duplicada_relatorio",
                "local_cadastro": "",
                "detalhe": (
                    "O mesmo número de série aparece mais de uma vez "
                    "no relatório."
                ),
            })
            continue

        correspondencias = cadastro_por_serie.get(chave, [])
        substituicao = substituicoes.get(chave)
        if not correspondencias and substituicao:
            correspondencias = [substituicao["registro_anterior"]]
        if not correspondencias:
            divergencias.append({
                **item,
                "tipo_divergencia": "nao_encontrado",
                "local_cadastro": "",
                "detalhe": (
                    "O número de série do relatório não foi encontrado "
                    "no cadastro municipal."
                ),
            })
            continue

        if len(correspondencias) > 1:
            locais = [str(registro.get("local", "")).strip()
                      for registro in correspondencias]
            divergencias.append({
                **item,
                "tipo_divergencia": "serie_duplicada_cadastro",
                "local_cadastro": " / ".join(local for local in locais if local),
                "detalhe": (
                    "O número de série está associado a mais de um "
                    "equipamento no cadastro municipal."
                ),
            })
            continue

        local_cadastro = str(
            correspondencias[0].get("local", "")
        ).strip()
        serie_equivalencia = (
            substituicao["serie_anterior"] if substituicao else chave
        )
        equivalencias_serie = locais_equivalentes.get(
            serie_equivalencia, []
        )
        local_relatorio_normalizado = normalizar_local_equivalencia(
            item["local_relatorio"]
        )
        if (
            local_relatorio_normalizado not in equivalencias_serie
            and not locais_conferem(item["local_relatorio"], local_cadastro)
        ):
            divergencias.append({
                **item,
                "tipo_divergencia": "local_divergente",
                "local_cadastro": local_cadastro,
                "detalhe": (
                    "O local informado no relatório difere do local "
                    "registrado no cadastro municipal."
                ),
            })

    return divergencias


def normalizar_local_equivalencia(local):
    texto = _limpar_texto_pdf(str(local or ""))
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    ).upper()
    return " ".join(re.findall(r"[A-Z0-9]+", texto))


def locais_conferem(local_relatorio, local_cadastro):
    if str(local_relatorio or "").strip().casefold() == str(
        local_cadastro or ""
    ).strip().casefold():
        return True

    tokens_relatorio = _tokens_local(local_relatorio)
    tokens_cadastro = _tokens_local(
        _limpar_local_cadastro(local_cadastro)
    )
    if not tokens_relatorio or not tokens_cadastro:
        return False

    truncado = str(local_relatorio or "").rstrip().endswith(("..", "…"))
    ultimo_token = len(tokens_relatorio) - 1
    return all(
        any(
            _tokens_semelhantes(
                token,
                cadastrado,
                prefixo_curto=truncado and indice == ultimo_token,
            )
            or (
                truncado
                and indice == ultimo_token
                and len(token) >= 3
                and any(
                    SequenceMatcher(None, token, cadastrado[:len(token) + 1])
                    .ratio() >= 0.7
                    for cadastrado in tokens_cadastro
                    if len(cadastrado) >= len(token)
                )
            )
            for cadastrado in tokens_cadastro)
        for indice, token in enumerate(tokens_relatorio)
    )


def criar_email(
    equipamentos,
    divergencias,
    texto_pdf,
    nome_arquivo,
    substituicoes=None,
):
    substituicoes = list((substituicoes or {}).values())
    competencia = re.search(
        r"DEMONSTRATIVO\s+DE\s+PRESTA\S{0,3}\s+DE\s+SERVI\S{0,3}\s*:\s*([^\r\n]+)",
        texto_pdf,
        re.IGNORECASE,
    )
    centro_custo = re.search(
        r"^[^\r\n]*CENTRO\s+DE\s+CUSTO\s*:[ \t]*(.*)$",
        texto_pdf,
        re.IGNORECASE | re.MULTILINE,
    )
    periodo = (
        _limpar_texto_pdf(competencia.group(1))
        if competencia
        else _nome_relatorio(nome_arquivo)
    )
    setor = _limpar_texto_pdf(
        centro_custo.group(1) if centro_custo else ""
    ).strip()
    setor = re.sub(r"\s*\[\d+\]\s*$", "", setor).strip()
    if "SECRETARIA DE EDUCAO" in setor.upper():
        setor = "Secretaria de Educação"
    if not setor:
        setor = "unidade informada no relatório"
    assunto = f"Conferência do relatório PRINTER — {setor} — {periodo}"

    if divergencias:
        corpo = [
            "Olá, equipe do Patrimônio,",
            "",
            f"Na conferência do relatório PRINTER de {setor}, "
            f"referente a {periodo}, foram analisados "
            f"{len(equipamentos)} equipamentos e identificadas "
            f"{len(divergencias)} divergências para verificação:",
            "",
        ]
        corpo.extend(_texto_substituicoes(substituicoes))
        for numero, item in enumerate(divergencias, start=1):
            corpo.extend([
                f"{numero}. {item['detalhe']}",
                f"   Identificação PRINTER: {item['codigo']}",
                f"   Número de série: {item['serie']}",
                f"   Modelo no relatório: {item['modelo']}",
            ])
            if item.get("arquivo"):
                corpo.append(f"   Arquivo: {item['arquivo']}")
            corpo.append(f"   Local no relatório: {item['local_relatorio']}")
            if item["local_cadastro"]:
                corpo.append(
                    f"   Local no cadastro municipal: "
                    f"{item['local_cadastro']}"
                )
            corpo.append("")
        corpo.extend([
            "Por gentileza, poderiam verificar as informações acima e "
            "confirmar eventuais atualizações?",
            "",
            "Atenciosamente,",
            "[Seu nome / Setor de Patrimônio]",
        ])
    else:
        corpo = [
            "Olá, equipe do Patrimônio,",
            "",
            f"Na conferência do relatório PRINTER de {setor}, "
            f"referente a {periodo}, foram analisados "
            f"{len(equipamentos)} equipamentos.",
            "",
        ]
        if substituicoes:
            corpo.extend([
                "Não foram identificadas outras divergências. As "
                "substituições abaixo foram consideradas pela confirmação "
                "do mesmo IP, sem alteração do cadastro municipal:",
                "",
            ])
            corpo.extend(_texto_substituicoes(substituicoes))
        else:
            corpo.extend([
                "Não foram identificadas divergências entre os números de "
                "série e os locais informados no relatório e no cadastro "
                "municipal.",
                "",
            ])
        corpo.extend([
            "Atenciosamente,",
            "[Seu nome / Setor de Patrimônio]",
        ])

    return assunto, "\n".join(corpo)


def _texto_substituicoes(substituicoes):
    if not substituicoes:
        return []
    linhas = [
        "Substituições confirmadas (cadastro não alterado):",
    ]
    for item in substituicoes:
        registro_anterior = item["registro_anterior"]
        linhas.append(
            f"- IP {item['ip']}: série anterior "
            f"{registro_anterior['serie']} substituída pela série "
            f"{item['serie_nova']}."
        )
    linhas.append("")
    return linhas


def _normalizar_identificador(valor):
    return re.sub(r"[^A-Z0-9]", "", str(valor or "").upper())


def _limpar_local_cadastro(local):
    local = re.sub(
        r"\s+\((?:KYOCERA|EPSON|ECOSYS|TASKALFA|M\d|L\d)[^)]*\)\s*$",
        "",
        local.strip(),
        flags=re.IGNORECASE,
    )
    return re.sub(r"^[A-Z0-9]{2,8}\s*[-–]\s*", "", local)


def _tokens_local(local):
    texto = _limpar_texto_pdf(str(local or ""))
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caractere for caractere in texto
        if not unicodedata.combining(caractere)
    ).upper()
    tokens = re.findall(r"[A-Z0-9]+", texto)
    return [
        token for token in tokens
        if token not in _PALAVRAS_GENERICAS and len(token) >= 3
    ]


def _tokens_semelhantes(primeiro, segundo, prefixo_curto=False):
    if primeiro == segundo:
        return True
    menor, maior = sorted((primeiro, segundo), key=len)
    tamanho_minimo_prefixo = 3 if prefixo_curto else 4
    if len(menor) >= tamanho_minimo_prefixo and maior.startswith(menor):
        return True
    return (
        len(menor) >= 6
        and SequenceMatcher(None, primeiro, segundo).ratio() >= 0.85
    )


def _limpar_texto_pdf(texto):
    return str(texto or "").replace("\ufffd", "")


def _nome_relatorio(nome_arquivo):
    nome = str(nome_arquivo or "Relatório PRINTER").rsplit("/", 1)[-1]
    nome = nome.rsplit("\\", 1)[-1]
    return nome.rsplit(".", 1)[0] or "Relatório PRINTER"
