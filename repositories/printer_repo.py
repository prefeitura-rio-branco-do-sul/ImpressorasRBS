"""Acesso ao banco de dados para o histórico de relatórios PRINTER."""
import json
from contextlib import closing
from datetime import datetime

from estoque import conectar

RESULTADO_SALVO = "salvo"
RESULTADO_JA_SALVO = "ja_salvo"
RESULTADO_CONFLITO = "conflito"
RESULTADO_ALTERADO = "alterado"


def salvar_relatorio(dados, nome, conteudo, digest, sha256_esperado):
    """Grava o relatório do setor/mês. Devolve (resultado, sha256_existente)."""
    with closing(conectar()) as conexao, conexao:
        conexao.execute("BEGIN IMMEDIATE")
        anterior = conexao.execute(
            "SELECT id, sha256 FROM historico_relatorios_printer WHERE setor = ? AND competencia = ?",
            (dados["setor"], dados["competencia"]),
        ).fetchone()
        if anterior and anterior[1] == digest:
            return RESULTADO_JA_SALVO, anterior[1]
        if anterior and sha256_esperado != anterior[1]:
            return RESULTADO_CONFLITO, anterior[1]
        if not anterior and sha256_esperado:
            return RESULTADO_ALTERADO, None
        valores = (
            dados["paginas"], json.dumps(dados["categorias"], ensure_ascii=False),
            dados["pagina_metro_linear"], nome, conteudo, digest,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        if anterior:
            conexao.execute("""
                UPDATE historico_relatorios_printer SET paginas=?, categorias=?,
                    pagina_metro_linear=?, nome_arquivo=?, arquivo_pdf=?, sha256=?, salvo_em=?
                WHERE id=?
            """, valores + (anterior[0],))
        else:
            conexao.execute("""
                INSERT INTO historico_relatorios_printer
                (paginas, categorias, pagina_metro_linear, nome_arquivo, arquivo_pdf,
                 sha256, salvo_em, setor, competencia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, valores + (dados["setor"], dados["competencia"]))
    return RESULTADO_SALVO, None


def listar_relatorios():
    with closing(conectar()) as conexao:
        linhas = conexao.execute("""
            SELECT id, setor, competencia, paginas, categorias, pagina_metro_linear,
                   nome_arquivo, salvo_em
            FROM historico_relatorios_printer ORDER BY competencia DESC, setor
        """).fetchall()
    return [
        {"id": linha[0], "setor": linha[1], "competencia": linha[2],
         "paginas": linha[3], "categorias": json.loads(linha[4]),
         "pagina_metro_linear": linha[5], "nome_arquivo": linha[6], "salvo_em": linha[7]}
        for linha in linhas
    ]


def buscar_pdf(relatorio_id):
    """Devolve (nome_arquivo, arquivo_pdf) ou None."""
    with closing(conectar()) as conexao:
        return conexao.execute(
            "SELECT nome_arquivo, arquivo_pdf FROM historico_relatorios_printer WHERE id = ?",
            (relatorio_id,),
        ).fetchone()
