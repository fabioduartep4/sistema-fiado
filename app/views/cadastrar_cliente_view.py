"""Tela de Cadastrar Cliente (PySide6).

Nesta etapa, cobre apenas o cadastro (criação) de um cliente novo, com
nome principal (obrigatório) e nomes alternativos, telefones e
compradores (todos opcionais e multivalorados). A edição de um cliente já
existente faz parte da "ficha do cliente", a ser implementada na etapa de
Busca de Cliente.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.views.componentes import ListaDinamicaWidget


class CadastrarClienteView(QWidget):
    """Tela de cadastro de um novo cliente."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = ClienteController(usuario_logado)

        self._campo_nome_principal = QLineEdit()
        self._campo_nome_principal.setPlaceholderText("Nome principal (obrigatório)")
        self._campo_nome_principal.setMinimumHeight(38)

        self._lista_nomes_alternativos = ListaDinamicaWidget(
            "Nomes alternativos (opcional)", "Digite um apelido e clique em Adicionar"
        )
        self._lista_telefones = ListaDinamicaWidget(
            "Telefones (opcional)", "Digite um telefone e clique em Adicionar"
        )
        self._lista_compradores = ListaDinamicaWidget(
            "Compradores (opcional)", "Digite o nome de um comprador e clique em Adicionar"
        )

        self._campo_limite_fiado = QLineEdit()
        self._campo_limite_fiado.setPlaceholderText(
            "Limite de fiado (opcional, ex.: 200,00) — deixe em branco para não ter limite"
        )
        self._campo_limite_fiado.setMinimumHeight(38)

        botao_salvar = QPushButton("Salvar Cliente")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(44)
        botao_salvar.clicked.connect(self._salvar)

        botao_limpar = QPushButton("Limpar Formulário")
        botao_limpar.setIcon(icone("ERASER"))
        botao_limpar.setMinimumHeight(38)
        botao_limpar.clicked.connect(self._limpar_formulario)

        titulo = QLabel("Cadastrar Cliente")
        titulo.setStyleSheet("font-size: 16px; font-weight: bold;")

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(QLabel("Nome principal:"))
        layout.addWidget(self._campo_nome_principal)
        layout.addWidget(self._lista_nomes_alternativos)
        layout.addWidget(self._lista_telefones)
        layout.addWidget(self._lista_compradores)
        layout.addWidget(QLabel("Limite de fiado:"))
        layout.addWidget(self._campo_limite_fiado)
        layout.addWidget(botao_salvar)
        layout.addWidget(botao_limpar)
        layout.addStretch()
        self.setLayout(layout)

    def _limite_fiado(self) -> Decimal | None:
        """Faz o parse do campo de limite, ou None se estiver em branco.

        Raises:
            ValueError: Se o texto não for um valor numérico válido.
        """
        texto = self._campo_limite_fiado.text().strip()
        if not texto:
            return None
        return Decimal(texto.replace("R$", "").replace(",", ".").strip())

    def _salvar(self) -> None:
        try:
            limite_fiado = self._limite_fiado()
        except (InvalidOperation, ValueError):
            QMessageBox.warning(
                self, "Limite inválido", "Informe um valor numérico válido (ex.: 200,00) ou deixe em branco."
            )
            return

        try:
            cliente = self._controller.cadastrar(
                nome_principal=self._campo_nome_principal.text(),
                nomes_alternativos=self._lista_nomes_alternativos.itens(),
                telefones=self._lista_telefones.itens(),
                compradores=self._lista_compradores.itens(),
                limite_fiado=limite_fiado,
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível cadastrar o cliente", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao cadastrar cliente.")
            QMessageBox.critical(
                self,
                "Erro inesperado",
                "Não foi possível cadastrar o cliente. Verifique a conexão com o "
                "banco de dados.",
            )
            return

        QMessageBox.information(
            self,
            "Cliente cadastrado",
            f"Cliente '{cliente.nome_principal}' cadastrado com sucesso "
            f"(código {cliente.id_visivel}).",
        )
        self._limpar_formulario()

    def _limpar_formulario(self) -> None:
        self._campo_nome_principal.clear()
        self._lista_nomes_alternativos.limpar()
        self._lista_telefones.limpar()
        self._lista_compradores.limpar()
        self._campo_limite_fiado.clear()
        self._campo_nome_principal.setFocus()
