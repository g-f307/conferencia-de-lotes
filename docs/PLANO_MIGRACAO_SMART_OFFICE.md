# Plano operacional de migração para o Smart Office

## Finalidade e limites

Este runbook define a coexistência temporária, o smoke test, o cutover e o
rollback do pipeline entre BotCity Maestro e Smart Office. Ele complementa o
controle técnico descrito em
[`CONTROLE_COEXISTENCIA.md`](CONTROLE_COEXISTENCIA.md) e a arquitetura dos seis
bots em [`ARQUITETURA_CAPSTONE.md`](ARQUITETURA_CAPSTONE.md).

O documento não autoriza uma mudança de produção. Datas, identificadores de
automações, nomes de hosts, destinatários e credenciais pertencem ao registro
operacional de acesso restrito. Os aliases deste runbook são neutros e não
devem ser copiados como identificadores reais.

## Princípios invariantes

1. A mesma unidade de negócio recebe o mesmo `execution_id` nos dois
   orquestradores.
2. Apenas o valor definido em `MIGRATION_OFFICIAL_PUBLISHER` produz a saída
   oficial.
3. O orquestrador em `shadow` pode coletar e calcular, mas não grava resultados,
   publica relatórios, envia alertas nem conclui efeitos oficiais.
4. Os dois ambientes usam o mesmo store de leases e efeitos. SQLite é aceito
   somente em volume local compartilhado; compartilhamento de rede exige um
   store distribuído equivalente.
5. A sessão desktop é exclusiva, permanece desbloqueada durante a coleta e não
   é compartilhada entre Runners.
6. Nenhum cutover começa com execução oficial em andamento.
7. Evidências são sanitizadas e relacionadas pela chave idempotente, nunca por
   senha, token, destinatário ou caminho pessoal.

## Estado atual e estado-alvo

| Dimensão | Estado atual: Maestro | Estado-alvo: Smart Office |
|---|---|---|
| Orquestração | Cadeia legada de três estágios, mantida durante a transição. | Pipeline híbrido de seis bots com fan-out, fan-in, prioridade e timeout. |
| Publicador inicial | `maestro` em modo `official`. | `smart_office` em modo `shadow` durante a coexistência. |
| Interface desktop | Não faz parte da cadeia legada. | Coletor dedicado em Runner Windows com sessão gráfica exclusiva. |
| Interface web | Executada pelo fluxo atual. | Coletor Playwright independente. |
| Decisão | Regras determinísticas do fluxo atual. | Consolidação determinística; ML apenas enriquece casos elegíveis. |
| Saídas oficiais | Relatório, resumo e alertas publicados pelo Maestro. | Após o cutover, publicação idempotente pelo Smart Office. |
| Contingência | Versão released e configuração operacional preservadas. | Retorno ao Maestro pelo procedimento de rollback. |

O estado-alvo encadeia os papéis `dispatcher`, `estoque desktop`,
`fornecedores web`, `consolidação`, `classificador ML` e `relatório e alertas`.
O mapeamento desses papéis para atividades reais fica fora do repositório.

## Papéis operacionais

As pessoas são designadas no registro privado da janela. Os papéis podem ser
alternados, mas uma mesma pessoa não executa e aprova o passo crítico do
cutover.

| Papel | Responsabilidades | Evidência sob custódia |
|---|---|---|
| Coordenação da migração | Declarar início e fim de fase, conferir pré-condições, autorizar cutover ou rollback e registrar a decisão. | Checklist assinado e linha do tempo. |
| Operação do Maestro | Drenar tarefas, alterar gatilhos, confirmar o estado das tasks e reativar a origem em rollback. | Captura sanitizada do painel e contagens do Maestro. |
| Operação do Smart Office e observação | Preparar Runners, executar shadow/smoke, comparar resultados e acompanhar leases, logs e saídas. | Capturas sanitizadas, logs correlacionados e matriz de comparação. |

Toda alteração de configuração usa a regra de duas pessoas: um papel executa e
outro confere o valor não sigiloso e o resultado. Credenciais são apenas
referenciadas por um alias aprovado, sem revelar seu conteúdo.

## Matriz de Runners

| Alias lógico | Orquestrador | Carga permitida | Sessão gráfica | Fase inicial | Restrição |
|---|---|---|---|---|---|
| `runner-maestro-geral` | Maestro | Pipeline legado | Não | `official` | Não recebe tasks do Smart Office. |
| `runner-so-servicos` | Smart Office | Dispatcher, consolidação, ML, relatório | Não | `shadow` | Sem navegador ou desktop interativo. |
| `runner-so-web` | Smart Office | Coleta Playwright | Não | `shadow` | Navegador headless e massa controlada. |
| `runner-so-desktop` | Smart Office | Coleta visual de estoque | Sim, Windows, desbloqueada | `shadow` | Exclusivo; sem uso humano durante a task. |

Os aliases representam capacidades, não exigem quatro máquinas físicas. Uma
consolidação de capacidades só é aceita quando não viola o isolamento da
sessão desktop nem mistura filas dos dois orquestradores. O coletor desktop usa
uma `MIGRATION_DESKTOP_SESSION_ID` estável, e a lease deve estar livre antes de
cada execução. Uma disputa gera rejeição auditável; nunca se contorna a trava
iniciando outra sessão com o mesmo recurso físico.

Com o adaptador SQLite atual, os processos dos dois orquestradores precisam
estar isolados logicamente no mesmo host seguro e compartilhar um volume local.
Se a matriz for implantada em hosts físicos distintos, o cutover fica bloqueado
até a troca por um store distribuído com aquisição atômica, TTL, heartbeat,
fencing token e ledger idempotente equivalentes. Montar o arquivo SQLite em
compartilhamento de rede não é uma mitigação aceita.

## Fases da migração

| Fase | Maestro | Smart Office | Saída oficial | Condição para avançar |
|---|---|---|---|---|
| 0. Preparação | Ativo | Instalado, sem agenda | Maestro | Pré-condições e baseline aprovados. |
| 1. Smoke controlado | Ativo | Execução manual em `shadow` | Maestro | Smoke test aprovado e sem efeitos shadow. |
| 2. Coexistência observada | Agenda normal | Agenda restrita em `shadow` | Maestro | Período acordado sem divergência bloqueante. |
| 3. Cutover | Agenda suspensa e tasks drenadas | Agenda liberada em `official` | Smart Office | Primeira execução oficial aprovada. |
| 4. Estabilização | Pronto para rollback, sem agenda | Ativo em `official` | Smart Office | Janela de observação concluída. |
| 5. Encerramento | Contingência arquivada | Operação normal | Smart Office | Critérios de encerramento assinados. |

O valor de `MIGRATION_OFFICIAL_PUBLISHER` é uniforme em todos os processos da
fase. A troca nunca é feita enquanto os dois agendadores estão liberados.

## Matriz de configuração por fase

O modo não é configurado diretamente. Ele é derivado pela comparação entre
`MIGRATION_ORCHESTRATOR` e `MIGRATION_OFFICIAL_PUBLISHER`. Os valores abaixo
devem ser aplicados com dupla checagem antes de liberar qualquer agenda:

| Fase | Processo | `MIGRATION_CONTROL_ENABLED` | `MIGRATION_ORCHESTRATOR` | `MIGRATION_OFFICIAL_PUBLISHER` | Agenda |
|---|---|---|---|---|---|
| Preparação | Maestro | `true` | `maestro` | `maestro` | Ativa; saída oficial atual. |
| Preparação | Smart Office | `true` | `smart_office` | `maestro` | Suspensa. |
| Smoke/coexistência | Maestro | `true` | `maestro` | `maestro` | Oficial, limitada à massa controlada no smoke. |
| Smoke/coexistência | Smart Office | `true` | `smart_office` | `maestro` | Manual/restrita em shadow. |
| Cutover/estabilização | Maestro | `true` | `maestro` | `smart_office` | Suspensa e drenada. |
| Cutover/estabilização | Smart Office | `true` | `smart_office` | `smart_office` | Oficial após autorização. |
| Rollback | Smart Office | `true` | `smart_office` | `maestro` | Suspensa; permanece shadow. |
| Rollback | Maestro | `true` | `maestro` | `maestro` | Reativada somente após leases livres. |

Os dois processos precisam obedecer às mesmas regras de recurso e correlação:

| Variável compartilhada | Regra operacional |
|---|---|
| `MIGRATION_LEASE_DB_PATH` | Mesmo volume local quando os processos estão no mesmo host; em hosts distintos, usar o adaptador distribuído homologado. |
| `MIGRATION_LEASE_TTL_SECONDS` | Mesmo valor positivo e superior ao intervalo de heartbeat. |
| `MIGRATION_DESKTOP_SESSION_ID` | Mesmo alias estável para o único recurso gráfico físico. |
| `execution_id` | Mesma referência de negócio, inédita para nova execução e preservada em retomadas. |

Após cada alteração, os operadores registram somente os nomes das variáveis e
seus valores não sigilosos. O caminho físico do store, nomes reais de hosts e
demais dados internos ficam no registro operacional restrito.

## Modo shadow

O shadow usa a mesma massa sintética e o mesmo `execution_id` do caminho de
comparação. Ele pode criar envelopes, consultar fontes controladas, consolidar
registros e calcular o relatório em memória. Os seguintes efeitos devem
retornar como ignorados ou bloqueados:

- escrita operacional ou atualização de item;
- publicação do relatório e do resumo;
- alerta em qualquer canal;
- conclusão de um efeito já reivindicado pelo publicador oficial.

Logs diagnósticos do shadow são permitidos e devem conter orquestrador, modo,
chave idempotente e resultado da tentativa. A comparação considera o conteúdo
calculado em memória; a ausência proposital de artefato shadow não é falha.

## Pré-condições do smoke test

- branch/release candidata identificada e artefatos construídos;
- relógios dos Runners sincronizados;
- store de coexistência acessível pelos dois processos;
- topologia do store aprovada: SQLite em volume local do mesmo host ou adaptador
  distribuído homologado para hosts distintos;
- TTL maior que o intervalo de heartbeat;
- `MIGRATION_OFFICIAL_PUBLISHER=maestro` em ambos os ambientes;
- Maestro em `official` e Smart Office em `shadow`;
- aliases de Runner conferidos e sessão desktop disponível;
- canais externos substituídos por destinos de teste ou adaptadores em memória;
- massa sintética sem dados pessoais, credenciais ou itens produtivos;
- diretório de evidências vazio e identificado pela janela;
- baseline de tarefas oficiais, relatórios, alertas e dead letters registrado.

## Smoke test controlado

Use uma referência inédita no formato neutro `smoke-AAAA-MM-DD-NNN` como
`execution_id` compartilhado. A massa mínima contém três itens sintéticos:

| Caso | Entrada controlada | Resultado esperado |
|---|---|---|
| S1 | Item nominal presente nas duas fontes. | Resultado terminal válido, sem dead letter. |
| S2 | Divergência determinística entre estoque e pedido. | Divergência rastreável; ML pode enriquecer, sem alterar o status. |
| S3 | Falha de dados repetida preparada no adaptador de teste. | `DATA_FAILURE` após o limite de tentativas e exatamente uma dead letter sanitizada. |

### Execução

1. Registre contagens iniciais de tasks, efeitos, relatórios, alertas e dead
   letters.
2. Confirme nos dois ambientes o mesmo `execution_id`, store, TTL, sessão
   desktop e publicador oficial, sem copiar valores sigilosos para a evidência.
3. Inicie a execução oficial no Maestro.
4. Inicie a execução shadow no Smart Office com a mesma referência.
5. Aguarde os estados terminais com timeout; não faça repetição manual enquanto
   houver lease ativa.
6. Capture os eventos de aquisição, heartbeat, bloqueio shadow e encerramento.
7. Compare as três entradas e os três resultados calculados por chave do item.
8. Conte os efeitos oficiais antes e depois da execução.
9. Repita a tentativa shadow com a mesma referência e confirme que nenhum
   efeito oficial adicional foi criado.
10. Execute a simulação automatizada do mecanismo:

```bash
python -m pytest tests/unit/test_migration_control.py -q
python -m pytest tests/integration/test_coexistence_pipeline.py \
  tests/integration/test_dead_letter.py -q
python -m pytest tests/e2e/test_migration_coexistence_e2e.py -q
```

### Resultado esperado e reconciliação

| Controle | Fórmula de aceite |
|---|---|
| Itens | `recebidos=3`, `terminais=3`, sem chave ausente ou repetida. |
| Resultados | S1, S2 e S3 coincidem com a tabela; divergência de conteúdo é zero. |
| Relatórios | Exatamente um conjunto oficial; nenhum arquivo shadow. |
| Alertas | Exatamente um envio oficial por evento configurado no smoke; zero envio shadow. |
| Dead letters | Exatamente uma para S3; chave idempotente única e conteúdo sanitizado. |
| Duplicidades | Zero efeito concluído mais de uma vez para a mesma chave e nome. |
| Desktop | Uma posse por vez; toda disputa é rejeitada e registrada. |
| Rastreabilidade | Todos os registros contêm modo, orquestrador, chave e timestamps. |

Qualquer contagem diferente reprova o smoke. Não se corrige a evidência
manualmente; preservam-se os dados, abre-se o incidente e repete-se com um novo
`execution_id` somente após o diagnóstico.

## Coexistência observada

A janela começa após a aprovação do smoke e termina quando os critérios de
cutover forem atingidos ou ao completar cinco dias úteis, o que ocorrer
primeiro. Ela deve conter no mínimo duas execuções controladas consecutivas e
uma jornada operacional completa em `shadow`. Datas, horários e volume máximo
por execução são definidos no registro privado antes da abertura. Durante a
janela:

- Maestro continua `official`;
- Smart Office continua `shadow`;
- amostras usam a mesma referência compartilhada;
- a comparação é feita por item, não apenas por totais;
- cada divergência recebe classificação `dados`, `regra`, `integração`,
  `infraestrutura` ou `esperada pelo shadow`;
- um desvio bloqueante interrompe novas execuções shadow, sem afetar a agenda
  oficial do Maestro.

O corte só pode ser proposto após duas execuções controladas consecutivas sem
efeito duplicado, sem disputa gráfica não tratada e sem divergência bloqueante.
Se os critérios não forem atingidos em cinco dias úteis, a coexistência é
suspensa, o Maestro permanece oficial e uma nova janela depende da análise dos
desvios.

## Critérios objetivos para o cutover

Todos os itens precisam estar aprovados:

- smoke test e suíte automatizada aprovados;
- duas execuções de coexistência consecutivas reconciliadas;
- zero efeito oficial originado pelo shadow;
- zero item, relatório, alerta ou dead letter duplicado;
- 100% dos itens com estado terminal e correlação completa;
- nenhuma task oficial em andamento no Maestro;
- sessão desktop livre, exclusiva e com lease recuperável;
- Runners do Smart Office saudáveis e com timeout configurado;
- mecanismo de alerta validado em destino controlado;
- backup do store de leases e inventário dos artefatos preservados;
- versão/configuração anterior do Maestro disponível para rollback;
- papéis de execução e aprovação presentes durante toda a janela.

## Riscos e medidas de mitigação

| Risco | Sinal de detecção | Mitigação | Resposta imediata |
|---|---|---|---|
| Gatilho duplicado | Mesma chave solicitada pelos dois orquestradores. | `execution_id` compartilhado, lease e ledger de efeitos. | Manter apenas o proprietário oficial e auditar a rejeição. |
| Split-brain no cutover | Dois ambientes configurados como publicador ou duas agendas ativas. | Suspender e drenar Maestro antes da troca, com dupla checagem. | Suspender Smart Office e iniciar rollback. |
| Store inadequado entre hosts | SQLite apontado para caminho de rede ou store divergente. | Mesmo host com volume local ou store distribuído equivalente. | Bloquear coexistência e cutover. |
| Expiração durante tarefa longa | Heartbeat atrasado ou fencing token alterado. | TTL dimensionado, relógios sincronizados e keepalive. | Interromper publicação do proprietário antigo. |
| Efeito indevido do shadow | Arquivo, alerta ou escrita originada pelo shadow. | Publishers protegidos e testes de efeitos idempotentes. | Reprovar smoke e preservar evidências. |
| Colisão de desktop | Lease ocupada ou sessão usada por pessoa/outro processo. | Runner dedicado, sessão desbloqueada e lease de recurso. | Não iniciar nova sessão; aguardar ou recuperar após TTL. |
| Falha parcial de publicação | Alertas entregues sem resumo ou artefato incompleto. | Efeitos granulares e retomada somente do passo pendente. | Retomar com a mesma chave após diagnóstico. |
| Divergência de resultado | Contagem igual, mas conteúdo diferente por item. | Reconciliação por chave e classificação do desvio. | Manter Maestro oficial e suspender shadow afetado. |
| Vazamento em evidência | Segredo, destinatário ou identificador interno em log/captura. | Massa sintética, sanitização e revisão antes do anexo. | Restringir o artefato e acionar procedimento de segurança. |
| Rollback concorrente | Maestro reativado com lease Smart Office ainda válida. | Drenagem e espera de liberação/TTL; fencing token. | Suspender ambos até confirmar posse livre. |

## Checklist de cutover

Preencha uma cópia desta tabela no registro restrito da janela. `UTC`,
`Evidência` e `Status` não podem ficar vazios. O executor e o conferente devem
ser papéis distintos; nomes de hosts, destinatários e segredos não entram na
cópia pública.

| # | Verificação | Executor | Conferente | UTC | Evidência | Status |
|---:|---|---|---|---|---|---|
| 1 | Declarar congelamento de mudanças e registrar versões candidatas. | Coordenação | Operação Smart Office | Pendente | Registro de versões | Pendente |
| 2 | Confirmar critérios objetivos e autorização para o corte. | Coordenação | Operação Maestro | Pendente | Decisão da janela | Pendente |
| 3 | Suspender novas agendas no Maestro. | Operação Maestro | Coordenação | Pendente | Estado do agendador | Pendente |
| 4 | Drenar ou encerrar de forma controlada as tasks oficiais abertas. | Operação Maestro | Operação Smart Office | Pendente | Contagem de tasks | Pendente |
| 5 | Confirmar leases oficial e desktop livres. | Operação Smart Office | Operação Maestro | Pendente | Consulta sanitizada do store | Pendente |
| 6 | Preservar baseline, store e inventário das evidências anteriores. | Operação Smart Office | Coordenação | Pendente | Hashes e inventário | Pendente |
| 7 | Aplicar a matriz de cutover nos dois ambientes. | Operação Smart Office | Operação Maestro | Pendente | Matriz conferida | Pendente |
| 8 | Confirmar Maestro sem agenda e em shadow. | Operação Maestro | Coordenação | Pendente | Estado e modo | Pendente |
| 9 | Liberar a agenda do Smart Office. | Operação Smart Office | Coordenação | Pendente | Estado do agendador | Pendente |
| 10 | Executar massa mínima não crítica com referência inédita. | Operação Smart Office | Operação Maestro | Pendente | Referência mascarada | Pendente |
| 11 | Confirmar publicação e alertas únicos, sem duplicidade ou dead letter inesperada. | Operação Smart Office | Coordenação | Pendente | Reconciliação | Pendente |
| 12 | Confirmar logs, relatório, artefatos e estados dos seis papéis. | Operação Smart Office | Operação Maestro | Pendente | Índice de evidências | Pendente |
| 13 | Declarar estabilização ou acionar rollback. | Coordenação | Ambos os operadores | Pendente | Decisão final | Pendente |

Valores permitidos em `Status`: `APROVADO`, `REPROVADO` ou `NÃO APLICÁVEL`
com justificativa. Qualquer linha pendente ou reprovada impede a estabilização.

## Gatilhos de rollback

O rollback é obrigatório diante de qualquer condição:

- publicação duplicada ou efeito produzido pelos dois orquestradores;
- perda da correlação ou itens sem estado terminal;
- divergência material entre dados de entrada, decisão e relatório;
- alerta crítico ausente ou repetido;
- dead letter inesperada ou sem rastreabilidade;
- disputa não controlada da sessão desktop;
- store de leases indisponível, inconsistente ou sem heartbeat;
- falha técnica recorrente acima do timeout operacional;
- exposição de informação sigilosa em log ou artefato.

## Procedimento de rollback

1. Suspenda imediatamente novas agendas do Smart Office.
2. Não inicie tarefas no Maestro enquanto houver lease oficial ativa.
3. Registre o gatilho, horário UTC, última chave idempotente e tasks afetadas.
4. Aguarde o encerramento controlado ou a expiração do TTL; não apague leases
   para forçar a posse.
5. Preserve logs, banco de leases, relatórios, alertas e dead letters da falha.
6. Confirme que nenhuma task Smart Office permanece em execução e que as leases
   oficial e desktop estão livres.
7. Restaure `MIGRATION_OFFICIAL_PUBLISHER=maestro` nos dois ambientes com dupla
   checagem.
8. Reative somente a agenda anterior do Maestro; mantenha o Smart Office
   suspenso ou em `shadow` sem agenda automática.
9. Execute um item sintético não crítico com referência inédita.
10. Confirme uma única saída oficial, reconcilie as contagens e registre o
    retorno ao estado anterior.
11. Abra análise de causa antes de propor uma nova janela de cutover.

O rollback não remove registros do store nem reutiliza uma referência que teve
efeito concluído. A preservação do ledger é parte da proteção contra repetição.

## Evidências da janela

| Evidência | Conteúdo mínimo | Critério de segurança |
|---|---|---|
| Linha do tempo | Fase, horário UTC, papel e decisão. | Sem nomes pessoais na cópia pública. |
| Configuração | Orquestrador, modo, TTL e aliases de recursos. | Sem valores de Vault, token ou destinatário. |
| Painéis | Estados e contagens de tasks. | IDs reais mascarados. |
| Logs JSON Lines | Aquisição, heartbeat, bloqueio, publicação e encerramento. | Mensagens e contexto sanitizados. |
| Reconciliação | Itens, resultados, relatórios, alertas, dead letters e duplicidades. | Identificadores sintéticos. |
| Artefatos | Relatório e hashes das evidências. | Massa não produtiva. |
| Testes | Comandos, resultado e versão do commit. | Sem dump de ambiente. |
| Decisão | Avançar, manter coexistência ou rollback, com justificativa. | Aprovação por papéis, não credenciais. |

Use [`VALIDACAO_MIGRACAO_SMART_OFFICE.md`](VALIDACAO_MIGRACAO_SMART_OFFICE.md)
como registro reproduzível da simulação e da revisão de mesa.

## Encerramento da coexistência

A coexistência termina somente depois de:

- estabilização mínima de uma jornada operacional e duas execuções oficiais
  consecutivas do Smart Office sem gatilho de rollback;
- execuções oficiais do Smart Office reconciliadas pelo período acordado;
- zero duplicidade e zero conflito gráfico não controlado;
- relatórios, alertas e dead letters conferidos;
- runbook de suporte e monitoração transferido à operação;
- evidências e decisão final aprovadas pelos três papéis;
- contingência do Maestro arquivada conforme a política de retenção.

Desativar o fluxo legado, remover código ou limpar dados históricos exige uma
issue posterior. Não faz parte deste plano.
