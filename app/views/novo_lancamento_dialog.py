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
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QWidget

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
        self.setMinimumSize(460, 150)

        botao_compra = self._criar_botao("Compra", "SHOPPING_CART_PLUS")
        botao_compra.clicked.connect(self._abrir_compra)

        botao_pagamento = self._criar_botao("Pagamento", "CASH_BANKNOTE")
        botao_pagamento.clicked.connect(self._abrir_pagamento)

        layout = QHBoxLayout()
        layout.addWidget(botao_compra)
        layout.addWidget(botao_pagamento)
        self.setLayout(layout)

    @staticmethod
    def _criar_botao(texto: str, nome_icone: str) -> QPushButton:
        botao = QPushButton(texto)
        botao.setIcon(icone(nome_icone, tamanho=40))
        botao.setIconSize(QSize(40, 40))
        botao.setMinimumHeight(120)
        botao.setStyleSheet("font-size: 24px; font-weight: 700;")
        return botao

    def _abrir_compra(self) -> None:
        self.accept()
        AdicionarCompraDialog(self._usuario_logado, parent=self.parentWidget()).exec()

    def _abrir_pagamento(self) -> None:
        self.accept()
        ReceberContaDialog(self._usuario_logado, parent=self.parentWidget()).exec()
