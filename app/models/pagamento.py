"""Modelo ORM: Pagamento.

Representa o recebimento de um valor de um cliente, que é aplicado às
compras em aberto seguindo a regra FIFO (ver app.services.pagamento_service).
"""

from __future__ import annotations

import uuid
from datetime import date as date_
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.pagamento_compra import PagamentoCompra
    from app.models.usuario import Usuario


class Pagamento(Base, ColunasComunsMixin):
    """Representa um pagamento recebido de um cliente.

    Attributes:
        cliente_id: Cliente que efetuou o pagamento.
        valor_pago: Valor total pago nesta transação.
        data_pagamento: Data em que o pagamento foi recebido (por padrão, o
            dia anterior à data do sistema, ajustável).
        recebido_por_usuario_id: Usuário do sistema que registrou o
            recebimento (vinculado automaticamente ao usuário logado).
        observacoes: Observações livres sobre o pagamento.
        aplicacoes: Detalhamento de quanto deste pagamento foi aplicado em
            cada compra (necessário para a lógica FIFO e para auditoria).
    """

    __tablename__ = "pagamentos"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )
    valor_pago: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data_pagamento: Mapped[date_] = mapped_column(Date, nullable=False)
    recebido_por_usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    observacoes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="pagamentos")
    recebido_por: Mapped["Usuario"] = relationship()
    aplicacoes: Mapped[list["PagamentoCompra"]] = relationship(
        back_populates="pagamento", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Pagamento valor_pago={self.valor_pago} data={self.data_pagamento}>"
