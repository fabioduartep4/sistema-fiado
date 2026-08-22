"""Repositório de acesso a dados das entidades Pagamento e PagamentoCompra.

A lógica de quitação FIFO (qual compra é paga primeiro, geração da compra
"Resto") fica na camada de serviço (``app.services.pagamento_service``) —
este repositório só executa as gravações unitárias (criar o pagamento,
registrar cada aplicação em uma compra).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.pagamento import Pagamento
from app.models.pagamento_compra import PagamentoCompra


def criar_pagamento(
    session: Session,
    cliente_id: uuid.UUID,
    valor_pago: Decimal,
    data_pagamento: date,
    recebido_por_usuario_id: uuid.UUID,
    observacoes: Optional[str] = None,
) -> Pagamento:
    """Cria o registro de um pagamento recebido de um cliente.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente que pagou.
        valor_pago: Valor total pago.
        data_pagamento: Data do pagamento.
        recebido_por_usuario_id: UUID do usuário que registrou o recebimento.
        observacoes: Observações livres (opcional).

    Returns:
        O :class:`Pagamento` recém-criado (já com ``id`` preenchido).
    """
    pagamento = Pagamento(
        cliente_id=cliente_id,
        valor_pago=valor_pago,
        data_pagamento=data_pagamento,
        recebido_por_usuario_id=recebido_por_usuario_id,
        observacoes=observacoes,
    )
    session.add(pagamento)
    session.flush()
    return pagamento


def registrar_aplicacao(
    session: Session,
    pagamento_id: uuid.UUID,
    compra_id: uuid.UUID,
    valor_aplicado: Decimal,
) -> PagamentoCompra:
    """Registra quanto de um pagamento foi aplicado em uma compra específica.

    Args:
        session: Sessão SQLAlchemy ativa.
        pagamento_id: UUID do pagamento de origem.
        compra_id: UUID da compra que recebeu a aplicação.
        valor_aplicado: Valor aplicado nessa compra.

    Returns:
        A :class:`PagamentoCompra` recém-criada.
    """
    aplicacao = PagamentoCompra(
        pagamento_id=pagamento_id, compra_id=compra_id, valor_aplicado=valor_aplicado
    )
    session.add(aplicacao)
    session.flush()
    return aplicacao


def buscar_por_id(session: Session, pagamento_id: uuid.UUID) -> Optional[Pagamento]:
    """Busca um pagamento (ativo ou estornado) pelo ID.

    Args:
        session: Sessão SQLAlchemy ativa.
        pagamento_id: UUID do pagamento.

    Returns:
        O :class:`Pagamento` encontrado, ou None se não existir.
    """
    return session.get(Pagamento, pagamento_id)


def listar_por_cliente(session: Session, cliente_id: uuid.UUID) -> list[Pagamento]:
    """Lista os pagamentos de um cliente, do mais recente para o mais antigo.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        Lista de :class:`Pagamento` (inclui os já estornados, para que o
        histórico mostre também esse status), com o usuário que recebeu
        já carregado.
    """
    stmt = (
        select(Pagamento)
        .options(joinedload(Pagamento.recebido_por))
        .where(Pagamento.cliente_id == cliente_id)
        .order_by(Pagamento.data_pagamento.desc(), Pagamento.criado_em.desc())
    )
    return list(session.execute(stmt).scalars().all())


def listar_aplicacoes(session: Session, pagamento_id: uuid.UUID) -> list[PagamentoCompra]:
    """Lista as aplicações ativas de um pagamento (quanto foi usado em cada compra).

    Args:
        session: Sessão SQLAlchemy ativa.
        pagamento_id: UUID do pagamento.

    Returns:
        Lista de :class:`PagamentoCompra` ativas, com a compra relacionada
        já carregada.
    """
    stmt = (
        select(PagamentoCompra)
        .options(joinedload(PagamentoCompra.compra))
        .where(PagamentoCompra.pagamento_id == pagamento_id, PagamentoCompra.ativo.is_(True))
    )
    return list(session.execute(stmt).scalars().all())


def definir_ativo(session: Session, pagamento: Pagamento, ativo: bool) -> None:
    """Marca um pagamento como estornado (``ativo=False``) ou reativa.

    Args:
        session: Sessão SQLAlchemy ativa.
        pagamento: Instância do pagamento (já carregada).
        ativo: False para estornar, True para reativar.
    """
    pagamento.ativo = ativo
    session.flush()


def reatribuir_cliente(session: Session, cliente_origem_id: uuid.UUID, cliente_destino_id: uuid.UUID) -> None:
    """Move todos os pagamentos de um cliente para outro (usado ao mesclar duplicados).

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_origem_id: UUID do cliente que está sendo mesclado (perderá os pagamentos).
        cliente_destino_id: UUID do cliente que passa a ser o dono dos pagamentos.
    """
    stmt = select(Pagamento).where(Pagamento.cliente_id == cliente_origem_id)
    for pagamento in session.execute(stmt).scalars().all():
        pagamento.cliente_id = cliente_destino_id
    session.flush()
