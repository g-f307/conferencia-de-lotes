# Evidência 05 — Telegram inválido e fallback de canal

## Sabotagem

O canal Telegram controlado lança uma falha. Na primeira execução, o Email está
disponível. Na segunda, Telegram e Email falham para exercitar o último recurso.

## Resultado observado

```json
{"cenario": "fallback_telegram_email", "entrega_primaria": ["email"], "pipeline_terminal": 1, "ultimo_recurso": ["log_local"]}
```

- o item do pipeline chegou ao estado terminal `APROVADO`;
- a falha do Telegram acionou automaticamente o Email;
- a perda dos dois canais externos acionou o log local;
- nenhuma exceção dos canais interrompeu o processamento;
- a mensagem sentinela de credencial não foi registrada.

## Reprodução

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  -k "telegram_invalido" -v -s
```
