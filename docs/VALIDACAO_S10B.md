# Pré-validação técnica S10-B

## Identificação

| Campo | Valor |
|---|---|
| Data | 25 de agosto de 2026 |
| Entrega | S10-B |
| Versão | Pré-validação documental |
| Responsável | Autor da implementação documental |

Esta pré-validação registra evidências reproduzíveis antes da revisão por pares.
Ela não representa aprovação independente e não deve ser anexada como se fosse
o checklist preenchido pelo grupo revisor.

## Resultado automatizado

| Verificação | Resultado |
|---|---|
| Cenários de crise | `8 passed` |
| Suíte completa | `498 passed`, `1 skipped`, `1 xfailed` |
| Cobertura de `src` | `94,54%` |
| Limite mínimo | Aprovado, mínimo de 80% |
| Linter configurado no CI | Aprovado |
| Higiene do diff | Aprovado |
| Busca por padrões de segredo nas mudanças | Nenhuma ocorrência |
| Arquivos Python alterados | Nenhum |

## Comandos reproduzidos

```bash
python -m pytest tests/integration/test_crisis_scenarios.py \
  tests/e2e/test_crisis_pipeline_e2e.py -q

python -m pytest \
  --cov=src \
  --cov-report=term-missing \
  --cov-fail-under=80

python -m ruff check \
  --select E4,E7,E9,F \
  api_ml bot.py gerar_relatorio.py src tests scripts

git diff --check
```

A suíte completa foi executada fora do sandbox para permitir o servidor HTTP
local e o Chromium usados pelos testes. Dentro do sandbox, essas duas
capacidades são bloqueadas por permissão do sistema operacional.

## Baseline do Ruff

O comando amplo sugerido para a validação:

```bash
python -m ruff check src tests scripts api_ml
```

encontra 51 avisos preexistentes na versão-base. Eles abrangem ordenação de
imports, modernização de tipos e regras adicionais que não fazem parte do gate
atual do GitHub Actions. Esta revisão não altera Python, e o escopo documental
proíbe usar a entrega para corrigir esses módulos.

O critério "linter permanece aprovado" foi validado com o comando efetivamente
configurado no job `Qualidade do código` de `.github/workflows/ci.yml`. O
diagnóstico amplo deve ser tratado em uma issue técnica própria se a equipe
decidir adotar todas as regras do Ruff como novo baseline.

## Evidências documentais

- [PDD com as seções 6, 8, 9, 16 e 17](REVISAO_BPMN_PDD.md);
- [roteiro cronometrado da Simulação de Crise](ROTEIRO_SIMULACAO_CRISE_S10B.md);
- [respostas para a banca](PERGUNTAS_BANCA_S10B.md);
- [cinco sabotagens reproduzíveis](evidencias/s10b/resumo-simulacao.md);
- [amostra sanitizada com `origem_decisao`](amostras/decisoes_ml_s10b.json);
- [checklist a ser executado pelo grupo revisor](CHECKLIST_REVISAO_PARES_S10B.md).

## Pendências externas

Antes do aceite final:

1. o grupo revisor deve conferir os 16 pontos contra o formulário oficial;
2. o grupo revisor deve executar, preencher e assinar o checklist;
3. o checklist preenchido deve acompanhar a revisão final;
4. um administrador deve confirmar o acesso do instrutor e do mentor.
