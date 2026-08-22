"""Componentes de interface reutilizáveis entre telas.

Contém ``ListaDinamicaWidget``, usado nos campos multivalorados e opcionais
do cadastro de cliente (nomes alternativos, telefones e compradores), e
``CampoBuscaClienteWidget``, usado em toda tela que precisa escolher um
cliente por nome (Buscar Cliente, Adicionar Compra, Receber Conta).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.controllers.cliente_controller import ClienteController
from app.services.cliente_service import ClienteBusca
from app.utils.icons import icone
from app.views.busca_cliente_worker import BuscaClienteWorker

_INTERVALO_DEBOUNCE_MS = 300


class ListaDinamicaWidget(QWidget):
    """Campo de formulário para uma lista de textos, com adicionar/remover.

    Usado sempre que um cadastro tem um campo opcional que pode ter zero
    ou várias ocorrências (ex.: nomes alternativos de um cliente).
    """

    def __init__(self, rotulo: str, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._campo_novo_item = QLineEdit()
        self._campo_novo_item.setPlaceholderText(placeholder)
        self._campo_novo_item.setMinimumHeight(34)
        self._campo_novo_item.returnPressed.connect(self._adicionar_item)

        botao_adicionar = QPushButton("Adicionar")
        botao_adicionar.setIcon(icone("PLUS"))
        botao_adicionar.setMinimumHeight(34)
        botao_adicionar.clicked.connect(self._adicionar_item)

        botao_remover = QPushButton("Remover selecionado")
        botao_remover.setIcon(icone("TRASH"))
        botao_remover.setMinimumHeight(30)
        botao_remover.clicked.connect(self._remover_item_selecionado)

        self._lista = QListWidget()
        self._lista.setMaximumHeight(110)

        layout_entrada = QHBoxLayout()
        layout_entrada.addWidget(self._campo_novo_item)
        layout_entrada.addWidget(botao_adicionar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(rotulo))
        layout.addLayout(layout_entrada)
        layout.addWidget(self._lista)
        layout.addWidget(botao_remover)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

    def _adicionar_item(self) -> None:
        texto = self._campo_novo_item.text().strip()
        if texto:
            self._lista.addItem(texto)
            self._campo_novo_item.clear()
        self._campo_novo_item.setFocus()

    def _remover_item_selecionado(self) -> None:
        linha = self._lista.currentRow()
        if linha >= 0:
            self._lista.takeItem(linha)

    def itens(self) -> list[str]:
        """Retorna todos os itens atualmente na lista."""
        return [self._lista.item(i).text() for i in range(self._lista.count())]

    def limpar(self) -> None:
        """Remove todos os itens da lista e limpa o campo de digitação."""
        self._lista.clear()
        self._campo_novo_item.clear()

    def definir_itens(self, itens: list[str]) -> None:
        """Substitui o conteúdo da lista pelos itens informados.

        Usado para pré-popular o campo com valores já existentes (ex.: ao
        abrir a edição de um cliente com nomes alternativos já cadastrados).

        Args:
            itens: Lista de textos a exibir.
        """
        self._lista.clear()
        for item in itens:
            self._lista.addItem(item)


class CampoBuscaClienteWidget(QWidget):
    """Campo de busca de cliente por nome, com debounce, thread própria e resultados.

    Reúne o padrão usado em três telas (Buscar Cliente, Adicionar Compra,
    Receber Conta): campo de texto com *debounce* de
    ``_INTERVALO_DEBOUNCE_MS``, busca executada em uma
    :class:`~app.views.busca_cliente_worker.BuscaClienteWorker` (fora da
    thread da UI), contador de sequência para descartar resultados
    desatualizados, e lista de resultados clicável.

    Emite:
        resultado_clicado: ``(cliente_id, nome_principal)`` quando um
            resultado é clicado uma vez — usado por telas que selecionam o
            cliente e seguem para um formulário (Adicionar Compra, Receber
            Conta).
        resultado_ativado: ``(cliente_id, nome_principal)`` quando um
            resultado é clicado duas vezes — usado pela tela de Buscar
            Cliente, que abre a ficha do cliente diretamente.
    """

    resultado_clicado = Signal(str, str)
    resultado_ativado = Signal(str, str)

    def __init__(
        self,
        controller: ClienteController,
        placeholder: str = "Digite o nome do cliente...",
        mostrar_pendente_confirmacao: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._mostrar_pendente_confirmacao = mostrar_pendente_confirmacao
        self._sequencia_busca = 0
        self._worker: BuscaClienteWorker | None = None

        self.campo_busca = QLineEdit()
        self.campo_busca.setPlaceholderText(placeholder)
        self.campo_busca.setMinimumHeight(38)
        self.campo_busca.textChanged.connect(self._agendar_busca)

        self._timer_debounce = QTimer(self)
        self._timer_debounce.setSingleShot(True)
        self._timer_debounce.setInterval(_INTERVALO_DEBOUNCE_MS)
        self._timer_debounce.timeout.connect(self._executar_busca)

        self.lista_resultados = QListWidget()
        self.lista_resultados.itemClicked.connect(self._item_clicado)
        self.lista_resultados.itemDoubleClicked.connect(self._item_ativado)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.campo_busca)
        layout.addWidget(self.lista_resultados)

    def focar_campo(self) -> None:
        """Move o foco do teclado para o campo de busca (ex.: ao voltar para esta página)."""
        self.campo_busca.setFocus()

    def refazer_busca(self) -> None:
        """Repete a última busca (ex.: após reabrir/editar um cliente já listado)."""
        self._executar_busca()

    def _agendar_busca(self) -> None:
        self._timer_debounce.start()

    def _executar_busca(self) -> None:
        termo = self.campo_busca.text().strip()
        self.lista_resultados.clear()
        if not termo:
            return

        self._sequencia_busca += 1
        worker = BuscaClienteWorker(self._controller, termo, self._sequencia_busca, self)
        worker.resultado_pronto.connect(self._exibir_resultados)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _exibir_resultados(self, resultados: list[ClienteBusca], sequencia: int) -> None:
        if sequencia != self._sequencia_busca:
            return  # resultado de uma busca já superada por uma digitação mais recente

        self.lista_resultados.clear()
        if not resultados:
            self.lista_resultados.addItem("Nenhum cliente encontrado.")
            return

        for resultado in resultados:
            texto = resultado.nome_principal
            if resultado.nome_alternativo_encontrado:
                texto = f"{resultado.nome_principal} ({resultado.nome_alternativo_encontrado})"
            pendente = self._mostrar_pendente_confirmacao and not resultado.confirmado
            if pendente:
                texto += "  [pendente de confirmação]"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, (resultado.id, resultado.nome_principal))
            if pendente:
                item.setForeground(QColor("red"))
            self.lista_resultados.addItem(item)

    def _item_clicado(self, item: QListWidgetItem) -> None:
        dados = item.data(Qt.ItemDataRole.UserRole)
        if not dados:
            return  # item de mensagem ("Nenhum cliente encontrado."), sem cliente associado
        self.resultado_clicado.emit(*dados)

    def _item_ativado(self, item: QListWidgetItem) -> None:
        dados = item.data(Qt.ItemDataRole.UserRole)
        if not dados:
            return
        self.resultado_ativado.emit(*dados)
