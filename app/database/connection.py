"""Gerenciamento de conexão e sessões do SQLAlchemy.

Fornece:

- ``engine``: engine único, compartilhado por toda a aplicação.
- ``SessionLocal``: fábrica de sessões.
- ``session_scope()``: context manager que garante COMMIT em caso de
  sucesso e ROLLBACK automático em caso de exceção, conforme exigido pelo
  requisito de transações do PostgreSQL.

Uso típico em um repositório/serviço::

    from app.database.connection import session_scope

    with session_scope() as session:
        session.add(novo_cliente)
        # commit automático ao sair do bloco sem erro
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.logging_config import logger
from app.config.settings import settings

engine = create_engine(
    settings.database.sqlalchemy_url,
    pool_pre_ping=True,  # detecta conexões mortas (ex.: servidor reiniciado) antes de usá-las
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Cria uma sessão transacional, com commit/rollback automáticos.

    Em caso de qualquer exceção dentro do bloco ``with``, a transação é
    revertida (rollback) e o erro é relançado para ser tratado/logado pela
    camada de serviço ou pelo decorator de tratamento de erros.

    Yields:
        Uma sessão SQLAlchemy pronta para uso.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Erro durante transação com o banco de dados; rollback executado.")
        raise
    finally:
        session.close()


def testar_conexao() -> bool:
    """Testa se é possível conectar ao servidor PostgreSQL configurado.

    Returns:
        True se a conexão foi bem-sucedida, False caso contrário.
    """
    try:
        with engine.connect():
            return True
    except Exception:
        logger.exception("Falha ao conectar ao banco de dados PostgreSQL.")
        return False
