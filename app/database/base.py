"""Base declarativa do SQLAlchemy e mixin de colunas comuns a todas as tabelas.

Todas as tabelas do sistema devem herdar de ``Base`` e, na grande maioria dos
casos, também de ``ColunasComunsMixin``, que já traz:

- ``id``: chave primária UUID (nunca reaproveitada, nunca exposta como
  "número sequencial" ao usuário).
- ``ativo``: flag de exclusão lógica (nunca apagamos registros do banco).
- ``criado_em`` / ``atualizado_em``: timestamps automáticos de auditoria.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Classe base declarativa usada por todos os modelos ORM do sistema."""


class ColunasComunsMixin:
    """Mixin com colunas padrão presentes na maioria das tabelas do sistema."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
