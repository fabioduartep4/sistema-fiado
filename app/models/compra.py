"""Modelo ORM: Compra.

Representa um lançamento de fiado (uma "compra" na conta de um cliente).
Compras são quitadas total ou parcialmente por pagamentos, seguindo a
regra FIFO (a compra mais antiga em aberto é quitada primeiro).

Quando um pagamento termina no meio de uma compra, a compra original é
marcada como quitada e uma nova compra é criada com o valor restante,
sinalizada por ``eh_resto=True`` (ver app.services.pagamento_service).
"""

from __future__ import annotations

import enum
import uuid
from datetime import date as date_
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, ColunasComunsMixin

if TYPE_CHECKING:
    from app.models.cliente import Cliente
    from app.models.comprador import Comprador
    from app.models.pagamento_compra import PagamentoCompra


class StatusCompra(str, enum.Enum):
    """Situação de quitação de uma compra.

    Uma compra em aberto é sempre integralmente devida — nunca existe um
    estado "parcialmente paga" persistente (ver app.services.pagamento_service).
    """

    ABERTA = "aberta"
    QUITADA = "quitada"


class Compra(Base, ColunasComunsMixin):
    """Representa uma compra (lançamento de fiado) na conta de um cliente.

    Attributes:
        cliente_id: Cliente dono da conta em que a compra foi lançada.
        comprador_id: Comprador que realizou a compra (opcional).
        valor: Valor da compra, em reais.
        data: Data da compra (por padrão, o dia anterior à data do sistema,
            ajustável conforme o modo configurado — ver app.utils.date_utils).
        status: Situação atual de quitação da compra.
        eh_resto: True quando esta compra foi gerada automaticamente como o
            valor restante de um pagamento parcial de outra compra.
        compra_origem_id: Referência à compra original que deu origem a este
            "Resto", para fins de auditoria/rastreabilidade (opcional).
        descricao: Campo livre opcional (ex.: observações do lançamento).
        origem_nfe_xml: Reservado para futura integração com XML de NF-e/NFC-e.
            Não utilizado nesta etapa do projeto.
    """

    __tablename__ = "compras"

    cliente_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clientes.id"), nullable=False, index=True
    )
    comprador_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compradores.id"), nullable=True, index=True
    )
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data: Mapped[date_] = mapped_column(Date, nullable=False)
    status: Mapped[StatusCompra] = mapped_column(
        Enum(StatusCompra, name="status_compra"), default=StatusCompra.ABERTA, nullable=False
    )
    eh_resto: Mapped[bool] = mapped_column(default=False, nullable=False)
    compra_origem_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("compras.id"), nullable=True, index=True
    )
    descricao: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Reservado para futura integração com NF-e/NFC-e (não usado ainda).
    origem_nfe_xml: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    cliente: Mapped["Cliente"] = relationship(back_populates="compras")
    comprador: Mapped[Optional["Comprador"]] = relationship()
    aplicacoes_pagamento: Mapped[list["PagamentoCompra"]] = relationship(
        back_populates="compra"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Compra valor={self.valor} status={self.status} eh_resto={self.eh_resto}>"
