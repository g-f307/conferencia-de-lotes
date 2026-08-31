from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.consolidation.main import run

pytestmark = pytest.mark.unit


def test_entrypoint_consolida_contratos_persistidos(tmp_path: Path) -> None:
    desktop = tmp_path / "desktop.json"
    supplier = tmp_path / "supplier.json"
    validations = tmp_path / "validations.json"
    output = tmp_path / "consolidation.json"
    desktop.write_text(
        json.dumps(
            {
                "status": "SUCCESS",
                "payload": {
                    "records": [
                        {
                            "lote_id": "L001",
                            "produto": "Produto A",
                            "quantidade_disponivel": 20,
                            "localizacao": "A-01",
                            "status_estoque": "DISPONIVEL",
                            "atualizado_em": "2026-08-31T10:00:00Z",
                        }
                    ],
                    "source_status": "AVAILABLE",
                },
            }
        ),
        encoding="utf-8",
    )
    supplier.write_text(
        json.dumps(
            {
                "status": "SUCCESS",
                "payload": {
                    "records": [
                        {
                            "pedido_id": "P001",
                            "lote_id": "L001",
                            "fornecedor": "Fornecedor A",
                            "produto": "Produto A",
                            "quantidade_solicitada": 10,
                            "status_pedido": "CONFIRMADO",
                            "data_prevista": "2026-09-01",
                        }
                    ],
                    "source_status": "AVAILABLE",
                },
            }
        ),
        encoding="utf-8",
    )
    validations.write_text(
        json.dumps(
            [
                {
                    "campos_originais": {"lote_id": "L001"},
                    "status_original": "OK",
                    "status_normalizado": "APROVADO",
                    "classificacao": "Válido",
                    "motivo": "Registro válido",
                    "regras_violadas": [],
                    "data_referencia": "2026-08-31",
                    "aba_origem": "Dia 1",
                    "linha_origem": 2,
                    "regra_aplicada": "",
                }
            ]
        ),
        encoding="utf-8",
    )

    result = run(desktop, supplier, validations, output)

    assert result["status"] == "SUCCESS"
    assert result["payload"]["processed_items"] == 1
    assert json.loads(output.read_text(encoding="utf-8")) == result
