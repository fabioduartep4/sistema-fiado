"""Worker de busca de cliente compartilhado (PySide6).

Contém a ``QThread`` usada para buscar clientes em segundo plano, sem
travar a interface. Fica em um módulo próprio (em vez de dentro de
``app.views.buscar_cliente_view``) para evitar import circular: as telas
Adicionar Compra e Receber Conta também usam esse worker para o próprio
seletor de cliente, e a Ficha do Cliente importa essas duas telas — um
worker definido dentro de ``buscar_cliente_view`` faria esse módulo
importar (indiretamente, via Ficha do Cliente) a si mesmo.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QWidget

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController


class BuscaClienteWorker(QThread):
    """Executa a busca de clientes em segundo plano, fora da thread da UI."""

    resultado_pronto = Signal(list, int)

    def __init__(
        self,
        controller: ClienteController,
        termo: str,
        sequencia: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._termo = termo
        self._sequencia = sequencia

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            resultados = self._controller.buscar(self._termo)
        except Exception:
            logger.exception("Falha ao buscar clientes com o termo '%s'.", self._termo)
            resultados = []
        self.resultado_pronto.emit(resultados, self._sequencia)
