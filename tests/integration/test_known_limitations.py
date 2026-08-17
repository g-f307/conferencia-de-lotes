"""Documenta limitações conhecidas sem ocultar regressões inesperadas."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.excel_reporting import service as service_module
from src.excel_reporting.service import gerar_relatorio_excel


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKBOOK_AULA22 = PROJECT_ROOT / "dados_entrada" / "inspecao_lotes_10dias.xlsx"
TOTAL_PROBLEMAS_ENUNCIADO = 100
TOTAL_PROBLEMAS_HOMOLOGADO = 98

pytestmark = pytest.mark.integration


class DivergenciaGabaritoAula22(AssertionError):
    """Identifica apenas a diferença conhecida entre o enunciado e a homologação."""


@pytest.mark.skip(
    reason=(
        "Atualização incremental do workbook ainda não implementada — "
        "escopo posterior à Aula 23"
    )
)
def test_servico_expoe_atualizacao_incremental_do_workbook() -> None:
    atualizar_incrementalmente = service_module.atualizar_relatorio_incremental

    assert callable(atualizar_incrementalmente)


@pytest.mark.regression
@pytest.mark.xfail(
    strict=True,
    raises=DivergenciaGabaritoAula22,
    reason=(
        "Enunciado da Aula 22 informa 100 registros problemáticos, mas a "
        "homologação das RN01-RN12 identifica 98; conciliação com o gabarito pendente"
    ),
)
def test_gabarito_aula22_totaliza_cem_registros_problematicos(tmp_path: Path) -> None:
    result = gerar_relatorio_excel(
        WORKBOOK_AULA22,
        tmp_path / "relatorio.xlsx",
        log_path=tmp_path / "execucao.log",
    )
    total_problematicos = (
        result.divergencias + result.ambiguos + result.erros_entrada
    )

    if total_problematicos == TOTAL_PROBLEMAS_HOMOLOGADO:
        raise DivergenciaGabaritoAula22(
            "Enunciado espera 100 registros problemáticos; homologação produziu 98"
        )

    assert total_problematicos == TOTAL_PROBLEMAS_ENUNCIADO
