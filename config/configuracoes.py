"""Valores fixos do sistema. Segredos (senhas, chaves) continuam no arquivo .env."""
# Servidor web
SERVIDOR_HOST = 
SERVIDOR_PORTA = 
HOSTS_LOCAIS = 
HOSTS_LOCAIS_URL = 
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
SMTP_HOST = 
SMTP_PORTA = 
SMTP_TIMEOUT_ESTOQUE = 

# SNMP
SNMP_PORTA = 161
SNMP_COMMUNITY_PADRAO = "public"
OID_DESCRICAO_SISTEMA =
OID_CONTADOR_PAGINAS = 
OID_SUPRIMENTOS_DESCRICAO = 
OID_SUPRIMENTOS_CAPACIDADE = 
OID_SUPRIMENTOS_NIVEL =

# Consulta web de contadores de cor (Kyocera)
KYOCERA_ESQUEMA_URL = "https"
