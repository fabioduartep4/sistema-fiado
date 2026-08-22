"""Preparação automática do esquema do banco de dados.

Evita que o usuário precise rodar ``alembic upgrade head`` manualmente ao
instalar o sistema num computador novo:

- **Banco novo/vazio**: todas as tabelas são criadas diretamente a partir
  dos modelos SQLAlchemy (``Base.metadata.create_all``) — não depende de
  quais arquivos de migração foram gerados até agora. Em seguida, o
  controle de versão do Alembic é marcado como "head" (``stamp``), para
  que futuras atualizações do sistema apliquem migrações incrementais
  normalmente a partir daí.
- **Banco já existente** (já tem a tabela ``clientes``): aplica só as
  migrações pendentes (``alembic upgrade head``), preservando os dados já
  cadastrados.

Funciona tanto rodando a partir do código-fonte quanto dentro do
executável (.exe) gerado pelo PyInstaller — ``alembic.ini`` e a pasta de
migrações são incluídos no pacote (ver ``fiado.spec``).
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

import app.models  # noqa: F401 — garante que todos os modelos estejam registrados
from app.config.settings import settings
from app.database.base import Base
from app.database.connection import engine


def _pasta_recursos() -> Path:
    """Pasta onde ``alembic.ini`` e as migrações estão.

    Funciona tanto rodando a partir do código-fonte (pasta base do
    projeto) quanto dentro do executável gerado pelo PyInstaller, que
    disponibiliza os arquivos empacotados em ``sys._MEIPASS``.
    """
    pasta_empacotada = getattr(sys, "_MEIPASS", None)
    if pasta_empacotada:
        return Path(pasta_empacotada)
    return settings.base_dir


def _montar_config_alembic() -> Config:
    pasta = _pasta_recursos()
    config = Config(str(pasta / "alembic.ini"))
    config.set_main_option("script_location", str(pasta / "app" / "database" / "migrations"))
    config.set_main_option("sqlalchemy.url", settings.database.sqlalchemy_url)
    return config


def _banco_ja_inicializado() -> bool:
    """True se o banco já tiver alguma tabela do sistema (instalação existente)."""
    inspetor = inspect(engine)
    return "clientes" in inspetor.get_table_names()


def aplicar_esquema_banco() -> None:
    """Garante que o banco de dados tenha todas as tabelas necessárias.

    Chamada uma vez, ao iniciar a aplicação (ver ``app.main``), antes de
    exibir a tela de login.

    Raises:
        Exception: Qualquer erro do SQLAlchemy/Alembic ao criar as
            tabelas ou aplicar migrações (ex.: usuário do banco sem
            permissão para criar tabelas) — propagado para o chamador
            decidir como informar o usuário.
    """
    config = _montar_config_alembic()

    if _banco_ja_inicializado():
        command.upgrade(config, "head")
    else:
        Base.metadata.create_all(engine)
        command.stamp(config, "head")
