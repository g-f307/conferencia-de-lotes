from pathlib import Path
from zipfile import ZipFile

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def test_dockerfile_instala_playwright_e_chromium_headless():
    content = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "HOME=/tmp" in content
    assert "ENVIRONMENT=container" in content
    assert "TZ=America/Manaus" in content
    assert "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright" in content
    assert (
        "python -m playwright install --with-deps --only-shell chromium"
        in content
    )
    assert "python -m playwright install-deps chromium" not in content
    assert "apt-get install --yes --no-install-recommends chromium" not in content
    assert "PLAYWRIGHT_CHROMIUM_PATH" not in content
    assert "chromedriver" not in content.lower()
    assert "web/index-lotes/" in content
    assert "artefatos" in content
    assert "data/output/" in content


def test_dockerignore_mantem_pagina_web_no_contexto():
    content = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "docs/*" in content
    assert "web/*" in content
    assert "!web/index-lotes" in content
    assert "!web/index-lotes/**" in content
    assert "data/output/*" in content
    assert "!data/output/.gitkeep" in content


def test_compose_mapeia_volumes_operacionais():
    content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "./logs:/app/logs" in content
    assert "./relatorios:/app/relatorios" in content
    assert "./artefatos:/app/artefatos" in content
    assert "./data/output:/app/data/output" in content
    assert "DEAD_LETTER_PATH: data/output/dead_letter.jsonl" in content
    assert "WEB_AUTOMATION_ENABLED" in content
    assert "WEB_TIMEOUT_SECONDS" in content
    assert "ENVIRONMENT: container" in content
    assert "TZ: America/Manaus" in content
    assert "PLAYWRIGHT_BROWSERS_PATH: /ms-playwright" in content
    assert "PLAYWRIGHT_CHROMIUM_PATH" not in content
    assert "HOME: /tmp" in content


def test_compose_conecta_bot_a_api_ml_por_nome_do_servico():
    content = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ML_ENABLED" in content
    assert "ML_API_URL" in content
    assert "http://api-ml:8000" in content
    assert "ML_TIMEOUT_SECONDS" in content
    assert "depends_on" not in content


def test_ci_executa_smoke_test_playwright_na_imagem():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "Executar smoke test Playwright" in content
    assert "WEB_AUTOMATION_ENABLED=true" in content
    assert "REFERENCE_LOTES=L001,L002" in content
    assert "conferencia-de-lotes:ci" in content


def test_ci_constroi_e_valida_healthcheck_da_api_ml():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "docker compose build api-ml" in content
    assert "docker compose up --detach --wait --wait-timeout 60 api-ml" in content
    assert "http://127.0.0.1:8000/health" in content
    assert "{\"status\":\"healthy\",\"model_loaded\":true}" in content
    assert "docker compose down --remove-orphans" in content


def test_ci_encadeia_qualidade_testes_e_docker():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "  lint:\n    name: Qualidade do código" in content
    assert "  tests:\n    name: Testes por camada\n    needs: lint" in content
    assert "  coverage:\n    name: Cobertura mínima\n    needs: tests" in content
    assert "  test-e2e:\n    name: Testes E2E\n    needs: coverage" in content
    assert (
        "  build-docker:\n"
        "    name: Validar imagem Docker e artefatos\n"
        "    needs: test-e2e"
    ) in content


def test_ci_valida_importacao_e_lock_da_dead_letter_no_windows():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "  windows-compatibility:" in content
    assert "    name: Compatibilidade Windows" in content
    assert "    runs-on: windows-latest" in content
    assert 'python -c "from src.dead_letter import DeadLetterWriter"' in content
    assert "python -m pytest tests/integration/test_dead_letter.py -q" in content


def test_ci_executa_markers_e_publica_cobertura():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    for marker in ("unit", "integration", "regression", "e2e"):
        assert f"python -m pytest -m {marker}" in content

    assert "--cov=src" in content
    assert "--cov-report=term-missing" in content
    assert "--cov-report=xml" in content
    assert "--cov-report=html" in content
    assert "--cov-fail-under=80" in content
    assert '          -m "not browser"' in content
    assert "--timeout=60" in content
    assert "    timeout-minutes: 20" in content
    assert "name: coverage-report" in content
    assert "coverage.xml" in content
    assert "htmlcov/" in content


def test_ci_executa_e_publica_evidencias_e2e():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    assert "playwright install" in content
    assert "--with-deps" in content
    assert "--only-shell" in content
    assert "python -m pytest tests/e2e/ -q" in content
    assert "name: screenshots-e2e" in content
    assert "--basetemp=e2e-artifacts" in content
    assert "e2e-artifacts/**/*.png" in content


def test_ci_valida_e_publica_artefatos_docker():
    content = (
        PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    ).read_text(encoding="utf-8")

    expected_outputs = (
        "ci-output/logs/execucao.log",
        "ci-output/relatorios/resumo_execucao.json",
        "ci-output/relatorios/relatorio_evidencias.pdf",
    )
    assert all(f"test -s {path}" in content for path in expected_outputs)
    assert "ci-output/artefatos" in content
    assert "-size +0c" in content
    assert content.count("actions/upload-artifact@v4") == 4
    assert "name: relatorios-docker" in content
    assert "name: screenshots-docker" in content
    assert "MAESTRO_ENABLED=false" in content
    assert "VAULT_ENABLED=false" in content


def test_pacote_botcity_inclui_recursos_de_runtime():
    from scripts.build_botcity_package import iter_package_files

    package_files = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in iter_package_files(PROJECT_ROOT)
    }

    assert "web/index-lotes/index.html" in package_files
    assert "web/index-lotes/login.html" in package_files
    assert "web/index-lotes/login.js" in package_files
    assert "src/orchestrator.py" in package_files
    assert "src/wait_for_predecessor.py" in package_files
    assert "src/retry_policy.py" in package_files
    assert "src/reference_base.py" in package_files
    assert "src/dead_letter.py" in package_files
    assert "data/output/.gitkeep" in package_files
    assert not any(path.endswith(".jsonl") for path in package_files)


def test_requirements_do_pacote_usa_playwright_sem_selenium():
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "playwright" in requirements
    assert "selenium" not in requirements
    assert "webdriver-manager" not in requirements
    assert "reportlab" in requirements
    assert "portalocker" in requirements


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

    for directory in ("src", "dados_entrada", "web/index-lotes", "data/output"):
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
