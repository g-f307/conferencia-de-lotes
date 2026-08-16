"""Cenarios E2E do formulario de lotes executados em Chromium real."""

from pathlib import Path
from typing import Any

import pytest

from src.pages import FormPage


pytestmark = pytest.mark.browser


def dados_lote(**overrides: str) -> dict[str, str]:
    item = {
        "lote_id": "E2E-001",
        "produto": "Monitor",
        "resultado_validacao": "APROVADO",
        "mensagem_resultado": "Fluxo E2E validado",
    }
    item.update(overrides)
    return item


def test_titulo_da_pagina_esta_correto(pagina_html: Any) -> None:
    assert pagina_html.title() == "Cadastro de Lotes de Produção"
    assert pagina_html.get_by_role(
        "heading",
        name="Cadastro de Lotes de Produção",
        exact=True,
    ).is_visible()


def test_campo_numero_do_lote_aceita_preenchimento(pagina_html: Any) -> None:
    numero_lote = pagina_html.get_by_label("Número do lote", exact=True)

    numero_lote.fill("E2E-LOTE-002")

    assert numero_lote.input_value() == "E2E-LOTE-002"


def test_produto_pode_ser_selecionado(pagina_html: Any) -> None:
    produto = pagina_html.get_by_label("Produto", exact=True)

    produto.select_option(label="Notebook")

    assert produto.input_value() == "Notebook"


def test_status_aprovado_e_o_padrao_do_formulario(pagina_html: Any) -> None:
    aprovado = pagina_html.get_by_role("radio", name="Aprovado", exact=True)
    reprovado = pagina_html.get_by_role("radio", name="Reprovado", exact=True)

    assert aprovado.is_checked()
    assert not reprovado.is_checked()


def test_formulario_completo_apresenta_sucesso(
    formulario_page: FormPage,
) -> None:
    mensagem = formulario_page.preencher_lote(dados_lote())

    assert formulario_page.is_sucesso()
    assert "Aprovado — lote E2E-001" in mensagem
    assert "Fluxo E2E validado" in mensagem


def test_formulario_sem_produto_nao_apresenta_sucesso(
    pagina_html: Any,
) -> None:
    pagina_html.get_by_label("Número do lote", exact=True).fill("E2E-003")

    pagina_html.get_by_role(
        "button",
        name="Processar lote",
        exact=True,
    ).click()

    resultado = pagina_html.get_by_role(
        "status",
        name="Resultado do processamento",
    )
    assert resultado.is_visible()
    assert resultado.inner_text() == "Revise os campos obrigatórios."
    assert resultado.get_attribute("data-resultado") is None
    assert pagina_html.locator("#erro-produto").inner_text() == (
        "Selecione um produto."
    )


def test_formulario_sem_numero_do_lote_nao_apresenta_sucesso(
    pagina_html: Any,
) -> None:
    pagina_html.get_by_label("Produto", exact=True).select_option(label="Monitor")

    pagina_html.get_by_role(
        "button",
        name="Processar lote",
        exact=True,
    ).click()

    resultado = pagina_html.get_by_role(
        "status",
        name="Resultado do processamento",
    )
    assert resultado.is_visible()
    assert resultado.inner_text() == "Revise os campos obrigatórios."
    assert resultado.get_attribute("data-resultado") is None
    assert pagina_html.locator("#erro-numero-lote").inner_text() == (
        "Informe o número do lote."
    )


def test_screenshot_e2e_existe_e_nao_esta_vazio(
    formulario_page: FormPage,
    tmp_path: Path,
) -> None:
    formulario_page.preencher_lote(
        dados_lote(
            lote_id="E2E-004",
            produto="Scanner",
        )
    )
    evidence_path = tmp_path / "evidencias" / "sucesso-e2e-004.png"

    result = formulario_page.capturar_evidencia(evidence_path)

    assert result == evidence_path
    assert evidence_path.is_file()
    assert evidence_path.stat().st_size > 0
    assert evidence_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
