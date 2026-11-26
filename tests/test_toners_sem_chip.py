import asyncio
import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import app
import estoque
import suprimentos_snmp
from toners_sem_chip import criar_tabela_trocas_sem_chip, estimar_niveis_sem_chip


IP = "10.6.0.1"
PATRIMONIO = "V7B8Z02969"
MODELO = "Kyocera TASKalfa 306ci"


class TonersSemChipTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        anterior = estoque.BANCO
        estoque.BANCO = os.path.join(self.pasta.name, "estoque.db")
        self.addCleanup(setattr, estoque, "BANCO", anterior)
        estoque.criar_banco()
        with closing(estoque.conectar()) as conexao, conexao:
            criar_tabela_trocas_sem_chip(conexao)
            conexao.execute(
                "INSERT INTO toners (marca, codigo, cor, modelos_compativeis, estoque) VALUES (?, ?, ?, ?, ?)",
                ("Kyocera", "TK", "Preto", MODELO, 10),
            )
        self.toner_id = 1

    def trocar(self, contador, oid="1.2.3", toner_id=1):
        return estoque.registrar_saida_toner(
            toner_id, 1, IP, PATRIMONIO, "Teste", "",
            troca_sem_chip={"contador": contador, "oid": oid, "modelo": MODELO},
        )

    def estimar(self, contador, oid="1.2.3", cor="Preto"):
        with closing(estoque.conectar()) as conexao:
            return estimar_niveis_sem_chip(conexao.cursor(), IP, PATRIMONIO, contador, oid)[cor]

    def test_estimativa_usa_media_dos_ciclos_concluidos_da_mesma_cor(self):
        self.trocar(100)
        self.assertIsNone(self.estimar(150)["nivel"])
        self.assertEqual(self.estimar(150)["paginas"], 50)
        self.trocar(200)
        self.assertEqual(self.estimar(225)["nivel"], 75)
        self.trocar(400)
        resultado = self.estimar(475)
        self.assertEqual(resultado["media_paginas"], 150)
        self.assertEqual(resultado["nivel"], 50)
        self.assertIsNone(self.estimar(475, cor="Ciano")["nivel"])

    def test_contador_ausente_reduzido_ou_oid_diferente_nao_gera_estimativa(self):
        self.trocar(100)
        self.trocar(200)
        for contador, oid in [(None, None), (199, "1.2.3"), (250, "1.2.4")]:
            self.assertIsNone(self.estimar(contador, oid)["nivel"])
        self.assertEqual(self.estimar(500)["nivel"], 0)

    def test_media_nao_e_transferida_para_outro_toner(self):
        self.trocar(100)
        self.trocar(200)
        with closing(estoque.conectar()) as conexao, conexao:
            conexao.execute(
                "INSERT INTO toners (marca, codigo, cor, modelos_compativeis, estoque) VALUES (?, ?, ?, ?, ?)",
                ("Outra", "TK2", "Preto", MODELO, 5),
            )
        self.trocar(300, toner_id=2)
        self.assertIsNone(self.estimar(350)["nivel"])

    def test_troca_repetida_ou_toner_incompativel_nao_altera_estoque(self):
        self.trocar(100)
        with self.assertRaisesRegex(ValueError, "não mudou"):
            self.trocar(100)
        with closing(estoque.conectar()) as conexao, conexao:
            conexao.execute("UPDATE toners SET modelos_compativeis = 'Outro M2040' WHERE id = 1")
        with self.assertRaisesRegex(ValueError, "compatível"):
            self.trocar(200)
        with closing(estoque.conectar()) as conexao:
            self.assertEqual(conexao.execute("SELECT estoque FROM toners WHERE id = 1").fetchone()[0], 9)
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM trocas_toner_sem_chip").fetchone()[0], 1)

    def test_contador_reiniciado_descarta_ciclo_e_avisa(self):
        self.trocar(100)
        _, aviso = self.trocar(50)
        self.assertIn("não foi usado", aviso)
        self.assertIsNone(self.estimar(60)["nivel"])
        with closing(estoque.conectar()) as conexao:
            self.assertIsNone(conexao.execute(
                "SELECT contador_final FROM trocas_toner_sem_chip ORDER BY id LIMIT 1"
            ).fetchone()[0])

    def test_saida_e_troca_sao_atomicas_se_saida_falhar(self):
        with patch.object(estoque, "_registrar_saida_no_cursor", side_effect=ValueError("erro")):
            with self.assertRaisesRegex(ValueError, "erro"):
                self.trocar(100)
        with closing(estoque.conectar()) as conexao:
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM trocas_toner_sem_chip").fetchone()[0], 0)
            self.assertEqual(conexao.execute("SELECT estoque FROM toners").fetchone()[0], 10)

    def test_rota_registra_troca_e_rejeita_falha_do_contador_sem_baixa(self):
        usuario = {"id": 123, "nome": "Teste", "usuario": "teste",
                   "administrador": True, "permissoes": [], "ativo": True}
        cadastro = [{"ip": IP, "nome": "Teste", "excluida": False,
                     "patrimonio_planilha": PATRIMONIO, "modelo_cadastro": MODELO}]
        cliente = app.app.test_client()
        corpo = {"toner_id": 1, "quantidade": 1, "ip_impressora": IP,
                 "patrimonio": PATRIMONIO, "responsavel": "Teste", "troca_sem_chip": True}
        with cliente.session_transaction() as sessao:
            from time import time
            sessao["presenca_atualizada_em"] = time()
        with patch.object(app, "_obter_usuario_atual", return_value=usuario), \
             patch.object(app, "carregar_lista_impressoras", return_value=cadastro), \
             patch.object(app, "consultar_contador_paginas", new_callable=AsyncMock) as consulta:
            consulta.side_effect = RuntimeError("Sem resposta")
            resposta = cliente.post("/registrar-saida-toner", json=corpo)
            self.assertEqual(resposta.status_code, 400)
            consulta.side_effect = None
            consulta.return_value = {"contador": 100, "oid": "1.2.3"}
            resposta = cliente.post("/registrar-saida-toner", json=corpo)
            self.assertEqual(resposta.status_code, 200)
            self.assertEqual(resposta.json["novo_estoque"], 9)
        with closing(estoque.conectar()) as conexao:
            self.assertEqual(conexao.execute("SELECT COUNT(*) FROM trocas_toner_sem_chip").fetchone()[0], 1)

    def test_coleta_ignora_leitura_sem_chip_e_nao_faz_baixa_ou_envia_email(self):
        self.trocar(100)
        self.trocar(200)
        cadastro = [{"ip": IP, "excluida": False, "descricao": "Teste",
                     "patrimonio": PATRIMONIO, "setor": "", "modelo": MODELO}]
        with patch.object(suprimentos_snmp, "BASE_DIR", Path(self.pasta.name)), \
             patch.object(suprimentos_snmp, "carregar_offline", return_value={}), \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar_suprimentos_e_presenca", new_callable=AsyncMock, return_value=(["Black"], MODELO)), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=[["100"], ["5"]]), \
             patch.object(suprimentos_snmp, "consultar_contador_paginas", new_callable=AsyncMock, return_value={"contador": 250, "oid": "1.2.3"}), \
             patch.object(suprimentos_snmp, "registrar_nivel_toner") as registrar, \
             patch.object(suprimentos_snmp, "enviar_email_toner") as email:
            resultado = asyncio.run(suprimentos_snmp.main())
        self.assertEqual(resultado[0]["preto"], "50%")
        self.assertEqual(resultado[0]["niveis_estimados"]["Preto"]["media_paginas"], 100)
        registrar.assert_not_called()
        email.assert_not_called()

if __name__ == "__main__":
    unittest.main()
