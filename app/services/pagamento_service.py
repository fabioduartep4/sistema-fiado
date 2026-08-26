"""Serviço de pagamento.

Contém a regra de negócio de "Receber Conta": quitação das compras em
aberto de um cliente seguindo FIFO (a compra mais antiga é quitada
primeiro) e geração automática de uma compra "Resto" quando o pagamento
termina no meio de uma compra.

Regra adotada (conforme definido na análise de requisitos): uma compra em
aberto é sempre integralmente devida — nunca fica "parcialmente paga" de
forma persistente. Quando um pagamento cobre parte de uma compra, essa
compra é marcada como quitada e o valor que sobrou vira uma nova compra
("Resto"), que por sua vez poderá ser quitada (total ou parcialmente) em
um pagamento futuro.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from app.database.connection import session_scope
from app.models.compra import StatusCompra
from app.repositories import cliente_repository, compra_repository, pagamento_repository
from app.services import historico_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros
from app.utils.exceptions import ErroDeNegocio


@dataclass(frozen=True)
class PagamentoRegistrado:
    """Resultado do registro de um pagamento, para exibição."""

    id: str
    valor_pago: Decimal
    valor_resto_gerado: Decimal


@tratar_erros
def registrar_pagamento(
    usuario_logado: UsuarioAutenticado,
    cliente_id: str,
    valor_pago: Decimal,
    data_pagamento: date,
    observacoes: Optional[str] = None,
) -> PagamentoRegistrado:
    """Registra o recebimento de um pagamento e aplica a quitação FIFO.

    Args:
        usuario_logado: Usuário autenticado que está recebendo o pagamento
            (vinculado automaticamente como "quem recebeu", conforme
            definido na análise de requisitos).
        cliente_id: UUID (como texto) do cliente que está pagando.
        valor_pago: Valor total recebido (deve ser maior que zero).
        data_pagamento: Data do pagamento.
        observacoes: Observações livres sobre o pagamento (opcional).

    Returns:
        Um :class:`PagamentoRegistrado`, com o valor da compra "Resto"
        gerada (``Decimal("0")`` se o pagamento quitou tudo exatamente).

    Raises:
        ValueError: Se o cliente não for encontrado/estiver inativo, se
            não houver compras em aberto, se o valor pago não for maior
            que zero, se o valor pago exceder o total em aberto, ou se a
            data do pagamento for anterior à da compra em aberto mais
            antiga (evita que a compra "Resto" gerada saia com uma data
            que a coloque à frente de outras compras na fila FIFO).
    """
    if valor_pago <= 0:
        raise ValueError("O valor pago deve ser maior que zero.")

    with session_scope() as session:
        cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id))
        if cliente is None or not cliente.ativo:
            raise ValueError("Cliente não encontrado.")

        compras_abertas = compra_repository.listar_em_aberto_por_cliente(session, cliente.id)
        if not compras_abertas:
            raise ValueError("Este cliente não possui contas em aberto.")

        compra_mais_antiga = compras_abertas[0]
        if data_pagamento < compra_mais_antiga.data:
            raise ValueError(
                f"A data do pagamento ({data_pagamento.strftime('%d/%m/%Y')}) não pode ser "
                f"anterior à data da compra em aberto mais antiga "
                f"({compra_mais_antiga.data.strftime('%d/%m/%Y')})."
            )

        total_em_aberto = sum((compra.valor for compra in compras_abertas), Decimal("0"))
        if valor_pago > total_em_aberto:
            raise ValueError(
                f"O valor pago (R$ {valor_pago:.2f}) é maior que o total em aberto "
                f"(R$ {total_em_aberto:.2f})."
            )

        pagamento = pagamento_repository.criar_pagamento(
            session,
            cliente_id=cliente.id,
            valor_pago=valor_pago,
            data_pagamento=data_pagamento,
            recebido_por_usuario_id=uuid.UUID(usuario_logado.id),
            observacoes=observacoes,
        )

        saldo_do_pagamento = valor_pago
        valor_resto_gerado = Decimal("0")

        for compra in compras_abertas:
            if saldo_do_pagamento <= 0:
                break

            if saldo_do_pagamento >= compra.valor:
                # Quita a compra inteira e segue para a próxima (FIFO).
                pagamento_repository.registrar_aplicacao(
                    session, pagamento.id, compra.id, compra.valor
                )
                compra_repository.marcar_status(session, compra, StatusCompra.QUITADA)
                saldo_do_pagamento -= compra.valor
            else:
                # O pagamento termina no meio desta compra: quita-a
                # integralmente (aplicando o que restou do pagamento) e
                # gera uma nova compra "Resto" com a diferença.
                pagamento_repository.registrar_aplicacao(
                    session, pagamento.id, compra.id, saldo_do_pagamento
                )
                compra_repository.marcar_status(session, compra, StatusCompra.QUITADA)
                valor_resto_gerado = compra.valor - saldo_do_pagamento
                compra_repository.criar_compra_resto(
                    session, compra, valor_resto_gerado, data_pagamento
                )
                saldo_do_pagamento = Decimal("0")

        historico_service.registrar_historico(
            session,
            entidade="Pagamento",
            entidade_id=pagamento.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="criacao",
            valor_novo=f"valor_pago={valor_pago}, cliente_id={cliente.id}",
        )

        return PagamentoRegistrado(
            id=str(pagamento.id),
            valor_pago=pagamento.valor_pago,
            valor_resto_gerado=valor_resto_gerado,
        )


class EstornoNaoPermitidoError(ErroDeNegocio):
    """Lançada quando um pagamento não pode ser estornado com segurança."""


@dataclass(frozen=True)
class CompraQuitadaResumo:
    """Uma compra quitada (total ou parcialmente) por um pagamento específico.

    Exibida no Histórico de Pagamentos, junto do pagamento que a quitou —
    é para lá que uma compra "sai de vista" quando deixa de aparecer na
    lista de compras em aberto da Ficha do Cliente.
    """

    compra_id: str
    valor: Decimal
    data: date
    valor_aplicado: Decimal
    eh_resto: bool
    origem_nfe_xml: Optional[str]


@dataclass(frozen=True)
class PagamentoResumo:
    """Dados de um pagamento, para exibição no histórico do cliente."""

    id: str
    valor_pago: Decimal
    data_pagamento: date
    recebido_por_nome: str
    observacoes: Optional[str]
    ativo: bool
    compras_quitadas: list[CompraQuitadaResumo]


@tratar_erros
def listar_pagamentos_por_cliente(cliente_id: str) -> list[PagamentoResumo]:
    """Lista os pagamentos de um cliente (histórico), incluindo estornados.

    Disponível para qualquer usuário autenticado — é uma consulta, não uma
    ação sensível (diferente do estorno, restrito a Administrador).

    Args:
        cliente_id: UUID (como texto) do cliente.

    Returns:
        Lista de :class:`PagamentoResumo`, mais recente primeiro. Cada um
        traz também as compras que ele quitou (``compras_quitadas``) — um
        pagamento estornado não tem nenhuma, já que o estorno desfaz essas
        aplicações e reabre as compras.
    """
    with session_scope() as session:
        pagamentos = pagamento_repository.listar_por_cliente(session, uuid.UUID(cliente_id))
        return [
            PagamentoResumo(
                id=str(p.id),
                valor_pago=p.valor_pago,
                data_pagamento=p.data_pagamento,
                recebido_por_nome=p.recebido_por.nome,
                observacoes=p.observacoes,
                ativo=p.ativo,
                compras_quitadas=[
                    CompraQuitadaResumo(
                        compra_id=str(aplicacao.compra.id),
                        valor=aplicacao.compra.valor,
                        data=aplicacao.compra.data,
                        valor_aplicado=aplicacao.valor_aplicado,
                        eh_resto=aplicacao.compra.eh_resto,
                        origem_nfe_xml=aplicacao.compra.origem_nfe_xml,
                    )
                    for aplicacao in pagamento_repository.listar_aplicacoes(session, p.id)
                ],
            )
            for p in pagamentos
        ]


@tratar_erros
def estornar_pagamento(usuario_logado: UsuarioAutenticado, pagamento_id: str) -> None:
    """Estorna um pagamento, reabrindo as compras que ele havia quitado.

    Só é permitido quando cada compra "Resto" eventualmente gerada por
    este pagamento ainda não tiver sido tocada por um pagamento posterior
    — do contrário, desfazer este pagamento também desfaria, de forma
    inconsistente, o que aconteceu depois dele.

    Args:
        usuario_logado: Usuário autenticado que está solicitando o estorno.
        pagamento_id: UUID (como texto) do pagamento a ser estornado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se o pagamento não for encontrado, já estiver
            estornado, ou não possuir aplicações registradas.
        EstornoNaoPermitidoError: Se alguma compra "Resto" gerada por este
            pagamento já tiver sido total ou parcialmente paga.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem estornar pagamentos.")

    with session_scope() as session:
        pagamento = pagamento_repository.buscar_por_id(session, uuid.UUID(pagamento_id))
        if pagamento is None or not pagamento.ativo:
            raise ValueError("Pagamento não encontrado ou já estornado.")

        aplicacoes = pagamento_repository.listar_aplicacoes(session, pagamento.id)
        if not aplicacoes:
            raise ValueError("Este pagamento não possui aplicações registradas.")

        # 1ª passada: valida se é seguro estornar, sem alterar nada ainda.
        restos_para_inativar = []
        for aplicacao in aplicacoes:
            compra = aplicacao.compra
            if aplicacao.valor_aplicado < compra.valor:
                resto = compra_repository.buscar_resto_de(session, compra.id)
                if resto is not None:
                    if not resto.ativo or resto.status != StatusCompra.ABERTA:
                        raise EstornoNaoPermitidoError(
                            "Não é possível estornar: a conta 'Resto' gerada por este "
                            "pagamento já foi total ou parcialmente paga."
                        )
                    restos_para_inativar.append(resto)

        # 2ª passada: reverte de fato (só chega aqui se a validação passou).
        for aplicacao in aplicacoes:
            compra_repository.marcar_status(session, aplicacao.compra, StatusCompra.ABERTA)
            aplicacao.ativo = False

        for resto in restos_para_inativar:
            compra_repository.definir_ativo(session, resto, False)

        pagamento_repository.definir_ativo(session, pagamento, False)

        historico_service.registrar_historico(
            session,
            entidade="Pagamento",
            entidade_id=pagamento.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="estorno",
            valor_antigo=f"valor_pago={pagamento.valor_pago}",
        )
