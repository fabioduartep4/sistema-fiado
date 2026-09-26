"""Janela principal da aplicação (PySide6).

Navegação em sidebar lateral fixa (substitui as antigas abas horizontais):
Início, Clientes, Saldos, Histórico, Backups e Configurações para
Administrador — Funcionário só vê Clientes (que já reúne busca e
cadastro, ver ``app.views.clientes_view``; "Adicionar Compra"/"Receber
Conta" não são mais telas próprias — abrem, com o cliente já
pré-selecionado, pelos botões da Ficha do Cliente, ou sem cliente
pré-selecionado através do atalho global "+ Novo Lançamento" no
cabeçalho, ver ``app.views.novo_lancamento_dialog``).

Também dispara, em segundo plano, a verificação do backup automático
diário, e registra os atalhos de teclado globais do sistema.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.services import auth_service, backup_service, xml_importacao_service
from app.services.auth_service import UsuarioAutenticado
from app.views.backup_view import BackupView
from app.views.clientes_view import ClientesView
from app.views.configuracoes_view import ConfiguracoesView
from app.views.novo_lancamento_dialog import NovoLancamentoDialog
from app.views.painel_inicio_view import PainelInicioView
from app.views.relatorio_view import RelatorioView
from app.views.saldos_view import SaldosView
from app.views.xml_importacao_view import ImportarXmlDialog
from app.utils.icons import icone

_INTERVALO_VERIFICACAO_BACKUP_MS = 60 * 60 * 1000  # verifica a cada hora
_LARGURA_SIDEBAR = 230


class _BackupAutomaticoWorker(QThread):
    """Executa a verificação/backup automático diário fora da thread da UI."""

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            backup_service.verificar_e_executar_backup_automatico_se_necessario()
        except Exception:
            logger.exception("Falha ao executar a verificação de backup automático diário.")


class _VerificarXmlWorker(QThread):
    """Verifica, fora da thread da UI, se há XMLs de venda a prazo pendentes."""

    candidatos_encontrados = Signal(int)

    def __init__(self, usuario_logado: UsuarioAutenticado, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            candidatos = xml_importacao_service.listar_candidatos_importacao(self._usuario_logado)
            self.candidatos_encontrados.emit(len(candidatos))
        except Exception:
            logger.exception("Falha ao verificar XMLs pendentes de importação.")
            self.candidatos_encontrados.emit(0)

        # Depois da listagem acima, que já atualizou o índice de XMLs.
        try:
            xml_importacao_service.preencher_data_hora_emissao_faltante()
        except Exception:
            logger.exception("Falha ao preencher a data/hora de emissão de compras importadas de XML.")


class MainWindow(QMainWindow):
    """Janela principal do sistema, exibida após login bem-sucedido."""

    def __init__(self, usuario: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario = usuario
        self._sessao_encerrada = False
        self._botoes_nav: list[QPushButton] = []

        self.setWindowTitle("Sistema de Gestão de Fiado")
        self.resize(1100, 720)

        self._stack = QStackedWidget()

        # Guardadas em variáveis (não por índice) pros atalhos de teclado e
        # pra troca de página no clique de cada botão da sidebar.
        view_clientes = ClientesView(usuario)

        sidebar = self._construir_sidebar(usuario, view_clientes)

        cabecalho = self._construir_cabecalho()

        area_conteudo = QWidget()
        layout_conteudo = QVBoxLayout(area_conteudo)
        layout_conteudo.setContentsMargins(0, 0, 0, 0)
        layout_conteudo.setSpacing(0)
        layout_conteudo.addWidget(cabecalho)
        layout_conteudo.addWidget(self._stack)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(sidebar)
        layout.addWidget(area_conteudo, stretch=1)
        self.setCentralWidget(container)

        self._worker_backup_automatico: _BackupAutomaticoWorker | None = None
        self._timer_backup_automatico = QTimer(self)
        self._timer_backup_automatico.setInterval(_INTERVALO_VERIFICACAO_BACKUP_MS)
        self._timer_backup_automatico.timeout.connect(self._verificar_backup_automatico)
        self._timer_backup_automatico.start()
        self._verificar_backup_automatico()  # também verifica logo ao abrir o sistema

        self._atalho_novo_cliente = QShortcut(QKeySequence("Ctrl+N"), self)
        self._atalho_novo_cliente.activated.connect(view_clientes.abrir_novo_cliente)

        self._atalho_buscar_cliente = QShortcut(QKeySequence("Ctrl+F"), self)
        self._atalho_buscar_cliente.activated.connect(lambda: self._focar_clientes(view_clientes))

        self._atalho_sair = QShortcut(QKeySequence("Ctrl+Q"), self)
        self._atalho_sair.activated.connect(self.close)

        self._worker_verificar_xml: _VerificarXmlWorker | None = None
        self._verificar_xmls_pendentes()

    # -- Sidebar ---------------------------------------------------------------

    def _construir_sidebar(self, usuario: UsuarioAutenticado, view_clientes: ClientesView) -> QFrame:
        sidebar = QFrame()
        sidebar.setProperty("papel", "sidebar")
        sidebar.setFixedWidth(_LARGURA_SIDEBAR)

        logo = QLabel("FIADO")
        logo.setProperty("papel", "titulo")
        logo.setStyleSheet("padding: 16px 14px 8px 14px;")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 0, 10, 14)
        layout.setSpacing(2)
        layout.addWidget(logo)

        # Início exige Administrador (ver PainelController.obter_painel) —
        # a própria PainelInicioView só pode ser CONSTRUÍDA por um admin,
        # então nem o widget é criado se o perfil for Funcionário (ao
        # contrário dos outros itens, aqui não basta só esconder o botão
        # depois: construir a view já dispara a consulta e derrubaria
        # com PermissaoNegadaError pra quem não é admin).
        if usuario.eh_administrador:
            self._adicionar_item_nav(layout, "HOME", "Início", PainelInicioView(usuario))

        self._botao_clientes = self._adicionar_item_nav(layout, "USERS", "Clientes", view_clientes)

        if usuario.eh_administrador:
            self._adicionar_item_nav(layout, "REPORT_MONEY", "Saldos", SaldosView(usuario))
            self._adicionar_item_nav(layout, "CHART_BAR", "Histórico", RelatorioView(usuario))
            self._adicionar_item_nav(layout, "DATABASE", "Backups", BackupView(usuario))
            self._adicionar_item_nav(layout, "SETTINGS", "Configurações", ConfiguracoesView(usuario))

        layout.addStretch()

        separador = QFrame()
        separador.setFrameShape(QFrame.Shape.HLine)
        layout.addWidget(separador)

        usuario_nome = QLabel(usuario.nome)
        usuario_nome.setStyleSheet("padding: 10px 6px 0 6px; font-weight: 600;")
        usuario_perfil = QLabel(usuario.perfil.value.capitalize())
        usuario_perfil.setProperty("papel", "secundario")
        usuario_perfil.setStyleSheet("padding: 0 6px 8px 6px;")
        layout.addWidget(usuario_nome)
        layout.addWidget(usuario_perfil)

        botao_sair = QPushButton("Sair")
        botao_sair.setIcon(icone("LOGOUT"))
        botao_sair.clicked.connect(self._sair)
        layout.addWidget(botao_sair)

        # A primeira aba disponível abre selecionada (Início pra
        # Administrador, Clientes pra Funcionário — não há Início pra
        # quem não é admin).
        if self._botoes_nav:
            self._selecionar_item_nav(self._botoes_nav[0])

        return sidebar

    def _adicionar_item_nav(
        self, layout: QVBoxLayout, nome_icone: str, rotulo: str, pagina: QWidget
    ) -> QPushButton:
        """Adiciona uma página ao stack e seu botão correspondente na sidebar.

        Quem chama decide se/quando a página deve ser construída (ex.:
        só dentro de ``if usuario.eh_administrador:``) — construir o
        widget já pode disparar consultas que exigem permissão, então
        não adianta filtrar só aqui dentro.
        """
        indice = self._stack.addWidget(pagina)
        botao = QPushButton(rotulo)
        botao.setIcon(icone(nome_icone))
        botao.setProperty("papel", "item_sidebar")
        botao.setProperty("selecionado", False)
        botao.clicked.connect(lambda _checked=False, i=indice: self._ir_para_pagina(i))
        layout.addWidget(botao)
        self._botoes_nav.append(botao)
        return botao

    def _ir_para_pagina(self, indice: int) -> None:
        self._stack.setCurrentIndex(indice)
        for i, botao in enumerate(self._botoes_nav):
            botao.setProperty("selecionado", i == indice)
            botao.style().unpolish(botao)
            botao.style().polish(botao)

    def _selecionar_item_nav(self, botao: QPushButton) -> None:
        self._ir_para_pagina(self._botoes_nav.index(botao))

    def _focar_clientes(self, view_clientes: ClientesView) -> None:
        self._selecionar_item_nav(self._botao_clientes)
        view_clientes.focar_busca()

    # -- Cabeçalho (ações globais) ----------------------------------------------

    def _construir_cabecalho(self) -> QWidget:
        cabecalho = QWidget()
        layout = QHBoxLayout(cabecalho)
        layout.setContentsMargins(20, 14, 20, 14)

        botao_novo_lancamento = QPushButton("+ Novo Lançamento")
        botao_novo_lancamento.setProperty("importancia", "primaria")
        botao_novo_lancamento.clicked.connect(self._abrir_novo_lancamento)

        botao_sino = QPushButton()
        botao_sino.setIcon(icone("BELL"))
        botao_sino.setToolTip("Notificações (em breve)")
        botao_sino.setEnabled(False)
        botao_sino.setFlat(True)

        layout.addStretch()
        layout.addWidget(botao_novo_lancamento)
        layout.addWidget(botao_sino)
        return cabecalho

    def _abrir_novo_lancamento(self) -> None:
        dialogo = NovoLancamentoDialog(self._usuario, self)
        dialogo.exec()

    def _sair(self) -> None:
        """Fecha a janela principal (o logout é registrado em ``closeEvent``,
        cobrindo também o atalho Ctrl+Q e o botão "X" da janela)."""
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (nome exigido pelo Qt)
        """Garante que o logout seja registrado ao fechar a janela, por
        qualquer via (botão Sair, atalho Ctrl+Q, ou o "X" da janela)."""
        if not self._sessao_encerrada:
            self._sessao_encerrada = True
            auth_service.encerrar_sessao(self._usuario)
        super().closeEvent(event)

    def _verificar_backup_automatico(self) -> None:
        """Dispara, em segundo plano, a checagem do backup automático diário.

        Não bloqueia a interface nem interrompe o usuário: qualquer falha
        (ex.: 'pg_dump' não encontrado) é apenas registrada no log de
        arquivo (ver ``_BackupAutomaticoWorker``).
        """
        worker = _BackupAutomaticoWorker(self)
        worker.finished.connect(worker.deleteLater)
        self._worker_backup_automatico = worker
        worker.start()

    def _verificar_xmls_pendentes(self) -> None:
        """Dispara, em segundo plano, a checagem de XMLs de venda a prazo pendentes.

        Se encontrar algum, pergunta ao usuário se deseja importar agora
        (ver ``_perguntar_importar_xml``). Não bloqueia a interface.
        """
        worker = _VerificarXmlWorker(self._usuario, self)
        worker.candidatos_encontrados.connect(self._perguntar_importar_xml)
        worker.finished.connect(worker.deleteLater)
        self._worker_verificar_xml = worker
        worker.start()

    def _perguntar_importar_xml(self, quantidade: int) -> None:
        if quantidade <= 0:
            return

        resposta = QMessageBox.question(
            self,
            "Importar XMLs",
            f"Foram encontrados {quantidade} XML(s) de venda a prazo ainda não importados. "
            "Deseja importar agora?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        dialogo = ImportarXmlDialog(self._usuario, self)
        dialogo.exec()
