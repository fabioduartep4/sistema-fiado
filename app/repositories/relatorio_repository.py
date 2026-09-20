"""Repositório de relatórios agregados (somente leitura).

Contém o relatório de saldo em aberto por cliente (usado na aba
Histórico), os históricos de Vendas e Recebimentos (compras/pagamentos
lançados, um por linha — ver ``listar_historico_vendas``/
``listar_historico_recebimentos``) e as consultas agregadas usadas no
painel de Início (vendas de hoje, maior valor gasto, mais contas
lançadas, evolução mensal, total em aberto geral, clientes com maior
atraso e clientes acima do limite de fiado) — todas somente para
Administrador.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.compra import Compra, StatusCompra
from app.models.historico_alteracao import HistoricoAlteracao
from app.models.pagamento import Pagamento
from app.models.usuario import Usuario


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


def listar_saldos_em_atraso(
    session: Session, data_limite: date
) -> list[tuple[Cliente, Decimal, Decimal, date]]:
    """Lista clientes com compras em aberto lançadas há mais de N dias.

    Usado como aproximação de "saldo em atraso" — o modelo de dados não tem
    uma data de vencimento própria (fiado não tem prazo fixo), então a data
    da compra é usada como referência: quanto mais antiga uma compra ainda
    em aberto, mais "atrasada" ela está.

    Args:
        session: Sessão SQLAlchemy ativa.
        data_limite: Só considera "atrasada" (pra fins de filtro e de
            ``total_em_atraso``) uma compra com ``data <= data_limite``
            (ex.: hoje menos 30 dias).

    Returns:
        Lista de tuplas (cliente, total_em_atraso, total_em_aberto,
        data_da_compra_mais_antiga_em_atraso), da maior para a menor soma
        atrasada. ``total_em_atraso`` soma só as compras que passam do
        limite; ``total_em_aberto`` soma TODAS as compras em aberto do
        cliente (atrasadas ou não) — a situação completa da conta, não só
        a parte atrasada.
    """
    esta_atrasada = Compra.data <= data_limite
    valor_se_atrasada = case((esta_atrasada, Compra.valor), else_=0)
    stmt = (
        select(
            Cliente,
            func.sum(valor_se_atrasada),
            func.sum(Compra.valor),
            func.min(case((esta_atrasada, Compra.data))),
        )
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Compra.ativo.is_(True),
            Compra.status != StatusCompra.QUITADA,
        )
        .group_by(Cliente.id)
        .having(func.sum(valor_se_atrasada) > 0)
        .order_by(func.sum(valor_se_atrasada).desc())
    )
    return list(session.execute(stmt).all())


def listar_clientes_acima_do_limite(session: Session) -> list[tuple[Cliente, Decimal]]:
    """Lista clientes com saldo em aberto maior que o limite de fiado definido para eles.

    Só considera clientes com ``limite_fiado`` definido (não nulo) — quem
    não tem limite configurado nunca aparece aqui, não importa o quanto
    deva.

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Lista de tuplas (cliente, total_em_aberto), do maior excesso
        (``total_em_aberto - limite_fiado``) para o menor.
    """
    stmt = (
        select(Cliente, func.sum(Compra.valor))
        .join(Compra, Compra.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            Cliente.limite_fiado.is_not(None),
            Compra.ativo.is_(True),
            Compra.status != StatusCompra.QUITADA,
        )
        .group_by(Cliente.id)
        .having(func.sum(Compra.valor) > Cliente.limite_fiado)
        .order_by((func.sum(Compra.valor) - Cliente.limite_fiado).desc())
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


def calcular_total_vendido_no_dia(session: Session, dia: date) -> Decimal:
    """Soma o valor de todas as vendas no fiado lançadas em um dia específico.

    Diferente do total em aberto, aqui conta toda venda feita naquele dia,
    já paga ou não — é sobre o que foi vendido, não sobre o que ainda
    está pendente (mesmo critério de :func:`listar_maior_valor_gasto`).

    Args:
        session: Sessão SQLAlchemy ativa.
        dia: Data a considerar.

    Returns:
        Soma do valor de todas as compras ativas lançadas em ``dia``.
    """
    stmt = select(func.coalesce(func.sum(Compra.valor), 0)).where(
        Compra.ativo.is_(True), Compra.data == dia
    )
    total = session.execute(stmt).scalar_one()
    return Decimal(total)


def listar_vendas_ultimos_dias(session: Session, dias: int = 7) -> list[tuple[date, Decimal]]:
    """Soma o valor de vendas no fiado por dia, para os últimos ``dias`` dias (incluindo hoje).

    Ao contrário de :func:`listar_evolucao_mensal` (que só lista meses com
    alguma venda), aqui todo dia da janela aparece no resultado, mesmo sem
    nenhuma venda (total zero) — numa janela tão curta (dias, não meses) é
    comum ter um dia sem nenhuma venda (ex.: mercado fechado no domingo),
    e pular esse dia deixaria o gráfico com menos pontos que o esperado.

    Args:
        session: Sessão SQLAlchemy ativa.
        dias: Quantidade de dias a considerar (incluindo hoje).

    Returns:
        Lista de tuplas (dia, valor_total), em ordem cronológica, sempre
        com exatamente ``dias`` elementos.
    """
    hoje = date.today()
    data_inicio = hoje - timedelta(days=dias - 1)

    stmt = (
        select(Compra.data, func.coalesce(func.sum(Compra.valor), 0))
        .where(Compra.ativo.is_(True), Compra.data >= data_inicio, Compra.data <= hoje)
        .group_by(Compra.data)
    )
    totais_por_dia = {dia_com_venda: Decimal(total) for dia_com_venda, total in session.execute(stmt).all()}

    return [
        (
            data_inicio + timedelta(days=offset),
            totais_por_dia.get(data_inicio + timedelta(days=offset), Decimal("0")),
        )
        for offset in range(dias)
    ]


def listar_historico_vendas(session: Session, limite: int = 200) -> list[tuple]:
    """Lista as compras lançadas no sistema, uma por linha (aba "Vendas").

    Vem do histórico de alterações (não direto da tabela de compras),
    porque é lá que fica registrado quem lançou cada uma — a tabela de
    compras não guarda isso. Cobre tanto lançamento manual (ação
    "criacao") quanto por importação de XML ("criacao_via_xml"); compras
    "Resto" (geradas automaticamente ao dividir um pagamento) nunca geram
    uma entrada de "criacao" aqui, então já ficam de fora naturalmente —
    não são uma venda nova.

    Args:
        session: Sessão SQLAlchemy ativa.
        limite: Número máximo de registros retornados.

    Returns:
        Lista de tuplas (data_hora, nome_cliente, valor, nome_usuario), da
        mais recente para a mais antiga.
    """
    stmt = (
        select(
            HistoricoAlteracao.data_hora,
            Cliente.nome_principal,
            Compra.valor,
            Usuario.nome,
        )
        .join(Compra, Compra.id == HistoricoAlteracao.entidade_id)
        .join(Cliente, Cliente.id == Compra.cliente_id)
        .join(Usuario, Usuario.id == HistoricoAlteracao.usuario_id)
        .where(
            HistoricoAlteracao.entidade == "Compra",
            HistoricoAlteracao.acao.in_(("criacao", "criacao_via_xml")),
        )
        .order_by(HistoricoAlteracao.data_hora.desc())
        .limit(limite)
    )
    return list(session.execute(stmt).all())


def listar_historico_recebimentos(session: Session, limite: int = 200) -> list[tuple]:
    """Lista os pagamentos recebidos no sistema, um por linha (aba "Recebimentos").

    Ao contrário de Vendas, vem direto da tabela de pagamentos — ela já
    guarda quem recebeu (``Pagamento.recebido_por_usuario_id``). Inclui
    pagamentos já estornados (``ativo=False``): o dinheiro foi recebido
    naquele dia, então continua aparecendo aqui — o chamador decide como
    sinalizar visualmente que foi desfeito depois.

    Args:
        session: Sessão SQLAlchemy ativa.
        limite: Número máximo de registros retornados.

    Returns:
        Lista de tuplas (criado_em, nome_cliente, valor_pago, nome_usuario,
        ativo), da mais recente para a mais antiga.
    """
    stmt = (
        select(
            Pagamento.criado_em,
            Cliente.nome_principal,
            Pagamento.valor_pago,
            Usuario.nome,
            Pagamento.ativo,
        )
        .join(Cliente, Cliente.id == Pagamento.cliente_id)
        .join(Usuario, Usuario.id == Pagamento.recebido_por_usuario_id)
        .order_by(Pagamento.criado_em.desc())
        .limit(limite)
    )
    return list(session.execute(stmt).all())
