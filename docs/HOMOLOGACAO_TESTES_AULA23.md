# Homologação dos testes — Aula 23

## Objetivo

Este documento registra a execução reproduzível da suíte da Aula 23, a
cobertura do código e as limitações conhecidas. Os comandos partem da raiz do
repositório e não exigem Maestro, DataPool, Vault, internet ou credenciais reais
para as camadas controladas.

## Ambiente homologado

- Python 3.14.6 no ambiente local;
- Pytest 8.4.2;
- pytest-cov 6.3.0;
- pytest-playwright 0.8.0;
- Chromium executado em modo headless;
- data da homologação: 17 de agosto de 2026.

O GitHub Actions utiliza Python 3.12, conforme
`.github/workflows/ci.yml`. A aplicação é compatível com Python 3.10 ou
superior.

## Preparação

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
python -m playwright install --with-deps --only-shell chromium
```

No PowerShell, use `.venv\Scripts\Activate.ps1` para ativar o ambiente e omita
`--with-deps` da instalação do navegador.

## Comandos homologados

```bash
python -m ruff check --select E4,E7,E9,F bot.py gerar_relatorio.py src tests scripts

python -m pytest -m unit -q
python -m pytest -m integration -q -rsx
python -m pytest -m regression -q -rxX
python -m pytest -m e2e -q -rsx
python -m pytest -m browser -q
python -m pytest -q

python -m pytest \
  --cov=src \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-report=html \
  --cov-fail-under=80
```

## Resultado consolidado

Na homologação foram coletados 239 testes:

- 237 aprovados;
- 1 ignorado de forma explícita (`SKIPPED`);
- 1 falha esperada e documentada (`XFAIL`);
- 0 falhas inesperadas;
- cobertura total aproximada: 93,5%;
- limite obrigatório: 80%.

O relatório de terminal usa `term-missing` e identifica os números das linhas
não exercitadas. O XML é escrito em `coverage.xml` e a versão HTML em
`htmlcov/index.html`. `.coverage`, `coverage.xml` e `htmlcov/` não são
versionados.

O percentual e a quantidade de statements pertencem a cada execução e podem
apresentar pequenas variações conforme as versões do Python, do Coverage.py e
das dependências instaladas. Por isso, a homologação registra a cobertura como
aproximadamente 93,5%; o artefato `coverage-report` produzido pelo GitHub
Actions no commit avaliado é a evidência oficial dos valores exatos.

## Resultados por camada

| Marker | Responsabilidade | Resultado homologado |
|---|---|---|
| `unit` | Regras e unidades isoladas | 142 aprovados |
| `integration` | Colaboração entre módulos e arquivos temporários | 80 aprovados, 1 SKIPPED e 1 XFAIL |
| `regression` | RN07, RN10, precedência e demais regras críticas | 43 aprovados e 1 XFAIL |
| `e2e` | Pipeline Excel controlado, sem navegador | 7 aprovados |
| `browser` | Interface local em Chromium real | 8 aprovados |
| suíte completa | Todas as camadas | 237 aprovados, 1 SKIPPED e 1 XFAIL |

Os totais de `unit`, `integration` e `regression` podem se sobrepor porque um
teste pode possuir mais de um marker. Eles não devem ser somados para calcular
o total da suíte.

## SKIPPED e XFAIL esperados

O `SKIPPED` registra a atualização incremental do workbook, funcionalidade que
ainda não faz parte do produto. Seu corpo não é executado.

O `XFAIL` reproduz a diferença entre as 100 inconsistências informadas no
enunciado da Aula 22 e os 98 registros problemáticos encontrados pela
homologação das RN01–RN12. Ele usa `strict=True`: se o cenário passar sem que o
marker seja removido, o resultado será `XPASS` e a suíte falhará.

Detalhes e critérios para remoção dos markers estão em
[`REGRESSAO_LIMITACOES_AULA23.md`](REGRESSAO_LIMITACOES_AULA23.md).

## Cobertura e linhas não exercitadas

A cobertura não está concentrada apenas em funções simples. A medição inclui
todo o pacote `src`, incluindo orquestração, gateway do Maestro, descoberta do
navegador, Page Objects, relatórios, leitura do Excel e RN01–RN12.

Os principais trechos não cobertos são caminhos defensivos ou dependentes de
ambiente: falhas específicas do SDK do Maestro, alternativas de descoberta do
Chromium e exceções raras de I/O ou encerramento. Eles permanecem visíveis no
`term-missing`; nenhum arquivo foi omitido apenas para elevar o percentual.

## Evidência no GitHub Actions

O job `coverage` executa a suíte completa depois do lint e dos testes por
marker. A opção `--cov-fail-under=80` encerra o job com erro quando a cobertura
fica abaixo do limite.

Para baixar a evidência:

1. abra **Actions** no repositório;
2. selecione o workflow **CI** e a execução desejada;
3. aguarde o job **Cobertura mínima**;
4. na seção **Artifacts**, baixe `coverage-report`;
5. consulte `coverage.xml` ou abra `htmlcov/index.html`.

O artefato permanece disponível por sete dias. Os jobs de navegador e Docker
continuam publicando seus próprios relatórios e screenshots.

## Respostas para a banca

### Por que um teste é de integração e não unitário?

Porque valida a colaboração real entre mais de um componente, como leitura do
workbook, validação, serialização, escrita do relatório e log. As dependências
externas são simuladas para que apenas essa colaboração seja avaliada.

### Qual teste falha primeiro se NOK deixar de virar REPROVADO?

`tests/unit/test_excel_validation.py::test_rn07_normaliza_nok_para_reprovado`.
O teste está marcado como regressão e protege diretamente a normalização RN07.

### Qual é a diferença prática entre skip e xfail?

`skip` não executa o corpo porque a funcionalidade ou o ambiente não existe.
`xfail` executa um defeito conhecido e espera uma falha específica. Neste
projeto, `strict=True` transforma uma correção inesperada em `XPASS` bloqueante.

### A suíte depende de algum arquivo criado manualmente?

Não depende de arquivo local não versionado. Os testes controlados criam suas
entradas em `tmp_path`; os cenários de homologação da Aula 22 usam somente o
workbook controlado e versionado em `dados_entrada/`.

### A cobertura está concentrada apenas em código fácil?

Não. A medição inclui todo o pacote `src`, inclusive integração, orquestração,
navegador e gateway. Os módulos de menor cobertura continuam expostos no
relatório, assim como as linhas não exercitadas. A contagem exata deve ser
consultada no artefato `coverage-report` da execução avaliada.

### Como executar somente os testes de regressão?

```bash
python -m pytest -m regression -q -rxX
```

### Como localizar o relatório de cobertura no CI?

Abra a execução em **Actions** e baixe o artefato `coverage-report`. O arquivo
HTML inicial é `htmlcov/index.html`.

### Por que o E2E da Aula 23 não usa navegador real?

O objetivo é validar deterministicamente o pipeline Excel completo, sem rede,
credencial ou interface. O navegador possui uma camada própria, executada com
`python -m pytest -m browser -q`, e continua sendo validado separadamente.

## Limitações conhecidas

- a atualização incremental do workbook ainda não está implementada;
- o gabarito informa 100 problemas, enquanto as regras homologadas identificam
  98;
- Maestro, DataPool e Vault reais não são acessados pela suíte controlada;
- o Chromium dos testes de navegador é local e headless;
- os artefatos do GitHub Actions possuem retenção de sete dias.
