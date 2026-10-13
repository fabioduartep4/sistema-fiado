"""Repositório de acesso a dados da entidade HistoricoAlteracao (leitura)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session, joinedload

from app.models.cliente import Cliente
from app.models.compra import Compra
from app.models.historico_alteracao import HistoricoAlteracao


def listar(
    session: Session, entidade: Optional[str] = None, limite: int = 200
) -> list[HistoricoAlteracao]:
    """Lista o histórico de alterações ("Histórico" > "Alterações", na tela
    de Histórico), do mais recente para o mais antigo.

    Sempre exclui três tipos de entrada que não fazem sentido junto de
    "criei cadastro"/"excluí uma conta" — cada uma já tem seu próprio
    lugar: a criação de uma Compra (ver ``listar_historico_vendas``, na
    aba "Vendas") e a criação de um Pagamento (ver
    ``listar_historico_recebimentos``, na aba "Recebimentos") viram suas
    próprias listas dedicadas; login/logout de Usuario são eventos de
    sessão, não uma alteração num registro.

    Args:
        session: Sessão SQLAlchemy ativa.
        entidade: Se informado, filtra apenas por essa entidade (ex.:
            "Cliente", "Pagamento", "Usuario" — "Compra" nunca aparece
            aqui, ver acima).
        limite: Número máximo de registros retornados.

    Returns:
        Lista de :class:`HistoricoAlteracao`, com o usuário já carregado
        (evita consulta adicional ao acessar ``registro.usuario``).
    """
    stmt = (
        select(HistoricoAlteracao)
        .options(joinedload(HistoricoAlteracao.usuario))
        .where(
            HistoricoAlteracao.entidade != "Compra",
            ~and_(HistoricoAlteracao.entidade == "Pagamento", HistoricoAlteracao.acao == "criacao"),
            ~and_(
                HistoricoAlteracao.entidade == "Usuario",
                HistoricoAlteracao.acao.in_(("login", "logout")),
            ),
        )
        .order_by(HistoricoAlteracao.data_hora.desc())
        .limit(limite)
    )
    if entidade:
        stmt = stmt.where(HistoricoAlteracao.entidade == entidade)
    return list(session.execute(stmt).scalars().all())


def obter_data_ultima_importacao_xml(session: Session) -> Optional[datetime]:
    """Momento em que a compra mais recente foi importada de XML (None se nunca houve).

    Ignora compras de clientes excluídos.
    """
    stmt = (
        select(func.max(HistoricoAlteracao.data_hora))
        .join(Compra, Compra.id == HistoricoAlteracao.entidade_id)
        .join(Cliente, Cliente.id == Compra.cliente_id)
        .where(
            HistoricoAlteracao.entidade == "Compra",
            HistoricoAlteracao.acao == "criacao_via_xml",
            Cliente.ativo.is_(True),
        )
    )
    return session.execute(stmt).scalar_one_or_none()
