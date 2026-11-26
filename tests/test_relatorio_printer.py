import unittest
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import relatorio_printer
from monitor.reports.printer import service
from relatorio_printer import (
    comparar_equipamentos,
    criar_email,
    extrair_consumo_relatorio,
    extrair_equipamentos_relatorio,
    locais_conferem,
    RelatorioInvalido,
)


def texto_consumo():
    return (
        "DEMONSTRATIVO DE PRESTAÇÃO DE SERVIÇO: Setembro de 2026\n"
        "CENTRO DE CUSTO: TESOURO [114]\n"
        "353 COPIA COPIAS E IMPRESSOES P&B 1.000 2.234 0 1.234 0\n"
        "355 COPIA COPIAS E IMPRESSOES COLOR 0 50 0 50 0\n"
        "40 FRANQUIA SCANNER 0 1 0 1 0\n"
        "CODIGO FATURADO POR DESCRICAO CONSUMO FRANQUIA EXCEDENTE RETROATIVO\n"
        "6 COPIA PAGINA/METRO LINEAR 58,90 0 0 0\n"
        "40 FRANQUIA LOCACAO SCANNER 1 1 0 0\n"
        "353 COPIA COPIAS E IMPRESSOES P&B 1.234 0 0 0\n"
        "355 COPIA COPIAS E IMPRESSOES COLOR 50 0 0 0\n"
        "TOTAIS\nTOTAL GERAL: R$ 1.000,00\n"
    )


class RelatorioPrinterTests(unittest.TestCase):
    def test_facade_monkeypatch_of_extrair_equipamentos_affects_pdf_reading(self):
        escritor = PdfWriter()
        escritor.add_blank_page(width=612, height=792)
        arquivo = BytesIO()
        escritor.write(arquivo)
        conteudo = arquivo.getvalue()
        equipamentos = [{"serie": "VR91282459"}]

        with patch.object(
            relatorio_printer, "extrair_equipamentos_relatorio", return_value=equipamentos
        ) as extrair:
            texto, resultado = relatorio_printer.ler_relatorio_pdf(conteudo)
            self.assertEqual(resultado, equipamentos)
            extrair.assert_called_once_with(texto)

        with self.assertRaises(RelatorioInvalido):
            relatorio_printer.ler_relatorio_pdf(conteudo)

    def test_facade_monkeypatch_of_normalizar_local_equivalencia_affects_comparison(self):
        equipamentos = extrair_equipamentos_relatorio(
            "4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "ALMOXARIFADO C. ANT."
        )
        cadastro = [{"serie": "VR91282459", "local": "FINANCEIRO"}]
        equivalencias = {"VR91282459": ["LOCAL APROVADO"]}
        self.assertEqual(len(comparar_equipamentos(equipamentos, cadastro, equivalencias)), 1)

        with patch.object(
            relatorio_printer, "normalizar_local_equivalencia", return_value="LOCAL APROVADO"
        ) as normalizar:
            self.assertEqual(comparar_equipamentos(equipamentos, cadastro, equivalencias), [])
            normalizar.assert_called_once_with("ALMOXARIFADO")

        self.assertEqual(len(comparar_equipamentos(equipamentos, cadastro, equivalencias)), 1)

    def test_facade_monkeypatch_of_locais_conferem_affects_comparison(self):
        equipamentos = extrair_equipamentos_relatorio(
            "4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "ALMOXARIFADO C. ANT."
        )
        cadastro = [{"serie": "VR91282459", "local": "FINANCEIRO"}]
        self.assertEqual(len(relatorio_printer.comparar_equipamentos(equipamentos, cadastro)), 1)

        with patch.object(relatorio_printer, "locais_conferem", return_value=True) as conferir:
            self.assertEqual(relatorio_printer.comparar_equipamentos(equipamentos, cadastro), [])
            conferir.assert_called_once_with("ALMOXARIFADO", "FINANCEIRO")

        self.assertEqual(len(relatorio_printer.comparar_equipamentos(equipamentos, cadastro)), 1)

    def test_facade_exports_original_functions_and_exceptions(self):
        for nome in (
            "RelatorioInvalido", "RelatorioDependenciaAusente",
            "criar_tabela_historico_printer", "extrair_consumo_relatorio",
            "extrair_equipamentos_relatorio", "ler_relatorio_pdf",
            "comparar_equipamentos", "normalizar_local_equivalencia",
            "locais_conferem", "criar_email",
        ):
            with self.subTest(nome=nome):
                self.assertIs(getattr(relatorio_printer, nome), getattr(service, nome))

    def test_reads_real_pdf_with_equipment(self):
        escritor = PdfWriter()
        pagina = escritor.add_blank_page(width=612, height=792)
        fonte = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        pagina[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): fonte}),
        })
        conteudo = DecodedStreamObject()
        conteudo.set_data(
            b"BT /F1 12 Tf 50 700 Td "
            b"(4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            b"POLO UNIVERSITARIO C. ANT.) Tj ET"
        )
        pagina[NameObject("/Contents")] = escritor._add_object(conteudo)
        arquivo = BytesIO()
        escritor.write(arquivo)

        texto, equipamentos = relatorio_printer.ler_relatorio_pdf(arquivo.getvalue())

        self.assertIn("POLO UNIVERSITARIO", texto)
        self.assertEqual(equipamentos[0]["serie"], "VR91282459")

    def test_rejects_invalid_pdf(self):
        with self.assertRaises(RelatorioInvalido):
            relatorio_printer.ler_relatorio_pdf(b"nao e um PDF")

    def test_consumo_separa_scanner_metro_linear_e_soma_paginas(self):
        resultado = extrair_consumo_relatorio(texto_consumo())
        self.assertEqual(resultado["competencia"], "2026-09")
        self.assertEqual(resultado["setor"], "Tesouro")
        self.assertEqual(resultado["paginas"], 1284)
        self.assertEqual(resultado["pagina_metro_linear"], "58,90")

    def test_consumo_recusa_total_inconsistente_incompleto_ou_desconhecido(self):
        texto = texto_consumo()
        for invalido in (
            texto.replace("1.234 0 0 0", "1.235 0 0 0"),
            texto.replace("TOTAL GERAL:", "TOTAL AUSENTE:"),
            texto.replace("40 FRANQUIA LOCACAO SCANNER", "41 FRANQUIA OUTRO SERVICO"),
            texto.replace("TESOURO [114]", "OUTRO [999]"),
        ):
            with self.subTest(invalido=invalido), self.assertRaises(RelatorioInvalido):
                extrair_consumo_relatorio(invalido)

    def test_extracts_equipment_fields(self):
        texto = (
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "POLO UNIVERSITARIO C. ANT. C. ATUAL."
        )

        equipamentos = extrair_equipamentos_relatorio(texto)

        self.assertEqual(len(equipamentos), 1)
        self.assertEqual(equipamentos[0]["codigo"], "4728")
        self.assertEqual(equipamentos[0]["serie"], "VR91282459")
        self.assertEqual(
            equipamentos[0]["local_relatorio"],
            "POLO UNIVERSITARIO",
        )

    def test_ignores_scanners(self):
        texto = (
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "POLO UNIVERSITARIO C. ANT.\n"
            "  4729 SCANNER COLORIDO, ABCD12345678, ScanJet Pro, "
            "POLO UNIVERSITARIO C. ANT.\n"
            "  4730 IMPRESSORA, ABCD12345679, Scanner MFP, "
            "POLO UNIVERSITARIO C. ANT."
        )

        equipamentos = extrair_equipamentos_relatorio(texto)

        self.assertEqual(len(equipamentos), 1)
        self.assertEqual(equipamentos[0]["serie"], "VR91282459")

    def test_accepts_abbreviated_report_locations(self):
        self.assertTrue(locais_conferem(
            "EM MARIA DA LUZ CRI..",
            "SEMED - E.M. Maria da Luz Christo Lima (Coordenação) "
            "(Kyocera ECOSYS M3655idn)",
        ))

    def test_detects_different_locations(self):
        self.assertFalse(locais_conferem(
            "COMPRAS",
            "SEMED - Financeiro (Kyocera ECOSYS M3145idn)",
        ))
        self.assertFalse(locais_conferem(
            "ALMOXARIFADO - ANDAR..",
            "SEMED - Almoxarifado (Kyocera ECOSYS M3145idn)",
        ))

    def test_exact_approved_abbreviated_location_matches(self):
        self.assertTrue(locais_conferem("E.M.", "E.M."))

    def test_compares_by_serial_and_generates_email(self):
        equipamento = extrair_equipamentos_relatorio(
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "POLO UNIVERSITARIO C. ANT."
        )
        cadastro = [{
            "serie": "VR91282459",
            "local": "SEMED - Polo Universitario "
                     "(Kyocera ECOSYS M2040dn)",
        }]

        divergencias = comparar_equipamentos(equipamento, cadastro)
        assunto, corpo = criar_email(
            equipamento,
            divergencias,
            "DEMONSTRATIVO DE PRESTACAO DE SERVICO: Outubro de 2026\n"
            "CENTRO DE CUSTO: SECRETARIA DE EDUCACAO",
            "Educacao.pdf",
        )

        self.assertEqual(divergencias, [])
        self.assertIn("Outubro de 2026", assunto)
        self.assertIn("Não foram identificadas divergências", corpo)

    def test_approved_local_alias_matches_future_reports(self):
        equipamento = extrair_equipamentos_relatorio(
            "  4728 IMPRESSORA MONO, VR91282459, ECOSYS M2040dn, "
            "POLO UNIVERSITARIO CENTRAL C. ANT."
        )
        cadastro = [{
            "serie": "VR91282459",
            "local": "SEMED - Polo Universitario "
                     "(Kyocera ECOSYS M2040dn)",
        }]
        equivalencias = {
            "VR91282459": ["POLO UNIVERSITARIO CENTRAL"],
        }

        divergencias = comparar_equipamentos(
            equipamento,
            cadastro,
            equivalencias,
        )

        self.assertEqual(divergencias, [])

    def test_confirmed_same_ip_replacement_uses_old_printer_and_mentions_it(self):
        equipamento = extrair_equipamentos_relatorio(
            "  4731 IMPRESSORA MONO, VR99355944, ECOSYS M2040dn, "
            "Local antigo C. ANT."
        )
        inventario = [{
            "serie": "VR91282459",
            "ip": "10.0.0.1",
            "local": "SEMED - Local antigo (Kyocera ECOSYS M2040dn)",
        }]
        substituicoes = {
            "VR99355944": {
                "ip": "10.0.0.1",
                "serie_nova": "VR99355944",
                "serie_anterior": "VR91282459",
                "registro_anterior": inventario[0],
            }
        }

        divergencias = comparar_equipamentos(
            equipamento,
            inventario,
            substituicoes=substituicoes,
        )
        _, corpo = criar_email(
            equipamento,
            divergencias,
            "DEMONSTRATIVO DE PRESTACAO DE SERVICO: Outubro de 2026\n"
            "CENTRO DE CUSTO: SECRETARIA DE EDUCACAO",
            "Educacao.pdf",
            substituicoes,
        )

        self.assertEqual(divergencias, [])
        self.assertIn("IP 10.0.0.1", corpo)
        self.assertIn("série anterior VR91282459", corpo)
        self.assertIn("série VR99355944", corpo)
        self.assertIn("sem alteração do cadastro municipal", corpo)


if __name__ == "__main__":
    unittest.main()
