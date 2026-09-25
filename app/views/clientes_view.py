"""Tela de Clientes (PySide6).

Tela única para buscar, listar e cadastrar clientes — reúne o que antes
eram duas abas separadas ("Buscar Cliente" e "Cadastrar Cliente"; o
cadastro agora abre como diálogo, ver :class:`CadastrarClienteDialog` em
``app.views.cadastrar_cliente_view``). Mostra todo cliente ativo (não só
resultados de busca), com saldo/limite/status já calculados, e filtros
rápidos por situação da conta.

Clicar numa linha abre a Ficha do Cliente (``app.views.ficha_cliente_view``,
continua diálogo modal).

Funcionário vê uma versão reduzida: só a busca, sem filtros e sem a lista
de saldos — os resultados mostram apenas código e nome, e o saldo só
aparece ao abrir a ficha do cliente.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import ClienteStatusResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.tabelas import aplicar_estado_vazio, ajustar_colunas
from app.views.cadastrar_cliente_view import CadastrarClienteDialog
from app.views.ficha_cliente_view import FichaClienteView

_ATRASO_DIAS_PADRAO = 30

# Espera depois da última tecla digitada antes de refazer a busca — evita
# refazer a consulta a cada letra enquanto o usuário ainda está digitando.
_DEBOUNCE_BUSCA_MS = 250

_FILTROS = ["Todos", "Com saldo", "Em atraso", "Acima do limite"]


class ClientesView(QWidget):
    """Tela de gestão de clientes: busca, filtros, listagem e cadastro."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._controller = ClienteController(usuario_logado)
        self._filtro_atual = "Todos"
        self._eh_administrador = usuario_logado.eh_administrador

        titulo = QLabel("Clientes")
        titulo.setProperty("papel", "titulo")
        subtitulo = QLabel(
            "Gerencie clientes, limites e saldos."
            if self._eh_administrador
            else "Busque o cliente e abra a ficha para ver o saldo."
        )
        subtitulo.setProperty("papel", "secundario")

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("Buscar por nome...")
        self._campo_busca.setMinimumHeight(38)
        self._timer_busca = QTimer(self)
        self._timer_busca.setSingleShot(True)
        self._timer_busca.setInterval(_DEBOUNCE_BUSCA_MS)
        self._timer_busca.timeout.connect(self._carregar)
        self._campo_busca.textChanged.connect(lambda _texto: self._timer_busca.start())

        botao_novo_cliente = QPushButton("+ Novo Cliente")
        botao_novo_cliente.setIcon(icone("USER_PLUS"))
        botao_novo_cliente.setMinimumHeight(38)
        botao_novo_cliente.setProperty("importancia", "primaria")
        botao_novo_cliente.clicked.connect(self.abrir_novo_cliente)

        layout_busca = QHBoxLayout()
        layout_busca.addWidget(self._campo_busca)
        layout_busca.addWidget(botao_novo_cliente)

        barra_filtros = QWidget()
        if not self._eh_administrador:
            barra_filtros.hide()
        layout_filtros = QHBoxLayout(barra_filtros)
        layout_filtros.setContentsMargins(0, 0, 0, 0)
        self._grupo_filtros = QButtonGroup(self)
        self._grupo_filtros.setExclusive(True)
        for filtro in _FILTROS:
            botao = QPushButton(filtro)
            botao.setCheckable(True)
            botao.setChecked(filtro == "Todos")
            botao.clicked.connect(lambda _checked=False, f=filtro: self._selecionar_filtro(f))
            self._grupo_filtros.addButton(botao)
            layout_filtros.addWidget(botao)

        self._campo_dias_atraso = QSpinBox()
        self._campo_dias_atraso.setRange(1, 365)
        self._campo_dias_atraso.setValue(_ATRASO_DIAS_PADRAO)
        self._campo_dias_atraso.setSuffix(" dias")
        self._campo_dias_atraso.setVisible(False)
        self._campo_dias_atraso.valueChanged.connect(lambda _valor: self._carregar())
        layout_filtros.addWidget(QLabel("Considerar atraso com mais de:"))
        self._rotulo_dias_atraso = layout_filtros.itemAt(layout_filtros.count() - 1).widget()
        self._rotulo_dias_atraso.setVisible(False)
        layout_filtros.addWidget(self._campo_dias_atraso)
        layout_filtros.addStretch()

        if self._eh_administrador:
            self._tabela = QTableWidget(0, 5)
            self._tabela.setHorizontalHeaderLabels(["Cliente", "Telefone", "Saldo", "Limite", "Status"])
        else:
            self._tabela = QTableWidget(0, 2)
            self._tabela.setHorizontalHeaderLabels(["Cliente", "Código"])
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela.cellDoubleClicked.connect(self._abrir_ficha_da_linha)
        ajustar_colunas(self._tabela, 0)  # Cliente

        self._label_vazio = QLabel("Nenhum cliente encontrado.")
        self._label_vazio.setProperty("papel", "secundario")
        self._label_vazio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label_vazio.setVisible(False)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(subtitulo)
        layout.addLayout(layout_busca)
        layout.addWidget(barra_filtros)
        layout.addWidget(self._tabela)
        layout.addWidget(self._label_vazio)
        self.setLayout(layout)

        self._carregar()

    def _selecionar_filtro(self, filtro: str) -> None:
        self._filtro_atual = filtro
        mostrar_dias = filtro == "Em atraso"
        self._campo_dias_atraso.setVisible(mostrar_dias)
        self._rotulo_dias_atraso.setVisible(mostrar_dias)
        self._carregar()

    def _carregar(self) -> None:
        if not self._eh_administrador:
            self._carregar_busca_funcionario()
            return

        try:
            clientes = self._controller.listar_com_status(
                termo=self._campo_busca.text(), dias_atraso=self._campo_dias_atraso.value()
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar os clientes", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de clientes.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar os clientes.")
            return

        clientes = self._aplicar_filtro(clientes)

        self._tabela.setRowCount(len(clientes))
        for linha, cliente in enumerate(clientes):
            nome = cliente.nome_principal
            if not cliente.confirmado:
                nome += " (pendente de confirmação)"
            self._tabela.setItem(linha, 0, QTableWidgetItem(nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(cliente.telefone or "-"))
            self._tabela.setItem(linha, 2, QTableWidgetItem(f"R$ {cliente.saldo:.2f}"))
            texto_limite = f"R$ {cliente.limite_fiado:.2f}" if cliente.limite_fiado is not None else "-"
            self._tabela.setItem(linha, 3, QTableWidgetItem(texto_limite))
            item_status = QTableWidgetItem(self._texto_status(cliente))
            self._tabela.setItem(linha, 4, item_status)
            self._tabela.item(linha, 0).setData(Qt.ItemDataRole.UserRole, cliente.id)

        self._label_vazio.setText("Nenhum cliente encontrado.")
        aplicar_estado_vazio(self._tabela, self._label_vazio)

    def _carregar_busca_funcionario(self) -> None:
        termo = self._campo_busca.text().strip()
        if not termo:
            self._tabela.setRowCount(0)
            self._label_vazio.setText("Digite o nome do cliente para buscar.")
            aplicar_estado_vazio(self._tabela, self._label_vazio)
            return

        try:
            clientes = self._controller.buscar(termo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível buscar os clientes", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao buscar clientes.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível buscar os clientes.")
            return

        self._tabela.setRowCount(len(clientes))
        for linha, cliente in enumerate(clientes):
            nome = cliente.nome_principal
            if cliente.nome_alternativo_encontrado:
                nome += f" (também: {cliente.nome_alternativo_encontrado})"
            if not cliente.confirmado:
                nome += " (pendente de confirmação)"
            item_nome = QTableWidgetItem(nome)
            item_nome.setData(Qt.ItemDataRole.UserRole, cliente.id)
            self._tabela.setItem(linha, 0, item_nome)
            self._tabela.setItem(linha, 1, QTableWidgetItem(str(cliente.id_visivel)))

        self._label_vazio.setText("Nenhum cliente encontrado.")
        aplicar_estado_vazio(self._tabela, self._label_vazio)

    def _aplicar_filtro(self, clientes: list[ClienteStatusResumo]) -> list[ClienteStatusResumo]:
        if self._filtro_atual == "Com saldo":
            return [c for c in clientes if c.saldo > 0]
        if self._filtro_atual == "Em atraso":
            return [c for c in clientes if c.atrasado]
        if self._filtro_atual == "Acima do limite":
            return [c for c in clientes if c.excedido]
        return clientes

    @staticmethod
    def _texto_status(cliente: ClienteStatusResumo) -> str:
        if cliente.excedido:
            return "⚠ Excedido"
        if cliente.saldo > 0:
            return "Normal"
        return "-"

    def _abrir_ficha_da_linha(self, linha: int, _coluna: int) -> None:
        item = self._tabela.item(linha, 0)
        if item is None:
            return
        cliente_id = item.data(Qt.ItemDataRole.UserRole)
        dialogo = FichaClienteView(self._usuario_logado, cliente_id, self)
        dialogo.exec()
        self._carregar()  # cliente pode ter sido editado/excluído/recebido pagamento

    def abrir_novo_cliente(self) -> None:
        """Abre o diálogo de cadastro de cliente (botão "+ Novo Cliente" ou Ctrl+N)."""
        dialogo = CadastrarClienteDialog(self._usuario_logado, self)
        dialogo.exec()
        self._carregar()

    def focar_busca(self) -> None:
        """Foca o campo de busca (atalho Ctrl+F, acionado pela janela principal)."""
        self._campo_busca.setFocus()
        self._carregar()
