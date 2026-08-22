"""Serviço de histórico/auditoria.

Fornece uma função única para registrar entradas em ``historico_alteracoes``,
usada por todos os demais serviços (cliente, usuário, compra, pagamento
etc.) sempre que um registro é criado, editado, inativado ou tem um
pagamento/estorno lançado.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models.historico_alteracao import HistoricoAlteracao


def registrar_historico(
    session: Session,
    entidade: str,
    entidade_id: uuid.UUID,
    usuario_id: uuid.UUID,
    acao: str,
    campo: Optional[str] = None,
    valor_antigo: Optional[str] = None,
    valor_novo: Optional[str] = None,
) -> None:
    """Registra uma entrada de auditoria.

    Deve ser chamada dentro da mesma transação (``session_scope``) da
    alteração que está sendo auditada, para que ambas sejam persistidas (ou
    revertidas) juntas.

    Args:
        session: Sessão SQLAlchemy ativa (mesma da alteração original).
        entidade: Nome da entidade alterada (ex.: "Cliente", "Usuario").
        entidade_id: UUID do registro alterado.
        usuario_id: UUID do usuário que realizou a alteração.
        acao: Ação realizada (ex.: "criacao", "edicao", "exclusao_logica",
            "reativacao", "pagamento", "estorno", "redefinicao_senha").
        campo: Nome do campo alterado, quando aplicável.
        valor_antigo: Valor anterior do campo, quando aplicável.
        valor_novo: Novo valor do campo, quando aplicável.
    """
    session.add(
        HistoricoAlteracao(
            entidade=entidade,
            entidade_id=entidade_id,
            usuario_id=usuario_id,
            acao=acao,
            campo=campo,
            valor_antigo=valor_antigo,
            valor_novo=valor_novo,
        )
    )
