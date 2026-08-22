"""Repositório de relatórios agregados (somente leitura).

Contém o relatório de saldo em aberto por cliente (usado na aba
Histórico e Relatórios) e as consultas agregadas usadas no painel de
Início (maior valor gasto, mais contas lançadas, evolução mensal e total
em aberto geral) — ambas somente para Administrador.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.compra import Compra, StatusCompra


def listar_saldos_em_aberto(session: Session) -> list[tuple[Cliente, Decimal]]:
    """Lista os clientes ativos que possuem saldo em aberto, com o total devido.

    Clientes sem nenhuma compra em aberto não aparecem no resultado (uma
    junção interna com ``Compra`` é usada de propósito).

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Lista de tuplas (cliente, total_em_aberto), ordenada por nome
        principal.
    """
    stmt = (
        select(Cliente, func.coalesce(func.sum(Compra.valor), 0))
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Compra.ativo.is_(True),
            Compra.status != StatusCompra.QUITADA,
        )
        .group_by(Cliente.id)
        .order_by(Cliente.nome_principal)
    )
    return list(session.execute(stmt).all())


def listar_saldos_em_atraso(session: Session, data_limite: date) -> list[tuple[Cliente, Decimal, date]]:
    """Lista clientes com compras em aberto lançadas há mais de N dias.

    Usado como aproximação de "saldo em atraso" — o modelo de dados não tem
    uma data de vencimento própria (fiado não tem prazo fixo), então a data
    da compra é usada como referência: quanto mais antiga uma compra ainda
    em aberto, mais "atrasada" ela está.

    Args:
        session: Sessão SQLAlchemy ativa.
        data_limite: Só considera compras com ``data <= data_limite``
            (ex.: hoje menos 30 dias).

    Returns:
        Lista de tuplas (cliente, total_em_atraso, data_da_compra_mais_antiga),
        da maior para a menor soma. ``total_em_atraso`` soma só as compras
        que passam do limite — compras em aberto mais recentes do mesmo
        cliente não entram nesse total.
    """
    stmt = (
        select(Cliente, func.sum(Compra.valor), func.min(Compra.data))
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Compra.ativo.is_(True),
            Compra.status != StatusCompra.QUITADA,
            Compra.data <= data_limite,
        )
        .group_by(Cliente.id)
        .order_by(func.sum(Compra.valor).desc())
    )
    return list(session.execute(stmt).all())


def listar_maior_valor_gasto(
    session: Session, data_inicio: date, data_fim: date, limite: int = 10
) -> list[tuple[Cliente, Decimal]]:
    """Lista os clientes que mais gastaram (maior soma de compras) no período.

    Args:
        session: Sessão SQLAlchemy ativa.
        data_inicio: Início do período (inclusive).
        data_fim: Fim do período (inclusive).
        limite: Número máximo de clientes retornados.

    Returns:
        Lista de tuplas (cliente, valor_total), da maior para a menor soma.
    """
    stmt = (
        select(Cliente, func.coalesce(func.sum(Compra.valor), 0))
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Compra.ativo.is_(True),
            Compra.data >= data_inicio,
            Compra.data <= data_fim,
        )
        .group_by(Cliente.id)
        .order_by(func.sum(Compra.valor).desc())
        .limit(limite)
    )
    return list(session.execute(stmt).all())


def listar_mais_contas_lancadas(
    session: Session, data_inicio: date, data_fim: date, limite: int = 10
) -> list[tuple[Cliente, int]]:
    """Lista os clientes que mais lançaram contas (maior número de compras) no período.

    Args:
        session: Sessão SQLAlchemy ativa.
        data_inicio: Início do período (inclusive).
        data_fim: Fim do período (inclusive).
        limite: Número máximo de clientes retornados.

    Returns:
        Lista de tuplas (cliente, quantidade_de_compras), da maior para a menor.
    """
    stmt = (
        select(Cliente, func.count(Compra.id))
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Compra.ativo.is_(True),
            Compra.data >= data_inicio,
            Compra.data <= data_fim,
        )
        .group_by(Cliente.id)
        .order_by(func.count(Compra.id).desc())
        .limit(limite)
    )
    return list(session.execute(stmt).all())


def listar_evolucao_mensal(session: Session, meses: int = 6) -> list[tuple[str, Decimal]]:
    """Soma o valor de compras por mês, para os últimos ``meses`` meses (incluindo o atual).

    Args:
        session: Sessão SQLAlchemy ativa.
        meses: Quantidade de meses a considerar (incluindo o mês atual).

    Returns:
        Lista de tuplas (mes "AAAA-MM", valor_total), em ordem cronológica.
    """
    hoje = date.today()
    ano, mes = hoje.year, hoje.month - (meses - 1)
    while mes <= 0:
        mes += 12
        ano -= 1
    data_inicio = date(ano, mes, 1)

    stmt = (
        select(
            func.to_char(Compra.data, "YYYY-MM").label("mes"),
            func.coalesce(func.sum(Compra.valor), 0),
        )
        .where(Compra.ativo.is_(True), Compra.data >= data_inicio)
        .group_by("mes")
        .order_by("mes")
    )
    return [(mes_str, Decimal(total)) for mes_str, total in session.execute(stmt).all()]


def calcular_total_em_aberto_geral(session: Session) -> Decimal:
    """Soma o total em aberto de todos os clientes (visão geral do negócio).

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Soma de todas as compras não quitadas e ativas.
    """
    stmt = select(func.coalesce(func.sum(Compra.valor), 0)).where(
        Compra.ativo.is_(True), Compra.status != StatusCompra.QUITADA
    )
    total = session.execute(stmt).scalar_one()
    return Decimal(total)
