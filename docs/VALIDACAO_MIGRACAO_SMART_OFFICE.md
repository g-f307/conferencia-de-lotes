# Validação do plano de migração para o Smart Office

## Identificação

| Campo | Valor |
|---|---|
| Issue | `#117` |
| Data | 30 de agosto de 2026 |
| Tipo | Pré-validação técnica e roteiro de simulação de mesa |
| Ambiente | Local, isolado e sem serviços externos |
| Massa | Temporária e sintética |
| Base validada | `b453f9b` + alterações documentais da branch da issue |
| Estado do cutover | Não executado |

Este registro comprova a parte automatizável do smoke test e prepara a
validação humana exigida pelo plano. Ele não representa autorização para
cutover nem aprovação independente.

## Comandos reproduzíveis

```bash
python -m pytest tests/unit/test_migration_control.py -q
python -m pytest tests/integration/test_coexistence_pipeline.py \
  tests/integration/test_dead_letter.py -q
python -m pytest tests/e2e/test_migration_coexistence_e2e.py -q
python -m ruff check \
  --select E4,E7,E9,F \
  api_ml bot.py gerar_relatorio.py src tests scripts
git diff --check
```

Os testes criam stores e diretórios temporários. Não dependem de Maestro,
Smart Office, canais externos, sessão desktop real ou credenciais.

## Resultado da pré-validação

| Verificação | Resultado | Evidência |
|---|---|---|
| Lease, TTL, fencing e shadow | Aprovado: `10 passed` | `tests/unit/test_migration_control.py`. |
| Coexistência, retomada e dead letter | Aprovado: `11 passed` | Dois módulos de integração documentados acima. |
| Efeitos duplicados | Aprovado: `1 passed` | `tests/e2e/test_migration_coexistence_e2e.py`. |
| Qualidade | Aprovado | Ruff retornou `All checks passed!`. |
| Whitespace | Aprovado | `git diff --check` sem saída. |

Os resultados validam a coordenação em memória e SQLite, inclusive disputa de
posse, shadow sem efeito oficial, retomada, sessão gráfica, relatório, alertas
e dead letter. Eles não substituem o smoke nos dois produtos de orquestração.

## Gates de validação

| Gate | Escopo | Estado | Condição de conclusão |
|---|---|---|---|
| G1 | Smoke automatizado local | `APROVADO` | Os 22 testes e os gates de qualidade acima permanecem aprovados. |
| G2 | Smoke controlado Maestro + Smart Office | `PENDENTE` | Três itens reconciliados e nenhuma saída shadow ou duplicada. |
| G3 | Simulação de mesa | `PENDENTE` | Os três papéis percorrem cutover e rollback e registram o parecer. |
| G4 | Revisão independente | `PENDENTE` | Pessoa diferente do autor confere documentação e evidências. |

Somente G1 pode ser concluído localmente por esta branch. A issue fica pronta
para revisão documental, mas o cutover permanece bloqueado enquanto G2, G3 e
G4 não estiverem aprovados no registro da janela.

## Simulação de mesa com três papéis

Participam coordenação, operação do Maestro e operação do Smart Office. Os
nomes e contatos ficam no registro privado da atividade.

1. A coordenação apresenta a fase 2 com Maestro oficial e Smart Office shadow.
2. A operação do Maestro demonstra como suspender e drenar as agendas.
3. A operação do Smart Office demonstra a matriz de Runners e a sessão desktop.
4. O grupo percorre cada pré-condição e cada linha do checklist de cutover.
5. A coordenação sorteia um gatilho de rollback do runbook.
6. Os operadores narram a suspensão, espera do TTL, troca do publicador e
   restauração do Maestro.
7. O grupo confirma onde localizar contagens, resultados, relatórios, alertas,
   dead letters, duplicidades e logs de lease.
8. Cada papel registra aprovação, ressalva ou reprovação.

## Registro da simulação

| Controle | Coordenação | Operação Maestro | Operação Smart Office | Evidência |
|---|---|---|---|---|
| Plano de coexistência compreendido | Pendente | Pendente | Pendente | Ata sanitizada. |
| Matriz de Runners validada | Pendente | Pendente | Pendente | Diagrama/captura sanitizada. |
| Smoke test reproduzível | Pendente | Pendente | Pendente | Saídas e reconciliação. |
| Cutover com dupla checagem | Pendente | Pendente | Pendente | Checklist preenchido. |
| Rollback reproduzível | Pendente | Pendente | Pendente | Linha do tempo simulada. |
| Evidências localizáveis e seguras | Pendente | Pendente | Pendente | Índice de evidências. |

## Checklist de segurança documental

- [ ] Nenhuma senha, chave, token ou destinatário aparece nas evidências.
- [ ] Identificadores reais de automações, tasks, hosts e pessoas estão
      mascarados na cópia pública.
- [ ] A massa usada é sintética e não crítica.
- [ ] Logs preservam modo, orquestrador, chave idempotente e timestamp.
- [ ] A decisão final foi registrada como avançar, manter coexistência ou
      rollback.

## Pendências externas

- executar o smoke no ambiente controlado dos dois orquestradores;
- realizar a simulação de mesa com os três papéis;
- anexar capturas sanitizadas e a reconciliação das contagens;
- obter revisão independente antes de autorizar qualquer cutover.

Quando essas atividades forem realizadas, substitua `Pendente` pelos estados
observados, informe a referência sanitizada de cada evidência e preserve o
registro preenchido junto à janela. Não altere retroativamente os resultados
do smoke automatizado.
