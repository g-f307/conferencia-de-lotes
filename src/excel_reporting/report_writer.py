"""Geração do relatório Excel segregado pelas classificações RN01-RN12."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.chart import DoughnutChart, LineChart, Reference
from openpyxl.chart.marker import DataPoint
from openpyxl.chart.shapes import GraphicalProperties
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
MAX_DASHBOARD_DAYS = 10

CLASSIFICATION_COLORS = {
    CLASSIFICACAO_VALIDO: "70AD47",
    CLASSIFICACAO_DIVERGENCIA: "C00000",
    CLASSIFICACAO_AMBIGUO: "F4B183",
    CLASSIFICACAO_ERRO_ENTRADA: "7F8C8D",
}

SUMMARY_CARDS = (
    ("A4:C4", "A5:C6", "Total de registros", None, "1F4E78"),
    ("E4:G4", "E5:G6", "Total de válidos", CLASSIFICACAO_VALIDO, "70AD47"),
    ("I4:K4", "I5:K6", "% de válidos", CLASSIFICACAO_VALIDO, "A9D18E"),
    (
        "A8:C8",
        "A9:C10",
        "Total de divergências",
        CLASSIFICACAO_DIVERGENCIA,
        "C00000",
    ),
    (
        "E8:G8",
        "E9:G10",
        "% de divergências",
        CLASSIFICACAO_DIVERGENCIA,
        "E26B6B",
    ),
    ("I8:K8", "I9:K10", "Total de ambíguos", CLASSIFICACAO_AMBIGUO, "ED7D31"),
    ("A12:C12", "A13:C14", "% de ambíguos", CLASSIFICACAO_AMBIGUO, "F4B183"),
    (
        "E12:G12",
        "E13:G14",
        "Total de erros de entrada",
        CLASSIFICACAO_ERRO_ENTRADA,
        "5B6573",
    ),
    (
        "I12:K12",
        "I13:K14",
        "% de erros de entrada",
        CLASSIFICACAO_ERRO_ENTRADA,
        "A5A5A5",
    ),
)


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
        _format_summary_sheet(workbook["Resumo"], ordered_records)
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


def _format_summary_sheet(
    sheet: Any,
    records: list[RegistroValidado],
) -> None:
    sheet.sheet_view.showGridLines = False
    sheet.merge_cells("A1:J2")
    title = sheet["A1"]
    title.value = "Relatório de Conferência de Lotes"
    title.fill = SUMMARY_TITLE_FILL
    title.font = Font(color="FFFFFF", bold=True, size=18)
    title.alignment = Alignment(horizontal="center", vertical="center")
    sheet.row_dimensions[1].height = 24

    totals = Counter(record.classificacao for record in records)
    total_records = len(records)
    _write_summary_cards(sheet, totals, total_records)
    _write_classification_table(sheet, totals)
    daily_rows = _write_daily_table(sheet, records)
    _add_doughnut_chart(sheet)
    _add_line_chart(sheet, daily_rows)
    _format_summary_layout(sheet)


def _write_summary_cards(
    sheet: Any,
    totals: Counter[str],
    total_records: int,
) -> None:
    for index, (label_range, value_range, label, classification, color) in enumerate(
        SUMMARY_CARDS
    ):
        sheet.merge_cells(label_range)
        sheet.merge_cells(value_range)
        label_cell = sheet[label_range.split(":")[0]]
        value_cell = sheet[value_range.split(":")[0]]
        is_percentage = index in {2, 4, 6, 8}

        label_cell.value = label
        label_cell.fill = PatternFill(fill_type="solid", fgColor=color)
        label_cell.font = Font(color="FFFFFF", bold=True, size=11)
        label_cell.alignment = Alignment(horizontal="center", vertical="center")

        count = total_records if classification is None else totals[classification]
        value_cell.value = (
            count / total_records if is_percentage and total_records else count
        )
        value_cell.fill = PatternFill(fill_type="solid", fgColor="F2F2F2")
        value_cell.font = Font(color="1F1F1F", bold=True, size=20)
        value_cell.alignment = Alignment(horizontal="center", vertical="center")
        if is_percentage:
            value_cell.number_format = "0.0%"


def _write_classification_table(sheet: Any, totals: Counter[str]) -> None:
    sheet["R1"] = "Classificação"
    sheet["S1"] = "Total"
    for row_index, classification in enumerate(CLASSIFICATION_SHEETS, start=2):
        sheet.cell(row=row_index, column=18, value=classification)
        sheet.cell(row=row_index, column=19, value=totals[classification])


def _write_daily_table(sheet: Any, records: list[RegistroValidado]) -> int:
    daily_counts: defaultdict[date, Counter[str]] = defaultdict(Counter)
    for record in records:
        reference = _reference_date(record, record.campos_originais)
        if isinstance(reference, date):
            daily_counts[reference][record.classificacao] += 1

    headers = (
        "Data",
        "Divergências",
        "Ambíguos",
        "Erros de Entrada",
        "Total de problemas",
    )
    for column_index, header in enumerate(headers, start=21):
        sheet.cell(row=1, column=column_index, value=header)

    dashboard_dates = sorted(daily_counts)[-MAX_DASHBOARD_DAYS:]
    for row_index, reference in enumerate(dashboard_dates, start=2):
        counts = daily_counts[reference]
        divergence = counts[CLASSIFICACAO_DIVERGENCIA]
        ambiguous = counts[CLASSIFICACAO_AMBIGUO]
        input_errors = counts[CLASSIFICACAO_ERRO_ENTRADA]
        values = (
            reference,
            divergence,
            ambiguous,
            input_errors,
            divergence + ambiguous + input_errors,
        )
        for column_index, value in enumerate(values, start=21):
            sheet.cell(row=row_index, column=column_index, value=value)
        sheet.cell(row=row_index, column=21).number_format = "dd/mm/yyyy"

    return len(dashboard_dates)


def _add_doughnut_chart(sheet: Any) -> None:
    chart = DoughnutChart()
    chart.title = "Distribuição por classificação"
    chart.style = 10
    chart.holeSize = 55
    chart.firstSliceAng = 270
    chart.legend.position = "r"
    chart.height = 8.2
    chart.width = 12.5

    data = Reference(sheet, min_col=19, min_row=1, max_row=5)
    labels = Reference(sheet, min_col=18, min_row=2, max_row=5)
    chart.add_data(data, titles_from_data=True)
    chart.set_categories(labels)
    chart.series[0].data_points = [
        DataPoint(
            idx=index,
            spPr=GraphicalProperties(solidFill=CLASSIFICATION_COLORS[classification]),
        )
        for index, classification in enumerate(CLASSIFICATION_SHEETS)
    ]
    sheet.add_chart(chart, "A17")


def _add_line_chart(sheet: Any, daily_rows: int) -> None:
    chart = LineChart()
    chart.title = "Evolução diária dos problemas"
    chart.style = 13
    chart.y_axis.title = "Registros"
    chart.x_axis.title = "Data"
    chart.x_axis.number_format = "dd/mm"
    chart.legend.position = "b"
    chart.height = 8.2
    chart.width = 15.5

    if daily_rows:
        data = Reference(
            sheet, min_col=22, max_col=25, min_row=1, max_row=daily_rows + 1
        )
        dates = Reference(sheet, min_col=21, min_row=2, max_row=daily_rows + 1)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(dates)
        colors = ("C00000", "ED7D31", "7F8C8D", "4472C4")
        for series, color in zip(chart.series, colors, strict=True):
            series.graphicalProperties.line.solidFill = color
            series.graphicalProperties.line.width = 24000
            series.marker.symbol = "circle"
            series.marker.size = 6

    sheet.add_chart(chart, "G17")


def _format_summary_layout(sheet: Any) -> None:
    for column in range(1, 17):
        sheet.column_dimensions[get_column_letter(column)].width = 12

    for row in (4, 8, 12):
        sheet.row_dimensions[row].height = 24
    for row in (5, 6, 9, 10, 13, 14):
        sheet.row_dimensions[row].height = 22

    sheet.freeze_panes = "A3"
    sheet.print_area = "A1:P34"
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 1
    sheet.sheet_view.zoomScale = 85


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
