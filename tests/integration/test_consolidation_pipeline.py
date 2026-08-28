from __future__ import annotations

from src.consolidation import STATUS_APROVADO, STATUS_DIVERGENCIA, ConsolidationService
from src.excel_reporting import ValidationService


def validation(lote_id: str, produto: str):
    return ValidationService(["L001", "L002"]).validar_registro(
        {
            "lote_id": lote_id,
            "produto": produto,
            "linha": "Linha A",
            "status": "APROVADO",
            "responsavel": "Equipe",
            "data": "28/08/2026",
            "observacao": "",
        },
        aba_origem="Insp_28_08_2026",
        linha_origem=2,
    )


def test_consolida_envelopes_reais_dos_coletores_sem_acessar_interfaces():
    desktop_result = {
        "status": "SUCCESS",
        "payload": {
            "source_status": "AVAILABLE",
            "records": [
                {
                    "lote_id": "L001",
                    "produto": "Monitor",
                    "quantidade_disponivel": 10,
                    "localizacao": "A-01",
                    "status_estoque": "DISPONIVEL",
                    "atualizado_em": "2026-08-28T10:00:00Z",
                },
                {
                    "lote_id": "L002",
                    "produto": "Teclado",
                    "quantidade_disponivel": 1,
                    "localizacao": "A-02",
                    "status_estoque": "BAIXO",
                    "atualizado_em": "2026-08-28T10:00:00Z",
                },
            ],
        },
    }
    web_result = {
        "status": "SUCCESS",
        "payload": {
            "source_status": "AVAILABLE",
            "records": [
                {
                    "pedido_id": "P001",
                    "lote_id": "L001",
                    "fornecedor": "Fornecedor A",
                    "produto": "Monitor",
                    "quantidade_solicitada": 5,
                    "status_pedido": "ABERTO",
                    "data_prevista": "30/08/2026",
                },
                {
                    "pedido_id": "P002",
                    "lote_id": "L002",
                    "fornecedor": "Fornecedor B",
                    "produto": "Teclado",
                    "quantidade_solicitada": 4,
                    "status_pedido": "ABERTO",
                    "data_prevista": "30/08/2026",
                },
            ],
        },
    }

    result = ConsolidationService().consolidate_envelopes(
        desktop_result,
        web_result,
        [validation("L001", "Monitor"), validation("L002", "Teclado")],
    )
    payload = result.to_dict()

    assert [item.status_operacional for item in result.registros] == [
        STATUS_APROVADO,
        STATUS_DIVERGENCIA,
    ]
    assert result.status == "SUCCESS"
    assert result.modo_degradado is False
    assert payload["ml_consultado"] is False
    assert payload["payload"]["processed_items"] == 2
    assert payload["payload"]["failed_items"] == 0
    assert all("regra_aplicada" in row for row in payload["payload"]["records"])
    assert all("origem_campos" in row for row in payload["payload"]["records"])
