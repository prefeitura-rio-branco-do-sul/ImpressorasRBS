from datetime import datetime


TONERS_SEM_CHIP = {
    "10.52.0.6": {"patrimonio": "W643302410", "cores": ("Preto",)},
    "10.6.0.1": {
        "patrimonio": "V7B8Z02969",
        "cores": ("Preto", "Ciano", "Magenta", "Amarelo"),
    },
}


def criar_tabela_trocas_sem_chip(conexao):
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS trocas_toner_sem_chip (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            patrimonio TEXT NOT NULL,
            cor TEXT NOT NULL,
            toner_id INTEGER NOT NULL,
            contador_inicial INTEGER NOT NULL,
            oid TEXT NOT NULL,
            iniciado_em TEXT NOT NULL,
            contador_final INTEGER,
            encerrado_em TEXT,
            FOREIGN KEY (toner_id) REFERENCES toners(id)
        )
    """)
    conexao.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS troca_sem_chip_aberta
        ON trocas_toner_sem_chip (ip, cor) WHERE encerrado_em IS NULL
    """)


def registrar_troca_sem_chip(cursor, ip, patrimonio, toner_id, cor, contador, oid):
    configuracao = TONERS_SEM_CHIP.get(ip)
    if not configuracao or patrimonio != configuracao["patrimonio"] or cor not in configuracao["cores"]:
        raise ValueError("Impressora, patrimônio ou cor não correspondem à configuração de toner sem chip.")
    if not isinstance(contador, int) or contador < 0 or not oid:
        raise ValueError("Contador de páginas inválido; a troca não foi registrada.")

    anterior = cursor.execute("""
        SELECT id, patrimonio, contador_inicial, oid
        FROM trocas_toner_sem_chip
        WHERE ip = ? AND cor = ? AND encerrado_em IS NULL
    """, (ip, cor)).fetchone()
    agora = datetime.now().isoformat(timespec="seconds")
    aviso = None
    if anterior:
        id_anterior, patrimonio_anterior, inicio, oid_anterior = anterior
        if patrimonio_anterior == patrimonio and oid_anterior == oid and contador == inicio:
            raise ValueError("O contador não mudou desde a última troca. Confira se ela já foi registrada.")
        valido = patrimonio_anterior == patrimonio and oid_anterior == oid and contador > inicio
        cursor.execute("""
            UPDATE trocas_toner_sem_chip
            SET contador_final = ?, encerrado_em = ?
            WHERE id = ?
        """, (contador if valido else None, agora, id_anterior))
        if not valido:
            aviso = "O ciclo anterior não foi usado na média: contador sem avanço, reduzido ou incompatível."
    cursor.execute("""
        INSERT INTO trocas_toner_sem_chip
        (ip, patrimonio, cor, toner_id, contador_inicial, oid, iniciado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (ip, patrimonio, cor, toner_id, contador, oid, agora))
    return aviso


def estimar_niveis_sem_chip(cursor, ip, patrimonio, contador, oid):
    configuracao = TONERS_SEM_CHIP.get(ip)
    if not configuracao:
        return {}
    niveis = {}
    for cor in configuracao["cores"]:
        if patrimonio != configuracao["patrimonio"]:
            niveis[cor] = {"nivel": None, "media_paginas": None, "paginas": None}
            continue
        atual = cursor.execute("""
            SELECT toner_id, contador_inicial, oid
            FROM trocas_toner_sem_chip
            WHERE ip = ? AND patrimonio = ? AND cor = ? AND encerrado_em IS NULL
        """, (ip, patrimonio, cor)).fetchone()
        if not atual:
            niveis[cor] = {"nivel": None, "media_paginas": None, "paginas": None}
            continue
        toner_id, inicio, oid_inicial = atual
        media = cursor.execute("""
            SELECT AVG(contador_final - contador_inicial)
            FROM trocas_toner_sem_chip
            WHERE ip = ? AND patrimonio = ? AND cor = ? AND toner_id = ?
              AND oid = ? AND contador_final > contador_inicial
        """, (ip, patrimonio, cor, toner_id, oid_inicial)).fetchone()[0]
        paginas = contador - inicio if contador is not None and oid == oid_inicial and contador >= inicio else None
        nivel = None if media is None or paginas is None else max(0, min(100, round(100 * (1 - paginas / media))))
        niveis[cor] = {"nivel": nivel, "media_paginas": round(media) if media is not None else None, "paginas": paginas}
    return niveis
