import asyncio
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from io import BytesIO
from time import time
from unittest.mock import patch

import openpyxl

import app
import contadores_cor_kyocera as cor_kyocera
import estoque
import relatorio_impressoes as relatorio


def cadastro(ip="10.0.0.1", patrimonio="123", nome="Escola", modelo="Modelo", serie=""):
    return {
        "ip": ip, "nome": nome, "grupo": "Escolas", "modelo_cadastro": modelo,
        "patrimonio_planilha": patrimonio, "serie_planilha": serie, "excluida": False,
    }


class RelatorioImpressoesTests(unittest.TestCase):
    def setUp(self):
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        banco = patch.object(estoque, "BANCO", os.path.join(pasta.name, "teste.db"))
        banco.start()
        self.addCleanup(banco.stop)
        with closing(estoque.conectar()) as conexao, conexao:
            relatorio.criar_tabelas_contadores(conexao)
        self.itens = [cadastro(), cadastro("10.0.0.2", "456")]

    def coletar(self, momento, consulta):
        return relatorio.verificar_coleta_mensal(
            lambda: self.itens, agora=momento, relogio=lambda: momento, consulta=consulta,
        )

    def test_coleta_retorna_apenas_no_dia_1_e_retesta_falhas_sem_sobrescrever_sucessos(self):
        momento = datetime(2026, 12, 1)
        chamadas = []

        async def consulta(ip):
            chamadas.append(ip)
            if ip.endswith(".2") and chamadas.count(ip) == 1:
                raise RuntimeError("Sem resposta")
            return {"contador": 0 if ip.endswith(".1") else 200, "oid": "1.2.3"}

        self.assertFalse(self.coletar(momento - timedelta(days=1), consulta))
        self.assertTrue(self.coletar(momento, consulta))
        self.assertFalse(self.coletar(momento + timedelta(minutes=29), consulta))
        self.assertTrue(self.coletar(momento + timedelta(minutes=30), consulta))
        self.assertEqual(chamadas, ["10.0.0.1", "10.0.0.2", "10.0.0.2"])
        with closing(estoque.conectar()) as conexao:
            linhas = conexao.execute(
                "SELECT contador, coletado_em, erro FROM leituras_contadores_mensais ORDER BY ip"
            ).fetchall()
        self.assertEqual(linhas[0], (0, "2026-12-01T00:00:00", None))
        self.assertEqual(linhas[1], (200, "2026-12-01T00:30:00", None))

    def test_reserva_impede_coletas_concorrentes_e_permite_recuperar_interrupcao(self):
        momento = datetime(2026, 12, 1)
        comecou, liberar = threading.Event(), threading.Event()
        self.itens = self.itens[:1]

        async def consulta(ip):
            comecou.set()
            await asyncio.to_thread(liberar.wait, 5)
            return {"contador": 10, "oid": "1.2.3"}

        with ThreadPoolExecutor(max_workers=1) as executor:
            primeira = executor.submit(self.coletar, momento, consulta)
            try:
                self.assertTrue(comecou.wait(3))
                self.assertFalse(self.coletar(momento, consulta))
            finally:
                liberar.set()
            self.assertTrue(primeira.result(timeout=5))

        with closing(estoque.conectar()) as conexao, conexao:
            conexao.execute(
                "UPDATE coletas_contadores_mensais SET finalizado_em = NULL WHERE data = ?",
                ("2026-12-01",),
            )
        self.assertFalse(self.coletar(momento + timedelta(minutes=59), consulta))
        self.assertTrue(self.coletar(momento + timedelta(hours=1), consulta))

    def test_erro_no_cadastro_nao_trava_reserva_para_retentativa(self):
        momento = datetime(2026, 12, 1)
        with self.assertRaises(OSError):
            relatorio.verificar_coleta_mensal(
                lambda: (_ for _ in ()).throw(OSError("erro")), agora=momento,
                relogio=lambda: momento,
            )
        self.assertFalse(self.coletar(momento + timedelta(minutes=29), None))

        async def consulta(ip):
            return {"contador": 10, "oid": "1.2.3"}

        self.assertTrue(self.coletar(momento + timedelta(minutes=30), consulta))

    def test_descarta_resposta_que_termina_no_dia_seguinte(self):
        momento = datetime(2026, 12, 1, 23, 59, 59)

        async def consulta(ip):
            return {"contador": 10, "oid": "1.2.3"}

        relatorio.verificar_coleta_mensal(
            lambda: self.itens, agora=momento, consulta=consulta,
            relogio=lambda: momento + timedelta(seconds=2),
        )
        with closing(estoque.conectar()) as conexao:
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM leituras_contadores_mensais").fetchone()[0], 0)

    def test_relatorio_virada_de_ano_zero_ausente_e_coleta_tardia(self):
        async def inicio(ip):
            if ip.endswith(".2"):
                raise RuntimeError("Sem resposta")
            return {"contador": 0, "oid": "1.2.3"}

        async def fim(ip):
            return {"contador": 200, "oid": "1.2.3"}

        self.coletar(datetime(2026, 12, 1, 0, 30), inicio)
        self.coletar(datetime(2027, 1, 1), fim)
        resultado = relatorio.gerar_relatorio("2026-12", self.itens)
        self.assertEqual(resultado["fim"], "2027-01-01")
        primeiro, segundo = resultado["itens"]
        self.assertEqual((primeiro["contador_inicial"], primeiro["impressoes"]), (0, 200))
        self.assertIn("tardia", primeiro["situacao"])
        self.assertIsNone(segundo["impressoes"])
        self.assertEqual(segundo["erro_inicial"], "Sem resposta")
        self.assertEqual((resultado["total_calculado"], resultado["sem_total"]), (200, 1))
        vazio = relatorio.gerar_relatorio("2025-01", self.itens)
        self.assertIsNone(vazio["total_calculado"])
        self.assertEqual(vazio["sem_total"], 2)

    def test_troca_contador_reduzido_oid_diferente_e_registro_historico(self):
        self.itens = [cadastro()]
        async def leitura(valor, oid):
            return {"contador": valor, "oid": oid}

        self.coletar(datetime(2026, 12, 1), lambda ip: leitura(100, "1.2.3"))
        self.coletar(datetime(2027, 1, 1), lambda ip: leitura(20, "1.2.3"))
        resultado = relatorio.gerar_relatorio("2026-12", [cadastro(nome="Nome atual")])
        self.assertIsNone(resultado["itens"][0]["impressoes"])
        self.assertIn("diminuiu", resultado["itens"][0]["situacao"])
        self.assertEqual(resultado["itens"][0]["nome"], "Escola")
        with closing(estoque.conectar()) as conexao, conexao:
            conexao.execute(
                "UPDATE leituras_contadores_mensais SET contador = 200, oid = 'outro' WHERE data = '2027-01-01'"
            )
        resultado = relatorio.gerar_relatorio("2026-12", self.itens)
        self.assertIsNone(resultado["itens"][0]["impressoes"])
        self.assertIn("alterado", resultado["itens"][0]["situacao"])

    def test_identidade_repetida_cai_para_ip_e_alteracao_de_serie_nao_gera_total(self):
        self.itens = [
            cadastro("10.0.0.1", "123", serie="S1"),
            cadastro("10.0.0.2", "123"),
            cadastro("10.0.0.3", "123"),
        ]
        chaves = relatorio.identificar_cadastros(self.itens)
        self.assertEqual(set(chaves), {"serie:S1", "ip:10.0.0.2", "ip:10.0.0.3"})

        async def consulta(ip):
            return {"contador": 100, "oid": "1.2.3"}

        self.itens = [cadastro(serie="S1")]
        self.coletar(datetime(2026, 12, 1), consulta)
        self.itens = [cadastro(serie="S2")]
        self.coletar(datetime(2027, 1, 1), consulta)
        item = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertIsNone(item["impressoes"])
        self.assertIn("alterado", item["situacao"])

    def test_identificacao_por_ip_e_contador_invalido_sao_sinalizados(self):
        self.itens = [cadastro(patrimonio="")]

        async def invalida(ip):
            return {"contador": -1, "oid": "1.2.3"}

        self.coletar(datetime(2026, 12, 1), invalida)
        item = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertIn("inválido", item["erro_inicial"])
        self.assertIsNone(item["impressoes"])

        async def valida(ip):
            return {"contador": 100, "oid": "1.2.3"}

        self.coletar(datetime(2026, 12, 1, 0, 30), valida)
        self.coletar(datetime(2027, 1, 1), valida)
        item = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertEqual(item["impressoes"], 0)
        self.assertIn("tardia", item["situacao"])
        self.assertIn("IP", item["situacao"])

    def test_rotas_permissao_validacao_e_excel_sem_formulas(self):
        usuario = {"id": 123, "nome": "Teste", "usuario": "teste",
                   "administrador": False, "permissoes": ["monitor.view"], "ativo": True}
        self.itens = [cadastro(nome="=1+1")]
        async def consulta(ip):
            return {"contador": 10, "oid": "1.2.3"}
        self.coletar(datetime(2026, 12, 1), consulta)
        self.coletar(datetime(2027, 1, 1), consulta)
        cliente = app.app.test_client()
        with cliente.session_transaction() as sessao:
            sessao["presenca_atualizada_em"] = time()
        with patch.object(app, "_obter_usuario_atual", return_value=usuario), \
             patch.object(app, "_cadastros_para_relatorio_impressoes", return_value=self.itens):
            for url in ("/api/relatorio-impressoes", "/api/relatorio-impressoes/excel"):
                for mes in ("", "2026-13", "2026-1", "9999-12"):
                    self.assertEqual(cliente.get(url, query_string={"mes": mes}).status_code, 400)
            dados = cliente.get("/api/relatorio-impressoes?mes=2026-12").json
            self.assertEqual(dados["total_calculado"], 0)
            resposta = cliente.get("/api/relatorio-impressoes/excel?mes=2026-12")
            self.assertEqual(resposta.status_code, 200)
            aba = openpyxl.load_workbook(BytesIO(resposta.data)).active
            self.assertEqual(aba["A6"].value, "'=1+1")
            self.assertEqual(aba["A6"].data_type, "s")
            self.assertEqual((aba["F6"].value, aba["H6"].value, aba["J6"].value), (10, 10, 0))
            with patch.object(app, "_cadastros_para_relatorio_impressoes", side_effect=ValueError("erro interno")):
                self.assertEqual(cliente.get("/api/relatorio-impressoes?mes=2026-12").status_code, 503)
        usuario["permissoes"] = ["stock.view"]
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            for url in ("/api/relatorio-impressoes", "/api/relatorio-impressoes/excel"):
                self.assertEqual(cliente.get(url + "?mes=2026-12").status_code, 403)

    def test_coleta_cor_retesta_independentemente_do_contador_geral_e_calcula_niveis(self):
        self.itens = [cadastro(modelo="Kyocera TASKalfa 2554ci")]
        chamadas = []
        tentativa = {"valor": 0}
        inicio = {"preto_branco": 100, "nivel_1": 10, "nivel_2": 20, "nivel_3": 0}
        fim = {"preto_branco": 130, "nivel_1": 12, "nivel_2": 25, "nivel_3": 1}

        async def geral(ip):
            chamadas.append("geral")
            return {"contador": 999, "oid": "1.2.3"}

        def cor(ip):
            chamadas.append("cor")
            tentativa["valor"] += 1
            if tentativa["valor"] == 1:
                raise RuntimeError("Sem resposta")
            return inicio if tentativa["valor"] == 2 else fim

        def coletar(momento):
            return relatorio.verificar_coleta_mensal(
                lambda: self.itens, agora=momento, relogio=lambda: momento,
                consulta=geral, consulta_cor=cor,
            )

        coletar(datetime(2026, 12, 1))
        coletar(datetime(2026, 12, 1, 0, 30))
        self.assertEqual((chamadas.count("geral"), chamadas.count("cor")), (1, 2))
        coletar(datetime(2027, 1, 1))
        item = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertTrue(item["cor_aplicavel"])
        self.assertEqual(
            [item["categorias_cor"][campo]["impressoes"] for campo in inicio],
            [30, 2, 5, 1],
        )
        self.assertIn("tardia", item["categorias_cor"]["nivel_1"]["situacao"])
        self.assertEqual(item["cor_coletado_inicial"], "2026-12-01T00:30:00")
        usuario = {"id": 123, "nome": "Teste", "usuario": "teste",
                   "administrador": True, "permissoes": [], "ativo": True}
        cliente = app.app.test_client()
        with cliente.session_transaction() as sessao:
            sessao["presenca_atualizada_em"] = time()
        with patch.object(app, "_obter_usuario_atual", return_value=usuario), \
             patch.object(app, "_cadastros_para_relatorio_impressoes", return_value=self.itens):
            resposta = cliente.get("/api/relatorio-impressoes/excel?mes=2026-12")
        self.assertEqual(resposta.status_code, 200)
        aba = openpyxl.load_workbook(BytesIO(resposta.data)).active
        colunas = {celula.value: celula.column for celula in aba[5]}
        self.assertEqual(aba.cell(6, colunas["Cor nível 1 inicial"]).value, 10)
        self.assertEqual(aba.cell(6, colunas["Cor nível 1 final"]).value, 12)
        self.assertEqual(aba.cell(6, colunas["Cor nível 1 impressões"]).value, 2)
        with closing(estoque.conectar()) as conexao, conexao:
            conexao.execute("UPDATE leituras_cores_mensais SET nivel_2=1 WHERE data='2027-01-01'")
        item = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertIsNone(item["categorias_cor"]["nivel_2"]["impressoes"])
        self.assertEqual(item["categorias_cor"]["nivel_1"]["impressoes"], 2)

    def test_cores_sem_leitura_e_troca_de_equipamento_nao_geram_total(self):
        self.itens = [cadastro(modelo="Kyocera TASKalfa 2554ci", serie="A")]
        async def geral(ip):
            raise RuntimeError("Sem SNMP")
        def cor(ip):
            return {"preto_branco": 1, "nivel_1": 2, "nivel_2": 3, "nivel_3": 4}
        def coletar(momento):
            relatorio.verificar_coleta_mensal(
                lambda: self.itens, agora=momento, relogio=lambda: momento,
                consulta=geral, consulta_cor=cor,
            )
        coletar(datetime(2026, 12, 1))
        parcial = relatorio.gerar_relatorio("2026-12", self.itens)["itens"][0]
        self.assertIsNone(parcial["categorias_cor"]["nivel_1"]["impressoes"])
        self.itens = [cadastro(modelo="Kyocera TASKalfa 2554ci", serie="B")]
        coletar(datetime(2027, 1, 1))
        item = relatorio.gerar_relatorio("2026-12", [])["itens"][0]
        self.assertIsNone(item["categorias_cor"]["nivel_1"]["impressoes"])
        self.assertIn("alterado", item["categorias_cor"]["nivel_1"]["situacao"])


class ContadoresCorKyoceraTests(unittest.TestCase):
    def test_interpreta_copias_e_impressoes_por_nivel(self):
        modelo = """_pp.colorOrMono = 'color'; _pp.colorcoveragemode = '1';
        _pp.copyBlackWhite = ('100').toString(); _pp.printerBlackWhite = ('200').toString();"""
        cobertura = """_pp.counterLow = [parseInt('10', 10), parseInt('20', 10)];
        _pp.counterMiddle = [parseInt('0', 10), parseInt('4', 10)];
        _pp.counterHigh = [parseInt('1', 10), parseInt('2', 10)];"""
        self.assertEqual(cor_kyocera.interpretar_contadores(modelo, cobertura), {
            "preto_branco": 300, "nivel_1": 30, "nivel_2": 4, "nivel_3": 3,
        })
        with self.assertRaises(ValueError):
            cor_kyocera.interpretar_contadores(modelo, cobertura.replace("counterHigh", "ausente"))
        with self.assertRaises(ValueError):
            cor_kyocera.interpretar_contadores(modelo.replace("'color'", "'mono'"), cobertura)

    def test_nao_consulta_enderecos_publicos_ou_locais_do_servidor(self):
        for ip in ("127.0.0.1", "8.8.8.8", "nome-invalido"):
            with self.subTest(ip=ip), self.assertRaises(RuntimeError):
                cor_kyocera.consultar_contadores_cor(ip)


if __name__ == "__main__":
    unittest.main()
