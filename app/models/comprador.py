"""Modelo ORM: Comprador.

Pessoa que compra na conta de um cliente (ex.: filhos do titular da conta).
Pertence a um único cliente e não é compartilhado entre contas. Diferente
dos nomes alternativos, compradores não entram na busca de clientes — são
usados apenas ao registrar uma compra, para saber quem a realizou.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.cliente import Cliente


class Comprador(Base, ColunasComunsMixin):
    """Representa uma pessoa autorizada a comprar na conta de um cliente.

    Attributes:
        cliente_id: Cliente (conta) ao qual este comprador pertence.
        nome: Nome do comprador (texto livre).
    """

    __tablename__ = "compradores"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(150), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="compradores")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Comprador nome={self.nome!r}>"
