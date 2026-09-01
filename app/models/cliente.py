"""Modelo ORM: Cliente.

O cliente é o "dono" da conta de fiado. Possui um único nome principal
(obrigatório) e, opcionalmente, vários nomes alternativos, telefones e
compradores associados.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Identity, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.comprador import Comprador
    from app.models.compra import Compra
    from app.models.nome_alternativo import NomeAlternativo
    from app.models.pagamento import Pagamento
    from app.models.telefone import Telefone


class Cliente(Base, ColunasComunsMixin):
    """Representa um cliente (conta de fiado).

    Attributes:
        id_visivel: Identificador sequencial exibido ao usuário (não é a
            chave primária real, que é UUID).
        nome_principal: Nome principal do cliente. Único por conta, obrigatório.
        nome_principal_normalizado: Versão sem acento/maiúscula/espaços extras
            de ``nome_principal``, usada e indexada para busca.
        nomes_alternativos: Apelidos/variações do nome (0 ou mais).
        telefones: Telefones de contato (0 ou mais).
        compradores: Pessoas que compram nesta conta (0 ou mais), ex.: filhos.
        compras: Compras (lançamentos de fiado) feitas nesta conta.
        pagamentos: Pagamentos recebidos nesta conta.
        confirmado: False quando o cliente foi criado automaticamente a
            partir da importação de um XML de NF-e (sem confirmação
            humana do nome); True para clientes cadastrados manualmente
            ou já confirmados. Usado para destacar visualmente (cor
            vermelha) os cadastros pendentes de revisão.
        limite_fiado: Limite de compra no fiado, opcional (None = sem
            limite definido para este cliente). Clientes com saldo em
            aberto acima do limite aparecem na tela de Início, já com o
            botão de enviar lembrete — ver
            ``app.services.relatorio_service.listar_clientes_acima_do_limite``.
    """

    __tablename__ = "clientes"

    id_visivel: Mapped[int] = mapped_column(
        Integer, Identity(start=1, increment=1), unique=True, nullable=False
    )
    nome_principal: Mapped[str] = mapped_column(String(150), nullable=False)
    nome_principal_normalizado: Mapped[str] = mapped_column(String(150), nullable=False)
    confirmado: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    limite_fiado: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    nomes_alternativos: Mapped[list["NomeAlternativo"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    telefones: Mapped[list["Telefone"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    compradores: Mapped[list["Comprador"]] = relationship(
        back_populates="cliente", cascade="all, delete-orphan"
    )
    compras: Mapped[list["Compra"]] = relationship(back_populates="cliente")
    pagamentos: Mapped[list["Pagamento"]] = relationship(back_populates="cliente")

    __table_args__ = (
        Index("ix_clientes_nome_principal_normalizado", "nome_principal_normalizado"),
    )

    def __repr__(self) -> str:  # pragma: no cover - apenas apoio a debug
        return f"<Cliente id_visivel={self.id_visivel} nome_principal={self.nome_principal!r}>"
