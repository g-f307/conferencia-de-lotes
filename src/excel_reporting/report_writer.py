"""Geração do relatório Excel segregado pelas classificações RN01-RN12."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.validation_service import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
)


REPORT_SHEET_NAMES = (
    "Resumo",
    "Todos",
    "Válidos",
    "Divergências",
    "Ambíguos",
    "Erros de Entrada",
)

CLASSIFICATION_SHEETS = {
    CLASSIFICACAO_VALIDO: "Válidos",
    CLASSIFICACAO_DIVERGENCIA: "Divergências",
    CLASSIFICACAO_AMBIGUO: "Ambíguos",
    CLASSIFICACAO_ERRO_ENTRADA: "Erros de Entrada",
}

BUSINESS_COLUMNS = (
    "Data de referência",
    "Lote",
    "Produto",
    "Linha",
    "Turno",
    "Status",
    "Responsável",
    "Observação",
    "Classificação",
    "Motivo",
)

HEADER_FILL = PatternFill(fill_type="solid", fgColor="1F4E78")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SUMMARY_TITLE_FILL = PatternFill(fill_type="solid", fgColor="17365D")


def write_excel_report(
    registros: Iterable[RegistroValidado],
    output_path: str | Path,
) -> Path:
    """Grava um workbook com seis abas e dados segregados por classificação."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    ordered_records = sorted(registros, key=_record_order_key)
    _validate_classifications(ordered_records)
    all_rows = [_business_row(record) for record in ordered_records]

    with pd.ExcelWriter(destination, engine="openpyxl") as writer:
        pd.DataFrame().to_excel(writer, sheet_name="Resumo", index=False)
        _frame_from_rows(all_rows).to_excel(writer, sheet_name="Todos", index=False)

        for classification, sheet_name in CLASSIFICATION_SHEETS.items():
            rows = [
                row
                for record, row in zip(ordered_records, all_rows, strict=True)
                if record.classificacao == classification
            ]
            _frame_from_rows(rows).to_excel(writer, sheet_name=sheet_name, index=False)

        workbook = writer.book
        _format_summary_sheet(workbook["Resumo"])
        for sheet_name in REPORT_SHEET_NAMES[1:]:
            _format_data_sheet(workbook[sheet_name])

    return destination


def _frame_from_rows(rows: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(BUSINESS_COLUMNS))


def _business_row(record: RegistroValidado) -> dict[str, Any]:
    original = record.campos_originais
    return {
        "Data de referência": _reference_date(record, original),
        "Lote": _value(original, "lote_id"),
        "Produto": _value(original, "produto"),
        "Linha": _value(original, "linha"),
        "Turno": _value(original, "turno"),
        "Status": record.status_normalizado,
        "Responsável": _value(original, "responsavel"),
        "Observação": _value(original, "observacao"),
        "Classificação": record.classificacao,
        "Motivo": record.motivo,
    }


def _value(original: Mapping[str, Any], key: str) -> Any:
    value = original.get(key, "")
    return "" if _is_missing(value) else value


def _reference_date(
    record: RegistroValidado,
    original: Mapping[str, Any],
) -> date | str:
    value = original.get("data_referencia") or record.data_referencia
    if _is_missing(value):
        return ""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    for date_format in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return text


def _record_order_key(record: RegistroValidado) -> tuple[date, str, int]:
    reference = _reference_date(record, record.campos_originais)
    sortable_date = reference if isinstance(reference, date) else date.max
    line_order = record.linha_origem or _integer_value(
        record.campos_originais.get("ordem_linha")
    )
    return sortable_date, record.aba_origem, line_order


def _integer_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, bool) else False


def _validate_classifications(records: list[RegistroValidado]) -> None:
    invalid = sorted(
        {
            record.classificacao
            for record in records
            if record.classificacao not in CLASSIFICATION_SHEETS
        }
    )
    if invalid:
        values = ", ".join(repr(value) for value in invalid)
        raise ValueError(f"Classificações não suportadas pelo relatório: {values}")


def _format_summary_sheet(sheet: Any) -> None:
    sheet.sheet_view.showGridLines = False
    sheet.merge_cells("A1:J2")
    title = sheet["A1"]
    title.value = "Relatório de Conferência de Lotes"
    title.fill = SUMMARY_TITLE_FILL
    title.font = Font(color="FFFFFF", bold=True, size=18)
    title.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 24
    sheet.column_dimensions["A"].width = 22


def _format_data_sheet(sheet: Any) -> None:
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.sheet_view.showGridLines = False
    sheet.row_dimensions[1].height = 30

    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)

    for cell in sheet["A"][1:]:
        if isinstance(cell.value, (date, datetime)):
            cell.number_format = "dd/mm/yyyy"
            cell.alignment = Alignment(horizontal="center", vertical="top")

    for column_index, column_name in enumerate(BUSINESS_COLUMNS, start=1):
        values = [column_name]
        values.extend(
            "" if cell.value is None else str(cell.value)
            for cell in list(sheet.columns)[column_index - 1][1:]
        )
        content_width = max(len(value) for value in values) + 2
        maximum = 60 if column_name == "Motivo" else 40
        sheet.column_dimensions[get_column_letter(column_index)].width = min(
            max(content_width, 12), maximum
        )
