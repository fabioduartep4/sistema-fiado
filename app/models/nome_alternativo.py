"""Modelo ORM: NomeAlternativo.

Apelidos ou variações do nome principal de um cliente (ex.: "Mariazinha"
para "Maria Fernanda"). Um cliente pode ter zero ou vários.
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


class NomeAlternativo(Base, ColunasComunsMixin):
    """Representa um nome alternativo (apelido) de um cliente.

    Attributes:
        cliente_id: Cliente ao qual este apelido pertence.
        nome: O apelido/variação em si.
        nome_normalizado: Versão normalizada de ``nome``, usada na busca.
    """

    __tablename__ = "nomes_alternativos"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )
    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(String(150), nullable=False)

    cliente: Mapped["Cliente"] = relationship(back_populates="nomes_alternativos")

    __table_args__ = (Index("ix_nomes_alternativos_normalizado", "nome_normalizado"),)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<NomeAlternativo nome={self.nome!r}>"
