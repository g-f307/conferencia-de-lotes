# Conferência de Lotes

Automação para auditoria de registros de inspeção de lotes, desenvolvida em Python e preparada para integração com o ecossistema BotCity Maestro. O projeto organiza a entrada em uma fila do DataPool, aplica regras de negócio por item, separa exceções para revisão humana e mantém evidências técnicas da execução.

## Visão geral

O processo recebe registros de inspeção sujeitos a inconsistências de preenchimento e status. A solução divide o processamento em dois componentes:

1. **Dispatcher:** lê um arquivo CSV e publica uma entrada por linha no DataPool `FilaAuditoriaLotes2`.
2. **Performer:** consome os itens da fila, recupera a credencial do ERP, aplica as regras RN01–RN07 e reporta o resultado individual de cada lote.

O desenho considera resiliência por item: uma inconsistência de negócio não interrompe o processamento dos demais registros.

## Objetivo

Padronizar e tornar rastreável a conferência de lotes, reduzindo retrabalho causado por campos ausentes, status inválidos, lotes sem referência e reprovações sem justificativa.

Os objetivos técnicos são:

- eliminar caminhos fixos e configurações sensíveis do código;
- falhar imediatamente quando a estrutura mínima de entrada não existir;
- manter logs locais com data, hora e severidade;
- distribuir o processamento pelo DataPool do Maestro;
- recuperar credenciais por uma abstração de Vault, sem registrar a senha;
- distinguir erros de negócio, falhas de sistema e casos de revisão humana;
- produzir um resumo serializável da execução;
- permitir testes locais sem conexão ou credenciais reais do Maestro.

## Escopo implementado

- configuração por variáveis de ambiente;
- resolução de caminhos relativos à raiz do projeto;
- validação fail-fast da pasta `dados_entrada/`;
- logs locais em `logs/execucao.log`;
- saída padronizada por `ExecutionResult`;
- leitura de CSV por cabeçalho;
- publicação de uma entrada por linha no DataPool;
- gateway local em memória para desenvolvimento e testes;
- gateway real com `BotMaestroSDK`, `DataPoolEntry`, alertas e artefatos;
- associação dos itens a um `task_id` válido;
- consumo resiliente pelo Performer;
- regras RN01–RN07;
- normalização de `OK` e `NOK`;
- separação de status ambíguos para revisão humana;
- abstração de acesso à credencial `credencial_erp2`;
- testes unitários e de integração entre os módulos.

## Fora do escopo atual

- leitura direta de arquivos XLSX pelo Dispatcher;
- download automático de anexos de e-mail;
- navegação ou lançamento de dados em um ERP real;
- implementação concreta do provedor BotCity Credentials Vault;
- tela ou formulário para tratamento dos casos de revisão humana;
- atualização automática da base de referência de lotes;
- implantação e agendamento em ambiente produtivo.

O arquivo `bot.py` executa o ciclo principal em `src/main.py`: valida a configuração, publica o CSV no DataPool, consome os itens, aplica as regras de negócio e publica o resumo da execução como artefato.

## Processo de negócio

![Diagrama BPMN do processo de inspeção de lotes](docs/diagrama_pdd.svg)

O arquivo-fonte editável está disponível em [`docs/diagrama_pdd.bpmn`](docs/diagrama_pdd.bpmn). Os demais documentos de levantamento e evidências permanecem na pasta `docs/`.

## Regras de validação

| Regra | Comportamento implementado |
|---|---|
| RN01 | Exige exatamente as colunas `lote_id`, `produto`, `linha`, `turno`, `status`, `responsavel`, `data` e `observacao`. |
| RN02 | Exige preenchimento de todos os campos, exceto `observacao`. |
| RN03 | Verifica se `lote_id` pertence à base de referência informada ao Performer. |
| RN04 | Aceita como estados finais `APROVADO` e `REPROVADO`. |
| RN05 | Normaliza `OK` para `APROVADO` e `NOK` para `REPROVADO`. |
| RN06 | Encaminha `PENDENTE`, `EM ANALISE`, `A REVISAR` e `REVISAO` para revisão humana. |
| RN07 | Exige observação quando o status final é `REPROVADO`. |

Erros RN01, RN02, RN03, RN04 e RN07 são tratados como erros de negócio. RN06 gera uma pendência de revisão humana. Exceções técnicas inesperadas são classificadas como erros de sistema.

## Arquitetura

```text
CSV
 └── Dispatcher
      └── MaestroClient
           ├── InMemoryMaestroGateway
           └── BotCityMaestroGateway
                └── FilaAuditoriaLotes2
                     └── LotePerformer
                          ├── VaultClient
                          ├── RN01–RN07
                          └── resultado por item
```

Os módulos de domínio não dependem diretamente do SDK. Protocolos e adaptadores isolam DataPool, alertas e credenciais, permitindo substituir integrações reais por objetos controlados nos testes.

## Estrutura do repositório

```text
.
├── bot.py                         # entry point atual
├── dados_entrada/                 # arquivos recebidos para processamento
├── docs/
│   ├── DEPLOY_BOTCITY.md          # roteiro de deploy no BotCity Maestro
│   ├── GUIA_COLABORACAO_GIT.md    # roteiro Git/GitHub da equipe
│   ├── diagrama_pdd.bpmn          # fonte BPMN
│   └── diagrama_pdd.svg           # visualização do processo
├── logs/                          # logs locais; arquivos .log não são versionados
├── scripts/
│   └── build_botcity_package.py    # gera o zip de deploy BotCity
├── src/
│   ├── bot.py                     # Performer e resultado por lote
│   ├── config.py                  # variáveis de ambiente e caminhos
│   ├── dispatcher.py              # CSV para DataPool
│   ├── logging_config.py          # configuração do log local
│   ├── maestro_client.py          # gateways local e BotCity
│   ├── main.py                    # configuração e fail-fast
│   ├── models.py                  # ExecutionResult
│   ├── validation.py              # RN01–RN07
│   └── vault_client.py            # contrato de credenciais do ERP
├── tests/                         # testes automatizados
├── .env.example                   # modelo de configuração sem segredos
├── requirements.txt               # dependências de execução
└── requirements-dev.txt           # dependências de desenvolvimento
```

## Requisitos

- Python 3.10 ou superior;
- acesso ao BotCity Maestro para operações reais;
- DataPool previamente criado;
- credencial técnica do workspace Maestro;
- `task_id` fornecido pelo Runner ou configurado para desenvolvimento.

## Preparação do ambiente local

Clone o repositório e entre no diretório:

```bash
git clone https://github.com/g-f307/conferencia-de-lotes.git
cd conferencia-de-lotes
```

Crie e ative um ambiente virtual:

```bash
python -m venv .venv
source .venv/bin/activate
```

No Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Instale as dependências:

```bash
python -m pip install -r requirements-dev.txt
```

Crie a configuração local:

```bash
cp .env.example .env
```

Crie as pastas operacionais, caso ainda não existam:

```bash
mkdir -p dados_entrada logs relatorios
```

## Configuração

| Variável | Finalidade | Exemplo seguro |
|---|---|---|
| `MAESTRO_ENABLED` | Seleciona o gateway real do Maestro. | `false` |
| `VAULT_ENABLED` | Indica uso obrigatório do Vault quando o Maestro está ativo. | `false` |
| `MAESTRO_SERVER` | Endereço do workspace Maestro. | vazio no repositório |
| `MAESTRO_LOGIN` | Identificador técnico do workspace. | vazio no repositório |
| `MAESTRO_KEY` | Chave técnica do workspace. | vazio no repositório |
| `MAESTRO_TASK_ID` | Task usada em execução local; o Runner fornece a sua própria. | vazio no repositório |
| `DATAPOOL_LABEL` | Fila de auditoria. | `FilaAuditoriaLotes2` |
| `VAULT_LABEL` | Label da credencial do ERP. | `credencial_erp2` |
| `INPUT_DIR` | Diretório de entrada. | `dados_entrada` |
| `LOG_FILE` | Arquivo de log. | `logs/execucao.log` |
| `REPORT_DIR` | Diretório dos relatórios JSON. | `relatorios` |
| `WEB_AUTOMATION_ENABLED` | Habilita o preenchimento do formulário web de teste. | `false` |
| `WEB_TEST_URL` | URL HTTP, `file://` ou caminho local da página de teste. | `docs/index-lotes/index.html` |
| `WEB_ARTIFACT_DIR` | Diretório das evidências visuais da automação web. | `artefatos` |

O `.env` não deve ser versionado. A senha do ERP não pertence ao `.env` nem ao código; deve ser recuperada pelo provedor de credenciais em tempo de execução.

## Execução local

Com `MAESTRO_ENABLED=false`, execute o ciclo local completo usando o gateway em memória:

```bash
python bot.py
```

Com a pasta `dados_entrada/` e o CSV configurado disponíveis, o comando publica os itens no gateway local, processa a fila e gera `relatorios/resumo_execucao.json`. Se a pasta estiver ausente, encerra com código diferente de zero e registra um erro.

O Dispatcher e o Performer também podem ser consumidos programaticamente pelas funções e classes `dispatch_csv` e `LotePerformer`.

A execução real no Maestro exige `MAESTRO_ENABLED=true`, configuração técnica válida, DataPool existente e `task_id` não vazio.

## Automação web com Playwright

A automação web é opcional e permanece desabilitada por padrão. Instale o
navegador usado pelo Playwright depois das dependências Python:

```bash
python -m playwright install chromium
```

Configure no `.env`:

```dotenv
WEB_AUTOMATION_ENABLED=true
WEB_TEST_URL=docs/index-lotes/index.html
WEB_ARTIFACT_DIR=artefatos
```

`WEB_TEST_URL` aceita uma URL HTTP, uma URL `file://` ou um caminho relativo à
raiz do projeto. Para testar a página local sem acessar o Maestro:

```bash
MAESTRO_ENABLED=false VAULT_ENABLED=false PROCESSING_DELAY_SECONDS=0 python bot.py
```

O módulo abre a página, preenche o número do lote, seleciona produto e status,
aciona o botão e aguarda a confirmação visível. Em seguida, salva em
`artefatos/` um screenshot focado na mensagem de confirmação, identificado pelo
lote e pelo horário da execução. Se a confirmação não aparecer dentro do tempo
do Playwright, a execução informa claramente o lote afetado. Quando
`WEB_AUTOMATION_ENABLED=false`, nenhuma instância de navegador é criada e o
fluxo original permanece inalterado.

## Execução com Docker

Para construir a imagem localmente:

```bash
docker build -t conferencia-de-lotes:local .
```

Para executar o fluxo local com Docker Compose:

```bash
mkdir -p logs relatorios artefatos
docker compose up --build --abort-on-container-exit
```

Para executar uma rodada pontual do bot:

```bash
docker compose run --rm conferencia-de-lotes
```

O Compose monta `dados_entrada/` como somente leitura e persiste no host os
arquivos criados em `logs/`, `relatorios/` e `artefatos/`. A execução local
desabilita Maestro e Vault e reduz o atraso entre itens para zero. Para testar o
preenchimento web dentro do container, execute com `WEB_AUTOMATION_ENABLED=true`.
Por padrão, o container usa UID e GID `1000`; em outro ambiente Linux, informe
os identificadores do usuário local:

```bash
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) docker compose up --build --abort-on-container-exit
```

Para remover o container após a execução:

```bash
docker compose down
```

O `.env` não faz parte do contexto de build. Em uma execução integrada, forneça
as configurações por variáveis do ambiente de implantação ou pelos argumentos do
BotCity Runner. Nunca adicione chaves, tokens ou senhas ao `Dockerfile` ou ao
`docker-compose.yml`.

## Integração contínua

O workflow [`.github/workflows/ci.yml`](.github/workflows/ci.yml) é executado em
pushes e pull requests destinados à `main`. Ele instala as dependências, executa
a suíte com `pytest` e também confirma que a imagem Docker pode ser construída.
O workflow utiliza apenas o modo de teste e não depende de credenciais do Maestro.

## Pacote de deploy BotCity

O BotCity Runner espera um bot Python customizado com `bot.py` e `requirements.txt` no pacote. Gere o zip de deploy com:

```bash
python scripts/build_botcity_package.py --version 0.1.0
```

O arquivo será criado em `dist/bot-conferencia-de-lotes-v1.zip`. O roteiro operacional completo está em [`docs/DEPLOY_BOTCITY.md`](docs/DEPLOY_BOTCITY.md).

## Configuração no BotCity Maestro

### DataPool

Crie o DataPool `FilaAuditoriaLotes2` com os seguintes campos de texto:

```text
lote_id
produto
linha
turno
status
responsavel
data
observacao
```

O gateway publica itens com `DataPoolEntry`, consome usando o `task_id` e finaliza cada entrada com sucesso ou erro de negócio/sistema.

### Credentials Vault

Crie uma credencial com o label:

```text
credencial_erp2
```

O contrato atual espera um provedor que retorne:

```text
username
password
```

Somente o nome do usuário pode aparecer no log. A senha nunca deve ser impressa, persistida em relatório ou adicionada ao repositório.

## Testes

Execute a suíte completa:

```bash
python -m pytest
```

Execute com relatório de cobertura:

```bash
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

Na versão documentada, a suíte contém 66 testes. Os testes usam gateways e provedores controlados; nenhuma credencial real é necessária.

## Logs e evidências

Os logs seguem o formato:

```text
AAAA-MM-DD HH:MM:SS | SEVERIDADE | logger | mensagem
```

Arquivos `.log`, `.env`, ambientes virtuais e relatórios gerados não são versionados. O gateway Maestro suporta:

- alerta informativo de início;
- alerta de erro no fail-fast;
- postagem do resumo JSON como artefato;
- estado individual dos itens no DataPool.

## Segurança

- não registrar senhas ou tokens;
- não usar caminhos absolutos no código;
- manter `.env` fora do Git;
- usar Vault para a credencial do ERP;
- usar gateway em memória apenas em desenvolvimento e testes;
- rejeitar operações dependentes de task quando `task_id` estiver vazio ou igual a zero;
- revisar toda alteração por Pull Request.

## Colaboração e versionamento

O projeto utiliza GitHub Flow: Issue, branch, commits pequenos, Pull Request, revisão cruzada e squash merge. O roteiro completo está em [`docs/GUIA_COLABORACAO_GIT.md`](docs/GUIA_COLABORACAO_GIT.md).

Responsabilidades iniciais:

| Integrante | Área principal |
|---|---|
| Gabriel | configuração, logs, fail-fast e resultado de execução |
| Marcelo | Dispatcher, DataPool, alertas e artefatos Maestro |
| Rebecca | validações, Performer e abstração do Vault |

## Documentação de referência

- [`docs/diagrama_pdd.bpmn`](docs/diagrama_pdd.bpmn)
- [`docs/diagrama_pdd.svg`](docs/diagrama_pdd.svg)
- [`docs/Regras de validação a aplicar - Gabriel, Marcelo e Rebecca.docx.pdf`](docs/Regras%20de%20validação%20a%20aplicar%20-%20Gabriel,%20Marcelo%20e%20Rebecca.docx.pdf)
- [`docs/Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx`](docs/Inspeção%20de%20Lotes%20-%20Gabriel,%20Marcelo%20e%20Rebecca.xlsx)
- [`docs/index_lotes (1).html`](docs/index_lotes%20(1).html)

## Equipe

- Gabriel Fernandes
- Marcelo Uchôa
- Rebecca Xavier
