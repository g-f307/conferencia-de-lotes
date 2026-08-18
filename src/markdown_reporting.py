"""Geração de resumos executivos em Markdown."""

from pathlib import Path

from src.operational_indicators import OperationalIndicators


def gerar_resumo_executivo(
    indicadores: OperationalIndicators,
    caminho_saida: Path,
) -> Path:
    """Gera um arquivo Markdown com o resumo executivo operacional em linguagem de negócios."""
    conteudo = f"""# Resumo Executivo: Conferência de Lotes

**Visão Geral:** O presente documento consolida os resultados operacionais da conferência de lotes referente aos últimos 10 dias de operação. A análise abrange o volume total processado e destaca os principais gargalos identificados pela automação.

## Indicadores Operacionais Chave

| Indicador | Resultado |
|---|---|
| Total de Registros Processados | {indicadores.total_registros} |
| Cadastros Válidos | {indicadores.validos_qtd} ({indicadores.validos_pct:.1f}%) |
| Divergências Identificadas | {indicadores.divergencias_qtd} ({indicadores.divergencias_pct:.1f}%) |
| Casos Ambíguos (Revisão Manual) | {indicadores.ambiguos_qtd} ({indicadores.ambiguos_pct:.1f}%) |
| Erros de Entrada | {indicadores.erros_entrada_qtd} ({indicadores.erros_entrada_pct:.1f}%) |
| Regra Mais Acionada | {indicadores.regra_mais_acionada_codigo} ({indicadores.regra_mais_acionada_qtd} ocorrências) |
| Taxa de Qualidade da Entrada | {indicadores.taxa_qualidade_entrada:.1f}% |
| Taxa de Revisão Humana | {indicadores.taxa_revisao_humana:.1f}% |
| Taxa de Retrabalho | {indicadores.taxa_retrabalho:.1f}% |
| Ganho Estimado de Tempo | {indicadores.ganho_estimado_tempo_minutos:.2f} min &#124; {indicadores.ganho_estimado_tempo_horas:.2f} h |

## Destaque Operacional

A infração mais recorrente no período foi a **{indicadores.regra_mais_acionada_codigo}** ({indicadores.regra_mais_acionada_nome}), com **{indicadores.regra_mais_acionada_qtd}** ocorrência(s). Este apontamento representa o principal gargalo operacional atual e deve ser o foco primário para ações de melhoria contínua junto à operação.

## Ganho Estimado de Tempo

Com a automação do processo de conferência, estimamos um ganho de tempo de **{indicadores.ganho_estimado_tempo_minutos} minutos** (aproximadamente **{indicadores.ganho_estimado_tempo_horas} horas**).
*Premissas numéricas utilizadas:* Foi considerado o tempo de 2,0 minutos para a execução humana por registro, contra 0,25 minutos (15 segundos) para a execução automatizada.

> **Observação Metodológica:** O ganho de tempo apresentado é uma estimativa didática para demonstrar o potencial da solução. Ele não representa uma medição cronometrada em ambiente de produção real. Para que se torne uma métrica de produção definitiva, seria necessário implementar a captura real do tempo de processamento em cada etapa da automação e realizar estudos de tempos e movimentos da equipe operacional na ferramenta de uso real.
"""
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)
    caminho_saida.write_text(conteudo, encoding="utf-8")
    return caminho_saida
