# Evidência 02 — ML fora do ar durante o lote

## Sabotagem

O provedor responde normalmente ao primeiro item, fica indisponível no segundo e
volta a responder no terceiro. Uma chamada adicional exercita diretamente o
`ClassificadorDivergencia` com o serviço desligado.

## Resultado observado

```json
{"cenario": "ml_fora_do_ar_durante_lote", "motivo": "indisponibilidade", "origens": ["ml", "fallback", "ml"], "terminais": 3}
```

- nenhum item foi perdido;
- a queda intermediária produziu `causa_provavel=nao_classificado`;
- a origem registrada foi `fallback` com motivo `indisponibilidade`;
- o terceiro item foi processado após a queda;
- a chamada direta retornou fallback e não propagou exceção;
- o alerta `pipeline_operando_sem_ml` foi validado com uma massa 100% fallback;
- a mensagem sentinela do provedor não apareceu no log.

## Reprodução

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  -k "ml_cai_durante" -v -s
```
