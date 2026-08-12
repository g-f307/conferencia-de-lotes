# Conferência de Lotes

[![CI](https://github.com/g-f307/conferencia-de-lotes/actions/workflows/ci.yml/badge.svg)](https://github.com/g-f307/conferencia-de-lotes/actions/workflows/ci.yml)

Automação corporativa para conferência de registros de inspeção, com
processamento resiliente por item, integração com BotCity Maestro e automação
web controlada por Playwright.

## Visão geral

O fluxo combina Dispatcher, DataPool, Performer, Credentials Vault, Page
Objects, evidências visuais e observabilidade:

1. o Dispatcher lê `dados_entrada/lotes_auditoria.csv` e publica uma entrada
   por linha no DataPool `FilaAuditoriaLotes2`;
2. a credencial `credencial_erp2` é recuperada do Credentials Vault;
3. uma sessão Playwright headless autentica uma única vez na aplicação local;
4. o Performer consome a fila e processa cada lote isoladamente;
5. as regras RN01–RN07 determinam aprovação, reprovação, divergência ou
   revisão;
6. `LoginPage` e `FormPage` executam a interação web correspondente ao item;
7. o resultado, a mensagem e o caminho da captura são gravados no DataPool
   antes da finalização do item;
8. logs JSON Lines, resumo JSON e relatório PDF consolidam a execução.

Uma inconsistência ou falha web em um lote não interrompe os demais itens. Uma
falha anterior ao consumo, como configuração, entrada ou credencial inválida,
encerra a execução imediatamente.

## Objetivo

Executar a conferência de lotes de forma:

- resiliente, isolando falhas por item;
- rastreável, com resultado e evidência associados ao lote;
- segura, sem credenciais no código, no `.env` ou nos logs;
- reproduzível nos modos local, Docker e BotCity Runner;
- manutenível, separando regras, orquestração e interface por Page Objects;
- auditável, com logs estruturados e resultados consolidados.

## Escopo

Estão implementados:

- configuração externa e caminhos relativos;
- fail-fast da pasta `dados_entrada/`;
- Dispatcher de CSV por cabeçalho;
- DataPool local ou BotCity Maestro;
- validações RN01–RN07;
- recuperação da credencial pelo Vault;
- Playwright síncrono com Chromium headless;
- Page Objects com locators semânticos e waits por condição;
- processamento web e captura de PNG por item;
- continuidade após divergência, revisão ou falha técnica isolada;
- campos de saída no DataPool;
- logs estruturados no arquivo e no console;
- resumo JSON, relatório PDF, artefatos e `finish_task`;
- pacote ZIP para o BotCity Runner;
- Docker e integração contínua;
- relatório executivo Excel com dashboard, gráficos nativos e validação
  RN01–RN12.

## Fora do escopo

Não fazem parte desta versão:

- captura de anexos de e-mail;
- acesso ou atualização de ERP produtivo;
- armazenamento de credenciais reais no repositório;
- interface para resolução dos itens encaminhados à revisão;
- execução distribuída de navegadores;
- alteração automática da base de referência.

`web/index-lotes/` é uma aplicação controlada, destinada somente à
demonstração e à produção de evidências. Nenhum sistema real é acessado.

## Processo de negócio

![Processo BPMN de inspeção de lotes](docs/diagrama_pdd.svg)

O modelo editável está em
[`docs/diagrama_pdd.bpmn`](docs/diagrama_pdd.bpmn). A relação entre o processo,
as regras e o código está registrada em
[`docs/REVISAO_BPMN_PDD.md`](docs/REVISAO_BPMN_PDD.md).

## Arquitetura

```mermaid
flowchart LR
    CSV[CSV de lotes] --> DISPATCHER[Dispatcher]
    DISPATCHER --> DP[FilaAuditoriaLotes2]
    RUNNER[Local ou Runner] --> MAIN[src/main.py]
    MAIN --> VAULT[Credentials Vault]
    MAIN --> SESSION[Sessão Playwright headless]
    SESSION --> LOGIN[LoginPage]
    DP --> PERFORMER[LotePerformer]
    PERFORMER --> RULES[RN01–RN07]
    PERFORMER --> SESSION
    SESSION --> FORM[FormPage]
    FORM --> PNG[PNG por item]
    PERFORMER --> DP
    MAIN --> LOG[Logs JSON Lines]
    MAIN --> REPORT[Resumo JSON e PDF]
    MAIN --> MAESTRO[Artefatos e finish_task]
```

As responsabilidades principais são:

| Componente | Responsabilidade |
|---|---|
| `src/main.py` | Validar o ambiente e coordenar Vault, Playwright, Dispatcher, Performer e encerramento. |
| `src/dispatcher.py` | Publicar uma entrada por linha e reservar os campos de saída. |
| `src/bot.py` | Classificar, processar e finalizar cada item de forma isolada. |
| `src/validation.py` | Aplicar RN01–RN07 sem dependência da interface. |
| `src/web_automation.py` | Gerenciar o ciclo da sessão Playwright e a evidência por item. |
| `src/pages/login_page.py` | Encapsular autenticação, locators e waits. |
| `src/pages/form_page.py` | Encapsular o formulário, a confirmação e a captura visual. |
| `src/maestro_client.py` | Adaptar DataPool, alertas, artefatos e task. |
| `src/vault_client.py` | Recuperar e validar a credencial somente em memória. |

Detalhes e diagramas de sequência estão em
[`docs/ARQUITETURA.md`](docs/ARQUITETURA.md).

## Fluxo de execução

1. `bot.py` carrega o ambiente e os argumentos opcionais do Runner.
2. `Settings.validate()` valida configuração, caminhos e timeout.
3. A ausência de `dados_entrada/` causa falha imediata e alerta no Maestro.
4. O Vault é validado antes da criação ou do consumo de itens.
5. Quando habilitada, a sessão Playwright inicia em modo headless e
   `LoginPage.fazer_login()` utiliza a credencial recuperada.
6. O Dispatcher publica o CSV no DataPool.
7. O Performer obtém um item e aplica RN01–RN07.
8. `FormPage.preencher_lote()` apresenta o resultado do item na aplicação
   controlada e aguarda a confirmação.
9. Uma captura `aprovado-*`, `reprovado-*`, `divergencia-*` ou `erro-*` é
   produzida.
10. `resultado_validacao`, `evidencia` e `mensagem_resultado` são atualizados no
    DataPool antes de `report_done` ou `report_error`.
11. O loop continua até o fim da fila.
12. O resumo e o PDF são publicados, e a task é finalizada.
13. Página, navegador e runtime Playwright são encerrados em `finally`.

Não existem `sleep()` para sincronização da interface. A camada web aguarda
condições explícitas de visibilidade, disponibilidade e confirmação.

## Regras de validação

| Regra | Comportamento |
|---|---|
| RN01 | Reconhece somente os campos oficiais do lote e os três campos operacionais de saída. |
| RN02 | Exige todos os campos de entrada, exceto `observacao`. |
| RN03 | Confirma que `lote_id` pertence a `REFERENCE_LOTES`. |
| RN04 | Aceita como estados finais apenas `APROVADO` e `REPROVADO`. |
| RN05 | Normaliza `OK` para `APROVADO` e `NOK` para `REPROVADO`. |
| RN06 | Encaminha estados ambíguos para revisão humana. |
| RN07 | Exige observação quando o lote está reprovado. |

As regras permanecem em `src/validation.py`. Os Page Objects apenas representam
a interface e não decidem o resultado do negócio.

### Validação RN01-RN12 para relatórios

`src/excel_reporting/` contém a implementação de leitura e consolidação de planilhas. Ele produz `RegistroValidado`, aceita `PENDENTE` e acumula todas as regras violadas antes de atribuir uma única classificação.

A precedência é `Erro de Entrada > Divergência > Ambíguo > Válido`. Esse
serviço não é importado pelo Performer e não altera as RN01-RN07 aplicadas ao
DataPool.

## Resultados por item

| `resultado_validacao` | Finalização | Evidência |
|---|---|---|
| `APROVADO` | `report_done` | `artefatos/aprovado-<lote>-<timestamp>.png` |
| `REPROVADO` | `report_done` | `artefatos/reprovado-<lote>-<timestamp>.png` |
| `DIVERGENCIA` | erro de negócio | `artefatos/divergencia-<lote>-<timestamp>.png` |
| `REVISAO` | erro de negócio com motivo de revisão | `artefatos/divergencia-<lote>-<timestamp>.png` |
| `ERRO` | erro de sistema | `artefatos/erro-<lote>-<timestamp>.png`, quando a captura for possível |

`REPROVADO` é um resultado final válido das regras RN01–RN07. Ele não é
contabilizado como divergência nem como falha da automação.

O caminho gravado no DataPool, no log e no resumo é relativo à raiz do projeto,
o que evita referências específicas de uma máquina ou Runner.

## Estrutura do projeto

```text
.
├── .github/workflows/ci.yml
├── artefatos/                     # PNG e PDF gerados em runtime
├── dados_entrada/
│   ├── lotes_auditoria.csv
│   └── inspecao_lotes_10dias.xlsx  # workbook de 10 dias (Aula 22)
├── docs/
│   ├── ADERENCIA_PAGE_OBJECTS.md
│   ├── ARQUITETURA.md
│   ├── DEPLOY_BOTCITY.md
│   ├── EXECUCAO_E2E_DOCKER_CI.md
│   ├── RELATORIO_EXCEL_AULA22.md
│   ├── RELEASE_V1.6.0.md
│   ├── REVISAO_BPMN_PDD.md
│   ├── ROTEIRO_APRESENTACAO_AULA22.md
│   ├── ROTEIRO_DEMONSTRACAO.md
│   ├── diagrama_pdd.bpmn
│   └── diagrama_pdd.svg
├── logs/                          # JSON Lines gerado em runtime
├── relatorios/                    # JSON, PDF e XLSX gerados em runtime
├── scripts/
│   └── build_botcity_package.py
├── src/
│   ├── excel_reporting/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── report_writer.py
│   │   ├── service.py
│   │   ├── validation_service.py
│   │   └── workbook_reader.py
│   ├── pages/
│   │   ├── login_page.py
│   │   └── form_page.py
│   ├── bot.py
│   ├── config.py
│   ├── dispatcher.py
│   ├── logging_config.py
│   ├── maestro_client.py
│   ├── main.py
│   ├── models.py
│   ├── reporting.py
│   ├── validation.py
│   ├── vault_client.py
│   └── web_automation.py
├── tests/
│   └── e2e/                       # cenários reais com pytest-playwright
├── web/index-lotes/               # aplicação controlada
├── .env.example
├── bot.py
├── gerar_relatorio.py             # entry point do relatório Excel
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
└── requirements-report.txt        # dependências do relatório Excel
```

`.env`, logs, relatórios, PNG, pacotes e caches não são versionados. Os
diretórios operacionais mantêm somente seus arquivos `.gitkeep`.

## Pré-requisitos

- Python 3.10 ou superior;
- Git;
- Chromium fornecido pelo Playwright ou instalado no ambiente;
- para integração real, workspace e Runner ativos no BotCity Maestro.

O ambiente do Maestro deve possuir:

- DataPool `FilaAuditoriaLotes2`;
- credencial `credencial_erp2`;
- permissão para alertas, artefatos e finalização de tasks.

## Instalação

```bash
git clone https://github.com/g-f307/conferencia-de-lotes.git
cd conferencia-de-lotes
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m playwright install --with-deps --only-shell chromium
cp .env.example .env
```

No PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m playwright install --only-shell chromium
Copy-Item .env.example .env
```

`requirements-dev.txt` instala `pytest-playwright`. O comando seguinte instala
o Chromium Headless Shell usado pelos testes; `--with-deps` também prepara as
bibliotecas do sistema em distribuições Linux compatíveis. A instalação do
bundle é dispensável quando `PLAYWRIGHT_CHROMIUM_PATH` aponta para um Chromium
compatível já instalado.

## Variáveis de ambiente

| Variável | Finalidade | Padrão |
|---|---|---|
| `MAESTRO_ENABLED` | Ativa o gateway BotCity. | `false` |
| `VAULT_ENABLED` | Exige o Credentials Vault. | `false` |
| `MAESTRO_SERVER` | URL do workspace fora do Runner. | vazio |
| `MAESTRO_LOGIN` | Login técnico fora do Runner. | vazio |
| `MAESTRO_KEY` | Chave técnica fora do Runner. | vazio |
| `MAESTRO_TASK_ID` | Task controlada fora do Runner. | vazio |
| `BOT_ID` | Identificador da automação. | `bot-conferencia-de-lotes-v2` |
| `EXECUTION_ID` | Correlação dos logs. | `execucao-local` |
| `DATAPOOL_LABEL` | Nome da fila. | `FilaAuditoriaLotes2` |
| `VAULT_LABEL` | Nome da credencial. | `credencial_erp2` |
| `REFERENCE_LOTES` | IDs de referência separados por vírgula. | `L001,L002` |
| `INPUT_DIR` | Diretório validado no fail-fast. | `dados_entrada` |
| `INPUT_CSV` | Massa publicada pelo Dispatcher. | `dados_entrada/lotes_auditoria.csv` |
| `LOG_FILE` | Log JSON Lines. | `logs/execucao.log` |
| `REPORT_DIR` | Resumo e PDF. | `relatorios` |
| `PROCESSING_DELAY_SECONDS` | Atraso de demonstração após aprovação. | `0` |
| `WEB_AUTOMATION_ENABLED` | Ativa a sessão Playwright. | `false` local |
| `WEB_TEST_URL` | Aplicação controlada. | `web/index-lotes/index.html` |
| `WEB_ARTIFACT_DIR` | Capturas por item. | `artefatos` |
| `WEB_TIMEOUT_SECONDS` | Timeout dos waits por condição. | `15` |
| `PLAYWRIGHT_CHROMIUM_PATH` | Chromium explícito do Runner. | vazio |

Caminhos relativos são resolvidos a partir da raiz do projeto. A senha do ERP
não é uma variável de ambiente deste projeto.

## Credentials Vault

Crie o label `credencial_erp2` com as chaves:

```text
username
password
```

A ausência da credencial, do usuário ou da senha interrompe o fluxo antes da
publicação e do processamento dos itens. Somente o nome do usuário pode aparecer
no log.

## DataPool

Crie `FilaAuditoriaLotes2` com os onze campos de texto:

```text
lote_id
produto
linha
turno
status
responsavel
data
observacao
resultado_validacao
evidencia
mensagem_resultado
```

Os oito primeiros são entradas. Os três últimos são inicializados vazios pelo
Dispatcher e preenchidos pelo Performer antes da finalização individual.

## Execução local

Sem navegador:

```bash
MAESTRO_ENABLED=false \
VAULT_ENABLED=false \
WEB_AUTOMATION_ENABLED=false \
PROCESSING_DELAY_SECONDS=0 \
python bot.py
```

Com Playwright e evidências por item:

```bash
MAESTRO_ENABLED=false \
VAULT_ENABLED=false \
WEB_AUTOMATION_ENABLED=true \
PROCESSING_DELAY_SECONDS=0 \
python bot.py
```

A execução local usa gateway em memória e credencial efêmera. Ao final,
verifique:

```text
logs/execucao.log
relatorios/resumo_execucao.json
relatorios/relatorio_evidencias.pdf
artefatos/*.png
```

## Docker

```bash
mkdir -p logs relatorios artefatos
docker compose build
WEB_AUTOMATION_ENABLED=true docker compose run --rm conferencia-de-lotes
```

Em Linux, quando o usuário do host não possui UID/GID `1000`, exporte os IDs
antes da execução para preservar a propriedade dos arquivos:

```bash
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
```

A imagem instala somente o Chromium Headless Shell gerenciado pelo Playwright
em `/ms-playwright`. O Compose monta `logs/`, `relatorios/` e `artefatos/` no
host; os arquivos gerados permanecem disponíveis depois que o container é
removido.

## BotCity Runner

O Runner invoca:

```text
bot.py <maestro-server> <task-id> <token>
```

Nesse contexto, Maestro, Vault e automação web ficam ativos por padrão, salvo
configuração explícita de contingência. O token recebido não é registrado.

Gere o pacote:

```bash
python scripts/build_botcity_package.py --version 2
unzip -l dist/bot-conferencia-de-lotes-v2.zip
```

O ZIP contém somente o necessário para execução:

```text
bot.py
requirements.txt
src/
dados_entrada/
web/index-lotes/
```

O procedimento completo está em
[`docs/DEPLOY_BOTCITY.md`](docs/DEPLOY_BOTCITY.md).

## Logs, resumo e evidências

Cada linha de `logs/execucao.log` é um objeto JSON independente, com
`timestamp`, `level`, `execution_id`, `bot_id`, `evento`, `ambiente`, `usuario`
e `detalhes`.

Eventos relevantes:

| Evento | Finalidade |
|---|---|
| `VALIDACAO_VAULT` | Confirma a disponibilidade da credencial. |
| `PLAYWRIGHT_AMBIENTE` | Registra engine, caminho e versão do navegador. |
| `INICIO_PLAYWRIGHT` / `FIM_PLAYWRIGHT` | Delimitam a sessão web. |
| `INICIO_ITEM` / `RESULTADO_ITEM` | Delimitam o processamento do lote. |
| `EVIDENCIA_ITEM` | Relaciona a captura ao item. |
| `ERRO_WEB_ITEM` | Registra falha isolada da interação web. |
| `PUBLICACAO_RESULTADOS` | Confirma JSON e PDF. |
| `ENCERRAMENTO` | Confirma sucesso operacional. |

`resumo_execucao.json` inclui total, aprovados, divergências, revisões,
erros técnicos e a lista de caminhos das evidências. O PDF e o JSON são
publicados como artefatos da task.

## Relatório executivo Excel (Aula 22)

O módulo `src/excel_reporting/` implementa um fluxo independente que lê o
workbook de inspeção, aplica RN01–RN12, classifica os 250 registros e gera um
relatório formatado com dashboard nativo do Excel.

Esse fluxo não substitui a automação Playwright/DataPool. Ele opera como uma
camada analítica paralela para consolidação gerencial.

### Instalação das dependências

```bash
python -m pip install -r requirements-report.txt
```

### Execução

```bash
python gerar_relatorio.py
```

Argumentos opcionais:

```bash
python gerar_relatorio.py --entrada dados_entrada/inspecao_lotes_10dias.xlsx \
                          --saida relatorios/relatorio_conferencia_lotes.xlsx \
                          --log logs/execucao_relatorio.log
```

### Saídas

```text
relatorios/relatorio_conferencia_lotes.xlsx   # relatório com 6 abas
logs/execucao_relatorio.log                   # log da execução
artefatos/dashboard_resumo.pdf                # evidência opcional, exportada manualmente
```

O comando gera automaticamente o XLSX e o log. Quando necessária para a
entrega, a evidência em PDF deve ser exportada manualmente a partir da área de
impressão da aba `Resumo`. Esses arquivos não devem ser versionados.

### Estrutura das seis abas

| Aba | Conteúdo |
|---|---|
| `Resumo` | Indicadores KPI (total, válidos, divergências, ambíguos, erros de entrada), percentuais, gráfico de rosca com as quatro classificações e gráfico de linha com a evolução diária dos problemas. |
| `Todos` | Os 250 registros consolidados com classificação e motivo detalhado. |
| `Válidos` | Registros aprovados sem violações. |
| `Divergências` | Registros com divergência de referência, produto ou status. |
| `Ambíguos` | Registros com status não reconhecido, encaminhados à revisão. |
| `Erros de Entrada` | Registros com campos obrigatórios ausentes ou estrutura inválida. |

### Classificações

Cada registro recebe exatamente uma classificação final, determinada pela
precedência:

```text
Erro de Entrada > Divergência > Ambíguo > Válido
```

Um registro com múltiplas regras violadas recebe a classificação de maior
prioridade. No modelo interno, as regras ficam em `regras_violadas`; no XLSX,
elas são apresentadas na coluna `Motivo`.

### Deduplicação diária (RN11)

A regra RN11 identifica duplicatas pela chave `(aba_origem, lote_id)`. Dentro
de cada aba diária, somente a primeira ocorrência de cada lote é preservada;
as demais são marcadas como duplicatas.

### Indicadores e gráficos

- **Gráfico de rosca**: distribuição percentual das quatro classificações.
- **Gráfico de evolução**: linha temporal com o número de problemas
  (divergências + ambíguos + erros) por dia ao longo das 10 abas.

A documentação completa, incluindo solução de problemas e perguntas da banca,
está em [`docs/RELATORIO_EXCEL_AULA22.md`](docs/RELATORIO_EXCEL_AULA22.md).

## Testes e integração contínua

As validações possuem responsabilidades diferentes:

| Camada | Comando local | Finalidade |
|---|---|---|
| Qualidade | `python -m ruff check --select E4,E7,E9,F bot.py src tests scripts` | Erros estáticos e imports inválidos. |
| Unitários e integração | `python -m pytest -q --ignore=tests/e2e` | Regras e componentes sem abrir navegador. |
| E2E | `python -m pytest tests/e2e/ -q` | Formulário real em Chromium headless. |
| Suíte completa | `python -m pytest -q` | Testes Python, incluindo E2E. |
| Smoke test Docker | `WEB_AUTOMATION_ENABLED=true docker compose run --rm conferencia-de-lotes` | Imagem, navegador e persistência das saídas. |

```bash
python -m ruff check --select E4,E7,E9,F bot.py src tests scripts
python -m pytest -q --ignore=tests/e2e
python -m pytest tests/e2e/ -q
python -m pytest -q
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

O workflow `.github/workflows/ci.yml`, acionado em Pull Requests e pushes para
`main`, executa a cadeia `lint -> tests -> test-e2e -> build-docker`. O último
job usa massa e credencial efêmera controladas, verifica log, resumo JSON,
relatório PDF e screenshots e publica os artefatos `screenshots-e2e`,
`relatorios-docker` e `screenshots-docker` por sete dias.

Para baixá-los, abra **Actions**, selecione a execução do workflow **CI** e use
a seção **Artifacts** ao final da página. O procedimento completo e as
limitações conhecidas estão em
[`docs/EXECUCAO_E2E_DOCKER_CI.md`](docs/EXECUCAO_E2E_DOCKER_CI.md).

## Limitações conhecidas

- os testes web usam a aplicação local controlada, não um ERP real;
- a CI valida o gateway em memória e não acessa BotCity Maestro ou Vault;
- os artefatos do GitHub Actions possuem retenção temporária de sete dias.

## Tratamento de erros

| Categoria | Comportamento |
|---|---|
| Configuração ou entrada | Falha antes da fila. |
| Vault ou login inicial | Falha antes da publicação dos itens. |
| Divergência RN01–RN07 | Item finalizado como erro de negócio; fila continua. |
| Revisão humana | Item separado com motivo; fila continua. |
| Timeout ou falha web de um item | Captura de erro, saída `ERRO` e fila continua. |
| Falha ao obter o próximo item | Falha fatal, pois não há item seguro para atualizar. |

Uma execução com divergências pode resultar em `PARTIALLY_COMPLETED` e ainda ser
finalizada no Maestro como sucesso operacional.

## Segurança

- `.env` real nunca é versionado ou empacotado;
- a senha existe somente no Vault ou na credencial efêmera local;
- logs sanitizam senha, token, chave e API key;
- capturas usam somente a aplicação e a massa controladas;
- imagens e pacotes não recebem credenciais durante o build;
- logs, relatórios, PNG e `dist/` permanecem fora do Git.

## Documentação complementar

| Documento | Finalidade |
|---|---|
| [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) | Componentes, sequência e limites. |
| [`docs/EXECUCAO_E2E_DOCKER_CI.md`](docs/EXECUCAO_E2E_DOCKER_CI.md) | Instalação, testes E2E, Docker, pipeline e artefatos. |
| [`docs/REVISAO_BPMN_PDD.md`](docs/REVISAO_BPMN_PDD.md) | Aderência do processo e das regras. |
| [`docs/ADERENCIA_PAGE_OBJECTS.md`](docs/ADERENCIA_PAGE_OBJECTS.md) | Matriz técnica da entrega. |
| [`docs/DEPLOY_BOTCITY.md`](docs/DEPLOY_BOTCITY.md) | Implantação, smoke test e rollback. |
| [`docs/ROTEIRO_DEMONSTRACAO.md`](docs/ROTEIRO_DEMONSTRACAO.md) | Roteiro objetivo da demonstração. |
| [`docs/EVOLUCAO_AUTOMACAO_WEB.md`](docs/EVOLUCAO_AUTOMACAO_WEB.md) | Histórico e comparação entre Selenium e Playwright. |
| [`docs/RELATORIO_EXCEL_AULA22.md`](docs/RELATORIO_EXCEL_AULA22.md) | Documentação completa do relatório Excel e perguntas da banca. |
| [`docs/ROTEIRO_APRESENTACAO_AULA22.md`](docs/ROTEIRO_APRESENTACAO_AULA22.md) | Roteiro de apresentação de cinco minutos. |
| [`docs/RELEASE_V1.3.0.md`](docs/RELEASE_V1.3.0.md) | Notas da versão Selenium com Page Objects. |
| [`docs/RELEASE_V1.4.0.md`](docs/RELEASE_V1.4.0.md) | Notas e checklist da candidata Playwright. |
| [`docs/RELEASE_V1.6.0.md`](docs/RELEASE_V1.6.0.md) | Notas e checklist da entrega Excel (Aula 22). |

## Equipe

Projeto acadêmico desenvolvido por Gabriel Fernandes, Marcelo Uchôa e Rebecca
Xavier.

## Releases

| Release | Tecnologia | Marco |
|---|---|---|
| `v1.0.0` | Sem integração web final | Primeira versão implantável no BotCity Maestro. |
| `v1.1.0` | Playwright inicial | Consolidação do fluxo corporativo. |
| `v1.2.0` | Selenium | Automação homologada no Runner. |
| [`v1.3.0`](docs/RELEASE_V1.3.0.md) | Selenium com Page Objects | Separação da interface e do orquestrador. |
| [`v1.4.0`](docs/RELEASE_V1.4.0.md) | Playwright com Page Objects | DataPool e evidências rastreáveis por item. |
| [`v1.6.0`](docs/RELEASE_V1.6.0.md) | Playwright com Relatório Excel | Dashboard Excel integrado e evidências da Aula 22. |

## Licença

Este repositório não possui licença de uso definida. O código e os materiais
devem ser utilizados conforme as orientações da atividade acadêmica.
