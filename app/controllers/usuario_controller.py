"""Controller de gestão de usuários.

Faz a ponte entre a tela de usuários (``app.views.usuario_view``) e a
regra de negócio (``app.services.usuario_service``), mantendo a view livre
de lógica de negócio ou acesso a dados.
"""

from __future__ import annotations

from app.models.usuario import PerfilUsuario
from app.services import usuario_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import UsuarioResumo


class UsuarioController:
    """Controlador da tela de gestão de usuários.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (necessário para a checagem de permissão de Administrador,
            feita na camada de serviço).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def listar(self, incluir_inativos: bool = True) -> list[UsuarioResumo]:
        """Lista os usuários cadastrados."""
        return usuario_service.listar_usuarios(self.usuario_logado, incluir_inativos)

    def criar(self, nome: str, login: str, senha: str, perfil: PerfilUsuario) -> UsuarioResumo:
        """Cria um novo usuário."""
        return usuario_service.criar_usuario(self.usuario_logado, nome, login, senha, perfil)

    def editar(self, usuario_id: str, nome: str, perfil: PerfilUsuario) -> UsuarioResumo:
        """Edita nome e perfil de um usuário existente."""
        return usuario_service.editar_usuario(self.usuario_logado, usuario_id, nome, perfil)

    def redefinir_senha(self, usuario_id: str, nova_senha: str) -> None:
        """Redefine a senha de um usuário."""
        usuario_service.redefinir_senha(self.usuario_logado, usuario_id, nova_senha)

    def definir_ativo(self, usuario_id: str, ativo: bool) -> None:
        """Inativa ou reativa um usuário."""
        usuario_service.definir_ativo(self.usuario_logado, usuario_id, ativo)
