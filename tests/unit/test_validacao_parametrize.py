"""Cenarios de negocio parametrizados para as regras RN05 e RN09-RN12."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.excel_reporting import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    validar_registro,
)

REGISTRO_VALIDO: Mapping[str, object] = {
    "lote_id": "L001",
    "produto": "Monitor",
    "linha": "Linha A",
    "turno": "Manhã",
    "status": "APROVADO",
    "responsavel": "Rebecca",
    "data": "14/06/2026",
    "observacao": "",
}
ABA_ORIGEM = "Insp_14_06_2026"


@pytest.mark.unit
@pytest.mark.parametrize(
    (
        "alteracoes",
        "lotes_referencia",
        "registros_vistos",
        "classificacao_esperada",
        "regras_esperadas",
        "status_normalizado_esperado",
    ),
    (
        (
            {},
            {"L001"},
            frozenset(),
            CLASSIFICACAO_VALIDO,
            (),
            "APROVADO",
        ),
        (
            {"lote_id": "L999"},
            {"L001"},
            frozenset(),
            CLASSIFICACAO_DIVERGENCIA,
            ("RN05",),
            "APROVADO",
        ),
        (
            {"status": "em análise"},
            {"L001"},
            frozenset(),
            CLASSIFICACAO_AMBIGUO,
            ("RN09",),
            "EM ANALISE",
        ),
        (
            {"status": "NOK"},
            {"L001"},
            frozenset(),
            CLASSIFICACAO_DIVERGENCIA,
            ("RN10",),
            "REPROVADO",
        ),
        (
            {},
            {"L001"},
            frozenset({(ABA_ORIGEM, "L001")}),
            CLASSIFICACAO_DIVERGENCIA,
            ("RN11",),
            "APROVADO",
        ),
        (
            {"data": "2026-06-14"},
            {"L001"},
            frozenset(),
            CLASSIFICACAO_ERRO_ENTRADA,
            ("RN12",),
            "APROVADO",
        ),
    ),
    ids=(
        "registro_valido",
        "lote_inexistente",
        "status_ambiguo",
        "reprovado_sem_observacao",
        "lote_duplicado_no_dia",
        "data_invalida",
    ),
)
def test_validar_cenarios_de_negocio(
    alteracoes: Mapping[str, object],
    lotes_referencia: set[str],
    registros_vistos: frozenset[tuple[str, str]],
    classificacao_esperada: str,
    regras_esperadas: tuple[str, ...],
    status_normalizado_esperado: str,
) -> None:
    # Arrange
    registro = dict(REGISTRO_VALIDO)
    registro.update(alteracoes)

    # Act
    resultado = validar_registro(
        registro,
        lotes_referencia,
        registros_vistos=set(registros_vistos),
        aba_origem=ABA_ORIGEM,
    )

    # Assert
    assert resultado.classificacao == classificacao_esperada
    assert resultado.regras_violadas == regras_esperadas
    assert resultado.status_normalizado == status_normalizado_esperado
