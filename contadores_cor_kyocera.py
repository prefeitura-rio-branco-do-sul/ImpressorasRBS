import http.cookiejar
import http.client
import ipaddress
import re
import ssl
import urllib.error
import urllib.request

from config.configuracoes import KYOCERA_ESQUEMA_URL


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def modelo_compativel(modelo):
    return bool(re.search(r"\bTASKalfa\b.*\b\d+ci\b", modelo or "", re.IGNORECASE))


def interpretar_contadores(modelo, cobertura):
    def campo(nome):
        encontrado = re.search(
            rf"_pp\.{re.escape(nome)}\s*=\s*\(\s*'(\d+)'\s*\)\.toString\(\)\s*;",
            modelo,
        )
        if not encontrado:
            raise ValueError(f"Contador {nome} não encontrado.")
        return int(encontrado.group(1))

    def niveis(nome):
        encontrado = re.search(
            rf"_pp\.{re.escape(nome)}\s*=\s*\[\s*"
            r"parseInt\('(\d+)',\s*10\)\s*,\s*parseInt\('(\d+)',\s*10\)\s*\]\s*;",
            cobertura,
        )
        if not encontrado:
            raise ValueError(f"Contador {nome} não encontrado.")
        return sum(map(int, encontrado.groups()))

    if not re.search(r"_pp\.colorOrMono\s*=\s*'color'\s*;", modelo):
        raise ValueError("A impressora não informou contadores coloridos.")
    if not re.search(r"_pp\.colorcoveragemode\s*=\s*'1'\s*;", modelo):
        raise ValueError("A impressora não informou níveis de cobertura de cor.")
    return {
        "preto_branco": campo("copyBlackWhite") + campo("printerBlackWhite"),
        "nivel_1": niveis("counterLow"),
        "nivel_2": niveis("counterMiddle"),
        "nivel_3": niveis("counterHigh"),
    }


def consultar_contadores_cor(ip):
    try:
        endereco = ipaddress.ip_address(ip)
    except ValueError as erro:
        raise RuntimeError("Endereço IP inválido para consulta de cor.") from erro
    if endereco.version != 4 or not endereco.is_private or endereco.is_loopback:
        raise RuntimeError("A consulta de cor exige um IP privado IPv4.")

    base = f"{KYOCERA_ESQUEMA_URL}://{endereco}"
    contexto = ssl.create_default_context()
    contexto.check_hostname = False
    contexto.verify_mode = ssl.CERT_NONE
    navegador = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _SemRedirecionamento(),
        urllib.request.HTTPSHandler(context=contexto),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )

    def ler(caminho, referencia):
        requisicao = urllib.request.Request(
            base + caminho, headers={"Referer": base + referencia}
        )
        with navegador.open(requisicao, timeout=3) as resposta:
            conteudo = resposta.read(131073)
        if len(conteudo) > 131072:
            raise ValueError("Resposta da impressora excedeu o tamanho esperado.")
        return conteudo.decode("utf-8")

    try:
        raiz = ler("/", "/")
        inicio = ler("/startwlm/Start_Wlm.htm", "/")
        if "Start_Wlm.htm" not in raiz or "Counternav" not in inicio:
            raise ValueError("Interface de contadores Kyocera não reconhecida.")
        modelo = ler(
            "/js/jssrc/model/dvcinfo/dvccounter/DvcInfo_Counter_PrnCounter.model.htm",
            "/dvcinfo/dvccounter/DvcInfo_Counter_PrnCounter.htm",
        )
        cobertura = ler(
            "/js/jssrc/model/dvcinfo/dvccounter/DvcInfo_Counter_FuncCoverage.model.htm",
            "/dvcinfo/dvccounter/DvcInfo_Counter_FuncCoverage.htm",
        )
        return interpretar_contadores(modelo, cobertura)
    except (OSError, http.client.HTTPException, urllib.error.URLError, UnicodeError, ValueError) as erro:
        raise RuntimeError(f"Não foi possível ler os contadores de cor: {erro}") from erro
