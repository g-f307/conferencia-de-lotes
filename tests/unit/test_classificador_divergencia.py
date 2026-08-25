import json
import logging

import pytest

from src.classificador_divergencia import (
    NAO_CLASSIFICADO,
    ClassificadorDivergencia,
    PredicaoCausa,
    ProvedorHTTPClassificacaoDivergencia,
)
from src.config import Settings
from src.logging_config import LOGGER_NAME

pytestmark = pytest.mark.unit


class ProvedorControlado:
    def __init__(self, resposta=None, erro: Exception | None = None):
        self.resposta = resposta
        self.erro = erro
        self.chamadas: list[tuple[str, float]] = []

    def classificar(self, observacao: str, timeout_seconds: float):
        self.chamadas.append((observacao, timeout_seconds))
        if self.erro is not None:
            raise self.erro
        return self.resposta


class RelogioControlado:
    def __init__(self, *instantes: float):
        self.instantes = iter(instantes)

    def __call__(self) -> float:
        return next(self.instantes)


def classificador(provedor, **opcoes):
    return ClassificadorDivergencia(
        enabled=opcoes.get("enabled", True),
        confianca_minima=opcoes.get("confianca_minima", 0.8),
        timeout_seconds=opcoes.get("timeout_seconds", 0.5),
        provedor=provedor,
        clock=opcoes.get("clock", RelogioControlado(1.0, 1.025)),
    )


def test_classifica_conteudo_da_observacao_e_repassa_timeout():
    provedor = ProvedorControlado(PredicaoCausa("erro_digitacao", 0.94))

    resultado = classificador(provedor).classificar("digitei errado o código do lote")

    assert provedor.chamadas == [("digitei errado o código do lote", 0.5)]
    assert resultado.causa_provavel == "erro_digitacao"
    assert resultado.confianca_ml == 0.94
    assert resultado.origem_decisao == "ml"
    assert resultado.motivo_fallback is None
    assert resultado.latencia_ms == 25.0


def test_feature_flag_desabilitada_nao_chama_provedor():
    provedor = ProvedorControlado(PredicaoCausa("duplicidade", 0.99))

    resultado = classificador(provedor, enabled=False).classificar(
        "lançamento duplicado"
    )

    assert provedor.chamadas == []
    assert resultado.causa_provavel == NAO_CLASSIFICADO
    assert resultado.origem_decisao == "fallback"
    assert resultado.motivo_fallback == "ml_desabilitado"
    assert resultado.latencia_ms == 0.0


def test_observacao_ausente_nao_chama_provedor():
    provedor = ProvedorControlado(PredicaoCausa("duplicidade", 0.99))

    resultado = classificador(provedor).classificar("   ")

    assert provedor.chamadas == []
    assert resultado.motivo_fallback == "observacao_ausente"


def test_confianca_abaixo_do_limiar_e_descartada():
    provedor = ProvedorControlado(PredicaoCausa("falta_peca", 0.79))

    resultado = classificador(provedor, confianca_minima=0.8).classificar(
        "faltou peça na doca 3"
    )

    assert resultado.causa_provavel == NAO_CLASSIFICADO
    assert resultado.confianca_ml == 0.79
    assert resultado.origem_decisao == "fallback"
    assert resultado.motivo_fallback == "baixa_confianca"


def test_confianca_igual_ao_limiar_e_aceita():
    provedor = ProvedorControlado(PredicaoCausa("falta_peca", 0.8))

    resultado = classificador(provedor, confianca_minima=0.8).classificar("faltou peça")

    assert resultado.causa_provavel == "falta_peca"
    assert resultado.origem_decisao == "ml"


@pytest.mark.parametrize(
    ("erro", "motivo"),
    [
        (TimeoutError("serviço lento"), "timeout"),
        (ConnectionError("serviço fora do ar"), "indisponibilidade"),
        (RuntimeError("falha inesperada"), "indisponibilidade"),
        (ValueError("JSON inválido"), "resposta_invalida"),
    ],
)
def test_falhas_do_provedor_nunca_sao_propagadas(erro, motivo):
    provedor = ProvedorControlado(erro=erro)

    resultado = classificador(provedor).classificar("observação controlada")

    assert resultado.causa_provavel == NAO_CLASSIFICADO
    assert resultado.origem_decisao == "fallback"
    assert resultado.motivo_fallback == motivo


def test_contrato_inesperado_do_provedor_vira_resposta_invalida():
    resultado = classificador(ProvedorControlado({"causa": "duplicidade"})).classificar(
        "duplicado"
    )

    assert resultado.motivo_fallback == "resposta_invalida"


def test_provedor_http_envia_o_texto_livre_e_interpreta_resposta():
    chamadas = []

    def transporte(url: str, payload: bytes, timeout: float) -> bytes:
        chamadas.append((url, json.loads(payload), timeout))
        return json.dumps(
            {"causa_provavel": "erro_digitacao", "confianca_ml": 0.91}
        ).encode("utf-8")

    provedor = ProvedorHTTPClassificacaoDivergencia(
        "http://ml.test/",
        transport=transporte,
    )

    resultado = provedor.classificar("digitei errado", 0.25)

    assert chamadas == [
        (
            "http://ml.test/predict-divergencia",
            {"observacao": "digitei errado"},
            0.25,
        )
    ]
    assert resultado == PredicaoCausa("erro_digitacao", 0.91)


@pytest.mark.parametrize(
    "resposta",
    [
        b"[]",
        b"{}",
        b'{"causa_provavel": "duplicidade", "confianca_ml": 2}',
        b"conteudo-invalido",
    ],
)
def test_provedor_http_rejeita_resposta_malformada(resposta):
    provedor = ProvedorHTTPClassificacaoDivergencia(
        "http://ml.test",
        transport=lambda *_: resposta,
    )

    with pytest.raises((TypeError, ValueError)):
        provedor.classificar("duplicado", 0.5)


def test_observacao_nao_vaza_para_o_log(caplog):
    observacao_sensivel = "operador informou segredo do lote"
    provedor = ProvedorControlado(erro=ConnectionError("offline"))

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        classificador(provedor).classificar(observacao_sensivel)

    assert observacao_sensivel not in caplog.text


@pytest.mark.parametrize("valor", [-0.1, 1.1, float("nan"), True, "0.8"])
def test_rejeita_limiar_invalido(valor):
    with pytest.raises((TypeError, ValueError), match="confianca_minima"):
        ClassificadorDivergencia(
            enabled=False,
            confianca_minima=valor,
            timeout_seconds=1,
        )


@pytest.mark.parametrize("valor", [0, -1, float("inf")])
def test_rejeita_timeout_invalido(valor):
    with pytest.raises(ValueError, match="timeout_seconds"):
        ClassificadorDivergencia(
            enabled=False,
            confianca_minima=0.8,
            timeout_seconds=valor,
        )


@pytest.mark.parametrize(
    ("causa", "confianca", "erro"),
    [
        ("   ", 0.8, ValueError),
        ("duplicidade", True, TypeError),
        ("duplicidade", "0.8", TypeError),
        ("duplicidade", -0.1, ValueError),
        ("duplicidade", float("inf"), ValueError),
    ],
)
def test_predicao_rejeita_contrato_invalido(causa, confianca, erro):
    with pytest.raises(erro):
        PredicaoCausa(causa, confianca)


def test_ml_habilitado_exige_provedor():
    with pytest.raises(ValueError, match="provedor"):
        ClassificadorDivergencia(
            enabled=True,
            confianca_minima=0.8,
            timeout_seconds=1,
        )


def test_from_settings_monta_provedor_http_com_configuracao(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ML_ENABLED", "true")
    monkeypatch.setenv("ML_API_URL", "http://ml.test")
    monkeypatch.setenv("ML_TIMEOUT_SECONDS", "0.4")
    monkeypatch.setenv("ML_CONFIANCA_MINIMA", "0.9")
    chamadas = []

    def transporte(url: str, payload: bytes, timeout: float) -> bytes:
        chamadas.append((url, json.loads(payload), timeout))
        return b'{"causa_provavel":"duplicidade","confianca_ml":0.93}'

    classificador_configurado = ClassificadorDivergencia.from_settings(
        Settings.from_env(tmp_path),
        transport=transporte,
        clock=RelogioControlado(1.0, 1.01),
    )

    resultado = classificador_configurado.classificar("duplicado por engano")

    assert resultado.causa_provavel == "duplicidade"
    assert resultado.latencia_ms == 10.0
    assert chamadas == [
        (
            "http://ml.test/predict-divergencia",
            {"observacao": "duplicado por engano"},
            0.4,
        )
    ]


def test_from_settings_desabilitado_tolera_parametros_ml_invalidos(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("ML_ENABLED", "false")
    monkeypatch.setenv("ML_TIMEOUT_SECONDS", "invalido")
    monkeypatch.setenv("ML_CONFIANCA_MINIMA", "invalida")

    classificador_configurado = ClassificadorDivergencia.from_settings(
        Settings.from_env(tmp_path)
    )

    resultado = classificador_configurado.classificar("texto não enviado")
    assert resultado.motivo_fallback == "ml_desabilitado"
