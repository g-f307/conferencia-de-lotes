from __future__ import annotations

import json

import pytest

from src.config import Settings
from src.item_processor import ItemProcessor
from src.logging_config import configure_logging
from src.ml_audit import MLDecisionRecorder
from src.ml_client import MLClient


pytestmark = pytest.mark.integration


def test_decisao_ml_possui_contexto_estruturado_no_json_lines(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("BOT_ID", "bot-ml-test")
    monkeypatch.setenv("EXECUTION_ID", "exec-ml-123")
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    times = iter([10.0, 10.025])
    client = MLClient(
        "http://ml.test",
        1,
        transport=lambda url, body, timeout: json.dumps(
            {
                "classe": "valido_automatico",
                "probabilidade": 0.91,
                "nivel_confianca": "alta",
                "acao": "valido_automatico",
            }
        ).encode(),
        clock=lambda: next(times),
    )

    processor = ItemProcessor(
        {"L001"},
        ml_enabled=True,
        ml_client=client,
        decision_recorder=MLDecisionRecorder(
            settings.bot_id,
            settings.execution_id,
        ),
    )
    classification = processor.process(
        {
            "lote_id": "L001",
            "produto": "Monitor",
            "linha": "Linha A",
            "turno": "A",
            "status": "EM ANALISE",
            "responsavel": "Operador",
            "data": "2026-08-19",
            "observacao": "Conferir",
        }
    )

    assert classification.ml_decision is not None
    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["bot_id"] == "bot-ml-test"
    assert record["execution_id"] == "exec-ml-123"
    assert record["evento"] == "DECISAO_ML"
    assert record["detalhes"] | {
        "lote_id": "L001",
        "classe": "valido_automatico",
        "probabilidade": 0.91,
        "nivel_confianca": "alta",
        "acao": "valido_automatico",
        "latencia_ms": 25.0,
        "resultado_aplicado": "APROVADO",
    } == record["detalhes"]


class OfflineClient:
    def classificar(self, **payload):
        return None


def test_fallback_e_falha_esperada_nao_expoem_observacao_nem_traceback(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("BOT_ID", "bot-ml-test")
    monkeypatch.setenv("EXECUTION_ID", "exec-ml-offline")
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    secret_observation = "observacao confidencial do lote"
    processor = ItemProcessor(
        {"L001"},
        ml_enabled=True,
        ml_client=OfflineClient(),
    )

    result = processor.process(
        {
            "lote_id": "L001",
            "produto": "Monitor",
            "linha": "Linha A",
            "turno": "Manha",
            "status": "EM ANALISE",
            "responsavel": "Operador",
            "data": "2026-08-19",
            "observacao": secret_observation,
        }
    )

    assert result.resultado == "REVISAO_ML_OFFLINE"
    content = log_file.read_text(encoding="utf-8")
    record = json.loads(content)
    assert record["evento"] == "REVISAO_ML_OFFLINE"
    assert record["detalhes"]["lote_id"] == "L001"
    assert record["detalhes"]["classe"] is None
    assert record["detalhes"]["resultado_aplicado"] == "REVISAO_ML_OFFLINE"
    assert "exception" not in record["detalhes"]
    assert secret_observation not in content


def test_falha_de_comunicacao_registra_tipo_sem_traceback(tmp_path):
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        raise TimeoutError("detalhe interno que nao deve ser registrado")

    client = MLClient("http://ml.test", 1, transport=unavailable)
    result = client.classificar(
        lote_id="L001",
        status_raw="PENDENTE",
        turno="B",
        tem_obs=False,
    )

    assert result is None
    record = json.loads(log_file.read_text(encoding="utf-8"))
    assert record["evento"] == "FALHA_COMUNICACAO_ML"
    assert record["detalhes"]["ml_error_type"] == "TimeoutError"
    assert record["detalhes"]["falhas_consecutivas"] == 1
    assert "exception" not in record["detalhes"]
    assert "detalhe interno" not in record["detalhes"]["mensagem"]


def test_abertura_do_circuit_breaker_e_registrada_uma_unica_vez(tmp_path):
    settings = Settings.from_env(tmp_path)
    log_file = tmp_path / "logs" / "execucao.log"
    configure_logging(log_file, settings)
    network_calls = 0

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        nonlocal network_calls
        network_calls += 1
        raise ConnectionError("offline")

    client = MLClient("http://ml.test", 1, transport=unavailable)
    for index in range(7):
        assert client.classificar(
            lote_id=f"L{index:03d}",
            status_raw="PENDENTE",
            turno="C",
            tem_obs=False,
        ) is None

    events = [
        json.loads(line)["evento"]
        for line in log_file.read_text(encoding="utf-8").splitlines()
    ]
    assert network_calls == 5
    assert events.count("FALHA_COMUNICACAO_ML") == 5
    assert events.count("CIRCUIT_BREAKER_ML") == 1


def test_todos_os_itens_apos_abertura_do_circuito_preservam_auditoria(tmp_path):
    network_calls = 0

    def unavailable(url: str, body: bytes, timeout: float) -> bytes:
        nonlocal network_calls
        network_calls += 1
        raise ConnectionError("offline")

    client = MLClient("http://ml.test", 0.1, transport=unavailable)
    recorder = MLDecisionRecorder("bot-ml", "exec-sabotagem")
    processor = ItemProcessor(
        {f"L{index:03d}" for index in range(7)},
        ml_enabled=True,
        ml_client=client,
        decision_recorder=recorder,
    )

    results = [
        processor.process(
            {
                "lote_id": f"L{index:03d}",
                "produto": "Monitor",
                "linha": "Linha A",
                "turno": "A",
                "status": "PENDENTE",
                "responsavel": "Operador",
                "data": "2026-08-19",
                "observacao": "",
            }
        )
        for index in range(7)
    ]

    assert network_calls == 5
    assert client.circuit_open
    assert all(result.resultado == "REVISAO_ML_OFFLINE" for result in results)
    assert len(recorder.decisions) == 7
    assert len({decision.lote_id for decision in recorder.decisions}) == 7
    assert all(
        decision.resultado_aplicado == "REVISAO_ML_OFFLINE"
        for decision in recorder.decisions
    )
