from dataclasses import asdict

import pytest

from src.excel_reporting.models import RegistroValidado
from src.excel_reporting.validation_service import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
)
from src.operational_indicators import (
    OperationalIndicators,
    _percentual,
    calcular_indicadores,
)

pytestmark = pytest.mark.unit


def _criar_registro(
    classificacao: str,
    regra_aplicada: str = "",
) -> RegistroValidado:
    return RegistroValidado(
        campos_originais={},
        status_original="OK",
        status_normalizado="APROVADO",
        classificacao=classificacao,
        motivo="Cenário controlado",
        regras_violadas=(regra_aplicada,) if regra_aplicada else (),
        data_referencia="01/01/2026",
        aba_origem="Insp_01_01_2026",
        linha_origem=2,
        regra_aplicada=regra_aplicada,
    )


@pytest.mark.parametrize(
    ("parte", "total", "esperado"),
    [
        pytest.param(5, 10, 50.0, id="metade"),
        pytest.param(1, 3, 33.33, id="arredondamento_duas_casas"),
        pytest.param(0, 10, 0.0, id="parte_zero"),
    ],
)
def test_percentual_casos_normais(parte, total, esperado):
    assert _percentual(parte, total) == esperado


@pytest.mark.parametrize("parte", [0, 10], ids=["zero_por_zero", "parte_positiva"])
def test_percentual_impede_divisao_por_zero(parte):
    assert _percentual(parte, 0) == 0.0


@pytest.mark.parametrize(
    ("registros", "esperado"),
    [
        pytest.param(
            [
                _criar_registro(CLASSIFICACAO_VALIDO),
                _criar_registro(CLASSIFICACAO_VALIDO),
                _criar_registro(CLASSIFICACAO_DIVERGENCIA, "RN05"),
                _criar_registro(CLASSIFICACAO_AMBIGUO, "RN09"),
                _criar_registro(CLASSIFICACAO_ERRO_ENTRADA, "RN01"),
            ],
            OperationalIndicators(
                total_registros=5,
                validos_qtd=2,
                validos_pct=40.0,
                divergencias_qtd=1,
                divergencias_pct=20.0,
                ambiguos_qtd=1,
                ambiguos_pct=20.0,
                erros_entrada_qtd=1,
                erros_entrada_pct=20.0,
                regra_mais_acionada_codigo="RN05",
                regra_mais_acionada_nome=(
                    "Lote não encontrado na base de referência"
                ),
                regra_mais_acionada_qtd=1,
                taxa_qualidade_entrada=80.0,
                taxa_revisao_humana=20.0,
                taxa_retrabalho=20.0,
                ganho_estimado_tempo_minutos=8.75,
                ganho_estimado_tempo_horas=0.15,
            ),
            id="classificacoes_mistas",
        ),
        pytest.param(
            [
                _criar_registro(CLASSIFICACAO_ERRO_ENTRADA, "RN01"),
                _criar_registro(CLASSIFICACAO_ERRO_ENTRADA, "RN01"),
                _criar_registro(CLASSIFICACAO_DIVERGENCIA, "RN05"),
                _criar_registro(CLASSIFICACAO_VALIDO),
            ],
            OperationalIndicators(
                total_registros=4,
                validos_qtd=1,
                validos_pct=25.0,
                divergencias_qtd=1,
                divergencias_pct=25.0,
                ambiguos_qtd=0,
                ambiguos_pct=0.0,
                erros_entrada_qtd=2,
                erros_entrada_pct=50.0,
                regra_mais_acionada_codigo="RN01",
                regra_mais_acionada_nome="Lote não informado",
                regra_mais_acionada_qtd=2,
                taxa_qualidade_entrada=50.0,
                taxa_revisao_humana=0.0,
                taxa_retrabalho=25.0,
                ganho_estimado_tempo_minutos=7.0,
                ganho_estimado_tempo_horas=0.12,
            ),
            id="regra_recorrente",
        ),
        pytest.param(
            [],
            OperationalIndicators(
                total_registros=0,
                validos_qtd=0,
                validos_pct=0.0,
                divergencias_qtd=0,
                divergencias_pct=0.0,
                ambiguos_qtd=0,
                ambiguos_pct=0.0,
                erros_entrada_qtd=0,
                erros_entrada_pct=0.0,
                regra_mais_acionada_codigo="N/A",
                regra_mais_acionada_nome="Nenhuma regra acionada",
                regra_mais_acionada_qtd=0,
                taxa_qualidade_entrada=0.0,
                taxa_revisao_humana=0.0,
                taxa_retrabalho=0.0,
                ganho_estimado_tempo_minutos=0.0,
                ganho_estimado_tempo_horas=0.0,
            ),
            id="lote_vazio",
        ),
    ],
)
def test_calcular_dez_indicadores_parametrizados(registros, esperado):
    indicadores = calcular_indicadores(registros)

    assert asdict(indicadores) == asdict(esperado)
