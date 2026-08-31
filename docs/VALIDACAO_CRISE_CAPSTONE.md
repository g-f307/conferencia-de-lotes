# Validação de crise do pipeline híbrido

## Objetivo e limite

Este roteiro valida localmente o encadeamento dos seis bots do Capstone e seis
sabotagens reproduzíveis. O ensaio usa gateway Maestro em memória, SQLite
temporário, massa sintética, fronteiras desktop controladas e o portal web
versionado. Os IDs iniciados por `local-` não são tasks do Smart Office.

Telegram, SMTP, Vault e serviços corporativos reais não são necessários. Um
smoke manual desses canais pode usar o `.env` local, mas nunca integra a suíte
automatizada nem exige invalidar credenciais reais.

## Preparação

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
python -m playwright install chromium
```

## Execução

O teste de integração substitui as fronteiras visuais por adaptadores
controlados e exercita os componentes reais do pipeline:

```bash
python -m pytest tests/integration/test_crisis_scenarios.py -v
```

O E2E abre o portal local com Chromium e persiste um resumo JSON por cenário:

```bash
python -m pytest tests/e2e/test_crisis_pipeline_e2e.py -v \
  --capstone-evidence-dir=dist/evidencias-capstone
python scripts/validate_capstone_crisis_evidence.py dist/evidencias-capstone
```

As regressões de coexistência e a validação completa são executadas com:

```bash
python -m pytest tests/e2e/test_migration_coexistence_e2e.py -v
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
python -m ruff check --select E4,E7,E9,F \
  api_ml bot.py gerar_relatorio.py src tests scripts
git diff --check
```

## Cenários e oráculos

| Sabotagem | Resultado obrigatório |
|---|---|
| Base de referência indisponível | Retry linear limitado, revisão segura, alerta, quatro itens processados e nenhuma dead letter. |
| Serviço de ML indisponível | Decisão determinística preservada, fallback `indisponibilidade` e relatório produzido. |
| Timeout e cancelamento de dependência | Estados `TIMEOUT` e `CANCELED` distintos, espera limitada e continuidade degradada. |
| Telegram e Email indisponíveis | Fallback Telegram para Email e, quando ambos falham, entrega no log local. |
| Concorrência official/shadow | Somente o official publica; shadow não produz efeito e reexecução não duplica relatório ou alerta. |
| Dado irrecuperável | Três tentativas limitadas, exatamente uma dead letter sanitizada e continuidade dos demais itens. |

Em todos os casos, Dispatcher, coleta desktop, coleta web, consolidação, ML e
relatório/alertas terminam sem tasks em `START` ou `RUNNING`. Os artefatos de
relatório continuam disponíveis quando o pipeline opera em modo degradado.

## Evidências

O diretório informado por `--capstone-evidence-dir` recebe seis arquivos de
cenário e `resumo_cenarios.json`. Cada cenário registra:

- massa sintética e sabotagem aplicada;
- estados observados e quantidade processada;
- fallback, alertas e dead letters;
- duplicidades e artefatos produzidos;
- `execution_id`, `correlation_id` e escopo local;
- duração limitada do ensaio.

O gravador remove valores de senha, token, observação e credencial, além de
substituir caminhos pessoais. Não anexe `.env`, logs brutos ou diretórios
temporários. No GitHub Actions, os mesmos JSONs são publicados no artefato
`evidencias-crise-capstone` com retenção de sete dias.
