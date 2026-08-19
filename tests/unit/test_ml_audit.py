from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.ml_audit import MLDecisionAudit, MLDecisionRecorder
from src.ml_client import MLPrediction


pytestmark = pytest.mark.unit


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
    payload = {
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

    assert MLDecisionAudit.from_dict(payload).to_dict() == payload
