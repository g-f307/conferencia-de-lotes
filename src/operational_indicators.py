"""Módulo dedicado para consolidação matemática de indicadores operacionais."""

from collections import Counter
from dataclasses import dataclass

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.validation_service import MOTIVOS


def _percentual(parte: int, total: int) -> float:
    """Calcula proporção em percentual, com proteção contra divisão por zero."""
    if total == 0:
        return 0.0
    return round((parte / total) * 100.0, 2)


@dataclass(frozen=True)
class OperationalIndicators:
    """Consolidação matemática dos indicadores operacionais da automação."""

    total_registros: int
    validos_qtd: int
    validos_pct: float
    divergencias_qtd: int
    divergencias_pct: float
    ambiguos_qtd: int
    ambiguos_pct: float
    erros_entrada_qtd: int
    erros_entrada_pct: float
    regra_mais_acionada_codigo: str
    regra_mais_acionada_nome: str
    regra_mais_acionada_qtd: int
    taxa_qualidade_entrada: float
    taxa_revisao_humana: float
    taxa_retrabalho: float
    ganho_estimado_tempo_minutos: float
    ganho_estimado_tempo_horas: float


def calcular_indicadores(
    registros: list[RegistroValidado],
    tempo_manual_min: float = 2.0,
    tempo_auto_min: float = 0.25,
) -> OperationalIndicators:
    """Gera uma fonte única de verdade dos indicadores a partir da lista processada."""
    total = len(registros)

    validos_qtd = sum(1 for r in registros if r.classificacao == "Válido")
    divergencias_qtd = sum(1 for r in registros if r.classificacao == "Divergência")
    ambiguos_qtd = sum(1 for r in registros if r.classificacao == "Ambíguo")
    erros_entrada_qtd = sum(1 for r in registros if r.classificacao == "Erro de Entrada")

    regras_acionadas = [r.regra_aplicada for r in registros if r.regra_aplicada]

    if regras_acionadas:
        mais_acionada = Counter(regras_acionadas).most_common(1)[0]
        codigo = mais_acionada[0]
        qtd = mais_acionada[1]
        nome = MOTIVOS.get(codigo, "Regra desconhecida")
    else:
        codigo = "N/A"
        nome = "Nenhuma regra acionada"
        qtd = 0

    ganho_minutos = total * (tempo_manual_min - tempo_auto_min)

    return OperationalIndicators(
        total_registros=total,
        validos_qtd=validos_qtd,
        validos_pct=_percentual(validos_qtd, total),
        divergencias_qtd=divergencias_qtd,
        divergencias_pct=_percentual(divergencias_qtd, total),
        ambiguos_qtd=ambiguos_qtd,
        ambiguos_pct=_percentual(ambiguos_qtd, total),
        erros_entrada_qtd=erros_entrada_qtd,
        erros_entrada_pct=_percentual(erros_entrada_qtd, total),
        regra_mais_acionada_codigo=codigo,
        regra_mais_acionada_nome=nome,
        regra_mais_acionada_qtd=qtd,
        taxa_qualidade_entrada=_percentual(total - erros_entrada_qtd, total),
        taxa_revisao_humana=_percentual(ambiguos_qtd, total),
        taxa_retrabalho=_percentual(divergencias_qtd, total),
        ganho_estimado_tempo_minutos=round(ganho_minutos, 2),
        ganho_estimado_tempo_horas=round(ganho_minutos / 60.0, 2),
    )
