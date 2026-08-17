# Execução E2E, Docker e integração contínua

Este guia consolida os procedimentos técnicos e operacionais das atividades
19-X e 20-X. Os comandos partem da raiz do repositório e usam somente a
aplicação controlada em `web/index-lotes/`, sem acesso a ERP, DataPool ou
credenciais reais.

## Preparação local

Crie o ambiente e instale as dependências de desenvolvimento:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
cp .env.example .env
```

`requirements-dev.txt` inclui as dependências de produção, `pytest`,
`pytest-playwright`, cobertura e Ruff. Em Linux, instale o Chromium Headless
Shell e as bibliotecas do sistema com:

```bash
python -m playwright install --with-deps --only-shell chromium
```

No PowerShell, instale o navegador sem a etapa de pacotes Linux:

```powershell
python -m playwright install --only-shell chromium
```

Quando o host ou o BotCity Runner já possuir um Chromium homologado, defina
`PLAYWRIGHT_CHROMIUM_PATH` com o caminho absoluto do executável. Sem essa
variável, a automação procura executáveis em caminhos conhecidos e, se nenhum
estiver disponível, Playwright utiliza o navegador que gerencia em cache.

## Camadas de teste

| Camada | Abre navegador | Ambiente | Objetivo |
|---|---|---|---|
| Qualidade | não | Python local | detectar erros estáticos com Ruff |
| Unitários e integração | não | Python local | validar regras, configuração e componentes |
| E2E | sim | Chromium headless local | validar o formulário por meio de locators reais |
| Smoke test Docker | sim | imagem construída | validar empacotamento, execução e saídas persistidas |

Execute somente os testes sem navegador:

```bash
python -m pytest -q --ignore=tests/e2e
```

Execute exclusivamente os testes E2E:

```bash
python -m pytest tests/e2e/ -q
```

Para preservar localmente a captura produzida pelo cenário de evidência:

```bash
python -m pytest tests/e2e/ -q --basetemp=e2e-artifacts
find e2e-artifacts -type f -name '*.png' -size +0c
```

Execute a suíte completa, incluindo os testes E2E:

```bash
python -m pytest -q
```

Os cenários E2E abrem `web/index-lotes/index.html` por URI `file://`, portanto
não exigem servidor HTTP. Eles verificam título, campos, seleção, validações,
mensagem de sucesso e geração de PNG não vazio.

## Execução com Docker Compose

Prepare os diretórios persistidos e construa a imagem:

```bash
mkdir -p logs relatorios artefatos
docker compose build
```

Em Linux, exporte o usuário do host quando ele não possuir UID/GID `1000`:

```bash
export LOCAL_UID="$(id -u)"
export LOCAL_GID="$(id -g)"
```

Execute o bot com Playwright real no container:

```bash
WEB_AUTOMATION_ENABLED=true docker compose run --rm conferencia-de-lotes
```

O Dockerfile instala o Chromium Headless Shell com o Playwright em
`/ms-playwright`. Não é necessário configurar `PLAYWRIGHT_CHROMIUM_PATH` no
Compose.

### Volumes persistidos

| Host | Container | Conteúdo esperado |
|---|---|---|
| `dados_entrada/` | `/app/dados_entrada` | CSV montado como somente leitura |
| `logs/` | `/app/logs` | `execucao.log` em JSON Lines |
| `relatorios/` | `/app/relatorios` | resumo JSON e relatório PDF |
| `artefatos/` | `/app/artefatos` | screenshots PNG por item |

Confira as saídas sem depender da quantidade de itens da massa:

```bash
test -s logs/execucao.log
test -s relatorios/resumo_execucao.json
test -s relatorios/relatorio_evidencias.pdf
find artefatos -type f -name '*.png' -size +0c
```

O container pode terminar com status de negócio `PARTIALLY_COMPLETED` e ainda
retornar código de saída zero quando não houve falha técnica global.

## GitHub Actions

O workflow [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) é acionado
por Pull Requests destinados à `main` e por pushes realizados nela. Os jobs são
sequenciais:

```text
lint
  └── tests
        └── coverage
              └── test-e2e
                    └── build-docker
```

| Job | Ação principal | Saída |
|---|---|---|
| `lint` | executa Ruff | diagnóstico no check da PR |
| `tests` | executa separadamente os markers `unit`, `integration`, `regression` e `e2e` | resultado de cada camada, incluindo razões de `SKIP` e `XFAIL` |
| `coverage` | executa a suíte completa e exige cobertura mínima de 80% | `coverage-report` com XML e HTML navegável |
| `test-e2e` | instala Chromium e executa `tests/e2e/` | `screenshots-e2e` |
| `build-docker` | constrói e executa a imagem com Playwright | `relatorios-docker` e `screenshots-docker` |

O smoke test Docker monta `ci-output/` no container e exige arquivos não
vazios antes de concluir o job:

```text
ci-output/logs/execucao.log
ci-output/relatorios/resumo_execucao.json
ci-output/relatorios/relatorio_evidencias.pdf
ci-output/artefatos/*.png
```

Nenhum secret do repositório é consumido. Maestro e Vault ficam desabilitados,
e os identificadores usados na execução são exclusivos da CI.

### Download dos artefatos

1. Abra a aba **Actions** do repositório.
2. Selecione o workflow **CI** e a execução desejada.
3. Aguarde os cinco jobs ficarem verdes.
4. Na seção **Artifacts**, baixe `coverage-report`, `screenshots-e2e`,
   `relatorios-docker` ou `screenshots-docker`.

Os artefatos ficam disponíveis por sete dias. `coverage-report` contém
`coverage.xml` e o relatório navegável em `htmlcov/index.html`;
`relatorios-docker` contém o log JSON Lines, o resumo JSON e o relatório PDF;
os outros dois pacotes contêm as capturas dos testes E2E e da execução Docker,
respectivamente.

## Arquivos fora do Git

O repositório mantém apenas `.gitkeep` nos diretórios operacionais. A
configuração real e as saídas são ignoradas:

```text
.env
logs/*.log
relatorios/*
artefatos/*.png
ci-output/
test-results/
e2e-artifacts/
.coverage
coverage.xml
htmlcov/
```

Confirme as regras sem adicionar os arquivos ao índice:

```bash
git check-ignore .env logs/execucao.log \
  relatorios/resumo_execucao.json artefatos/evidencia.png \
  ci-output/ e2e-artifacts/
```

## Limitações e pendências

- a aplicação web é local e controlada; os testes não homologam um ERP real;
- a CI usa gateway em memória e credencial efêmera, sem validar Maestro, Vault
  ou permissões do Runner;
- o navegador é executado somente em modo headless;
- a instalação com `--with-deps` depende de uma distribuição Linux suportada e
  de permissão para instalar pacotes do sistema;
- os artefatos do GitHub Actions são temporários e expiram após sete dias;
- o mapeamento de UID/GID descrito para o Compose é específico de hosts Unix;
- o projeto gera `resumo_execucao.json` e `relatorio_evidencias.pdf`. Ainda é
  necessário confirmar com o professor se esses formatos atendem ao requisito
  de relatório ou se um arquivo Excel é obrigatório. Esta documentação não
  considera os formatos equivalentes antes dessa confirmação.

## Diagnóstico rápido

| Sintoma | Verificação |
|---|---|
| Chromium não inicia | reinstale com `python -m playwright install --with-deps --only-shell chromium` |
| Arquivos do Docker sem permissão | confira `LOCAL_UID`, `LOCAL_GID` e a propriedade dos diretórios |
| Nenhum PNG no E2E local | use `--basetemp=e2e-artifacts` e confira a saída do pytest |
| Docker daemon inacessível | confirme o serviço e a associação do usuário ao grupo `docker` |
| Job sem artefato | abra o log do job que produz o arquivo antes do passo `upload-artifact` |
