# Deploy no BotCity Maestro

## Pré-requisitos

- workspace e Runner ativos;
- DataPool `FilaAuditoriaLotes2`;
- credencial `credencial_erp2`;
- Python disponível no Runner;
- Chrome ou Chromium compatível;
- permissão para alertas, artefatos, `create_task`, `get_task` e `finish_task`.

## DataPool

Crie quinze campos de texto:

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
causa_provavel
origem_decisao
confianca_ml
motivo_fallback
```

Os sete últimos são preenchidos antes da finalização de cada item.

## Credentials Vault

Crie `credencial_erp2` com:

```text
username
password
```

As chaves devem estar em minúsculo. A senha não pode estar no `.env`, código,
log, imagem, relatório ou pacote.

## Ambiente

```text
MAESTRO_ENABLED=true
VAULT_ENABLED=true
ORCHESTRATION_ENABLED=false
ORCHESTRATION_TIMEOUT_SECONDS=300
ORCHESTRATION_POLL_INTERVAL_SECONDS=2
DATAPOOL_LABEL=FilaAuditoriaLotes2
VAULT_LABEL=credencial_erp2
REFERENCE_LOTES=L001,L002
REFERENCE_MAX_ATTEMPTS=3
REFERENCE_RETRY_BASE_INTERVAL_SECONDS=1
REFERENCE_TIMEOUT_SECONDS=5
DEAD_LETTER_PATH=data/output/dead_letter.jsonl
INPUT_DIR=dados_entrada
INPUT_CSV=dados_entrada/lotes_auditoria.csv
LOG_FILE=logs/execucao.log
REPORT_DIR=relatorios
PROCESSING_DELAY_SECONDS=0
WEB_AUTOMATION_ENABLED=true
WEB_TEST_URL=web/index-lotes/index.html
WEB_ARTIFACT_DIR=artefatos
WEB_TIMEOUT_SECONDS=15
PLAYWRIGHT_CHROMIUM_PATH=<opcional>
```

O Runner fornece `server`, `task_id` e `token` no formato:

```text
bot.py <maestro-server> <task-id> <token>
```

Não configure o token como variável e não o registre.

## Retry e dead letter

Cada falha de infraestrutura da Base de Referência usa backoff linear. Com os
valores padrão, as esperas são de 1 e 2 segundos antes da segunda e terceira
tentativas. Se a base permanecer indisponível, o item recebe
`PENDENTE_REVISAO`, solicita alerta operacional e não interrompe a fila.

Somente falhas repetidas de dados são gravadas em
`data/output/dead_letter.jsonl`. O arquivo contém item sanitizado, motivo,
tentativas, timestamp, `execution_id` e `task_id`; observações e segredos não
são persistidos. A escrita concorrente usa `portalocker`, compatível com Linux
e Windows. Garanta permissão de escrita em `data/output/` no Runner.

## Orquestração com três bots

Para a cadeia S10-B, registre o mesmo pacote em três automações e atividades:

```text
rebecca-dispatcher-v1
gabriel-conferencia-v1
marcelo-relatorio-v1
```

Defina `ORCHESTRATION_ENABLED=true`. O estágio é identificado automaticamente
pelo `activity_label` da task, portanto o mesmo pacote e o mesmo ambiente podem
atender os três registros. Inicie manualmente somente
`rebecca-dispatcher-v1`; as outras tasks são criadas em sequência por
`create_task()`. Consulte
[`ORQUESTRACAO_MAESTRO.md`](ORQUESTRACAO_MAESTRO.md) para parâmetros, timeout,
logs e coleta da evidência no painel.

## Playwright no Runner

O pacote instala a biblioteca Playwright, mas o host precisa disponibilizar um
Chromium compatível ou o bundle instalado. Verifique:

```bash
command -v google-chrome
command -v chromium
google-chrome --version
chromium --version
```

Se o navegador estiver fora dos caminhos padrão, configure:

```text
PLAYWRIGHT_CHROMIUM_PATH=/caminho/absoluto/chromium
```

O arquivo precisa existir e possuir permissão de execução. Não configure
caminho pessoal de outro usuário. Prefira um executável global e estável
administrado no Runner.

Se o ambiente permitir instalar o bundle:

```bash
python -m playwright install chromium
```

O evento `PLAYWRIGHT_AMBIENTE` informa engine, caminho, versão e modo headless,
sem credenciais.

## Validação local

```bash
python -m pytest -q
MAESTRO_ENABLED=false \
VAULT_ENABLED=false \
WEB_AUTOMATION_ENABLED=false \
PROCESSING_DELAY_SECONDS=0 \
python bot.py
```

Para validar a integração web:

```bash
MAESTRO_ENABLED=false \
VAULT_ENABLED=false \
WEB_AUTOMATION_ENABLED=true \
PROCESSING_DELAY_SECONDS=0 \
python bot.py
```

Confirme PNG de aprovação e divergência, log e resumo.

## Pacote

```bash
python scripts/build_botcity_package.py --version 2
unzip -l dist/bot-conferencia-de-lotes-v2.zip
```

Presença obrigatória:

```text
bot.py
requirements.txt
src/
dados_entrada/
web/index-lotes/
```

Ausência obrigatória:

```text
.env
.venv/
__pycache__/
.pytest_cache/
logs/
relatorios/
artefatos/
dist/
```

## Publicação

1. Acesse o bot `bot-conferencia-de-lotes-v2`.
2. Crie uma nova versão Python.
3. Envie `dist/bot-conferencia-de-lotes-v2.zip`.
4. Configure as variáveis não sigilosas.
5. Marque a versão como released.
6. Execute um smoke test com poucos itens controlados.

## Smoke test

Valide:

- alerta inicial;
- `VALIDACAO_VAULT`;
- `PLAYWRIGHT_AMBIENTE` e `INICIO_PLAYWRIGHT`;
- itens criados e consumidos;
- `resultado_validacao`, `evidencia` e `mensagem_resultado`;
- pelo menos uma aprovação e uma divergência;
- PNG por item com caminho relativo;
- continuidade após falha isolada;
- resumo JSON e PDF publicados;
- `FIM_PLAYWRIGHT` e `ENCERRAMENTO`;
- task finalizada com sucesso operacional;
- ausência de senha e token nos logs.

## Rollback

1. interrompa novas execuções;
2. reative a versão released anterior;
3. preserve logs e artefatos da falha;
4. use `WEB_AUTOMATION_ENABLED=false` somente como contingência documentada;
5. corrija navegador, permissão ou configuração;
6. publique uma nova versão e repita o smoke test.

## Alertas externos

Telegram e Email ficam desabilitados por padrão. Para ativá-los no host do
Runner, forneça `ALERTS_ENABLED=true` e as variáveis descritas em
[`ALERTAS_MULTICANAL.md`](ALERTAS_MULTICANAL.md) pelo ambiente seguro do
processo. Não inclua token, senha SMTP ou destinatários no ZIP do bot.

Antes do deploy definitivo, execute o smoke test controlado no mesmo ambiente:

```bash
python -m scripts.smoke_test_alerts
```

O resultado deve listar `telegram` e `email` em `entregues`. Em seguida, confira
as duas mensagens recebidas e valide no JSON Lines que nenhuma credencial foi
persistida.
