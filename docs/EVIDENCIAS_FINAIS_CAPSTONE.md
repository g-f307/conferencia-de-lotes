# Índice de evidências finais do Capstone

## Como interpretar

| Status | Significado |
|---|---|
| `ATENDIDO LOCALMENTE` | Código e teste reproduzível existem no repositório. |
| `OPCIONAL EXTERNO` | Integração depende de credencial ou serviço externo e não é requisito para a execução local. |
| `NÃO EXECUTADO — SEM ACESSO` | Estado-alvo documentado, sem alegação de cadastro ou homologação real. |

Todos os dados são sintéticos. Logs e artefatos gerados em runtime permanecem
fora do Git; o workflow de CI os publica com retenção temporária.

## Matriz da revisão por pares

| # | Critério verificável | Código/documento | Teste ou comando | Evidência/status |
|---:|---|---|---|---|
| 1 | Seis bots, incluindo desktop e web | `deployment/capstone_bots.json` | `python scripts/build_smart_office_packages.py --output-dir dist/capstone` | Manifesto, seis ZIPs e validação estrutural — `ATENDIDO LOCALMENTE` |
| 2 | Encadeamento rastreável | `src/capstone_orchestrator.py` | `python -m pytest tests/e2e/test_capstone_orchestration_pipeline_e2e.py -v` | IDs de execução, correlação e tasks no snapshot — `ATENDIDO LOCALMENTE` |
| 3 | Prioridade coerente do desktop | `src/capstone_orchestrator.py` e `docs/HOMOLOGACAO_LOCAL_CAPSTONE.md` | `python -m pytest tests/unit/test_capstone_orchestrator.py -v` | prioridade local `100`; tradução-alvo Smart Office `1` — `ATENDIDO LOCALMENTE` |
| 4 | Sucesso, erro/cancelamento e timeout separados | `src/capstone_orchestrator.py` | `python -m pytest tests/integration/test_capstone_orchestration.py -v` | estados terminais distintos — `ATENDIDO LOCALMENTE` |
| 5 | Timeout razoável e documentado | `docs/ARQUITETURA_CAPSTONE.md` | `python -m pytest tests/unit/test_capstone_orchestrator.py -v` | limites por dependência — `ATENDIDO LOCALMENTE` |
| 6 | Feature flag desliga o ML sem chamada | `src/ml_bot/service.py` | `python -m pytest tests/unit/test_ml_bot.py -v` | fallback determinístico — `ATENDIDO LOCALMENTE` |
| 7 | ML não altera o status determinístico | `src/consolidation/service.py` e `src/ml_bot/service.py` | `python -m pytest tests/integration/test_ml_bot_pipeline.py -v` | decisão e enriquecimento separados — `ATENDIDO LOCALMENTE` |
| 8 | Origem, confiança e fallback por item | `src/capstone_reporting/service.py` | `python -m pytest tests/integration/test_capstone_report_pipeline.py -v` | Excel/Markdown/JSON/PDF — `ATENDIDO LOCALMENTE` |
| 9 | Queda do desktop não encerra o pipeline | `src/capstone_orchestrator.py` | `test_pipeline_continua_ate_relatorio_quando_desktop_cai` em `tests/e2e/test_capstone_orchestration_pipeline_e2e.py` | desktop `FAILED`, consolidação e relatório `PARTIALLY_COMPLETED` — `ATENDIDO LOCALMENTE` |
| 10 | Retry, fallback e dead letter | `src/retry_policy.py`, `src/dead_letter.py` | `python -m pytest tests/integration/test_crisis_scenarios.py tests/integration/test_dead_letter.py -v` | dead letter sanitizado e idempotente — `ATENDIDO LOCALMENTE` |
| 11 | ML ou auxiliar fora do ar não bloqueia | `src/ml_bot/service.py` | cenário `servico_ml_indisponivel` em `tests/e2e/test_crisis_pipeline_e2e.py` | término degradado — `ATENDIDO LOCALMENTE` |
| 12 | Dois canais de notificação | `src/alerts.py` | `python -m pytest tests/integration/test_alertas_multicanal.py -v` | adaptadores Telegram/SMTP testados; envio real — `OPCIONAL EXTERNO` |
| 13 | Falha do canal primário usa alternativa | `src/alerts.py` | cenário `falha_canal_notificacao` em `tests/e2e/test_crisis_pipeline_e2e.py` | fallback para SMTP/log — `ATENDIDO LOCALMENTE` |
| 14 | Coexistência, cutover e rollback | `docs/PLANO_MIGRACAO_SMART_OFFICE.md` | `python -m pytest tests/e2e/test_migration_coexistence_e2e.py -v` | coexistência simulada; cutover real — `NÃO EXECUTADO — SEM ACESSO` |
| 15 | Prevenção de execução duplicada | `src/migration_control.py` | `python -m pytest tests/integration/test_coexistence_pipeline.py -v` | lease, fencing token e modo shadow — `ATENDIDO LOCALMENTE` |
| 16 | Smoke test no Smart Office | `docs/PLANO_MIGRACAO_SMART_OFFICE.md` | procedimento manual documentado | `NÃO EXECUTADO — SEM ACESSO` |
| 17 | Fluxo de branches, PR e revisão | histórico GitHub | `git log --oneline --decorate -n 20` | branches por issue e revisão cruzada; sem GitLab — `ATENDIDO LOCALMENTE` |
| 18 | README, PDD e arquitetura finais | `README.md`, `docs/REVISAO_BPMN_PDD.md`, `docs/DIAGRAMAS_CAPSTONE.md` | conferência de links e diff | documentação versionada — `ATENDIDO LOCALMENTE` |
| 19 | Pitch de até dez minutos | `docs/ROTEIRO_PITCH_CAPSTONE.md` | ensaio cronometrado pela equipe | roteiro de 9 min 30 s — `ATENDIDO LOCALMENTE` após ensaio |
| 20 | Explicação técnica e decisões | roteiro, diagramas e matriz | revisão por pares | material preparado; avaliação pertence ao grupo revisor |

## Evidências de empacotamento

```bash
python scripts/build_smart_office_packages.py --output-dir dist/capstone
python scripts/validate_smart_office_packages.py --package-dir dist/capstone
sha256sum dist/capstone/*.zip
```

O build determinístico e o comando `sha256sum` registram o SHA-256 dos seis
pacotes. Os hashes não são fixados neste documento: devem ser regenerados a
partir do commit efetivamente apresentado sempre que código, manifesto ou
dependências dos bots mudar.

## Evidências das seis sabotagens

```bash
python -m pytest tests/integration/test_crisis_scenarios.py -v
python -m pytest tests/e2e/test_crisis_pipeline_e2e.py -v \
  --capstone-evidence-dir=dist/evidencias-capstone
python scripts/validate_capstone_crisis_evidence.py dist/evidencias-capstone
```

O diretório gerado contém um JSON sanitizado por cenário e
`resumo_cenarios.json`: base de referência indisponível, ML indisponível,
timeout/cancelamento, Telegram e SMTP indisponíveis, conflito
oficial/`shadow` e dado irrecuperável enviado ao dead letter.

## Inventário dos artefatos reproduzíveis

| Artefato | Origem | Versionamento |
|---|---|---|
| Excel, Markdown, PDF, JSON e logs | `relatorio-alertas-v2` | gerados em runtime; fora do Git |
| Dead letter sanitizado | cenário de dado irrecuperável | gerado em runtime; fora do Git |
| Verificação de duplicidade | testes de coexistência | resultado de teste/CI |
| Captura desktop controlada | `docs/evidencias/capstone/desktop-windows/` | amostra sanitizada versionada |
| Evidência do portal controlado | `docs/evidencias/capstone/fornecedores-chromium/` | índice sanitizado versionado |
| Cobertura e crise | workflow de CI | artefatos temporários do GitHub Actions |

Credenciais, IDs de deploy, capturas inventadas e dados reais não fazem parte
da entrega.
