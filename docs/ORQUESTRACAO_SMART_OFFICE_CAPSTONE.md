# Orquestração dos seis bots no Smart Office

O fluxo do Capstone é implementado de forma aditiva em
`src/capstone_orchestrator.py`. A cadeia de três bots de
`src/orchestrator.py` continua disponível durante a migração, assim como o
adaptador do BotCity Maestro. A integração nova usa
`SmartOfficeGatewayAdapter`, que recebe um cliente por injeção e não importa o
SDK nem acessa credenciais durante os testes.

## Grafo de execução

```text
dispatcher-v2
├── estoque-desktop-v1 (prioridade maior)
└── fornecedores-web-v1
          │
          └── consolidacao-v2 (aguarda as duas coletas)
                    └── classificador-ml-v1
                              └── relatorio-alertas-v2
```

O Dispatcher cria as cinco tasks posteriores e registra em cada uma
`execution_id`, `correlation_id`, `root_task_id`, `parent_task_id` e os IDs das
predecessoras. A consolidação recebe os dois IDs reais do fan-out; não são
fabricados IDs quando a criação de uma task falha.

As prioridades e esperas são configuradas por ambiente:

| Variável | Padrão | Finalidade |
| --- | ---: | --- |
| `SMART_OFFICE_DESKTOP_PRIORITY` | `100` | Prioridade da coleta desktop. |
| `SMART_OFFICE_DEFAULT_PRIORITY` | `50` | Prioridade dos demais bots. |
| `SMART_OFFICE_DEPENDENCY_TIMEOUT_SECONDS` | `300` | Limite por predecessora. |
| `SMART_OFFICE_POLL_INTERVAL_SECONDS` | `2` | Intervalo entre consultas. |

O valor da prioridade desktop deve ser maior que a prioridade padrão.

## Estados e continuidade degradada

Cada espera termina como `SUCCESS`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELED`
ou `TIMEOUT`; não existe espera infinita. Erro, cancelamento e timeout são
registrados separadamente nos logs.

- Desktop, web e ML são bloqueados quando sua dependência obrigatória falha.
- A consolidação ainda executa com uma fonte indisponível e recebe os resultados
  das duas dependências para construir um snapshot degradado.
- O relatório e os alertas executam mesmo quando o ML falha, é cancelado ou
  excede o timeout. Uma execução originalmente bem-sucedida é registrada como
  `PARTIALLY_COMPLETED` nesse caso.
- Falhas na criação de tasks são registradas em `creation_failures` e propagadas
  como `upstream_creation_failures` às tasks que ainda puderem ser criadas.
  Cada falha direta é materializada no contexto como dependência sintética com
  `task_id=null`, `status=FAILED`, `source_status=UNAVAILABLE` e
  `motivo_fallback=task_creation_failed`, sem entrar no polling.
- Se uma coleta não for criada, a consolidação termina como
  `PARTIALLY_COMPLETED`; se as duas não forem criadas, termina como `FAILED`
  com snapshot `OPERATIONAL_FAILURE` e `report_type=OPERATIONAL_INCIDENT`.

Essa política mantém as regras determinísticas e a emissão de relatório como
fontes operacionais obrigatórias; o enriquecimento por ML permanece opcional.

## Validação local

```bash
python -m pytest tests/unit -k "orchestrat" -v
python -m pytest tests/integration -k "orchestrat" -v
python -m pytest -m e2e -k "pipeline" -v
```

Os testes utilizam `InMemoryMaestroGateway` como gateway compatível, sem Smart
Office, Maestro, internet ou credenciais reais.
