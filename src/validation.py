from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping


EXPECTED_COLUMNS = (
    "lote_id",
    "produto",
    "linha",
    "turno",
    "status",
    "responsavel",
    "data",
    "observacao",
)

REQUIRED_COLUMNS = (
    "lote_id",
    "produto",
    "linha",
    "turno",
    "status",
    "responsavel",
    "data",
)

OFFICIAL_STATUSES = {"APROVADO", "REPROVADO"}
STATUS_ALIASES = {
    "OK": "APROVADO",
    "NOK": "REPROVADO",
}
AMBIGUOUS_STATUSES = {"PENDENTE", "EM ANALISE", "A REVISAR", "REVISAO"}


class ValidationError(Exception):
    """Erro deterministico de negocio em um item da fila."""


@dataclass(frozen=True)
class HumanReviewRequired:
    lote_id: str
    status_original: str
    reason: str = "Status ambiguo separado para revisao humana"


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_for_comparison(value: object) -> str:
    text = normalize_text(value).upper()
    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )


def normalize_status(status: object) -> str:
    normalized = normalize_for_comparison(status)
    return STATUS_ALIASES.get(normalized, normalized)


def validate_columns(item: Mapping[str, object]) -> None:
    missing = [column for column in EXPECTED_COLUMNS if column not in item]
    unexpected = [column for column in item if column not in EXPECTED_COLUMNS]

    if missing or unexpected:
        details = []
        if missing:
            details.append(f"colunas ausentes: {', '.join(missing)}")
        if unexpected:
            details.append(f"colunas inesperadas: {', '.join(unexpected)}")
        raise ValidationError("RN01 estrutura invalida - " + "; ".join(details))


def validate_required_fields(item: Mapping[str, object]) -> None:
    empty_fields = [column for column in REQUIRED_COLUMNS if not normalize_text(item.get(column))]
    if empty_fields:
        raise ValidationError("RN02 campos obrigatorios vazios: " + ", ".join(empty_fields))


def validate_lote_in_reference(item: Mapping[str, object], reference_lotes: Iterable[str]) -> None:
    lote_id = normalize_text(item.get("lote_id"))
    normalized_reference = {normalize_text(lote) for lote in reference_lotes}
    if lote_id not in normalized_reference:
        raise ValidationError(f"RN03 lote nao encontrado na base de referencia: {lote_id}")


def validate_status(status: object) -> str:
    normalized = normalize_status(status)
    if normalized in AMBIGUOUS_STATUSES:
        raise HumanReviewStatus(normalized)
    if normalized not in OFFICIAL_STATUSES:
        raise ValidationError(f"RN04 status nao oficial: {normalize_text(status)}")
    return normalized


def validate_observation_for_reproved(item: Mapping[str, object], status: str) -> None:
    if status == "REPROVADO" and not normalize_text(item.get("observacao")):
        raise ValidationError("RN07 lote reprovado exige observacao")


class HumanReviewStatus(Exception):
    def __init__(self, status: str) -> None:
        super().__init__(f"RN06 status ambiguo para revisao humana: {status}")
        self.status = status


def validate_lote(item: Mapping[str, object], reference_lotes: Iterable[str]) -> dict[str, str]:
    validate_columns(item)
    validate_required_fields(item)
    validate_lote_in_reference(item, reference_lotes)
    status = validate_status(item.get("status"))
    validate_observation_for_reproved(item, status)

    normalized = {column: normalize_text(item.get(column)) for column in EXPECTED_COLUMNS}
    normalized["status"] = status
    return normalized
