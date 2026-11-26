import unittest
from html.parser import HTMLParser
from pathlib import Path


class VerificadorEstruturaCartoes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.pilha = []
        self.erros = []

    def handle_starttag(self, tag, attrs):
        if tag in {"div", "button"}:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag not in {"div", "button"}:
            return
        if not self.pilha or self.pilha[-1] != tag:
            self.erros.append(f"Fechamento inesperado: {tag}")
            return
        self.pilha.pop()


class PainelHtmlTests(unittest.TestCase):
    def test_cartoes_fecham_antes_dos_graficos(self):
        template = (
            Path(__file__).resolve().parent.parent / "templates" / "index.html"
        ).read_text(encoding="utf-8")
        inicio = template.index('<div class="cartoes"')
        fim = template.index('<section class="graficos-painel"', inicio)
        verificador = VerificadorEstruturaCartoes()
        verificador.feed(template[inicio:fim])

        self.assertEqual(verificador.erros, [])
        self.assertEqual(verificador.pilha, [])


if __name__ == "__main__":
    unittest.main()
