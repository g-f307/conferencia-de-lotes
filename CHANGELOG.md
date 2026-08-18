# Changelog

As mudanças relevantes deste projeto são registradas neste arquivo. O formato
segue as categorias de *Keep a Changelog* e o versionamento semântico adotado
pelas releases do repositório.

## [1.8.0] - 2026-08-18

### Adicionado

- camada pura `src/operational_indicators.py` como fonte matemática dos 10
  indicadores operacionais;
- atributo `regra_aplicada` para rastrear a regra principal de cada registro;
- Dashboard Executivo com metas visuais e exatamente 8 abas;
- abas `Ranking de Regras` e `Dicionário`;
- resumo gerencial `relatorios/resumo_executivo.md`;
- publicação protegida dos artefatos Excel e Markdown;
- métricas operacionais completas no log de execução;
- testes parametrizados e de integração para indicadores e artefatos físicos;
- checklist final de aceite da Aula 24.

### Alterado

- `write_excel_report()` passou a receber explicitamente a coleção ordenada e
  a instância de `OperationalIndicators`;
- o orquestrador passou a calcular indicadores exatamente uma vez por execução
  e compartilhar o mesmo objeto entre Excel e Markdown;
- a aba `Resumo` foi reorganizada para exibir indicadores, metas e gráficos
  nativos sem imagens estáticas;
- documentação principal e PDD atualizados para o fluxo de saídas duplas.

### Qualidade

- cobertura global comprovada em `93,87%`, acima do mínimo de `80%`;
- cobertura de `src/operational_indicators.py` comprovada em `100%`;
- suíte de aceite com `254 passed`, `1 skipped` e `1 xfailed`;
- markers `unit`, `integration`, `regression`, `e2e` e `browser` preservados.

### Limitações conhecidas

- ganho estimado de tempo baseado em premissas didáticas de `2,0` minutos para
  o processo manual e `0,25` minuto para a automação;
- atualização incremental do workbook ainda não implementada;
- diferença homologada entre 100 inconsistências mencionadas no enunciado e 98
  registros problemáticos reproduzidos pela massa oficial.

## [1.7.0] - 2026-08-17

### Adicionado

- organização da suíte em camadas com markers Pytest;
- testes unitários com `unittest.TestCase`, `subTest()` e parametrização;
- testes de integração controlados e E2E sem dependências externas;
- cenários documentados com `skip` e `xfail` estritos;
- cobertura mínima de 80% na integração contínua.

## [1.6.0] - 2026-08-12

### Adicionado

- relatório executivo Excel da Aula 22 com 6 abas;
- validação RN01–RN12 e Dashboard com gráficos nativos;
- homologação da massa oficial de 250 registros.

[1.8.0]: https://github.com/g-f307/conferencia-de-lotes/compare/v1.7.0...HEAD
[1.7.0]: https://github.com/g-f307/conferencia-de-lotes/releases/tag/v1.7.0
[1.6.0]: https://github.com/g-f307/conferencia-de-lotes/releases/tag/v1.6.0
