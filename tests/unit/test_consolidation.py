from __future__ import annotations

import pytest

from src.consolidation import (
    STATUS_APROVADO,
    STATUS_DIVERGENCIA,
    STATUS_ERRO_ITEM,
    STATUS_REVISAO,
    ConsolidationInputError,
    ConsolidationService,
)
from src.desktop_stock.models import StockRecord
from src.excel_reporting import ValidationService
from src.supplier_portal import SupplierOrder


def stock(**overrides: object) -> StockRecord:
    values = {
        "lote_id": "L001",
        "produto": "Monitor",
        "quantidade_disponivel": 10,
        "localizacao": "A-01",
        "status_estoque": "DISPONIVEL",
        "atualizado_em": "2026-08-28T10:00:00Z",
        **overrides,
    }
    return StockRecord(**values)  # type: ignore[arg-type]


def order(**overrides: object) -> SupplierOrder:
    values = {
        "pedido_id": "P001",
        "lote_id": "L001",
        "fornecedor": "Fornecedor controlado",
        "produto": "Monitor",
        "quantidade_solicitada": 5,
        "status_pedido": "ABERTO",
        "data_prevista": "30/08/2026",
        **overrides,
    }
    return SupplierOrder(**values)  # type: ignore[arg-type]


def validated(**overrides: object):
    values = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "status": "APROVADO",
        "responsavel": "Equipe",
        "data": "28/08/2026",
        "observacao": "",
        **overrides,
    }
    return ValidationService(["L001", "L002"]).validar_registro(
        values,
        aba_origem="Insp_28_08_2026",
        linha_origem=2,
    )


def test_consolida_fontes_completas_e_preserva_auditoria_das_regras():
    result = ConsolidationService().consolidate(
        [stock()],
        [order()],
        [validated()],
    )

    assert result.status == "SUCCESS"
    assert result.ml_consultado is False
    item = result.registros[0]
    assert item.status_operacional == STATUS_APROVADO
    assert item.regra_aplicada == ""
    assert item.regras_violadas == ()
    assert item.origem_campos["lote_id"] == (
        "desktop",
        "web",
        "motor_rn01_rn12",
    )
    assert item.to_dict()["quantidade_disponivel"] == 10
    assert item.to_dict()["quantidade_solicitada"] == 5


@pytest.mark.parametrize(
    ("stocks", "orders", "expected_check"),
    [
        ([], [order()], "CONS01"),
        ([stock()], [], "CONS02"),
    ],
)
def test_fonte_ausente_fica_explicita_e_exige_revisao(
    stocks,
    orders,
    expected_check,
):
    result = ConsolidationService().consolidate(stocks, orders, [validated()])

    assert result.status == "PARTIALLY_COMPLETED"
    assert result.registros[0].status_operacional == STATUS_REVISAO
    assert expected_check in result.registros[0].verificacoes_consolidacao
    assert result.registros[0].fontes_ausentes


@pytest.mark.parametrize(
    ("stock_values", "order_values", "expected_check"),
    [
        ({"produto": "Teclado"}, {}, "CONS03"),
        ({"quantidade_disponivel": 2}, {}, "CONS04"),
    ],
)
def test_divergencias_entre_fontes_nao_reutilizam_codigo_rn(
    stock_values,
    order_values,
    expected_check,
):
    result = ConsolidationService().consolidate(
        [stock(**stock_values)],
        [order(**order_values)],
        [validated()],
    )

    item = result.registros[0]
    assert result.status == "SUCCESS"
    assert result.modo_degradado is False
    assert item.status_operacional == STATUS_DIVERGENCIA
    assert item.regras_violadas == ()
    assert item.regra_aplicada == ""
    assert item.verificacoes_consolidacao == (expected_check,)


def test_classificacao_e_regra_aplicada_mantem_precedencia_rn01_rn12():
    validation = validated(produto="", lote_id="L999", data="fora-do-formato")
    result = ConsolidationService().consolidate(
        [stock(lote_id="L999")],
        [order(lote_id="L999")],
        [validation],
    )

    item = result.registros[0]
    assert item.status_operacional == STATUS_ERRO_ITEM
    assert item.classificacao == "Erro de Entrada"
    assert item.regras_violadas == ("RN02", "RN05", "RN12")
    assert item.regra_aplicada == "RN02"


def test_registro_invalido_nao_interrompe_os_demais_itens():
    invalid_stock = {"lote_id": "L002", "produto": "Mouse"}
    result = ConsolidationService().consolidate(
        [invalid_stock, stock()],
        [order()],
        [validated()],
    )

    assert len(result.falhas_itens) == 1
    assert result.falhas_itens[0].lote_id == "L002"
    assert len(result.registros) == 1
    assert result.registros[0].status_operacional == STATUS_APROVADO


def test_objetos_invalidos_e_booleano_sao_isolados_como_falha_de_item():
    result = ConsolidationService().consolidate(
        [object(), {**stock().to_dict(), "quantidade_disponivel": True}],
        [object(), order()],
        [validated()],
    )

    assert result.status == "PARTIALLY_COMPLETED"
    assert [failure.codigo for failure in result.falhas_itens] == [
        "INVALID_STOCK_ITEM",
        "INVALID_STOCK_ITEM",
        "INVALID_SUPPLIER_ITEM",
    ]
    assert result.registros[0].status_operacional == STATUS_REVISAO


@pytest.mark.parametrize(
    "invalid_stock",
    [
        stock(quantidade_disponivel=True),
        stock(quantidade_disponivel=-1),
        stock(produto=""),
    ],
    ids=["quantidade-booleana", "quantidade-negativa", "campo-vazio"],
)
def test_stock_record_tipado_respeita_a_validacao_de_fronteira(invalid_stock):
    result = ConsolidationService().consolidate(
        [invalid_stock],
        [order()],
        [validated()],
    )

    assert result.status == "PARTIALLY_COMPLETED"
    assert result.falhas_itens[0].codigo == "INVALID_STOCK_ITEM"
    assert result.registros[0].status_operacional == STATUS_REVISAO


@pytest.mark.parametrize(
    "invalid_order",
    [
        order(quantidade_solicitada=True),
        order(quantidade_solicitada=-1),
        order(fornecedor=""),
    ],
    ids=["quantidade-booleana", "quantidade-negativa", "campo-vazio"],
)
def test_supplier_order_tipado_respeita_a_validacao_de_fronteira(invalid_order):
    result = ConsolidationService().consolidate(
        [stock()],
        [invalid_order],
        [validated()],
    )

    assert result.status == "PARTIALLY_COMPLETED"
    assert result.falhas_itens[0].codigo == "INVALID_SUPPLIER_ITEM"
    assert result.registros[0].status_operacional == STATUS_REVISAO


def test_fonte_ausente_prioriza_revisao_sem_apagar_auditoria_rn10():
    validation = validated(status="REPROVADO", observacao="")

    result = ConsolidationService().consolidate([], [order()], [validation])

    item = result.registros[0]
    assert result.status == "PARTIALLY_COMPLETED"
    assert item.status_operacional == STATUS_REVISAO
    assert item.classificacao == "Divergência"
    assert item.regras_violadas == ("RN10",)
    assert item.regra_aplicada == "RN10"
    assert item.verificacoes_consolidacao == ("CONS01",)


def test_duas_fontes_indisponiveis_produzem_falha_geral_sem_chamar_ml():
    result = ConsolidationService().consolidate(
        [],
        [],
        [],
        source_statuses={"desktop": "UNAVAILABLE", "web": "UNAVAILABLE"},
    )

    assert result.status == "FAILED"
    assert result.ml_consultado is False
    assert result.registros == ()


def test_envelope_com_contrato_estrutural_invalido_falha_rapido():
    with pytest.raises(ConsolidationInputError, match="payload da fonte desktop"):
        ConsolidationService().consolidate_envelopes(
            {"payload": None},
            {"payload": {"records": [], "source_status": "AVAILABLE"}},
            [],
        )
