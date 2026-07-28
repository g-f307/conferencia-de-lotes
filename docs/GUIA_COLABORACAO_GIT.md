# Guia de colaboração Git — Conferência de Lotes

Este documento registra o GitHub Flow utilizado por Gabriel, Marcelo e Rebecca
na construção e evolução do projeto. Ele preserva o roteiro inicial e define as
práticas que continuam válidas para manutenção, correções e novas releases.

## 1. Antes de programar: revisão conjunta do BPMN e PDD

Os três integrantes devem fazer uma reunião curta e revisar:

- `docs/diagrama_pdd.bpmn` e `docs/diagrama_pdd.svg`;
- `docs/Regras de validação a aplicar - Gabriel, Marcelo e Rebecca.docx.pdf`;
- `docs/Inspeção de Lotes - Gabriel, Marcelo e Rebecca.xlsx`;
- `docs/WhatsApp Image 2026-06-23 at 09.45.04.jpeg`;
- `docs/index_lotes (1).html`.

Decisões que precisam ser registradas em uma Issue de documentação:

1. O cenário real é **Inspeção de Lotes**, embora parte do enunciado use o exemplo genérico de auditoria de usuários e CPF.
2. O DataPool usado no projeto será `FilaAuditoriaLotes2`.
3. Cada item da fila representa uma linha/lote da planilha.
4. Campo obrigatório vazio será um `ValidationError`, equivalente ao exemplo do CPF vazio.
5. Status ambíguo não será decidido pelo bot; será separado para revisão humana.
6. A senha do ERP ficará somente no Credentials Vault.

Ao final da reunião, Gabriel cria uma Issue chamada `docs: registrar revisão inicial do BPMN e PDD`. Marcelo e Rebecca comentam na Issue confirmando a revisão. Essa Issue é encerrada por um pequeno PR de documentação, antes das features.

## 2. Divisão técnica equilibrada

Cada pessoa fica responsável por uma entrega completa e independente: Issue, branch, código, testes, documentação do próprio módulo e correções pedidas no review.

| Pessoa | Responsabilidade técnica | Arquivos previstos | Revisor principal |
|---|---|---|---|
| Gabriel | Estrutura, configuração, logs, fail-fast, `ExecutionResult` e fechamento da execução | `bot.py`, `src/main.py`, `src/config.py`, configuração de logs | Rebecca |
| Marcelo | Integração Maestro, Dispatcher, DataPool, alertas e artefato JSON | `src/dispatcher.py`, `src/maestro_client.py`, testes do DataPool | Gabriel |
| Rebecca | RN01–RN07, Performer, `ValidationError` e Credentials Vault | `src/bot.py`, `src/validation.py`, `src/vault_client.py`, testes das regras | Marcelo |

Gabriel administra o repositório, mas não implementa as partes de Marcelo e Rebecca. Cada autor corrige e conclui o próprio PR.

## 3. Preparação inicial do repositório — Gabriel

### 3.1 Criar o repositório local

Na raiz deste projeto:

```bash
git init -b main
git status
git add README.md docs/
git commit -m "docs: adicionar materiais base e plano de colaboracao"
```

### 3.2 Criar o repositório no GitHub

No GitHub:

1. Clicar em **New repository**.
2. Repositório criado: `g-f307/conferencia-de-lotes`.
3. Não marcar criação automática de README, `.gitignore` ou licença, pois o projeto local já possui conteúdo.
4. Copiar a URL apresentada pelo GitHub.

Depois, no terminal:

```bash
git remote add origin https://github.com/g-f307/conferencia-de-lotes.git
git remote -v
git push -u origin main
```

### 3.3 Adicionar a equipe

No repositório do GitHub:

1. Entrar em **Settings → Collaborators**.
2. Adicionar as contas de Marcelo e Rebecca.
3. Os dois devem aceitar o convite antes de começar.
4. Cada integrante deve clonar o repositório na própria máquina:

```bash
git clone https://github.com/g-f307/conferencia-de-lotes.git
cd conferencia-de-lotes
git status
```

### 3.4 Proteger a `main`

Em **Settings → Branches/Rulesets**, criar uma regra para `main` com:

- Pull Request obrigatório;
- pelo menos uma aprovação;
- conversas resolvidas antes do merge;
- aprovação antiga descartada quando houver novos commits;
- bloqueio de force push;
- bloqueio de exclusão da `main`.

Quando a CI for criada, Gabriel acrescenta a exigência de testes aprovados.

## 4. Criar as Issues antes das branches

As Issues devem ser criadas no GitHub antes de alguém programar.

### Issue 1 — Gabriel

Título:

```text
feat: criar estrutura, configuração e ciclo de execução
```

Descrição sugerida:

```markdown
## Objetivo
Criar a estrutura modular do bot e o ciclo principal de execução.

## Critérios de aceite
- [ ] Existem bot.py, src/main.py e src/config.py
- [ ] Não existem caminhos absolutos no código
- [ ] Variáveis não sigilosas são carregadas do .env
- [ ] A pasta dados_entrada é validada antes do processamento
- [ ] A ausência da pasta encerra imediatamente a execução
- [ ] logs/execucao.log contém data, hora e severidade
- [ ] A saída utiliza ExecutionResult
- [ ] Há testes da configuração e do fail-fast

## Fora do escopo
Dispatcher, DataPool, RN01-RN07 e acesso ao Vault.
```

Assignee: Gabriel. Labels: `feature`, `priority:high`.

### Issue 2 — Marcelo

Título:

```text
feat: integrar dispatcher e fila do Maestro
```

Descrição sugerida:

```markdown
## Objetivo
Criar o Dispatcher e encapsular a integração com o BotCity Maestro.

## Critérios de aceite
- [ ] O CSV é lido linha por linha
- [ ] Cada linha gera um DataPoolEntry
- [ ] A fila utilizada é FilaAuditoriaLotes2
- [ ] O Performer pode obter itens com has_next e next
- [ ] O início registra "Iniciando auditoria de acessos"
- [ ] É possível emitir alerta de pasta ausente
- [ ] O resumo JSON pode ser enviado como artefato
- [ ] Os testes não dependem de credenciais reais

## Fora do escopo
Implementação das RN01-RN07 e leitura da senha do ERP.
```

Assignee: Marcelo. Labels: `feature`, `integration`.

### Issue 3 — Rebecca

Título:

```text
feat: implementar performer, validacoes e vault
```

Descrição sugerida:

```markdown
## Objetivo
Implementar RN01-RN07, consumo resiliente e credencial do ERP.

## Critérios de aceite
- [ ] RN01 valida as oito colunas
- [ ] RN02 valida campos obrigatórios
- [ ] RN03 verifica lote na base de referência
- [ ] RN04 aceita somente os status oficiais
- [ ] RN05 normaliza OK e NOK antes da validação
- [ ] RN06 separa status ambíguo para revisão humana
- [ ] RN07 exige observação em lote reprovado
- [ ] ValidationError marca somente o item como erro e o loop continua
- [ ] Usuário e senha são recuperados do Vault credencial_erp2
- [ ] Somente o nome do usuário aparece no log
- [ ] Existem testes positivos e negativos
```

Assignee: Rebecca. Labels: `feature`, `security`, `priority:high`.

## 5. Fluxo individual: Issue → branch → código → PR

Cada integrante repete o processo abaixo na própria Issue.

### 5.1 Atualizar a `main`

```bash
git switch main
git pull --ff-only origin main
git status
```

O resultado de `git status` deve indicar uma árvore limpa antes de criar a branch.

### 5.2 Criar a branch ligada à Issue

Gabriel:

```bash
git switch -c feature/1-core-configuracao
```

Marcelo:

```bash
git switch -c feature/2-maestro-datapool
```

Rebecca:

```bash
git switch -c feature/3-validacoes-vault
```

Confirmar:

```bash
git branch --show-current
```

### 5.3 Trabalhar somente no próprio escopo

Durante a implementação:

```bash
git status
git diff
```

Evitar que um PR altere arquivos pertencentes à entrega de outro integrante. Quando uma interface entre módulos for necessária, os envolvidos combinam primeiro na Issue.

### 5.4 Fazer commits por blocos lógicos

Cada commit deve representar uma unidade coerente e verificável. Mensagens vagas
como `ajustes`, `mudanças` ou `fix` não são aceitas. Também não se deve
concentrar uma funcionalidade ampla em um único commit quando implementação,
testes, build e documentação formam blocos independentes.

O objetivo não é produzir muitos commits pequenos, mas um histórico claro,
descritivo e proporcional ao trabalho realizado.

Exemplos para Gabriel:

```bash
git add src/config.py
git commit -m "feat(config): carregar variaveis de ambiente refs #1"

git add src/main.py tests/
git commit -m "feat(core): adicionar fail-fast e resultado de execucao refs #1"
```

Exemplos para Marcelo:

```bash
git add src/dispatcher.py tests/
git commit -m "feat(dispatcher): publicar linhas no datapool refs #2"

git add src/maestro_client.py
git commit -m "feat(maestro): adicionar alertas e artefatos refs #2"
```

Exemplos para Rebecca:

```bash
git add src/validation.py tests/
git commit -m "feat(validacao): implementar RN01 a RN07 refs #3"

git add src/bot.py src/vault_client.py
git commit -m "feat(performer): tratar itens e acessar vault refs #3"
```

Antes de cada commit:

```bash
git diff --cached
```

Isso permite verificar se senha, token, `.env` real ou arquivo fora do escopo foi incluído por engano.

### 5.5 Enviar a branch

```bash
git push -u origin NOME_DA_BRANCH
```

Depois do primeiro push, novos commits usam apenas:

```bash
git push
```

## 6. Abrir o Pull Request

No GitHub:

1. Abrir **Pull Requests → New Pull Request**.
2. Base: `main`.
3. Compare: branch do integrante.
4. Usar um título objetivo.
5. Colocar `Closes #N` na descrição.
6. Informar o que foi feito e como testar.
7. Marcar o revisor definido na tabela.

Modelo de descrição:

```markdown
## Issue relacionada
Closes #N

## O que foi feito
- Item 1
- Item 2

## Como testar
1. Criar o ambiente virtual
2. Instalar as dependências
3. Executar os testes

## Evidências
- Resultado dos testes
- Print do Maestro, quando aplicável

## Checklist
- [ ] Trabalhei somente no escopo da Issue
- [ ] Não incluí senha, token ou .env
- [ ] Criei testes positivos e negativos
- [ ] Atualizei a documentação necessária
```

## 7. Revisão cruzada

O revisor deve:

1. Ler a Issue e seus critérios de aceite.
2. Abrir a aba **Files changed**.
3. Verificar se o PR alterou somente o escopo esperado.
4. Procurar senha, token, caminhos fixos e logs indevidos.
5. Baixar e executar a branch:

```bash
git fetch origin
git switch NOME_DA_BRANCH_DO_AUTOR
python -m pytest
```

6. Usar **Request changes** quando algum critério não for atendido.
7. Explicar o problema de forma verificável, por exemplo:

```text
RN07 ainda aceita REPROVADO sem observação. Adicione um teste com
observacao vazia e faça a função gerar ValidationError.
```

O autor não abre outro PR para corrigir. Ele altera a mesma branch:

```bash
git add ARQUIVOS_CORRIGIDOS
git commit -m "fix(validacao): exigir observacao em reprovados refs #3"
git push
```

O PR será atualizado automaticamente.

## 8. Ordem dos merges

Para diminuir conflitos:

1. PR de Gabriel: estrutura e contratos básicos.
2. PR de Marcelo: integração Maestro e DataPool.
3. PR de Rebecca: Performer, regras e Vault.
4. PR final de integração, se necessário, contendo apenas ajustes entre os módulos.

Antes de abrir ou concluir um PR, o autor atualiza a branch:

```bash
git switch main
git pull --ff-only origin main
git switch NOME_DA_BRANCH
git merge main
python -m pytest
git push
```

Se houver conflito, o autor da branch resolve, executa os testes e pede nova revisão.

Depois da aprovação e dos testes verdes, usar **Squash and merge**. Em seguida, apagar a branch no GitHub e localmente:

```bash
git switch main
git pull --ff-only origin main
git branch -d NOME_DA_BRANCH
git fetch --prune
```

## 9. Trabalho técnico detalhado por integrante

### Gabriel — núcleo corporativo

1. Criar `src/`, `logs/`, `dados_entrada/` e o entry point `bot.py`.
2. Criar `.gitignore`, garantindo que `.env`, logs, relatórios e ambiente virtual não sejam versionados.
3. Criar `.env.example` somente com nomes das variáveis e valores fictícios não sigilosos.
4. Implementar `config.py` sem caminhos absolutos.
5. Configurar log com data, hora e níveis `INFO`, `WARNING` e `ERROR`.
6. Validar a existência de `dados_entrada/` antes de qualquer processamento.
7. Criar o modelo `ExecutionResult` com totais, sucessos, erros e status final.
8. Integrar os módulos de Marcelo e Rebecca somente depois dos PRs aprovados.

### Marcelo — Maestro e Dispatcher

1. Criar no painel do Maestro o DataPool `FilaAuditoriaLotes2`.
2. Definir os campos: `lote_id`, `produto`, `linha`, `turno`, `status`, `responsavel`, `data`, `observacao`.
3. Criar um CSV com registros válidos e erros propositais.
4. Implementar leitura do CSV usando cabeçalho, sem posições mágicas.
5. Criar um `DataPoolEntry` para cada linha.
6. Implementar o acesso à fila em uma classe adaptadora.
7. Implementar alerta inicial, alerta de pasta ausente e postagem do resumo JSON.
8. Criar mocks nos testes para não depender do Maestro real.

### Rebecca — validação, Performer e segurança

1. Implementar RN01–RN07 como funções pequenas e testáveis.
2. Normalizar espaços e caixa antes das comparações.
3. Converter `OK → APROVADO` e `NOK → REPROVADO` antes de validar o status.
4. Criar `ValidationError` para erro determinístico de negócio.
5. Criar tratamento específico para RN06 e registrar revisão humana.
6. Consumir a fila em `while`, obtendo um item por vez.
7. Colocar `try/except` dentro do loop, para um item inválido não interromper os próximos.
8. Marcar validações como erro de negócio e falhas técnicas como erro de sistema.
9. Criar `credencial_erp2` no Vault com as chaves combinadas pela equipe, por exemplo `username` e `password`.
10. Recuperar as duas chaves em tempo de execução e nunca registrar a senha.

## 10. Integração e demonstração final

Depois dos três PRs:

1. Gabriel demonstra o fail-fast removendo ou renomeando temporariamente `dados_entrada/`.
2. Marcelo demonstra o Dispatcher preenchendo `FilaAuditoriaLotes2` e o artefato JSON.
3. Rebecca demonstra item válido, campo obrigatório vazio, status ambíguo e acesso ao Vault.
4. Os três verificam juntos que a senha não aparece em `git diff`, histórico, `.env.example` ou logs.
5. Executar toda a suíte de testes.

```bash
python -m pytest --cov=src --cov-report=term-missing
git log --oneline --graph --decorate --all
git status
```

## 11. Evidências para a entrega

Guardar prints ou exportações de:

- revisão inicial de BPMN/PDD;
- três Issues atribuídas a pessoas diferentes;
- três branches com nomes padronizados;
- três PRs vinculados às Issues;
- comentários e correções de code review;
- testes com cobertura mínima de 80%;
- proteção da `main`;
- DataPool com itens concluídos e com erro;
- alerta de pasta ausente;
- Vault mostrando o label, sem revelar a senha;
- artefato JSON no Maestro;
- histórico Git mostrando contribuições dos três integrantes.

## 12. Release

Somente depois de todos os critérios aprovados. O exemplo abaixo representa a
primeira release; versões posteriores devem usar o marco semântico definido para
cada entrega:

```bash
git switch main
git pull --ff-only origin main
python -m pytest
git tag -a v1.0.0 -m "Auditor de Lotes v1.0.0"
git push origin v1.0.0
```

No GitHub, criar uma Release a partir da tag e listar as três Issues/PRs que formam a versão.
