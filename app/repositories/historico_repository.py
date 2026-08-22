"""Repositório de acesso a dados da entidade HistoricoAlteracao (leitura)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.historico_alteracao import HistoricoAlteracao


def listar(
    session: Session, entidade: Optional[str] = None, limite: int = 200
) -> list[HistoricoAlteracao]:
    """Lista o histórico de alterações, do mais recente para o mais antigo.

    Args:
        session: Sessão SQLAlchemy ativa.
        entidade: Se informado, filtra apenas por essa entidade (ex.:
            "Cliente", "Compra", "Pagamento", "Usuario").
        limite: Número máximo de registros retornados.

    Returns:
        Lista de :class:`HistoricoAlteracao`, com o usuário já carregado
        (evita consulta adicional ao acessar ``registro.usuario``).
    """
    stmt = (
        select(HistoricoAlteracao)
        .options(joinedload(HistoricoAlteracao.usuario))
        .order_by(HistoricoAlteracao.data_hora.desc())
        .limit(limite)
    )
    if entidade:
        stmt = stmt.where(HistoricoAlteracao.entidade == entidade)
    return list(session.execute(stmt).scalars().all())
