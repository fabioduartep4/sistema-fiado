"""Tela de Adicionar Compra (PySide6).

Não é mais uma aba própria da janela principal (o cliente já é buscado
antes, em "Buscar Cliente") — hoje só é aberta pelo botão "Adicionar
Compra" da Ficha do Cliente, através de :class:`AdicionarCompraDialog`,
com o cliente já pré-selecionado. A página de busca (``_paginas`` índice
0) continua existindo na classe pra quem quiser reaproveitá-la sem
cliente pré-selecionado, mas nenhuma tela do sistema faz isso hoje.

Reaproveita o mesmo componente de busca de cliente com debounce usado em
Buscar Cliente e Receber Conta (``app.views.componentes.CampoBuscaClienteWidget``).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.controllers.compra_controller import CompraController
from app.services.auth_service import UsuarioAutenticado
from app.services.compra_service import CompradorOpcao
from app.utils.date_utils import obter_data_padrao
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.icons import icone
from app.views.componentes import (
    TAMANHO_DIALOGO_LANCAMENTO,
    TAMANHO_MINIMO_DIALOGO_LANCAMENTO,
    CampoBuscaClienteWidget,
    desligar_botao_padrao,
)

_ID_NENHUM_COMPRADOR = "__nenhum__"


class AdicionarCompraView(QWidget):
    """Tela de lançamento de uma nova compra (fiado)."""

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_pre_selecionado: Optional[tuple[str, str]] = None,
    ) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._compra_controller = CompraController(usuario_logado)
        self._cliente_controller = ClienteController(usuario_logado)
        self._cliente_bloqueado = cliente_pre_selecionado is not None
        self._cliente_id: Optional[str] = None

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self._construir_pagina_busca())
        self._paginas.addWidget(self._construir_pagina_formulario())

        layout = QVBoxLayout()
        titulo = QLabel("Adicionar Compra")
        titulo.setProperty("papel", "titulo")
        layout.addWidget(titulo)
        # Ocupa o diálogo todo: sem isso, a área pega a altura da maior página
        # e a lista de busca fica com tamanho diferente em cada diálogo.
        layout.addWidget(self._paginas, 1)
        self.setLayout(layout)

        if cliente_pre_selecionado is not None:
            cliente_id, nome_principal = cliente_pre_selecionado
            self._selecionar_cliente(cliente_id, nome_principal)
        else:
            self._paginas.setCurrentIndex(0)

    # -- Página 1: busca de cliente ------------------------------------------

    def _construir_pagina_busca(self) -> QWidget:
        pagina = QWidget()

        self._campo_busca_cliente = CampoBuscaClienteWidget(self._cliente_controller)
        self._campo_busca_cliente.resultado_clicado.connect(self._selecionar_cliente)

        layout = QVBoxLayout(pagina)
        layout.addWidget(QLabel("Selecione o cliente:"))
        layout.addWidget(self._campo_busca_cliente)
        return pagina

    # -- Página 2: formulário da compra --------------------------------------

    def _construir_pagina_formulario(self) -> QWidget:
        pagina = QWidget()

        self._label_cliente_selecionado = QLabel()
        self._label_cliente_selecionado.setStyleSheet("font-weight: bold;")

        self._botao_trocar_cliente = QPushButton("Trocar Cliente")
        self._botao_trocar_cliente.setIcon(icone("USERS"))
        self._botao_trocar_cliente.clicked.connect(self._voltar_para_busca)

        self._campo_valor = QLineEdit()
        self._campo_valor.setPlaceholderText("Ex.: 25,50")
        self._campo_valor.setMinimumHeight(36)
        self._campo_valor.returnPressed.connect(self._salvar_compra)  # Enter salva

        self._campo_data = QDateEdit()
        self._campo_data.setCalendarPopup(True)
        self._campo_data.setDisplayFormat("dd/MM/yyyy")
        self._campo_data.setMinimumHeight(36)

        self._campo_comprador = QComboBox()
        self._campo_comprador.setMinimumHeight(36)

        self._campo_observacoes = QTextEdit()
        self._campo_observacoes.setPlaceholderText("Observações (opcional)")
        self._campo_observacoes.setMaximumHeight(60)

        botao_salvar = QPushButton("Salvar Compra")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(44)
        botao_salvar.setProperty("importancia", "primaria")
        botao_salvar.clicked.connect(self._salvar_compra)

        layout = QVBoxLayout(pagina)
        layout.addWidget(self._label_cliente_selecionado)
        layout.addWidget(self._botao_trocar_cliente)
        layout.addWidget(QLabel("Valor:"))
        layout.addWidget(self._campo_valor)
        layout.addWidget(QLabel("Data:"))
        layout.addWidget(self._campo_data)
        layout.addWidget(QLabel("Comprador (opcional):"))
        layout.addWidget(self._campo_comprador)
        layout.addWidget(QLabel("Observações:"))
        layout.addWidget(self._campo_observacoes)
        layout.addWidget(botao_salvar)
        layout.addStretch()
        return pagina

    def _selecionar_cliente(self, cliente_id: str, nome_principal: str) -> None:
        self._cliente_id = cliente_id
        self._label_cliente_selecionado.setText(f"Cliente: {nome_principal}")
        self._botao_trocar_cliente.setVisible(not self._cliente_bloqueado)

        self._campo_data.setDate(QDate(obter_data_padrao()))
        self._carregar_compradores(cliente_id)

        self._paginas.setCurrentIndex(1)
        self._campo_valor.setFocus()  # já pode digitar o valor, sem mouse

    def focar_campo_inicial(self) -> None:
        """Foco no campo por onde o usuário começa: o valor, ou a busca se ainda não há cliente."""
        if self._paginas.currentIndex() == 1:
            self._campo_valor.setFocus()
        else:
            self._campo_busca_cliente.focar_campo()

    def _voltar_para_busca(self) -> None:
        self._paginas.setCurrentIndex(0)
        self._campo_busca_cliente.focar_campo()

    def _carregar_compradores(self, cliente_id: str) -> None:
        self._campo_comprador.clear()
        self._campo_comprador.addItem("Nenhum", userData=_ID_NENHUM_COMPRADOR)
        try:
            compradores: list[CompradorOpcao] = self._compra_controller.listar_compradores(cliente_id)
        except Exception:
            logger.exception("Falha ao carregar compradores do cliente %s.", cliente_id)
            compradores = []
        for comprador in compradores:
            self._campo_comprador.addItem(comprador.nome, userData=comprador.id)

    def _salvar_compra(self) -> None:
        if self._cliente_id is None:
            return

        try:
            valor = Decimal(self._campo_valor.text().strip().replace("R$", "").replace(",", "."))
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Valor inválido", "Informe um valor numérico válido (ex.: 25,50).")
            return

        data_compra = self._campo_data.date().toPython()
        comprador_id = self._campo_comprador.currentData()
        if comprador_id == _ID_NENHUM_COMPRADOR:
            comprador_id = None
        observacoes = self._campo_observacoes.toPlainText().strip() or None

        try:
            compra = self._compra_controller.registrar(
                self._cliente_id, valor, data_compra, comprador_id, observacoes
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível registrar a compra", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao registrar compra para o cliente %s.", self._cliente_id)
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível registrar a compra."
            )
            return

        QMessageBox.information(
            self,
            "Compra registrada",
            f"Compra de {formatar_reais(compra.valor)} registrada com sucesso para {data_compra.strftime('%d/%m/%Y')}.",
        )
        self._campo_valor.clear()
        self._campo_valor.setFocus()  # pronto para o próximo lançamento
        self._campo_observacoes.clear()
        self._campo_data.setDate(QDate(obter_data_padrao()))
        self._campo_comprador.setCurrentIndex(0)


class AdicionarCompraDialog(QDialog):
    """Abre :class:`AdicionarCompraView` como um diálogo modal.

    Usado pelo botão "Adicionar Compra" da Ficha do Cliente, com o
    cliente já pré-selecionado (etapa de busca pulada) — e também pelo
    atalho global "+ Novo Lançamento" (``app.views.novo_lancamento_dialog``),
    sem cliente pré-selecionado (``cliente_id``/``nome_principal``
    omitidos), caso em que a própria :class:`AdicionarCompraView` cuida
    da busca.
    """

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_id: str | None = None,
        nome_principal: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Adicionar Compra — {nome_principal}" if nome_principal else "Adicionar Compra")
        self.setMinimumSize(*TAMANHO_MINIMO_DIALOGO_LANCAMENTO)
        self.resize(*TAMANHO_DIALOGO_LANCAMENTO)

        pre_selecionado = (cliente_id, nome_principal) if cliente_id else None
        self._view = AdicionarCompraView(usuario_logado, cliente_pre_selecionado=pre_selecionado)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self._view)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)
        desligar_botao_padrao(self)

    def showEvent(self, evento) -> None:  # noqa: N802 (nome exigido pelo Qt)
        super().showEvent(evento)
        # Só depois de a janela aparecer: antes disso o foco pedido não "pega".
        QTimer.singleShot(0, self._view.focar_campo_inicial)
