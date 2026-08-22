"""Repositório de acesso a dados da entidade LogErro (leitura)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.log_erro import LogErro


def listar(session: Session, limite: int = 200) -> list[LogErro]:
    """Lista os erros registrados, do mais recente para o mais antigo.

    Args:
        session: Sessão SQLAlchemy ativa.
        limite: Número máximo de registros retornados.

    Returns:
        Lista de :class:`LogErro`.
    """
    stmt = select(LogErro).order_by(LogErro.data_hora.desc()).limit(limite)
    return list(session.execute(stmt).scalars().all())
