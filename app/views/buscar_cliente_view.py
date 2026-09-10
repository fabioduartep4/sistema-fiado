"""Tela de Busca de Cliente (PySide6).

A busca é disparada com *debounce* (aguarda uma pausa na digitação) e
executada em uma ``QThread`` separada, para que a interface nunca trave
enquanto o banco de dados é consultado — ver
``app.views.componentes.CampoBuscaClienteWidget``, que também é reaproveitado
pelas telas de Adicionar Compra e Receber Conta.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.controllers.cliente_controller import ClienteController
from app.services.auth_service import UsuarioAutenticado
from app.views.componentes import CampoBuscaClienteWidget
from app.views.ficha_cliente_view import FichaClienteView


class BuscarClienteView(QWidget):
    """Tela de busca de cliente, com resultados em tempo real."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado

        self._campo_busca = CampoBuscaClienteWidget(
            ClienteController(usuario_logado), mostrar_pendente_confirmacao=True
        )
        self._campo_busca.resultado_ativado.connect(self._abrir_ficha)

        titulo = QLabel("Buscar Cliente")
        titulo.setProperty("papel", "titulo")

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(QLabel("Dê duplo clique em um cliente para abrir a ficha."))
        layout.addWidget(self._campo_busca)
        self.setLayout(layout)

    def _abrir_ficha(self, cliente_id: str, _nome_principal: str) -> None:
        dialogo = FichaClienteView(self._usuario_logado, cliente_id, self)
        dialogo.exec()
        self._campo_busca.refazer_busca()  # atualiza a lista (cliente pode ter sido editado/excluído)
