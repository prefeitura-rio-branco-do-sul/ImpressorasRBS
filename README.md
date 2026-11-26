# ImpressorasRBS# Relatório completo de aplicação — Monitor de Impressoras

## 1. Resumo

O **Monitor de Impressoras** é uma aplicação web interna para acompanhar uma frota de impressoras de rede e reunir, em um só painel, informações de disponibilidade, suprimentos, estoque de toners, consumo de páginas e conferência de relatórios PRINTER. O sistema combina leitura de dispositivos por SNMP, cadastro em planilhas Excel, dados operacionais em SQLite, tarefas agendadas e ações feitas por pessoas com permissões diferentes.

Este documento descreve a aplicação: sua inicialização, os perfis de acesso, o fluxo de dados, as funcionalidades, os arquivos utilizados, as rotas e as configurações necessárias para execução.

## 2. Visão geral e componentes

### 2.1 Fluxo de funcionamento de ponta a ponta

1. **Inicialização:** ao executar `python app.py`, a aplicação prepara as tabelas SQLite, carrega as configurações locais e inicia o servidor Flask. A inicialização direta também inicia os agendadores do resumo semanal de estoque e dos contadores mensais.
2. **Cadastro:** o servidor lê os dados dos equipamentos da planilha de impressoras selecionada. Esse cadastro fornece endereço IP, nome/local, setor, patrimônio, série e modelo, conforme o formato da planilha.
3. **Coleta:** em segundo plano, o monitor consulta as impressoras por SNMP. Os dados coletados são processados, associados ao cadastro, usados para atualizar o estado e os níveis de suprimentos e, quando aplicável, gravados no histórico.
4. **Consulta no painel:** depois de entrar, cada usuário vê as áreas liberadas para suas permissões. A interface consulta os dados do painel e atualiza os indicadores periodicamente; as ações de estoque, cadastro e relatórios enviam pedidos ao servidor, que valida a permissão e os dados antes de gravar alterações.
5. **Acompanhamento e operação:** a equipe localiza impressoras, verifica alertas, registra movimentos de toner, confere históricos e analisa relatórios. Sugestões podem apoiar a compra, mas uma pessoa confirma o pedido e registra o recebimento.
6. **Tarefas automáticas:** o processo semanal prepara e envia um resumo de reposição; o processo mensal coleta contadores em datas determinadas; os alertas de toner são avaliados durante as coletas. Essas tarefas dependem de a aplicação estar em execução e de rede, dispositivos e configurações externas disponíveis.

O fluxo resume a implementação atual. Se o processo Flask não estiver iniciado diretamente como descrito, as rotinas de agendamento daquele bloco de inicialização não são iniciadas automaticamente.

### 2.2 Componentes e responsabilidades

| Componente | Responsabilidade |
|---|---|
| [`app.py`](./app.py) | Aplicação Flask: autenticação, controle de permissões, páginas e APIs, validação das operações, atualização do painel e integração dos serviços. |
| [`suprimentos_snmp.py`](./suprimentos_snmp.py) | Coleta de estado, suprimentos e contadores por SNMP; tratamento de indisponibilidade; atualização de leituras e execução das regras de alerta. |
| [`estoque.py`](./estoque.py) | Acesso ao banco e regras de cadastro de toner, saldos, entradas/saídas, ajustes, trocas, níveis e eventos de impressoras. |
| [`pedidos_estoque.py`](./pedidos_estoque.py) | Consulta de sugestões e pedidos, confirmação manual de pedido, controle de recebimentos parciais e registro de entradas no estoque. |
| [`email_estoque.py`](./email_estoque.py) | Geração da sugestão semanal, agendamento e envio do resumo de reposição por SMTP; o e-mail não efetua compra. |
| [`relatorio_impressoes.py`](./relatorio_impressoes.py) | Coleta mensal dos contadores, armazenamento das leituras, geração da diferença de páginas e exportação Excel. |
| [`contadores_cor_kyocera.py`](./contadores_cor_kyocera.py) | Consulta dos contadores específicos de cor de modelos Kyocera compatíveis. |
| [`toners_sem_chip.py`](./toners_sem_chip.py) | Lista os equipamentos e cores acompanhados sem chip e fornece regras para estimar níveis após trocas registradas. |
| [`relatorio_printer.py`](./relatorio_printer.py) e [`monitor/reports/printer/service.py`](./monitor/reports/printer/service.py) | Fachada de compatibilidade e implementação da leitura de PDFs PRINTER, extração e comparação de equipamentos/consumo, validação dos formatos e preparação do texto para e-mail. |
| [`repositories/`](./repositories) | Consultas e operações de persistência separadas para banco, histórico, configurações/tokens, impressoras e PDFs PRINTER. |
| [`config/`](./config) e [`utils/`](./utils) | Constantes de configuração e funções comuns de normalização de texto, datas, rede e segurança. |
| [`templates/`](./templates) e [`static/`](./static) | Interface do navegador: menu, painel, formulários, gráficos, estilos e chamadas às APIs. A página principal está em [`templates/index.html`](./templates/index.html); os scripts principais ficam em [`static/js/`](./static/js). |

### 2.3 Árvore dos componentes da aplicação

A árvore abaixo mostra os principais componentes de execução e dados da aplicação. Arquivos temporários, caches, testes, utilitários de diagnóstico e documentos do projeto foram omitidos. O `.env` contém configurações locais e não deve ser compartilhado nem incluído em repositórios.

```text
impressoras-teste/
├── app.py
├── estoque.py
├── suprimentos_snmp.py
├── pedidos_estoque.py
├── email_estoque.py
├── relatorio_impressoes.py
├── contadores_cor_kyocera.py
├── relatorio_printer.py
├── toners_sem_chip.py
├── requirements.txt
├── monitor/
│   ├── __init__.py
│   ├── auth/
│   │   └── __init__.py
│   ├── printers/
│   │   └── __init__.py
│   ├── stock/
│   │   └── __init__.py
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── printer/
│   │   │   ├── __init__.py
│   │   │   └── service.py
│   │   └── usage/
│   │       └── __init__.py
│   ├── infrastructure/
│   │   └── __init__.py
│   └── shared/
│       └── __init__.py
├── config/
│   ├── __init__.py
│   └── configuracoes.py
├── repositories/
│   ├── __init__.py
│   ├── banco_repo.py
│   ├── comum.py
│   ├── historico_repo.py
│   ├── painel_repo.py
│   ├── printer_repo.py
│   └── usuario_repo.py
├── utils/
│   ├── __init__.py
│   ├── datas.py
│   ├── rede.py
│   ├── seguranca.py
│   └── texto.py
├── .gitignore
├── .env.example
├── templates/
│   ├── index.html
│   ├── login.html
│   ├── aceitar_convite.html
│   ├── recuperar_senha_admin.html
│   ├── usuarios.html
│   └── _grafico_printer.html
├── static/
│   ├── BRASAO_CURVAS-01.png
│   ├── css/
│   │   └── style.css
│   └── js/
│       ├── api.js
│       ├── impressoras.js
│       ├── menu-state.js
│       └── script.js& "C:\Program Files\Git\cmd\git.exe" init
├── ImpressorasRBS.xlsx
├── ImpressorasRBS_atualizada.xlsx
├── ImpressorasRBS_consolidada.xlsx
├── Impressoras_Limpo.csv
├── estoque.db
├── alertas_enviados.json
├── historico.json
├── historico_toner_6.json
├── impressoras_encontradas.json
├── impressoras_offline.json
├── .relatorio_locais_equivalentes.json
├── monitor.log
└── .env
```

Os arquivos Python implementam o servidor e as regras; `templates/` e `static/` compõem a interface. A planilha, o banco, os arquivos JSON e o log guardam ou registram dados da execução local.

## 3. Funcionalidades

### 3.1 Acesso e administração de usuários

- Login com usuário e senha; as senhas são guardadas como hash.
- Primeiro acesso de contas individuais por convite de uso único, com expiração em 48 horas. A pessoa define o próprio usuário e senha ao aceitar o convite.
- A opção de administração de contas foi retirada do menu; a rota administrativa existente continua restrita a administradores e mantém os usuários e permissões cadastrados.
- A presença é atualizada durante o uso do painel; a tela de administração considera online quem acessou nos últimos dois minutos.
- Permissões separadas para monitoramento, edição/exclusão de impressoras, visualização e operações de estoque, histórico e análise/aprovação de relatórios. A administração tem acesso total.
- Há proteção CSRF em formulários, tokens temporários para login/recuperação e redefinição da senha administrativa limitada ao próprio computador.
- O acesso é limitado a loopback ou endereços privados; `PAINEL_REDE_LOCAL` pode restringir a sub-rede permitida.

As permissões podem ser atribuídas em conjunto à conta. Elas controlam o acesso às funções, não apenas a visibilidade dos botões:

| Permissão | Ações liberadas |
|---|---|
| `monitor.view` | Consultar painel, lista/ficha de impressoras, contadores e relatório mensal de impressões. |
| `printers.edit` / `printers.delete` | Editar dados cadastrais ou retirar logicamente uma impressora do painel. |
| `stock.view` | Consultar estoque e pedidos/sugestões. |
| `toner.create` / `toner.manage` | Cadastrar, ativar/desativar toner e editar compatibilidades. |
| `stock.adjust` / `stock.issue` | Ajustar saldos, confirmar pedidos, registrar recebimentos e saídas. |
| `history.view` | Consultar movimentações e eventos do histórico geral. |
| `report.analyze` / `report.approve` | Analisar e guardar relatórios PRINTER; aprovar correções, equivalências e inclusões. |
| Administrador | Administrar contas/permissões e executar todas as funções do painel. |

O gerenciamento de usuários é uma página administrativa separada. Convites são individuais e devem ser enviados por canal confiável; o link expira em 48 horas e só pode ser utilizado uma vez.

### 3.2 Monitoramento das impressoras

- O cadastro vem, por ordem de preferência, de `ImpressorasRBS_atualizada.xlsx`, `ImpressorasRBS_consolidada.xlsx` ou `ImpressorasRBS.xlsx`, usando o primeiro arquivo existente.
- O painel consulta `/dados` e atualiza os indicadores a cada 30 segundos. O servidor mantém um cache e inicia a coleta SNMP em segundo plano, também com intervalo mínimo de 30 segundos.
- A coleta combina IPs do cadastro com IPs encontrados em coletas anteriores e consulta as impressoras por SNMP na porta UDP 161.
- Quando a consulta de suprimentos falha, o monitor verifica novamente a presença por SNMP antes de marcar o equipamento como offline. Se ele responder, mas não fornecer os suprimentos, permanece online com os níveis indisponíveis. O estado offline indica ausência de resposta SNMP, não necessariamente que a impressora esteja desligada.
- Para impressoras que respondem, tenta identificar modelo e suprimentos e calcula níveis aproximados de toner a partir de capacidade e nível reportados pelo equipamento.
- A interface mostra total, online, offline e impressoras com toner baixo; apresenta gráficos de situação e quantidade por setor; permite pesquisar por nome/IP/patrimônio e filtrar por setor ou estado.
- A tela de impressoras organiza equipamentos por setor e oferece ficha com dados do equipamento, toners compatíveis cadastrados e contador de páginas consultado via SNMP.
- Na ficha, os toners são consultados independentemente do contador. A compatibilidade usa o modelo ou família cadastrada; o contador depende da resposta SNMP da impressora e informa quando está indisponível.
- Em **Relatório de impressões**, o sistema compara o contador registrado no dia 1 com o do dia 1 seguinte e permite baixar o resultado em Excel. A coleta começa à meia-noite, somente com a aplicação ligada, e equipamentos sem resposta são consultados novamente a cada 30 minutos durante o dia 1. Leituras ausentes não são estimadas; os horários efetivos e situações que precisam de conferência são exibidos. A diferença corresponde ao intervalo entre as leituras e pode não detectar reinicializações intermediárias do contador.
- Nas Kyocera TASKalfa coloridas compatíveis, a coleta consulta também a interface local do equipamento para P&B e níveis 1, 2 e 3 de cor; cada categoria soma cópias e impressões e não inclui fax. Esses contadores são independentes do contador geral SNMP e podem divergir dele. Modelos sem suporte ou leituras ausentes não recebem valores estimados. Para acessar o HTTPS dessas impressoras, que usam certificados próprios, a consulta não valida o certificado; não são enviadas credenciais e redirecionamentos são recusados.
- Há edição de nome/local, setor, série e modelo. Exclusão pelo painel marca o registro como excluído em vez de apagar a linha da planilha. O sistema impede editar ou excluir quando não consegue identificar o registro de forma única e mantém modelos M2040dn no grupo `OUTRAS`.

No menu principal, o usuário encontra **Impressoras**, **Offline**, **Toners baixos**, **Toners não confiáveis**, **Relatório de impressões**, **Estoque**, **Histórico** e **Relatório PRINTER**, de acordo com suas permissões. Os cartões, gráficos e filtros levam às listas correspondentes; a ficha da impressora reúne os dados cadastrados, suprimentos compatíveis e contadores disponíveis.

### 3.3 Alertas e histórico de toner baixo

- O cartão e a lista de toner baixo consideram impressoras online com pelo menos uma leitura confiável de **7% ou menos**. Leituras não confiáveis são excluídas, exceto estimativas identificadas; quando não é possível verificá-las, o cartão mostra um traço e a lista informa a falha. O envio automático de e-mail ocorre quando uma leitura confiável chega a **5% ou menos**, uma vez por impressora e cor enquanto permanecer nesse nível.
- O alerta usa configurações de destinatário e conta de e-mail presentes no ambiente; o envio não é tentado se remetente ou senha de aplicativo não estiverem configurados.
- Os alertas de toner usam destinatários fixos definidos no ambiente: `EMAIL_SEMED` para SEMED e `EMAIL_OUTROS` para os demais setores. A planilha de impressoras não é consultada para obter endereços de e-mail.
- Os alertas enviados são controlados em `alertas_enviados.json`; quando o nível volta a ser maior que 5%, um novo alerta pode ser enviado se cair novamente. Alertas registrados pela regra anterior permanecem ativos até o nível ultrapassar 5%, evitando repetição. Falhas de envio são registradas e retentadas na próxima coleta. Se ocorrer falha após o aceite do e-mail pelo servidor ou interrupção antes de gravar o controle, pode ocorrer envio duplicado.
- Leituras diárias em 6% são registradas em `historico_toner_6.json`. Cinco dias consecutivos nessa condição, com leitura atual ainda em 6%, classificam o toner como não confiável e suspendem o alerta automático. A interface tem uma seção própria para essa condição.
- Os toners sem chip das impressoras 10.52.0.6 (preto) e 10.6.0.1 (preto, ciano, magenta e amarelo) são classificados diretamente como não confiáveis. As leituras do chip são ignoradas e não provocam saída automática nem e-mail.
- Ao instalar um toner novo nesses equipamentos, use **Registrar saída**, informe uma unidade e marque a opção de troca sem chip. A saída e a troca são gravadas juntas depois da leitura do contador; se a leitura falhar, nenhuma das duas é gravada. O modelo e o patrimônio precisam corresponder ao cadastro. Não marque a opção para uma retirada que ainda não foi instalada.
- A primeira troca inicia o acompanhamento; após a troca seguinte, a média de páginas entre trocas é calculada separadamente por equipamento, cor e toner cadastrado. O nível é estimado considerando o toner recém-instalado como 100% e o consumo proporcional à média, limitado entre 0% e 100%. Antes de existir um ciclo completo, após falha do contador ou se o contador diminuir, o nível fica indisponível. Ciclos com contador reiniciado ou incompatível não entram na média. O painel identifica os valores como estimativas e não envia e-mails para eles.
- O contador utilizado é o contador geral de páginas: especialmente para cores, ele não mede a cobertura ou o consumo real de cada toner, portanto a estimativa pode divergir bastante da quantidade restante. A troca deve ser registrada no momento da instalação para que o ciclo seja representativo.
- O módulo de estoque também detecta uma possível troca quando o nível passa de até 10% para pelo menos 90%. Ele usa o modelo cadastrado da impressora e, se encontrar exatamente um toner ativo compatível com esse modelo e a cor, registra uma saída automática de uma unidade. Essa detecção depende das leituras SNMP e das compatibilidades cadastradas; a baixa pode deixar o saldo negativo.

### 3.4 Estoque de toners

- Consulta de toners ativos e opção para incluir inativos.
- Pesquisa por código ou modelo compatível na tabela de estoque, sem diferenciar letras maiúsculas ou acentos; o filtro continua aplicado após atualizar a tabela.
- Cadastro com marca, código, cor, modelos compatíveis, quantidade inicial e estoque mínimo. Marca/código/cor identificam o toner; ao cadastrar novamente um item existente, a quantidade informada é somada ao saldo.
- Ajuste manual de entrada ou saída ao clicar na quantidade em estoque de um toner ativo, com quantidade informada, confirmação e mensagem de resultado; exige permissão de ajuste. A retirada não pode superar o saldo disponível; os novos ajustes são registrados no histórico com o responsável.
- Registro de saída com quantidade, impressora/IP, patrimônio, responsável e observação. A saída altera o saldo e cria registros de movimentação/troca; não permite retirar toner inativo ou quantidade não positiva.
- Edição de modelos compatíveis e do estoque mínimo.
- Remoção lógica e reativação de toner, preservando o cadastro.
- Indicadores e filtros de estoque usam o saldo e o mínimo cadastrado para destacar itens que precisam de reposição.
- Às segundas-feiras a partir das 8h, o servidor envia uma sugestão simples de pedido para `EMAIL_ESTOQUE_SEMANAL`, com os toners e as quantidades positivas necessárias para atingir o mínimo, sem modelos de impressora ou saldos. Se não houver quantidades positivas, envia uma mensagem informativa. Nenhum pedido é realizado automaticamente.
- O servidor precisa estar em execução; se iniciar após as 8h de segunda-feira, tenta enviar naquele dia. Se permanecer desligado durante toda a segunda-feira, o resumo daquela semana não será enviado. Falhas são registradas em `monitor.log` e retentadas a cada cinco minutos. O registro de envio no banco evita envios repetidos na mesma semana; uma interrupção após o aceite pelo servidor de e-mail e antes do registro local pode causar duplicidade.
- Em **Estoque > Sugestões e pedidos**, a sugestão semanal fica disponível para revisão sem mostrar saldos ou modelos de impressora. Ela também permite ajustar itens que estão no mínimo e começam com quantidade zero; informe zero para não incluí-los no pedido. Uma pessoa com permissão de ajuste pode alterar as quantidades e confirmar seu registro como pedido; isso não envia uma compra ao fornecedor. Cada sugestão pode ser confirmada uma única vez. Confira pedidos pendentes para evitar registrar pedidos duplicados em semanas diferentes.
- A coluna **Impressoras compatíveis** estima quantos equipamentos cadastrados usam modelos ou famílias compatíveis com cada toner, incluindo os offline. Com permissão de monitoramento, clique na quantidade para ver nome, modelo, setor, patrimônio e IP. O mesmo equipamento pode aparecer em mais de um toner e a contagem não confirma o toner instalado; modelos não identificados não entram no cálculo.
- As quantidades ainda não confirmadas permanecem na tela ao trocar o filtro de estoque ou navegar entre seções, mas não são salvas ao recarregar ou fechar a página.
- Ao receber toners, informe as quantidades efetivamente recebidas no pedido e selecione **Adicionar recebimento ao estoque**. São aceitas entregas parciais até o total pedido; cada entrada é registrada no histórico com o responsável. Toners inativos precisam ser reativados antes do recebimento.

### 3.5 Histórico

A rota `/historico` retorna entradas, saídas manuais, saídas automáticas por detecção de troca e eventos de impressoras offline. As movimentações manuais são paginadas (limite configurável de 1 a 200, padrão 50); as saídas automáticas aparecem apenas na seção de trocas automáticas e são contadas uma vez. As contagens nas abas e seções consideram apenas os registros exibidos. A consulta de eventos offline considera os eventos registrados no dia atual.

O banco SQLite mantém as tabelas de toners, movimentações, trocas, níveis de toner e eventos offline. O histórico de retorno online também é gravado em `historico.json`.

### 3.6 Conferência do relatório PRINTER

- A conferência aceita um ou mais PDFs pesquisáveis, com limite total de upload de 10 MB e até 100 páginas por PDF. A análise não salva os arquivos automaticamente.
- Extrai número de série, modelo, local e identificador do equipamento; ignora itens identificados como scanners.
- Compara as séries e locais do PDF com o cadastro atual e aponta séries duplicadas, séries não encontradas, duplicidades no cadastro e divergências de local.
- Gera assunto e corpo de e-mail para revisão e cópia manual. **Essa função não envia o e-mail.**
- Permite aprovar equivalência entre nomes de locais, corrigir o local do cadastro, incluir um equipamento novo ou confirmar substituição quando a série muda e o IP permanece.
- Alterações aprovadas são gravadas em `ImpressorasRBS_atualizada.xlsx`; a planilha original é preservada. As equivalências aprovadas ficam em `.relatorio_locais_equivalentes.json`.
- As aprovações validam série/IP e recusam operações ambíguas, como série duplicada ou IP associado a vários registros.
- No histórico, o usuário salva um PDF por vez e pode baixá-lo novamente. O PDF original e os dados ficam no SQLite, sem criptografia adicional. O acesso exige a permissão de análise PRINTER.
- Os relatórios são identificados pelo centro de custo e competência; há um por mês para Saúde, Tesouro e Educação. Um PDF diferente para o mesmo setor e mês exige confirmação antes de substituir o anterior; um PDF idêntico não é duplicado.
- A comparação permite escolher dois meses e mostra a diferença por setor. Um relatório ausente é indicado como tal, não como zero.
- O gráfico de barras aparece na página inicial para usuários com permissão de análise PRINTER. Mostra os meses disponíveis lado a lado por setor, com valores e ausências também disponíveis em tabela. Um relatório ausente não é representado como zero.
- O total de páginas soma o consumo de cópias/impressões P&B e níveis de cor 1, 2 e 3, validando o resumo contra os detalhes. Scanner e outros serviços não entram. O consumo de página/metro linear é exibido separadamente, pois não representa uma quantidade identificável de páginas. Formatos ou serviços não reconhecidos são recusados para evitar totais incorretos.

### 3.7 O que é automático e o que depende da equipe

| Processo | Automático | Ação humana necessária |
|---|---|---|
| Coleta de estado e suprimentos | Consulta SNMP, atualização do cache e avaliação das regras de toner baixo. | Investigar indisponibilidade, conferir níveis não confiáveis e providenciar a troca física. |
| Alerta de toner | Envio de e-mail quando uma leitura confiável atinge o limite configurado, com controle para evitar repetição enquanto continuar abaixo do limite. | Manter destinatários e conta SMTP configurados e acompanhar o alerta. |
| Sugestão semanal de reposição | Gera a sugestão de itens abaixo do mínimo e tenta enviá-la por e-mail às segundas-feiras após as 8h. | Revisar quantidades, confirmar o pedido e realizar a compra fora do sistema. |
| Recebimento de toners | Não é automático: a aplicação permite registrar entradas parciais de um pedido confirmado. | Informar a quantidade recebida e a pessoa responsável. |
| Contadores mensais | Coleta leituras nas datas previstas, tenta novamente equipamentos pendentes e calcula diferenças entre períodos. | Conferir horários, falhas e leituras antes de usar os valores como referência administrativa. |
| Relatório PRINTER | Extrai e compara dados do PDF e prepara um texto de e-mail. | Revisar divergências, aprovar alterações cadastrais e enviar/circular o e-mail manualmente. |

## 4. Armazenamento e arquivos

| Arquivo | Uso identificado |
|---|---|
| `estoque.db` | Banco SQLite para estoque, usuários, convites, configuração, tokens, leituras de toner e contadores, movimentações, eventos offline, sugestões/pedidos, agendamentos e histórico PRINTER (incluindo PDFs). |
| `ImpressorasRBS.xlsx` | Planilha original do cadastro de impressoras. |
| `ImpressorasRBS_atualizada.xlsx` | Cadastro de trabalho preferencial; recebe alterações aprovadas/editadas pelo sistema. |
| `ImpressorasRBS_consolidada.xlsx` | Fonte alternativa do cadastro, usada quando a planilha atualizada não existe e antes da original. |
| `Impressoras_Limpo.csv` | Fonte auxiliar usada junto à planilha para comparar cadastros na geração do arquivo consolidado para download. |
| `Impressoras_Consolidadas.xlsx` | Nome do arquivo Excel criado para download pela rota de comparação/consolidação; não é o mesmo que a planilha `ImpressorasRBS_consolidada.xlsx`. |
| `alertas_enviados.json` | Controle de alertas de toner já enviados. |
| `historico_toner_6.json` | Histórico diário de toner em 6%. |
| `impressoras_encontradas.json` | IPs que responderam na coleta. |
| `impressoras_offline.json` | Controle do início de indisponibilidade durante a coleta. |
| `historico.json` | Eventos de retorno online registrados pelo coletor. |
| `monitor.log` | Log de execução e erros. |
| `.env` | Fonte de configurações locais carregadas pelo módulo SNMP; contém credenciais e configurações privadas, não deve ser compartilhado nem incluído no repositório. |
| `.env.example` | Modelo sem credenciais com os nomes das variáveis de ambiente usadas pela aplicação; copie para `.env` e preencha os valores locais. |
| `.gitignore` | Evita que credenciais, bancos, logs, planilhas, exportações e arquivos de estado locais sejam adicionados ao Git. Não remove arquivos que já estejam sendo rastreados. |

## 5. Rotas principais

| Rota | Uso |
|---|---|
| `/entrar`, `/sair`, `/convite/<token>`, `/recuperar-admin` | Autenticação, ativação de convite, saída e recuperação administrativa local. |
| `/admin/usuarios` e rotas `/admin/...` | Gerenciamento de contas, permissões, convites e presença. |
| `/` e `/dados` | Interface e dados atualizados do monitoramento. |
| `/api/impressoras/editar`, `/api/impressoras/excluir` | Edição e exclusão lógica do cadastro. |
| `/api/impressoras/consolidado` | Download do Excel que compara e consolida os cadastros da planilha e do CSV auxiliar. |
| `/api/impressoras/<ip>/contador` | Contador SNMP e compatibilidade de toner para a ficha do equipamento. |
| `/api/impressoras/<ip>/toners` | Toners compatíveis com o modelo cadastrado da impressora. |
| `/api/relatorio-impressoes` e `/api/relatorio-impressoes/excel` | Comparação mensal dos contadores e exportação em Excel. |
| `/api/toners/compatibilidade` | Consulta das impressoras compatíveis com cada toner. |
| `/estoque`, `/cadastrar-toner`, `/ajustar-estoque/<id>`, `/registrar-saida-toner` | Consulta, cadastro, ajuste e saída de toner. |
| `/remover-toner/<id>`, `/reativar-toner/<id>`, `/toner/<id>/...` | Gerenciamento de toner, compatibilidade e estoque mínimo. |
| `/api/pedidos-estoque` e `/api/pedidos-estoque/<id>/receber` | Consulta e confirmação de sugestões/pedidos e registro de recebimentos. |
| `/historico`, `/toners-nao-confiaveis` | Histórico e consulta de toners classificados como não confiáveis. |
| `/api/relatorio-printer/...` | Análise, histórico/download de PDFs e aprovação de equivalências, correções e inclusões/substituições. |

## 6. Configuração e execução

Dependências Python declaradas em [`requirements.txt`](./requirements.txt): Flask, openpyxl, pypdf, python-dotenv e pysnmp. A aplicação pode ser iniciada com `python app.py`; com a inicialização direta, o código inicia os agendadores e o servidor Flask na porta 5000, vinculado a todas as interfaces (`0.0.0.0`) e com `debug=False`. Essa forma de execução descreve o código atual, mas não substitui a configuração de um servidor de produção com WSGI, HTTPS, logs, monitoramento e processo de recuperação.

Para configurar o ambiente local, copie `.env.example` para `.env` e preencha as variáveis necessárias. Mantenha o `.env` privado: ele é ignorado pelo Git, enquanto `.env.example` pode ser compartilhado por conter apenas nomes e valores vazios ou padrões. As regras do `.gitignore` não deixam de rastrear arquivos que já tenham sido adicionados ao Git anteriormente.

Configurações lidas pelo código:

- `PAINEL_SESSION_SECRET`: chave persistente das sessões; se ausente, o sistema mantém uma chave no banco.
- `PAINEL_REDE_LOCAL`: sub-rede autorizada opcional.
- `PAINEL_BASE_URL`: URL-base opcional para links de convite.
- `SNMP_COMMUNITY`: comunidade SNMP; o padrão no código é `public`.
- `EMAIL_SEMED`, `EMAIL_OUTROS`, `GMAIL_REMETENTE` e `GMAIL_SENHA_APP`: destinatários e credenciais usados para alertas automáticos.
- `EMAIL_ESTOQUE_SEMANAL`: destinatário do resumo semanal de estoque; usa o mesmo remetente e senha de aplicativo dos alertas.

O navegador carrega Tailwind CSS por CDN, além dos estilos locais; portanto, essa parte visual depende de acesso ao CDN.


