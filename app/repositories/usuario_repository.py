"""Repositório de acesso a dados da entidade Usuario.

Camada de repositório: contém apenas consultas/gravações no banco, sem
regra de negócio (validações, hash de senha etc. ficam em
``app.services.auth_service``).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.usuario import PerfilUsuario, Usuario


def buscar_por_login(session: Session, login: str) -> Usuario | None:
    """Busca um usuário ativo pelo login exato.

    Args:
        session: Sessão SQLAlchemy ativa.
        login: Login do usuário.

    Returns:
        O :class:`Usuario` encontrado, ou None se não existir/estiver inativo.
    """
    stmt = select(Usuario).where(Usuario.login == login, Usuario.ativo.is_(True))
    return session.execute(stmt).scalar_one_or_none()


def buscar_por_id(session: Session, usuario_id: uuid.UUID) -> Usuario | None:
    """Busca um usuário (ativo ou inativo) pelo ID.

    Args:
        session: Sessão SQLAlchemy ativa.
        usuario_id: UUID do usuário.

    Returns:
        O :class:`Usuario` encontrado, ou None se não existir.
    """
    return session.get(Usuario, usuario_id)


def listar(session: Session, incluir_inativos: bool = False) -> list[Usuario]:
    """Lista os usuários cadastrados, ordenados por nome.

    Args:
        session: Sessão SQLAlchemy ativa.
        incluir_inativos: Se True, inclui usuários inativados na listagem.

    Returns:
        Lista de :class:`Usuario`.
    """
    stmt = select(Usuario).order_by(Usuario.nome)
    if not incluir_inativos:
        stmt = stmt.where(Usuario.ativo.is_(True))
    return list(session.execute(stmt).scalars().all())


def atualizar_dados(session: Session, usuario: Usuario, nome: str, perfil: PerfilUsuario) -> None:
    """Atualiza nome e perfil de um usuário existente.

    Args:
        session: Sessão SQLAlchemy ativa.
        usuario: Instância do usuário a ser atualizada (já carregada).
        nome: Novo nome completo.
        perfil: Novo perfil de acesso.
    """
    usuario.nome = nome
    usuario.perfil = perfil
    session.flush()


def redefinir_senha(session: Session, usuario: Usuario, senha_hash: str) -> None:
    """Substitui o hash de senha de um usuário (redefinição de senha).

    Args:
        session: Sessão SQLAlchemy ativa.
        usuario: Instância do usuário (já carregada).
        senha_hash: Novo hash de senha.
    """
    usuario.senha_hash = senha_hash
    session.flush()


def definir_ativo(session: Session, usuario: Usuario, ativo: bool) -> None:
    """Inativa (exclusão lógica) ou reativa um usuário.

    Args:
        session: Sessão SQLAlchemy ativa.
        usuario: Instância do usuário (já carregada).
        ativo: True para reativar, False para inativar.
    """
    usuario.ativo = ativo
    session.flush()


def criar_usuario(
    session: Session,
    nome: str,
    login: str,
    senha_hash: str,
    perfil: PerfilUsuario,
) -> Usuario:
    """Cria um novo usuário no banco.

    Args:
        session: Sessão SQLAlchemy ativa (o commit é responsabilidade do
            chamador, tipicamente via ``session_scope()``).
        nome: Nome completo do usuário.
        login: Login único de acesso.
        senha_hash: Hash da senha (nunca a senha em texto puro).
        perfil: Perfil de acesso do usuário.

    Returns:
        O :class:`Usuario` recém-criado (ainda não commitado).
    """
    usuario = Usuario(nome=nome, login=login, senha_hash=senha_hash, perfil=perfil)
    session.add(usuario)
    session.flush()  # garante que o ID seja gerado antes de retornar
    return usuario
