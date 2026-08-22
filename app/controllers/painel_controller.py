"""Controller do painel de Início (dashboard).

Faz a ponte entre a tela de Início (``app.views.painel_inicio_view``) e o
``app.services.relatorio_service``.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from app.services import relatorio_service
from app.services.auth_service import UsuarioAutenticado
from app.services.relatorio_service import PainelInicio


class PainelController:
    """Controlador do painel de Início.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela (o
            painel exige perfil Administrador).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def obter_painel(
        self, data_inicio: Optional[date] = None, data_fim: Optional[date] = None
    ) -> PainelInicio:
        """Obtém os dados do painel para o período informado."""
        return relatorio_service.obter_painel_inicio(self.usuario_logado, data_inicio, data_fim)
