from __future__ import annotations

import csv
from pathlib import Path

import joblib
import pytest

from scripts.train_ml_model import (
    AMBIGUOUS_STATUSES,
    CLASSES,
    FEATURE_COLUMNS,
    generate_dataset,
    train_model,
    write_dataset,
)


pytestmark = pytest.mark.unit


def test_generate_dataset_is_reproducible_and_complete():
    first = generate_dataset(samples=210, seed=24)
    second = generate_dataset(samples=210, seed=24)

    assert first == second
    assert len(first) == 210
    assert {str(record["classe"]) for record in first} == set(CLASSES)
    assert all(
        all(column in record for column in FEATURE_COLUMNS)
        for record in first
    )


def test_generate_dataset_rejects_less_than_minimum():
    with pytest.raises(ValueError, match="ao menos 200"):
        generate_dataset(samples=199, seed=24)


def test_every_ambiguous_status_is_represented_in_all_classes():
    records = generate_dataset(samples=300, seed=24)

    classes_by_status = {
        status: {
            str(record["classe"])
            for record in records
            if record["status_raw"] == status
        }
        for status in AMBIGUOUS_STATUSES
    }

    assert all(
        classes == set(CLASSES)
        for classes in classes_by_status.values()
    )


def test_training_serializes_pipeline_with_expected_classes(tmp_path: Path):
    records = generate_dataset(samples=210, seed=24)
    dataset_path = tmp_path / "historico.csv"
    model_path = tmp_path / "classificador.pkl"
    write_dataset(records, dataset_path)

    result = train_model(records, model_path, seed=24, dataset_path=dataset_path)
    persisted_model = joblib.load(model_path)

    assert result.samples == 210
    assert result.accuracy >= 0.80
    assert set(result.classes) == set(CLASSES)
    assert set(str(value) for value in persisted_model.classes_) == set(CLASSES)
    automatic_cases = (
        (["EM ANALISE", "A", True], "valido_automatico"),
        (["ESPECIFICACAO EM REVISAO", "C", False], "recusar_automatico"),
    )
    for features, expected_class in automatic_cases:
        predicted_class = str(persisted_model.predict([features])[0])
        probability = float(max(persisted_model.predict_proba([features])[0]))
        assert predicted_class == expected_class
        assert probability >= 0.85
    with dataset_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 210
