"""Controller de pagamento.

Faz a ponte entre as telas Receber Conta e Histórico de Pagamentos
(``app.views.receber_conta_view`` / ``app.views.historico_pagamentos_view``)
e a regra de negócio (``app.services.pagamento_service``).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from app.services import pagamento_service
from app.services.auth_service import UsuarioAutenticado
from app.services.pagamento_service import PagamentoRegistrado, PagamentoResumo


class PagamentoController:
    """Controlador da tela de Receber Conta.

    Attributes:
        usuario_logado: Usuário autenticado que está operando a tela
            (também é quem fica registrado como "recebido por").
    """

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        self.usuario_logado = usuario_logado

    def registrar(
        self,
        cliente_id: str,
        valor_pago: Decimal,
        data_pagamento: date,
        observacoes: Optional[str],
    ) -> PagamentoRegistrado:
        """Registra o recebimento de um pagamento."""
        return pagamento_service.registrar_pagamento(
            self.usuario_logado, cliente_id, valor_pago, data_pagamento, observacoes
        )

    def listar_pagamentos(self, cliente_id: str) -> list[PagamentoResumo]:
        """Lista o histórico de pagamentos de um cliente."""
        return pagamento_service.listar_pagamentos_por_cliente(cliente_id)

    def estornar(self, pagamento_id: str) -> None:
        """Estorna um pagamento."""
        pagamento_service.estornar_pagamento(self.usuario_logado, pagamento_id)
