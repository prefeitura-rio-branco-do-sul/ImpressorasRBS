# Mapeamento técnico da aplicação

**Levantamento:** 25/11/2026  
**Escopo:** arquivos presentes no diretório do projeto, estrutura observável do código, símbolos declarados, rotas, interface, dependências e dados locais. O arquivo `RELATORIO_APLICACAO.md` foi mantido sem alteração.

> O inventário abaixo distingue código-fonte de dados/artefatos locais. Arquivos `.env`, banco de dados, planilhas e logs podem conter informações operacionais; seus conteúdos não são reproduzidos aqui. O catálogo de Python lista declarações de nível de módulo (incluindo classes e métodos); o catálogo JavaScript destaca os comportamentos nomeados da interface.

## 1. Visão geral e arquitetura

Aplicação web local para monitoramento e cadastro de impressoras, gestão de toner/estoque, relatórios de consumo e gestão de acessos. O servidor é Flask; a persistência principal é SQLite; os cadastros e relatórios também usam Excel/CSV e arquivos JSON. O monitoramento consulta dispositivos pela rede usando SNMP e, para determinados contadores Kyocera, uma consulta web.

```text
Navegador
  templates/*.html + static/js/*.js + static/css/style.css
       │ fetch / API JSON e formulários
       ▼
app.py (Flask: autenticação, autorização, rotas e coordenação)
  ├─ repositories/       acesso a dados e inicialização de tabelas
  ├─ estoque.py          regras e persistência de toner/estoque
  ├─ pedidos_estoque.py  ciclo de pedido e recebimento
  ├─ suprimentos_snmp.py consulta de impressoras e suprimentos
  ├─ relatorio_impressoes.py coleta e relatório mensal
  └─ monitor/reports/printer/service.py leitura/análise de PDF PRINTER
       │
       ├─ estoque.db (SQLite)
       ├─ planilhas Excel / CSV
       ├─ JSON e logs locais
       └─ impressoras na rede (SNMP / HTTP(S))
```

`monitor/` contém pacotes e diretórios preparados para separação por domínio; a implementação funcional de relatório PRINTER está em `monitor/reports/printer/service.py`. Vários `__init__.py` e os diretórios `monitor/auth`, `monitor/infrastructure`, `monitor/printers`, `monitor/reports/usage`, `monitor/shared` e `monitor/stock` não declaram funcionalidades próprias no momento.

## 2. Inventário de arquivos

### Código Python da aplicação

- Raiz: `app.py`, `estoque.py`, `pedidos_estoque.py`, `email_estoque.py`, `suprimentos_snmp.py`, `relatorio_impressoes.py`, `relatorio_printer.py`, `contadores_cor_kyocera.py`, `toners_sem_chip.py`.
- Configuração: `config/__init__.py`, `config/configuracoes.py`.
- Repositórios: `repositories/__init__.py`, `repositories/banco_repo.py`, `repositories/comum.py`, `repositories/historico_repo.py`, `repositories/painel_repo.py`, `repositories/printer_repo.py`, `repositories/usuario_repo.py`.
- Domínio `monitor`: `monitor/__init__.py`, `monitor/auth/__init__.py`, `monitor/infrastructure/__init__.py`, `monitor/printers/__init__.py`, `monitor/reports/__init__.py`, `monitor/reports/printer/__init__.py`, `monitor/reports/printer/service.py`, `monitor/reports/usage/__init__.py`, `monitor/shared/__init__.py`, `monitor/stock/__init__.py`.
- Utilitários: `utils/__init__.py`, `utils/datas.py`, `utils/rede.py`, `utils/seguranca.py`, `utils/texto.py`.
- Scripts operacionais: `scripts/monitor_impressoras.py`, `scripts/teste_email.py`, `scripts/teste_kyocera.py`, `scripts/teste_snmp.py`.

### Interface, testes e documentação

- Templates: `templates/index.html`, `templates/_grafico_printer.html`, `templates/login.html`, `templates/recuperar_senha_admin.html`, `templates/aceitar_convite.html`, `templates/usuarios.html`.
- Front-end: `static/js/api.js`, `static/js/menu-state.js`, `static/js/script.js`, `static/css/style.css`, `static/BRASAO_CURVAS-01.png`.
- Testes: `tests/helpers_repositorios.py`, `tests/test_ajuste_estoque.js`, `tests/test_alerta_toner.py`, `tests/test_app_acesso_remoto.py`, `tests/test_app_cadastro_consolidado.py`, `tests/test_app_edicao_impressoras.py`, `tests/test_app_estoque_minimo.py`, `tests/test_app_grupos_impressoras.py`, `tests/test_app_historico.py`, `tests/test_app_historico_printer.py`, `tests/test_app_relatorio_correcoes.py`, `tests/test_baixa_automatica.py`, `tests/test_email_estoque.py`, `tests/test_ficha_impressora.py`, `tests/test_grafico_printer.js`, `tests/test_painel_html.py`, `tests/test_pedidos_estoque.py`, `tests/test_relatorio_impressoes.py`, `tests/test_relatorio_printer.py`, `tests/test_toners_sem_chip.py`.
- Dependências: `requirements.txt`.
- Relatórios existentes: `RELATORIO_APLICACAO.md` (pré-existente) e este novo arquivo.

### Dados e artefatos locais observados

- Configuração local: `.env` (segredos/configuração privada; conteúdo intencionalmente omitido), `.relatorio_locais_equivalentes.json`.
- Banco e registros: `estoque.db`, `monitor.log`, `historico.json`, `historico_toner_6.json`, `alertas_enviados.json`, `impressoras_encontradas.json`, `impressoras_offline.json`.
- Cadastro: `ImpressorasRBS.xlsx`, `ImpressorasRBS_atualizada.xlsx`, `ImpressorasRBS_consolidada.xlsx`, `Impressoras_Limpo.csv`.
- Arquivos temporários do Excel observados: `~$Apresentacao_Monitor_de_Impressoras.pptx`, `~$ImpressorasRBS.xlsx`, `~$ImpressorasRBS_consolidada.xlsx`.
- Metadados locais de desenvolvimento: `.vscode/launch.json`, `.vscode/settings.json`, `.vscode/tasks.json`; cache `.pytest_cache/` e bytecode `__pycache__/` (gerados, não código-fonte).

## 3. Módulos e funções Python

Lista de declarações no nível de módulo. Métodos de classes aparecem como `Classe.método`.

### Aplicação e endpoints — `app.py`

**Acesso e contas:** `_garantir_tabela_configuracao_painel`, `_garantir_tabelas_usuarios_painel`, `_obter_usuario_por_id`, `_obter_usuario_atual`, `_usuario_tem_permissao`, `_normalizar_permissoes`, `_token_csrf`, `_validar_csrf`, `_cliente_rede_autorizada`, `exigir_autenticacao_painel`, `login_painel`, `recuperar_senha_admin`, `aceitar_convite`, `sair_painel`, `_url_convite_publica`, `admin_usuarios`, `criar_convite_painel`, `presenca_usuarios_painel`, `alterar_status_usuario_painel`, `alterar_permissoes_usuario_painel`, `cancelar_convite_painel`.

**Cadastro e dados de impressoras:** `_arquivo_locais_equivalentes`, `_carregar_locais_equivalentes`, `_salvar_locais_equivalentes`, `_arquivo_lista_impressoras`, `_linha_cabecalho_cadastro`, `_colunas_cadastro`, `_salvar_cadastro_atualizado`, `_carregar_grupos_cadastro_original`, `carregar_lista_impressoras`, `carregar_inventario_relatorio`, `_chave_cadastro_consolidado`, `_carregar_cadastro_consolidado`, `baixar_cadastro_consolidado`, `_cadastros_por_ip`, `_cadastros_para_relatorio_impressoes`, `_dados_relatorio_impressoes`, `adicionar_grupos`, `_atualizar_cache_impressoras`, `_iniciar_atualizacao_impressoras`, `index`, `dados`, `_encontrar_linha_cadastro`, `_preparar_colunas_edicao`, `cadastrar_impressora`, `editar_impressora`, `excluir_impressora`.

**Relatórios, ficha e análise de impressão:** `relatorio_impressoes`, `exportar_relatorio_impressoes`, `salvar_historico_printer`, `listar_historico_printer`, `baixar_historico_printer`, `analisar_relatorio_printer`, `_resolver_substituicoes_relatorio`, `aprovar_equivalencia_relatorio_printer`, `aprovar_correcao_relatorio_printer`, `aprovar_inclusao_relatorio_printer`, `arquivo_relatorio_excede_limite`, `_cadastro_impressora_para_ficha`, `_toners_compativeis_para_ficha`, `toners_compativeis_impressora`, `contador_paginas_impressora`.

**Estoque e pedidos:** `listar_pedidos_estoque`, `adiar_sugestao_pedido_estoque`, `enviar_solicitacao_pedido_estoque`, `decidir_solicitacao_pedido_estoque`, `receber_pedido_estoque`, `cancelar_pendencias_pedido_estoque`, `estoque`, `compatibilidade_toners`, `cadastrar_toner_rota`, `ajustar_estoque_rota`, `remover_toner_rota`, `reativar_toner_rota`, `atualizar_modelos_compativeis_rota`, `atualizar_estoque_minimo_rota`, `historico`, `toners_nao_confiaveis`, `registrar_saida_toner_rota`.

### Domínio e infraestrutura

- `estoque.py` — `conectar`, `criar_banco`, `cadastrar_toner`, `listar_toners`, `remover_toner`, `reativar_toner`, `atualizar_modelos_compativeis`, `atualizar_estoque_minimo`, `buscar_toner`, `registrar_saida_toner`, `_registrar_saida_no_cursor`, `registrar_nivel_toner`, `_salvar_nivel_toner`, `ajustar_estoque_manual`, `registrar_evento_impressora`. Persistência, movimentos, compatibilidades, níveis e ajustes de estoque.
- `pedidos_estoque.py` — `criar_tabelas_pedidos`, `listar_sugestoes_e_pedidos`, `_validar_itens`, `adiar_sugestao_pedido`, `criar_solicitacao_pedido`, `marcar_solicitacao_enviada`, `cancelar_solicitacao_envio`, `decidir_solicitacao_pedido`, `cancelar_pendencias_pedido`, `receber_pedido`. Regras do ciclo de pedido e recebimento.
- `email_estoque.py` — `ErroEnvioEmailEstoque`, `gerar_sugestao_semanal`, `_inserir_itens_sugestao`, `_mensagem_solicitacao`, `enviar_email_solicitacao`, `_executar_agendador`, `iniciar_agendador_estoque`. Sugestões periódicas e envio SMTP.
- `suprimentos_snmp.py` — `obter_arquivo_planilha_impressoras`, `carregar_alertas_enviados`, `salvar_alertas_enviados`, `carregar_historico_toner_6`, `salvar_historico_toner_6`, `registrar_toner_6`, `limpar_historico_toner_6`, `verificar_toners_nao_confiaveis`, `enviar_email_toner`, `atualizar_alerta_toner`, `carregar_planilha`, `_qualidade_nome_cadastro`, `registrar_evento`, `carregar_offline`, `salvar_offline`, `consultar_contador_paginas` (async), `consultar` (async), `consultar_modelo` (async), `consultar_suprimentos_e_presenca` (async), `main` (async), `obter_impressoras` (async). Consulta e processamento de impressoras, contadores, suprimentos, alertas e estado online/offline.
- `relatorio_impressoes.py` — `criar_tabelas_contadores`, `identificar_cadastros`, `_reservar`, `_registrar_leitura`, `_consultar_pendentes` (async), `_consultar_cores_pendentes` (async), `_coletar_pendentes` (async), `verificar_coleta_mensal`, `_executar_agendador`, `iniciar_agendador_contadores`, `gerar_relatorio`. Coleta periódica e exportação mensal.
- `contadores_cor_kyocera.py` — `_SemRedirecionamento.redirect_request`, `modelo_compativel`, `interpretar_contadores`, `consultar_contadores_cor`. Interpretação/consulta de contadores de cor Kyocera.
- `toners_sem_chip.py` — `criar_tabela_trocas_sem_chip`, `registrar_troca_sem_chip`, `estimar_niveis_sem_chip`. Registro de troca e estimativa de nível para suprimentos sem leitura de chip.
- `monitor/reports/printer/service.py` — classes `RelatorioInvalido`, `RelatorioDependenciaAusente`; funções `criar_tabela_historico_printer`, `extrair_consumo_relatorio`, `extrair_equipamentos_relatorio`, `ler_relatorio_pdf`, `comparar_equipamentos`, `normalizar_local_equivalencia`, `locais_conferem`, `criar_email`, `_texto_substituicoes`, `_normalizar_identificador`, `_limpar_local_cadastro`, `_tokens_local`, `_tokens_semelhantes`, `_limpar_texto_pdf`, `_nome_relatorio`. Leitura de PDF, extração, comparação e geração de e-mail.
- `relatorio_printer.py` — fachada de compatibilidade `class _Fachada` e `__setattr__`; reexporta a implementação do pacote `monitor.reports.printer`.
- `repositories/banco_repo.py` — `inicializar_tabelas`; inicializa estruturas de banco chamando módulos de estoque, pedidos, contadores e trocas sem chip.
- `repositories/comum.py` — `agora`; utilitário de data/hora.
- `repositories/historico_repo.py` — `_consultar`, `listar_movimentacoes`, `listar_saidas_automaticas`, `listar_offline_hoje`; consultas de histórico.
- `repositories/painel_repo.py` — `garantir_tabela_configuracao`, `_criar_token`, `_consumir_token`, `criar_token_login`, `consumir_token_login`, `criar_token_recuperacao_admin`, `consumir_token_recuperacao_admin`; configuração e tokens de acesso.
- `repositories/printer_repo.py` — `salvar_relatorio`, `listar_relatorios`, `buscar_pdf`; relatórios PRINTER armazenados.
- `repositories/usuario_repo.py` — `garantir_tabelas_usuarios`, `obter_usuario_por_id`, `registrar_presenca`, `buscar_credenciais_login`, `redefinir_senha_admin`, `buscar_convite_valido`, `aceitar_convite`, `listar_usuarios_e_convites`, `criar_convite`, `listar_usuarios_online`, `alterar_status_usuario`, `alterar_permissoes_usuario`, `cancelar_convite`.
- `utils/datas.py` — `limites_mes`; limites de mês para relatórios.
- `utils/rede.py` — `ip_normalizado`; normalização de endereço IP.
- `utils/seguranca.py` — `token_hash`; hash de token.
- `utils/texto.py` — `normalizar_grupo`, `normalizar_numero_serie`, `modelo_do_nome`, `qualidade_nome_cadastro`, `registro_excluido`, `modelos_da_descricao`, `modelos_para_compatibilidade`, `extrair_modelo_planilha`; normalização e identificação de modelos/grupos.
- `scripts/monitor_impressoras.py` e `scripts/teste_email.py` — scripts de execução/diagnóstico sem funções nomeadas de nível de módulo.
- `scripts/teste_kyocera.py`, `scripts/teste_snmp.py` — função assíncrona `testar` em cada script.
- `config/configuracoes.py` — constantes de host/porta, nomes de arquivos, SMTP e OIDs/parâmetros SNMP; valores secretos são mantidos fora deste arquivo, em `.env`.

## 4. Rotas HTTP do Flask

As rotas foram associadas às funções decoradas no `app.py`. Foram identificadas 44 regras de rota.

| Área | Rotas |
|---|---|
| Sessão e usuários | `GET/POST /entrar`, `GET/POST /recuperar-admin`, `GET/POST /convite/<token>`, `POST /sair`, `GET /admin/usuarios`, `POST /admin/usuarios/convites`, `GET /admin/usuarios/presenca`, `POST /admin/usuarios/<usuario_id>/status`, `POST /admin/usuarios/<usuario_id>/permissoes`, `POST /admin/convites/<convite_id>/cancelar` |
| Painel e impressoras | `GET /`, `GET /dados`, `POST /api/impressoras`, `PUT /api/impressoras/editar`, `DELETE /api/impressoras/excluir`, `GET /api/impressoras/consolidado`, `GET /api/impressoras/<ip>/toners`, `GET /api/impressoras/<ip>/contador` |
| Relatório mensal | `GET /api/relatorio-impressoes`, `GET /api/relatorio-impressoes/excel` |
| Relatório PRINTER | `POST/GET /api/relatorio-printer/historico`, `GET /api/relatorio-printer/historico/<relatorio_id>/pdf`, `POST /api/relatorio-printer/analisar`, `POST /api/relatorio-printer/aprovar-equivalencia`, `POST /api/relatorio-printer/aprovar-correcao`, `POST /api/relatorio-printer/aprovar-inclusao` |
| Pedidos | `GET /api/pedidos-estoque`, `POST /api/pedidos-estoque`, `POST /api/pedidos-estoque/sugestoes/<semana>/adiar`, `POST /api/pedidos-estoque/<pedido_id>/decisao`, `POST /api/pedidos-estoque/<pedido_id>/receber`, `POST /api/pedidos-estoque/<pedido_id>/cancelar-pendentes` |
| Estoque e histórico | `GET /estoque`, `GET /api/toners/compatibilidade`, `POST /cadastrar-toner`, `POST /ajustar-estoque/<toner_id>`, `DELETE /remover-toner/<toner_id>`, `POST /reativar-toner/<toner_id>`, `PUT /toner/<toner_id>/modelos-compativeis`, `PUT /toner/<toner_id>/estoque-minimo`, `GET /historico`, `GET /toners-nao-confiaveis`, `POST /registrar-saida-toner` |

O acesso é protegido por `exigir_autenticacao_painel` e por verificações de permissões nas operações aplicáveis. A rota de sessão `/sair` usa POST. O código também implementa proteção CSRF e validações relacionadas à rede local.

## 5. Componentes da interface e JavaScript

- `templates/index.html` — tela principal: visão geral, estados online/offline, gráficos, filtro e busca, tabela e grupos de impressoras, estoque, compatibilidade, pedidos, histórico, relatórios mensal/PRINTER, ficha e edição de impressora, formulários de toner, ajuste e saída.
- `templates/_grafico_printer.html` — fragmento reutilizável de gráfico PRINTER e tabela acessível de dados.
- `templates/login.html` — formulário de autenticação.
- `templates/recuperar_senha_admin.html` — redefinição de senha administrativa.
- `templates/aceitar_convite.html` — criação de credenciais pelo convite.
- `templates/usuarios.html` — presença online, criação/cancelamento de convites, permissões e status de contas.
- `static/js/api.js` — módulo `api`: `fazerRequisicao`, `buscarDados`, `buscarTonersNaoConfiaveis`, operações de cadastro/edição/exclusão e ficha; ações do relatório PRINTER; relatório mensal; estoque/toner/histórico; pedidos; presença de usuários.
- `static/js/menu-state.js` — restaura estado recolhido do menu via `localStorage`.
- `static/js/script.js` — lógica do painel e eventos de interface abaixo. Funções auxiliares anônimas e callbacks locais também existem dentro de algumas rotinas.
- `static/css/style.css` — estilos próprios do painel e dos formulários. `index.html` também referencia Tailwind via CDN.

**Funções nomeadas de `script.js`, agrupadas por comportamento:**

- Permissões, tempo e impressoras: `painelPode`, `atualizarHorario`, `abrirEdicaoImpressora`, `abrirCadastroImpressora`, `fecharEdicaoImpressora`, `salvarEdicaoImpressora`, `excluirImpressoraPainel`, `obterNivelToner`, `impressoraComTonerBaixo`, `atualizarFiltroSetor`, `filtrarTabelaDashboard`, `definirFiltroStatus`, `resetarFiltrosTabela`, `abrirListaGrafico`, `abrirListaTonerBaixoPainel`, `atualizarDescricaoTonerBaixo`, `abrirStatusGrafico`, `atualizarGraficos`, `renderizarImpressoras`, `atualizarResumo`.
- Navegação: `atualizarEstadoBotaoMenu`, `atualizarDescricaoSecao`, `alternarSecaoMenu`, `esconderAreas`, `pesquisarImpressoras`, `abrirImpressoras`, `abrirPastas`, `voltarInicio`, `alternarMenu`, `focarPesquisa`.
- Relatório PRINTER: `abrirRelatorioPrinter`, `carregarHistoricoPrinter`, `mostrarGraficoHistoricoPrinter`, `mostrarComparacaoPrinter`, `salvarHistoricoPrinter`, `limparSubstituicoesRelatorio`, `analisarRelatorioPrinter`, `aprovarSubstituicaoRelatorio`, `aprovarCorrecaoRelatorio`, `aprovarInclusaoRelatorio`, `aprovarEquivalenciaLocal`, `copiarEmailPrinter`.
- Estado offline, estoque e toner: `carregar_offline`, `fecharOffline`, `mostrarTonerBaixo`, `atualizarResumoEstoque`, `mostrarEstoque`, `escaparHtml`, `filtrarEstoque`, `carregarCompatibilidadeToners`, `mostrarImpressorasCompativeis`, `carregarPedidosEstoque`, `enviarFormularioPedido`, `confirmarSugestaoEstoque`, `adiarSugestaoEstoque`, `decidirSolicitacaoEstoque`, `receberPedidoEstoque`, `cancelarPendenciasPedidoEstoque`, `definirTonersInativos`, `filtrarInativos`, `editarModelosCompativeis`, `editarEstoqueMinimo`, `reativarToner`, `mostrarTonersNaoConfiaveis`, `abrirCadastroToner`, `fecharCadastroToner`, `cadastrarToner`, `removerToner`, `abrirSaidaToner`, `fecharSaidaToner`, `salvarSaidaToner`, `buscarImpressoraSaida`, `atualizarEstoqueSaida`, `abrirAjusteEstoque`, `salvarAjusteEstoque`.
- Relatórios e ficha: `alterarMesRelatorioImpressoes`, `abrirRelatorioImpressoes`, `carregarRelatorioImpressoes`, `mostrarhistorico`, `formatarModeloImpressora`, `abrirFichaImpressora`, `abrirFichaImpressoraComTeclado`, `fecharFichaImpressora`.

## 6. Dependências

### Dependências Python declaradas em `requirements.txt`

| Pacote | Versão declarada | Uso observado |
|---|---|---|
| Flask | `3.1.0` | Servidor web, rotas, sessões e templates |
| openpyxl | `3.1.5` | Leitura/escrita de planilhas Excel |
| pypdf | `>=5.0,<7` | Leitura e extração de conteúdo de relatórios PDF |
| python-dotenv | `1.1.1` | Carregamento de variáveis de ambiente |
| pysnmp | `>=7.1.0,<8` | Consultas SNMP assíncronas às impressoras |

### Bibliotecas padrão e integrações

Entre os módulos padrão importados estão `asyncio`, `sqlite3`, `threading`, `datetime`, `json`, `csv`, `email`, `smtplib`, `urllib`, `ssl`, `ipaddress`, `openpyxl` (biblioteca externa) e utilitários de arquivos/processo. Integrações externas: servidor SMTP (configurado para Gmail), impressoras via SNMP e consulta HTTPS de contadores Kyocera. A interface carrega Tailwind por CDN.

### Dependências internas principais

- `app.py` coordena `config.configuracoes`, `repositories`, `estoque`, `pedidos_estoque`, `suprimentos_snmp`, `relatorio_impressoes`, `relatorio_printer`, `email_estoque`, `toners_sem_chip` e `utils`.
- `repositories/banco_repo.py` integra a inicialização do esquema de `estoque.py`, `pedidos_estoque.py`, `relatorio_impressoes.py` e `toners_sem_chip.py`.
- `estoque.py` usa configuração, normalização de texto e funções de `toners_sem_chip.py`.
- `pedidos_estoque.py` depende do domínio de estoque.
- `relatorio_impressoes.py` integra consultas SNMP, contadores Kyocera, estoque e utilitário de datas.
- `suprimentos_snmp.py` integra SNMP, estoque, histórico/alertas locais e e-mail.
- `relatorio_printer.py` preserva uma fachada compatível sobre `monitor.reports.printer.service`.
- O front-end centraliza chamadas HTTP em `static/js/api.js`; templates servem a interface Flask.

## 7. Testes e cobertura funcional observável

- Estoque e interface de ajuste: `tests/test_ajuste_estoque.js`, `tests/test_baixa_automatica.py`, `tests/test_app_estoque_minimo.py`.
- Acesso/usuários e painel: `tests/test_app_acesso_remoto.py`, `tests/test_painel_html.py`.
- Cadastro e organização de impressoras: `tests/test_app_cadastro_consolidado.py`, `tests/test_app_edicao_impressoras.py`, `tests/test_app_grupos_impressoras.py`, `tests/test_ficha_impressora.py`.
- Histórico e relatórios: `tests/test_app_historico.py`, `tests/test_app_historico_printer.py`, `tests/test_app_relatorio_correcoes.py`, `tests/test_grafico_printer.js`, `tests/test_relatorio_impressoes.py`, `tests/test_relatorio_printer.py`.
- Toner, alertas e pedidos: `tests/test_alerta_toner.py`, `tests/test_email_estoque.py`, `tests/test_pedidos_estoque.py`, `tests/test_toners_sem_chip.py`.
- `tests/helpers_repositorios.py` fornece apoio de teste para conexão/repositórios. Os testes usam `unittest`/`unittest.mock`; os testes de interface JS são scripts Node.

## 8. Observações e limites do levantamento

- Não há manifesto JavaScript (`package.json`) no inventário observado; os testes `.js` indicam uso de Node, mas a versão e os comandos de execução não estão declarados em manifesto.
- `.env`, banco, planilhas, logs e arquivos JSON foram listados apenas pelo nome; seus dados podem ser mutáveis, sensíveis ou dependentes do ambiente.
- `.pytest_cache`, `__pycache__` e arquivos temporários do Excel não são módulos da aplicação e não foram tratados como código.
- O inventário é uma fotografia do diretório no momento do levantamento; arquivos criados posteriormente não estão incluídos.

## 9. Dependências externas e uso encontrado no código

Nesta seção, “rota” significa o endpoint Flask que inicia o fluxo; chamadas a serviços SNMP ou SQLite podem ocorrer em segundo plano ou dentro da chamada HTTP. Os pacotes listados em `requirements.txt` são dependências diretas declaradas. `Werkzeug` é importado diretamente pelo código, mas não aparece separado no arquivo de requisitos (é dependência do Flask).

| Dependência | Classes, funções e variáveis usadas | Funções/rotas que a utilizam | Consultas ou dados associados |
|---|---|---|---|
| **Flask 3.1.0** | Classe `Flask`; instância global `app`; `request`, `session`, `jsonify`, `redirect`, `render_template`, `send_file`, `make_response`, `url_for`. `app.config["MAX_CONTENT_LENGTH"]` limita o upload a 10 MiB; `app.secret_key` usa `PAINEL_SESSION_SECRET` ou token aleatório; opções de cookie são configuradas no início de `app.py`. | As 44 rotas do `app.py` são registradas na instância `app`. Leitura de parâmetros/formulários é feita em handlers como `login_painel`, `cadastrar_impressora`, `analisar_relatorio_printer`, `estoque` e handlers de pedido; respostas JSON usam `jsonify`; páginas usam `render_template`; downloads usam `send_file`. O hook `exigir_autenticacao_painel` verifica sessão/permissão antes das rotas protegidas. | Flask não executa SQL por si só. Os handlers chamam `repositories/*`, `estoque.py`, `pedidos_estoque.py` e módulos de relatório, detalhados na seção 11. |
| **openpyxl 3.1.5** | `openpyxl.load_workbook`, `openpyxl.Workbook`, `openpyxl.utils.get_column_letter`, `openpyxl.styles.Font`, `openpyxl.styles.PatternFill` e exceção `InvalidFileException`. Variável local recorrente: `planilha`; folhas/células são usadas para transformar e salvar cadastros/relatórios. | Em `app.py`: `_carregar_grupos_cadastro_original`, `carregar_lista_impressoras`, `carregar_inventario_relatorio`, `_carregar_cadastro_consolidado`, `baixar_cadastro_consolidado`, `exportar_relatorio_impressoes`, `cadastrar_impressora`, `editar_impressora`, `excluir_impressora`, `aprovar_correcao_relatorio_printer`, `aprovar_inclusao_relatorio_printer`. Rotas associadas: `GET /api/impressoras/consolidado`, `GET /api/relatorio-impressoes/excel`, `POST /api/impressoras`, `PUT /api/impressoras/editar`, `DELETE /api/impressoras/excluir`, `POST /api/relatorio-printer/aprovar-correcao` e `/aprovar-inclusao`. Também é usado por `suprimentos_snmp.carregar_planilha` para ler o cadastro do monitoramento. | Sem SQL: lê/escreve planilhas Excel. Arquivos configurados por `NOME_PLANILHA_ORIGINAL`, `NOME_PLANILHA_ATUALIZADA`, `NOME_PLANILHA_CONSOLIDADA` e `NOME_CSV_LIMPO`. O relatório mensal exportado é criado em memória e enviado como arquivo. |
| **pypdf `>=5,<7`** | `PdfReader` e `PdfReadError`, importados dentro de `monitor/reports/printer/service.py::ler_relatorio_pdf`. Variáveis locais: `leitor`, `texto`, `equipamentos`; o conteúdo de entrada é envolto em `io.BytesIO`. | `ler_relatorio_pdf` é chamado por `app.py::salvar_historico_printer` (`POST /api/relatorio-printer/historico`) e `app.py::analisar_relatorio_printer` (`POST /api/relatorio-printer/analisar`). De lá, o texto passa por `extrair_consumo_relatorio` ou `extrair_equipamentos_relatorio` e depois, para análise, por `comparar_equipamentos`/`criar_email`. | Sem SQL direto. O PDF salvo, o hash SHA-256 e os campos de consumo/equipamentos são persistidos pelo repositório PRINTER na tabela `historico_relatorios_printer`. |
| **python-dotenv 1.1.1** | Função `load_dotenv`. Em `suprimentos_snmp.py`, chamada de módulo `load_dotenv()` carrega o `.env`; em `scripts/teste_email.py`, carrega explicitamente o `.env` na raiz do projeto. | Preparação de configuração antes de consultas SNMP e envio de alertas; o script de teste prepara o envio SMTP. Não há rota que chame `load_dotenv` diretamente. | Não executa SQL. Nomes de variáveis lidos: `EMAIL_SEMED`, `EMAIL_OUTROS`, `SNMP_COMMUNITY`, `GMAIL_REMETENTE` e `GMAIL_SENHA_APP`; `email_estoque.py` também lê `GMAIL_REMETENTE`, `GMAIL_SENHA_APP` e `EMAIL_ESTOQUE_SEMANAL`. Os valores são configuração local e não são reproduzidos neste relatório. |
| **pysnmp `>=7.1,<8`** | Importação wildcard de `pysnmp.hlapi.v1arch.asyncio`; uso observado de `SnmpDispatcher`, `UdpTransportTarget.create`, `CommunityData` e `walk_cmd`. OIDs e `SNMP_PORTA` vêm de `config.configuracoes`; variável `SNMP_COMMUNITY` vem do ambiente com fallback `SNMP_COMMUNITY_PADRAO`. | `suprimentos_snmp.consultar_contador_paginas` lê contador padrão; `consultar` e `consultar_suprimentos_e_presenca` coletam OIDs de modelo/suprimentos; `obter_impressoras` e `main` orquestram o monitoramento. Chamadas síncronas/assíncronas aparecem no `app.py` em `_atualizar_cache_impressoras`, `contador_paginas_impressora` e `registrar_saida_toner_rota`; `relatorio_impressoes.verificar_coleta_mensal`/`_consultar_pendentes` coleta contadores mensais. Rotas alcançadas: `GET /dados`, `GET /api/impressoras/<ip>/contador`, `POST /registrar-saida-toner`, `GET /api/relatorio-impressoes` (esta última lê o resultado já coletado; o agendador faz as consultas). | Sem SQL próprio. Os resultados vão para estado de impressoras/JSON, tabelas de níveis/eventos/estoque e tabelas de coleta mensal. O SNMP usa OIDs padrão configurados, porta 161 e timeout/retries definidos nos pontos de consulta. |
| **Werkzeug** (importado diretamente; não listado à parte em `requirements.txt`) | `RequestEntityTooLarge`, `check_password_hash`, `generate_password_hash`, `secure_filename`. | Em `app.py`, senha é verificada no `login_painel` e gerada no fluxo de `recuperar_senha_admin`/`aceitar_convite`; nome de arquivo é sanitizado em uploads de relatórios; `RequestEntityTooLarge` dá resposta controlada para upload excedente. Estas funções são usadas nas rotas de sessão e de upload de relatório PRINTER. | Sem SQL próprio; hashes de senha e metadados são persistidos pelos repositórios de usuários. |
| **SQLite (`sqlite3`, biblioteca padrão Python)** | `sqlite3.connect` em `estoque.conectar`; conexões/cursors e `execute`/`executemany`; `sqlite3.Row` ao montar relatórios. Arquivo de banco selecionado por `NOME_BANCO` (`estoque.db`). | Usado por `estoque.py`, `pedidos_estoque.py`, `email_estoque.py`, `relatorio_impressoes.py`, `toners_sem_chip.py` e `repositories/*`. As rotas de estoque, histórico, pedidos, contas e relatórios usam esses serviços. | É a dependência que executa as consultas SQL. As principais tabelas e respectivas operações/funções estão discriminadas na seção 11. |

### Fluxo de integração SNMP e contadores

1. `/dados` chama `app._atualizar_cache_impressoras`, que executa `obter_impressoras`; o monitor consulta disponibilidade, modelo e suprimentos e mantém resultados para o painel.
2. `/api/impressoras/<ip>/contador` chama `app.contador_paginas_impressora`, que consulta `suprimentos_snmp.consultar_contador_paginas`; `registrar_saida_toner_rota` também pode confirmar leitura de contador antes de efetuar baixa de estoque.
3. O agendador `iniciar_agendador_contadores` roda `verificar_coleta_mensal`; no primeiro dia do mês, consulta pendências gerais e de cor via `consultar_contador_paginas` e `consultar_contadores_cor`, e grava leituras para o endpoint/exportação de relatório mensal.
4. `contadores_cor_kyocera.consultar_contadores_cor` usa HTTP(S) da biblioteca padrão, não pysnmp; `pysnmp` cobre as consultas SNMP.

## 10. Dependências internas: quem chama quem

| Módulo/serviço interno | Símbolos consumidores observados | Rotas/fluxos que expõem o uso |
|---|---|---|
| `repositories.banco_repo` | `inicializar_tabelas` | Executada na inicialização do `app`; prepara tabelas de estoque, pedidos, coleta mensal, trocas sem chip e histórico PRINTER. |
| `repositories.usuario_repo` | funções de usuário/token: `garantir_tabelas_usuarios`, `obter_usuario_por_id`, `registrar_presenca`, `buscar_credenciais_login`, `redefinir_senha_admin`, `buscar_convite_valido`, `aceitar_convite`, `listar_usuarios_e_convites`, `criar_convite`, `listar_usuarios_online`, `alterar_status_usuario`, `alterar_permissoes_usuario`, `cancelar_convite` | `/entrar`, `/recuperar-admin`, `/convite/<token>`, `/admin/usuarios` e seus endpoints de convite, presença, status e permissões. |
| `repositories.painel_repo` | `garantir_tabela_configuracao`, `criar_token_login`, `consumir_token_login`, `criar_token_recuperacao_admin`, `consumir_token_recuperacao_admin` | Chave de sessão e tokens CSRF de login/recuperação, nos fluxos `/entrar` e `/recuperar-admin`. |
| `repositories.printer_repo` | `salvar_relatorio`, `listar_relatorios`, `buscar_pdf` | `POST/GET /api/relatorio-printer/historico` e `GET /api/relatorio-printer/historico/<id>/pdf`. |
| `repositories.historico_repo` | `listar_movimentacoes`, `listar_saidas_automaticas`, `listar_offline_hoje` | `GET /historico`, incluindo movimentações, baixas automáticas e eventos offline. |
| `estoque.py` | CRUD e operações `cadastrar_toner`, `listar_toners`, `remover_toner`, `reativar_toner`, `atualizar_modelos_compativeis`, `atualizar_estoque_minimo`, `registrar_saida_toner`, `ajustar_estoque_manual`, `registrar_nivel_toner`, `registrar_evento_impressora` | Endpoints de estoque/toner, saída de toner e apresentação do histórico; integra também os eventos e níveis recebidos do monitor. |
| `pedidos_estoque.py` + `email_estoque.py` | Funções de sugestão, criação/envio, decisão, recebimento, cancelamento e agendador | `/api/pedidos-estoque` e subrotas; geração semanal e envio SMTP de pedido. Em caso de falha de envio, `cancelar_solicitacao_envio` desfaz a reserva do pedido. |
| `relatorio_impressoes.py` + `contadores_cor_kyocera.py` + `suprimentos_snmp.py` | `gerar_relatorio_impressoes`, `iniciar_agendador_contadores`, `limites_mes`, `consultar_contador_paginas`, `consultar_contadores_cor`, `modelo_compativel` | `GET /api/relatorio-impressoes`, exportação Excel e coleta mensal em thread daemon. |
| `monitor.reports.printer.service` por `relatorio_printer.py` | `ler_relatorio_pdf`, `extrair_consumo_relatorio`, `extrair_equipamentos_relatorio`, `comparar_equipamentos`, `criar_email` e tipos de erro | Recebimento/análise PRINTER e aprovação de equivalência, correção ou inclusão de equipamento. |
| `utils.texto`, `utils.rede`, `utils.datas`, `utils.seguranca` | normalização de grupo/modelo/série/IP, limites de mês e hash de token | Usados por cadastro, compatibilidade, comparação de inventário, relatórios e autenticação. |

## 11. Consultas SQL, tabelas e pontos de entrada

As consultas a seguir são executadas pelo SQLite. Os nomes de tabela abaixo foram confirmados nas instruções SQL do código. “Rota/fluxo” aponta o ponto funcional que consome o serviço; a transação e as instruções específicas permanecem encapsuladas nos módulos listados.

| Tabelas consultadas/alteradas | Funções que criam ou consultam | Finalidade da consulta | Rota/fluxo da aplicação |
|---|---|---|---|
| `toners` | `estoque.criar_banco`, `cadastrar_toner`, `listar_toners`, `buscar_toner`, `remover_toner`, `reativar_toner`, `atualizar_modelos_compativeis`, `atualizar_estoque_minimo`, `registrar_saida_toner`, `_registrar_saida_no_cursor`, `registrar_nivel_toner`, `ajustar_estoque_manual`; também `pedidos_estoque.receber_pedido` | Criação/migração do esquema; `SELECT` para localizar toner/compatibilidade/saldo; `INSERT` e `UPDATE` para cadastro, saldo, status, modelos e mínimo. | `GET /estoque`, `GET /api/toners/compatibilidade`, `POST /cadastrar-toner`, `POST /ajustar-estoque/<id>`, `DELETE /remover-toner/<id>`, `POST /reativar-toner/<id>`, `PUT /toner/<id>/modelos-compativeis`, `PUT /toner/<id>/estoque-minimo`, `POST /registrar-saida-toner`. |
| `movimentacoes`, `trocas` | `estoque.criar_banco`, `_registrar_saida_no_cursor`, `ajustar_estoque_manual`, `pedidos_estoque.receber_pedido`; leitura por `repositories.historico_repo` | Registra entradas/saídas, responsável, toner, impressora e observação; consulta paginação de movimentações e baixas automáticas. | Rotas de saída/ajuste/recebimento e `GET /historico`. |
| `eventos_impressoras`, `niveis_toner` | `estoque.criar_banco`, `registrar_evento_impressora`, `registrar_nivel_toner`, `_salvar_nivel_toner`; consultas de offline em `repositories.historico_repo`; leitura em `suprimentos_snmp` | Registra transições offline, nível/cor por IP e data; impede eventos offline duplicados no mesmo dia e atualiza o nível atual. | Coleta de impressoras chamada por `/dados`; `GET /historico` apresenta eventos offline. |
| `trocas_toner_sem_chip` | `toners_sem_chip.criar_tabela_trocas_sem_chip`, `registrar_troca_sem_chip`, `estimar_niveis_sem_chip`; consumida por `suprimentos_snmp` | Índice parcial mantém uma troca aberta por IP/cor; `SELECT` encontra ciclo aberto e calcula média de consumo de ciclos fechados do mesmo toner/OID; `INSERT`/`UPDATE` abre/fecha ciclos. | Monitoramento de suprimentos em `/dados`; baixa/registro de troca por `POST /registrar-saida-toner`. |
| `sugestoes_estoque`, `sugestoes_estoque_itens` | `pedidos_estoque.criar_tabelas_pedidos`, `listar_sugestoes_e_pedidos`, `adiar_sugestao_pedido`, `criar_solicitacao_pedido`, `decidir_solicitacao_pedido`; `email_estoque.gerar_sugestao_semanal`, `_inserir_itens_sugestao` | Armazena snapshot semanal do estoque; `SELECT` verifica semana/status/saldo; `INSERT` guarda sugestões e itens; `UPDATE` adia, reabre, arquiva ou muda status; `ALTER TABLE` migra colunas de status e adiamento. | `GET/POST /api/pedidos-estoque` e `POST /api/pedidos-estoque/sugestoes/<semana>/adiar`; sugestão também é gerada pelo agendador semanal. |
| `pedidos_estoque`, `pedidos_estoque_itens` | `pedidos_estoque.criar_tabelas_pedidos`, `listar_sugestoes_e_pedidos`, `_validar_itens`, `criar_solicitacao_pedido`, `marcar_solicitacao_enviada`, `cancelar_solicitacao_envio`, `decidir_solicitacao_pedido`, `cancelar_pendencias_pedido`, `receber_pedido`; `email_estoque.enviar_email_solicitacao` | Consulta estados/itens; registra pedido e linhas; atualiza aceite, envio, recebimento parcial ou cancelamento; migra colunas de status/destinatário/cancelamento. O recebimento aumenta `toners.estoque` e insere `movimentacoes`. | Lista, envio, decisão, recebimento e cancelamento nas rotas `/api/pedidos-estoque...`. |
| `leituras_contadores_mensais`, `leituras_cores_mensais`, `coletas_contadores_mensais` | `relatorio_impressoes.criar_tabelas_contadores`, `_reservar`, `_registrar_leitura`, `_consultar_cores_pendentes`, `verificar_coleta_mensal`, `gerar_relatorio` | Reserva concorrente por data/token; `SELECT` identifica leituras concluídas e limites da coleta; `INSERT ... ON CONFLICT` armazena/retenta leitura; `UPDATE` finaliza coleta. O relatório busca leituras da data inicial/final do mês. | Coleta automática no dia 1; `GET /api/relatorio-impressoes` e `GET /api/relatorio-impressoes/excel`. |
| `historico_relatorios_printer` | `monitor.reports.printer.service.criar_tabela_historico_printer`; `repositories.printer_repo.salvar_relatorio`, `listar_relatorios`, `buscar_pdf` | `SELECT` por setor/competência e hash; `INSERT` ou `UPDATE` de páginas/categorias/PDF; listagem e recuperação do BLOB para download. | Salvar/listar/baixar em `/api/relatorio-printer/historico...`; análise usa o PDF enviado sem persistir até confirmação de salvamento. |
| `usuarios_painel`, `convites_painel` | `repositories.usuario_repo.garantir_tabelas_usuarios`, `obter_usuario_por_id`, `buscar_credenciais_login`, `aceitar_convite`, `listar_usuarios_e_convites`, `criar_convite`, `listar_usuarios_online`, `alterar_status_usuario`, `alterar_permissoes_usuario`, `cancelar_convite` | `SELECT` de credenciais, convites válidos, contas e presença; `INSERT` de usuários/convites; `UPDATE` de senha, acesso, permissões e uso do convite; `DELETE` de convite cancelado. | Login/convite e `/admin/usuarios` com endpoints filhos. |
| `configuracao_painel`, `tokens_login`, `tokens_recuperacao_admin` | `repositories.painel_repo.garantir_tabela_configuracao`, `_criar_token`, `_consumir_token`, `criar_token_login`, `consumir_token_login`, `criar_token_recuperacao_admin`, `consumir_token_recuperacao_admin` | Lê/grava a configuração da sessão e cria/consome tokens com hash e expiração; tokens expirados são removidos e tokens aceitos são consumidos uma única vez. | Inicialização do `app`; formulários de login e recuperação administrativa. |

## 12. Variáveis de integração e configuração relevantes

| Variável/nome | Definição/origem | Uso concreto |
|---|---|---|
| `app` | Instância `Flask(__name__)` em `app.py` | Registro das 44 rotas, configuração de sessão e limite de upload. |
| `BASE_DIR` | `Path(__file__).parent` em `app.py` e `suprimentos_snmp.py` | Resolve caminhos locais de planilhas, logs e arquivos JSON. |
| `NOME_BANCO` / `BANCO` | `NOME_BANCO` em `config/configuracoes.py`; caminho ligado no módulo de estoque | Seleciona o arquivo SQLite usado por `estoque.conectar`. |
| `SNMP_COMMUNITY` | Variável de ambiente com fallback para `SNMP_COMMUNITY_PADRAO` | Credencial comunitária entregue a `CommunityData` nas consultas SNMP. |
| `OID_CONTADOR_PAGINAS`, `OID_DESCRICAO_SISTEMA`, `OID_SUPRIMENTOS_*`, `SNMP_PORTA` | Constantes em `config/configuracoes.py` | Identificam contadores, modelo, suprimentos e destino das consultas SNMP. |
| `EMAIL_SEMED`, `EMAIL_OUTROS`, `GMAIL_REMETENTE`, `GMAIL_SENHA_APP`, `EMAIL_ESTOQUE_SEMANAL` | `.env`/ambiente; somente os nomes estão documentados aqui | Selecionam destinatário/remetente e credencial SMTP em `suprimentos_snmp.py`, `email_estoque.py` e scripts de teste. |
| `NOME_PLANILHA_*`, `NOME_CSV_LIMPO`, `NOME_*` JSON | Constantes em `config/configuracoes.py` | Conectam os módulos de cadastro/monitoramento aos arquivos de dados listados na seção 2. |
| `planilha`, `aba`, `linha` | Variáveis locais nas rotinas `openpyxl` | Representam workbook, worksheet e registro processado; não são objetos compartilhados globalmente. |
| `leitor`, `texto`, `equipamentos` | Variáveis locais de `ler_relatorio_pdf` e funções de extração | Encadeiam a leitura do PDF para validação e análise PRINTER. |
| `conexao`, `cursor`, `token` | Variáveis locais dos serviços SQLite | `conexao/cursor` executam transações e SQL; `token` identifica a reserva exclusiva de coleta mensal. |

### Limites da associação estática

O mapa associa importações e chamadas que aparecem no código local; não atribui consultas SQL a bibliotecas que não as executam. Alguns fluxos, como monitoramento e coleta mensal, são iniciados por threads/agendadores e não por uma requisição individual; nesses casos, a rota indicada é a que expõe os dados ou inicia a leitura sob demanda, e o fluxo assíncrono é identificado separadamente. Bibliotecas padrão adicionais (`asyncio`, `threading`, `smtplib`, `json`, `openpyxl` etc.) são detalhadas quando participam diretamente das integrações acima; a lista não pretende catalogar cada import de biblioteca padrão sem relação com as dependências solicitadas.
