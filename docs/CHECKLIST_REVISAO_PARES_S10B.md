# Checklist de revisão por pares S10-B

## Identificação

| Campo | Preenchimento do grupo revisor |
|---|---|
| Grupo revisor |  |
| Integrantes |  |
| Data e hora |  |
| Repositório | `https://github.com/g-f307/conferencia-de-lotes` |
| Versão avaliada |  |
| Ambiente utilizado |  |
| IDs das tasks no Maestro |  |

## Orientação

Este checklist deve ser executado por um grupo diferente dos autores. Em cada
linha, registrar `Conforme`, `Não conforme` ou `Não executado` e anexar um link,
comando, task, log ou artefato que sustente a decisão. Item não executado não
pode ser considerado aprovado.

Os 16 pontos abaixo foram consolidados a partir do escopo, dos critérios de
aceite e das dependências da entrega S10-B. Como o formulário oficial não está
versionado no repositório, o grupo revisor deve compará-los com o formulário
recebido antes de iniciar. Qualquer diferença deve ser corrigida nesta tabela e
registrada na PR, sem alterar o resultado de uma verificação já executada.

A [pré-validação técnica](VALIDACAO_S10B.md) registra os comandos executados
pelo autor. Ela serve como ponto de partida, mas não substitui a reprodução nem
a decisão independente do grupo revisor.

## Formulário de 16 pontos

| Nº | Ponto verificável | Resultado | Evidência ou observação |
|---:|---|---|---|
| 1 | O README identifica os três bots e separa Dispatcher, conferência e relatório. |  |  |
| 2 | `ML_ENABLED`, `ML_CONFIANCA_MINIMA` e `ML_TIMEOUT_SECONDS` estão documentados e foram exercitados. |  |  |
| 3 | O pipeline conclui com ML habilitado e também com ML desabilitado. |  |  |
| 4 | A decisão determinística não é substituída pela classificação da observação. |  |  |
| 5 | A cadeia A -> B -> C preserva `correlation_id`, parentesco e estados terminais no Maestro. |  |  |
| 6 | A Base de Referência indisponível aplica retry/backoff e termina o item em `PENDENTE_REVISAO`. |  |  |
| 7 | A queda do ML durante o lote usa fallback e não perde os itens seguintes. |  |  |
| 8 | O timeout do ML é respeitado e registra `motivo_fallback=timeout`. |  |  |
| 9 | Uma sugestão abaixo de `ML_CONFIANCA_MINIMA` é descartada sem alterar a regra aplicada. |  |  |
| 10 | Telegram inválido aciona Email e a perda dos dois canais produz alerta em log local sem interromper o pipeline. |  |  |
| 11 | Falha repetida de dados gera dead letter físico, sanitizado, idempotente e apto ao procedimento de reprocessamento. |  |  |
| 12 | Logs JSON Lines e decisões ML contêm `bot_id`, `execution_id`, lote, origem, resultado e latência. |  |  |
| 13 | O resumo JSON, o PDF, as evidências web e o relatório de amostra com `origem_decisao` foram inspecionados. |  |  |
| 14 | As cinco sabotagens e a massa sintética de 30 casos foram executadas sem interrupção do pipeline. |  |  |
| 15 | Linter, suíte automatizada e cobertura mínima de 80% foram aprovados na versão revisada. |  |  |
| 16 | Nenhuma senha, token, chave, observação sensível ou credencial real aparece no código, logs, relatórios ou evidências. |  |  |

## Acesso ao repositório privado

Esta confirmação depende da tela de colaboradores e deve ser feita por alguém
com permissão administrativa. Não registrar e-mail, token ou convite privado.

| Colaborador | Acesso confirmado por | Data | Situação |
|---|---|---|---|
| Instrutor |  |  |  |
| Mentor |  |  |  |

## Pontos fortes

1. _Preencher._
2. _Preencher._
3. _Preencher._

## Correções obrigatórias

1. _Preencher._
2. _Preencher._
3. _Preencher._

Quando não houver correções obrigatórias, escrever explicitamente `Nenhuma`.

## Decisão do grupo revisor

- [ ] Aprovado.
- [ ] Aprovado com ressalvas registradas acima.
- [ ] Reprovado até a correção dos itens obrigatórios.

**Responsável pela decisão:** _Preencher._

**Data:** _Preencher._

**Local do checklist preenchido:** _Preencher._

O autor da implementação não deve preencher ou marcar esta decisão em nome do
grupo revisor.
