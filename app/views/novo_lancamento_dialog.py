"""Diálogo "Novo Lançamento" (PySide6).

Atalho global — acessível de qualquer tela através do botão no cabeçalho
da janela principal (``app.views.main_window``) — para lançar uma compra
ou registrar um pagamento sem precisar passar pela Ficha de um cliente
específico primeiro. Só escolhe o tipo; quem busca o cliente e preenche
o formulário são as telas que já existem (``AdicionarCompraDialog``/
``ReceberContaDialog``, chamadas aqui sem cliente pré-selecionado).
"""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.services.auth_service import UsuarioAutenticado
from app.utils.icons import icone
from app.views.adicionar_compra_view import AdicionarCompraDialog
from app.views.receber_conta_view import ReceberContaDialog


class NovoLancamentoDialog(QDialog):
    """Escolhe entre lançar uma Compra ou registrar um Pagamento."""

    def __init__(self, usuario_logado: UsuarioAutenticado, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado
        self.setWindowTitle("Novo Lançamento")
        self.setMinimumSize(420, 200)

        titulo = QLabel("O que deseja registrar?")
        titulo.setProperty("papel", "subtitulo")

        botao_compra = QPushButton("Compra\nRegistrar fiado")
        botao_compra.setIcon(icone("SHOPPING_CART_PLUS"))
        botao_compra.setIconSize(QSize(32, 32))
        botao_compra.setMinimumHeight(96)
        botao_compra.clicked.connect(self._abrir_compra)

        botao_pagamento = QPushButton("Pagamento\nRegistrar valor recebido")
        botao_pagamento.setIcon(icone("CASH_BANKNOTE"))
        botao_pagamento.setIconSize(QSize(32, 32))
        botao_pagamento.setMinimumHeight(96)
        botao_pagamento.clicked.connect(self._abrir_pagamento)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_compra)
        layout_botoes.addWidget(botao_pagamento)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

    def _abrir_compra(self) -> None:
        self.accept()
        AdicionarCompraDialog(self._usuario_logado, parent=self.parentWidget()).exec()

    def _abrir_pagamento(self) -> None:
        self.accept()
        ReceberContaDialog(self._usuario_logado, parent=self.parentWidget()).exec()
