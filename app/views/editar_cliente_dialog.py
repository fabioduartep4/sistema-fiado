"""Diálogo de edição de cliente (PySide6).

Aberto a partir da Ficha do Cliente (botão "Editar Cliente"). Reaproveita
``ListaDinamicaWidget`` (mesmo componente usado no cadastro), pré-populado
com os dados atuais do cliente.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.cliente_service import ClienteFicha
from app.utils.icons import icone
from app.views.componentes import ListaDinamicaWidget


class EditarClienteDialog(QDialog):
    """Formulário de edição de nome principal, nomes alternativos,
    telefones e compradores de um cliente existente."""

    def __init__(self, ficha: ClienteFicha, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Editar Cliente — {ficha.nome_principal}")
        self.setMinimumSize(420, 540)

        self._campo_nome_principal = QLineEdit(ficha.nome_principal)
        self._campo_nome_principal.setMinimumHeight(36)

        self._lista_nomes_alternativos = ListaDinamicaWidget(
            "Nomes alternativos (opcional)", "Digite um apelido e clique em Adicionar"
        )
        self._lista_nomes_alternativos.definir_itens(ficha.nomes_alternativos)

        self._lista_telefones = ListaDinamicaWidget(
            "Telefones (opcional)", "Digite um telefone e clique em Adicionar"
        )
        self._lista_telefones.definir_itens(ficha.telefones)

        self._lista_compradores = ListaDinamicaWidget(
            "Compradores (opcional)", "Digite o nome de um comprador e clique em Adicionar"
        )
        self._lista_compradores.definir_itens(ficha.compradores)

        botao_salvar = QPushButton("Salvar Alterações")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(42)
        botao_salvar.setDefault(True)
        botao_salvar.clicked.connect(self._validar_e_aceitar)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setIcon(icone("X"))
        botao_cancelar.setMinimumHeight(42)
        botao_cancelar.clicked.connect(self.reject)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_cancelar)
        layout_botoes.addWidget(botao_salvar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Nome principal:"))
        layout.addWidget(self._campo_nome_principal)
        layout.addWidget(self._lista_nomes_alternativos)
        layout.addWidget(self._lista_telefones)
        layout.addWidget(self._lista_compradores)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

    def _validar_e_aceitar(self) -> None:
        if not self._campo_nome_principal.text().strip():
            QMessageBox.warning(self, "Nome obrigatório", "O nome principal é obrigatório.")
            return
        self.accept()

    def dados(self) -> tuple[str, list[str], list[str], list[str]]:
        """Retorna (nome_principal, nomes_alternativos, telefones, compradores)."""
        return (
            self._campo_nome_principal.text().strip(),
            self._lista_nomes_alternativos.itens(),
            self._lista_telefones.itens(),
            self._lista_compradores.itens(),
        )
