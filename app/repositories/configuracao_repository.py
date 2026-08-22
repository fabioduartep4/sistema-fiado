"""Repositório de acesso a dados da entidade ConfiguracaoSistema."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.configuracao_sistema import ConfiguracaoSistema


def buscar_por_chave(session: Session, chave: str) -> ConfiguracaoSistema | None:
    """Busca uma configuração pelo nome da chave.

    Args:
        session: Sessão SQLAlchemy ativa.
        chave: Nome da configuração (ex.: "modo_data_padrao").

    Returns:
        A :class:`ConfiguracaoSistema` encontrada, ou None se não existir.
    """
    stmt = select(ConfiguracaoSistema).where(ConfiguracaoSistema.chave == chave)
    return session.execute(stmt).scalar_one_or_none()


def definir(session: Session, chave: str, valor: str) -> ConfiguracaoSistema:
    """Cria ou atualiza (upsert) uma configuração.

    Args:
        session: Sessão SQLAlchemy ativa.
        chave: Nome da configuração.
        valor: Novo valor (sempre armazenado como texto).

    Returns:
        A :class:`ConfiguracaoSistema` criada ou atualizada.
    """
    configuracao = buscar_por_chave(session, chave)
    if configuracao is None:
        configuracao = ConfiguracaoSistema(chave=chave, valor=valor)
        session.add(configuracao)
    else:
        configuracao.valor = valor
    session.flush()
    return configuracao
