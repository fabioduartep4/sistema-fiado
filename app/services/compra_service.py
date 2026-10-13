"""Serviço de compra.

Nesta etapa, contém o registro de uma nova compra (lançamento de fiado) e a
listagem de compradores de um cliente, usada para a seleção opcional no
formulário de Adicionar Compra.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.database.connection import session_scope
from app.models.compra import StatusCompra
from app.repositories import cliente_repository, compra_repository
from app.services import historico_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros


@dataclass(frozen=True)
class CompradorOpcao:
    """Um comprador disponível para seleção no formulário de compra."""

    id: str
    nome: str


@dataclass(frozen=True)
class CompraCriada:
    """Dados de uma compra recém-registrada, para exibição."""

    id: str
    valor: Decimal
    data: date


@tratar_erros
def listar_compradores(cliente_id: str) -> list[CompradorOpcao]:
    """Lista os compradores ativos de um cliente, para seleção opcional.

    Args:
        cliente_id: UUID (como texto) do cliente.

    Returns:
        Lista de :class:`CompradorOpcao`.
    """
    with session_scope() as session:
        compradores = compra_repository.listar_compradores_do_cliente(session, uuid.UUID(cliente_id))
        return [CompradorOpcao(id=str(c.id), nome=c.nome) for c in compradores]


# Tamanho da coluna ``compras.descricao``.
_TAMANHO_MAXIMO_OBSERVACOES = 255


@tratar_erros
def registrar_compra(
    usuario_logado: UsuarioAutenticado,
    cliente_id: str,
    valor: Decimal,
    data_compra: date,
    comprador_id: Optional[str] = None,
    observacoes: Optional[str] = None,
) -> CompraCriada:
    """Registra uma nova compra na conta de um cliente.

    Args:
        usuario_logado: Usuário autenticado que está lançando a compra
            (usado para o registro de histórico).
        cliente_id: UUID (como texto) do cliente.
        valor: Valor da compra (deve ser maior que zero).
        data_compra: Data da compra.
        comprador_id: UUID (como texto) do comprador, se informado.
        observacoes: Observações livres do lançamento (opcional, até
            255 caracteres).

    Returns:
        Um :class:`CompraCriada` com os dados da compra registrada.

    Raises:
        ValueError: Se o cliente não for encontrado/estiver inativo, se
            o valor não for maior que zero, ou se a observação passar de
            255 caracteres.
    """
    if valor <= 0:
        raise ValueError("O valor da compra deve ser maior que zero.")

    observacoes = (observacoes or "").strip() or None
    if observacoes and len(observacoes) > _TAMANHO_MAXIMO_OBSERVACOES:
        raise ValueError(
            f"A observação pode ter no máximo {_TAMANHO_MAXIMO_OBSERVACOES} caracteres "
            f"(tem {len(observacoes)})."
        )

    with session_scope() as session:
        cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id))
        if cliente is None or not cliente.ativo:
            raise ValueError("Cliente não encontrado.")

        compra = compra_repository.criar_compra(
            session,
            cliente_id=cliente.id,
            valor=valor,
            data=data_compra,
            comprador_id=uuid.UUID(comprador_id) if comprador_id else None,
            descricao=observacoes,
        )
        historico_service.registrar_historico(
            session,
            entidade="Compra",
            entidade_id=compra.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="criacao",
            valor_novo=f"valor={valor}, data={data_compra}",
        )
        return CompraCriada(id=str(compra.id), valor=compra.valor, data=compra.data)


@tratar_erros
def cancelar_compra(usuario_logado: UsuarioAutenticado, compra_id: str) -> None:
    """Cancela uma compra lançada errada (exclusão lógica; fica no Histórico).

    Só vale para compra ainda em aberto. Compra já quitada precisa primeiro
    do estorno do pagamento; conta "Resto" não é uma compra de verdade, é a
    sobra de um pagamento parcial — some estornando esse pagamento.

    Args:
        usuario_logado: Quem está cancelando (precisa ser Administrador).
        compra_id: UUID (como texto) da compra.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se a compra não existir, já estiver cancelada, não
            estiver em aberto, ou for uma conta "Resto".
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem cancelar compras.")

    with session_scope() as session:
        compra = compra_repository.buscar_por_id(session, uuid.UUID(compra_id))
        if compra is None or not compra.ativo:
            raise ValueError("Compra não encontrada ou já cancelada.")

        cliente_repository.travar_conta(session, compra.cliente_id)
        session.refresh(compra)  # outro computador pode ter recebido/cancelado enquanto esperávamos a trava
        if not compra.ativo:
            raise ValueError("Compra não encontrada ou já cancelada.")
        if compra.eh_resto:
            raise ValueError(
                'Conta "Resto" não pode ser cancelada: ela é a sobra de um pagamento parcial. '
                "Estorne esse pagamento para desfazê-la."
            )
        if compra.status != StatusCompra.ABERTA:
            raise ValueError(
                "Esta compra já foi paga. Estorne o pagamento antes de cancelá-la."
            )

        compra_repository.definir_ativo(session, compra, False)
        historico_service.registrar_historico(
            session,
            entidade="Compra",
            entidade_id=compra.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="cancelamento",
            valor_antigo=f"valor={compra.valor}, data={compra.data}",
        )

