"""Controller de configurações.

Faz a ponte entre a tela Configurações (``app.views.configuracoes_view``) e
o ``app.services.configuracao_service``.
"""

from __future__ import annotations

from app.services import configuracao_service
from app.services.auth_service import UsuarioAutenticado
from app.services.configuracao_service import ModoDataPadrao, ModoTema


class ConfiguracaoController:
    """Controlador da tela de Configurações.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (as alterações exigem perfil Administrador).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def obter_modo_data_padrao(self) -> ModoDataPadrao:
        """Obtém o modo de data padrão configurado."""
        return configuracao_service.obter_modo_data_padrao()

    def definir_modo_data_padrao(self, modo: ModoDataPadrao) -> None:
        """Define o modo de data padrão (configuração global)."""
        configuracao_service.definir_modo_data_padrao(self.usuario_logado, modo)

    def obter_tema(self) -> ModoTema:
        """Obtém o tema configurado (claro ou escuro)."""
        return configuracao_service.obter_tema()

    def definir_tema(self, tema: ModoTema) -> None:
        """Define o tema do sistema (configuração global; requer reiniciar)."""
        configuracao_service.definir_tema(self.usuario_logado, tema)
