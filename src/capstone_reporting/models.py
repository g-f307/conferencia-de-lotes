"""Contratos imutáveis do relatório híbrido do Capstone."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any

from src.ml_audit import MLDecisionAudit

REPORT_TYPE_BUSINESS = "BUSINESS"
REPORT_TYPE_INCIDENT = "OPERATIONAL_INCIDENT"
REPORT_TYPES = frozenset({REPORT_TYPE_BUSINESS, REPORT_TYPE_INCIDENT})

CLASSIFICACAO_VALIDO = "Válido"
CLASSIFICACAO_DIVERGENCIA = "Divergência"
CLASSIFICACAO_AMBIGUO = "Ambíguo"
CLASSIFICACAO_ERRO_ENTRADA = "Erro de Entrada"

STATUS_AVAILABLE = "AVAILABLE"
STATUS_UNAVAILABLE = "UNAVAILABLE"
STATUS_REVIEW = "PENDENTE_REVISAO"
STATUS_ITEM_ERROR = "ERRO_ITEM"
_SOURCE_STATUSES = frozenset({STATUS_AVAILABLE, "DEGRADED", STATUS_UNAVAILABLE})
_OPERATIONAL_STATUSES = frozenset(
    {"APROVADO", "DIVERGENCIA", STATUS_REVIEW, STATUS_ITEM_ERROR}
)

FALLBACK_DESCRIPTIONS = MappingProxyType(
    {
        "ml_desabilitado": "ML desabilitado por configuração",
        "observacao_ausente": "Observação necessária ao ML não informada",
        "indisponibilidade": "Serviço de ML indisponível",
        "timeout": "Tempo limite da operação excedido",
        "baixa_confianca": "Confiança do ML abaixo do limite configurado",
        "resposta_invalida": "Resposta inválida do serviço de ML",
        "multiplos_fallbacks": "Mais de um fallback ocorreu na execução",
        "desktop_unavailable_after_retry": (
            "Coleta desktop indisponível após todas as tentativas"
        ),
        "source_unavailable": "Fonte de dados indisponível",
        "authentication_failed": "Falha de autenticação na fonte",
        "invalid_source_data": "Fonte retornou dados inválidos",
        "task_creation_failed": "Não foi possível criar a task dependente",
        "fonte_indisponivel": "Uma ou mais fontes ficaram indisponíveis",
        "consolidation_failed": "A consolidação terminou com falha",
        "consolidation_canceled": "A consolidação foi cancelada",
        "consolidation_timeout": "A consolidação excedeu o tempo limite",
        "consolidation_task_creation_failed": (
            "Não foi possível criar a task de consolidação"
        ),
        "not_executed_due_upstream_failure": (
            "Etapa não executada devido a falha anterior"
        ),
        "pipeline_degradado": "Pipeline operando em modo degradado",
        "falha_operacional": "Falha operacional no pipeline",
        "item_irrecuperavel": "Item encaminhado para dead letter",
        "falha_item": "Falha isolada no processamento do item",
        "INVALID_STOCK_ITEM": "Registro de estoque inválido",
        "INVALID_SUPPLIER_ITEM": "Registro de fornecedor inválido",
        "INVALID_VALIDATION_ITEM": "Resultado de validação inválido",
    }
)

_SENSITIVE_KEY_MARKERS = frozenset(
    {
        "password",
        "senha",
        "token",
        "secret",
        "api_key",
        "apikey",
        "credential",
        "credencial",
        "observacao",
        "observation",
    }
)


class CapstoneReportInputError(ValueError):
    """O envelope de entrada não atende ao contrato do relatório."""


def _required_text(value: object, field_name: str) -> str:
    rendered = str(value or "").strip()
    if not rendered:
        raise CapstoneReportInputError(f"{field_name} deve ser informado")
    return rendered


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CapstoneReportInputError(f"{field_name} deve ser um objeto")
    return value


def _non_negative_int(value: object, field_name: str, default: int) -> int:
    if value is None:
        return default
    try:
        converted = int(value)
    except (TypeError, ValueError) as exc:
        raise CapstoneReportInputError(f"{field_name} deve ser inteiro") from exc
    if converted < 0:
        raise CapstoneReportInputError(f"{field_name} não pode ser negativo")
    return converted


def _optional_probability(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise CapstoneReportInputError("confianca_ml deve ser numérica") from exc
    if not 0 <= converted <= 1:
        raise CapstoneReportInputError("confianca_ml deve estar entre 0 e 1")
    return converted


def controlled_fallback(value: object, field_name: str = "motivo_fallback") -> str | None:
    """Aceita apenas códigos publicados pelo contrato, nunca texto livre."""
    rendered = str(value or "").strip()
    if not rendered:
        return None
    if rendered not in FALLBACK_DESCRIPTIONS:
        raise CapstoneReportInputError(f"{field_name} desconhecido: {rendered}")
    return rendered


def describe_fallback(value: str | None) -> str:
    if value is None:
        return "Não aplicável"
    return FALLBACK_DESCRIPTIONS[value]


def _text_from_sources(field_name: str, *sources: Mapping[str, Any]) -> str:
    for source in sources:
        rendered = str(source.get(field_name) or "").strip()
        if rendered:
            return rendered
    return ""


def _source_status(
    statuses: Mapping[str, str],
    *aliases: str,
) -> str:
    normalized = {str(key).casefold(): str(value).upper() for key, value in statuses.items()}
    for alias in aliases:
        if alias.casefold() in normalized:
            return normalized[alias.casefold()]
    return STATUS_UNAVAILABLE


def _safe_original_fields(validation: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = validation.get("campos_originais")
    if not isinstance(raw, Mapping):
        return MappingProxyType({})
    sanitized: dict[str, Any] = {}
    for key, value in raw.items():
        normalized_key = str(key).strip()
        folded_key = normalized_key.casefold()
        if any(marker in folded_key for marker in _SENSITIVE_KEY_MARKERS):
            continue
        sanitized[normalized_key] = value
    return MappingProxyType(sanitized)


def _normalized_classification(record: Mapping[str, Any]) -> str:
    value = str(record.get("classificacao") or "").strip()
    accepted = {
        CLASSIFICACAO_VALIDO,
        CLASSIFICACAO_DIVERGENCIA,
        CLASSIFICACAO_AMBIGUO,
        CLASSIFICACAO_ERRO_ENTRADA,
    }
    if value in accepted:
        return value
    status = str(record.get("status_operacional") or "").upper()
    if value and value not in _OPERATIONAL_STATUSES:
        raise CapstoneReportInputError(f"classificacao desconhecida: {value}")
    if status == "DIVERGENCIA":
        return CLASSIFICACAO_DIVERGENCIA
    if status == STATUS_ITEM_ERROR:
        return CLASSIFICACAO_ERRO_ENTRADA
    if status == STATUS_REVIEW:
        return CLASSIFICACAO_AMBIGUO
    return CLASSIFICACAO_VALIDO


@dataclass(frozen=True)
class HybridReportItem:
    """Linha comum aos quatro artefatos, sem texto livre sensível."""

    lote_id: str
    classificacao: str
    status_operacional: str
    origem_dados: tuple[str, ...]
    status_coleta_desktop: str
    status_coleta_web: str
    origem_decisao: str
    confianca_ml: float | None
    motivo_fallback: str | None
    modo_degradado: bool
    execution_id: str
    correlation_id: str
    task_id: str
    regras_violadas: tuple[str, ...] = ()
    regra_aplicada: str = ""
    campos_relatorio: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "origem_dados", tuple(self.origem_dados))
        object.__setattr__(self, "regras_violadas", tuple(self.regras_violadas))
        object.__setattr__(
            self,
            "campos_relatorio",
            MappingProxyType(dict(self.campos_relatorio)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lote_id": self.lote_id,
            "classificacao": self.classificacao,
            "status_operacional": self.status_operacional,
            "origem_dados": list(self.origem_dados),
            "status_coleta_desktop": self.status_coleta_desktop,
            "status_coleta_web": self.status_coleta_web,
            "origem_decisao": self.origem_decisao,
            "confianca_ml": self.confianca_ml,
            "motivo_fallback": self.motivo_fallback,
            "motivo_fallback_descricao": describe_fallback(self.motivo_fallback),
            "modo_degradado": self.modo_degradado,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "task_id": self.task_id,
            "regras_violadas": list(self.regras_violadas),
            "regra_aplicada": self.regra_aplicada,
        }


@dataclass(frozen=True)
class HybridReportSnapshot:
    """Fonte única para Excel, Markdown, JSON, PDF e alertas."""

    report_type: str
    status: str
    execution_id: str
    correlation_id: str
    root_task_id: str
    task_id: str
    generated_at: str
    source_statuses: Mapping[str, str]
    ml_status: str
    modo_degradado: bool
    motivo_fallback: str | None
    total_items: int
    processed_items: int
    failed_items: int
    review_items: int
    items: tuple[HybridReportItem, ...]
    ml_decisions: tuple[MLDecisionAudit, ...]
    degraded_duration_seconds: float = 0.0
    dead_letter_produced: bool = False
    failure_code: str | None = None

    def __post_init__(self) -> None:
        if self.report_type not in REPORT_TYPES:
            raise CapstoneReportInputError("report_type inválido")
        if self.status not in {"SUCCESS", "PARTIALLY_COMPLETED", "FAILED"}:
            raise CapstoneReportInputError("status do relatório inválido")
        object.__setattr__(
            self,
            "source_statuses",
            MappingProxyType(dict(self.source_statuses)),
        )
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "ml_decisions", tuple(self.ml_decisions))
        if self.report_type == REPORT_TYPE_BUSINESS and self.total_items != len(self.items):
            raise CapstoneReportInputError(
                "total_items deve corresponder aos itens do relatório de negócio"
            )

    @property
    def classification_counts(self) -> dict[str, int]:
        result = {
            CLASSIFICACAO_VALIDO: 0,
            CLASSIFICACAO_DIVERGENCIA: 0,
            CLASSIFICACAO_AMBIGUO: 0,
            CLASSIFICACAO_ERRO_ENTRADA: 0,
        }
        for item in self.items:
            result[item.classificacao] = result.get(item.classificacao, 0) + 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "report_type": self.report_type,
            "status": self.status,
            "execution_id": self.execution_id,
            "correlation_id": self.correlation_id,
            "root_task_id": self.root_task_id,
            "task_id": self.task_id,
            "generated_at": self.generated_at,
            "source_statuses": dict(self.source_statuses),
            "ml_status": self.ml_status,
            "modo_degradado": self.modo_degradado,
            "motivo_fallback": self.motivo_fallback,
            "motivo_fallback_descricao": describe_fallback(self.motivo_fallback),
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "failed_items": self.failed_items,
            "review_items": self.review_items,
            "classification_counts": self.classification_counts,
            "ml_decisions": [decision.to_dict() for decision in self.ml_decisions],
            "degraded_duration_seconds": self.degraded_duration_seconds,
            "dead_letter_produced": self.dead_letter_produced,
            "failure_code": self.failure_code,
            "items": [item.to_dict() for item in self.items],
        }


def build_report_snapshot(payload: Mapping[str, Any]) -> HybridReportSnapshot:
    """Valida o envelope final e cria a visão única dos artefatos."""
    report_type = _required_text(payload.get("report_type"), "report_type").upper()
    consolidation = _mapping(payload.get("consolidation_result"), "consolidation_result")
    ml_result = _mapping(payload.get("ml_result"), "ml_result")
    consolidation_payload = _mapping(
        consolidation.get("payload", {}),
        "consolidation_result.payload",
    )
    ml_payload = _mapping(ml_result.get("payload", {}), "ml_result.payload")

    source_statuses_raw = payload.get("source_statuses", consolidation.get("source_statuses", {}))
    source_statuses_mapping = _mapping(source_statuses_raw, "source_statuses")
    source_statuses = {
        str(key): _required_text(value, f"source_statuses.{key}").upper()
        for key, value in source_statuses_mapping.items()
    }
    invalid_source_statuses = {
        value for value in source_statuses.values() if value not in _SOURCE_STATUSES
    }
    if invalid_source_statuses:
        raise CapstoneReportInputError(
            "source_statuses contém estado desconhecido: "
            + ", ".join(sorted(invalid_source_statuses))
        )

    execution_id = _required_text(
        _text_from_sources("execution_id", payload, ml_result, consolidation),
        "execution_id",
    )
    correlation_id = _required_text(
        _text_from_sources("correlation_id", payload, ml_result, consolidation),
        "correlation_id",
    )
    root_task_id = _required_text(
        _text_from_sources("root_task_id", payload, ml_result, consolidation),
        "root_task_id",
    )
    task_id = _required_text(
        _text_from_sources("task_id", payload, ml_result, consolidation),
        "task_id",
    )

    records_raw = consolidation_payload.get("records", [])
    failures_raw = consolidation_payload.get("item_failures", [])
    if not isinstance(records_raw, list) or not all(
        isinstance(record, Mapping) for record in records_raw
    ):
        raise CapstoneReportInputError("payload.records deve ser uma lista de objetos")
    if not isinstance(failures_raw, list) or not all(
        isinstance(failure, Mapping) for failure in failures_raw
    ):
        raise CapstoneReportInputError("payload.item_failures deve ser uma lista de objetos")

    ml_decisions = _ml_audits(ml_payload)
    decisions = {decision.lote_id: decision.to_dict() for decision in ml_decisions}
    decisions.update(_decision_index(ml_payload))
    items = [
        _build_business_item(
            record,
            decisions.get(str(record.get("lote_id") or "").strip()),
            source_statuses,
            execution_id,
            correlation_id,
            task_id,
        )
        for record in records_raw
    ]
    items.extend(
        _build_failure_item(
            failure,
            index,
            source_statuses,
            execution_id,
            correlation_id,
            task_id,
        )
        for index, failure in enumerate(failures_raw, start=1)
    )

    derived_failed = len(failures_raw) + sum(
        str(record.get("status_operacional") or "").upper() == STATUS_ITEM_ERROR
        for record in records_raw
    )
    derived_review = sum(item.status_operacional == STATUS_REVIEW for item in items)
    default_total = len(items) if report_type == REPORT_TYPE_BUSINESS else int(
        consolidation.get("expected_items") or 0
    )
    total_items = _non_negative_int(
        consolidation_payload.get("total_items", consolidation.get("expected_items")),
        "total_items",
        default_total,
    )
    processed_items = _non_negative_int(
        consolidation_payload.get("processed_items", consolidation.get("processed_items")),
        "processed_items",
        len(records_raw),
    )
    failed_items = _non_negative_int(
        consolidation_payload.get("failed_items", consolidation.get("failed_items")),
        "failed_items",
        derived_failed,
    )
    review_items = _non_negative_int(
        consolidation_payload.get("review_items", consolidation.get("review_items")),
        "review_items",
        derived_review,
    )

    if report_type == REPORT_TYPE_BUSINESS:
        expected = {
            "total_items": (total_items, len(items)),
            "processed_items": (processed_items, len(records_raw)),
            "failed_items": (failed_items, derived_failed),
            "review_items": (review_items, derived_review),
        }
        for field_name, (declared, derived) in expected.items():
            if declared != derived:
                raise CapstoneReportInputError(
                    f"{field_name} inconsistente: declarado={declared}, calculado={derived}"
                )
    if processed_items > total_items:
        raise CapstoneReportInputError("processed_items não pode exceder total_items")
    if failed_items > total_items:
        raise CapstoneReportInputError("failed_items não pode exceder total_items")
    if review_items > total_items:
        raise CapstoneReportInputError("review_items não pode exceder total_items")

    desktop_status = _source_status(
        source_statuses,
        "desktop",
        "estoque",
        "estoque-desktop-v1",
    )
    web_status = _source_status(
        source_statuses,
        "web",
        "pedidos",
        "fornecedores-web-v1",
    )
    ml_status = str(ml_result.get("status") or "NOT_EXECUTED").upper()
    fallback = controlled_fallback(
        payload.get("motivo_fallback")
        or ml_result.get("motivo_fallback")
        or consolidation.get("motivo_fallback")
    )
    degraded = bool(
        payload.get("modo_degradado")
        or consolidation.get("modo_degradado")
        or ml_result.get("modo_degradado")
        or desktop_status != STATUS_AVAILABLE
        or web_status != STATUS_AVAILABLE
    )
    duration = float(payload.get("degraded_duration_seconds") or 0)
    if duration < 0:
        raise CapstoneReportInputError(
            "degraded_duration_seconds não pode ser negativo"
        )

    return HybridReportSnapshot(
        report_type=report_type,
        status=str(consolidation.get("status") or "FAILED").upper(),
        execution_id=execution_id,
        correlation_id=correlation_id,
        root_task_id=root_task_id,
        task_id=task_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_statuses=source_statuses,
        ml_status=ml_status,
        modo_degradado=degraded,
        motivo_fallback=fallback,
        total_items=total_items,
        processed_items=processed_items,
        failed_items=failed_items,
        review_items=review_items,
        items=tuple(items),
        ml_decisions=ml_decisions,
        degraded_duration_seconds=duration,
        dead_letter_produced=_dead_letter_produced(
            payload,
            consolidation,
            consolidation_payload,
            ml_result,
            ml_payload,
        ),
        failure_code=controlled_fallback(
            consolidation.get("failure_code"),
            "failure_code",
        ),
    )


def _decision_index(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    records = payload.get("records", [])
    if isinstance(records, list):
        for record in records:
            if not isinstance(record, Mapping):
                continue
            lote_id = str(record.get("lote_id") or "").strip()
            decision = record.get("decisao_ml")
            if lote_id and isinstance(decision, Mapping):
                index[lote_id] = decision
    decisions = payload.get("ml_decisions", [])
    if isinstance(decisions, list):
        for decision in decisions:
            if not isinstance(decision, Mapping):
                continue
            lote_id = str(decision.get("lote_id") or "").strip()
            if lote_id:
                index[lote_id] = decision
    return index


def _ml_audits(payload: Mapping[str, Any]) -> tuple[MLDecisionAudit, ...]:
    raw_decisions = payload.get("ml_decisions", [])
    if not isinstance(raw_decisions, list):
        raise CapstoneReportInputError("payload.ml_decisions deve ser uma lista")
    decisions: list[MLDecisionAudit] = []
    for raw in raw_decisions:
        if not isinstance(raw, Mapping):
            raise CapstoneReportInputError("cada decisão de ML deve ser um objeto")
        try:
            decisions.append(MLDecisionAudit.from_dict(raw))
        except (TypeError, ValueError) as exc:
            raise CapstoneReportInputError(f"decisão de ML inválida: {exc}") from exc
    return tuple(decisions)


def _build_business_item(
    record: Mapping[str, Any],
    decision: Mapping[str, Any] | None,
    source_statuses: Mapping[str, str],
    execution_id: str,
    correlation_id: str,
    task_id: str,
) -> HybridReportItem:
    lote_id = _required_text(record.get("lote_id"), "lote_id")
    validation = record.get("validacao")
    validation_mapping = validation if isinstance(validation, Mapping) else {}
    origins = record.get("origens_consultadas", [])
    if not isinstance(origins, (list, tuple)):
        origins = []
    rules = record.get("regras_violadas", [])
    if not isinstance(rules, (list, tuple)):
        rules = []
    fallback = None
    decision_origin = "regras_deterministicas"
    confidence = None
    if decision:
        decision_origin = str(decision.get("origem_decisao") or "fallback").strip()
        if decision_origin not in {"ml", "fallback"}:
            raise CapstoneReportInputError(
                f"origem_decisao desconhecida para o lote {lote_id}"
            )
        confidence = _optional_probability(
            decision.get("confianca_ml", decision.get("probabilidade"))
        )
        fallback = controlled_fallback(decision.get("motivo_fallback"))
        if decision_origin == "fallback" and fallback is None:
            raise CapstoneReportInputError(
                f"motivo_fallback ausente para o lote {lote_id}"
            )
        if decision_origin == "ml" and fallback is not None:
            raise CapstoneReportInputError(
                f"motivo_fallback não se aplica à decisão ML do lote {lote_id}"
            )
    missing_sources = record.get("fontes_ausentes", [])
    if not fallback and isinstance(missing_sources, (list, tuple)) and missing_sources:
        fallback = "fonte_indisponivel"

    report_fields = dict(_safe_original_fields(validation_mapping))
    report_fields["lote_id"] = lote_id
    stock = record.get("estoque")
    order = record.get("pedido")
    if isinstance(stock, Mapping):
        report_fields.setdefault("produto", stock.get("produto"))
    if isinstance(order, Mapping):
        report_fields.setdefault("produto", order.get("produto"))

    desktop_status = _source_status(
        source_statuses,
        "desktop",
        "estoque",
        "estoque-desktop-v1",
    )
    web_status = _source_status(
        source_statuses,
        "web",
        "pedidos",
        "fornecedores-web-v1",
    )
    if not fallback and (
        desktop_status != STATUS_AVAILABLE or web_status != STATUS_AVAILABLE
    ):
        fallback = "fonte_indisponivel"
    operational_status = _required_text(
        record.get("status_operacional"),
        "status_operacional",
    ).upper()
    if operational_status not in _OPERATIONAL_STATUSES:
        raise CapstoneReportInputError(
            f"status_operacional desconhecido para o lote {lote_id}"
        )
    return HybridReportItem(
        lote_id=lote_id,
        classificacao=_normalized_classification(record),
        status_operacional=operational_status,
        origem_dados=tuple(str(origin) for origin in origins),
        status_coleta_desktop=desktop_status,
        status_coleta_web=web_status,
        origem_decisao=decision_origin,
        confianca_ml=confidence,
        motivo_fallback=fallback,
        modo_degradado=bool(
            record.get("modo_degradado")
            or desktop_status != STATUS_AVAILABLE
            or web_status != STATUS_AVAILABLE
        ),
        execution_id=execution_id,
        correlation_id=correlation_id,
        task_id=task_id,
        regras_violadas=tuple(str(rule) for rule in rules),
        regra_aplicada=str(record.get("regra_aplicada") or ""),
        campos_relatorio=report_fields,
    )


def _build_failure_item(
    failure: Mapping[str, Any],
    index: int,
    source_statuses: Mapping[str, str],
    execution_id: str,
    correlation_id: str,
    task_id: str,
) -> HybridReportItem:
    source = str(failure.get("fonte") or "desconhecida").strip()
    return HybridReportItem(
        lote_id=str(failure.get("lote_id") or f"FALHA-{index}").strip(),
        classificacao=CLASSIFICACAO_ERRO_ENTRADA,
        status_operacional=STATUS_ITEM_ERROR,
        origem_dados=(source,),
        status_coleta_desktop=_source_status(
            source_statuses,
            "desktop",
            "estoque",
            "estoque-desktop-v1",
        ),
        status_coleta_web=_source_status(
            source_statuses,
            "web",
            "pedidos",
            "fornecedores-web-v1",
        ),
        origem_decisao="regras_deterministicas",
        confianca_ml=None,
        motivo_fallback=controlled_fallback(
            failure.get("codigo") or "falha_item",
            "item_failure.codigo",
        ),
        modo_degradado=True,
        execution_id=execution_id,
        correlation_id=correlation_id,
        task_id=task_id,
        campos_relatorio={"lote_id": failure.get("lote_id") or f"FALHA-{index}"},
    )


def _dead_letter_produced(*sources: Mapping[str, Any]) -> bool:
    for source in sources:
        if source.get("dead_letter_produced") is True:
            return True
        for field_name in ("artifacts", "available_artifacts"):
            artifacts = source.get(field_name, ())
            if not isinstance(artifacts, (list, tuple)):
                continue
            if any(_is_dead_letter_artifact(artifact) for artifact in artifacts):
                return True
    return False


def _is_dead_letter_artifact(artifact: object) -> bool:
    if isinstance(artifact, Mapping):
        candidates = (
            artifact.get("type"),
            artifact.get("name"),
            artifact.get("path"),
            artifact.get("artifact_name"),
        )
    else:
        candidates = (artifact,)
    normalized = " ".join(str(value or "").casefold() for value in candidates)
    return "dead_letter" in normalized or "dead-letter" in normalized


__all__ = [
    "FALLBACK_DESCRIPTIONS",
    "REPORT_TYPE_BUSINESS",
    "REPORT_TYPE_INCIDENT",
    "CapstoneReportInputError",
    "HybridReportItem",
    "HybridReportSnapshot",
    "build_report_snapshot",
    "controlled_fallback",
    "describe_fallback",
]
