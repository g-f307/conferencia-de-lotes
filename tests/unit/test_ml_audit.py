from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.ml_audit import MLDecisionAudit, MLDecisionRecorder
from src.ml_client import MLPrediction


pytestmark = pytest.mark.unit


def valid_payload() -> dict[str, object]:
    return {
        "timestamp": "2026-08-19T12:30:00+00:00",
        "execution_id": "exec-123",
        "bot_id": "bot-ml",
        "lote_id": "L001",
        "classe": "revisar",
        "probabilidade": 0.72,
        "nivel_confianca": "media",
        "acao": "revisar",
        "resultado_aplicado": "REVISAO",
        "latencia_ms": 18.4,
    }


def test_registro_tipado_serializa_contexto_e_resultado_aplicado():
    recorder = MLDecisionRecorder(
        "bot-ml",
        "exec-123",
        clock=lambda: datetime(2026, 8, 19, 12, 30, tzinfo=timezone.utc),
    )
    prediction = MLPrediction(
        classe="revisar",
        probabilidade=0.72,
        nivel_confianca="media",
        acao="revisar",
        latencia_ms=18.4,
    )

    decision = recorder.record_prediction("L001", prediction, "REVISAO")

    assert recorder.decisions == (decision,)
    assert decision.to_dict() == {
        "timestamp": "2026-08-19T12:30:00+00:00",
        "execution_id": "exec-123",
        "bot_id": "bot-ml",
        "lote_id": "L001",
        "classe": "revisar",
        "probabilidade": 0.72,
        "nivel_confianca": "media",
        "acao": "revisar",
        "resultado_aplicado": "REVISAO",
        "latencia_ms": 18.4,
    }


def test_fallback_nao_inventa_campos_indisponiveis():
    recorder = MLDecisionRecorder("bot-ml", "exec-offline")

    decision = recorder.record_fallback("L002", "REVISAO_ML_OFFLINE")

    assert decision.classe is None
    assert decision.probabilidade is None
    assert decision.nivel_confianca is None
    assert decision.acao is None
    assert decision.latencia_ms is None


def test_decisao_pode_ser_reconstruida_do_resumo_json():
    payload = valid_payload()

    assert MLDecisionAudit.from_dict(payload).to_dict() == payload


def test_recorder_exige_identificadores():
    with pytest.raises(TypeError):
        MLDecisionRecorder()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("bot_id", "execution_id"),
    [("", "exec-123"), ("   ", "exec-123"), ("bot-ml", "")],
)
def test_recorder_rejeita_identificadores_vazios(bot_id, execution_id):
    with pytest.raises(ValueError, match="bot_id|execution_id"):
        MLDecisionRecorder(bot_id, execution_id)


@pytest.mark.parametrize(
    "field_name",
    ["timestamp", "execution_id", "bot_id", "lote_id", "resultado_aplicado"],
)
def test_from_dict_rejeita_campos_obrigatorios_ausentes(field_name):
    payload = valid_payload()
    payload.pop(field_name)

    with pytest.raises(ValueError, match=field_name):
        MLDecisionAudit.from_dict(payload)


@pytest.mark.parametrize(
    "field_name",
    ["timestamp", "execution_id", "bot_id", "lote_id", "resultado_aplicado"],
)
@pytest.mark.parametrize("invalid_value", [None, "", "   "])
def test_from_dict_rejeita_campos_obrigatorios_vazios(
    field_name,
    invalid_value,
):
    payload = valid_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValueError, match=field_name):
        MLDecisionAudit.from_dict(payload)


@pytest.mark.parametrize(
    "invalid_timestamp",
    ["data-invalida", "2026-08-19T12:30:00"],
)
def test_from_dict_rejeita_timestamp_invalido_ou_sem_fuso(invalid_timestamp):
    payload = valid_payload()
    payload["timestamp"] = invalid_timestamp

    with pytest.raises(ValueError, match="timestamp"):
        MLDecisionAudit.from_dict(payload)


@pytest.mark.parametrize(
    "invalid_probability",
    [-0.01, 1.01, float("nan"), float("inf"), "0.5", True],
)
def test_from_dict_rejeita_probabilidade_invalida(invalid_probability):
    payload = valid_payload()
    payload["probabilidade"] = invalid_probability

    with pytest.raises(ValueError, match="probabilidade"):
        MLDecisionAudit.from_dict(payload)


@pytest.mark.parametrize(
    "invalid_latency",
    [-0.01, float("nan"), float("inf"), "18.4", True],
)
def test_from_dict_rejeita_latencia_invalida(invalid_latency):
    payload = valid_payload()
    payload["latencia_ms"] = invalid_latency

    with pytest.raises(ValueError, match="latencia_ms"):
        MLDecisionAudit.from_dict(payload)
