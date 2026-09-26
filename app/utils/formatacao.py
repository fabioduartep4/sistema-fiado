"""Formatação de valores para exibição ao cliente (extrato, lembretes)."""

from __future__ import annotations

from decimal import Decimal


def formatar_reais(valor: Decimal) -> str:
    """Formata no padrão brasileiro: R$ 1.234,56."""
    texto = f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {texto}"
