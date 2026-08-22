"""Serviço de autenticação.

Contém a regra de negócio de login: verificação de credenciais, hash de
senha (via Argon2, algoritmo moderno e recomendado para senhas) e emissão
de uma sessão de usuário autenticado para a aplicação.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.config.logging_config import definir_usuario_logado, logger
from app.database.connection import SessionLocal, session_scope
from app.models.usuario import PerfilUsuario, Usuario
from app.repositories import usuario_repository
from app.services import historico_service

_hasher = PasswordHasher()


@dataclass(frozen=True)
class UsuarioAutenticado:
    """Dados do usuário autenticado, expostos para o restante da aplicação.

    Deliberadamente não guarda a sessão SQLAlchemy nem o hash da senha —
    apenas o necessário para exibição e checagem de permissões.
    """

    id: str
    nome: str
    login: str
    perfil: PerfilUsuario

    @property
    def eh_administrador(self) -> bool:
        """True se o usuário autenticado for Administrador."""
        return self.perfil == PerfilUsuario.ADMINISTRADOR


class CredenciaisInvalidasError(Exception):
    """Lançada quando login ou senha estão incorretos (mensagem genérica,
    para não revelar se o problema foi o login ou a senha)."""


def gerar_hash_senha(senha: str) -> str:
    """Gera o hash Argon2 de uma senha em texto puro.

    Args:
        senha: Senha em texto puro.

    Returns:
        Hash da senha, pronto para ser armazenado em ``Usuario.senha_hash``.
    """
    return _hasher.hash(senha)


def autenticar(login: str, senha: str) -> UsuarioAutenticado:
    """Autentica um usuário pelo login e senha.

    Em caso de sucesso, também registra o usuário logado no contexto de
    logging (para que os logs de erro subsequentes identifiquem quem
    estava usando o sistema).

    Login/senha incorretos são tratados como fluxo de negócio normal (não
    geram entrada no log de erros) — apenas falhas técnicas inesperadas
    (ex.: banco de dados fora do ar) são logadas.

    Args:
        login: Login informado pelo usuário.
        senha: Senha em texto puro informada pelo usuário.

    Returns:
        Um :class:`UsuarioAutenticado` com os dados básicos do usuário.

    Raises:
        CredenciaisInvalidasError: Se o login não existir, estiver inativo,
            ou a senha estiver incorreta.
    """
    session = SessionLocal()
    try:
        usuario: Usuario | None = usuario_repository.buscar_por_login(session, login.strip())
    except Exception:
        logger.exception("Falha técnica ao consultar usuário durante autenticação.")
        raise
    finally:
        session.close()

    if usuario is None:
        raise CredenciaisInvalidasError("Login ou senha inválidos.")

    try:
        _hasher.verify(usuario.senha_hash, senha)
    except VerifyMismatchError as exc:
        raise CredenciaisInvalidasError("Login ou senha inválidos.") from exc

    resultado = UsuarioAutenticado(
        id=str(usuario.id),
        nome=usuario.nome,
        login=usuario.login,
        perfil=usuario.perfil,
    )

    try:
        with session_scope() as session_historico:
            historico_service.registrar_historico(
                session_historico,
                entidade="Usuario",
                entidade_id=usuario.id,
                usuario_id=usuario.id,
                acao="login",
            )
    except Exception:
        logger.exception("Falha ao registrar o login no histórico de auditoria.")

    definir_usuario_logado(resultado.login)
    return resultado


def encerrar_sessao(usuario_logado: UsuarioAutenticado) -> None:
    """Encerra a sessão do usuário atual (logout) e registra no histórico.

    Args:
        usuario_logado: Usuário que está encerrando a sessão.
    """
    try:
        with session_scope() as session_historico:
            historico_service.registrar_historico(
                session_historico,
                entidade="Usuario",
                entidade_id=uuid.UUID(usuario_logado.id),
                usuario_id=uuid.UUID(usuario_logado.id),
                acao="logout",
            )
    except Exception:
        logger.exception("Falha ao registrar o logout no histórico de auditoria.")

    definir_usuario_logado("não autenticado")
