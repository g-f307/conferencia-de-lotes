"""Ciclo principal sob responsabilidade do núcleo da automação."""

import json
import logging
from pathlib import Path
from typing import Protocol

from src.config import Settings
from src.logging_config import configure_logging
from src.models import ExecutionResult


class AlertGateway(Protocol):
    """Contrato que o adaptador Maestro deverá implementar."""

    def send_error_alert(self, message: str) -> None: ...


def save_execution_report(result: ExecutionResult, report_dir: Path) -> Path:
    """Persiste o resumo local que depois será publicado como artefato."""
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "resumo_execucao.json"
    report_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report_path


def run(
    settings: Settings | None = None,
    alert_gateway: AlertGateway | None = None,
    logger: logging.Logger | None = None,
) -> ExecutionResult:
    """Valida o ambiente antes de entregar o controle ao Performer.

    O consumo do DataPool será conectado após os PRs de Marcelo e Rebecca.
    Este núcleo já define o contrato do alerta necessário no fail-fast.
    """
    current_settings = settings or Settings.from_env()
    current_logger = logger or configure_logging(current_settings.log_file)
    result = ExecutionResult()

    try:
        current_settings.validate()
    except ValueError as exc:
        current_logger.error("Configuração inválida: %s", exc)
        return result.fail(str(exc))

    if not current_settings.input_dir.is_dir():
        message = f"Pasta de entrada inexistente: {current_settings.input_dir}"
        current_logger.error(message)
        if alert_gateway is not None:
            try:
                alert_gateway.send_error_alert(message)
            except Exception:
                current_logger.exception("Não foi possível emitir o alerta no Maestro")
        return result.fail(message)

    current_logger.info("Estrutura inicial validada; bot pronto para o Performer")
    result.message = "Estrutura inicial validada"
    return result.complete()


def main() -> int:
    """Converte o resultado padronizado em código de saída do processo."""
    result = run()
    return 0 if result.status in {"SUCCESS", "PARTIALLY_COMPLETED"} else 1
