# Roteiro de apresentação — Aula 22

## Duração e divisão

Roteiro planejado para cinco minutos, sem executar etapas demoradas durante a
fala. O relatório, o log e o PDF devem estar abertos antes do início.

| Tempo | Conteúdo | Evidência em tela |
|---:|---|---|
| 0:00–0:35 | problema e objetivo | capa com “250 registros em 10 dias” |
| 0:35–1:15 | entrada e RN01–RN12 | workbook de entrada e tabela das regras |
| 1:15–1:50 | processamento e deduplicação | diagrama da arquitetura |
| 1:50–2:30 | quatro classificações e seis abas | abas do relatório final |
| 2:30–3:30 | indicadores e gráficos | aba `Resumo` ou seu PDF |
| 3:30–4:10 | rastreabilidade e validação | aba `Divergências` e log final |
| 4:10–4:40 | decisão sustentada | indicadores e evolução diária |
| 4:40–5:00 | limitações e próximos passos | slide final |

## Falas essenciais

### 1. Problema e objetivo

“A supervisão recebia inspeções distribuídas por dez abas, sem uma visão única
das inconsistências. Consolidamos 250 registros, aplicamos RN01–RN12 e geramos
um relatório executivo rastreável, sem alterar a planilha de origem.”

### 2. Entrada e regras

“O leitor descobre abas no padrão `Insp_DD_MM_AAAA`, consolida 25 registros por
dia e consulta a `Base_Referencia`. As regras verificam obrigatoriedade,
referência, status, observação, duplicidade diária e data.”

### 3. Deduplicação

“A RN11 considera lote e aba de origem. Assim, a repetição é detectada somente
dentro do mesmo dia. Reaparecer em outro dia não é erro por si só.”

### 4. Resultado

“Cada linha conserva todas as regras violadas, mas recebe uma classificação
única pela precedência Erro de Entrada, Divergência, Ambíguo e Válido. Isso
evita dupla contagem.”

### 5. Workbook

“O arquivo possui exatamente seis abas: Resumo, Todos, Válidos, Divergências,
Ambíguos e Erros de Entrada. O Resumo contém objetos nativos do Excel; os dados
detalhados permanecem disponíveis para conferência.”

### 6. Dashboard e decisão

“Na rodada homologada, 152 registros são válidos e 98 exigem atenção. O gráfico
de rosca mostra a distribuição e o gráfico de linha permite identificar em
quais dias os problemas se concentraram. A supervisora usa o Resumo para
priorizar e as abas segregadas para decidir.”

### 7. Rastreabilidade

“O log registra entrada, duração, totais e regras acionadas. O relatório e o log
são produzidos em runtime e ficam fora do Git; a entrega ocorre como artefato
ou anexo da release.”

### 8. Limitações e próximos passos

“A execução ainda é integral, não incremental, e não envia o arquivo
automaticamente. Como evolução, o comando pode ser agendado e publicar XLSX,
PDF e log no Maestro ou em armazenamento corporativo.”

## Materiais que devem estar preparados

1. branch e Pull Request revisado;
2. `dados_entrada/inspecao_lotes_10dias.xlsx`;
3. `relatorios/relatorio_conferencia_lotes.xlsx`;
4. `artefatos/dashboard_resumo.pdf`;
5. `logs/execucao_relatorio.log`;
6. `docs/RELATORIO_EXCEL_AULA22.md`;
7. página da release `v1.6.0`, quando publicada.

## Encerramento

“A entrega converte uma massa operacional fragmentada em uma visão executiva
reproduzível, sem perder o motivo de cada classificação. O dashboard orienta a
ação e as abas detalhadas sustentam a auditoria.”
