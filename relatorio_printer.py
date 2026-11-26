"""Fachada de compatibilidade para o serviço de relatórios PRINTER."""

import sys as _sys
from types import ModuleType as _ModuleType

from monitor.reports.printer import service as _service
from monitor.reports.printer.service import (
    Counter,
    SequenceMatcher,
    defaultdict,
    io,
    re,
    unicodedata,
    RelatorioDependenciaAusente,
    RelatorioInvalido,
    comparar_equipamentos,
    criar_email,
    criar_tabela_historico_printer,
    extrair_consumo_relatorio,
    extrair_equipamentos_relatorio,
    ler_relatorio_pdf,
    locais_conferem,
    normalizar_local_equivalencia,
    _INTEIRO_BR,
    _LINHA_EQUIPAMENTO,
    _MESES,
    _NUMERO_BR,
    _OUTROS_SERVICOS,
    _PALAVRAS_GENERICAS,
    _SCANNER,
    _SERVICOS_PAGINAS,
    _SETORES_PRINTER,
    _limpar_local_cadastro,
    _limpar_texto_pdf,
    _nome_relatorio,
    _normalizar_identificador,
    _texto_substituicoes,
    _tokens_local,
    _tokens_semelhantes,
)


class _Fachada(_ModuleType):
    def __setattr__(self, nome, valor):
        if nome in (
            "locais_conferem",
            "normalizar_local_equivalencia",
            "extrair_equipamentos_relatorio",
        ):
            setattr(_service, nome, valor)
        super().__setattr__(nome, valor)


_sys.modules[__name__].__class__ = _Fachada
