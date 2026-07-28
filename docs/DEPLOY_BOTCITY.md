# Deploy no BotCity Maestro

Este roteiro prepara o deploy da automacao como um bot Python customizado. O pacote gerado contem `bot.py`, `requirements.txt`, `src/`, `dados_entrada/` e `docs/index-lotes/` na raiz do arquivo zip.

## Pre-requisitos

- Acesso ao workspace BotCity Maestro.
- Runner ativo no ambiente de execucao.
- DataPool `FilaAuditoriaLotes2` criado.
- Credencial `credencial_erp2` criada no Credentials Vault.
- Python disponivel no host do Runner.
- Google Chrome ou Chromium disponivel no host do Runner.
- ChromeDriver compativel com a versao do navegador.

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
WEB_AUTOMATION_ENABLED=true
WEB_TEST_URL=docs/index-lotes/index.html
WEB_ARTIFACT_DIR=artefatos
WEB_TIMEOUT_SECONDS=15
CHROME_BIN=<opcional-se-estiver-em-caminho-padrao>
CHROMEDRIVER_PATH=<opcional-se-estiver-em-caminho-padrao>
```

Quando a execucao vier do Runner, o `task_id` deve ser fornecido pelos argumentos do proprio Runner. Use `MAESTRO_TASK_ID` apenas em teste controlado fora do Runner.

O bot reconhece automaticamente a chamada do Runner no formato:

```text
bot.py <maestro-server> <task-id> <token>
```

Nesse contexto, `MAESTRO_ENABLED`, `VAULT_ENABLED` e `WEB_AUTOMATION_ENABLED` ficam ativos por padrao se as variaveis nao forem informadas. Use `WEB_AUTOMATION_ENABLED=false` apenas como contingencia para desabilitar Selenium. Ainda assim, mantenha `DATAPOOL_LABEL=FilaAuditoriaLotes2` e `VAULT_LABEL=credencial_erp2` configurados no ambiente da automacao.

## Selenium no Runner

O pacote Python nao instala dependencias de sistema operacional. Antes de publicar a versao com `WEB_AUTOMATION_ENABLED=true`, valide os binarios no host do Runner:

```bash
command -v google-chrome
command -v chromium
command -v chromedriver
google-chrome --version
chromium --version
chromedriver --version
```

O bot tenta autodetectar Chrome/Chromium e ChromeDriver nos caminhos padrao do Linux, incluindo `/usr/bin/google-chrome` e `/usr/local/bin/chromedriver`. Se o host usar outro caminho, configure `CHROME_BIN` e `CHROMEDRIVER_PATH` explicitamente. Exemplo:

```text
CHROME_BIN=/usr/bin/google-chrome
CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
```

No Runner de homologacao atual, o Chrome ja esta instalado globalmente:

```text
CHROME_BIN=/usr/bin/google-chrome
CHROME_VERSION=Google Chrome 149.0.7827.102
```

O ChromeDriver compativel foi encontrado no cache do `webdriver-manager`.
Localize o executavel obtido no Runner e copie-o para um caminho global. No
comando abaixo, substitua `/caminho/para/chromedriver` pelo caminho encontrado:

```bash
sudo install -m 0755 \
  /caminho/para/chromedriver \
  /usr/local/bin/chromedriver
```

Depois valide:

```bash
/usr/local/bin/chromedriver --version
```

Configure apenas se o caminho nao for um dos padroes autodetectados:

```text
CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
```

Na homologacao, o executavel obtido pelo `webdriver-manager` foi instalado em
`/usr/local/bin/chromedriver`. Esse e o caminho operacional usado pelo Runner;
o caminho de origem no cache e especifico do usuario e nao faz parte da
configuracao permanente.

Se o Runner nao possuir ChromeDriver local, o `webdriver-manager` pode baixar o driver em execucao local. Para homologacao no Runner, prefira sempre `CHROMEDRIVER_PATH` configurado para evitar dependencia de acesso externo. O bot valida se os caminhos configurados existem e possuem permissao de execucao antes de iniciar o navegador.

Quando a automacao web estiver habilitada, o log estruturado registra o evento `SELENIUM_AMBIENTE` com os caminhos e versoes dos binarios usados. Esse registro nao contem senhas, tokens ou chaves.

## Validacao local

Antes de empacotar:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python bot.py
```

O resultado local esperado com o CSV de exemplo atual e:

```text
122 passed
status PARTIALLY_COMPLETED
16 itens totais
4 sucessos
9 erros
3 revisoes humanas
```

## Gerar pacote

```bash
.venv/bin/python scripts/build_botcity_package.py --version 2
```

O artefato sera criado em:

```text
dist/bot-conferencia-de-lotes-v2.zip
```

Inspecione o conteudo antes do deploy:

```bash
unzip -l dist/bot-conferencia-de-lotes-v2.zip
```

Confirme a presenca de:

```text
bot.py
requirements.txt
src/
dados_entrada/
docs/index-lotes/
```

Confirme a ausencia de:

```text
.env
.venv/
__pycache__/
.pytest_cache/
logs/
relatorios/
artefatos/
```

## Deploy no Maestro

1. Acesse o menu de Bots no Maestro.
2. Faça deploy de uma nova versao.
3. Use:
   - Bot ID: `bot-conferencia-de-lotes-v2`
   - Versao: `2`
   - Tecnologia: `Python`
   - Arquivo: `dist/bot-conferencia-de-lotes-v2.zip`
4. Marque a versao como released.
5. Execute um smoke test com poucos registros.

## Smoke test

Valide no Maestro:

- alerta informativo de inicio;
- evento `SELENIUM_AMBIENTE` com versoes de Chrome/Chromium e ChromeDriver;
- evento `AUTOMACAO_WEB` com evidencia PNG em `artefatos/`;
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
4. mantenha `WEB_AUTOMATION_ENABLED=false` apenas como contingencia documentada;
5. corrija Chrome/Chromium, ChromeDriver ou permissoes no host;
6. limpe apenas dados de teste do DataPool, quando aplicavel.
