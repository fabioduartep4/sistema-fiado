"""Controller de compra.

Faz a ponte entre a tela Adicionar Compra (``app.views.adicionar_compra_view``)
e a regra de negócio (``app.services.compra_service``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app.services import compra_service
from app.services.auth_service import UsuarioAutenticado
from app.services.compra_service import CompraCriada, CompradorOpcao


class CompraController:
    """Controlador da tela de Adicionar Compra.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (necessário para o registro de histórico de auditoria).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def listar_compradores(self, cliente_id: str) -> list[CompradorOpcao]:
        """Lista os compradores ativos de um cliente."""
        return compra_service.listar_compradores(cliente_id)

    def registrar(
        self,
        cliente_id: str,
        valor: Decimal,
        data_compra: date,
        comprador_id: Optional[str],
    ) -> CompraCriada:
        """Registra uma nova compra."""
        return compra_service.registrar_compra(
            self.usuario_logado, cliente_id, valor, data_compra, comprador_id
        )
