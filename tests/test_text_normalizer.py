"""Testes de app.utils.text_normalizer — não tocam em banco nem em Qt."""

from __future__ import annotations

from app.utils.text_normalizer import normalizar_telefone, normalizar_texto


def test_normalizar_texto_remove_acentos() -> None:
    assert normalizar_texto("Mariázinha") == "mariazinha"
    assert normalizar_texto("MARIA DO CLÁUDIO") == "maria do claudio"


def test_normalizar_texto_colapsa_espacos_extras() -> None:
    assert normalizar_texto("  Maria   Fernanda  ") == "maria fernanda"


def test_normalizar_texto_converte_para_minusculas() -> None:
    assert normalizar_texto("ROSE E CHICO") == "rose e chico"


def test_normalizar_texto_com_string_vazia() -> None:
    assert normalizar_texto("") == ""


def test_normalizar_telefone_mantem_so_digitos() -> None:
    assert normalizar_telefone("(35) 99999-8888") == "35999998888"


def test_normalizar_telefone_com_string_vazia() -> None:
    assert normalizar_telefone("") == ""


def test_normalizar_telefone_ja_so_com_digitos() -> None:
    assert normalizar_telefone("35999998888") == "35999998888"
