from pathlib import Path
from zipfile import ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_instala_playwright_e_chromium_headless():
    content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "HOME=/tmp" in content
    assert "ENVIRONMENT=container" in content
    assert "TZ=America/Manaus" in content
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in content
    assert "python -m playwright install-deps chromium" in content
    assert "python -m playwright install chromium" in content
    assert "apt-get install --yes --no-install-recommends chromium" not in content
    assert "PLAYWRIGHT_CHROMIUM_PATH" not in content
    assert "chromedriver" not in content.lower()
    assert "web/index-lotes/" in content
    assert "artefatos" in content


def test_dockerignore_mantem_pagina_web_no_contexto():
    content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "docs/*" in content
    assert "web/*" in content
    assert "!web/index-lotes" in content
    assert "!web/index-lotes/**" in content


def test_compose_mapeia_volumes_operacionais():
    content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./logs:/app/logs" in content
    assert "./relatorios:/app/relatorios" in content
    assert "./artefatos:/app/artefatos" in content
    assert "WEB_AUTOMATION_ENABLED" in content
    assert "WEB_TIMEOUT_SECONDS" in content
    assert "ENVIRONMENT: container" in content
    assert "TZ: America/Manaus" in content
    assert "PLAYWRIGHT_BROWSERS_PATH: /ms-playwright" in content
    assert "PLAYWRIGHT_CHROMIUM_PATH" not in content
    assert "HOME: /tmp" in content


def test_ci_executa_smoke_test_playwright_na_imagem():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "Executar smoke test Playwright" in content
    assert "WEB_AUTOMATION_ENABLED=true" in content
    assert "REFERENCE_LOTES=L001,L002" in content
    assert "conferencia-de-lotes:ci" in content


def test_pacote_botcity_inclui_pagina_web_local():
    from scripts.build_botcity_package import iter_package_files

    package_files = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in iter_package_files(PROJECT_ROOT)
    }

    assert "web/index-lotes/index.html" in package_files
    assert "web/index-lotes/login.html" in package_files
    assert "web/index-lotes/login.js" in package_files


def test_requirements_do_pacote_usa_playwright_sem_selenium():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "playwright" in requirements
    assert "selenium" not in requirements
    assert "webdriver-manager" not in requirements
    assert "reportlab" in requirements


def test_pacote_botcity_exclui_arquivos_locais_e_caches():
    from scripts.build_botcity_package import iter_package_files

    package_files = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in iter_package_files(PROJECT_ROOT)
    }

    forbidden_prefixes = (
        ".env",
        ".venv/",
        ".pytest_cache/",
        "logs/",
        "relatorios/",
        "artefatos/",
        "dist/",
    )
    assert not any(
        file_path == prefix.rstrip("/") or file_path.startswith(prefix)
        for file_path in package_files
        for prefix in forbidden_prefixes
    )


def test_build_botcity_package_usa_versao_no_nome_do_artefato(tmp_path):
    from scripts.build_botcity_package import build_package

    for directory in ("src", "dados_entrada", "web/index-lotes"):
        (tmp_path / directory).mkdir(parents=True)
        (tmp_path / directory / ".gitkeep").write_text("", encoding="utf-8")
    (tmp_path / "bot.py").write_text("print('bot')\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("playwright\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=nao-incluir\n", encoding="utf-8")

    artifact = build_package(
        tmp_path,
        version="2",
        package_name="bot-conferencia-de-lotes",
    )

    assert artifact.name == "bot-conferencia-de-lotes-v2.zip"
    with ZipFile(artifact) as package:
        names = set(package.namelist())
    assert "bot.py" in names
    assert ".env" not in names
