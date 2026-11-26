"""Criação das tabelas usadas pela aplicação na inicialização."""
from contextlib import closing

from estoque import conectar, criar_banco
from pedidos_estoque import criar_tabelas_pedidos
from relatorio_impressoes import criar_tabelas_contadores
from toners_sem_chip import criar_tabela_trocas_sem_chip


def inicializar_tabelas(criar_tabela_historico_printer):
    criar_banco()
    with closing(conectar()) as conexao, conexao:
        criar_tabelas_pedidos(conexao)
        criar_tabelas_contadores(conexao)
        criar_tabela_trocas_sem_chip(conexao)
        criar_tabela_historico_printer(conexao)
