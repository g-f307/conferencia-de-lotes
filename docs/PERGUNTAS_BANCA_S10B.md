# Perguntas da banca S10-B

## Por que o ML não pode decidir o status?

O status possui efeito operacional e precisa ser explicável pelas regras
RN01-RN07 no Performer ou RN01-RN12 no relatório. Essas regras são executadas
antes do ML, têm precedência conhecida e podem ser reproduzidas sem rede ou
modelo. O ML recebe apenas um caso já classificado como ambíguo e sugere uma
causa provável para a observação. A resposta enriquece a auditoria, mas nunca
substitui o resultado nem a regra aplicada.

Esse limite reduz risco: uma alteração de modelo, uma baixa confiança ou uma
resposta incorreta não transforma um lote em aprovado ou reprovado.

## O que acontece se o ML cair durante um lote de 10 mil itens?

A classificação da observação respeita `ML_TIMEOUT_SECONDS` e retorna fallback
com `causa_provavel=nao_classificado`. O item mantém a decisão determinística e
é finalizado normalmente. Cada novo caso elegível pode realizar uma chamada
limitada pelo timeout; portanto, os 10 mil itens não são perdidos, mas uma
indisponibilidade lenta pode aumentar o tempo total da execução.

O `MLClient` tabular possui circuit breaker após cinco falhas, mas o contrato
textual `/predict-divergencia` usado pelo pipeline aplica fallback por item. Ao
final, uma execução em que todas as divergências usaram fallback emite um aviso
de pipeline operando sem ML. Integrar um circuit breaker também ao contrato
textual é uma evolução de desempenho, não uma condição para preservar os
resultados.

## Qual é a diferença entre fallback do ML e fallback da Base de Referência?

O fallback do ML ocorre depois da decisão determinística e afeta somente o
enriquecimento da causa. O status permanece igual e o motivo pode ser timeout,
indisponibilidade, resposta inválida, baixa confiança, observação ausente ou ML
desabilitado.

A Base de Referência participa da regra determinística RN03. Uma falha de
infraestrutura nessa base recebe retry com backoff linear; se persistir, o item
vai para `PENDENTE_REVISAO` e gera alerta. Uma falha repetida de dados pode gerar
dead letter sanitizado. Portanto, os dois fallbacks preservam a fila, mas
atuam em momentos e impactos diferentes.

## O que permanece observável se o ML e o Telegram falharem simultaneamente?

Permanecem disponíveis:

- a decisão determinística e o estado terminal no DataPool;
- a auditoria ML com `origem_decisao=fallback` e motivo específico;
- os logs JSON Lines com `bot_id`, `execution_id`, lote, evento e latência;
- o resumo JSON, o PDF e as evidências web geradas;
- os IDs de correlação e as tasks da cadeia no Maestro;
- o Email, quando configurado, ou o log local como último canal de alerta.

A falha simultânea reduz o enriquecimento e a entrega externa do alerta, mas
não elimina a trilha local nem interrompe o processamento.
