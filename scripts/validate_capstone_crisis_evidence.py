"""Valida o conjunto sanitizado de evidências das sabotagens do Capstone."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

REQUIRED_SCENARIOS = frozenset(
    {
        "base_referencia_indisponivel",
        "servico_ml_indisponivel",
        "timeout_cancelamento_dependencia",
        "falha_canal_notificacao",
        "concorrencia_official_shadow",
        "dado_irrecuperavel",
    }
)
REQUIRED_FIELDS = frozenset(
    {
        "schema_version",
        "scope",
        "scenario",
        "input",
        "sabotage",
        "observed_states",
        "processed_count",
        "terminal_count",
        "fallback",
        "alerts",
        "dead_letters",
        "duplicates",
        "artifacts",
        "identifiers",
    }
)
FORBIDDEN_CONTENT = (
    "demo-local",
    "senha=",
    "token=",
    "/home/",
    "c:\\users\\",
)


def validate_evidence_directory(directory: Path) -> dict[str, object]:
    """Rejeita conjuntos incompletos, não locais ou potencialmente sensíveis."""
    evidence_dir = Path(directory)
    index_path = evidence_dir / "resumo_cenarios.json"
    if not index_path.is_file():
        raise ValueError(f"índice de evidências ausente: {index_path}")
    index = _read_json(index_path)
    indexed = index.get("scenarios")
    if not isinstance(indexed, list):
        raise ValueError("resumo_cenarios.json deve conter uma lista scenarios")
    scenarios = {
        str(item.get("scenario")): item
        for item in indexed
        if isinstance(item, Mapping) and item.get("scenario")
    }
    if set(scenarios) != REQUIRED_SCENARIOS:
        missing = sorted(REQUIRED_SCENARIOS - scenarios.keys())
        unexpected = sorted(scenarios.keys() - REQUIRED_SCENARIOS)
        raise ValueError(
            f"conjunto de cenários inválido; ausentes={missing}; extras={unexpected}"
        )

    for scenario in sorted(REQUIRED_SCENARIOS):
        scenario_path = evidence_dir / f"{scenario}.json"
        evidence = _read_json(scenario_path)
        if evidence != scenarios[scenario]:
            raise ValueError(f"índice diverge da evidência do cenário {scenario}")
        _validate_evidence(evidence, scenario_path)
    return index


def _validate_evidence(evidence: Mapping[str, object], path: Path) -> None:
    missing = REQUIRED_FIELDS - evidence.keys()
    if missing:
        raise ValueError(f"{path.name} sem campos: {sorted(missing)}")
    if evidence["scope"] != "LOCAL_CONTROLLED":
        raise ValueError(f"{path.name} possui escopo diferente de LOCAL_CONTROLLED")
    if int(evidence["processed_count"]) <= 0 or int(evidence["terminal_count"]) <= 0:
        raise ValueError(f"{path.name} possui contagens não positivas")
    identifiers = evidence.get("identifiers")
    if not isinstance(identifiers, Mapping):
        raise ValueError(f"{path.name} não possui identificadores estruturados")
    _validate_identifiers(identifiers, path.name)


def _validate_identifiers(identifiers: Mapping[str, object], source: str) -> None:
    for key in ("execution_id", "correlation_id", "root_task_id"):
        _require_local_id(identifiers.get(key), f"{source}:{key}")
    if identifiers.get("task_scope") != "local":
        raise ValueError(f"{source} não declara task_scope local")
    task_chain = identifiers.get("task_chain")
    if not isinstance(task_chain, list) or len(task_chain) != 6:
        raise ValueError(f"{source} deve registrar a cadeia local dos seis bots")
    for task in task_chain:
        if not isinstance(task, Mapping):
            raise ValueError(f"{source} possui task inválida")
        _require_local_id(task.get("current_task_id"), f"{source}:current_task_id")
        parent = task.get("parent_task_id")
        if parent is not None:
            _require_local_id(parent, f"{source}:parent_task_id")
        predecessors = task.get("predecessor_task_ids")
        if not isinstance(predecessors, list):
            raise ValueError(f"{source} possui predecessores inválidos")
        for predecessor in predecessors:
            _require_local_id(predecessor, f"{source}:predecessor_task_id")
    related = identifiers.get("related_executions", [])
    if not isinstance(related, list):
        raise ValueError(f"{source} possui related_executions inválido")
    for index, item in enumerate(related):
        if not isinstance(item, Mapping):
            raise ValueError(f"{source} possui execução relacionada inválida")
        _validate_identifiers(item, f"{source}:related_executions[{index}]")


def _require_local_id(value: object, field: str) -> None:
    if not str(value or "").startswith("local-"):
        raise ValueError(f"{field} deve usar identificador local")


def _read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ValueError(f"evidência ausente: {path}")
    content = path.read_text(encoding="utf-8")
    lowered = content.casefold()
    if any(marker in lowered for marker in FORBIDDEN_CONTENT):
        raise ValueError(f"{path.name} contém informação potencialmente sensível")
    loaded = json.loads(content)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path.name} deve conter um objeto JSON")
    return loaded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path("dist/evidencias-capstone"),
    )
    args = parser.parse_args()
    index = validate_evidence_directory(args.directory)
    print(f"Evidências Capstone válidas: {len(index['scenarios'])} cenários")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
