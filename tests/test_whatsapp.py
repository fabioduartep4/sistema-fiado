"""Testes de app.utils.whatsapp — não tocam banco nem Qt."""

from __future__ import annotations

from app.utils.whatsapp import (
    montar_link_whatsapp,
    montar_mensagem_lembrete_limite,
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


def test_lembrete_em_atraso_fala_do_atraso_e_do_total() -> None:
    mensagem = montar_mensagem_lembrete_saldo("Maria da Silva", "10/10/2026", "R$ 3.000,00", atrasado=True)

    assert "Maria da Silva" in mensagem
    assert "em atraso" in mensagem
    assert "10/10/2026" in mensagem
    assert "R$ 3.000,00" in mensagem


def test_lembrete_em_atraso_sem_pagamento_anterior() -> None:
    mensagem = montar_mensagem_lembrete_saldo("Maria da Silva", None, "R$ 3.000,00", atrasado=True)

    assert "nenhum pagamento" in mensagem
    assert "R$ 3.000,00" in mensagem


def test_lembrete_sem_atraso_so_informa_o_valor_da_conta() -> None:
    mensagem = montar_mensagem_lembrete_saldo("Maria da Silva", "10/10/2026", "R$ 150,00", atrasado=False)

    assert "Maria da Silva" in mensagem
    assert "R$ 150,00" in mensagem
    assert "atraso" not in mensagem
    assert "10/10/2026" not in mensagem


def test_montar_mensagem_lembrete_limite_inclui_dados_do_cliente() -> None:
    mensagem = montar_mensagem_lembrete_limite("Maria da Silva", "R$ 250,00", "R$ 200,00")

    assert "Maria da Silva" in mensagem
    assert "R$ 250,00" in mensagem
    assert "R$ 200,00" in mensagem


def test_formatar_reais_usa_virgula_e_ponto_de_milhar() -> None:
    from decimal import Decimal

    from app.utils.formatacao import formatar_reais

    assert formatar_reais(Decimal("150")) == "R$ 150,00"
    assert formatar_reais(Decimal("1234.5")) == "R$ 1.234,50"
