from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.build_smart_office_packages import build_packages, load_manifest, sha256
from scripts.validate_smart_office_packages import validate_packages

pytestmark = pytest.mark.unit


def test_gera_e_valida_seis_pacotes_independentes(tmp_path: Path) -> None:
    base_dir = Path(__file__).resolve().parents[2]

    artifacts = build_packages(base_dir, tmp_path)
    validated = validate_packages(base_dir, tmp_path)

    assert validated == artifacts
    assert len(artifacts) == 6
    for artifact in artifacts:
        with ZipFile(artifact) as package:
            assert {"bot.py", "requirements.txt", "package-manifest.json"} <= set(
                package.namelist()
            )
            assert ".env" not in package.namelist()
            assert all("tests/" not in name for name in package.namelist())


def test_build_e_deterministico(tmp_path: Path) -> None:
    base_dir = Path(__file__).resolve().parents[2]
    first = build_packages(base_dir, tmp_path / "first")
    second = build_packages(base_dir, tmp_path / "second")

    assert [sha256(path) for path in first] == [sha256(path) for path in second]


def test_manifesto_traduz_prioridade_e_define_fan_in() -> None:
    base_dir = Path(__file__).resolve().parents[2]
    packages = load_manifest(base_dir)["packages"]
    by_id = {item["bot_id"]: item for item in packages}

    assert by_id["estoque-desktop-v1"]["priority_smart_office"] == 1
    assert by_id["estoque-desktop-v1"]["priority_local"] == 100
    assert by_id["consolidacao-v2"]["predecessors"] == [
        "estoque-desktop-v1",
        "fornecedores-web-v1",
    ]
    assert all(item["timeout_seconds"] > 0 for item in packages)


def test_manifestos_embutidos_nao_contem_valores_do_env_local(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_dir = Path(__file__).resolve().parents[2]
    sentinel = "segredo-local-que-nao-pode-ser-empacotado"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", sentinel)
    monkeypatch.setenv("SMTP_PASSWORD", sentinel)

    for artifact in build_packages(base_dir, tmp_path):
        with ZipFile(artifact) as package:
            manifest = package.read("package-manifest.json").decode("utf-8")
            assert json.loads(manifest)["bot_id"] in artifact.name
            assert sentinel not in manifest
