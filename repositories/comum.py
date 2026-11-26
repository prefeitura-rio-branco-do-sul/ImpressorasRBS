"""Utilitários compartilhados pelos repositórios."""
from datetime import datetime

FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


def agora():
    return datetime.now().strftime(FORMATO_DATA)
