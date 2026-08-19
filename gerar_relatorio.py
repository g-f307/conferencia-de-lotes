from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from src.excel_reporting.service import (
    DEFAULT_LOG_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_WORKBOOK_PATH,
    gerar_relatorio_excel,
)
from src.ml_audit import MLDecisionAudit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gera o relatorio Excel de conferencia de lotes."
    )
    parser.add_argument(
        "--entrada",
        default=str(DEFAULT_WORKBOOK_PATH),
        help="Caminho do workbook de entrada.",
    )
    parser.add_argument(
        "--saida",
        default=str(DEFAULT_REPORT_PATH),
        help="Caminho do relatorio Excel final.",
    )
    parser.add_argument(
        "--log",
        default=str(DEFAULT_LOG_PATH),
        help="Caminho do log da execucao.",
    )
    parser.add_argument(
        "--decisoes-ml",
        help=(
            "Resumo JSON do bot ou arquivo JSON contendo a lista de decisões de ML."
        ),
    )
    return parser


def load_ml_decisions(path: str | Path | None) -> list[MLDecisionAudit]:
    if path is None:
        return []
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Arquivo de decisões de ML inexistente: {source}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("ml_decisions", [])
    if not isinstance(payload, list):
        raise ValueError("Decisões de ML devem ser uma lista JSON")
    if not all(isinstance(item, dict) for item in payload):
        raise ValueError("Cada decisão de ML deve ser um objeto JSON")
    return [MLDecisionAudit.from_dict(item) for item in payload]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ml_decisions = load_ml_decisions(args.decisoes_ml)
        result = gerar_relatorio_excel(
            entrada=Path(args.entrada),
            saida=Path(args.saida),
            log_path=Path(args.log),
            ml_decisions=ml_decisions,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print("Relatorio gerado com sucesso")
    print(f"Arquivo processado: {result.entrada}")
    print(f"Total de registros: {result.total_registros}")
    print(f"Validos: {result.validos}")
    print(f"Divergencias: {result.divergencias}")
    print(f"Ambiguos: {result.ambiguos}")
    print(f"Erros de entrada: {result.erros_entrada}")
    print(f"Decisões de ML: {result.decisoes_ml}")
    print(f"Duracao: {result.duracao_segundos:.3f}s")
    print(f"Relatorio: {result.saida}")
    print(f"Log: {result.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
