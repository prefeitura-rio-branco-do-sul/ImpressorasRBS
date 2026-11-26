import asyncio
import tempfile
import unittest
from pathlib import Path
from time import time
from unittest.mock import AsyncMock, MagicMock, patch

import app
import suprimentos_snmp


class FichaImpressoraTests(unittest.TestCase):
    def setUp(self):
        usuario = {
            "id": 123, "nome": "Teste", "usuario": "teste",
            "administrador": True, "permissoes": [], "ativo": True,
        }
        usuario_patch = patch.object(app, "_obter_usuario_atual", return_value=usuario)
        usuario_patch.start()
        self.addCleanup(usuario_patch.stop)
        cadastro_patch = patch.object(app, "carregar_lista_impressoras", return_value=[
            {
                "ip": "10.0.0.1", "nome": "Unidade de teste",
                "modelo_cadastro": "Canon TM-300", "excluida": False,
            },
        ])
        cadastro_patch.start()
        self.addCleanup(cadastro_patch.stop)
        toners_patch = patch.object(app, "listar_toners", return_value=[
            {"marca": "Canon", "codigo": "PFI-120", "cor": "Preto",
             "modelos_compativeis": "Canon TM-200, Canon TM-300"},
            {"marca": "Outra", "codigo": "Outro", "cor": "Preto",
             "modelos_compativeis": "M2040"},
        ])
        toners_patch.start()
        self.addCleanup(toners_patch.stop)
        self.cliente = app.app.test_client()
        with self.cliente.session_transaction() as sessao:
            sessao["presenca_atualizada_em"] = time()

    @patch.object(app, "consultar_contador_paginas", new_callable=AsyncMock)
    def test_toners_usam_modelo_cadastrado_sem_aguardar_snmp(self, contador):
        resposta = self.cliente.get("/api/impressoras/10.0.0.1/toners")
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json["modelo_identificado"])
        self.assertEqual([item["codigo"] for item in resposta.json["toners"]], ["PFI-120"])
        contador.assert_not_called()

    @patch.object(app, "consultar_contador_paginas", new_callable=AsyncMock)
    def test_contador_preserva_toners_e_exibe_falha_snmp(self, contador):
        contador.side_effect = RuntimeError("Sem resposta SNMP.")
        resposta = self.cliente.get("/api/impressoras/10.0.0.1/contador")
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.json["contador"])
        self.assertEqual(resposta.json["erro"], "Sem resposta SNMP.")
        self.assertEqual([item["codigo"] for item in resposta.json["toners"]], ["PFI-120"])

    @patch.object(app, "consultar_contador_paginas", new_callable=AsyncMock)
    def test_contador_retornando_paginas(self, contador):
        contador.return_value = {"contador": 12345, "oid": "1.2.3"}
        resposta = self.cliente.get("/api/impressoras/10.0.0.1/contador")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["contador"], 12345)

    @patch.object(app, "consultar_contador_paginas", new_callable=AsyncMock)
    def test_consulta_lenta_retorna_indisponivel(self, contador):
        async def esgotar(corrotina, timeout):
            corrotina.close()
            self.assertEqual(timeout, 8)
            raise asyncio.TimeoutError()

        with patch.object(app.asyncio, "wait_for", side_effect=esgotar):
            resposta = self.cliente.get("/api/impressoras/10.0.0.1/contador")
        self.assertEqual(resposta.status_code, 200)
        self.assertIsNone(resposta.json["contador"])
        self.assertIn("demorou demais", resposta.json["erro"])

    def test_toners_exigem_permissao_de_monitoramento(self):
        usuario = {
            "id": 123, "nome": "Teste", "usuario": "teste",
            "administrador": False, "permissoes": ["stock.view"], "ativo": True,
        }
        with patch.object(app, "_obter_usuario_atual", return_value=usuario):
            resposta = self.cliente.get("/api/impressoras/10.0.0.1/toners")
        self.assertEqual(resposta.status_code, 403)


class ContadorSnmpTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrompe_percurso_ao_sair_da_arvore_do_contador(self):
        oid = suprimentos_snmp.OID_CONTADOR_PAGINAS
        chamadas = []

        class Valor:
            def __init__(self, valor):
                self.valor = valor

            def prettyPrint(self):
                return str(self.valor)

        async def caminhar(*args, **kwargs):
            chamadas.append(kwargs)
            yield None, None, None, [(oid + ".2.1", Valor(12))]
            yield None, None, None, [(oid + ".1.1", Valor(37))]
            yield None, None, None, [("1.3.6.1.2.1.43.10.2.1.5.1", Valor(99))]
            self.fail("A consulta continuou fora da árvore do contador.")

        transporte = MagicMock()
        transporte.create = AsyncMock(return_value=object())
        with patch.object(suprimentos_snmp, "SnmpDispatcher"), \
             patch.object(suprimentos_snmp, "UdpTransportTarget", transporte), \
             patch.object(suprimentos_snmp, "walk_cmd", caminhar):
            resultado = await suprimentos_snmp.consultar_contador_paginas("10.0.0.1")
        self.assertFalse(chamadas[0]["lexicographicMode"])
        self.assertEqual(resultado["contador"], 37)

    @patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock)
    async def test_falha_inicial_de_suprimentos_verifica_presenca_e_tenta_novamente(self, consultar):
        consultar.side_effect = [[], ["Modelo SNMP"], ["Toner"]]
        descricoes, modelo = await suprimentos_snmp.consultar_suprimentos_e_presenca("10.0.0.1")
        self.assertEqual((descricoes, modelo), (["Toner"], "Modelo SNMP"))
        self.assertEqual(consultar.await_count, 3)
        self.assertEqual(consultar.await_args_list[1].kwargs, {"timeout": 1.5, "retries": 1})

    @patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock)
    async def test_ausencia_de_suprimentos_nao_significa_impressora_offline(self, consultar):
        consultar.side_effect = [[], ["Modelo SNMP"], []]
        self.assertEqual(
            await suprimentos_snmp.consultar_suprimentos_e_presenca("10.0.0.1"),
            ([], "Modelo SNMP"),
        )

    @patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock)
    async def test_falha_das_duas_verificacoes_marca_indisponivel(self, consultar):
        consultar.side_effect = [[], []]
        self.assertEqual(
            await suprimentos_snmp.consultar_suprimentos_e_presenca("10.0.0.1"),
            (None, None),
        )
        self.assertEqual(consultar.await_count, 2)

    @patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock)
    async def test_suprimentos_disponiveis_nao_exigem_consulta_adicional(self, consultar):
        consultar.return_value = ["Toner"]
        self.assertEqual(
            await suprimentos_snmp.consultar_suprimentos_e_presenca("10.0.0.1"),
            (["Toner"], None),
        )
        consultar.assert_awaited_once()

    async def test_coleta_mantem_online_sem_suprimentos_e_nao_registra_nivel(self):
        cadastro = [{
            "ip": "10.0.0.1", "excluida": False, "descricao": "Escola",
            "patrimonio": "123", "setor": "SEMED", "modelo": "Modelo",
        }]
        offline = {"10.0.0.1": {"inicio": "01/01/2020 00:00:00", "registrado": True}}
        with tempfile.TemporaryDirectory() as pasta, \
             patch.object(suprimentos_snmp, "BASE_DIR", Path(pasta)), \
             patch.object(suprimentos_snmp, "carregar_offline", return_value=offline), \
             patch.object(suprimentos_snmp, "salvar_offline") as salvar_offline, \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=[[], ["Modelo SNMP"], [], [], []]), \
             patch.object(suprimentos_snmp, "registrar_evento") as registrar_evento, \
             patch.object(suprimentos_snmp, "registrar_nivel_toner") as registrar_nivel:
            impressoras = await suprimentos_snmp.main()
        self.assertEqual(impressoras[0]["status"], "Online")
        self.assertEqual(impressoras[0]["preto"], "-")
        salvar_offline.assert_called_once_with({})
        registrar_evento.assert_called_once()
        self.assertEqual(registrar_evento.call_args.args[:2], ("10.0.0.1", "ONLINE"))
        registrar_nivel.assert_not_called()

    async def test_coleta_registra_offline_quando_nao_ha_resposta_snmp(self):
        cadastro = [{
            "ip": "10.0.0.1", "excluida": False, "descricao": "Escola",
            "patrimonio": "123", "setor": "SEMED", "modelo": "Modelo",
        }]
        with tempfile.TemporaryDirectory() as pasta, \
             patch.object(suprimentos_snmp, "BASE_DIR", Path(pasta)), \
             patch.object(suprimentos_snmp, "carregar_offline", return_value={}), \
             patch.object(suprimentos_snmp, "salvar_offline") as salvar_offline, \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=[[], []]), \
             patch.object(suprimentos_snmp, "registrar_nivel_toner") as registrar_nivel:
            impressoras = await suprimentos_snmp.main()
        self.assertEqual(impressoras[0]["status"], "Offline")
        self.assertIn("10.0.0.1", salvar_offline.call_args.args[0])
        registrar_nivel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
