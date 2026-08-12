from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
import unicodedata
from typing import Any

import pandas as pd


DAILY_SHEET_PATTERN = re.compile(r"^Insp_(\d{2})_(\d{2})_(\d{4})$")
BASE_REFERENCE_SHEET = "Base_Referencia"
DEFAULT_WORKBOOK_PATH = Path("dados_entrada") / "inspecao_lotes_10dias.xlsx"
DAILY_HEADER_ROW = 3
REFERENCE_HEADER_ROW = 2
DAILY_COLUMNS = (
    "lote_id",
    "produto",
    "linha",
    "turno",
    "status",
    "responsavel",
    "data",
    "observacao",
)


@dataclass(frozen=True)
class WorkbookReadResult:
    """Dados consolidados do workbook antes da validacao RN01-RN12."""

    registros: list[dict[str, Any]]
    base_referencia: list[dict[str, Any]]
    lotes_referencia: set[str]
    contagem_lotes_por_aba: dict[str, Counter[str]]

    @property
    def total_duplicidades_adicionais(self) -> int:
        return sum(1 for registro in self.registros if registro["duplicado_no_dia"])


def read_workbook(workbook_path: str | Path = DEFAULT_WORKBOOK_PATH) -> WorkbookReadResult:
    """Le as abas diarias e a base de referencia de um workbook configuravel."""
    path = Path(workbook_path)
    daily_sheet_names = list_daily_sheet_names(path)
    registros = _read_daily_records(path, daily_sheet_names)
    base_referencia = read_reference_base(path)
    lotes_referencia = {
        _normalize_text(row.get("lote_id"))
        for row in base_referencia
        if _normalize_text(row.get("lote_id"))
    }
    contagem_lotes_por_aba = _mark_daily_duplicates(registros)

    return WorkbookReadResult(
        registros=registros,
        base_referencia=base_referencia,
        lotes_referencia=lotes_referencia,
        contagem_lotes_por_aba=contagem_lotes_por_aba,
    )


def list_daily_sheet_names(workbook_path: str | Path) -> list[str]:
    """Retorna dinamicamente as abas no formato Insp_DD_MM_AAAA."""
    excel_file = pd.ExcelFile(workbook_path, engine="openpyxl")
    return [
        sheet_name
        for sheet_name in excel_file.sheet_names
        if DAILY_SHEET_PATTERN.fullmatch(sheet_name)
    ]


def read_reference_base(workbook_path: str | Path) -> list[dict[str, Any]]:
    """Le a aba Base_Referencia ignorando titulo e nota final."""
    frame = _read_sheet_table(workbook_path, BASE_REFERENCE_SHEET, REFERENCE_HEADER_ROW)
    if "lote_id" not in frame.columns:
        raise ValueError("Base_Referencia deve conter a coluna lote_id")

    frame = _drop_reference_non_records(frame)
    return _records_from_frame(frame)


def _read_daily_records(
    workbook_path: Path,
    daily_sheet_names: list[str],
) -> list[dict[str, Any]]:
    registros: list[dict[str, Any]] = []
    for sheet_name in daily_sheet_names:
        frame = _read_sheet_table(workbook_path, sheet_name, DAILY_HEADER_ROW)
        missing = [column for column in DAILY_COLUMNS if column not in frame.columns]
        if missing:
            raise ValueError(
                f"Aba {sheet_name} sem colunas obrigatorias: {', '.join(missing)}"
            )

        frame = _drop_daily_non_records(frame)
        frame = frame.loc[:, list(DAILY_COLUMNS)]
        data_referencia = _date_from_sheet_name(sheet_name)

        for ordem_linha, row in enumerate(_records_from_frame(frame), start=1):
            row["aba_origem"] = sheet_name
            row["data_referencia"] = data_referencia
            row["ordem_linha"] = ordem_linha
            registros.append(row)

    return registros


def _mark_daily_duplicates(registros: list[dict[str, Any]]) -> dict[str, Counter[str]]:
    counters: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for registro in registros:
        sheet_name = str(registro["aba_origem"])
        lote_id = _normalize_text(registro.get("lote_id"))
        if not lote_id:
            registro["duplicado_no_dia"] = False
            registro["ocorrencia_lote_no_dia"] = 0
            continue

        counters[sheet_name][lote_id] += 1
        registro["duplicado_no_dia"] = counters[sheet_name][lote_id] > 1
        registro["ocorrencia_lote_no_dia"] = counters[sheet_name][lote_id]

    return dict(counters)


def _read_sheet_table(
    workbook_path: str | Path,
    sheet_name: str,
    header_row: int,
) -> pd.DataFrame:
    frame = pd.read_excel(
        workbook_path,
        sheet_name=sheet_name,
        header=header_row - 1,
        dtype=object,
        engine="openpyxl",
    )
    frame = frame.rename(columns=_normalize_column_name)
    frame = frame.loc[:, [not str(column).startswith("unnamed_") for column in frame.columns]]
    frame = frame.dropna(how="all")
    return frame


def _drop_daily_non_records(frame: pd.DataFrame) -> pd.DataFrame:
    useful_rows = []
    for _, row in frame.iterrows():
        first_value = _normalize_for_comparison(row.iloc[0])
        useful_rows.append(
            not _is_empty_row(row)
            and not first_value.startswith("TOTAL DE REGISTROS")
            and not first_value.startswith("OBSERVACAO")
            and not first_value.startswith("NOTA")
        )
    return frame.loc[useful_rows].reset_index(drop=True)


def _drop_reference_non_records(frame: pd.DataFrame) -> pd.DataFrame:
    useful_rows = []
    for _, row in frame.iterrows():
        key_value = _normalize_text(row.get("lote_id"))
        marker = _normalize_for_comparison(key_value)
        useful_rows.append(
            bool(key_value)
            and not marker.startswith("TOTAL DE REGISTROS")
            and not marker.startswith("NOTA")
            and not marker.startswith("OBSERVACAO")
        )
    return frame.loc[useful_rows].reset_index(drop=True)


def _is_empty_row(row: pd.Series) -> bool:
    return all(not _normalize_text(value) for value in row)


def _records_from_frame(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append(
            {
                str(column): _clean_value(value)
                for column, value in row.items()
            }
        )
    return records


def _clean_value(value: Any) -> Any:
    if pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _date_from_sheet_name(sheet_name: str) -> str:
    match = DAILY_SHEET_PATTERN.fullmatch(sheet_name)
    if not match:
        raise ValueError(f"Aba diaria fora do padrao esperado: {sheet_name}")

    day, month, year = match.groups()
    return date(int(year), int(month), int(day)).isoformat()


def _normalize_column_name(value: object) -> str:
    normalized = _normalize_for_comparison(value).lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def _normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_for_comparison(value: object) -> str:
    text = _normalize_text(value).upper()
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
