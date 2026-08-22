"""Modelo ORM: Telefone.

Telefones de contato de um cliente. Um cliente pode ter zero ou vários.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.cliente import Cliente


class Telefone(Base, ColunasComunsMixin):
    """Representa um telefone de contato de um cliente.

    Attributes:
        cliente_id: Cliente ao qual este telefone pertence.
        numero: Telefone como digitado (com formatação, para exibição).
        numero_normalizado: Apenas os dígitos, usado na busca.
    """

    __tablename__ = "telefones"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )
    numero: Mapped[str] = mapped_column(String(30), nullable=False)
    numero_normalizado: Mapped[str] = mapped_column(String(20), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="telefones")

    __table_args__ = (Index("ix_telefones_normalizado", "numero_normalizado"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Telefone numero={self.numero!r}>"
