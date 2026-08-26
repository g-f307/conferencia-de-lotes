# Roteiro da Simulação de Crise S10-B

## Objetivo

Demonstrar em até oito minutos que o pipeline mantém decisão determinística,
rastreabilidade e estados terminais quando Base de Referência, ML e canais de
notificação são sabotados de forma controlada.

## Papéis

| Responsável | Papel durante a apresentação |
|---|---|
| Operador do pipeline | Iniciar os testes, conduzir a execução e apresentar o relatório final. |
| Responsável pela sabotagem | Provocar e identificar cada falha controlada. |
| Analista de observabilidade | Explicar os logs, os fallbacks e a rastreabilidade entre as tasks. |

Na ausência de um integrante, quem opera o pipeline também apresenta o
relatório; quem explica os logs assume a narração da sabotagem.

## Preparação

1. Usar a versão aprovada e um `.env` sem valores reais expostos.
2. Deixar o ambiente virtual ativo e as dependências instaladas.
3. Abrir previamente o painel do Maestro, os logs JSON Lines, o relatório de
   amostra e o resumo das evidências.
4. Confirmar que nenhuma captura mostra token, senha, endereço privado ou
   cabeçalho de autenticação.
5. Executar a validação completa antes da apresentação:

   ```bash
   python -m pytest tests/integration/test_crisis_scenarios.py \
     tests/e2e/test_crisis_pipeline_e2e.py -v -s
   ```

## Cronograma de 7 minutos e 40 segundos

| Tempo | Responsável | Ação e mensagem principal |
|---|---|---|
| `0:00-0:35` | Operador | Apresentar objetivo: três bots, decisão determinística e ML apenas consultivo. |
| `0:35-1:05` | Analista | Mostrar a cadeia A -> B -> C e os IDs de correlação no Maestro. |
| `1:05-1:35` | Operador | Iniciar a suíte de crise e mostrar a massa sintética de 30 itens. |
| `1:35-2:10` | Sabotagem | Tornar a Base de Referência indisponível. |
| `2:10-2:45` | Sabotagem | Derrubar o ML durante o lote. |
| `2:45-3:20` | Sabotagem | Exceder o timeout do ML. |
| `3:20-3:55` | Sabotagem | Devolver confiança abaixo do limite. |
| `3:55-4:30` | Sabotagem | Usar Telegram inválido e acionar Email/log local. |
| `4:30-5:35` | Analista | Relacionar logs, fallback, dead letter e estados terminais. |
| `5:35-6:35` | Operador | Mostrar resumo, amostra com `origem_decisao` e cinco evidências. |
| `6:35-7:20` | Analista | Responder às quatro perguntas técnicas da banca. |
| `7:20-7:40` | Operador | Encerrar com resultado, segurança e decisão solicitada ao grupo revisor. |

O roteiro reserva 20 segundos antes do limite de oito minutos para troca de
tela ou atraso de terminal.

## Sequência das cinco sabotagens

### 1. Base de Referência indisponível

O responsável pela sabotagem identifica a injeção de
`ReferenceInfrastructureError`. O analista aponta as três tentativas, o backoff
linear, o alerta e o resultado
`PENDENTE_REVISAO`. Destacar que indisponibilidade não gera dead letter.

Evidência: [Base de Referência indisponível](evidencias/s10b/01-base-referencia-indisponivel.md).

### 2. ML fora do ar durante o lote

O responsável pela sabotagem mostra a sequência resposta válida, falha e nova
resposta válida. O analista confirma `origem_decisao=fallback`,
`motivo_fallback=indisponibilidade` e o processamento do item seguinte.

Evidência: [ML fora do ar](evidencias/s10b/02-ml-fora-do-ar.md).

### 3. ML acima do timeout

O responsável pela sabotagem aponta o timeout controlado de `0.25` segundo. O
analista confirma que o limite foi repassado ao provedor, a latência foi
auditada e a chamada retornou fallback sem bloquear a suíte.

Evidência: [Timeout do ML](evidencias/s10b/03-ml-timeout.md).

### 4. ML com baixa confiança

O responsável pela sabotagem mostra confiança `0.49` diante do limite `0.80`.
O analista destaca que a causa foi descartada e que `DIVERGENCIA` e RN02
permaneceram inalteradas.

Evidência: [Baixa confiança](evidencias/s10b/04-ml-baixa-confianca.md).

### 5. Telegram inválido

O responsável pela sabotagem identifica a falha do canal principal. O analista
mostra a entrega por Email e, no segundo ensaio, o log local quando os dois
canais externos falham. O operador confirma que o item chegou a um estado
terminal.

Evidência: [Fallback Telegram, Email e log](evidencias/s10b/05-fallback-telegram-email.md).

## Fechamento e relatório

Apresentar o [resumo da simulação](evidencias/s10b/resumo-simulacao.md) e o
[relatório de amostra](amostras/decisoes_ml_s10b.json). Confirmar verbalmente:

- 30 de 30 casos sintéticos chegaram a estado terminal;
- 10 decisões ocorreram via ML e 20 via fallback após a queda;
- nenhuma regra determinística foi substituída;
- a amostra contém `origem_decisao`, IDs, resultado e latência;
- nenhuma credencial aparece nas evidências.

## Plano alternativo

### Maestro indisponível

Executar os testes de integração com o gateway em memória e apresentar a
evidência gravada da cadeia `task-a -> local-child-1 -> local-child-2`. Explicar
que essa contingência comprova o contrato de encadeamento, mas não substitui a
captura de homologação do painel real.

### Internet indisponível

Executar integralmente a suíte local. Os provedores de ML, Telegram e Email são
controlados pelos testes e não acessam serviços externos. Usar as cinco
evidências versionadas e o relatório de amostra como apoio visual.

### Ambiente local indisponível

Apresentar as evidências gravadas e o último workflow aprovado. Não declarar
uma nova execução como aprovada; registrar a indisponibilidade no checklist e
agendar a reprodução pelo grupo revisor.
