"""Modelo ORM: PagamentoCompra.

Tabela associativa entre ``Pagamento`` e ``Compra``: registra exatamente
quanto de um pagamento foi aplicado em cada compra. É essencial para:

- Auditar a lógica FIFO (qual pagamento quitou qual compra).
- Permitir estornar um pagamento sabendo exatamente o que reverter.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.compra import Compra
    from app.models.pagamento import Pagamento


class PagamentoCompra(Base, ColunasComunsMixin):
    """Representa a aplicação de (parte de) um pagamento em uma compra.

    Attributes:
        pagamento_id: Pagamento de origem.
        compra_id: Compra que recebeu a aplicação.
        valor_aplicado: Quanto do pagamento foi usado para quitar esta compra.
    """

    __tablename__ = "pagamento_compra"

    pagamento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pagamentos.id"), nullable=False, index=True
    )
    compra_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compras.id"), nullable=False, index=True
    )
    valor_aplicado: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    pagamento: Mapped["Pagamento"] = relationship(back_populates="aplicacoes")
    compra: Mapped["Compra"] = relationship(back_populates="aplicacoes_pagamento")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PagamentoCompra valor_aplicado={self.valor_aplicado}>"
