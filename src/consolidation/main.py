"""Ponto de entrada independente do bot ``consolidacao-v2``."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

from src.excel_reporting.models import RegistroValidado

from .service import ConsolidationService


def _read_object(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"{path} deve conter um objeto JSON")
    return payload


def _read_validations(path: Path) -> tuple[RegistroValidado, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"{path} deve conter uma lista JSON")
    records: list[RegistroValidado] = []
    for item in payload:
        if not isinstance(item, Mapping):
            raise TypeError("cada validacao deve ser um objeto JSON")
        records.append(
            RegistroValidado(
                campos_originais=dict(item.get("campos_originais", {})),
                status_original=str(item.get("status_original", "")),
                status_normalizado=str(item.get("status_normalizado", "")),
                classificacao=str(item.get("classificacao", "")),
                motivo=str(item.get("motivo", "")),
                regras_violadas=tuple(item.get("regras_violadas", ())),
                data_referencia=str(item.get("data_referencia", "")),
                aba_origem=str(item.get("aba_origem", "")),
                linha_origem=int(item.get("linha_origem", 0)),
                regra_aplicada=str(item.get("regra_aplicada", "")),
            )
        )
    return tuple(records)


def run(
    desktop_path: Path,
    supplier_path: Path,
    validation_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Consolida os três contratos persistidos sem consultar serviços externos."""
    result = ConsolidationService().consolidate_envelopes(
        _read_object(desktop_path),
        _read_object(supplier_path),
        _read_validations(validation_path),
    ).to_dict()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return result


def main() -> int:
    result = run(
        Path(os.getenv("DESKTOP_RESULT_PATH", "data/output/desktop-stock.json")),
        Path(os.getenv("SUPPLIER_RESULT_PATH", "data/output/fornecedores.json")),
        Path(os.getenv("VALIDATION_RESULT_PATH", "data/output/validacoes.json")),
        Path(os.getenv("CONSOLIDATION_RESULT_PATH", "data/output/consolidacao.json")),
    )
    print(json.dumps({"status": result["status"]}, ensure_ascii=False))
    return 0 if result["status"] != "FAILED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
