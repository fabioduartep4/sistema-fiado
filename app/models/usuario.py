"""Modelo ORM: Usuario.

Usuários do sistema (funcionários da loja), com dois perfis de acesso:
Administrador e Funcionário.
"""

from __future__ import annotations

import enum

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, ColunasComunsMixin


class PerfilUsuario(str, enum.Enum):
    """Perfis de acesso disponíveis no sistema."""

    ADMINISTRADOR = "administrador"
    FUNCIONARIO = "funcionario"


class Usuario(Base, ColunasComunsMixin):
    """Representa um usuário do sistema (login).

    Attributes:
        nome: Nome completo do usuário, para exibição.
        login: Nome de usuário usado para autenticação (único).
        senha_hash: Hash da senha (nunca a senha em texto puro).
        perfil: Perfil de acesso (Administrador ou Funcionário).
    """

    __tablename__ = "usuarios"

    nome: Mapped[str] = mapped_column(String(150), nullable=False)
    login: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    perfil: Mapped[PerfilUsuario] = mapped_column(
        Enum(PerfilUsuario, name="perfil_usuario"), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario login={self.login!r} perfil={self.perfil}>"
