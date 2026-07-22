# Deploy no BotCity Maestro

Este roteiro prepara o deploy da automacao como um bot Python customizado. O pacote gerado contem `bot.py`, `requirements.txt`, `src/` e `dados_entrada/` na raiz do arquivo zip.

## Pre-requisitos

- Acesso ao workspace BotCity Maestro.
- Runner ativo no ambiente de execucao.
- DataPool `FilaAuditoriaLotes2` criado.
- Credencial `credencial_erp2` criada no Credentials Vault.
- Python disponivel no host do Runner.

## DataPool

Crie o DataPool `FilaAuditoriaLotes2` com estes campos de texto:

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

## Credentials Vault

Crie uma credencial com label `credencial_erp2` contendo:

```text
username
password
```

A senha nao deve ficar em `.env`, codigo, log ou relatorio.

As chaves devem estar exatamente em minusculo, sem espacos: `username` e `password`. Se o Runner mostrar `Server returned 400. Key not found`, revise se a automacao esta com `VAULT_LABEL=credencial_erp2` e se a credencial possui essas duas chaves.

## Variaveis de ambiente

No ambiente do Maestro/Runner, configure:

```text
MAESTRO_ENABLED=true
VAULT_ENABLED=true
MAESTRO_SERVER=<url-do-workspace>
MAESTRO_LOGIN=<login-tecnico>
MAESTRO_KEY=<chave-tecnica>
MAESTRO_TASK_ID=
DATAPOOL_LABEL=FilaAuditoriaLotes2
VAULT_LABEL=credencial_erp2
REFERENCE_LOTES=L001,L002
INPUT_DIR=dados_entrada
INPUT_CSV=dados_entrada/lotes_auditoria.csv
LOG_FILE=logs/execucao.log
REPORT_DIR=relatorios
PROCESSING_DELAY_SECONDS=1
```

Quando a execucao vier do Runner, o `task_id` deve ser fornecido pelos argumentos do proprio Runner. Use `MAESTRO_TASK_ID` apenas em teste controlado fora do Runner.

O bot reconhece automaticamente a chamada do Runner no formato:

```text
bot.py <maestro-server> <task-id> <token>
```

Nesse contexto, `MAESTRO_ENABLED` e `VAULT_ENABLED` ficam ativos por padrao se as variaveis nao forem informadas. Ainda assim, mantenha `DATAPOOL_LABEL=FilaAuditoriaLotes2` e `VAULT_LABEL=credencial_erp2` configurados no ambiente da automacao.

## Validacao local

Antes de empacotar:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python bot.py
```

O resultado local esperado com o CSV de exemplo atual e:

```text
66 passed
status PARTIALLY_COMPLETED
16 itens totais
4 sucessos
9 erros
3 revisoes humanas
```

## Gerar pacote

```bash
.venv/bin/python scripts/build_botcity_package.py --version 0.1.0
```

O artefato sera criado em:

```text
dist/bot-conferencia-de-lotes-v1.zip
```

## Deploy no Maestro

1. Acesse o menu de Bots no Maestro.
2. Faça deploy de uma nova versao.
3. Use:
   - Bot ID: `bot-conferencia-de-lotes-v1`
   - Versao: `0.1.0`
   - Tecnologia: `Python`
   - Arquivo: `dist/bot-conferencia-de-lotes-v1.zip`
4. Marque a versao como released.
5. Execute um smoke test com poucos registros.

## Smoke test

Valide no Maestro:

- alerta informativo de inicio;
- itens criados/consumidos no DataPool;
- status individual de sucesso, erro de negocio, erro de sistema ou revisao;
- artefato `resumo_execucao.json`;
- task finalizada como `SUCCESS` quando o processamento termina, mesmo com itens de negocio rejeitados;
- log do Runner contendo `Automacao encerrada com sucesso operacional`;
- ausencia de senha nos logs.

Se o log do Runner mostrar `UnknownHostException` ou `A rede está fora de alcance`, a falha esta na conectividade do Runner com o workspace Maestro, nao no pacote Python. Verifique rede, DNS, proxy/VPN e acesso a `https://lgcmdi.botcity.dev` no host do Runner.

## Rollback

Se a versao falhar em homologacao:

1. desative o agendamento ou pare novas execucoes;
2. volte a versao released anterior;
3. preserve logs e artefatos da falha;
4. limpe apenas dados de teste do DataPool, quando aplicavel.
