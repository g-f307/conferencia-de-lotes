# Memoria operacional do projeto

Este documento registra as decisoes, praticas e criterios usados no projeto
`conferencia-de-lotes`. Ele serve como contexto unico para retomar o trabalho
fora desta conversa, orientar novos agentes e manter consistencia entre codigo,
documentacao, Pull Requests e releases.

## Finalidade do projeto

O projeto implementa uma automacao corporativa para conferencia de lotes, com
foco em rastreabilidade, resiliencia por item, seguranca de credenciais e
evidencias operacionais.

A automacao evoluiu por entregas incrementais:

- bot modular com configuracao externa, logs, fail-fast e resultado padronizado;
- integracao com BotCity Maestro, DataPool e Credentials Vault;
- processamento resiliente de itens da fila;
- automacao web controlada, primeiro com Selenium e depois com Playwright;
- Page Objects para isolar locators e acoes de interface;
- evidencias por item, resumo JSON e relatorios;
- Docker, GitHub Actions, testes por camada e cobertura minima;
- relatorio Excel executivo com validacoes RN01-RN12, abas segregadas e dashboard.

## Principios de implementacao

O codigo deve continuar seguindo estes principios:

- configuracao por variaveis de ambiente, sem caminhos absolutos fixos;
- credenciais somente em runtime, recuperadas pelo Vault ou mockadas em testes;
- senha, token e chave nunca aparecem em codigo, `.env`, logs, relatorios ou PR;
- falhas de ambiente devem parar cedo, antes de processar itens;
- falhas de item devem ser isoladas e nao podem interromper toda a fila;
- regra de negocio deve ficar fora dos Page Objects;
- locators e acoes web devem ficar encapsulados em Page Objects;
- evidencias devem ser rastreaveis por lote e por execucao;
- arquivos gerados em runtime ficam fora do Git;
- toda mudanca relevante deve ter teste proporcional ao risco;
- documentacao deve refletir o comportamento real aprovado na `main`.

## Arquitetura esperada

A separacao atual deve ser preservada:

| Camada | Responsabilidade |
|---|---|
| `bot.py` | Entrada local e entrada do BotCity Runner. |
| `src/config.py` | Carregar ambiente, argumentos do Runner, caminhos e validacoes. |
| `src/main.py` | Orquestrar execucao, Vault, DataPool, web, relatorios e encerramento. |
| `src/dispatcher.py` | Ler entrada e publicar itens no DataPool. |
| `src/bot.py` | Processar item individualmente, aplicar validacao e finalizar item. |
| `src/validation.py` | Regras RN01-RN07 do fluxo principal. |
| `src/web_automation.py` | Gerenciar Playwright e delegar interacoes aos Page Objects. |
| `src/pages/` | Page Objects, locators, waits e acoes da interface. |
| `src/maestro_client.py` | Adaptador do Maestro, DataPool, alertas, artefatos e task. |
| `src/vault_client.py` | Recuperacao e validacao de credenciais. |
| `src/excel_reporting/` | Leitura, validacao RN01-RN12, relatorio Excel e dashboard. |
| `tests/` | Testes unitarios, integracao, regressao, E2E e validacoes de CI. |

Quando uma mudanca misturar responsabilidades, ela deve ser recusada ou
refatorada antes do merge.

## Padrao de codigo

O estilo de implementacao usado no projeto e conservador e incremental:

- preferir funcoes pequenas e nomes descritivos;
- manter adaptadores para dependencias externas;
- usar `Path` para caminhos;
- evitar `sleep()` em automacao web;
- usar waits por condicao;
- retornar objetos ou dicionarios claros, sem acoplamento com interface;
- tratar erros de negocio separadamente de erros tecnicos;
- registrar eventos importantes com logs estruturados;
- preservar compatibilidade local, Docker e BotCity Runner;
- nao criar abstracoes novas sem necessidade real.

Em caso de duvida, siga o padrao ja existente no modulo mais proximo.

## GitFlow adotado

O projeto usa GitHub Flow com controle por Issue e Pull Request.

Fluxo padrao:

1. Atualizar a `main` local antes de iniciar.
2. Criar uma Issue com contexto, objetivo, escopo e criterios de aceite.
3. Criar uma branch a partir da `main` atualizada.
4. Implementar a mudanca em blocos logicos.
5. Executar testes locais proporcionais.
6. Abrir Pull Request vinculado a Issue.
7. Solicitar revisao de outro integrante.
8. Ajustar feedback quando necessario.
9. Fazer squash merge.
10. Excluir branch remota.
11. Atualizar ambiente local e limpar branches antigas.

Branches recomendadas:

```text
feat/<numero-issue>-descricao-curta
fix/<numero-issue>-descricao-curta
docs/<numero-issue>-descricao-curta
test/<numero-issue>-descricao-curta
ci/<numero-issue>-descricao-curta
refactor/<numero-issue>-descricao-curta
```

Exemplos:

```text
feat/52-relatorio-excel-classificacao
test/63-validacao-testcase-parametrize
ci/67-cobertura-evidencias-testes
docs/55-dashboard-excel-evidencias
```

## Commits

Os commits devem seguir Conventional Commits e precisam ser claros.

Formato:

```text
tipo(escopo): descricao objetiva refs #numero
```

Tipos usados:

| Tipo | Uso |
|---|---|
| `feat` | Nova funcionalidade. |
| `fix` | Correcao de comportamento. |
| `docs` | Documentacao. |
| `test` | Testes. |
| `ci` | Pipeline e GitHub Actions. |
| `refactor` | Refatoracao sem mudanca funcional esperada. |
| `chore` | Ajustes auxiliares. |

Boas praticas:

- nao usar mensagens vagas como `ajustes`, `update`, `correcao`;
- nao colocar tudo em um unico commit quando houver blocos independentes;
- nao quebrar em commits artificiais sem sentido;
- separar implementacao, testes, CI e documentacao quando fizer sentido;
- referenciar a Issue com `refs #N` quando o commit nao fecha sozinho;
- deixar `Closes #N` na descricao do PR, nao necessariamente no commit.

Exemplos bons:

```text
feat(reporting): gerar workbook segregado por classificacao refs #52
test(validation): adicionar cenarios parametrizados RN01-RN12 refs #63
ci(testing): exigir cobertura minima e publicar artefatos refs #67
docs(aula22): documentar dashboard Excel e evidencias refs #55
```

## Issues

Uma Issue boa deve ser pequena o bastante para revisar e grande o bastante para
entregar valor real.

Template recomendado:

```markdown
## Contexto

Explique o problema, a aula, a entrega ou a lacuna atual.

## Objetivo

Declare o resultado esperado de forma direta.

## Escopo

- Item verificavel 1.
- Item verificavel 2.
- Item verificavel 3.

## Fora do escopo

- O que nao deve ser alterado nesta Issue.

## Criterios de aceite

- [ ] Criterio testavel.
- [ ] Criterio testavel.
- [ ] Testes passam.
- [ ] Documentacao atualizada, se aplicavel.
```

Evite Issues que misturem funcionalidade, deploy, testes e documentacao final
sem necessidade. Quando houver dependencia real, registre explicitamente.

## Pull Requests

Todo PR deve responder:

- qual Issue fecha;
- o que foi feito;
- como foi validado;
- o que ficou fora do escopo;
- riscos ou limitacoes relevantes.

Template pratico:

```markdown
## Issue relacionada

Closes #N

## Objetivo

Resumo curto da entrega.

## O que foi feito

- Mudanca principal.
- Testes adicionados.
- Documentacao atualizada.

## Como testar

```bash
python -m pytest
```

## Evidencias

- Testes executados.
- Cobertura ou artefatos, se aplicavel.

## Fora do escopo

- Itens propositalmente nao tratados.
```

Em revisao, priorizar:

- regressao funcional;
- falhas de seguranca;
- quebra de DataPool, Vault ou Runner;
- falta de teste para comportamento novo;
- documentacao divergente do codigo;
- arquivos gerados ou segredos entrando no Git.

## Releases

O projeto usa versionamento semantico e releases por marco de entrega.

Padrao de titulo:

```text
Auditor de Lotes vX.Y.Z - Descricao curta da entrega
```

Exemplos publicados:

```text
Auditor de Lotes v1.0.0 - Deploy inicial no BotCity Maestro
Auditor de Lotes v1.1.0 - Integracao completa da automacao
Auditor de Lotes v1.2.0 - Selenium e homologacao no BotCity
Auditor de Lotes v1.3.0 - Page Objects e consolidacao documental
Auditor de Lotes v1.4.0 - Playwright, DataPool e evidencias por item
Auditor de Lotes v1.5.0 - Testes E2E, Docker e integracao continua
```

Regra pratica:

- `PATCH`: correcao pequena sem nova entrega de aula;
- `MINOR`: nova entrega funcional, tecnica ou avaliativa;
- `MAJOR`: ruptura de compatibilidade ou mudanca estrutural ampla.

Ao criar release pelo GitHub:

1. usar tag no formato `vX.Y.Z`;
2. selecionar o commit exato da `main` que conclui a entrega;
3. manter o padrao de titulo;
4. escrever notas em secoes consistentes;
5. marcar como `Latest` apenas a versao mais recente;
6. nao gerar notas automaticas quando elas quebrarem o padrao do projeto.

Secoes recomendadas:

```markdown
## Visao geral

## Principais entregas

## Validacao

## Artefatos e evidencias

## Compatibilidade

## Seguranca

## Limitacoes conhecidas

## Pull Requests incluidos
```

## Testes

A suite foi organizada por camadas e markers.

Markers principais:

```text
unit
integration
regression
e2e
browser
```

Comandos usuais:

```bash
python -m pytest
python -m pytest -m unit
python -m pytest -m integration
python -m pytest -m regression
python -m pytest -m e2e
python -m pytest --cov=src --cov-report=term-missing
```

Cuidados:

- testes unitarios nao devem depender de navegador, internet ou arquivos reais;
- testes de integracao devem usar mocks, fixtures e `tmp_path`;
- testes E2E devem usar massa controlada;
- cobertura minima atual esperada: 80%;
- cobertura observada pode variar por ambiente, entao usar aproximadamente
  93,5% e o artefato do CI como evidencia oficial;
- `xfail` e `skip` so devem existir quando documentarem limitacao real ou
  funcionalidade futura.

## Docker e CI

O ambiente Docker deve:

- declarar `ENVIRONMENT=container`;
- declarar `TZ=America/Manaus`;
- usar `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright`;
- instalar somente o necessario para execucao headless;
- persistir logs, relatorios e evidencias em volumes;
- nao incluir `.env`, `.venv`, cache, logs ou artefatos no build final.

O GitHub Actions deve manter validacoes separadas:

- lint;
- testes por camada;
- cobertura;
- E2E;
- imagem Docker ou smoke test containerizado;
- publicacao de artefatos quando aplicavel.

## Automacao web

A versao final usa Playwright como fluxo principal.

Diretrizes:

- navegador em modo headless;
- credenciais recuperadas do Vault;
- `LoginPage` autentica e valida sucesso antes do processamento;
- `FormPage` preenche dados do lote e valida confirmacao;
- locators preferem `get_by_label`, `get_by_role` e nomes acessiveis;
- screenshot deve ser gerado por item;
- caminho da evidencia deve ser salvo no DataPool;
- falhas web devem gerar evidencia de erro quando possivel;
- navegador deve ser encerrado em `finally`.

O historico com Selenium permanece como bagagem tecnica e comparacao, mas a
linha principal da entrega final e Playwright.

## DataPool e Maestro

O DataPool e usado como fila e trilha de auditoria.

Campos de entrada:

```text
lote_id, produto, linha, turno, status, responsavel, data, observacao
```

Campos de saida:

```text
resultado_validacao, evidencia, mensagem_resultado
```

Regras:

- atualizar campos de saida antes de finalizar o item;
- usar `report_done` para estados finais validos;
- usar erro de negocio para divergencia ou revisao;
- usar erro de sistema para falha tecnica isolada;
- publicar resumo e relatorios como artefatos;
- chamar `finish_task` no fim da execucao operacional.

## Validacoes de negocio

No fluxo principal, RN01-RN07 definem o resultado por item.

Pontos importantes:

- `APROVADO` e `REPROVADO` sao estados finais oficiais;
- `REPROVADO` nao deve ser convertido em divergencia;
- `OK` normaliza para `APROVADO`;
- `NOK` normaliza para `REPROVADO`;
- status ambiguo deve ir para revisao;
- regra de observacao para reprovado deve ser preservada;
- regras de negocio nao pertencem aos Page Objects.

No relatorio Excel, RN01-RN12 possuem classificacao propria:

```text
Valido
Divergencia
Ambiguo
Erro de Entrada
```

A precedencia do relatorio Excel deve permanecer documentada e testada.

## Relatorio Excel

A entrega da Aula 22 gera workbook executivo com:

- abas diarias consolidadas;
- `Base_Referencia`;
- abas segregadas por classificacao;
- aba `Resumo`;
- indicadores de totais e percentuais;
- graficos nativos do Excel;
- dados sem formulas frageis ou dependencias manuais.

Arquivos gerados de relatorio devem ficar fora do Git, salvo quando forem
materiais-base fornecidos pela aula.

## Documentacao

Documentacao boa neste projeto deve ser:

- tecnica e operacional;
- sobria;
- reprodutivel;
- alinhada com a `main`;
- sem atribuicoes individuais desnecessarias;
- sem detalhes internos de colaboracao que nao ajudem a operar o produto;
- sem prometer comportamento que nao existe;
- sem esconder limitacoes reais.

Documentos centrais:

| Documento | Uso |
|---|---|
| `README.md` | Visao geral, execucao, arquitetura resumida e comandos. |
| `docs/ARQUITETURA.md` | Componentes, sequencia e responsabilidades. |
| `docs/DEPLOY_BOTCITY.md` | Implantacao no BotCity Runner. |
| `docs/EXECUCAO_E2E_DOCKER_CI.md` | Testes E2E, Docker e CI. |
| `docs/RELATORIO_EXCEL_AULA22.md` | Relatorio Excel e dashboard. |
| `docs/HOMOLOGACAO_TESTES_AULA23.md` | Suite, markers, cobertura e evidencias. |
| `docs/REVISAO_BPMN_PDD.md` | Relacao entre processo, PDD e codigo. |

Antes de abrir PR de documentacao, verificar:

- comandos ainda funcionam;
- nomes de filas, credenciais e variaveis estao atuais;
- releases mencionadas existem ou estao claramente planejadas;
- links internos apontam para arquivos existentes;
- nao ha informacao sensivel ou pessoal desnecessaria.

## Arquivos que nao devem entrar no Git

Manter fora do versionamento:

```text
.env
.venv/
__pycache__/
.pytest_cache/
.coverage
coverage.xml
htmlcov/
logs/*
relatorios/*
artefatos/*
dist/*
```

Excecoes aceitaveis:

```text
logs/.gitkeep
relatorios/.gitkeep
artefatos/.gitkeep
```

Se uma evidencia precisa ser compartilhada com revisor, preferir artefato do
GitHub Actions, release, comentario no PR ou canal externo definido pela equipe.

## Comandos uteis

Atualizar ambiente local:

```bash
git switch main
git pull --ff-only origin main
git fetch --prune origin
```

Remover branch local ja integrada:

```bash
git branch -d nome-da-branch
```

Se o Git avisar que a branch local nao esta totalmente mergeada, confirmar se o
PR foi integrado por squash merge. Nesse caso, a branch local pode nao conter o
mesmo commit da `main`, mesmo com o conteudo ja entregue. Use `-D` somente apos
conferir que nao ha trabalho pendente.

Criar branch:

```bash
git switch main
git pull --ff-only origin main
git switch -c tipo/numero-descricao
```

Validar antes do PR:

```bash
python -m pytest
python -m pytest --cov=src --cov-report=term-missing
```

Validar Docker:

```bash
docker compose build
docker compose run --rm bot
```

## Checklist antes de merge

- Issue vinculada.
- Escopo respeitado.
- Sem segredos.
- Sem arquivos gerados.
- Testes locais executados.
- CI aprovado.
- Documentacao atualizada quando necessario.
- PR revisado por outra pessoa.
- Comentarios resolvidos.
- Branch remota excluida apos merge.

## Como orientar agentes futuros

Ao pedir ajuda para outro agente, inclua:

- Issue ou objetivo atual;
- branch atual;
- estado do PR, se existir;
- comandos ja executados;
- restricoes de escopo;
- arquivos que nao devem ser alterados;
- criterio de aceite da aula ou entrega.

Instrucao curta recomendada:

```text
Leia docs/MEMORIA_PROJETO.md antes de alterar o projeto. Preserve GitHub Flow,
commits semanticos, separacao de responsabilidades, testes por camada,
seguranca de credenciais e documentacao alinhada ao comportamento real.
```

## Decisoes importantes ja tomadas

- O projeto nao deve centralizar responsabilidade tecnica em uma unica pessoa.
- O README publico nao deve expor atribuicoes individuais detalhadas.
- `REPROVADO` e estado final valido, nao divergencia.
- Playwright e o fluxo principal atual; Selenium fica como historico tecnico.
- Page Objects encapsulam interface, nao regra de negocio.
- Evidencias de runtime nao entram no Git.
- Release notes devem seguir padrao manual e sobrio.
- Cobertura deve ser tratada como evidencia de execucao, nao como numero fixo
  imutavel.
- Testes devem ser reprodutiveis sem dependencia de credenciais reais.

## Proximos cuidados recorrentes

Ao evoluir o projeto, verificar sempre:

- se a `main` local esta atualizada;
- se a branch foi criada a partir do ponto correto;
- se o PR fecha a Issue certa;
- se a release aponta para o commit certo;
- se os comandos do README continuam validos;
- se Docker, CI e BotCity ainda executam o mesmo fluxo;
- se logs, relatorios e evidencias continuam rastreaveis;
- se nenhuma credencial foi exposta por acidente.

