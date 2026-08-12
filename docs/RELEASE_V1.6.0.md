# Auditor de Lotes v1.6.0 — Relatório executivo Excel

## Visão geral

A versão `v1.6.0` consolida a entrega da Aula 22. Ela adiciona um fluxo
independente para leitura do workbook de inspeção, validação RN01–RN12,
segregação dos resultados e geração de dashboard com gráficos nativos do Excel.

As automações BotCity, DataPool, Selenium histórico e Playwright permanecem
documentadas e não são substituídas por este novo fluxo analítico.

## Principais entregas

- leitura dinâmica das dez abas diárias e da `Base_Referencia`;
- consolidação de 250 registros sem alterar a entrada;
- validação RN01–RN12 com rastreabilidade completa;
- normalização de status e deduplicação por dia;
- classificação única em Válido, Divergência, Ambíguo ou Erro de Entrada;
- relatório com seis abas segregadas;
- indicadores executivos e percentuais consistentes;
- gráfico de rosca com as quatro classificações;
- gráfico de evolução dos dez dias;
- CLI `gerar_relatorio.py` com caminhos configuráveis;
- log final e escrita atômica do XLSX;
- documentação operacional, arquitetura, revisão do PDD e roteiro de cinco
  minutos.

## Resultado homologado

| Classificação | Total | Percentual |
|---|---:|---:|
| Válido | 152 | 60,8% |
| Divergência | 50 | 20,0% |
| Ambíguo | 20 | 8,0% |
| Erro de Entrada | 28 | 11,2% |
| **Total** | **250** | **100,0%** |

## Execução

```bash
python -m pip install -r requirements-report.txt
python gerar_relatorio.py
```

Saídas geradas pelo comando:

```text
relatorios/relatorio_conferencia_lotes.xlsx
logs/execucao_relatorio.log
```

Evidência opcional, exportada manualmente da aba `Resumo`:

```text
artefatos/dashboard_resumo.pdf
```

Os arquivos usados como anexos da entrega não devem ser versionados.

## Validação antes da publicação

```bash
python -m pytest -q --ignore=tests/e2e
python -m pytest tests/e2e/ -q
python -m ruff check --select E4,E7,E9,F bot.py gerar_relatorio.py src tests scripts
git check-ignore \
  relatorios/relatorio_conferencia_lotes.xlsx \
  logs/execucao_relatorio.log \
  artefatos/dashboard_resumo.pdf
```

Checklist:

- [ ] Issue #55 concluída e Pull Request revisado;
- [ ] CI aprovada na `main`;
- [ ] XLSX final aberto e conferido;
- [ ] PDF opcional da aba `Resumo` exportado manualmente e legível;
- [ ] log da rodada final conferido;
- [ ] artefatos gerados ausentes do histórico Git;
- [ ] tag criada a partir do commit de merge da entrega;
- [ ] anexos adicionados à release;
- [ ] release marcada como `Latest`.

## Publicação no GitHub

- Tag: `v1.6.0`
- Target: commit da `main` que concluir a Issue #55
- Título: `Auditor de Lotes v1.6.0 — Relatório executivo Excel`
- Tipo: release estável, não marcar como pre-release
- Comparação anterior: `v1.5.0`

Anexar o XLSX e o log. Se a evidência visual tiver sido preparada, anexar
também o PDF exportado manualmente:

```text
relatorio_conferencia_lotes.xlsx
dashboard_resumo.pdf
execucao_relatorio.log
```

## Compatibilidade e limitações

- o processamento do workbook é integral;
- a estrutura esperada das abas deve ser preservada;
- o dashboard é estático após a geração;
- não há envio automático por e-mail ou publicação automática no Maestro;
- o fluxo Excel não altera RN01–RN07 nem a automação Playwright/DataPool.
