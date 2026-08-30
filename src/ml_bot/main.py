"""Ponto de entrada executável do bot independente de ML."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from src.config import Settings

from .models import MLBotContext
from .service import build_service_from_settings, write_ml_bot_result


def build_context_from_environment(settings: Settings) -> MLBotContext:
    task_id = os.getenv("TASK_ID", settings.maestro_task_id or "ml-task-local")
    parent_task_id = os.getenv("PARENT_TASK_ID") or None
    configured_predecessors = tuple(
        value.strip()
        for value in os.getenv("PREDECESSOR_TASK_IDS", "").split(",")
        if value.strip()
    )
    predecessors = configured_predecessors or (
        (parent_task_id,) if parent_task_id else ()
    )
    return MLBotContext(
        execution_id=os.getenv("EXECUTION_ID", settings.execution_id),
        correlation_id=os.getenv("CORRELATION_ID", settings.execution_id),
        root_task_id=os.getenv("ROOT_TASK_ID", task_id),
        task_id=task_id,
        parent_task_id=parent_task_id,
        predecessor_task_ids=predecessors,
    )


def run(
    input_path: Path,
    output_path: Path,
    settings: Settings,
) -> dict[str, object]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("o resultado da consolidação deve ser um objeto JSON")
    result = build_service_from_settings(settings).process(
        payload,
        build_context_from_environment(settings),
    )
    write_ml_bot_result(result, output_path)
    return result


def main() -> int:
    settings = Settings.from_env()
    input_path = Path(
        os.getenv("ML_INPUT_PATH", "data/output/consolidacao.json")
    )
    output_path = Path(
        os.getenv("ML_RESULT_PATH", "data/output/classificacao-ml.json")
    )
    result = run(input_path, output_path, settings)
    print(
        json.dumps(
            {
                "status": result["status"],
                "execution_id": result["execution_id"],
                "result_path": output_path.as_posix(),
                "eligible_items": result["payload"]["eligible_items"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
