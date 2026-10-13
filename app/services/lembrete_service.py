"""Montagem do lembrete de conta de um cliente (mensagem de WhatsApp).

Decide qual mensagem o cliente recebe e para qual telefone — a regra é a
mesma no botão "Enviar Lembrete" da Ficha do Cliente e nos lembretes em
lote da tela de Início:

1. acima do limite de fiado → avisa que passou do limite combinado;
2. com compra em atraso → avisa do atraso, cita o último pagamento e o total;
3. senão → só informa o total da conta.

Não envia nada: só devolve o texto e o telefone (ver ``app.utils.whatsapp``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

from app.services import cliente_service, pagamento_service
from app.utils.error_handler import tratar_erros
from app.utils.formatacao import formatar_reais
from app.utils.whatsapp import montar_mensagem_lembrete_limite, montar_mensagem_lembrete_saldo

# Há quantos dias uma compra em aberto passa a contar como atrasada.
DIAS_ATRASO_PADRAO = 30


@dataclass(frozen=True)
class Lembrete:
    """Lembrete pronto para um cliente: para quem, em qual telefone e o texto."""

    cliente_id: str
    nome_cliente: str
    telefone: Optional[str]
    mensagem: str


@tratar_erros
def montar_lembrete(cliente_id: str, dias_atraso: int = DIAS_ATRASO_PADRAO) -> Lembrete:
    """Monta o lembrete de um cliente, conforme a situação atual da conta.

    Args:
        cliente_id: UUID (como texto) do cliente.
        dias_atraso: Com quantos dias uma compra em aberto conta como atrasada.

    Returns:
        Um :class:`Lembrete`. ``telefone`` é ``None`` se o cliente não tem
        telefone cadastrado.

    Raises:
        ValueError: Se o cliente não existir ou estiver inativo.
    """
    ficha = cliente_service.obter_ficha(cliente_id)
    total = formatar_reais(ficha.total_em_aberto)

    if ficha.limite_fiado is not None and ficha.total_em_aberto > ficha.limite_fiado:
        mensagem = montar_mensagem_lembrete_limite(
            ficha.nome_principal, total, formatar_reais(ficha.limite_fiado)
        )
    else:
        data_limite = date.today() - timedelta(days=dias_atraso)
        atrasado = any(c.status == "aberta" and c.data <= data_limite for c in ficha.compras)
        data_ultimo_pagamento = None
        if atrasado:
            pagamentos = pagamento_service.listar_pagamentos_por_cliente(cliente_id)
            ultimo_ativo = next((p for p in pagamentos if p.ativo), None)
            if ultimo_ativo is not None:
                data_ultimo_pagamento = ultimo_ativo.data_pagamento.strftime("%d/%m/%Y")
        mensagem = montar_mensagem_lembrete_saldo(
            ficha.nome_principal, data_ultimo_pagamento, total, atrasado
        )

    return Lembrete(
        cliente_id=cliente_id,
        nome_cliente=ficha.nome_principal,
        telefone=ficha.telefones[0] if ficha.telefones else None,
        mensagem=mensagem,
    )
