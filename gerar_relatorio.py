from __future__ import annotations

import argparse
from pathlib import Path
import sys

from src.excel_reporting.service import (
    DEFAULT_LOG_PATH,
    DEFAULT_REPORT_PATH,
    DEFAULT_WORKBOOK_PATH,
    gerar_relatorio_excel,
)


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = gerar_relatorio_excel(
            entrada=Path(args.entrada),
            saida=Path(args.saida),
            log_path=Path(args.log),
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    print("Relatorio gerado com sucesso")
    print(f"Arquivo processado: {result.entrada}")
    print(f"Total de registros: {result.total_registros}")
    print(f"Validos: {result.validos}")
    print(f"Divergencias: {result.divergencias}")
    print(f"Ambiguos: {result.ambiguos}")
    print(f"Erros de entrada: {result.erros_entrada}")
    print(f"Duracao: {result.duracao_segundos:.3f}s")
    print(f"Relatorio: {result.saida}")
    print(f"Log: {result.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
