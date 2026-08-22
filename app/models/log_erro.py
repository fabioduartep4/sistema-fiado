"""Modelo ORM: LogErro.

O requisito pede registro de erros em arquivo (ver app.config.logging_config),
mas também persistimos os erros no banco de dados: isso permite consultar o
histórico de erros pela própria interface do sistema (tela administrativa),
sem depender de acesso direto ao servidor para ler arquivos de log.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, ColunasComunsMixin


class LogErro(Base, ColunasComunsMixin):
    """Representa um erro registrado pelo sistema.

    Attributes:
        data_hora: Momento em que o erro ocorreu.
        usuario: Login do usuário autenticado no momento do erro (ou
            "não autenticado").
        erro: Mensagem resumida do erro.
        stacktrace: Stacktrace completo, para diagnóstico técnico.
    """

    __tablename__ = "log_erros"

    data_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    usuario: Mapped[str] = mapped_column(String(50), nullable=False)
    erro: Mapped[str] = mapped_column(String(500), nullable=False)
    stacktrace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<LogErro erro={self.erro!r} data_hora={self.data_hora}>"
