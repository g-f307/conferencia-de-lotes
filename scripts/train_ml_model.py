"""Gera dados ficticios e treina o classificador do Exercicio 24-A."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import random
from typing import Sequence

import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_PATH = PROJECT_ROOT / "dados_ml" / "historico_lotes.csv"
DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "classificador_lotes.pkl"
MINIMUM_SAMPLES = 200
FEATURE_COLUMNS = ("status_raw", "turno", "tem_obs")
TARGET_COLUMN = "classe"
CLASSES = (
    "valido_automatico",
    "revisar",
    "recusar_automatico",
)
AMBIGUOUS_STATUSES = (
    "EM ANALISE",
    "AJUSTE DE LINHA",
    "ESPECIFICACAO EM REVISAO",
    "PENDENTE",
)
STATUS_RISK = {
    "EM ANALISE": 0,
    "AJUSTE DE LINHA": 1,
    "ESPECIFICACAO EM REVISAO": 2,
    "PENDENTE": 1,
}
SHIFT_RISK = {"A": 0, "B": 1, "C": 2}


@dataclass(frozen=True)
class TrainingResult:
    dataset_path: str
    model_path: str
    samples: int
    train_samples: int
    test_samples: int
    accuracy: float
    classes: tuple[str, ...]
    seed: int


def classify_scenario(status: str, turno: str, has_observation: bool) -> str:
    """Aplica a regra ficticia usada somente para gerar o historico de ML."""
    observation_risk = -2 if has_observation else 1
    risk_score = STATUS_RISK[status] + SHIFT_RISK[turno] + observation_risk
    if risk_score <= 0:
        return "valido_automatico"
    if risk_score >= 3:
        return "recusar_automatico"
    return "revisar"


def build_scenarios() -> list[dict[str, object]]:
    """Cria todas as combinacoes do dominio ambiguo e seus rotulos."""
    return [
        {
            "status_raw": status,
            "turno": turno,
            "tem_obs": has_observation,
            "classe": classify_scenario(status, turno, has_observation),
        }
        for status in AMBIGUOUS_STATUSES
        for turno in SHIFT_RISK
        for has_observation in (False, True)
    ]


def generate_dataset(samples: int, seed: int) -> list[dict[str, object]]:
    """Gera cenarios ficticios balanceados, sem usar dados de producao."""
    if samples < MINIMUM_SAMPLES:
        raise ValueError(f"O dataset deve ter ao menos {MINIMUM_SAMPLES} amostras")

    randomizer = random.Random(seed)
    scenarios = build_scenarios()
    scenarios_by_class = {
        target: [row for row in scenarios if row["classe"] == target]
        for target in CLASSES
    }
    selected = list(scenarios)
    class_counts = Counter(str(row["classe"]) for row in selected)

    while len(selected) < samples:
        target = min(CLASSES, key=lambda value: class_counts[value])
        selected.append(dict(randomizer.choice(scenarios_by_class[target])))
        class_counts[target] += 1

    randomizer.shuffle(selected)
    return [
        {"lote_id": f"ML-{index + 1:04d}", **scenario}
        for index, scenario in enumerate(selected, start=0)
    ]


def write_dataset(records: Sequence[dict[str, object]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=("lote_id", *FEATURE_COLUMNS, TARGET_COLUMN),
        )
        writer.writeheader()
        writer.writerows(records)


def build_pipeline(seed: int) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=(
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                [0, 1],
            ),
            ("boolean", "passthrough", [2]),
        )
    )
    classifier = RandomForestClassifier(
        n_estimators=200,
        min_samples_leaf=2,
        class_weight="balanced",
        random_state=seed,
        n_jobs=1,
    )
    return Pipeline(
        steps=(
            ("preprocessamento", preprocessor),
            ("classificador", classifier),
        )
    )


def train_model(
    records: Sequence[dict[str, object]],
    model_path: Path,
    seed: int,
    dataset_path: Path,
) -> TrainingResult:
    features = [
        [record[column] for column in FEATURE_COLUMNS]
        for record in records
    ]
    targets = [str(record[TARGET_COLUMN]) for record in records]
    train_x, test_x, train_y, test_y = train_test_split(
        features,
        targets,
        test_size=0.25,
        random_state=seed,
        stratify=targets,
    )

    pipeline = build_pipeline(seed)
    pipeline.fit(train_x, train_y)
    predictions = pipeline.predict(test_x)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, model_path)

    return TrainingResult(
        dataset_path=str(dataset_path),
        model_path=str(model_path),
        samples=len(records),
        train_samples=len(train_x),
        test_samples=len(test_x),
        accuracy=round(float(accuracy_score(test_y, predictions)), 6),
        classes=tuple(str(value) for value in pipeline.classes_),
        seed=seed,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera o dataset ficticio e treina o classificador de lotes."
    )
    parser.add_argument("--samples", type=int, default=300)
    parser.add_argument("--seed", type=int, default=24)
    parser.add_argument("--dataset-output", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--model-output", type=Path, default=DEFAULT_MODEL_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    records = generate_dataset(args.samples, args.seed)
    write_dataset(records, args.dataset_output)
    result = train_model(
        records,
        model_path=args.model_output,
        seed=args.seed,
        dataset_path=args.dataset_output,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
