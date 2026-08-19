# Roteiro do Torneio de Classificadores

## Objetivo

Demonstrar em até oito minutos a API ML saudável, a decisão complementar do
bot, a auditoria e a continuidade do processamento após sabotagem controlada.
Nenhum comando utiliza credenciais reais.

## Preparação

```bash
docker compose build api-ml conferencia-de-lotes
docker compose up --detach --wait api-ml
curl --fail http://127.0.0.1:8000/health
```

O healthcheck esperado é:

```json
{"status":"healthy","model_loaded":true}
```

## Demonstração de até oito minutos

### 0:00–1:00 — arquitetura

Mostrar a separação entre bot, `MLClient`, FastAPI e modelo. Reforçar que o ML
somente complementa casos ambíguos e não altera RN01–RN12.

### 1:00–3:00 — condição saudável

```bash
docker compose run --rm \
  -e ML_ENABLED=true \
  -e EXECUTION_ID=torneio-saudavel \
  -e INPUT_CSV=dados_entrada/lotes_sabotagem_ml.csv \
  conferencia-de-lotes
```

Exibir em `logs/execucao.log` os eventos `DECISAO_ML`, com lote, classe,
probabilidade, confiança, ação, resultado e latência.

### 3:00–5:30 — sabotagem controlada

```bash
docker compose stop api-ml
docker compose run --rm \
  -e ML_ENABLED=true \
  -e ML_TIMEOUT_SECONDS=0.5 \
  -e EXECUTION_ID=torneio-sabotagem \
  -e INPUT_CSV=dados_entrada/lotes_sabotagem_ml.csv \
  conferencia-de-lotes
```

A massa tem sete itens elegíveis. As cinco primeiras falhas abrem o circuit
breaker; os dois itens restantes não tentam a rede. Todos terminam como
`REVISAO_ML_OFFLINE`, sem interromper o lote.

### 5:30–7:00 — evidências

Filtrar os eventos da execução sabotada:

```bash
python -c "import json; p='logs/execucao.log'; [print(l, end='') for l in open(p, encoding='utf-8') if l.lstrip().startswith('{') and json.loads(l).get('execution_id') == 'torneio-sabotagem']"
```

Gerar o Excel usando a auditoria persistida no resumo, sem consultar a API:

```bash
python gerar_relatorio.py \
  --entrada dados_entrada/inspecao_lotes_10dias.xlsx \
  --saida relatorios/relatorio_conferencia_lotes.xlsx \
  --decisoes-ml relatorios/resumo_execucao.json
```

Confirmar a aba `Decisões de ML`, a quantidade de linhas e os campos vazios do
fallback. O `resumo_execucao.json`, o log e o XLSX derivam da mesma coleção de
decisões.

### 7:00–8:00 — recuperação e respostas

```bash
docker compose up --detach --wait api-ml
curl --fail http://127.0.0.1:8000/health
```

O circuit breaker é reiniciado com o processo do bot ou por
`reset_circuit_breaker()`. Um lote nunca fica sem encaminhamento: na
indisponibilidade, segue para revisão humana. O limiar de 0,85 preserva o
contrato da atividade; elevar esse valor reduz automações e falsos positivos,
mas aumenta revisões humanas.

## Dataset oculto

O lote de 50 casos deve respeitar o contrato de `/predict`: `lote_id`,
`status_raw`, `turno` e `tem_obs`. O gabarito é usado apenas pela banca para
calcular a acurácia. O grupo não altera o modelo ou os limiares durante a
avaliação; mede a latência retornada e preserva os logs produzidos.

## Evidências mínimas

- resposta do `/health`;
- eventos `DECISAO_ML` em condição saudável;
- cinco `FALHA_COMUNICACAO_ML` e um `CIRCUIT_BREAKER_ML`;
- sete registros `REVISAO_ML_OFFLINE` na sabotagem;
- execução concluída sem falha fatal;
- resumo JSON e nona aba com a mesma quantidade de decisões.
