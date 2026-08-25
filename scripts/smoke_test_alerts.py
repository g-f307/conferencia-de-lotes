"""Envia um alerta controlado para homologar Telegram e Email reais."""

from __future__ import annotations

import json

from src.alerts import Alerta, Severidade, construir_sistema_alertas
from src.config import Settings
from src.logging_config import configure_logging


def main() -> int:
    settings = Settings.from_env()
    settings.validate()
    logger = configure_logging(settings.log_file, settings)
    alerts = construir_sistema_alertas(settings, logger)
    if alerts is None:
        raise RuntimeError("ALERTS_ENABLED deve ser true para o smoke test")

    result = alerts.notificar(
        Alerta(
            severidade=Severidade.ERRO,
            execution_id=settings.execution_id,
            bot_id=settings.bot_id,
            quantidade_afetada=1,
            motivo_predominante="smoke_test_controlado",
            estado_pipeline="HOMOLOGACAO_ALERTAS",
        )
    )
    print(
        json.dumps(
            {"entregues": result.entregues, "falhos": result.falhos},
            ensure_ascii=False,
        )
    )
    return 0 if {"telegram", "email"}.issubset(result.entregues) else 1


if __name__ == "__main__":
    raise SystemExit(main())
