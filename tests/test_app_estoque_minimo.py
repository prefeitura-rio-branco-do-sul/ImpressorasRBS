import unittest
from unittest.mock import patch

import app as monitor_app


class EstoqueMinimoTests(unittest.TestCase):
    def setUp(self):
        self.patch_senha_painel = patch.object(
            monitor_app,
            "_obter_usuario_atual",
            return_value={
                "id": 999999,
                "nome": "Teste",
                "usuario": "teste",
                "senha_hash": "",
                "permissoes": [],
                "administrador": True,
                "ativo": True,
                "ultimo_acesso": None,
            },
        )
        self.patch_senha_painel.start()
        self.cliente = monitor_app.app.test_client()

    def tearDown(self):
        self.patch_senha_painel.stop()

    @patch.object(monitor_app, "atualizar_estoque_minimo")
    def test_atualiza_estoque_minimo_sem_alterar_quantidade(self, atualizar):
        resposta = self.cliente.put(
            "/toner/12/estoque-minimo",
            json={"estoque_minimo": 4},
        )

        self.assertEqual(resposta.status_code, 200)
        atualizar.assert_called_once_with(12, 4)

    @patch.object(monitor_app, "atualizar_estoque_minimo")
    def test_rejeita_valor_minimo_invalido(self, atualizar):
        for valor in (-1, 1.5, True, "2", None):
            with self.subTest(valor=valor):
                resposta = self.cliente.put(
                    "/toner/12/estoque-minimo",
                    json={"estoque_minimo": valor},
                )
                self.assertEqual(resposta.status_code, 400)

        atualizar.assert_not_called()

    @patch.object(
        monitor_app,
        "atualizar_estoque_minimo",
        side_effect=ValueError("Toner não encontrado."),
    )
    def test_toner_inexistente_retorna_nao_encontrado(self, atualizar):
        resposta = self.cliente.put(
            "/toner/999/estoque-minimo",
            json={"estoque_minimo": 2},
        )

        self.assertEqual(resposta.status_code, 404)

    @patch.object(monitor_app, "listar_toners")
    @patch.object(monitor_app, "carregar_lista_impressoras")
    def test_conta_impressoras_compativeis_por_modelo_sem_duplicar_ip(
        self, carregar, listar
    ):
        carregar.return_value = [
            {"ip": "10.0.0.1", "nome": "Kyocera M2040dn", "modelo_cadastro": "M2040dn", "excluida": False},
            {"ip": "10.0.0.1", "nome": "Kyocera M2040dn", "modelo_cadastro": "M2040dn", "excluida": False},
            {"ip": "10.0.0.2", "nome": "Kyocera M2040", "modelo_cadastro": "M2040", "excluida": False},
            {"ip": "10.0.0.3", "nome": "Outro", "modelo_cadastro": "M3655", "excluida": False},
            {"ip": "10.0.0.4", "nome": "Não identificado", "modelo_cadastro": "", "excluida": False},
            {"ip": "10.0.0.5", "nome": "Canon TM-300", "modelo_cadastro": "TM-300", "excluida": False},
        ]
        for item in carregar.return_value:
            item["grupo"] = "Teste"
            item["patrimonio_planilha"] = "PAT-" + item["ip"]
        listar.return_value = [
            {"id": 1, "modelos_compativeis": "M2040dn"},
            {"id": 2, "modelos_compativeis": "M2040, M3655"},
            {"id": 3, "modelos_compativeis": "M9999"},
            {"id": 4, "modelos_compativeis": ""},
            {"id": 5, "modelos_compativeis": "Canon TM-200, Canon TM-300"},
        ]
        resposta = self.cliente.get("/api/toners/compatibilidade")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["contagens"], {"1": 2, "2": 3, "3": 0, "4": None, "5": 1})
        self.assertEqual(resposta.json["modelos_nao_identificados"], 1)
        listas = resposta.json["impressoras_por_toner"]
        self.assertEqual([item["ip"] for item in listas["1"]], ["10.0.0.1", "10.0.0.2"])
        self.assertEqual(listas["1"][0]["patrimonio"], "PAT-10.0.0.1")
        self.assertEqual(listas["3"], [])
        self.assertNotIn("4", listas)
        self.assertEqual(listas["5"][0]["modelo"], "TM-300")
        carregar.assert_called_once_with(exigir_arquivo=True)
        listar.assert_called_once_with(incluir_inativos=True)

    @patch.object(monitor_app, "listar_toners", return_value=[
        {"id": 1, "modelos_compativeis": "M2040"},
    ])
    @patch.object(monitor_app, "carregar_lista_impressoras", return_value=[
        {"ip": "10.0.0.1", "nome": "Kyocera M2040", "modelo_cadastro": "M2040", "excluida": False},
    ])
    def test_usuario_sem_monitoramento_ve_contagem_mas_nao_detalhes(self, carregar, listar):
        usuario = {
            "id": 123, "nome": "Teste", "usuario": "teste",
            "permissoes": ["stock.view"], "administrador": False, "ativo": True,
        }
        with patch.object(monitor_app, "_obter_usuario_atual", return_value=usuario):
            resposta = self.cliente.get("/api/toners/compatibilidade")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.json["contagens"]["1"], 1)
        self.assertNotIn("impressoras_por_toner", resposta.json)

    @patch.object(monitor_app, "carregar_lista_impressoras", side_effect=FileNotFoundError)
    def test_erro_no_cadastro_nao_e_mostrado_como_zero(self, carregar):
        resposta = self.cliente.get("/api/toners/compatibilidade")
        self.assertEqual(resposta.status_code, 503)
        self.assertIn("erro", resposta.json)

    def test_contagem_exige_permissao_de_estoque(self):
        usuario = {
            "id": 123, "nome": "Teste", "usuario": "teste",
            "permissoes": ["monitor.view"], "administrador": False, "ativo": True,
        }
        with patch.object(monitor_app, "_obter_usuario_atual", return_value=usuario):
            resposta = self.cliente.get("/api/toners/compatibilidade")
        self.assertEqual(resposta.status_code, 403)


if __name__ == "__main__":
    unittest.main()
