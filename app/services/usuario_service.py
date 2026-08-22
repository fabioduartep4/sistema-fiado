"""Serviço de gestão de usuários.

Todas as operações aqui exigem que quem as executa seja Administrador —
essa checagem é feita aqui (na camada de serviço), como segunda linha de
defesa além de a tela só ficar visível para Administradores.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.database.connection import session_scope
from app.models.usuario import PerfilUsuario, Usuario
from app.repositories import usuario_repository
from app.services import historico_service
from app.services.auth_service import UsuarioAutenticado, gerar_hash_senha
from app.utils.error_handler import tratar_erros


class PermissaoNegadaError(Exception):
    """Lançada quando um usuário sem permissão de Administrador tenta
    executar uma operação restrita."""


class LoginJaExisteError(Exception):
    """Lançada ao tentar criar/editar um usuário com um login já em uso."""


@dataclass(frozen=True)
class UsuarioResumo:
    """Dados de um usuário para exibição em listas/tabelas."""

    id: str
    nome: str
    login: str
    perfil: PerfilUsuario
    ativo: bool


def _exigir_administrador(usuario_logado: UsuarioAutenticado) -> None:
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem gerenciar usuários.")


def _para_resumo(usuario: Usuario) -> UsuarioResumo:
    return UsuarioResumo(
        id=str(usuario.id),
        nome=usuario.nome,
        login=usuario.login,
        perfil=usuario.perfil,
        ativo=usuario.ativo,
    )


@tratar_erros
def listar_usuarios(
    usuario_logado: UsuarioAutenticado, incluir_inativos: bool = True
) -> list[UsuarioResumo]:
    """Lista os usuários cadastrados.

    Args:
        usuario_logado: Usuário autenticado que está solicitando a listagem.
        incluir_inativos: Se True, inclui usuários inativados na listagem.

    Returns:
        Lista de :class:`UsuarioResumo`.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)
    with session_scope() as session:
        usuarios = usuario_repository.listar(session, incluir_inativos=incluir_inativos)
        return [_para_resumo(u) for u in usuarios]


@tratar_erros
def criar_usuario(
    usuario_logado: UsuarioAutenticado,
    nome: str,
    login: str,
    senha: str,
    perfil: PerfilUsuario,
) -> UsuarioResumo:
    """Cria um novo usuário do sistema.

    Args:
        usuario_logado: Usuário autenticado que está criando o novo usuário.
        nome: Nome completo do novo usuário.
        login: Login único do novo usuário.
        senha: Senha em texto puro (será convertida em hash Argon2).
        perfil: Perfil de acesso do novo usuário.

    Returns:
        Um :class:`UsuarioResumo` do usuário recém-criado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        LoginJaExisteError: Se já existir um usuário ativo com esse login.
        ValueError: Se algum campo obrigatório estiver vazio.
    """
    _exigir_administrador(usuario_logado)

    nome = nome.strip()
    login = login.strip()
    if not nome or not login or not senha:
        raise ValueError("Nome, login e senha são obrigatórios.")

    with session_scope() as session:
        if usuario_repository.buscar_por_login(session, login) is not None:
            raise LoginJaExisteError(f"Já existe um usuário ativo com o login '{login}'.")

        novo_usuario = usuario_repository.criar_usuario(
            session,
            nome=nome,
            login=login,
            senha_hash=gerar_hash_senha(senha),
            perfil=perfil,
        )
        historico_service.registrar_historico(
            session,
            entidade="Usuario",
            entidade_id=novo_usuario.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="criacao",
            valor_novo=f"login={login}, perfil={perfil.value}",
        )
        return _para_resumo(novo_usuario)


@tratar_erros
def editar_usuario(
    usuario_logado: UsuarioAutenticado,
    usuario_id: str,
    nome: str,
    perfil: PerfilUsuario,
) -> UsuarioResumo:
    """Edita nome e perfil de um usuário existente.

    Args:
        usuario_logado: Usuário autenticado que está editando.
        usuario_id: UUID (como texto) do usuário a ser editado.
        nome: Novo nome completo.
        perfil: Novo perfil de acesso.

    Returns:
        Um :class:`UsuarioResumo` atualizado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se o usuário não for encontrado ou o nome for vazio.
    """
    _exigir_administrador(usuario_logado)

    nome = nome.strip()
    if not nome:
        raise ValueError("O nome não pode ficar em branco.")

    with session_scope() as session:
        usuario = usuario_repository.buscar_por_id(session, uuid.UUID(usuario_id))
        if usuario is None:
            raise ValueError("Usuário não encontrado.")

        valor_antigo = f"nome={usuario.nome}, perfil={usuario.perfil.value}"
        usuario_repository.atualizar_dados(session, usuario, nome=nome, perfil=perfil)
        historico_service.registrar_historico(
            session,
            entidade="Usuario",
            entidade_id=usuario.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="edicao",
            valor_antigo=valor_antigo,
            valor_novo=f"nome={nome}, perfil={perfil.value}",
        )
        return _para_resumo(usuario)


@tratar_erros
def redefinir_senha(usuario_logado: UsuarioAutenticado, usuario_id: str, nova_senha: str) -> None:
    """Redefine a senha de um usuário.

    Args:
        usuario_logado: Usuário autenticado que está redefinindo a senha.
        usuario_id: UUID (como texto) do usuário alvo.
        nova_senha: Nova senha em texto puro.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se o usuário não for encontrado ou a senha for vazia.
    """
    _exigir_administrador(usuario_logado)

    if not nova_senha:
        raise ValueError("A senha não pode ficar em branco.")

    with session_scope() as session:
        usuario = usuario_repository.buscar_por_id(session, uuid.UUID(usuario_id))
        if usuario is None:
            raise ValueError("Usuário não encontrado.")

        usuario_repository.redefinir_senha(session, usuario, gerar_hash_senha(nova_senha))
        historico_service.registrar_historico(
            session,
            entidade="Usuario",
            entidade_id=usuario.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="redefinicao_senha",
        )


@tratar_erros
def definir_ativo(usuario_logado: UsuarioAutenticado, usuario_id: str, ativo: bool) -> None:
    """Inativa (exclusão lógica) ou reativa um usuário.

    Args:
        usuario_logado: Usuário autenticado que está realizando a ação.
        usuario_id: UUID (como texto) do usuário alvo.
        ativo: True para reativar, False para inativar.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se o usuário não for encontrado, ou se o usuário tentar
            inativar a própria conta (evita ficar sem acesso).
    """
    _exigir_administrador(usuario_logado)

    if str(usuario_id) == usuario_logado.id and not ativo:
        raise ValueError("Você não pode inativar seu próprio usuário.")

    with session_scope() as session:
        usuario = usuario_repository.buscar_por_id(session, uuid.UUID(usuario_id))
        if usuario is None:
            raise ValueError("Usuário não encontrado.")

        usuario_repository.definir_ativo(session, usuario, ativo)
        historico_service.registrar_historico(
            session,
            entidade="Usuario",
            entidade_id=usuario.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="reativacao" if ativo else "exclusao_logica",
        )
