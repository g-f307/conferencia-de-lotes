"""Valida estrutura, contrato e segurança dos seis pacotes do Capstone."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

try:
    from scripts.build_smart_office_packages import display_path, load_manifest
except ModuleNotFoundError:  # execução direta a partir da pasta scripts
    from build_smart_office_packages import display_path, load_manifest

REQUIRED_ROOT_FILES = {"bot.py", "requirements.txt", "package-manifest.json"}
FORBIDDEN_NAMES = {".env", "debug.log"}
FORBIDDEN_PARTS = {".git", "tests", "__pycache__"}
REQUIRED_FIELDS = {
    "bot_id",
    "version",
    "entrypoint",
    "priority_local",
    "priority_smart_office",
    "predecessors",
    "timeout_seconds",
    "runner_capability",
    "artifacts",
    "environment",
    "requirements",
}


def validate_package(path: Path, expected: dict[str, object]) -> None:
    with ZipFile(path) as archive:
        names = archive.namelist()
        roots = {name for name in names if "/" not in name}
        missing = REQUIRED_ROOT_FILES - roots
        if missing:
            raise ValueError(f"{path.name}: arquivos raiz ausentes: {sorted(missing)}")
        for name in names:
            item = PurePosixPath(name)
            if item.name in FORBIDDEN_NAMES or FORBIDDEN_PARTS.intersection(item.parts):
                raise ValueError(f"{path.name}: arquivo proibido: {name}")
        embedded = json.loads(archive.read("package-manifest.json"))
        if embedded != expected:
            raise ValueError(f"{path.name}: manifesto interno divergente")
        if REQUIRED_FIELDS - embedded.keys():
            raise ValueError(f"{path.name}: contrato incompleto")


def validate_packages(base_dir: Path, package_dir: Path) -> list[Path]:
    manifest = load_manifest(base_dir)
    specs = manifest["packages"]
    if len(specs) != 6:
        raise ValueError("o Capstone deve possuir exatamente seis pacotes")
    validated: list[Path] = []
    for raw_spec in specs:
        spec = dict(raw_spec)
        path = package_dir / f"{spec['bot_id']}-v{spec['version']}.zip"
        if not path.is_file():
            raise FileNotFoundError(path)
        validate_package(path, spec)
        validated.append(path)
    unexpected = set(package_dir.glob("*.zip")) - set(validated)
    if unexpected:
        raise ValueError(f"pacotes inesperados: {sorted(path.name for path in unexpected)}")
    return validated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-dir", type=Path, default=Path("dist/capstone"))
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    package_dir = args.package_dir
    if not package_dir.is_absolute():
        package_dir = base_dir / package_dir
    validated = validate_packages(base_dir, package_dir)
    print(f"{len(validated)} pacotes válidos em {display_path(package_dir, base_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
