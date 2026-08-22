"""Script de ambiente do Alembic.

Integra o Alembic com as configurações (``app.config.settings``) e com os
modelos ORM do projeto (``app.database.base.Base``), para que
``alembic revision --autogenerate`` funcione detectando automaticamente
mudanças nos modelos.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Garante que todos os modelos sejam importados (e registrados no metadata)
# antes do autogenerate rodar.
import app.models  # noqa: F401
from app.config.settings import settings
from app.database.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Usa a URL de conexão vinda das configurações da aplicação (.env), em vez
# do valor (vazio) do alembic.ini.
config.set_main_option("sqlalchemy.url", settings.database.sqlalchemy_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Executa as migrações em modo 'offline' (gera SQL sem conectar ao banco)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Executa as migrações em modo 'online' (conecta ao banco e aplica)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
