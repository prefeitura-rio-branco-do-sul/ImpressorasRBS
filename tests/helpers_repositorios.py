import sqlite3
from unittest.mock import patch

from repositories import banco_repo, historico_repo, painel_repo, printer_repo, usuario_repo

REPOSITORIOS = (banco_repo, historico_repo, painel_repo, printer_repo, usuario_repo)


class PatchConectarRepositorios:
    """Faz todos os repositórios usarem o mesmo banco temporário."""

    def __init__(self, caminho_banco):
        self.patches = [
            patch.object(
                repositorio,
                "conectar",
                side_effect=lambda: sqlite3.connect(caminho_banco),
            )
            for repositorio in REPOSITORIOS
        ]

    def start(self):
        for item in self.patches:
            item.start()

    def stop(self):
        for item in reversed(self.patches):
            item.stop()
