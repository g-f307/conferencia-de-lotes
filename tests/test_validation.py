import pytest

from src.validation import HumanReviewStatus, ValidationError, normalize_status, validate_lote


REFERENCE_LOTES = {"L001", "L002"}


def valid_item(**overrides):
    item = {
        "lote_id": "L001",
        "produto": "Monitor",
        "linha": "Linha A",
        "turno": "Manha",
        "status": "APROVADO",
        "responsavel": "Rebecca",
        "data": "2026-07-19",
        "observacao": "",
    }
    item.update(overrides)
    return item


def test_validate_lote_accepts_valid_item_and_normalizes_text():
    result = validate_lote(valid_item(status=" ok ", produto=" Monitor "), REFERENCE_LOTES)

    assert result["status"] == "APROVADO"
    assert result["produto"] == "Monitor"


def test_rn01_requires_exact_eight_columns():
    item = valid_item()
    del item["observacao"]

    with pytest.raises(ValidationError, match="RN01"):
        validate_lote(item, REFERENCE_LOTES)


def test_rn02_rejects_empty_required_field():
    with pytest.raises(ValidationError, match="RN02.*produto"):
        validate_lote(valid_item(produto=" "), REFERENCE_LOTES)


def test_rn03_rejects_lote_outside_reference_base():
    with pytest.raises(ValidationError, match="RN03"):
        validate_lote(valid_item(lote_id="L999"), REFERENCE_LOTES)


def test_rn04_rejects_non_official_status():
    with pytest.raises(ValidationError, match="RN04"):
        validate_lote(valid_item(status="cancelado"), REFERENCE_LOTES)


def test_rn05_normalizes_ok_and_nok_before_validation():
    assert normalize_status("ok") == "APROVADO"
    assert normalize_status(" NOK ") == "REPROVADO"


def test_rn06_separates_ambiguous_status_for_human_review():
    with pytest.raises(HumanReviewStatus, match="RN06"):
        validate_lote(valid_item(status="pendente"), REFERENCE_LOTES)


def test_rn07_requires_observation_for_reproved_lote():
    with pytest.raises(ValidationError, match="RN07"):
        validate_lote(valid_item(status="NOK", observacao=""), REFERENCE_LOTES)


def test_rn07_accepts_reproved_lote_with_observation():
    result = validate_lote(valid_item(status="NOK", observacao="Falha visual"), REFERENCE_LOTES)

    assert result["status"] == "REPROVADO"
