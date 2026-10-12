"""Tela de Receber Conta (PySide6).

Segue o mesmo padrão da tela Adicionar Compra: não é mais uma aba própria
da janela principal — hoje só é aberta pelo botão "Receber Conta" da
Ficha do Cliente, através de :class:`ReceberContaDialog`, com o cliente
já pré-selecionado. Mostra o total em aberto e a lista de compras
pendentes antes de confirmar o pagamento.

Dois jeitos de receber: marcar na lista as contas que o cliente quer pagar
(o valor vira a soma delas e só elas são quitadas), ou digitar o valor
(quitação FIFO, da mais antiga para a mais nova). Digitar um valor com
contas marcadas desmarca todas — os dois jeitos nunca valem ao mesmo tempo.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
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
from app.utils.formatacao import formatar_reais
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.views.componentes import TAMANHO_DIALOGO_LANCAMENTO, CampoBuscaClienteWidget


_ROTULO_VALOR_DIGITADO = "Valor pago:"
_ROTULO_VALOR_SELECIONADO = "Valor a receber (soma das contas marcadas):"
_TEXTO_SELECIONAR_TODAS = "Selecionar todas"
_TEXTO_DESMARCAR_TODAS = "Desmarcar todas"


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
        self._havia_selecao = False
        self._estado_ao_pressionar: tuple = (None, None)

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self._construir_pagina_busca())
        self._paginas.addWidget(self._construir_pagina_formulario())

        layout = QVBoxLayout()
        titulo = QLabel("Receber Conta")
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

    # -- Página 2: formulário de pagamento -----------------------------------

    def _construir_pagina_formulario(self) -> QWidget:
        pagina = QWidget()

        self._label_cliente_selecionado = QLabel()
        self._label_cliente_selecionado.setStyleSheet("font-weight: bold;")

        self._botao_trocar_cliente = QPushButton("Trocar Cliente")
        self._botao_trocar_cliente.setIcon(icone("USERS"))
        self._botao_trocar_cliente.clicked.connect(self._voltar_para_busca)

        self._lista_compras_abertas = QListWidget()
        self._lista_compras_abertas.setMaximumHeight(150)
        self._lista_compras_abertas.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._lista_compras_abertas.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._lista_compras_abertas.itemChanged.connect(self._atualizar_selecao)
        self._lista_compras_abertas.itemPressed.connect(self._guardar_estado_ao_pressionar)
        self._lista_compras_abertas.itemClicked.connect(self._alternar_ao_clicar_na_linha)

        dica_selecao = QLabel("Marque as contas que deseja receber, ou só digite o valor.")
        dica_selecao.setProperty("papel", "secundario")
        dica_selecao.setWordWrap(True)

        self._botao_selecionar_todas = QPushButton(_TEXTO_SELECIONAR_TODAS)
        self._botao_selecionar_todas.clicked.connect(self._alternar_todas)

        self._label_valor = QLabel(_ROTULO_VALOR_DIGITADO)

        self._label_total_em_aberto = QLabel()
        self._label_total_em_aberto.setProperty("papel", "subtitulo")

        self._campo_valor_pago = QLineEdit()
        self._campo_valor_pago.setPlaceholderText("Ex.: 25,50")
        self._campo_valor_pago.setMinimumHeight(36)
        # textEdited só dispara quando é o usuário que digita (não no setText).
        self._campo_valor_pago.textEdited.connect(self._ao_digitar_valor)

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
        layout.addWidget(dica_selecao)
        layout.addWidget(self._botao_selecionar_todas)
        layout.addWidget(self._lista_compras_abertas)
        layout.addWidget(self._label_total_em_aberto)
        layout.addWidget(self._label_valor)
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
        # Sem sinais enquanto a lista é remontada: cada item novo dispararia
        # itemChanged e recalcularia a seleção no meio do caminho.
        self._lista_compras_abertas.blockSignals(True)
        self._lista_compras_abertas.clear()
        try:
            ficha = self._cliente_controller.ficha(cliente_id)
        except Exception:
            logger.exception("Falha ao carregar contas em aberto do cliente %s.", cliente_id)
            self._label_total_em_aberto.setText("Total em aberto: R$ 0,00")
            self._lista_compras_abertas.blockSignals(False)
            self._atualizar_selecao()
            return

        compras_abertas = sorted(
            (c for c in ficha.compras if c.status != "quitada"), key=lambda c: c.data
        )
        if not compras_abertas:
            self._lista_compras_abertas.addItem("Nenhuma conta em aberto.")
        for compra in compras_abertas:
            rotulo_resto = " [Resto]" if compra.eh_resto else ""
            data_formatada = compra.data.strftime("%d/%m/%Y")
            item = QListWidgetItem(f"{formatar_reais(compra.valor)} — {data_formatada}{rotulo_resto}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, (compra.id, compra.valor))
            self._lista_compras_abertas.addItem(item)
        self._lista_compras_abertas.blockSignals(False)

        self._label_total_em_aberto.setText(f"Total em aberto: {formatar_reais(ficha.total_em_aberto)}")
        self._atualizar_selecao()

    def _guardar_estado_ao_pressionar(self, item: QListWidgetItem) -> None:
        self._estado_ao_pressionar = (item, item.checkState())

    def _alternar_ao_clicar_na_linha(self, item: QListWidgetItem) -> None:
        """Clicar em qualquer ponto da linha marca/desmarca, não só na caixinha.

        Se o clique foi na própria caixinha, o Qt já alternou o estado
        entre o pressionar e o soltar — aí não há nada a fazer.
        """
        item_pressionado, estado_anterior = self._estado_ao_pressionar
        self._estado_ao_pressionar = (None, None)
        if item.data(Qt.ItemDataRole.UserRole) is None:
            return  # linha "Nenhuma conta em aberto."
        if item is item_pressionado and item.checkState() == estado_anterior:
            marcado = estado_anterior == Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Unchecked if marcado else Qt.CheckState.Checked)

    def _compras_marcadas(self) -> list[tuple[str, Decimal]]:
        """(id, valor) de cada conta marcada na lista."""
        marcadas = []
        for indice in range(self._lista_compras_abertas.count()):
            item = self._lista_compras_abertas.item(indice)
            dado = item.data(Qt.ItemDataRole.UserRole)
            if dado is not None and item.checkState() == Qt.CheckState.Checked:
                marcadas.append(dado)
        return marcadas

    def _itens_de_conta(self) -> list[QListWidgetItem]:
        """Os itens da lista que são contas (fora a linha "Nenhuma conta em aberto.")."""
        itens = [self._lista_compras_abertas.item(i) for i in range(self._lista_compras_abertas.count())]
        return [item for item in itens if item.data(Qt.ItemDataRole.UserRole) is not None]

    def _marcar_todas(self, marcar: bool) -> None:
        """Marca/desmarca todas de uma vez, sem recalcular a cada item."""
        estado = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        self._lista_compras_abertas.blockSignals(True)
        for item in self._itens_de_conta():
            item.setCheckState(estado)
        self._lista_compras_abertas.blockSignals(False)

    def _alternar_todas(self) -> None:
        itens = self._itens_de_conta()
        todas_marcadas = bool(itens) and len(self._compras_marcadas()) == len(itens)
        self._marcar_todas(not todas_marcadas)
        self._atualizar_selecao()

    def _ao_digitar_valor(self, _texto: str) -> None:
        """Digitar um valor desmarca as contas: passa a valer a quitação pelo valor."""
        if not self._havia_selecao:
            return
        self._marcar_todas(False)
        self._havia_selecao = False  # o que está no campo agora é o que o usuário digitou
        self._atualizar_selecao()

    def _atualizar_selecao(self, _item: QListWidgetItem | None = None) -> None:
        """Com contas marcadas, o valor a receber é a soma delas."""
        itens = self._itens_de_conta()
        marcadas = self._compras_marcadas()
        if marcadas:
            total = sum((valor for _id, valor in marcadas), Decimal("0"))
            self._campo_valor_pago.setText(f"{total:.2f}".replace(".", ","))
            self._label_valor.setText(_ROTULO_VALOR_SELECIONADO)
            self._havia_selecao = True
        else:
            if self._havia_selecao:
                self._campo_valor_pago.clear()  # era a soma das marcadas, não um valor digitado
            self._label_valor.setText(_ROTULO_VALOR_DIGITADO)
            self._havia_selecao = False

        self._botao_selecionar_todas.setEnabled(bool(itens))
        self._botao_selecionar_todas.setText(
            _TEXTO_DESMARCAR_TODAS if itens and len(marcadas) == len(itens) else _TEXTO_SELECIONAR_TODAS
        )

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
        ids_marcados = [compra_id for compra_id, _valor in self._compras_marcadas()]

        try:
            resultado = self._pagamento_controller.registrar(
                self._cliente_id, valor_pago, data_pagamento, observacoes, ids_marcados or None
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
                f"Pagamento de {formatar_reais(resultado.valor_pago)} registrado.\n\n"
                f"Foi gerada uma nova conta 'Resto' de {formatar_reais(resultado.valor_resto_gerado)}."
            )
        elif ids_marcados:
            quantidade = len(ids_marcados)
            texto_contas = "1 conta quitada" if quantidade == 1 else f"{quantidade} contas quitadas"
            mensagem = f"Pagamento de {formatar_reais(resultado.valor_pago)} registrado. {texto_contas}."
        else:
            mensagem = f"Pagamento de {formatar_reais(resultado.valor_pago)} registrado. Conta quitada."

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
    pré-selecionado (etapa de busca pulada) — e também pelo atalho global
    "+ Novo Lançamento" (``app.views.novo_lancamento_dialog``), sem
    cliente pré-selecionado (``cliente_id``/``nome_principal`` omitidos),
    caso em que a própria :class:`ReceberContaView` cuida da busca.
    """

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_id: str | None = None,
        nome_principal: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Receber Conta — {nome_principal}" if nome_principal else "Receber Conta")
        self.setMinimumSize(*TAMANHO_DIALOGO_LANCAMENTO)
        self.resize(*TAMANHO_DIALOGO_LANCAMENTO)

        pre_selecionado = (cliente_id, nome_principal) if cliente_id else None
        self._view = ReceberContaView(usuario_logado, cliente_pre_selecionado=pre_selecionado)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self._view)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)
