# Evidência 04 — ML com baixa confiança

## Sabotagem

O provedor sugere `causa_incerta` com confiança `0.49`, abaixo do limite
controlado de `0.80`. O item já havia sido classificado pela RN02.

## Resultado observado

```json
{"cenario": "ml_baixa_confianca", "motivo": "baixa_confianca", "origem": "fallback", "regra": "RN02", "resultado": "DIVERGENCIA"}
```

- a causa sugerida foi descartada;
- a auditoria registrou `causa_provavel=nao_classificado`;
- a origem foi `fallback` com motivo `baixa_confianca`;
- a classificação determinística `DIVERGENCIA` e a RN02 foram preservadas.

## Reprodução

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  -k "baixa_confianca" -v -s
```
