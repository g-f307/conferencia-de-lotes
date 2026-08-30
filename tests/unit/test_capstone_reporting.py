from __future__ import annotations

import json
import logging
from email.message import EmailMessage
from pathlib import Path
from typing import Self

import pytest

from src.alerts import Alerta, CanalEmail, Severidade, SistemaAlertas
from src.capstone_reporting import (
    CapstoneReportInputError,
    CapstoneReportService,
    build_capstone_alerts,
    build_report_snapshot,
    renderers,
)

pytestmark = pytest.mark.unit


def _decision(lote_id: str = "L001") -> dict[str, object]:
    return {
        "timestamp": "2026-08-30T12:00:00+00:00",
        "execution_id": "exec-capstone-001",
        "bot_id": "classificador-ml-v1",
        "lote_id": lote_id,
        "classe": "divergencia_quantidade",
        "probabilidade": 0.91,
        "nivel_confianca": "alta",
        "acao": "revisar",
        "resultado_aplicado": "DIVERGENCIA",
        "latencia_ms": 12.5,
        "causa_provavel": "divergencia_quantidade",
        "origem_decisao": "ml",
        "confianca_ml": 0.91,
        "motivo_fallback": None,
    }


def _business_payload() -> dict[str, object]:
    decision = _decision()
    return {
        "report_type": "BUSINESS",
        "task_id": "task-report-001",
        "degraded_duration_seconds": 0,
        "source_statuses": {
            "estoque-desktop-v1": "AVAILABLE",
            "fornecedores-web-v1": "AVAILABLE",
        },
        "consolidation_result": {
            "status": "SUCCESS",
            "modo_degradado": False,
            "payload": {
                "records": [
                    {
                        "lote_id": "L001",
                        "status_operacional": "DIVERGENCIA",
                        "classificacao": "Divergência",
                        "regras_violadas": ["RN05"],
                        "regra_aplicada": "RN05",
                        "origens_consultadas": ["estoque", "pedidos", "validacao"],
                        "fontes_ausentes": [],
                        "modo_degradado": False,
                        "validacao": {
                            "campos_originais": {
                                "lote_id": "L001",
                                "produto": "Produto A",
                                "observacao": "texto operacional sensível",
                                "password": "segredo",
                                "erp_password": "segredo-composto",
                            },
                            "status_original": "REPROVADO",
                            "status_normalizado": "REPROVADO",
                            "classificacao": "Divergência",
                            "motivo": "RN05",
                            "regras_violadas": ["RN05"],
                            "data_referencia": "2026-08-30",
                            "aba_origem": "Dia 1",
                            "linha_origem": 2,
                            "regra_aplicada": "RN05",
                        },
                    }
                ],
                "item_failures": [],
                "total_items": 1,
                "processed_items": 1,
                "failed_items": 0,
                "review_items": 0,
            },
        },
        "ml_result": {
            "status": "SUCCESS",
            "execution_id": "exec-capstone-001",
            "correlation_id": "corr-capstone-001",
            "root_task_id": "task-root-001",
            "task_id": "task-ml-001",
            "modo_degradado": False,
            "payload": {
                "records": [{"lote_id": "L001", "decisao_ml": decision}],
                "ml_decisions": [decision],
            },
        },
    }


def _incident_payload() -> dict[str, object]:
    return {
        "report_type": "OPERATIONAL_INCIDENT",
        "task_id": "task-report-incident",
        "degraded_duration_seconds": 600,
        "source_statuses": {
            "estoque-desktop-v1": "UNAVAILABLE",
            "fornecedores-web-v1": "DEGRADED",
        },
        "consolidation_result": {
            "status": "FAILED",
            "snapshot_type": "OPERATIONAL_FAILURE",
            "execution_id": "exec-incident-001",
            "correlation_id": "corr-incident-001",
            "root_task_id": "task-root-incident",
            "expected_items": 4,
            "processed_items": 0,
            "failed_items": 4,
            "review_items": 4,
            "modo_degradado": True,
            "motivo_fallback": "consolidation_timeout",
            "failure_code": "consolidation_timeout",
            "available_artifacts": [
                {
                    "type": "dead_letter",
                    "path": "data/output/dead_letter.jsonl",
                }
            ],
            "payload": {},
        },
        "ml_result": {
            "status": "FAILED",
            "payload": {"ml_decisions": []},
        },
    }


def test_snapshot_reune_contexto_hibrido_sem_dados_sensiveis() -> None:
    snapshot = build_report_snapshot(_business_payload())

    assert snapshot.execution_id == "exec-capstone-001"
    assert snapshot.items[0].origem_decisao == "ml"
    assert snapshot.items[0].confianca_ml == pytest.approx(0.91)
    assert snapshot.items[0].status_coleta_desktop == "AVAILABLE"
    serialized = json.dumps(snapshot.to_dict(), ensure_ascii=False)
    assert "texto operacional sensível" not in serialized
    assert "segredo" not in serialized
    assert "segredo-composto" not in serialized
    assert "password" not in serialized


def test_snapshot_rejeita_contadores_inconsistentes() -> None:
    payload = _business_payload()
    payload["consolidation_result"]["payload"]["total_items"] = 2  # type: ignore[index]

    with pytest.raises(CapstoneReportInputError, match="total_items inconsistente"):
        build_report_snapshot(payload)


def test_snapshot_conta_falha_de_item_uma_unica_vez() -> None:
    payload = _business_payload()
    consolidation_payload = payload["consolidation_result"]["payload"]  # type: ignore[index]
    consolidation_payload["item_failures"] = [  # type: ignore[index]
        {
            "fonte": "pedidos",
            "lote_id": "L002",
            "codigo": "INVALID_SUPPLIER_ITEM",
        }
    ]
    consolidation_payload["total_items"] = 2  # type: ignore[index]
    consolidation_payload["failed_items"] = 1  # type: ignore[index]

    snapshot = build_report_snapshot(payload)

    assert snapshot.total_items == 2
    assert snapshot.failed_items == 1
    assert snapshot.classification_counts["Erro de Entrada"] == 1


def test_fonte_indisponivel_marca_item_e_snapshot_como_degradados() -> None:
    payload = _business_payload()
    payload["source_statuses"]["estoque-desktop-v1"] = "UNAVAILABLE"  # type: ignore[index]

    snapshot = build_report_snapshot(payload)

    assert snapshot.modo_degradado is True
    assert snapshot.items[0].modo_degradado is True
    assert snapshot.items[0].motivo_fallback == "fonte_indisponivel"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_status", "DESCONHECIDO", "source_statuses"),
        ("classification", "Talvez", "classificacao desconhecida"),
        ("decision_origin", "manual", "origem_decisao desconhecida"),
    ),
)
def test_snapshot_rejeita_dominios_desconhecidos(
    field: str,
    value: str,
    message: str,
) -> None:
    payload = _business_payload()
    if field == "source_status":
        payload["source_statuses"]["estoque-desktop-v1"] = value  # type: ignore[index]
    elif field == "classification":
        payload["consolidation_result"]["payload"]["records"][0][  # type: ignore[index]
            "classificacao"
        ] = value
    else:
        payload["ml_result"]["payload"]["records"][0]["decisao_ml"][  # type: ignore[index]
            "origem_decisao"
        ] = value
        payload["ml_result"]["payload"]["ml_decisions"] = []  # type: ignore[index]

    with pytest.raises(CapstoneReportInputError, match=message):
        build_report_snapshot(payload)


def test_snapshot_rejeita_fallback_livre_que_poderia_expor_segredo() -> None:
    payload = _business_payload()
    payload["motivo_fallback"] = "password=segredo"

    with pytest.raises(CapstoneReportInputError, match="motivo_fallback desconhecido"):
        build_report_snapshot(payload)


def test_alertas_capstone_cobrem_cinco_eventos_operacionais(tmp_path: Path) -> None:
    attachment = tmp_path / "incidente.pdf"
    attachment.write_bytes(b"pdf")
    alerts = build_capstone_alerts(
        build_report_snapshot(_incident_payload()),
        attachment,
        degraded_alert_seconds=300,
    )

    assert {alert.evento for alert in alerts} == {
        "execucao_critica",
        "modo_degradado_prolongado",
        "ml_indisponivel",
        "desktop_indisponivel",
        "dead_letter_produzido",
    }
    assert all(alert.anexo == attachment for alert in alerts)
    critical = next(alert for alert in alerts if alert.evento == "execucao_critica")
    assert critical.motivo_predominante == "A consolidação excedeu o tempo limite"


def test_desktop_degradado_nao_e_reportado_como_indisponivel(tmp_path: Path) -> None:
    payload = _business_payload()
    payload["source_statuses"]["estoque-desktop-v1"] = "DEGRADED"  # type: ignore[index]
    payload["degraded_duration_seconds"] = 600
    attachment = tmp_path / "relatorio.xlsx"
    attachment.write_bytes(b"xlsx")

    alerts = build_capstone_alerts(
        build_report_snapshot(payload),
        attachment,
        degraded_alert_seconds=300,
    )

    assert "modo_degradado_prolongado" in {alert.evento for alert in alerts}
    assert "desktop_indisponivel" not in {alert.evento for alert in alerts}


def test_pdf_recebe_os_mesmos_totais_de_classificacao(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_rows: list[list[list[object]]] = []

    class FakeDocument:
        def build(self, story: list[object]) -> None:
            return None

    def capture_table(
        rows: list[list[object]],
        widths: tuple[float, ...],
    ) -> object:
        captured_rows.append(rows)
        return object()

    monkeypatch.setattr(renderers, "SimpleDocTemplate", lambda *args, **kwargs: FakeDocument())
    monkeypatch.setattr(renderers, "_pdf_table", capture_table)

    snapshot = build_report_snapshot(_business_payload())
    renderers.write_capstone_pdf(snapshot, tmp_path / "relatorio.pdf")

    assert ["Divergência", 1] in captured_rows[0]
    assert ["Válido", 0] in captured_rows[0]
    assert ["Ambíguo", 0] in captured_rows[0]
    assert ["Erro de Entrada", 0] in captured_rows[0]


class _FakeSMTP:
    def __init__(self) -> None:
        self.message: EmailMessage | None = None
        self.started_tls = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        raise AssertionError("login não deveria ser usado neste teste")

    def send_message(self, message: EmailMessage) -> None:
        self.message = message


def test_email_anexa_relatorio_final(tmp_path: Path) -> None:
    attachment = tmp_path / "relatorio.xlsx"
    attachment.write_bytes(b"conteudo-xlsx")
    smtp = _FakeSMTP()
    channel = CanalEmail(
        "smtp.example.test",
        587,
        "bot@example.test",
        ("operacao@example.test",),
        smtp_factory=lambda *args, **kwargs: smtp,
    )
    channel.enviar(
        Alerta(
            Severidade.CRITICO,
            "exec-001",
            "relatorio-alertas-v2",
            1,
            "falha_operacional",
            "FAILED",
            anexo=attachment,
        )
    )

    assert smtp.message is not None
    attachments = list(smtp.message.iter_attachments())
    assert [part.get_filename() for part in attachments] == ["relatorio.xlsx"]
    assert attachments[0].get_payload(decode=True) == b"conteudo-xlsx"


class _SuccessfulChannel:
    def __init__(self, name: str) -> None:
        self.nome = name

    def enviar(self, alerta: Alerta) -> None:
        return None


def test_sistema_alertas_registra_cada_entrega_bem_sucedida(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("capstone-alert-delivery-test")
    system = SistemaAlertas(
        _SuccessfulChannel("telegram"),
        _SuccessfulChannel("email"),
        _SuccessfulChannel("log_local"),
        logger=logger,
    )
    alert = Alerta(
        Severidade.CRITICO,
        "exec-001",
        "relatorio-alertas-v2",
        1,
        "falha_operacional",
        "FAILED",
    )

    with caplog.at_level(logging.INFO, logger=logger.name):
        result = system.notificar(alert)

    assert result.entregues == ("telegram", "email")
    assert "Alerta entregue pelo canal telegram" in caplog.text
    assert "Alerta entregue pelo canal email" in caplog.text


class _BrokenAlertSystem:
    def notificar(self, alerta: Alerta) -> None:
        raise RuntimeError("canal indisponível")


def test_falha_total_de_notificacao_nao_interrompe_relatorio(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("capstone-report-test")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        result = CapstoneReportService(
            tmp_path,
            alerts=_BrokenAlertSystem(),  # type: ignore[arg-type]
            logger=logger,
        ).generate(_incident_payload())

    assert result.paths.pdf.is_file()
    assert result.paths.summary.is_file()
    assert all(item.status == "FAILED" for item in result.notification_results)
    assert "Falha inesperada no sistema de alertas" in caplog.text
