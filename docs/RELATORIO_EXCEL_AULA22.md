# Relatório Excel da Aula 22

## Finalidade

O gerador da Aula 22 transforma uma pasta de trabalho com inspeções diárias em
um relatório executivo segregado por classificação. Essa execução é
independente do fluxo BotCity/DataPool: ela lê o XLSX fornecido, aplica RN01–RN12
em memória e grava um novo workbook com indicadores e gráficos nativos do
Excel.

Nenhuma planilha de entrada é alterada durante o processamento.

## Pré-requisitos

- Python 3.10 ou superior;
- arquivo de entrada no formato `.xlsx` ou `.xlsm`;
- `pandas` para leitura e consolidação;
- `openpyxl` para leitura, formatação e gráficos nativos.

## Preparação do ambiente

Na raiz do repositório:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-report.txt
```

No PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-report.txt
```

## Arquivo de entrada

A massa da atividade está em:

```text
dados_entrada/inspecao_lotes_10dias.xlsx
```

O leitor identifica dinamicamente as abas `Insp_DD_MM_AAAA` e lê a
`Base_Referencia`. Na massa homologada existem 10 abas diárias, com 25 linhas
cada, totalizando 250 registros.

As abas diárias devem conter, a partir do cabeçalho esperado, os campos:

```text
lote_id, produto, linha, turno, status, responsavel, data, observacao
```

## Execução

Com os caminhos padrão:

```bash
python gerar_relatorio.py
```

Com caminhos explícitos:

```bash
python gerar_relatorio.py \
  --entrada dados_entrada/inspecao_lotes_10dias.xlsx \
  --saida relatorios/relatorio_conferencia_lotes.xlsx \
  --log logs/execucao_relatorio.log
```

O comando retorna código `0` quando conclui e código `1` quando a entrada não
existe ou possui formato inválido. A saída é escrita primeiro em arquivo
temporário e substituída de forma atômica, evitando deixar um relatório parcial.

## Saídas

| Artefato | Caminho padrão | Finalidade |
|---|---|---|
| Relatório Excel | `relatorios/relatorio_conferencia_lotes.xlsx` | resultado segregado e dashboard executivo |
| Log final | `logs/execucao_relatorio.log` | entrada, contagens, duração, saída e regras acionadas |
| PDF da aba Resumo | `artefatos/dashboard_resumo.pdf` | evidência visual preparada para entrega |

Esses arquivos são gerados em runtime e não pertencem ao histórico Git. Devem
ser anexados ao canal da atividade, a um artefato de CI ou à release.

## Estrutura das seis abas

| Aba | Conteúdo |
|---|---|
| `Resumo` | indicadores executivos, gráfico de rosca e evolução dos dez dias |
| `Todos` | os 250 registros, em ordem cronológica e na ordem original de cada aba |
| `Válidos` | registros sem violação das RN01–RN12 |
| `Divergências` | inconsistências objetivas de referência, observação ou duplicidade diária |
| `Ambíguos` | status desconhecido que não pode ser normalizado com segurança |
| `Erros de Entrada` | ausência de campo obrigatório ou data inválida |

Não existe uma sétima aba técnica. As tabelas auxiliares dos gráficos ficam na
própria aba `Resumo`, fora de sua área de impressão.

## Classificações e precedência

Cada registro recebe uma única classificação final, embora possa conservar
mais de uma regra violada:

1. `Erro de Entrada`;
2. `Divergência`;
3. `Ambíguo`;
4. `Válido`.

A precedência impede dupla contagem nas quatro classes. Por isso, a soma dos
totais e dos percentuais sempre corresponde a 250 registros e 100%.

## RN01–RN12

| Regra | Validação |
|---|---|
| RN01 | lote informado |
| RN02 | produto informado |
| RN03 | linha informada |
| RN04 | status informado |
| RN05 | lote existente na base de referência |
| RN06–RN08 | preservadas pelo contrato da atividade, sem ocorrência específica na massa atual |
| RN09 | status conhecido ou normalizável |
| RN10 | observação obrigatória para lote reprovado |
| RN11 | repetição do mesmo lote dentro da mesma aba diária |
| RN12 | data presente e válida em `DD/MM/AAAA` |

Todas as regras acionadas permanecem em `regras_violadas` e no motivo, mesmo
quando a precedência determina uma classificação diferente.

## Normalização de status

Antes da classificação, o status é aparado, convertido para caixa alta e
normalizado:

| Entrada | Status normalizado |
|---|---|
| `OK` | `APROVADO` |
| `NOK` | `REPROVADO` |
| `APROVADO` | `APROVADO` |
| `REPROVADO` | `REPROVADO` |
| `PENDENTE` | `PENDENTE` |

Um valor diferente desses estados é classificado como ambíguo pela RN09; ele
não é convertido arbitrariamente em aprovação ou reprovação.

## Deduplicação diária

A RN11 usa a chave lógica `(aba_origem, lote_id)`. A primeira ocorrência do
lote no dia permanece disponível para as demais validações; cada ocorrência
posterior, na mesma aba diária, recebe RN11. O mesmo lote pode aparecer em
outro dia sem ser considerado duplicado.

O contexto é mantido por uma instância de `ValidationService` durante uma
execução e descartado antes do processamento de outro workbook.

## Dashboard

A aba `Resumo` permite conferir em uma única página:

- total geral;
- total e percentual de válidos;
- total e percentual de divergências;
- total e percentual de ambíguos;
- total e percentual de erros de entrada.

O gráfico de rosca representa as quatro classificações. O gráfico de linha
mostra, em ordem cronológica, divergências, ambiguidades, erros de entrada e o
total diário de problemas. Ambos são objetos nativos (`DoughnutChart` e
`LineChart`), referenciando células da própria aba, e não imagens coladas.

## Resultado homologado

Na massa fornecida, a execução atual produz:

| Classificação | Total | Percentual |
|---|---:|---:|
| Válido | 152 | 60,8% |
| Divergência | 50 | 20,0% |
| Ambíguo | 20 | 8,0% |
| Erro de Entrada | 28 | 11,2% |
| **Total** | **250** | **100,0%** |

O enunciado menciona 100 problemas propositais. As regras implementadas
identificam 98 registros não válidos porque uma linha pode acionar múltiplas
regras e recebe somente uma classificação final. Nenhuma regra ou contagem foi
forçada para reproduzir um total informado externamente.

## Log de execução

`logs/execucao_relatorio.log` registra uma linha por atributo da rodada:

```text
data_hora
arquivo_processado
total_registros
validos
divergencias
ambiguos
erros_entrada
duracao_segundos
relatorio
regras
```

O log não contém planilhas completas nem dados sigilosos.

## Perguntas prováveis da banca

### Se um novo dia for adicionado, o processamento é completo ou incremental?

Completo. O leitor redescobre todas as abas diárias, reprocessa os registros e
substitui o relatório final. Atualização incremental não faz parte desta versão.

### Qual é o custo de reprocessar todas as abas?

O custo cresce linearmente com a quantidade de linhas, além da leitura e da
gravação do XLSX. Para a massa de 250 registros, a execução local é curta e o
tempo real fica registrado no log.

### O gráfico temporal apresenta ocorrências ou registros únicos?

Apresenta registros classificados em cada dia. Cada linha aparece uma vez na
classificação final; uma linha com várias regras não é repetida no gráfico.

### Como comprovar que RN11 foi calculada por dia?

A chave inclui `aba_origem`. Os testes criam e verificam repetições dentro da
mesma aba, e o relatório mantém data, lote, classificação e motivo para
rastrear cada ocorrência.

### Uma linha com duas regras violadas é contada quantas vezes?

Uma vez nos indicadores e gráficos, conforme sua classificação final. As duas
regras continuam listadas no motivo e no log agregado por regra.

### Como evitar decisão incorreta olhando apenas o Resumo?

O Resumo orienta a priorização, mas a decisão deve ser confirmada nas abas
segregadas e na aba `Todos`, que preservam o registro, a classificação e o
motivo detalhado.

### O que precisa mudar para incluir uma quinta classificação?

É necessário definir sua precedência e regras no serviço, adicioná-la ao mapa
de abas, aos indicadores e às referências dos gráficos, além de ampliar os
testes. A mudança deve ser tratada como requisito de negócio, não apenas visual.

### Como o relatório seria distribuído automaticamente no futuro?

O comando pode ser executado em um job agendado e seus três artefatos publicados
no BotCity Maestro, GitHub Actions ou armazenamento corporativo. Envio por
e-mail e integração produtiva permanecem fora do escopo atual.

## Limitações

- processamento integral, sem atualização incremental;
- entrada restrita a `.xlsx` e `.xlsm` com a estrutura conhecida;
- saída estática, sem atualização automática depois de aberta;
- ausência de envio automático por e-mail;
- ausência de integração do relatório Excel com Maestro/DataPool;
- conferência executada sobre uma massa acadêmica controlada.

## Solução de problemas

| Sintoma | Verificação |
|---|---|
| `Arquivo de entrada inexistente` | confirme `--entrada` e o diretório atual |
| extensão rejeitada | use `.xlsx` ou `.xlsm` |
| módulo `pandas` ou `openpyxl` ausente | reinstale `requirements-report.txt` no ambiente ativo |
| aba não processada | confirme o padrão `Insp_DD_MM_AAAA` |
| coluna obrigatória ausente | confira o cabeçalho das abas diárias |
| totais inesperados | consulte `Motivo`, regras violadas e a precedência de classificação |
| relatório não abre | execute novamente; a escrita atômica evita manter uma saída parcial |

## Evidências da rodada final

Antes da entrega, execute o gerador e preserve externamente:

```text
relatorios/relatorio_conferencia_lotes.xlsx
logs/execucao_relatorio.log
artefatos/dashboard_resumo.pdf
```

Confirme que nenhum deles está rastreado:

```bash
git check-ignore \
  relatorios/relatorio_conferencia_lotes.xlsx \
  logs/execucao_relatorio.log \
  artefatos/dashboard_resumo.pdf
```

## Revisão cruzada

A revisão deve ser registrada no Pull Request que encerra a Issue #55. O
revisor deve conferir comandos, contagens, legibilidade do PDF, ausência dos
artefatos no Git e aderência desta documentação ao workbook efetivamente
gerado.
