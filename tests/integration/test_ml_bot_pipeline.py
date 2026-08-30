from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.classificador_divergencia import (
    ClassificadorDivergencia,
    PredicaoCausa,
)
from src.config import Settings
from src.consolidation import ConsolidationService
from src.desktop_stock.models import StockRecord
from src.excel_reporting import ValidationService
from src.ml_audit import MLDecisionRecorder
from src.ml_bot import MLBotContext, MLBotService, write_ml_bot_result
from src.ml_bot.main import run
from src.supplier_portal import SupplierOrder

pytestmark = pytest.mark.integration
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class SuccessfulProvider:
    def classificar(self, observacao: str, timeout_seconds: float) -> PredicaoCausa:
        return PredicaoCausa("ruptura_de_estoque", 0.92)


def consolidated_divergence() -> dict[str, object]:
    validation = ValidationService(["L001"]).validar_registro(
        {
            "lote_id": "L001",
            "produto": "Monitor",
            "linha": "Linha A",
            "status": "APROVADO",
            "responsavel": "Equipe",
            "data": "30/08/2026",
            "observacao": "estoque abaixo da quantidade solicitada",
        },
        aba_origem="Insp_30_08_2026",
        linha_origem=2,
    )
    stock = StockRecord(
        lote_id="L001",
        produto="Monitor",
        quantidade_disponivel=2,
        localizacao="A-01",
        status_estoque="BAIXO",
        atualizado_em="2026-08-30T12:00:00Z",
    )
    order = SupplierOrder(
        pedido_id="P001",
        lote_id="L001",
        fornecedor="Fornecedor controlado",
        produto="Monitor",
        quantidade_solicitada=5,
        status_pedido="ABERTO",
        data_prevista="31/08/2026",
    )
    return ConsolidationService().consolidate(
        [stock],
        [order],
        [validation],
    ).to_dict()


def test_consolidacao_e_bot_ml_compartilham_status_sem_nova_decisao(
    tmp_path: Path,
) -> None:
    moments = iter([1.0, 1.02])
    classifier = ClassificadorDivergencia(
        enabled=True,
        confianca_minima=0.8,
        timeout_seconds=0.5,
        provedor=SuccessfulProvider(),
        clock=lambda: next(moments),
    )
    recorder = MLDecisionRecorder(
        "classificador-ml-v1",
        "exec-integration-113",
        clock=lambda: datetime(2026, 8, 30, 12, tzinfo=timezone.utc),
    )
    context = MLBotContext(
        execution_id="exec-integration-113",
        correlation_id="corr-integration-113",
        root_task_id="root-integration-113",
        task_id="task-ml-integration-113",
        parent_task_id="task-consolidacao-integration-113",
        predecessor_task_ids=("task-consolidacao-integration-113",),
    )

    result = MLBotService(classifier, recorder).process(
        consolidated_divergence(),
        context,
    )
    destination = tmp_path / "classificacao-ml.json"
    write_ml_bot_result(result, destination)
    persisted = json.loads(destination.read_text(encoding="utf-8"))

    assert persisted["status"] == "SUCCESS"
    assert persisted["correlation_id"] == "corr-integration-113"
    item = persisted["payload"]["records"][0]
    assert item["resultado_deterministico"] == "DIVERGENCIA"
    assert item["decisao_ml"]["resultado_aplicado"] == "DIVERGENCIA"
    assert item["decisao_ml"]["causa_provavel"] == "ruptura_de_estoque"


def test_ponto_de_entrada_independente_conclui_com_ml_desabilitado(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "consolidacao.json"
    output_path = tmp_path / "classificacao-ml.json"
    input_path.write_text(
        json.dumps(consolidated_divergence(), ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("ML_ENABLED", "false")
    monkeypatch.setenv("EXECUTION_ID", "exec-entrypoint-113")
    monkeypatch.setenv("CORRELATION_ID", "corr-entrypoint-113")
    monkeypatch.setenv("ROOT_TASK_ID", "root-entrypoint-113")
    monkeypatch.setenv("TASK_ID", "task-ml-entrypoint-113")
    monkeypatch.setenv("PARENT_TASK_ID", "task-consolidacao-entrypoint-113")

    result = run(input_path, output_path, Settings.from_env(tmp_path))
    persisted = json.loads(output_path.read_text(encoding="utf-8"))

    assert result["status"] == "SUCCESS"
    assert persisted["execution_id"] == "exec-entrypoint-113"
    assert persisted["correlation_id"] == "corr-entrypoint-113"
    assert persisted["task_id"] == "task-ml-entrypoint-113"
    assert persisted["predecessor_task_ids"] == [
        "task-consolidacao-entrypoint-113"
    ]
    decision = persisted["payload"]["ml_decisions"][0]
    assert decision["motivo_fallback"] == "ml_desabilitado"
    assert decision["resultado_aplicado"] == "DIVERGENCIA"


def test_modulo_executavel_produz_envelope_sem_dependencia_http(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "consolidacao-subprocess.json"
    output_path = tmp_path / "classificacao-ml-subprocess.json"
    input_path.write_text(
        json.dumps(consolidated_divergence(), ensure_ascii=False),
        encoding="utf-8",
    )
    environment = {
        **os.environ,
        "ML_ENABLED": "false",
        "ML_INPUT_PATH": str(input_path),
        "ML_RESULT_PATH": str(output_path),
        "EXECUTION_ID": "exec-subprocess-113",
        "CORRELATION_ID": "corr-subprocess-113",
        "ROOT_TASK_ID": "root-subprocess-113",
        "TASK_ID": "task-ml-subprocess-113",
        "PARENT_TASK_ID": "task-consolidacao-subprocess-113",
        "PREDECESSOR_TASK_IDS": "task-consolidacao-subprocess-113",
        "MAESTRO_ENABLED": "false",
        "VAULT_ENABLED": "false",
    }

    completed = subprocess.run(
        [sys.executable, "-m", "src.ml_bot.main"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary["status"] == "SUCCESS"
    assert summary["eligible_items"] == 1
    assert persisted["execution_id"] == "exec-subprocess-113"
    assert persisted["correlation_id"] == "corr-subprocess-113"
    assert persisted["payload"]["ml_decisions"][0]["motivo_fallback"] == (
        "ml_desabilitado"
    )
