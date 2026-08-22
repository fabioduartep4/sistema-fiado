"""Testes de app.utils.whatsapp — não tocam banco nem Qt."""

from __future__ import annotations

from app.utils.whatsapp import (
    montar_link_whatsapp,
    montar_mensagem_lembrete_saldo,
    normalizar_numero_whatsapp,
)


def test_normalizar_numero_whatsapp_adiciona_ddi_quando_ausente() -> None:
    assert normalizar_numero_whatsapp("35999998888") == "5535999998888"


def test_normalizar_numero_whatsapp_nao_duplica_ddi_ja_presente() -> None:
    assert normalizar_numero_whatsapp("5535999998888") == "5535999998888"


def test_normalizar_numero_whatsapp_numero_curto_nao_e_confundido_com_ddi() -> None:
    # Um número de 10-11 dígitos começando com "55" (DDD 55 = RS) não deve
    # ser confundido com um número que já tem o DDI.
    assert normalizar_numero_whatsapp("55912345678") == "5555912345678"


def test_montar_link_whatsapp_inclui_numero_e_mensagem_codificada() -> None:
    link = montar_link_whatsapp("35999998888", "Olá, tudo bem?")

    assert link.startswith("https://wa.me/5535999998888?text=")
    assert "Ol%C3%A1" in link or "tudo" in link


def test_montar_mensagem_lembrete_saldo_inclui_dados_do_cliente() -> None:
    mensagem = montar_mensagem_lembrete_saldo("Maria da Silva", "R$ 123,45", 40)

    assert "Maria da Silva" in mensagem
    assert "R$ 123,45" in mensagem
    assert "40 dias" in mensagem
