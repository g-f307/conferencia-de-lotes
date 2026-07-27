from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_instala_chromium_e_copia_pagina_web():
    content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in content
    assert "playwright install --with-deps chromium" in content
    assert "docs/index-lotes/" in content
    assert "artefatos" in content


def test_dockerignore_mantem_pagina_web_no_contexto():
    content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "docs/*" in content
    assert "!docs/index-lotes" in content
    assert "!docs/index-lotes/**" in content


def test_compose_mapeia_volumes_operacionais():
    content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./logs:/app/logs" in content
    assert "./relatorios:/app/relatorios" in content
    assert "./artefatos:/app/artefatos" in content
    assert "WEB_AUTOMATION_ENABLED" in content


def test_pacote_botcity_inclui_pagina_web_local():
    from scripts.build_botcity_package import iter_package_files

    package_files = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in iter_package_files(PROJECT_ROOT)
    }

    assert "docs/index-lotes/index.html" in package_files
