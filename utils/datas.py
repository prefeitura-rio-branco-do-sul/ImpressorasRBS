"""Funções puras de datas."""
import re
from datetime import datetime


def limites_mes(mes):
    if not isinstance(mes, str) or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", mes):
        raise ValueError("Informe o mês no formato AAAA-MM.")
    ano, numero = map(int, mes.split("-"))
    if not 1 <= ano <= 9998:
        raise ValueError("Ano fora do intervalo permitido.")
    inicio = datetime(ano, numero, 1)
    fim = datetime(ano + 1, 1, 1) if numero == 12 else datetime(ano, numero + 1, 1)
    return inicio, fim
