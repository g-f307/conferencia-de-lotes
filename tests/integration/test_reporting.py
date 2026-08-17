import pytest

from src.reporting import generate_evidence_pdf


pytestmark = pytest.mark.integration


def test_generate_evidence_pdf_com_imagem(tmp_path):
    evidence_path = tmp_path / "evidencia.png"
    evidence_path.write_bytes(
        bytes.fromhex(
            "89504E470D0A1A0A0000000D494844520000000100000001"
            "0802000000907753DE0000000C4944415408D763F8CFC000"
            "000301010018DD8DB10000000049454E44AE426082"
        )
    )
    destination = tmp_path / "relatorios" / "relatorio_evidencias.pdf"

    path = generate_evidence_pdf(
        {
            "status": "PARTIALLY_COMPLETED",
            "message": "Processamento concluido",
            "total_items": 16,
            "processed_items": 4,
            "failed_items": 9,
            "ambiguous_items": 3,
            "errors": [],
            "started_at": "2026-07-29T13:13:05+00:00",
            "finished_at": "2026-07-29T13:14:11+00:00",
        },
        destination,
        {
            "bot_id": "bot-conferencia-de-lotes-v2",
            "execution_id": "24142275",
            "datapool_label": "FilaAuditoriaLotes2",
            "vault_label": "credencial_erp2",
            "web_enabled": True,
        },
        evidence_path,
    )

    assert path == destination
    assert path.read_bytes().startswith(b"%PDF-")
    assert path.stat().st_size > 1_000
