"""Demonstra as regras criticas de validacao com ``unittest.TestCase``."""

from __future__ import annotations

import unittest

import pytest

from src.excel_reporting import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    validar_registro,
)


@pytest.mark.unit
class TestValidacaoRegrasCriticas(unittest.TestCase):
    """Exercita RN09-RN12 mantendo cada variacao independente."""

    def setUp(self) -> None:
        self.registro_valido: dict[str, object] = {
            "lote_id": "L001",
            "produto": "Monitor",
            "linha": "Linha A",
            "turno": "Manhã",
            "status": "APROVADO",
            "responsavel": "Rebecca",
            "data": "14/06/2026",
            "observacao": "",
        }
        self.lotes_referencia = {"L001", "L002"}
        self.registros_vistos: set[tuple[str, str]] = set()
        self.aba_origem = "Insp_14_06_2026"

    def test_variacoes_das_regras_rn09_a_rn12(self) -> None:
        cenarios = (
            {
                "id": "registro_valido",
                "alteracoes": {},
                "regras": (),
                "classificacao": CLASSIFICACAO_VALIDO,
                "status_normalizado": "APROVADO",
                "duplicado": False,
            },
            {
                "id": "status_ambiguo_rn09",
                "alteracoes": {"status": "em análise"},
                "regras": ("RN09",),
                "classificacao": CLASSIFICACAO_AMBIGUO,
                "status_normalizado": "EM ANALISE",
                "duplicado": False,
            },
            {
                "id": "reprovado_sem_observacao_rn10",
                "alteracoes": {"status": "REPROVADO"},
                "regras": ("RN10",),
                "classificacao": CLASSIFICACAO_DIVERGENCIA,
                "status_normalizado": "REPROVADO",
                "duplicado": False,
            },
            {
                "id": "nok_normalizado_e_sem_observacao_rn10",
                "alteracoes": {"status": "NOK"},
                "regras": ("RN10",),
                "classificacao": CLASSIFICACAO_DIVERGENCIA,
                "status_normalizado": "REPROVADO",
                "duplicado": False,
            },
            {
                "id": "lote_duplicado_no_dia_rn11",
                "alteracoes": {},
                "regras": ("RN11",),
                "classificacao": CLASSIFICACAO_DIVERGENCIA,
                "status_normalizado": "APROVADO",
                "duplicado": True,
            },
            {
                "id": "data_invalida_rn12",
                "alteracoes": {"data": "31/02/2026"},
                "regras": ("RN12",),
                "classificacao": CLASSIFICACAO_ERRO_ENTRADA,
                "status_normalizado": "APROVADO",
                "duplicado": False,
            },
        )

        for cenario in cenarios:
            with self.subTest(cenario=cenario["id"]):
                # Arrange
                registro = dict(self.registro_valido)
                registro.update(cenario["alteracoes"])
                registros_vistos = set(self.registros_vistos)
                if cenario["duplicado"]:
                    registros_vistos.add((self.aba_origem, "L001"))

                # Act
                resultado = validar_registro(
                    registro,
                    self.lotes_referencia,
                    registros_vistos=registros_vistos,
                    aba_origem=self.aba_origem,
                )

                # Assert
                self.assertEqual(resultado.regras_violadas, cenario["regras"])
                self.assertEqual(
                    resultado.classificacao,
                    cenario["classificacao"],
                )
                self.assertEqual(
                    resultado.status_normalizado,
                    cenario["status_normalizado"],
                )
