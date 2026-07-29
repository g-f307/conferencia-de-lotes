"""Geracao dos relatorios de evidencia da execucao."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _text(value: Any, fallback: str = "Nao informado") -> str:
    rendered = str(value or "").strip()
    return rendered or fallback


def _draw_page_footer(canvas: Any, document: Any) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#52606D"))
    canvas.drawString(18 * mm, 10 * mm, "Conferencia de lotes")
    canvas.drawRightString(
        A4[0] - 18 * mm,
        10 * mm,
        f"Pagina {document.page}",
    )
    canvas.restoreState()


def generate_evidence_pdf(
    summary: Mapping[str, Any],
    destination: Path,
    metadata: Mapping[str, Any],
    evidence_path: Path | None = None,
) -> Path:
    """Gera um PDF sem incluir credenciais ou valores sigilosos."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "EvidenceTitle",
        parent=styles["Title"],
        alignment=TA_CENTER,
        textColor=colors.HexColor("#073B4C"),
        fontSize=18,
        leading=22,
        spaceAfter=6 * mm,
    )
    heading_style = ParagraphStyle(
        "EvidenceHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#073B4C"),
        fontSize=12,
        leading=15,
        spaceBefore=4 * mm,
        spaceAfter=2 * mm,
    )
    body_style = ParagraphStyle(
        "EvidenceBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1F2933"),
    )

    document = SimpleDocTemplate(
        str(destination),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Relatorio de evidencias - Conferencia de lotes",
        author="bot-conferencia-de-lotes-v2",
    )
    story: list[Any] = [
        Paragraph("Relatorio de evidencias da automacao", title_style),
        Paragraph(
            "Documento gerado automaticamente ao final da execucao.",
            body_style,
        ),
        Spacer(1, 3 * mm),
    ]

    identification = [
        ["Campo", "Valor"],
        ["Bot", _text(metadata.get("bot_id"))],
        ["Execucao", _text(metadata.get("execution_id"))],
        ["DataPool", _text(metadata.get("datapool_label"))],
        ["Credencial Vault", _text(metadata.get("vault_label"))],
        [
            "Automacao web",
            "Habilitada" if metadata.get("web_enabled") else "Desabilitada",
        ],
    ]
    identification_table = Table(
        identification,
        colWidths=[46 * mm, 112 * mm],
        repeatRows=1,
    )
    identification_table.setStyle(_table_style())
    story.extend(
        [
            Paragraph("Identificacao", heading_style),
            identification_table,
            Paragraph("Resultado consolidado", heading_style),
        ]
    )

    result_data = [
        ["Indicador", "Valor"],
        ["Status", _text(summary.get("status"))],
        ["Mensagem", _text(summary.get("message"))],
        ["Total de itens", _text(summary.get("total_items"), "0")],
        ["Processados com sucesso", _text(summary.get("processed_items"), "0")],
        ["Falhas de negocio/tecnicas", _text(summary.get("failed_items"), "0")],
        ["Revisoes humanas", _text(summary.get("ambiguous_items"), "0")],
        ["Erros fatais registrados", str(len(summary.get("errors") or []))],
        ["Inicio", _text(summary.get("started_at"))],
        ["Fim", _text(summary.get("finished_at"))],
    ]
    result_table = Table(
        result_data,
        colWidths=[58 * mm, 100 * mm],
        repeatRows=1,
    )
    result_table.setStyle(_table_style())
    story.append(result_table)

    status = _text(summary.get("status"))
    if status == "PARTIALLY_COMPLETED":
        interpretation = (
            "A execucao terminou com sucesso operacional. O status parcial "
            "representa a classificacao dos itens de teste entre sucessos, "
            "falhas e revisoes humanas."
        )
    elif status == "SUCCESS":
        interpretation = "A execucao e todos os itens foram concluidos com sucesso."
    else:
        interpretation = (
            "A execucao registrou falha tecnica. Consulte o log estruturado "
            "associado ao identificador da execucao."
        )

    story.extend(
        [
            Paragraph("Parecer operacional", heading_style),
            Paragraph(interpretation, body_style),
            Paragraph("Validacoes registradas", heading_style),
            Paragraph(
                "O fluxo concluiu a recuperacao da credencial pelo Vault sem "
                "expor a senha, processou o DataPool configurado, persistiu o "
                "resumo JSON e gerou este documento no diretorio de resultados.",
                body_style,
            ),
        ]
    )

    if evidence_path is not None and evidence_path.is_file():
        image = Image(str(evidence_path))
        scale = min(
            (158 * mm) / image.imageWidth,
            (80 * mm) / image.imageHeight,
            1,
        )
        image.drawWidth = image.imageWidth * scale
        image.drawHeight = image.imageHeight * scale
        story.extend(
            [
                Paragraph("Evidencia da automacao web", heading_style),
                image,
                Spacer(1, 2 * mm),
                Paragraph(
                    f"Arquivo de origem: {evidence_path.name}",
                    body_style,
                ),
            ]
        )

    document.build(
        story,
        onFirstPage=_draw_page_footer,
        onLaterPages=_draw_page_footer,
    )
    return destination


def _table_style() -> TableStyle:
    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#073B4C")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LEADING", (0, 0), (-1, -1), 11),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]
    )
