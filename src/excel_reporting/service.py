from __future__ import annotations

import os
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.report_writer import record_order_key, write_excel_report
from src.excel_reporting.validation_service import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    ValidationService,
)
from src.excel_reporting.workbook_reader import DEFAULT_WORKBOOK_PATH, read_workbook
from src.markdown_reporting import gerar_resumo_executivo
from src.operational_indicators import OperationalIndicators, calcular_indicadores

DEFAULT_REPORT_PATH = Path("relatorios") / "relatorio_conferencia_lotes.xlsx"
DEFAULT_LOG_PATH = Path("logs") / "execucao_relatorio.log"
VALID_EXTENSIONS = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class ReportExecutionResult:
    entrada: Path
    saida: Path
    log_path: Path
    total_registros: int
    validos: int
    divergencias: int
    ambiguos: int
    erros_entrada: int
    regras: dict[str, int]
    duracao_segundos: float
    registros_validados: list[dict[str, Any]]
    indicadores: OperationalIndicators | None = None

    @property
    def total_classificacoes(self) -> int:
        return self.validos + self.divergencias + self.ambiguos + self.erros_entrada


def gerar_relatorio_excel(
    entrada: str | Path = DEFAULT_WORKBOOK_PATH,
    saida: str | Path = DEFAULT_REPORT_PATH,
    *,
    log_path: str | Path = DEFAULT_LOG_PATH,
) -> ReportExecutionResult:
    """Executa o fluxo completo de leitura, validacao e geracao do relatorio."""
    started = time.perf_counter()
    input_path = Path(entrada)
    output_path = Path(saida)
    log_file = Path(log_path)
    temp_path = _temporary_output_path(output_path)
    temp_markdown_path = output_path.parent / f"{output_path.name}.md.tmp"

    _validate_input_path(input_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        source = read_workbook(input_path)
        service = ValidationService(source.lotes_referencia)
        validated = [
            service.validar_registro(
                record,
                aba_origem=str(record["aba_origem"]),
                linha_origem=int(record["ordem_linha"]),
            )
            for record in source.registros
        ]
        serialized = [record.to_dict() for record in validated]

        ordered_records = sorted(validated, key=record_order_key)
        indicators = calcular_indicadores(ordered_records)

        write_excel_report(ordered_records, indicators, temp_path)
        gerar_resumo_executivo(indicators, temp_markdown_path)

        os.replace(temp_path, output_path)
        markdown_path = output_path.parent / "resumo_executivo.md"
        os.replace(temp_markdown_path, markdown_path)

        duration = time.perf_counter() - started
        result = _build_result(
            input_path=input_path,
            output_path=output_path,
            log_file=log_file,
            validated=validated,
            serialized=serialized,
            indicators=indicators,
            duration=duration,
        )
        _write_log(result)
        return result
    except Exception:
        temp_path.unlink(missing_ok=True)
        temp_markdown_path.unlink(missing_ok=True)
        raise


def _validate_input_path(input_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(f"Arquivo de entrada inexistente: {input_path}")
    if input_path.suffix.lower() not in VALID_EXTENSIONS:
        extensions = ", ".join(sorted(VALID_EXTENSIONS))
        raise ValueError(
            f"Arquivo de entrada deve ter extensao Excel ({extensions}): {input_path}"
        )


def _temporary_output_path(output_path: Path) -> Path:
    suffix = output_path.suffix or ".xlsx"
    return output_path.with_name(f".{output_path.stem}.{uuid4().hex}.tmp{suffix}")


def _build_result(
    *,
    input_path: Path,
    output_path: Path,
    log_file: Path,
    validated: list[RegistroValidado],
    serialized: list[dict[str, Any]],
    indicators: OperationalIndicators,
    duration: float,
) -> ReportExecutionResult:
    classifications = Counter(record.classificacao for record in validated)
    rules: Counter[str] = Counter()
    for record in validated:
        rules.update(record.regras_violadas)

    return ReportExecutionResult(
        entrada=input_path,
        saida=output_path,
        log_path=log_file,
        total_registros=len(validated),
        validos=classifications[CLASSIFICACAO_VALIDO],
        divergencias=classifications[CLASSIFICACAO_DIVERGENCIA],
        ambiguos=classifications[CLASSIFICACAO_AMBIGUO],
        erros_entrada=classifications[CLASSIFICACAO_ERRO_ENTRADA],
        regras=dict(sorted(rules.items())),
        duracao_segundos=duration,
        registros_validados=serialized,
        indicadores=indicators,
    )


def _write_log(result: ReportExecutionResult) -> None:
    lines = [
        f"data_hora={datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"arquivo_processado={result.entrada}",
        f"total_registros={result.total_registros}",
        f"validos={result.validos}",
        f"divergencias={result.divergencias}",
        f"ambiguos={result.ambiguos}",
        f"erros_entrada={result.erros_entrada}",
        f"duracao_segundos={result.duracao_segundos:.3f}",
        f"relatorio={result.saida}",
        "regras="
        + ",".join(f"{rule}:{count}" for rule, count in result.regras.items()),
    ]
    if result.indicadores:
        lines.extend([
            f"validos_pct={result.indicadores.validos_pct}",
            f"divergencias_pct={result.indicadores.divergencias_pct}",
            f"ambiguos_pct={result.indicadores.ambiguos_pct}",
            f"erros_entrada_pct={result.indicadores.erros_entrada_pct}",
            f"taxa_qualidade_entrada={result.indicadores.taxa_qualidade_entrada}",
            f"taxa_revisao_humana={result.indicadores.taxa_revisao_humana}",
            f"taxa_retrabalho={result.indicadores.taxa_retrabalho}",
            f"regra_mais_acionada={result.indicadores.regra_mais_acionada_codigo}",
            f"regra_mais_acionada_descricao={result.indicadores.regra_mais_acionada_nome}",
            f"regra_mais_acionada_qtd={result.indicadores.regra_mais_acionada_qtd}",
            f"ganho_estimado_tempo_minutos={result.indicadores.ganho_estimado_tempo_minutos}",
            f"ganho_estimado_tempo_horas={result.indicadores.ganho_estimado_tempo_horas}",
        ])
    result.log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
