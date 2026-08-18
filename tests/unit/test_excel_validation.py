from __future__ import annotations

import pytest

from src.excel_reporting import (
    CLASSIFICACAO_AMBIGUO,
    CLASSIFICACAO_DIVERGENCIA,
    CLASSIFICACAO_ERRO_ENTRADA,
    CLASSIFICACAO_VALIDO,
    RegistroValidado,
    ValidationService,
    validar_registro,
)


REFERENCIAS = {"L001", "L002"}
pytestmark = [pytest.mark.unit, pytest.mark.regression]


def registro_valido(**overrides: object) -> dict[str, object]:
    registro: dict[str, object] = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manhã",
        "status": "APROVADO",
        "responsavel": "Rebecca",
        "data": "14/06/2026",
        "observacao": "",
    }
    registro.update(overrides)
    return registro


def validar_diretamente(
    registro: dict[str, object],
    *,
    registros_vistos: set[tuple[str, str]] | None = None,
    **metadata: object,
) -> RegistroValidado:
    return validar_registro(
        registro,
        REFERENCIAS,
        registros_vistos=(
            registros_vistos if registros_vistos is not None else set()
        ),
        **metadata,
    )


def test_registro_validado_e_dataclass_serializavel():
    original = registro_valido(campo_extra="preservado")

    resultado = validar_diretamente(
        original,
        aba_origem="Inspecoes",
        linha_origem=7,
    )

    assert isinstance(resultado, RegistroValidado)
    assert resultado.classificacao == CLASSIFICACAO_VALIDO
    assert resultado.campos_originais == original
    assert resultado.campos_originais is not original
    assert resultado.to_dict() == {
        "campos_originais": original,
        "status_original": "APROVADO",
        "status_normalizado": "APROVADO",
        "classificacao": CLASSIFICACAO_VALIDO,
        "motivo": "Registro válido pelas regras RN01-RN12",
        "regras_violadas": [],
        "data_referencia": "14/06/2026",
        "aba_origem": "Inspecoes",
        "linha_origem": 7,
        "regra_aplicada": "",
    }


def test_rn01_lote_id_obrigatorio():
    resultado = validar_diretamente(registro_valido(lote_id=" "))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN01",)


def test_rn02_produto_obrigatorio():
    resultado = validar_diretamente(registro_valido(produto=None))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN02",)


def test_rn03_linha_obrigatoria():
    resultado = validar_diretamente(registro_valido(linha=""))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN03",)


def test_rn04_status_obrigatorio_sem_duplicar_rn09():
    resultado = validar_diretamente(registro_valido(status=""))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN04",)


@pytest.mark.parametrize(
    ("campo", "regra"),
    (
        ("lote_id", "RN01"),
        ("produto", "RN02"),
        ("linha", "RN03"),
        ("status", "RN04"),
    ),
)
def test_nan_e_tratado_como_ausencia_nos_campos_obrigatorios(campo, regra):
    resultado = validar_diretamente(registro_valido(**{campo: float("nan")}))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == (regra,)


def test_rn05_lote_deve_existir_na_referencia():
    resultado = validar_diretamente(registro_valido(lote_id="L999"))

    assert resultado.classificacao == CLASSIFICACAO_DIVERGENCIA
    assert resultado.regras_violadas == ("RN05",)


def test_rn06_normaliza_ok_para_aprovado():
    resultado = validar_diretamente(registro_valido(status=" ok "))

    assert resultado.status_original == " ok "
    assert resultado.status_normalizado == "APROVADO"
    assert resultado.classificacao == CLASSIFICACAO_VALIDO


@pytest.mark.regression
def test_rn07_normaliza_nok_para_reprovado():
    resultado = validar_diretamente(
        registro_valido(status="nok", observacao="Avaria"),
    )

    assert resultado.status_original == "nok"
    assert resultado.status_normalizado == "REPROVADO"
    assert resultado.classificacao == CLASSIFICACAO_VALIDO


def test_rn08_aceita_aprovado_reprovado_e_pendente():
    for status in ("APROVADO", "REPROVADO", "PENDENTE"):
        resultado = validar_diretamente(
            registro_valido(status=status, observacao="Justificativa"),
        )
        assert resultado.classificacao == CLASSIFICACAO_VALIDO
        assert resultado.regras_violadas == ()


def test_rn09_status_desconhecido_e_ambiguo():
    resultado = validar_diretamente(registro_valido(status="em análise"))

    assert resultado.status_normalizado == "EM ANALISE"
    assert resultado.classificacao == CLASSIFICACAO_AMBIGUO
    assert resultado.regras_violadas == ("RN09",)


@pytest.mark.regression
def test_rn10_reprovado_ou_nok_sem_observacao_e_divergencia():
    for status in ("REPROVADO", "NOK"):
        resultado = validar_diretamente(
            registro_valido(status=status, observacao=" "),
        )

        assert resultado.status_normalizado == "REPROVADO"
        assert resultado.classificacao == CLASSIFICACAO_DIVERGENCIA
        assert resultado.regras_violadas == ("RN10",)


def test_rn10_nan_e_tratado_como_observacao_ausente():
    resultado = validar_diretamente(
        registro_valido(status="REPROVADO", observacao=float("nan")),
    )

    assert resultado.classificacao == CLASSIFICACAO_DIVERGENCIA
    assert resultado.regras_violadas == ("RN10",)


def test_rn11_segunda_ocorrencia_do_lote_no_mesmo_dia_e_divergencia():
    service = ValidationService(REFERENCIAS)

    primeira = service.validar_registro(
        registro_valido(), aba_origem="Insp_14_06_2026", linha_origem=2
    )
    segunda = service.validar_registro(
        registro_valido(), aba_origem="Insp_14_06_2026", linha_origem=3
    )
    terceira = service.validar_registro(
        registro_valido(), aba_origem="Insp_14_06_2026", linha_origem=4
    )

    assert primeira.classificacao == CLASSIFICACAO_VALIDO
    assert segunda.classificacao == CLASSIFICACAO_DIVERGENCIA
    assert segunda.regras_violadas == ("RN11",)
    assert terceira.classificacao == CLASSIFICACAO_DIVERGENCIA
    assert terceira.regras_violadas == ("RN11",)


def test_rn11_mesmo_lote_em_abas_diferentes_e_valido():
    service = ValidationService(REFERENCIAS)

    primeira = service.validar_registro(
        registro_valido(), aba_origem="Insp_14_06_2026"
    )
    segunda = service.validar_registro(
        registro_valido(), aba_origem="Insp_15_06_2026"
    )

    assert primeira.classificacao == CLASSIFICACAO_VALIDO
    assert segunda.classificacao == CLASSIFICACAO_VALIDO


def test_rn11_usa_aba_origem_presente_no_registro_consolidado():
    service = ValidationService(REFERENCIAS)

    primeira = service.validar_registro(
        registro_valido(aba_origem="Insp_14_06_2026")
    )
    segunda = service.validar_registro(
        registro_valido(
            aba_origem="Insp_15_06_2026",
            data="15/06/2026",
        )
    )

    assert primeira.aba_origem == "Insp_14_06_2026"
    assert segunda.aba_origem == "Insp_15_06_2026"
    assert primeira.classificacao == CLASSIFICACAO_VALIDO
    assert segunda.classificacao == CLASSIFICACAO_VALIDO


def test_rn11_mesma_aba_com_data_invalida_registra_rn11_e_rn12():
    service = ValidationService(REFERENCIAS)

    primeira = service.validar_registro(
        registro_valido(data="data-invalida"), aba_origem="Insp_14_06_2026"
    )
    segunda = service.validar_registro(
        registro_valido(data="data-invalida"), aba_origem="Insp_14_06_2026"
    )

    assert primeira.regras_violadas == ("RN12",)
    assert segunda.regras_violadas == ("RN11", "RN12")
    assert segunda.classificacao == CLASSIFICACAO_ERRO_ENTRADA


def test_rn12_data_ausente_e_erro_de_entrada():
    resultado = validar_diretamente(registro_valido(data=""))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN12",)


def test_rn12_nan_e_tratado_como_data_ausente():
    resultado = validar_diretamente(registro_valido(data=float("nan")))

    assert resultado.data_referencia == ""
    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN12",)


def test_rn12_exige_formato_dd_mm_aaaa():
    resultado = validar_diretamente(registro_valido(data="2026-06-14"))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN12",)


def test_rn12_rejeita_data_inexistente():
    resultado = validar_diretamente(registro_valido(data="31/02/2026"))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN12",)


def test_rn12_exige_dia_e_mes_com_dois_digitos():
    resultado = validar_diretamente(registro_valido(data="1/6/2026"))

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN12",)


def test_multiplas_violacoes_mantem_todas_as_regras_e_uma_classificacao():
    resultado = validar_diretamente(
        registro_valido(
            produto="",
            lote_id="L999",
            status="cancelado",
            data="2026-06-14",
        ),
    )

    assert resultado.classificacao == CLASSIFICACAO_ERRO_ENTRADA
    assert resultado.regras_violadas == ("RN02", "RN05", "RN09", "RN12")
    assert resultado.motivo == (
        "RN02: Produto não informado; "
        "RN05: Lote não encontrado na base de referência; "
        "RN09: Status desconhecido e não normalizável; "
        "RN12: Data ausente ou fora do formato DD/MM/AAAA"
    )


@pytest.mark.regression
def test_precedencia_divergencia_sobre_ambiguo():
    resultado = validar_diretamente(
        registro_valido(lote_id="L999", status="cancelado"),
    )

    assert resultado.regras_violadas == ("RN05", "RN09")
    assert resultado.classificacao == CLASSIFICACAO_DIVERGENCIA


def test_servico_pode_reiniciar_contexto_de_duplicidade():
    service = ValidationService(REFERENCIAS)
    service.validar_registro(registro_valido())
    assert service.validar_registro(registro_valido()).regras_violadas == ("RN11",)

    service.reset()

    assert service.validar_registro(registro_valido()).regras_violadas == ()


def test_validacao_nao_altera_registro_original():
    original = registro_valido(status=" ok ", produto=" Monitor ")

    validar_diretamente(original)

    assert original["status"] == " ok "
    assert original["produto"] == " Monitor "


def test_funcao_publica_exige_contexto_e_aplica_rn11():
    vistos: set[tuple[str, str]] = set()

    with pytest.raises(TypeError, match="registros_vistos"):
        validar_registro(registro_valido(), REFERENCIAS)

    primeira = validar_diretamente(registro_valido(), registros_vistos=vistos)
    segunda = validar_diretamente(registro_valido(), registros_vistos=vistos)

    assert primeira.classificacao == CLASSIFICACAO_VALIDO
    assert segunda.regras_violadas == ("RN11",)
    assert segunda.classificacao == CLASSIFICACAO_DIVERGENCIA


def test_status_numerico_e_preservado_e_classificado_como_ambiguo():
    resultado = validar_diretamente(registro_valido(status=0))

    assert resultado.status_original == "0"
    assert resultado.status_normalizado == "0"
    assert resultado.regras_violadas == ("RN09",)
    assert resultado.classificacao == CLASSIFICACAO_AMBIGUO


def test_snapshot_dos_campos_originais_nao_pode_ser_alterado():
    original = registro_valido()
    resultado = validar_diretamente(original)
    original["produto"] = "Alterado externamente"

    assert resultado.campos_originais["produto"] == "Monitor"
    with pytest.raises(TypeError):
        resultado.campos_originais["produto"] = "Alterado internamente"


def test_to_dict_preserva_campo_original_que_colide_com_metadado():
    resultado = validar_diretamente(
        registro_valido(classificacao="Valor original", motivo="Motivo original")
    )

    serializado = resultado.to_dict()

    assert serializado["campos_originais"]["classificacao"] == "Valor original"
    assert serializado["campos_originais"]["motivo"] == "Motivo original"
    assert serializado["classificacao"] == CLASSIFICACAO_VALIDO
    assert serializado["motivo"] == "Registro válido pelas regras RN01-RN12"
