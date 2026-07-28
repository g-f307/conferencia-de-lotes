"""Build a BotCity custom Python deployment package.

The generated zip keeps bot.py and requirements.txt at the archive root, which
is the layout expected by BotCity Runner for custom Python automations.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


DEFAULT_VERSION = "2"
DEFAULT_PACKAGE_NAME = "bot-conferencia-de-lotes"
PACKAGE_ROOT_FILES = ("bot.py", "requirements.txt")
PACKAGE_DIRS = ("src", "dados_entrada", "web/index-lotes")
IGNORED_DIRS = {"__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def iter_package_files(base_dir: Path) -> list[Path]:
    files: list[Path] = []

    for filename in PACKAGE_ROOT_FILES:
        path = base_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Arquivo obrigatorio ausente: {path}")
        files.append(path)

    for dirname in PACKAGE_DIRS:
        directory = base_dir / dirname
        if not directory.is_dir():
            raise FileNotFoundError(f"Diretorio obrigatorio ausente: {directory}")
        files.extend(
            path
            for path in directory.rglob("*")
            if path.is_file()
            and not any(part in IGNORED_DIRS for part in path.parts)
            and path.suffix not in IGNORED_SUFFIXES
        )

    return sorted(files)


def build_package(
    base_dir: Path,
    version: str = DEFAULT_VERSION,
    package_name: str = DEFAULT_PACKAGE_NAME,
) -> Path:
    normalized_version = version.strip()
    if not normalized_version:
        raise ValueError("version deve ser informada")

    dist_dir = base_dir / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    artifact = dist_dir / f"{package_name}-v{normalized_version}.zip"

    with ZipFile(artifact, "w", compression=ZIP_DEFLATED) as package:
        for path in iter_package_files(base_dir):
            package.write(path, path.relative_to(base_dir).as_posix())

    return artifact


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Gera o pacote .zip para deploy no BotCity Maestro."
    )
    parser.add_argument("--version", default=DEFAULT_VERSION)
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    args = parser.parse_args()

    base_dir = Path(__file__).resolve().parents[1]
    artifact = build_package(base_dir, args.version, args.package_name)
    print(artifact.relative_to(base_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
