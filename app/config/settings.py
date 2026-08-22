"""Configurações centrais do sistema.

Todas as configurações sensíveis (dados de conexão com o banco, por exemplo)
são lidas de variáveis de ambiente / arquivo ``.env``, nunca hardcoded no
código-fonte. Isso permite que cada máquina da rede local aponte para o
mesmo servidor PostgreSQL sem precisar alterar código.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _calcular_base_dir() -> Path:
    """Calcula a pasta base da aplicação (onde ficam .env, backups e logs).

    Quando rodando a partir do código-fonte (``python -m app.main``), é a
    pasta que contém a pasta ``app``. Quando rodando como executável
    "congelado" pelo PyInstaller (``.exe``), ``__file__`` aponta para
    dentro da pasta temporária de extração — nesse caso, usamos a pasta
    onde o próprio ``.exe`` está, para que ``.env``, backups e logs fiquem
    ao lado dele (e sobrevivam a atualizações do executável).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


# Diretório raiz da aplicação (pasta que contém a pasta "app" em modo
# código-fonte, ou a pasta do .exe em modo executável).
BASE_DIR: Path = _calcular_base_dir()

# Carrega o arquivo .env, se existir, na pasta base.
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class DatabaseSettings:
    """Agrupa os dados de conexão com o PostgreSQL."""

    host: str
    port: int
    name: str
    user: str
    password: str

    @property
    def sqlalchemy_url(self) -> str:
        """Monta a URL de conexão no formato aceito pelo SQLAlchemy + psycopg 3."""
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass(frozen=True)
class AppSettings:
    """Agrupa as demais configurações da aplicação (pastas, etc.)."""

    base_dir: Path
    backup_dir: Path
    log_dir: Path
    database: DatabaseSettings


def _get_env(name: str, default: str | None = None, required: bool = False) -> str:
    """Lê uma variável de ambiente, com validação opcional de obrigatoriedade.

    Args:
        name: Nome da variável de ambiente.
        default: Valor padrão caso a variável não exista.
        required: Se True, lança erro quando a variável não está definida.

    Returns:
        O valor da variável de ambiente (ou o padrão).

    Raises:
        RuntimeError: Se ``required`` for True e a variável não existir.
    """
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(
            f"Variável de ambiente obrigatória '{name}' não foi definida. "
            f"Verifique o arquivo .env (veja .env.example)."
        )
    return value or ""


def load_settings() -> AppSettings:
    """Carrega e valida todas as configurações da aplicação.

    Returns:
        Uma instância de :class:`AppSettings` pronta para uso.
    """
    database = DatabaseSettings(
        host=_get_env("DB_HOST", required=True),
        port=int(_get_env("DB_PORT", default="5432")),
        name=_get_env("DB_NAME", required=True),
        user=_get_env("DB_USER", required=True),
        password=_get_env("DB_PASSWORD", required=True),
    )

    backup_dir = Path(_get_env("BACKUP_DIR", default=str(BASE_DIR / "app" / "backups")))
    log_dir = Path(_get_env("LOG_DIR", default=str(BASE_DIR / "app" / "logs")))

    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    return AppSettings(
        base_dir=BASE_DIR,
        backup_dir=backup_dir,
        log_dir=log_dir,
        database=database,
    )


# Instância única (singleton) de configurações, usada em toda a aplicação.
settings = load_settings()
