"""Gera seis pacotes independentes e determinísticos para o Capstone."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

MANIFEST_PATH = Path("deployment/capstone_bots.json")
FIXED_TIMESTAMP = (2024, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", "tests"}
EXCLUDED_NAMES = {".env", "debug.log"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".log", ".sqlite3", ".png", ".pdf"}

BOT_TEMPLATE = '''"""Entry point gerado para {bot_id}."""
from importlib import import_module


def main() -> int:
    module = import_module("{module}")
    return int(getattr(module, "{function}")())


if __name__ == "__main__":
    raise SystemExit(main())
'''


def load_manifest(base_dir: Path) -> dict[str, object]:
    data = json.loads((base_dir / MANIFEST_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("packages"), list):
        raise TypeError("manifesto de pacotes deve ser um objeto com uma lista")
    return data


def iter_source_files(base_dir: Path) -> Iterable[Path]:
    for root in (base_dir / "src", base_dir / "web"):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(base_dir)
            if (
                path.is_file()
                and not EXCLUDED_PARTS.intersection(relative.parts)
                and path.name not in EXCLUDED_NAMES
                and path.suffix.lower() not in EXCLUDED_SUFFIXES
            ):
                yield path


def _write_bytes(archive: ZipFile, name: str, content: bytes) -> None:
    info = ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    archive.writestr(info, content)


def _package_name(spec: Mapping[str, object]) -> str:
    return f"{spec['bot_id']}-v{spec['version']}.zip"


def build_packages(base_dir: Path, output_dir: Path) -> list[Path]:
    manifest = load_manifest(base_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_files = sorted(iter_source_files(base_dir))
    artifacts: list[Path] = []
    for raw_spec in manifest["packages"]:
        if not isinstance(raw_spec, Mapping):
            raise TypeError("cada pacote deve ser um objeto")
        spec = dict(raw_spec)
        module, function = str(spec["entrypoint"]).split(":", 1)
        artifact = output_dir / _package_name(spec)
        with ZipFile(artifact, "w") as archive:
            _write_bytes(
                archive,
                "bot.py",
                BOT_TEMPLATE.format(
                    bot_id=spec["bot_id"], module=module, function=function
                ).encode("utf-8"),
            )
            requirements = "\n".join(str(item) for item in spec["requirements"]) + "\n"
            _write_bytes(archive, "requirements.txt", requirements.encode("utf-8"))
            _write_bytes(
                archive,
                "package-manifest.json",
                json.dumps(spec, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            for path in source_files:
                _write_bytes(
                    archive,
                    path.relative_to(base_dir).as_posix(),
                    path.read_bytes(),
                )
        artifacts.append(artifact)
    return artifacts


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist/capstone"))
    args = parser.parse_args()
    base_dir = Path(__file__).resolve().parents[1]
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = base_dir / output_dir
    for artifact in build_packages(base_dir, output_dir):
        print(f"{artifact.relative_to(base_dir)} sha256={sha256(artifact)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
