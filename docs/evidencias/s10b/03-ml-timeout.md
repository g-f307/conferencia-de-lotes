# Evidência 03 — ML acima do timeout

## Sabotagem

O provedor controlado recebe o timeout configurado e lança `TimeoutError`. Um
relógio injetado simula a passagem do tempo, sem espera real.

## Resultado observado

```json
{"cenario": "ml_timeout", "latencia_simulada_ms": 250.0, "motivo": "timeout", "timeout_configurado": 0.25}
```

- o timeout de `0.25` segundo foi repassado ao provedor;
- o classificador retornou imediatamente um resultado seguro;
- a origem foi `fallback` e o motivo específico foi `timeout`;
- o log estruturado registrou o mesmo motivo.

## Reprodução

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  -k "timeout_ml" -v -s
```
