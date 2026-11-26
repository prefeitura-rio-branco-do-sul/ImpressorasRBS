"""Valores fixos do sistema. Segredos (senhas, chaves) continuam no arquivo .env."""
# Servidor web
SERVIDOR_HOST = "0.0.0.0"
SERVIDOR_PORTA = 5000
HOSTS_LOCAIS = {"127.0.0.1", "::1"}
HOSTS_LOCAIS_URL = {"localhost", "127.0.0.1", "::1"}

# Nomes de arquivos (relativos à pasta do projeto)
NOME_BANCO = "estoque.db"
NOME_LOG = "monitor.log"
NOME_OFFLINE = "impressoras_offline.json"
NOME_HISTORICO = "historico.json"
NOME_TONER_6 = "historico_toner_6.json"
NOME_ALERTAS_ENVIADOS = "alertas_enviados.json"
NOME_IMPRESSORAS_ENCONTRADAS = "impressoras_encontradas.json"
NOME_LOCAIS_EQUIVALENTES = ".relatorio_locais_equivalentes.json"
NOME_PLANILHA_ORIGINAL = "ImpressorasRBS.xlsx"
NOME_PLANILHA_ATUALIZADA = "ImpressorasRBS_atualizada.xlsx"
NOME_PLANILHA_CONSOLIDADA = "ImpressorasRBS_consolidada.xlsx"
NOME_CSV_LIMPO = "Impressoras_Limpo.csv"
NOME_DOWNLOAD_CONSOLIDADO = "Impressoras_Consolidadas.xlsx"

# E-mail (SMTP)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORTA = 587
SMTP_TIMEOUT_ESTOQUE = 30

# SNMP
SNMP_PORTA = 161
SNMP_COMMUNITY_PADRAO = "public"
OID_DESCRICAO_SISTEMA = "1.3.6.1.2.1.1.1"
OID_CONTADOR_PAGINAS = "1.3.6.1.2.1.43.10.2.1.4"
OID_SUPRIMENTOS_DESCRICAO = "1.3.6.1.2.1.43.11.1.1.6"
OID_SUPRIMENTOS_CAPACIDADE = "1.3.6.1.2.1.43.11.1.1.8"
OID_SUPRIMENTOS_NIVEL = "1.3.6.1.2.1.43.11.1.1.9"

# Consulta web de contadores de cor (Kyocera)
KYOCERA_ESQUEMA_URL = "https"
