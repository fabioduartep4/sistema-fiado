"""Controller de login.

Faz a ponte entre a tela de login (``app.views.login_view``) e a regra de
negócio de autenticação (``app.services.auth_service``), mantendo a view
livre de lógica de negócio ou acesso a dados.
"""

from __future__ import annotations

from app.services import auth_service
from app.services.auth_service import CredenciaisInvalidasError, UsuarioAutenticado


class LoginController:
    """Controlador da tela de login."""

    def tentar_login(self, login: str, senha: str) -> UsuarioAutenticado:
        """Tenta autenticar o usuário com as credenciais informadas.

        Args:
            login: Login digitado pelo usuário.
            senha: Senha digitada pelo usuário.

        Returns:
            O usuário autenticado.

        Raises:
            CredenciaisInvalidasError: Login e/ou senha incorretos, ou
                campos vazios.
        """
        if not login.strip() or not senha:
            raise CredenciaisInvalidasError("Informe login e senha.")

        return auth_service.autenticar(login, senha)
