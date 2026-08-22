"""Repositório de acesso a dados da entidade Compra.

Contém tanto consultas de leitura (usadas na Ficha do Cliente) quanto a
criação de novas compras (etapa "Adicionar Compra").
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.comprador import Comprador
from app.models.compra import Compra, StatusCompra


def listar_por_cliente(session: Session, cliente_id: uuid.UUID) -> list[Compra]:
    """Lista as compras ativas de um cliente, da mais antiga para a mais nova.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        Lista de :class:`Compra` ativas, ordenadas por data.
    """
    stmt = (
        select(Compra)
        .where(Compra.cliente_id == cliente_id, Compra.ativo.is_(True))
        .order_by(Compra.data, Compra.criado_em)
    )
    return list(session.execute(stmt).scalars().all())


def calcular_total_em_aberto(session: Session, cliente_id: uuid.UUID) -> Decimal:
    """Calcula a soma das compras em aberto (não quitadas) de um cliente.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        Soma dos valores das compras com status diferente de "quitada".
        Retorna ``Decimal("0")`` se não houver nenhuma compra em aberto.
    """
    stmt = select(func.coalesce(func.sum(Compra.valor), 0)).where(
        Compra.cliente_id == cliente_id,
        Compra.ativo.is_(True),
        Compra.status != StatusCompra.QUITADA,
    )
    total = session.execute(stmt).scalar_one()
    return Decimal(total)


def listar_compradores_do_cliente(session: Session, cliente_id: uuid.UUID) -> list[Comprador]:
    """Lista os compradores ativos de um cliente, em ordem alfabética.

    Usado para popular a seleção opcional de comprador em Adicionar Compra.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        Lista de :class:`Comprador` ativos.
    """
    stmt = (
        select(Comprador)
        .where(Comprador.cliente_id == cliente_id, Comprador.ativo.is_(True))
        .order_by(Comprador.nome)
    )
    return list(session.execute(stmt).scalars().all())


def criar_compra(
    session: Session,
    cliente_id: uuid.UUID,
    valor: Decimal,
    data: date,
    comprador_id: Optional[uuid.UUID] = None,
) -> Compra:
    """Cria uma nova compra (lançamento de fiado) para um cliente.

    A compra é criada com ``status=ABERTA`` (padrão do modelo) e
    ``eh_resto=False`` — a criação de compras do tipo "Resto" é feita
    apenas pela lógica de quitação (``app.services.pagamento_service``,
    etapa "Receber Conta"), não por este fluxo de cadastro manual.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente dono da conta.
        valor: Valor da compra (deve ser positivo — validado na camada de
            serviço).
        data: Data da compra.
        comprador_id: UUID do comprador que realizou a compra (opcional).

    Returns:
        A :class:`Compra` recém-criada (já com ``id`` preenchido).
    """
    compra = Compra(cliente_id=cliente_id, comprador_id=comprador_id, valor=valor, data=data)
    session.add(compra)
    session.flush()
    return compra


def listar_em_aberto_por_cliente(session: Session, cliente_id: uuid.UUID) -> list[Compra]:
    """Lista as compras em aberto de um cliente, da mais antiga para a mais nova.

    Usado pela lógica FIFO de quitação (``app.services.pagamento_service``):
    a primeira compra da lista é sempre a próxima a ser quitada. Compras
    com status "quitada" não entram na lista.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        Lista de :class:`Compra` em aberto, ordenadas por data (FIFO).
    """
    stmt = (
        select(Compra)
        .where(
            Compra.cliente_id == cliente_id,
            Compra.ativo.is_(True),
            Compra.status != StatusCompra.QUITADA,
        )
        .order_by(Compra.data, Compra.criado_em)
    )
    return list(session.execute(stmt).scalars().all())


def marcar_status(session: Session, compra: Compra, status: StatusCompra) -> None:
    """Atualiza o status de quitação de uma compra.

    Args:
        session: Sessão SQLAlchemy ativa.
        compra: Instância da compra (já carregada).
        status: Novo status.
    """
    compra.status = status
    session.flush()


def criar_compra_resto(
    session: Session, compra_origem: Compra, valor: Decimal, data: date
) -> Compra:
    """Cria a compra "Resto" com o valor que sobrou de um pagamento parcial.

    Herda o cliente e o comprador da compra de origem, e guarda a
    referência a ela (``compra_origem_id``) para fins de auditoria. Só
    deve ser chamada depois que a compra de origem já foi marcada como
    quitada (ver ``app.services.pagamento_service``).

    Args:
        session: Sessão SQLAlchemy ativa.
        compra_origem: Compra que originou o valor restante.
        valor: Valor restante (menor que o valor original da compra de origem).
        data: Data a ser usada na nova compra (normalmente a data do
            pagamento que gerou o resto).

    Returns:
        A nova :class:`Compra`, com ``eh_resto=True``.
    """
    resto = Compra(
        cliente_id=compra_origem.cliente_id,
        comprador_id=compra_origem.comprador_id,
        valor=valor,
        data=data,
        eh_resto=True,
        compra_origem_id=compra_origem.id,
    )
    session.add(resto)
    session.flush()
    return resto


def buscar_resto_de(session: Session, compra_origem_id: uuid.UUID) -> Optional[Compra]:
    """Busca a compra "Resto" gerada a partir de uma compra de origem.

    Usado pelo estorno de pagamento: antes de reabrir a compra original, é
    preciso checar se o "Resto" que ela gerou já foi tocado por outro
    pagamento (o que bloquearia o estorno).

    Args:
        session: Sessão SQLAlchemy ativa.
        compra_origem_id: UUID da compra que pode ter gerado um "Resto".

    Returns:
        A compra "Resto" correspondente, ou None se nenhuma foi gerada.
    """
    stmt = select(Compra).where(Compra.compra_origem_id == compra_origem_id)
    return session.execute(stmt).scalar_one_or_none()


def definir_ativo(session: Session, compra: Compra, ativo: bool) -> None:
    """Ativa ou inativa uma compra (usado para desfazer uma compra "Resto" no estorno).

    Args:
        session: Sessão SQLAlchemy ativa.
        compra: Instância da compra (já carregada).
        ativo: False para inativar, True para reativar.
    """
    compra.ativo = ativo
    session.flush()


def buscar_por_origem_nfe(session: Session, chave: str) -> Optional[Compra]:
    """Busca uma compra já vinculada a uma determinada chave de NF-e.

    Usado para detectar se um XML já foi importado antes (evita duplicidade).

    Args:
        session: Sessão SQLAlchemy ativa.
        chave: Chave de acesso da NF-e (44 dígitos).

    Returns:
        A :class:`Compra` vinculada a essa chave, ou None se nunca foi importada.
    """
    stmt = select(Compra).where(Compra.origem_nfe_xml == chave)
    return session.execute(stmt).scalar_one_or_none()


def reatribuir_cliente(session: Session, cliente_origem_id: uuid.UUID, cliente_destino_id: uuid.UUID) -> None:
    """Move todas as compras de um cliente para outro (usado ao mesclar duplicados).

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_origem_id: UUID do cliente que está sendo mesclado (perderá as compras).
        cliente_destino_id: UUID do cliente que passa a ser o dono das compras.
    """
    stmt = select(Compra).where(Compra.cliente_id == cliente_origem_id)
    for compra in session.execute(stmt).scalars().all():
        compra.cliente_id = cliente_destino_id
    session.flush()
