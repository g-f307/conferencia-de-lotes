import pytest
from types import MappingProxyType

from src.excel_reporting.models import RegistroValidado
from src.operational_indicators import _percentual, calcular_indicadores


@pytest.mark.unit
def test_percentual_normal():
    assert _percentual(5, 10) == 50.0
    assert _percentual(1, 3) == 33.33


@pytest.mark.unit
def test_percentual_divisao_zero():
    assert _percentual(10, 0) == 0.0
    assert _percentual(0, 0) == 0.0


def _criar_registro(
    classificacao: str,
    regra_aplicada: str = "",
) -> RegistroValidado:
    return RegistroValidado(
        campos_originais={},
        status_original="OK",
        status_normalizado="APROVADO",
        classificacao=classificacao,
        motivo="Teste",
        regras_violadas=(regra_aplicada,) if regra_aplicada else (),
        data_referencia="01/01/2026",
        aba_origem="Insp_01_01_2026",
        linha_origem=2,
        regra_aplicada=regra_aplicada,
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "classificacoes, esperado_validos, esperado_divergencias, esperado_ambiguos, esperado_erros",
    [
        (["Válido", "Válido"], 2, 0, 0, 0),
        (["Divergência", "Ambíguo", "Erro de Entrada"], 0, 1, 1, 1),
        ([], 0, 0, 0, 0),
    ],
)
def test_calcular_indicadores_contagens(
    classificacoes,
    esperado_validos,
    esperado_divergencias,
    esperado_ambiguos,
    esperado_erros,
):
    registros = [_criar_registro(c) for c in classificacoes]
    indicadores = calcular_indicadores(registros)

    assert indicadores.total_registros == len(classificacoes)
    assert indicadores.validos_qtd == esperado_validos
    assert indicadores.divergencias_qtd == esperado_divergencias
    assert indicadores.ambiguos_qtd == esperado_ambiguos
    assert indicadores.erros_entrada_qtd == esperado_erros


@pytest.mark.unit
def test_calcular_indicadores_regra_mais_acionada():
    registros = [
        _criar_registro("Erro de Entrada", "RN01"),
        _criar_registro("Erro de Entrada", "RN01"),
        _criar_registro("Divergência", "RN05"),
        _criar_registro("Válido", ""),
    ]
    indicadores = calcular_indicadores(registros)

    assert indicadores.regra_mais_acionada_codigo == "RN01"
    assert indicadores.regra_mais_acionada_qtd == 2
    assert indicadores.regra_mais_acionada_nome == "Lote não informado"


@pytest.mark.unit
def test_calcular_indicadores_lista_vazia():
    indicadores = calcular_indicadores([])

    assert indicadores.total_registros == 0
    assert indicadores.taxa_qualidade_entrada == 0.0
    assert indicadores.taxa_revisao_humana == 0.0
    assert indicadores.taxa_retrabalho == 0.0
    assert indicadores.regra_mais_acionada_codigo == "N/A"
    assert indicadores.ganho_estimado_tempo_minutos == 0.0


@pytest.mark.unit
def test_calcular_indicadores_taxas():
    registros = [
        _criar_registro("Válido", ""),
        _criar_registro("Válido", ""),
        _criar_registro("Divergência", "RN05"),
        _criar_registro("Ambíguo", "RN09"),
        _criar_registro("Erro de Entrada", "RN01"),
    ]
    indicadores = calcular_indicadores(registros, tempo_manual_min=2.0, tempo_auto_min=0.25)

    assert indicadores.total_registros == 5
    assert indicadores.taxa_qualidade_entrada == 80.0  # 4 / 5
    assert indicadores.taxa_revisao_humana == 20.0  # 1 / 5
    assert indicadores.taxa_retrabalho == 20.0  # 1 / 5
    assert indicadores.ganho_estimado_tempo_minutos == 8.75  # 5 * 1.75
