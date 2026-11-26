import asyncio
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import estoque
import suprimentos_snmp


class BaixaAutomaticaTests(unittest.TestCase):
    def test_coleta_usa_modelo_cadastrado_e_registra_uma_unica_saida(self):
        cadastro = [{
            "ip": "10.0.0.1", "excluida": False, "descricao": "SEMED - Escola",
            "patrimonio": "123", "setor": "SEMED", "modelo": "Kyocera TASKalfa 3554ci",
        }]
        with tempfile.TemporaryDirectory() as pasta, \
             patch.object(estoque, "BANCO", os.path.join(pasta, "teste.db")), \
             patch.object(suprimentos_snmp, "BASE_DIR", Path(pasta)), \
             patch.object(suprimentos_snmp, "logger"), \
             patch.object(suprimentos_snmp, "carregar_offline", return_value={}), \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar_suprimentos_e_presenca", new_callable=AsyncMock, return_value=(["Black"], "Modelo SNMP")), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=[["100"], ["5"], ["100"], ["100"], ["100"], ["100"]]), \
             patch.object(suprimentos_snmp, "atualizar_alerta_toner"), \
             patch.object(suprimentos_snmp, "limpar_historico_toner_6"):
            estoque.criar_banco()
            estoque.cadastrar_toner(
                "Kyocera", "TK-teste", "Preto", estoque=2,
                modelos_compativeis="Kyocera TASKalfa 3554ci",
            )
            for _ in range(3):
                asyncio.run(suprimentos_snmp.main())
            with closing(estoque.conectar()) as conexao:
                self.assertEqual(conexao.execute("SELECT estoque FROM toners").fetchone()[0], 1)
                saidas = conexao.execute(
                    "SELECT ip_impressora, local_impressora, observacao FROM movimentacoes WHERE tipo = 'SAIDA'"
                ).fetchall()
                self.assertEqual(len(saidas), 1)
                self.assertEqual(saidas[0][:2], ("10.0.0.1", "SEMED - Escola"))
                self.assertIn("5% para 100%", saidas[0][2])

    def test_sem_correspondencia_unica_nao_faz_baixa(self):
        with tempfile.TemporaryDirectory() as pasta, \
             patch.object(estoque, "BANCO", os.path.join(pasta, "teste.db")):
            estoque.criar_banco()
            estoque.cadastrar_toner("A", "A1", "Preto", estoque=1, modelos_compativeis="M2040")
            estoque.cadastrar_toner("B", "B1", "Preto", estoque=1, modelos_compativeis="M2040")
            estoque.registrar_nivel_toner("10.0.0.1", "M2040", "Preto", 5)
            resultado = estoque.registrar_nivel_toner("10.0.0.1", "M2040", "Preto", 100)
            self.assertEqual(resultado["status"], "varios_toners_compativeis")
            with closing(estoque.conectar()) as conexao:
                self.assertEqual(conexao.execute("SELECT COUNT(*) FROM movimentacoes WHERE tipo = 'SAIDA'").fetchone()[0], 0)
                self.assertEqual(conexao.execute("SELECT SUM(estoque) FROM toners").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
