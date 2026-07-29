# Evolução da automação web

Este documento registra a evolução técnica da camada web sem substituir as
instruções operacionais da versão atual. Para executar ou implantar o bot,
consulte o [`README.md`](../README.md) e
[`DEPLOY_BOTCITY.md`](DEPLOY_BOTCITY.md).

## Linha do tempo

| Versão | Tecnologia predominante | Marco |
|---|---|---|
| `v1.0.0` | Sem integração web final | Primeira versão implantável no BotCity Maestro. |
| `v1.1.0` | Playwright inicial | Consolidação do fluxo e primeiras interações com a aplicação controlada. |
| `v1.2.0` | Selenium | Migração para WebDriver, waits explícitos e homologação no Runner. |
| `v1.3.0` | Selenium com Page Objects | `LoginPage` e `FormPage` integradas ao fluxo Selenium. |
| `v1.4.0` | Playwright com Page Objects | Processamento web por item do DataPool e evidências rastreáveis. |

As tags Git preservam o código e a documentação correspondentes a cada marco.
A documentação corrente descreve somente `v1.4.0`; referências a Selenium
neste documento e em
[`RELEASE_V1.3.0.md`](RELEASE_V1.3.0.md) são históricas.

## Comparação técnica

| Aspecto | Selenium — `v1.2.0` e `v1.3.0` | Playwright — `v1.4.0` |
|---|---|---|
| API utilizada | Selenium WebDriver síncrono | Playwright síncrono |
| Inicialização | `webdriver.Chrome` com `Service` e `Options` | `sync_playwright()` e `chromium.launch()` |
| Navegador no Runner | `CHROME_BIN` | `PLAYWRIGHT_CHROMIUM_PATH` |
| Driver | `CHROMEDRIVER_PATH` ou `webdriver-manager` | Não utiliza ChromeDriver |
| Locators | `By.ID`, `By.XPATH` e seletores de teste | `get_by_label` e `get_by_role` por nome acessível |
| Esperas | `WebDriverWait` e `expected_conditions` | Auto-wait do Playwright e espera explícita por estado |
| Preenchimento | `clear`, `send_keys`, `Select` e `click` | `fill`, `select_option`, `check` e `click` |
| Page Objects | Driver e timeout compartilhados | Página e timeout compartilhados |
| Sessão | ChromeDriver encerrado com `quit()` | Página, browser e runtime encerrados em `finally` |
| Evidência | Captura do elemento de confirmação | Captura da página completa para cada item |
| Integração com a fila | Evidência web demonstrativa, separada do item | Interação e captura dentro do loop do DataPool |
| Resultado do item | Finalização de negócio sem contrato visual completo | Resultado, mensagem e caminho da evidência no DataPool |
| Dependências | `selenium` e `webdriver-manager` | `playwright` |

## O que foi preservado

A troca da tecnologia web não alterou:

- as regras RN01–RN07;
- o CSV de entrada;
- o DataPool `FilaAuditoriaLotes2`;
- a credencial `credencial_erp2`;
- o contrato `ExecutionResult`;
- os logs estruturados;
- a geração do resumo JSON e do relatório PDF;
- a finalização operacional da task;
- o princípio de não registrar senhas, tokens ou chaves.

`LoginPage` e `FormPage` também foram preservadas como fronteiras
arquiteturais. A migração modificou a implementação dos locators e das ações,
não a separação de responsabilidades.

## Motivos da migração final para Playwright

A versão `v1.4.0` atende à integração final solicitada para a atividade:

1. Chromium em modo headless;
2. locators semânticos;
3. waits orientados a condições;
4. autenticação com credencial recuperada pelo Vault;
5. processamento web dentro do loop do DataPool;
6. screenshot individual de aprovação, reprovação, divergência, revisão ou
   erro;
7. continuidade após falha isolada;
8. caminho relativo da evidência no item, no log e no resumo.

O Playwright elimina a coordenação entre navegador e ChromeDriver e oferece
auto-wait para as ações. Isso reduz a quantidade de código de infraestrutura,
mas não remove a necessidade de timeouts, tratamento de falhas e locators
estáveis.

## Alterações de configuração

Ao migrar de `v1.3.0` para `v1.4.0`, as configurações históricas abaixo deixam
de ser utilizadas:

```text
CHROME_BIN
CHROMEDRIVER_PATH
```

Quando o Runner disponibilizar um Chromium próprio, utilize:

```text
PLAYWRIGHT_CHROMIUM_PATH=/caminho/absoluto/chromium
```

Sem configuração explícita, a aplicação procura navegadores em caminhos
conhecidos e, quando disponível, utiliza o Chromium gerenciado pelo Playwright.

## Evidências por versão

| Versão | Evidência visual |
|---|---|
| `v1.2.0` | Comprovante produzido pela automação Selenium. |
| `v1.3.0` | Comprovante encapsulado pela `FormPage` Selenium. |
| `v1.4.0` | PNG por item com prefixo `aprovado-`, `reprovado-`, `divergencia-` ou `erro-`. |

Na versão atual, os caminhos são relativos à raiz do projeto e aparecem:

- nos campos de saída do DataPool;
- no evento estruturado `EVIDENCIA_ITEM`;
- em `relatorios/resumo_execucao.json`;
- no relatório consolidado em PDF.

## Consulta das versões anteriores

Para inspecionar uma versão sem alterar a branch atual:

```bash
git show v1.2.0:README.md
git show v1.3.0:docs/ARQUITETURA.md
git show v1.3.0:src/web_automation.py
```

Para executar uma versão histórica, crie uma branch temporária a partir da
tag correspondente. Não misture dependências ou variáveis históricas com a
configuração da versão atual.
