from __future__ import annotations

import json
from urllib.error import HTTPError

import pytest

from src.ml_client import MLClient


pytestmark = pytest.mark.unit


def valid_response(**overrides: object) -> bytes:
    payload: dict[str, object] = {
        "classe": "valido_automatico",
        "probabilidade": 0.91,
        "nivel_confianca": "alta",
        "acao": "valido_automatico",
    }
    payload.update(overrides)
    return json.dumps(payload).encode("utf-8")


def classify(client: MLClient):
    return client.classificar(
        lote_id="L001",
        status_raw="EM ANALISE",
        turno="A",
        tem_obs=True,
    )


def test_ml_client_envia_contrato_e_retorna_previsao_tipificada():
    calls: list[tuple[str, dict[str, object], float]] = []

    def transport(url: str, body: bytes, timeout: float) -> bytes:
        calls.append((url, json.loads(body), timeout))
        return valid_response()

    prediction = classify(
        MLClient("http://ml.test/", 2.5, transport=transport)
    )

    assert prediction is not None
    assert prediction.classe == "valido_automatico"
    assert prediction.probabilidade == 0.91
    assert prediction.nivel_confianca == "alta"
    assert prediction.acao == "valido_automatico"
    assert prediction.latencia_ms >= 0
    assert calls == [
        (
            "http://ml.test/predict",
            {
                "lote_id": "L001",
                "status_raw": "EM ANALISE",
                "turno": "A",
                "tem_obs": True,
            },
            2.5,
        )
    ]


@pytest.mark.parametrize(
    "failure",
    [TimeoutError("timeout"), ConnectionError("offline"), OSError("rede")],
)
def test_ml_client_falhas_de_comunicacao_retornam_none(failure: Exception):
    def transport(url: str, body: bytes, timeout: float) -> bytes:
        raise failure

    client = MLClient("http://ml.test", 1, transport=transport)

    assert classify(client) is None
    assert client.consecutive_failures == 1
    assert client.circuit_open is False


def test_ml_client_erro_http_retorna_none():
    def transport(url: str, body: bytes, timeout: float) -> bytes:
        raise HTTPError(url, 503, "Service Unavailable", None, None)

    client = MLClient("http://ml.test", 1, transport=transport)

    assert classify(client) is None
    assert client.consecutive_failures == 1


@pytest.mark.parametrize(
    "response",
    [
        b"nao-json",
        b"[]",
        b'{"classe":"revisar"}',
        valid_response(classe="desconhecida"),
        valid_response(probabilidade=2),
        valid_response(probabilidade="0.9"),
        valid_response(nivel_confianca="incerta"),
        valid_response(acao="aprovar"),
    ],
)
def test_ml_client_resposta_incompativel_retorna_none(response: bytes):
    client = MLClient(
        "http://ml.test",
        1,
        transport=lambda url, body, timeout: response,
    )

    assert classify(client) is None
    assert client.consecutive_failures == 1


def test_circuit_breaker_abre_na_quinta_falha_e_bloqueia_sexta_chamada():
    calls = 0

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        nonlocal calls
        calls += 1
        raise ConnectionError("API indisponivel")

    client = MLClient("http://ml.test", 1, transport=unavailable)

    for _ in range(5):
        assert classify(client) is None

    assert calls == 5
    assert client.consecutive_failures == 5
    assert client.circuit_open is True
    assert classify(client) is None
    assert calls == 5


def test_chamada_bem_sucedida_reinicia_contador_de_falhas():
    responses: list[bytes | Exception] = [
        ConnectionError("offline"),
        valid_response(),
    ]

    def transport(url: str, body: bytes, timeout: float) -> bytes:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    client = MLClient("http://ml.test", 1, transport=transport)

    assert classify(client) is None
    assert client.consecutive_failures == 1
    assert classify(client) is not None
    assert client.consecutive_failures == 0
    assert client.circuit_open is False


def test_reset_manual_permite_nova_chamada_apos_abertura():
    calls = 0

    def transport(url: str, body: bytes, timeout: float) -> bytes:
        nonlocal calls
        calls += 1
        if calls <= 5:
            raise ConnectionError("offline")
        return valid_response()

    client = MLClient("http://ml.test", 1, transport=transport)
    for _ in range(5):
        classify(client)

    client.reset_circuit_breaker()

    assert client.circuit_open is False
    assert client.consecutive_failures == 0
    assert classify(client) is not None
    assert calls == 6
