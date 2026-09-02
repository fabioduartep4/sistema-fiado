"""Testes de app.config.tema — não tocam banco nem Qt (só retorna texto)."""

from __future__ import annotations

from app.config.tema import obter_stylesheet
from app.services.configuracao_service import ModoTema


def test_tema_claro_tem_stylesheet_proprio() -> None:
    """Regressão: o tema claro passou a ter QSS próprio (antes era string
    vazia, usando a aparência crua do Windows sem estilo nenhum)."""
    css = obter_stylesheet(ModoTema.CLARO)
    assert css != ""
    assert "QWidget" in css
    assert "background-color" in css


def test_tema_escuro_tem_stylesheet_nao_vazio() -> None:
    css = obter_stylesheet(ModoTema.ESCURO)
    assert css != ""
    assert "QWidget" in css
    assert "background-color" in css


def test_temas_claro_e_escuro_tem_paletas_diferentes() -> None:
    assert obter_stylesheet(ModoTema.CLARO) != obter_stylesheet(ModoTema.ESCURO)


def test_temas_suportam_classes_de_titulo_e_botao_primario() -> None:
    for tema in (ModoTema.CLARO, ModoTema.ESCURO):
        css = obter_stylesheet(tema)
        assert 'papel="titulo"' in css
        assert 'importancia="primaria"' in css
