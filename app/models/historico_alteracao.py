"""Modelo ORM: HistoricoAlteracao.

Registro genérico de auditoria: toda alteração relevante (edição de
cliente, exclusão lógica, pagamento, compra, estorno, etc.) gera uma
entrada aqui, permitindo reconstruir o histórico completo de qualquer
registro do sistema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin


class HistoricoAlteracao(Base, ColunasComunsMixin):
    """Representa uma entrada de auditoria sobre uma alteração no sistema.

    Attributes:
        entidade: Nome da entidade alterada (ex.: "Cliente", "Compra").
        entidade_id: UUID do registro alterado.
        usuario_id: Usuário que realizou a alteração.
        acao: Ação realizada (ex.: "criacao", "edicao", "exclusao_logica",
            "pagamento", "estorno").
        campo: Nome do campo alterado (quando aplicável).
        valor_antigo: Valor anterior do campo (texto, para simplicidade).
        valor_novo: Novo valor do campo (texto, para simplicidade).
        data_hora: Momento em que a alteração ocorreu.
    """

    __tablename__ = "historico_alteracoes"

    entidade: Mapped[str] = mapped_column(String(50), nullable=False)
    entidade_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuarios.id"), nullable=False, index=True
    )
    acao: Mapped[str] = mapped_column(String(50), nullable=False)
    campo: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    valor_antigo: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    valor_novo: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    usuario: Mapped["Usuario"] = relationship()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HistoricoAlteracao entidade={self.entidade} acao={self.acao}>"


from app.models.usuario import Usuario  # noqa: E402  (import tardio evita ciclo)
