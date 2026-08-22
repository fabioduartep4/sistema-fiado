"""Testes de app.config.tema — não tocam banco nem Qt (só retorna texto)."""

from __future__ import annotations

from app.config.tema import obter_stylesheet
from app.services.configuracao_service import ModoTema


def test_tema_claro_nao_tem_stylesheet() -> None:
    assert obter_stylesheet(ModoTema.CLARO) == ""


def test_tema_escuro_tem_stylesheet_nao_vazio() -> None:
    css = obter_stylesheet(ModoTema.ESCURO)
    assert css != ""
    assert "QWidget" in css
    assert "background-color" in css
