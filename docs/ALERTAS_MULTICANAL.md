# Alertas multicanal

## Finalidade

`SistemaAlertas` mantém a notificação fora das regras de negócio e nunca torna
o sucesso do pipeline dependente de um serviço externo. Telegram é o canal
principal, Email SMTP é o canal adicional e o log JSON Lines é o último
recurso.

## Política de entrega

| Severidade | Entrega normal | Contingência |
|---|---|---|
| `INFO` | Telegram | Email quando Telegram falha; log quando ambos falham. |
| `AVISO` | Telegram | Email quando Telegram falha; log quando ambos falham. |
| `ERRO` | Telegram e Email | Log destacado quando Email falha. |
| `CRITICO` | Telegram e Email | Log destacado quando Email falha. |

O log registra o nome do canal e o tipo da exceção. Respostas remotas, tokens,
senhas e observações de operadores não são incluídos.

## Aviso de fallback do ML

Ao final do processamento, o sistema considera apenas as decisões associadas
a divergências. O evento `AVISO` é emitido quando existe pelo menos uma decisão
e todas possuem `origem_decisao=fallback`. A mensagem informa:

- `execution_id`;
- `bot_id`;
- quantidade de decisões afetadas;
- motivo de fallback mais frequente;
- estado final do pipeline.

Uma execução sem divergências ou com pelo menos uma decisão de origem `ml` não
gera esse aviso.

## Configuração

Copie os nomes presentes em `.env.example`. Valores sigilosos devem existir
somente no ambiente do processo ou em um mecanismo externo de segredos:

| Variável | Sigilosa | Uso |
|---|---:|---|
| `ALERTS_ENABLED` | não | Habilita os canais externos. |
| `TELEGRAM_BOT_TOKEN` | sim | Token do bot Telegram. |
| `TELEGRAM_CHAT_ID` | sim | Destino autorizado. |
| `TELEGRAM_API_BASE_URL` | não | API oficial; alteração prevista para testes controlados. |
| `SMTP_HOST` | não | Servidor SMTP. |
| `SMTP_PORT` | não | Porta SMTP. |
| `SMTP_USERNAME` | sim | Usuário técnico, quando exigido. |
| `SMTP_PASSWORD` | sim | Senha SMTP. |
| `SMTP_FROM` | não | Remetente autorizado. |
| `SMTP_TO` | sim | Destinatários separados por vírgula. |
| `SMTP_USE_TLS` | não | Ativa STARTTLS. |
| `ALERTS_TIMEOUT_SECONDS` | não | Timeout individual dos canais. |

Não coloque valores reais em `.env.example`, Compose, imagem Docker, ZIP do
BotCity, issue, PR ou evidência versionada.

## Validação automatizada

```bash
python -m pytest tests/unit/test_sistema_alertas.py -v
python -m pytest tests/integration/test_alertas_multicanal.py -v
python -m ruff check src tests
```

Os testes de integração usam um endpoint HTTP local e um transporte SMTP
controlado. Eles validam o contrato dos adaptadores e o token inválido sem
acessar contas externas.

## Evidência real

Com as variáveis carregadas apenas no ambiente, execute:

```bash
python -m scripts.smoke_test_alerts
```

O smoke test usa severidade `ERRO` para exigir os dois canais e termina com
código zero somente quando Telegram e Email confirmam a entrega. Preserve como
evidência a saída contendo apenas `entregues` e `falhos`, junto às confirmações
recebidas nos canais. Antes de compartilhar capturas, confira que não existem
tokens, endereços privados ou cabeçalhos SMTP visíveis.
