"""Controller de cliente.

Faz a ponte entre as telas de cliente (``app.views``) e a regra de negócio
(``app.services.cliente_service``), mantendo a view livre de lógica de
negócio ou acesso a dados.
"""

from __future__ import annotations

from app.services import cliente_service
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import ClienteBusca, ClienteFicha, ClienteResumo, GrupoDuplicados


class ClienteController:
    """Controlador das telas de cliente.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (necessário para o registro de histórico de auditoria).
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def cadastrar(
        self,
        nome_principal: str,
        nomes_alternativos: list[str],
        telefones: list[str],
        compradores: list[str],
    ) -> ClienteResumo:
        """Cadastra um novo cliente."""
        return cliente_service.cadastrar_cliente(
            self.usuario_logado, nome_principal, nomes_alternativos, telefones, compradores
        )

    def buscar(self, termo: str) -> list[ClienteBusca]:
        """Busca clientes por nome principal ou nome alternativo."""
        return cliente_service.buscar_clientes(termo)

    def ficha(self, cliente_id: str) -> ClienteFicha:
        """Obtém a ficha completa de um cliente."""
        return cliente_service.obter_ficha(cliente_id)

    def editar(
        self,
        cliente_id: str,
        nome_principal: str,
        nomes_alternativos: list[str],
        telefones: list[str],
        compradores: list[str],
    ) -> ClienteFicha:
        """Edita os dados de um cliente existente."""
        return cliente_service.editar_cliente(
            self.usuario_logado, cliente_id, nome_principal, nomes_alternativos, telefones, compradores
        )

    def excluir(self, cliente_id: str) -> None:
        """Exclui logicamente um cliente."""
        cliente_service.excluir_cliente(self.usuario_logado, cliente_id)

    def confirmar(self, cliente_id: str) -> None:
        """Confirma um cliente criado automaticamente pela importação de XML."""
        cliente_service.confirmar_cliente(self.usuario_logado, cliente_id)

    def listar_grupos_duplicados(self) -> list[GrupoDuplicados]:
        """Lista grupos de clientes ativos com o mesmo nome principal."""
        return cliente_service.listar_grupos_duplicados(self.usuario_logado)

    def mesclar(self, cliente_principal_id: str, clientes_duplicados_ids: list[str]) -> None:
        """Mescla clientes duplicados em um cliente principal."""
        cliente_service.mesclar_clientes(self.usuario_logado, cliente_principal_id, clientes_duplicados_ids)
