# Conferência de Lotes v1.4.0

Esta versão consolida a automação Playwright no processamento individual do
DataPool, mantendo Page Objects, observabilidade, segurança e evidências
rastreáveis por lote.

## Situação

Documento preparado como nota da próxima release. A versão somente estará
publicada após o merge da integração final, a criação da tag `v1.4.0` e a
homologação definida no checklist de release.

## Principais alterações

- substituição da camada Selenium por Playwright síncrono;
- remoção de `selenium`, `webdriver-manager` e ChromeDriver;
- execução do Chromium em modo headless;
- suporte a Chromium explicitamente configurado no Runner;
- migração de `LoginPage` e `FormPage` para locators semânticos;
- instanciação da `FormPage` para cada item processado;
- autenticação com a credencial recuperada pelo Credentials Vault;
- interação web dentro do loop de consumo do DataPool;
- preenchimento dos campos `resultado_validacao`, `evidencia` e
  `mensagem_resultado` antes da finalização do item;
- screenshot individual de aprovação, reprovação, divergência, revisão ou
  erro;
- continuidade do processamento após falha isolada;
- inclusão das evidências no resumo JSON e no relatório PDF;
- smoke test Playwright executado pela integração contínua;
- atualização do Docker, Docker Compose e pacote BotCity;
- consolidação da arquitetura, do PDD, da matriz de aderência e do roteiro de
  demonstração.

## Comparação com v1.3.0

| Item | `v1.3.0` | `v1.4.0` |
|---|---|---|
| Tecnologia web | Selenium WebDriver | Playwright síncrono |
| Page Objects | Selenium | Playwright |
| Gerenciamento do navegador | Chrome e ChromeDriver | Chromium pelo Playwright |
| Momento da interação | Etapa web separada | Dentro do processamento do item |
| Evidência | Comprovante do formulário | PNG individual por resultado |
| Rastreabilidade | Resultado de negócio e resumo | Resultado, mensagem e evidência no DataPool |
| Falha web | Tratamento da etapa web | Erro isolado com captura e continuidade |

A comparação detalhada está em
[`EVOLUCAO_AUTOMACAO_WEB.md`](EVOLUCAO_AUTOMACAO_WEB.md).

## Compatibilidade de negócio

Esta versão preserva:

- regras RN01–RN07;
- estrutura de entrada do CSV;
- DataPool `FilaAuditoriaLotes2`;
- credencial `credencial_erp2`;
- argumentos do BotCity Runner;
- modelo `ExecutionResult`;
- classificação entre aprovação, reprovação, divergência, revisão e erro
  técnico;
- finalização de falhas de negócio como sucesso operacional da automação.

Não existe migração de dados. A mudança necessária está no ambiente de
execução da automação web.

## Alterações de ambiente

As variáveis históricas abaixo não são mais utilizadas:

```text
CHROME_BIN
CHROMEDRIVER_PATH
```

A variável opcional atual é:

```text
PLAYWRIGHT_CHROMIUM_PATH=/caminho/absoluto/chromium
```

As demais variáveis e os procedimentos atuais estão documentados no
[`README.md`](../README.md), no [`.env.example`](../.env.example) e em
[`DEPLOY_BOTCITY.md`](DEPLOY_BOTCITY.md).

## Evidências

| Evidência | Destino |
|---|---|
| Aprovação | `artefatos/aprovado-<lote>-<timestamp>.png` |
| Reprovação válida | `artefatos/reprovado-<lote>-<timestamp>.png` |
| Divergência ou revisão | `artefatos/divergencia-<lote>-<timestamp>.png` |
| Falha técnica | `artefatos/erro-<lote>-<timestamp>.png` |
| Log estruturado | `logs/execucao.log` |
| Resumo consolidado | `relatorios/resumo_execucao.json` |
| Relatório de evidências | `relatorios/relatorio_evidencias.pdf` |
| Resultado individual | campos de saída do DataPool |

Logs, relatórios, screenshots, pacotes e caches permanecem fora do Git.

## Validação da candidata

- 152 testes automatizados aprovados;
- cobertura total de 92%;
- `git diff --check` aprovado;
- pacote `dist/bot-conferencia-de-lotes-v2.zip` gerado;
- imagem Docker construída;
- smoke test Playwright headless executado em Docker;
- 16 itens processados sem interrupção global;
- 4 itens concluídos com estado final oficial: 2 aprovados e 2 reprovados;
- 9 divergências de negócio e 3 revisões humanas;
- evidências de aprovação, reprovação e divergência geradas;
- resumo JSON e relatório PDF gerados;
- sessão Playwright encerrada corretamente.

## Homologação antes da publicação

- [ ] Pull Request aprovado por outro integrante;
- [ ] checks do GitHub Actions aprovados;
- [ ] branch integrada à `main`;
- [ ] pacote gerado a partir da `main`;
- [ ] Vault `credencial_erp2` validado no ambiente alvo;
- [ ] DataPool `FilaAuditoriaLotes2` validado;
- [ ] execução no BotCity Runner concluída;
- [ ] campos de saída conferidos no DataPool;
- [ ] JSON e PDF publicados como artefatos;
- [ ] senha e tokens ausentes dos logs;
- [ ] tag `v1.4.0` criada no commit aprovado;
- [ ] release publicada no GitHub.

## Limitações conhecidas

- a aplicação web é local e controlada; nenhum ERP real é acessado;
- a entrada por e-mail e XLSX permanece fora do escopo;
- itens encaminhados à revisão humana não possuem tela de decisão posterior;
- a referência de lotes continua configurada externamente;
- a homologação real depende dos recursos e permissões do BotCity Maestro.

## Histórico relacionado

- `v1.0.0`: primeira versão implantável no Maestro;
- `v1.1.0`: consolidação do fluxo corporativo;
- `v1.2.0`: Selenium e homologação no Runner;
- `v1.3.0`: Page Objects integrados ao Selenium;
- `v1.4.0`: Playwright integrado ao DataPool por item.
