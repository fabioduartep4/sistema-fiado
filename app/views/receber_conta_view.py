"""Tela de Receber Conta (PySide6).

Segue o mesmo padrão da tela Adicionar Compra: pode ser aberta pela aba
direta (busca o cliente primeiro) ou pelo botão "Receber Conta" da Ficha
do Cliente (cliente já pré-selecionado). Mostra o total em aberto e a
lista de compras pendentes antes de confirmar o pagamento.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.controllers.pagamento_controller import PagamentoController
from app.services.auth_service import UsuarioAutenticado
from app.utils.date_utils import obter_data_padrao
from app.utils.documentos import montar_html_recibo_pagamento
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.views.componentes import CampoBuscaClienteWidget


class ReceberContaView(QWidget):
    """Tela de recebimento de pagamento (quitação de contas em aberto)."""

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_pre_selecionado: Optional[tuple[str, str]] = None,
    ) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._pagamento_controller = PagamentoController(usuario_logado)
        self._cliente_controller = ClienteController(usuario_logado)
        self._cliente_bloqueado = cliente_pre_selecionado is not None
        self._cliente_id: Optional[str] = None
        self._nome_cliente_selecionado: Optional[str] = None

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self._construir_pagina_busca())
        self._paginas.addWidget(self._construir_pagina_formulario())

        layout = QVBoxLayout()
        titulo = QLabel("Receber Conta")
        titulo.setProperty("papel", "titulo")
        layout.addWidget(titulo)
        layout.addWidget(self._paginas)
        layout.addStretch()
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

    # -- Página 2: formulário de pagamento -----------------------------------

    def _construir_pagina_formulario(self) -> QWidget:
        pagina = QWidget()

        self._label_cliente_selecionado = QLabel()
        self._label_cliente_selecionado.setStyleSheet("font-weight: bold;")

        self._botao_trocar_cliente = QPushButton("Trocar Cliente")
        self._botao_trocar_cliente.setIcon(icone("USERS"))
        self._botao_trocar_cliente.clicked.connect(self._voltar_para_busca)

        self._lista_compras_abertas = QListWidget()
        self._lista_compras_abertas.setMaximumHeight(120)

        self._label_total_em_aberto = QLabel()
        self._label_total_em_aberto.setProperty("papel", "subtitulo")

        self._campo_valor_pago = QLineEdit()
        self._campo_valor_pago.setPlaceholderText("Ex.: 25,50")
        self._campo_valor_pago.setMinimumHeight(36)

        self._campo_data = QDateEdit()
        self._campo_data.setCalendarPopup(True)
        self._campo_data.setDisplayFormat("dd/MM/yyyy")
        self._campo_data.setMinimumHeight(36)

        self._label_recebido_por = QLabel(f"Recebido por: {self._usuario_logado.nome}")

        self._campo_observacoes = QTextEdit()
        self._campo_observacoes.setPlaceholderText("Observações (opcional)")
        self._campo_observacoes.setMaximumHeight(60)

        botao_confirmar = QPushButton("Confirmar Pagamento")
        botao_confirmar.setIcon(icone("CASH_BANKNOTE"))
        botao_confirmar.setMinimumHeight(44)
        botao_confirmar.setProperty("importancia", "primaria")
        botao_confirmar.clicked.connect(self._confirmar_pagamento)

        layout = QVBoxLayout(pagina)
        layout.addWidget(self._label_cliente_selecionado)
        layout.addWidget(self._botao_trocar_cliente)
        layout.addWidget(QLabel("Compras em aberto:"))
        layout.addWidget(self._lista_compras_abertas)
        layout.addWidget(self._label_total_em_aberto)
        layout.addWidget(QLabel("Valor pago:"))
        layout.addWidget(self._campo_valor_pago)
        layout.addWidget(QLabel("Data do pagamento:"))
        layout.addWidget(self._campo_data)
        layout.addWidget(self._label_recebido_por)
        layout.addWidget(QLabel("Observações:"))
        layout.addWidget(self._campo_observacoes)
        layout.addWidget(botao_confirmar)
        return pagina

    def _selecionar_cliente(self, cliente_id: str, nome_principal: str) -> None:
        self._cliente_id = cliente_id
        self._nome_cliente_selecionado = nome_principal
        self._label_cliente_selecionado.setText(f"Cliente: {nome_principal}")
        self._botao_trocar_cliente.setVisible(not self._cliente_bloqueado)

        self._campo_data.setDate(QDate(obter_data_padrao()))
        self._carregar_contas_em_aberto(cliente_id)

        self._paginas.setCurrentIndex(1)

    def _voltar_para_busca(self) -> None:
        self._paginas.setCurrentIndex(0)
        self._campo_busca_cliente.focar_campo()

    def _carregar_contas_em_aberto(self, cliente_id: str) -> None:
        self._lista_compras_abertas.clear()
        try:
            ficha = self._cliente_controller.ficha(cliente_id)
        except Exception:
            logger.exception("Falha ao carregar contas em aberto do cliente %s.", cliente_id)
            self._label_total_em_aberto.setText("Total em aberto: R$ 0,00")
            return

        compras_abertas = [c for c in ficha.compras if c.status != "quitada"]
        if not compras_abertas:
            self._lista_compras_abertas.addItem("Nenhuma conta em aberto.")
        for compra in compras_abertas:
            rotulo_resto = " [Resto]" if compra.eh_resto else ""
            data_formatada = compra.data.strftime("%d/%m")
            self._lista_compras_abertas.addItem(
                f"R$ {compra.valor:.2f} — {data_formatada}{rotulo_resto}"
            )

        self._label_total_em_aberto.setText(f"Total em aberto: R$ {ficha.total_em_aberto:.2f}")

    def _confirmar_pagamento(self) -> None:
        if self._cliente_id is None:
            return

        try:
            valor_pago = Decimal(
                self._campo_valor_pago.text().strip().replace("R$", "").replace(",", ".")
            )
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Valor inválido", "Informe um valor numérico válido (ex.: 25,50).")
            return

        data_pagamento = self._campo_data.date().toPython()
        observacoes = self._campo_observacoes.toPlainText().strip() or None

        try:
            resultado = self._pagamento_controller.registrar(
                self._cliente_id, valor_pago, data_pagamento, observacoes
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível registrar o pagamento", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao registrar pagamento para o cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível registrar o pagamento.")
            return

        if resultado.valor_resto_gerado > 0:
            mensagem = (
                f"Pagamento de R$ {resultado.valor_pago:.2f} registrado.\n\n"
                f"Foi gerada uma nova conta 'Resto' de R$ {resultado.valor_resto_gerado:.2f}."
            )
        else:
            mensagem = f"Pagamento de R$ {resultado.valor_pago:.2f} registrado. Conta quitada."

        caixa = QMessageBox(self)
        caixa.setWindowTitle("Pagamento registrado")
        caixa.setText(mensagem)
        caixa.setIcon(QMessageBox.Icon.Information)
        botao_imprimir = caixa.addButton("Imprimir Recibo", QMessageBox.ButtonRole.ActionRole)
        caixa.addButton(QMessageBox.StandardButton.Ok)
        caixa.exec()

        if caixa.clickedButton() == botao_imprimir:
            html = montar_html_recibo_pagamento(
                nome_cliente=self._nome_cliente_selecionado or "",
                valor_pago=resultado.valor_pago,
                data_pagamento=data_pagamento,
                recebido_por=self._usuario_logado.nome,
                observacoes=observacoes,
                valor_resto_gerado=resultado.valor_resto_gerado,
            )
            exibir_pre_visualizacao_impressao(self, "Comprovante de Pagamento", html)

        self._campo_valor_pago.clear()
        self._campo_observacoes.clear()
        self._campo_data.setDate(QDate(obter_data_padrao()))
        self._carregar_contas_em_aberto(self._cliente_id)


class ReceberContaDialog(QDialog):
    """Abre :class:`ReceberContaView` como um diálogo modal.

    Usado pelo botão "Receber Conta" da Ficha do Cliente, com o cliente já
    pré-selecionado (etapa de busca pulada).
    """

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_id: str,
        nome_principal: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Receber Conta — {nome_principal}")
        self.setMinimumSize(400, 560)

        self._view = ReceberContaView(usuario_logado, cliente_pre_selecionado=(cliente_id, nome_principal))

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self._view)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)
