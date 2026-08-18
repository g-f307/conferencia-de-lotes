# Checklist Final de Aceite — Aula 24

## Identificação

| Item | Valor |
|---|---|
| Entrega | Semana 5 — preparação para o Demo Day |
| Issue | #79 |
| Branch | `docs/79-documentacao-aula24` |
| Data da verificação | 18 de agosto de 2026 |
| Entrada homologada | `dados_entrada/inspecao_lotes_10dias.xlsx` |
| Saída Excel | `relatorios/relatorio_conferencia_lotes.xlsx` |
| Saída textual | `relatorios/resumo_executivo.md` |
| Log | `logs/execucao_relatorio.log` |

## A. Branch e rastreabilidade

- [x] Existe branch dedicada à issue #79.
- [x] A entrega parte das dependências #74, #75, #76, #77 e #78.
- [x] Nenhuma alteração foi aplicada diretamente na `main`.
- [x] Os commits seguem Conventional Commits e referenciam `#79`.
- [x] O diff da entrega está restrito a documentação.
- [x] Arquivos gerados, credenciais, caches e temporários permanecem fora do
  versionamento.

## B. Motor de validação e orquestração

- [x] RN01–RN12 permanecem implementadas sem mudança de regra nesta entrega.
- [x] A precedência continua `Erro de Entrada > Divergência > Ambíguo > Válido`.
- [x] `NOK` continua normalizado para `REPROVADO`.
- [x] RN10 continua classificando reprovação sem observação como Divergência.
- [x] RN11 continua considerando lote e dia, sem misturar datas diferentes.
- [x] Cada registro validado preserva `regra_aplicada` como regra principal.
- [x] Os registros são ordenados antes da consolidação dos indicadores.
- [x] `calcular_indicadores()` é chamado exatamente uma vez por execução.
- [x] Excel e Markdown recebem a mesma instância de `OperationalIndicators`.
- [x] Falha durante a geração remove temporários e impede publicação parcial.

## C. Indicadores operacionais

- [x] O Dashboard apresenta total de registros.
- [x] Quantidade e percentual de Válidos são calculados.
- [x] Quantidade e percentual de Divergências são calculados.
- [x] Quantidade e percentual de Ambíguos são calculados.
- [x] Quantidade e percentual de Erros de Entrada são calculados.
- [x] A regra mais acionada apresenta código, descrição e frequência.
- [x] A taxa de qualidade da entrada é calculada com proteção contra total zero.
- [x] A taxa de revisão humana é calculada com proteção contra total zero.
- [x] A taxa de retrabalho é calculada com proteção contra total zero.
- [x] O ganho estimado é apresentado em minutos e horas.
- [x] As premissas de `2,0` min manual e `0,25` min automatizado estão explícitas.
- [x] As metas visuais usam comparação estrita: qualidade `> 80%`, revisão
  `< 15%` e retrabalho `< 6%`.

## D. Relatório Excel

- [x] O arquivo XLSX é gerado fisicamente.
- [x] O workbook possui exatamente 8 abas e na ordem contratada.
- [x] As abas são `Resumo`, `Todos`, `Válidos`, `Divergências`, `Ambíguos`,
  `Erros de Entrada`, `Ranking de Regras` e `Dicionário`.
- [x] As cinco abas operacionais não misturam classificações.
- [x] `Resumo` contém os 10 indicadores operacionais.
- [x] O gráfico de distribuição é um `DoughnutChart` nativo do OpenPyXL.
- [x] O gráfico temporal é um `LineChart` nativo do OpenPyXL.
- [x] Nenhuma imagem estática substitui os gráficos.
- [x] O Ranking usa `regra_aplicada` e ordenação por frequência.
- [x] A primeira posição do Ranking coincide com o indicador 6.
- [x] O Dicionário cobre termos, fórmulas, metas e RN01–RN12.

## E. Resumo executivo e testes

- [x] `resumo_executivo.md` é gerado fisicamente junto ao relatório.
- [x] O texto usa linguagem de negócio e não expõe nomes de classes ou
  bibliotecas.
- [x] A tabela Markdown contém os 10 indicadores.
- [x] O ganho estimado declara premissas e observação metodológica.
- [x] Os testes unitários usam o marker `unit`.
- [x] Os testes de integração usam o marker `integration`.
- [x] `_percentual()` possui caso explícito com `total=0`.
- [x] Os 10 indicadores são cobertos por cenários parametrizados.
- [x] A geração física do XLSX e do Markdown usa `tmp_path`.
- [x] Existe teste que demonstra a dependência de `regra_aplicada` no indicador
  6 e no Ranking.
- [x] A suíte de aceite registra `254 passed`, `1 skipped` e `1 xfailed`.
- [x] A cobertura global é `93,87%`, acima do mínimo de `80%`.
- [x] `src/operational_indicators.py` possui `100%` de cobertura.

## F. Documentação

- [x] O `README.md` documenta a camada de indicadores.
- [x] O `README.md` descreve as 8 abas e o resumo Markdown.
- [x] Premissas e limitações do ganho estimado estão documentadas.
- [x] Instruções de Ruff, markers, suíte e cobertura estão atualizadas.
- [x] O PDD incorpora consolidação, saídas duplas e publicação protegida.
- [x] O `CHANGELOG.md` possui entrada da versão 1.8.0 referente à Aula 24.
- [x] As respostas prováveis da banca estão no README, no PDD e neste checklist.
- [x] A evolução para RN13 está descrita conforme o desenho atual.

## G. Segurança e execução controlada

- [x] Nenhuma credencial real foi adicionada ao código ou à documentação.
- [x] `.env`, tokens, senhas e chaves permanecem ignorados pelo Git.
- [x] Logs não registram credenciais ou segredos.
- [x] Testes controlados não acessam internet, Maestro ou Vault reais.
- [x] Artefatos de teste são escritos em diretórios temporários.
- [x] Excel, Markdown, logs e evidências de runtime permanecem ignorados.
- [x] A mudança documental não altera Playwright, DataPool ou Credentials Vault.

## H. Pull Request

- [x] A descrição contém `Closes #79`.
- [x] Objetivo, alterações, decisões, comandos e evidências estão descritos.
- [x] O Checklist Final A–H está anexado integralmente à descrição da PR.
- [x] O documento versionado deste checklist está referenciado na PR.
- [x] Os commits da documentação estão separados por responsabilidade.
- [x] Ruff, cobertura, `git diff --check` e `git status --short` fazem parte da
  validação final.
- [x] O PR não inclui mudanças em arquivos Python.
- [x] O conteúdo está pronto para revisão por pares antes do merge.

## Evidências da validação

```bash
python -m ruff check --select E4,E7,E9,F bot.py gerar_relatorio.py src tests scripts
python -m pytest -m unit -q
python -m pytest -m integration -q
python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80
git diff --check
git status --short
```

Resultados da rodada consolidada:

```text
unit: 151 passed
integration: 88 passed, 1 skipped, 1 xfailed
suíte completa: 254 passed, 1 skipped, 1 xfailed
cobertura global: 93,87%
operational_indicators.py: 100%
```

## Respostas rápidas para a banca

### Se amanhã surgir uma RN13, quantos lugares precisam mudar?

Com uma classificação existente, dois módulos de produção: o motor em
`validation_service.py` e o intervalo RN01–RN12 do Dicionário em
`report_writer.py`. Ranking, indicador 6, Excel e Markdown consomem
`regra_aplicada` genericamente. Testes e documentação também devem ser
atualizados. Se houver uma quinta classificação, abas e gráficos mudam.

### Por que o ganho estimado não é uma métrica de produção?

Porque usa duas constantes didáticas e não tempos observados. Para virar uma
medição real, o processo precisa de timestamps por etapa, baseline manual,
histórico persistente, separação de espera/retrabalho e análise estatística.

### Como provar que Excel e Markdown usam os mesmos números?

O orquestrador calcula uma vez e passa a mesma instância aos dois geradores. Um
teste intercepta ambas as chamadas, verifica identidade com `is` e os testes de
integração validam o conteúdo dos artefatos físicos.

### O que quebra sem `regra_aplicada`?

Os dois consumidores: o indicador 6 fica sem regra principal e o Ranking fica
sem linhas. Isso é um contrato explícito coberto por teste.

### Por que Ranking e Dicionário são abas separadas?

O Dashboard atende decisão rápida; o Ranking é uma tabela variável para
priorização; o Dicionário é um glossário estável. Separar evita poluição visual
e facilita filtros, auditoria e consulta.

### O que acontece se não houver registros?

`_percentual()` retorna `0.0` quando o total é zero, todos os indicadores ficam
zerados, não existe regra principal e não ocorre `ZeroDivisionError`.

### Os gráficos são imagens?

Não. São objetos `DoughnutChart` e `LineChart` do OpenPyXL e continuam
editáveis no Excel.

### Quais limitações permanecem para produção?

O ganho de tempo ainda é estimado, a atualização do workbook não é incremental,
os testes usam serviços externos simulados e a interface web é controlada, não
um ERP produtivo.
