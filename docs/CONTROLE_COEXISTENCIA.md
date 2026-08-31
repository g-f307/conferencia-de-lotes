# Controle de coexistência entre Maestro e Smart Office

Durante a migração, os dois orquestradores podem receber o mesmo identificador
de execução. `src/migration_control.py` converte essa referência em uma chave
idempotente sem expor seu valor original e mantém o estado em SQLite.

## Modelo de posse

Uma execução oficial possui um proprietário por vez. A lease registra:

- orquestrador solicitante;
- proprietário da execução;
- aquisição e validade em UTC;
- último heartbeat;
- modo `official` ou `shadow`;
- fencing token crescente.

Uma aquisição concorrente oficial é rejeitada e auditada. Depois do TTL, outro
processo pode recuperar a lease com um fencing token maior; o proprietário
antigo deixa de ter permissão para publicar. O encerramento normal libera a
lease imediatamente, mas as reivindicações concluídas de efeitos permanecem e
evitam repetição em uma nova tentativa da mesma execução.

O modo `shadow` não adquire a propriedade oficial. Ele pode produzir resultados
em memória para comparação, mas `run_effect_once()` bloqueia gravação,
relatório, notificação ou qualquer outro callback marcado como efeito oficial.

## Sessão gráfica

A sessão desktop possui uma lease independente. Maestro e Smart Office podem
executar etapas não gráficas em paralelo, mas somente um processo entra em
`desktop_session()` para o mesmo `MIGRATION_DESKTOP_SESSION_ID`. A trava também
tem TTL e pode ser recuperada depois de encerramento inesperado.

## Configuração

| Variável | Padrão | Finalidade |
|---|---|---|
| `MIGRATION_CONTROL_ENABLED` | `false` | Habilita o controle no bot de relatório. |
| `MIGRATION_LEASE_DB_PATH` | `data/output/migration_leases.sqlite3` | Estado compartilhado das leases e efeitos. |
| `MIGRATION_ORCHESTRATOR` | `smart_office` | Processo atual: `maestro` ou `smart_office`. |
| `MIGRATION_OFFICIAL_PUBLISHER` | `smart_office` | Único orquestrador autorizado a publicar. |
| `MIGRATION_LEASE_TTL_SECONDS` | `300` | Validade renovável da posse. |
| `MIGRATION_DESKTOP_SESSION_ID` | `runner-default` | Identificador estável da sessão gráfica. |

Os dois processos precisam apontar `MIGRATION_LEASE_DB_PATH` para o mesmo
arquivo em um volume local compartilhado e usar o mesmo valor de
`MIGRATION_OFFICIAL_PUBLISHER`. SQLite em compartilhamento de rede não é o
modelo suportado; nesse cenário, o adaptador deve ser substituído por um store
distribuído que preserve as mesmas garantias atômicas.

Maestro e Smart Office também devem receber o mesmo `execution_id` de negócio.
Quando o coordenador é habilitado, o Dispatcher rejeita agendamento sem esse
identificador compartilhado, pois UUIDs independentes não permitiriam detectar
a duplicidade.

O TTL deve ser maior que o intervalo entre heartbeats. `run_effect_once()` e
`desktop_session()` mantêm keepalive automático enquanto o callback está
ativo. `heartbeat()` e `DesktopLease.heartbeat()` permanecem disponíveis para
integrações que gerenciem o ciclo da lease diretamente.

## Proteção dos efeitos

`run_effect_once(permit, effect_name, callback)` executa o callback somente
quando:

1. a permissão é oficial;
2. a lease ainda pertence ao proprietário e ao fencing token informados;
3. o efeito ainda não foi concluído por essa chave idempotente.

O serviço `CapstoneReportService` separa `capstone_report_artifacts`,
`capstone_notification:<evento>` e `capstone_report_summary`. Assim, uma
retomada conclui somente a etapa pendente e não regrava artefatos nem repete
notificações já entregues.

Nos demais estágios, o `handler` calcula o `StageResult` e o callback
`publisher` concentra a gravação oficial. `CapstoneOrchestrator` executa esse
publisher por `CapstoneContext.publish_once()`; no modo `shadow`, o cálculo é
preservado e a gravação é bloqueada.

## Validação local

```bash
python -m pytest tests/unit -k "lease or idempot" -v
python -m pytest tests/integration -k "coexist" -v
python -m pytest -m e2e -k "duplicate or coexist" -v
```

Os testes usam dois coordenadores e um SQLite temporário. Nenhum SDK, serviço
externo ou credencial é necessário.

## Operação da migração

O mecanismo deste documento não substitui o controle operacional da janela.
Fases, matriz de Runners, smoke test, critérios de cutover, gatilhos de rollback
e evidências estão definidos em
[`PLANO_MIGRACAO_SMART_OFFICE.md`](PLANO_MIGRACAO_SMART_OFFICE.md).
