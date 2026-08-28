"""Cruzamento de estoque, pedidos e validações sem dependências externas."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping

from src.desktop_stock.models import StockRecord
from src.excel_reporting import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    RegistroValidado,
)
from src.supplier_portal import SupplierOrder, SupplierPortalDataError

from .models import (
    STATUS_APROVADO,
    STATUS_DIVERGENCIA,
    STATUS_ERRO_ITEM,
    STATUS_REVISAO,
    FalhaItemConsolidacao,
    RegistroConsolidado,
    ResultadoConsolidacao,
)

FONTE_ESTOQUE = "desktop"
FONTE_PEDIDOS = "web"
FONTE_VALIDACAO = "motor_rn01_rn12"

VERIFICACAO_ESTOQUE_AUSENTE = "CONS01"
VERIFICACAO_PEDIDO_AUSENTE = "CONS02"
VERIFICACAO_PRODUTO_DIVERGENTE = "CONS03"
VERIFICACAO_ESTOQUE_INSUFICIENTE = "CONS04"
VERIFICACAO_VALIDACAO_AUSENTE = "CONS05"
VERIFICACAO_ESTOQUE_DUPLICADO = "CONS06"
VERIFICACAO_VALIDACAO_DUPLICADA = "CONS07"

_VERIFICACOES_DEGRADADAS = {
    VERIFICACAO_ESTOQUE_AUSENTE,
    VERIFICACAO_PEDIDO_AUSENTE,
    VERIFICACAO_VALIDACAO_AUSENTE,
    VERIFICACAO_ESTOQUE_DUPLICADO,
    VERIFICACAO_VALIDACAO_DUPLICADA,
}

SOURCE_AVAILABLE = "AVAILABLE"
SOURCE_DEGRADED = "DEGRADED"
SOURCE_UNAVAILABLE = "UNAVAILABLE"


class ConsolidationInputError(ValueError):
    """Erro estrutural geral que impede interpretar o contrato de entrada."""


def _text(value: object) -> str:
    return str(value or "").strip()


def _stock_from_mapping(data: Mapping[str, object]) -> StockRecord:
    required = (
        "lote_id",
        "produto",
        "quantidade_disponivel",
        "localizacao",
        "status_estoque",
        "atualizado_em",
    )
    missing = [field for field in required if not _text(data.get(field))]
    if missing:
        raise ValueError("campos de estoque ausentes: " + ", ".join(missing))
    if isinstance(data["quantidade_disponivel"], bool):
        raise TypeError("quantidade_disponivel inválida")
    try:
        quantity = int(data["quantidade_disponivel"])
    except (TypeError, ValueError) as exc:
        raise ValueError("quantidade_disponivel inválida") from exc
    if quantity < 0:
        raise ValueError("quantidade_disponivel não pode ser negativa")
    return StockRecord(
        lote_id=_text(data["lote_id"]),
        produto=_text(data["produto"]),
        quantidade_disponivel=quantity,
        localizacao=_text(data["localizacao"]),
        status_estoque=_text(data["status_estoque"]),
        atualizado_em=_text(data["atualizado_em"]),
    )


def _coerce_source_status(value: object) -> str:
    normalized = _text(value).upper()
    return (
        normalized
        if normalized in {SOURCE_AVAILABLE, SOURCE_DEGRADED, SOURCE_UNAVAILABLE}
        else SOURCE_UNAVAILABLE
    )


def _records_from_envelope(
    envelope: Mapping[str, object],
    *,
    source: str,
) -> tuple[list[object], str]:
    payload = envelope.get("payload")
    if not isinstance(payload, Mapping):
        raise ConsolidationInputError(f"payload da fonte {source} é inválido")
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ConsolidationInputError(f"records da fonte {source} deve ser uma lista")
    return records, _coerce_source_status(payload.get("source_status"))


class ConsolidationService:
    """Consolida itens de forma determinística e sem chamar o ML."""

    def consolidate_envelopes(
        self,
        desktop_result: Mapping[str, object],
        web_result: Mapping[str, object],
        validated_records: Iterable[RegistroValidado],
    ) -> ResultadoConsolidacao:
        desktop_records, desktop_status = _records_from_envelope(
            desktop_result,
            source=FONTE_ESTOQUE,
        )
        web_records, web_status = _records_from_envelope(
            web_result,
            source=FONTE_PEDIDOS,
        )
        return self.consolidate(
            desktop_records,
            web_records,
            validated_records,
            source_statuses={
                FONTE_ESTOQUE: desktop_status,
                FONTE_PEDIDOS: web_status,
            },
        )

    def consolidate(
        self,
        stock_records: Iterable[StockRecord | Mapping[str, object]],
        supplier_orders: Iterable[SupplierOrder | Mapping[str, object]],
        validated_records: Iterable[RegistroValidado],
        *,
        source_statuses: Mapping[str, str] | None = None,
    ) -> ResultadoConsolidacao:
        source_statuses = source_statuses or {}
        statuses = {
            FONTE_ESTOQUE: _coerce_source_status(
                source_statuses.get(FONTE_ESTOQUE, SOURCE_AVAILABLE)
            ),
            FONTE_PEDIDOS: _coerce_source_status(
                source_statuses.get(FONTE_PEDIDOS, SOURCE_AVAILABLE)
            ),
        }
        failures: list[FalhaItemConsolidacao] = []
        stocks = self._parse_stocks(stock_records, failures)
        orders = self._parse_orders(supplier_orders, failures)
        validations = self._index_validations(validated_records, failures)

        stocks_by_lote: dict[str, list[StockRecord]] = defaultdict(list)
        orders_by_lote: dict[str, list[SupplierOrder]] = defaultdict(list)
        for stock in stocks:
            stocks_by_lote[stock.lote_id].append(stock)
        for order in orders:
            orders_by_lote[order.lote_id].append(order)

        lotes = sorted(set(stocks_by_lote) | set(orders_by_lote) | set(validations))
        consolidated: list[RegistroConsolidado] = []
        for lote_id in lotes:
            stock_items = stocks_by_lote.get(lote_id, [])
            order_items = orders_by_lote.get(lote_id, [])
            validation_items = validations.get(lote_id, [])
            if order_items:
                for order in order_items:
                    consolidated.append(
                        self._consolidate_item(
                            lote_id,
                            stock_items,
                            order,
                            validation_items,
                            statuses,
                        )
                    )
            else:
                consolidated.append(
                    self._consolidate_item(
                        lote_id,
                        stock_items,
                        None,
                        validation_items,
                        statuses,
                    )
                )

        unavailable = sum(value == SOURCE_UNAVAILABLE for value in statuses.values())
        degraded = any(value != SOURCE_AVAILABLE for value in statuses.values())
        if unavailable == len(statuses):
            result_status = "FAILED"
        elif degraded or failures or any(item.modo_degradado for item in consolidated):
            result_status = "PARTIALLY_COMPLETED"
        else:
            result_status = "SUCCESS"
        return ResultadoConsolidacao(
            status=result_status,
            registros=tuple(consolidated),
            falhas_itens=tuple(failures),
            status_fontes=statuses,
            modo_degradado=result_status != "SUCCESS",
            ml_consultado=False,
        )

    @staticmethod
    def _parse_stocks(
        records: Iterable[StockRecord | Mapping[str, object]],
        failures: list[FalhaItemConsolidacao],
    ) -> list[StockRecord]:
        parsed: list[StockRecord] = []
        for index, record in enumerate(records):
            try:
                if not isinstance(record, (StockRecord, Mapping)):
                    raise TypeError("item de estoque deve ser um objeto ou mapeamento")
                data = record.to_dict() if isinstance(record, StockRecord) else record
                parsed.append(_stock_from_mapping(data))
            except (AttributeError, TypeError, ValueError) as exc:
                lote_id = _text(record.get("lote_id")) if isinstance(record, Mapping) else ""
                failures.append(
                    FalhaItemConsolidacao(
                        fonte=FONTE_ESTOQUE,
                        indice=index,
                        lote_id=lote_id or None,
                        codigo="INVALID_STOCK_ITEM",
                        mensagem=str(exc),
                    )
                )
        return parsed

    @staticmethod
    def _parse_orders(
        records: Iterable[SupplierOrder | Mapping[str, object]],
        failures: list[FalhaItemConsolidacao],
    ) -> list[SupplierOrder]:
        parsed: list[SupplierOrder] = []
        for index, record in enumerate(records):
            try:
                if not isinstance(record, (SupplierOrder, Mapping)):
                    raise TypeError("pedido deve ser um objeto ou mapeamento")
                data = record.to_dict() if isinstance(record, SupplierOrder) else record
                parsed.append(SupplierOrder.from_mapping(data))
            except (AttributeError, SupplierPortalDataError, TypeError, ValueError) as exc:
                lote_id = _text(record.get("lote_id")) if isinstance(record, Mapping) else ""
                failures.append(
                    FalhaItemConsolidacao(
                        fonte=FONTE_PEDIDOS,
                        indice=index,
                        lote_id=lote_id or None,
                        codigo="INVALID_SUPPLIER_ITEM",
                        mensagem=str(exc),
                    )
                )
        return parsed

    @staticmethod
    def _index_validations(
        records: Iterable[RegistroValidado],
        failures: list[FalhaItemConsolidacao],
    ) -> dict[str, list[RegistroValidado]]:
        indexed: dict[str, list[RegistroValidado]] = defaultdict(list)
        for index, record in enumerate(records):
            if not isinstance(record, RegistroValidado):
                failures.append(
                    FalhaItemConsolidacao(
                        fonte=FONTE_VALIDACAO,
                        indice=index,
                        lote_id=None,
                        codigo="INVALID_VALIDATION_ITEM",
                        mensagem="resultado não é um RegistroValidado",
                    )
                )
                continue
            lote_id = _text(record.campos_originais.get("lote_id"))
            if not lote_id:
                failures.append(
                    FalhaItemConsolidacao(
                        fonte=FONTE_VALIDACAO,
                        indice=index,
                        lote_id=None,
                        codigo="INVALID_VALIDATION_ITEM",
                        mensagem="RegistroValidado não possui lote_id",
                    )
                )
                continue
            indexed[lote_id].append(record)
        return indexed

    @staticmethod
    def _consolidate_item(
        lote_id: str,
        stocks: list[StockRecord],
        order: SupplierOrder | None,
        validations: list[RegistroValidado],
        source_statuses: Mapping[str, str],
    ) -> RegistroConsolidado:
        stock = stocks[0] if stocks else None
        validation = validations[0] if validations else None
        checks: list[str] = []
        missing_sources: list[str] = []

        if stock is None:
            checks.append(VERIFICACAO_ESTOQUE_AUSENTE)
            missing_sources.append(FONTE_ESTOQUE)
        if order is None:
            checks.append(VERIFICACAO_PEDIDO_AUSENTE)
            missing_sources.append(FONTE_PEDIDOS)
        if validation is None:
            checks.append(VERIFICACAO_VALIDACAO_AUSENTE)
            missing_sources.append(FONTE_VALIDACAO)
        if len(stocks) > 1:
            checks.append(VERIFICACAO_ESTOQUE_DUPLICADO)
        if len(validations) > 1:
            checks.append(VERIFICACAO_VALIDACAO_DUPLICADA)
        if stock and order and stock.produto.casefold() != order.produto.casefold():
            checks.append(VERIFICACAO_PRODUTO_DIVERGENTE)
        if stock and order and stock.quantidade_disponivel < order.quantidade_solicitada:
            checks.append(VERIFICACAO_ESTOQUE_INSUFICIENTE)

        for source, status in source_statuses.items():
            if status == SOURCE_UNAVAILABLE and source not in missing_sources:
                missing_sources.append(source)

        status = ConsolidationService._operational_status(validation, checks)
        reason_parts = []
        if validation:
            reason_parts.append(validation.motivo)
        if checks:
            reason_parts.append("Verificações de consolidação: " + ", ".join(checks))
        reason = "; ".join(reason_parts) or "Fontes correlacionadas sem divergências"
        consulted = tuple(
            source
            for source, present in (
                (FONTE_ESTOQUE, stock is not None),
                (FONTE_PEDIDOS, order is not None),
                (FONTE_VALIDACAO, validation is not None),
            )
            if present
        )
        field_origins: dict[str, tuple[str, ...]] = {
            "lote_id": tuple(
                source
                for source, present in (
                    (FONTE_ESTOQUE, stock is not None),
                    (FONTE_PEDIDOS, order is not None),
                    (FONTE_VALIDACAO, validation is not None),
                )
                if present
            ),
        }
        if stock:
            for field in (
                "quantidade_disponivel",
                "localizacao",
                "status_estoque",
                "atualizado_em",
            ):
                field_origins[field] = (FONTE_ESTOQUE,)
        if order:
            for field in (
                "pedido_id",
                "fornecedor",
                "quantidade_solicitada",
                "status_pedido",
                "data_prevista",
            ):
                field_origins[field] = (FONTE_PEDIDOS,)
        if stock and order:
            field_origins["produto"] = (FONTE_ESTOQUE, FONTE_PEDIDOS)
        elif stock:
            field_origins["produto"] = (FONTE_ESTOQUE,)
        elif order:
            field_origins["produto"] = (FONTE_PEDIDOS,)

        return RegistroConsolidado(
            lote_id=lote_id,
            estoque=stock,
            pedido=order,
            validacao=validation,
            status_operacional=status,
            classificacao=validation.classificacao if validation else STATUS_REVISAO,
            motivo=reason,
            regras_violadas=validation.regras_violadas if validation else (),
            regra_aplicada=validation.regra_aplicada if validation else "",
            verificacoes_consolidacao=tuple(checks),
            origens_consultadas=consulted,
            fontes_ausentes=tuple(dict.fromkeys(missing_sources)),
            modo_degradado=bool(
                missing_sources
                or _VERIFICACOES_DEGRADADAS.intersection(checks)
                or any(value != SOURCE_AVAILABLE for value in source_statuses.values())
            ),
            origem_campos=field_origins,
        )

    @staticmethod
    def _operational_status(
        validation: RegistroValidado | None,
        checks: list[str],
    ) -> str:
        if _VERIFICACOES_DEGRADADAS.intersection(checks):
            return STATUS_REVISAO
        if validation and validation.classificacao == CLASSIFICACAO_ERRO_ENTRADA:
            return STATUS_ERRO_ITEM
        if validation and validation.classificacao == CLASSIFICACAO_DIVERGENCIA:
            return STATUS_DIVERGENCIA
        if any(
            check in {VERIFICACAO_PRODUTO_DIVERGENTE, VERIFICACAO_ESTOQUE_INSUFICIENTE}
            for check in checks
        ):
            return STATUS_DIVERGENCIA
        if validation and validation.classificacao == CLASSIFICACAO_AMBIGUO:
            return STATUS_REVISAO
        if checks:
            return STATUS_REVISAO
        return STATUS_APROVADO
