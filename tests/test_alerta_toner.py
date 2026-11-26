import asyncio
import json
import smtplib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import suprimentos_snmp


class AlertaTonerTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.addCleanup(self.pasta.cleanup)
        patch_dir = patch.object(suprimentos_snmp, "BASE_DIR", Path(self.pasta.name))
        patch_dir.start()
        self.addCleanup(patch_dir.stop)
        patch_alertas = patch.object(suprimentos_snmp, "toners_alertados", set())
        patch_alertas.start()
        self.addCleanup(patch_alertas.stop)
        patch_logger = patch.object(suprimentos_snmp, "logger")
        patch_logger.start()
        self.addCleanup(patch_logger.stop)

    def atualizar(self, nivel, cor="Preto", nao_confiaveis=frozenset()):
        suprimentos_snmp.atualizar_alerta_toner(
            "10.0.0.1", "Impressora teste", cor, nivel, "teste@example.invalid", nao_confiaveis,
        )

    @patch.object(suprimentos_snmp, "enviar_email_toner", return_value=True)
    def test_um_envio_por_ciclo_de_5_por_cento_ou_menos(self, enviar):
        for nivel in (7, 6, 5, 4, 0, 5):
            self.atualizar(nivel)
        enviar.assert_called_once_with("teste@example.invalid", "Impressora teste", "Preto", "5%")
        self.assertEqual(suprimentos_snmp.carregar_alertas_enviados(), {"10.0.0.1-Preto"})
        self.atualizar(6)
        self.assertEqual(suprimentos_snmp.carregar_alertas_enviados(), set())
        self.atualizar(4)
        self.assertEqual(enviar.call_count, 2)

    @patch.object(suprimentos_snmp, "enviar_email_toner", side_effect=[False, True])
    def test_falha_nao_marca_como_enviado_e_permite_nova_tentativa(self, enviar):
        self.atualizar(5)
        self.assertNotIn("10.0.0.1-Preto", suprimentos_snmp.toners_alertados)
        self.atualizar(5)
        self.atualizar(5)
        self.assertEqual(enviar.call_count, 2)
        self.assertIn("10.0.0.1-Preto", suprimentos_snmp.toners_alertados)

    @patch.object(suprimentos_snmp, "enviar_email_toner", return_value=True)
    def test_alertas_existentes_nao_se_repetem_e_cores_sao_independentes(self, enviar):
        suprimentos_snmp.toners_alertados.add("10.0.0.1-Preto")
        self.atualizar(5)
        self.atualizar(5, "Ciano")
        self.atualizar(5, "Amarelo", {("10.0.0.1", "Amarelo")})
        enviar.assert_called_once_with("teste@example.invalid", "Impressora teste", "Ciano", "5%")

    @patch.dict("os.environ", {"GMAIL_REMETENTE": "remetente@example.invalid", "GMAIL_SENHA_APP": "teste"})
    @patch.object(suprimentos_snmp.smtplib, "SMTP")
    def test_envio_informa_limite_e_trata_falha_smtp(self, smtp):
        servidor = smtp.return_value.__enter__.return_value
        self.assertTrue(suprimentos_snmp.enviar_email_toner(
            "teste@example.invalid", "Impressora teste", "Preto", "5%"
        ))
        mensagem = servidor.send_message.call_args.args[0]
        self.assertIn("5% ou menos", mensagem.get_content())
        servidor.send_message.side_effect = smtplib.SMTPException("erro de teste")
        self.assertFalse(suprimentos_snmp.enviar_email_toner(
            "teste@example.invalid", "Impressora teste", "Preto", "5%"
        ))

    def test_arquivo_de_alertas_invalido_nao_e_tratado_como_vazio(self):
        (Path(self.pasta.name) / "alertas_enviados.json").write_text("{", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            suprimentos_snmp.carregar_alertas_enviados()
        (Path(self.pasta.name) / "alertas_enviados.json").write_text('"invalido"', encoding="utf-8")
        with self.assertRaises(ValueError):
            suprimentos_snmp.carregar_alertas_enviados()

    def test_coleta_dispara_no_limite_e_nao_repete(self):
        cadastro = [{"ip": "10.0.0.1", "excluida": False, "descricao": "Teste",
                     "patrimonio": "123", "setor": "", "modelo": "M2040"}]
        with patch.object(suprimentos_snmp, "carregar_offline", return_value={}), \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar_suprimentos_e_presenca", new_callable=AsyncMock, return_value=(["Black"], "Modelo")), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=[["100"], ["6"], ["100"], ["5"], ["100"], ["4"]]), \
             patch.object(suprimentos_snmp, "registrar_nivel_toner", return_value=None), \
             patch.object(suprimentos_snmp, "registrar_toner_6"), \
             patch.object(suprimentos_snmp, "limpar_historico_toner_6"), \
             patch.object(suprimentos_snmp, "enviar_email_toner", return_value=True) as enviar:
            asyncio.run(suprimentos_snmp.main())
            enviar.assert_not_called()
            asyncio.run(suprimentos_snmp.main())
            asyncio.run(suprimentos_snmp.main())
        self.assertEqual(enviar.call_count, 1)

    def test_coleta_usa_destinatarios_fixos_por_setor(self):
        cadastro = [
            {"ip": "10.0.0.1", "excluida": False, "descricao": "Escola",
             "patrimonio": "1", "setor": "SEMED", "modelo": "M2040"},
            {"ip": "10.0.0.2", "excluida": False, "descricao": "Outro setor",
             "patrimonio": "2", "setor": "SAUDE", "modelo": "M2040"},
            {"ip": "10.0.0.3", "excluida": False, "descricao": "SEMED - Escola",
             "patrimonio": "3", "setor": "", "modelo": "M2040"},
        ]
        with patch.object(suprimentos_snmp, "EMAIL_SEMED", "semed@example.invalid"), \
             patch.object(suprimentos_snmp, "EMAIL_OUTROS", "outros@example.invalid"), \
             patch.object(suprimentos_snmp, "carregar_offline", return_value={}), \
             patch.object(suprimentos_snmp, "verificar_toners_nao_confiaveis", return_value=set()), \
             patch.object(suprimentos_snmp, "carregar_planilha", return_value=cadastro), \
             patch.object(suprimentos_snmp, "consultar_suprimentos_e_presenca", new_callable=AsyncMock, return_value=(["Black"], "Modelo")), \
             patch.object(suprimentos_snmp, "consultar", new_callable=AsyncMock, side_effect=lambda ip, oid: ["100"] if oid.endswith(".8") else ["5"]), \
             patch.object(suprimentos_snmp, "registrar_nivel_toner", return_value=None), \
             patch.object(suprimentos_snmp, "limpar_historico_toner_6"), \
             patch.object(suprimentos_snmp, "enviar_email_toner", return_value=True) as enviar:
            resultado = asyncio.run(suprimentos_snmp.main())
        emails = {item["ip"]: item["email"] for item in resultado}
        self.assertEqual(emails, {
            "10.0.0.1": "semed@example.invalid",
            "10.0.0.2": "outros@example.invalid",
            "10.0.0.3": "semed@example.invalid",
        })
        self.assertEqual(
            sorted(chamada.args[0] for chamada in enviar.call_args_list),
            ["outros@example.invalid", "semed@example.invalid", "semed@example.invalid"],
        )


if __name__ == "__main__":
    unittest.main()
