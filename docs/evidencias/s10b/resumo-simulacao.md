# Resumo da simulação de crise S10-B

## Resultado consolidado

Execução local em 25 de agosto de 2026, sem internet, Maestro ou credenciais
reais:

```text
8 passed
```

| Verificação | Resultado |
|---|---:|
| Cenários obrigatórios de sabotagem | 5/5 |
| Massa sintética | 30 casos |
| Casos em estado terminal | 30/30 |
| Decisões anteriores à queda do ML | 10 via ML |
| Decisões após a queda do ML | 20 via fallback |
| Erros de sistema no ensaio | 0 |
| Dead letter físico | criado e validado |
| Cadeia de tasks | `task-a` → `local-child-1` → `local-child-2` |
| Segredos nas evidências | 0 |

Saída reproduzível do ensaio de 30 casos:

```json
{"cenario": "massa_sintetica_30_casos", "erros_sistema": 0, "fallback": 20, "ml": 10, "motivo_fallback": "indisponibilidade", "terminais": 30, "total": 30}
```

## Cobertura complementar

- o arquivo `dead_letter.jsonl` é criado em `tmp_path`, lido e validado durante
  o teste; observação e token sentinela não são persistidos;
- a cadeia usa o gateway em memória, mantém um único `correlation_id` e preserva
  `parent_task_id` em todos os estágios;
- o teste de 30 casos derruba o ML depois da décima chamada, demonstrando que a
  falha ocorre durante o lote;
- logs reais dos testes são escritos em `tmp_path` e inspecionados contra os
  valores sentinela antes da aprovação.

## Reprodução completa

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  tests/e2e/test_crisis_pipeline_e2e.py -v -s
python -m pytest -m integration -v
python -m pytest -m e2e -v
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
```

As linhas iniciadas por `CRISIS_EVIDENCE` são intencionalmente limitadas a
contagens, estados, motivos controlados e IDs sintéticos.
