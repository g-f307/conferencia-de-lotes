# Evidência 01 — Base de Referência indisponível

## Sabotagem

O gateway controlado lança `ReferenceInfrastructureError` em todas as consultas.
O relógio real e a rede não são utilizados; a função de espera apenas registra os
intervalos solicitados.

## Resultado observado

```json
{"alertas": 3, "cenario": "base_referencia_indisponivel", "resultado": "PENDENTE_REVISAO", "tentativas": 9, "terminais": 3}
```

- cada item realizou três tentativas;
- os intervalos de backoff foram `0.1` e `0.2` segundo;
- os três itens chegaram a `PENDENTE_REVISAO`;
- um alerta foi solicitado por item;
- nenhuma entrada foi enviada ao dead letter;
- o valor sentinela informado como `token=...` apareceu no log apenas como
  `[REDACTED]`.

## Reprodução

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  -k "base_indisponivel" -v -s
```
