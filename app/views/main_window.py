"""Janela principal da aplicação (PySide6).

Mostra quem está logado, o perfil de acesso e as abas do sistema
(Cadastrar Cliente, Buscar Cliente, Adicionar Compra, Receber Conta e,
para Administradores, Usuários, Backup, Histórico e Relatórios e
Configurações). Também dispara, em segundo plano, a verificação do backup
automático diário, e registra os atalhos de teclado globais do sistema.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.services import auth_service, backup_service, xml_importacao_service
from app.services.auth_service import UsuarioAutenticado
from app.views.adicionar_compra_view import AdicionarCompraView
from app.views.backup_view import BackupView
from app.views.buscar_cliente_view import BuscarClienteView
from app.views.cadastrar_cliente_view import CadastrarClienteView
from app.views.configuracoes_view import ConfiguracoesView
from app.views.painel_inicio_view import PainelInicioView
from app.views.receber_conta_view import ReceberContaView
from app.views.relatorio_view import RelatorioView
from app.views.usuario_view import UsuarioView
from app.views.xml_importacao_view import ImportarXmlDialog
from app.utils.icons import icone

_INTERVALO_VERIFICACAO_BACKUP_MS = 60 * 60 * 1000  # verifica a cada hora


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


class MainWindow(QMainWindow):
    """Janela principal do sistema, exibida após login bem-sucedido."""

    def __init__(self, usuario: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario = usuario
        self._sessao_encerrada = False

        self.setWindowTitle("Sistema de Gestão de Fiado")
        self.resize(1024, 700)

        cabecalho = QLabel(
            f"Logado como: {usuario.nome}  —  Perfil: {usuario.perfil.value.capitalize()}"
        )
        cabecalho.setStyleSheet("padding: 6px; font-weight: bold;")

        botao_sair = QPushButton("Sair")
        botao_sair.setIcon(icone("LOGOUT"))
        botao_sair.clicked.connect(self._sair)

        abas = QTabWidget()
        abas.addTab(CadastrarClienteView(usuario), icone("USER_PLUS"), "Cadastrar Cliente")
        abas.addTab(BuscarClienteView(usuario), icone("SEARCH"), "Buscar Cliente")
        abas.addTab(AdicionarCompraView(usuario), icone("SHOPPING_CART_PLUS"), "Adicionar Compra")
        abas.addTab(ReceberContaView(usuario), icone("CASH_BANKNOTE"), "Receber Conta")

        if usuario.eh_administrador:
            abas.addTab(UsuarioView(usuario), icone("USERS"), "Usuários")
            abas.addTab(BackupView(usuario), icone("DATABASE"), "Backup")
            abas.addTab(RelatorioView(usuario), icone("CHART_BAR"), "Histórico e Relatórios")
            abas.addTab(ConfiguracoesView(usuario), icone("SETTINGS"), "Configurações")
            abas.insertTab(0, PainelInicioView(usuario), icone("HOME"), "Início")
            abas.setCurrentIndex(0)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(cabecalho)
        layout.addWidget(abas)
        layout.addWidget(botao_sair)
        self.setCentralWidget(container)

        self._worker_backup_automatico: _BackupAutomaticoWorker | None = None
        self._timer_backup_automatico = QTimer(self)
        self._timer_backup_automatico.setInterval(_INTERVALO_VERIFICACAO_BACKUP_MS)
        self._timer_backup_automatico.timeout.connect(self._verificar_backup_automatico)
        self._timer_backup_automatico.start()
        self._verificar_backup_automatico()  # também verifica logo ao abrir o sistema

        self._atalho_novo_cliente = QShortcut(QKeySequence("Ctrl+N"), self)
        self._atalho_novo_cliente.activated.connect(lambda: abas.setCurrentIndex(0))

        self._atalho_buscar_cliente = QShortcut(QKeySequence("Ctrl+F"), self)
        self._atalho_buscar_cliente.activated.connect(lambda: abas.setCurrentIndex(1))

        self._atalho_sair = QShortcut(QKeySequence("Ctrl+Q"), self)
        self._atalho_sair.activated.connect(self.close)

        self._worker_verificar_xml: _VerificarXmlWorker | None = None
        self._verificar_xmls_pendentes()

    @staticmethod
    def _aba_em_construcao(nome: str) -> QWidget:
        """Cria um widget placeholder para uma aba ainda não implementada."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(f"'{nome}' será implementada em uma próxima etapa.")
        label.setStyleSheet("padding: 24px; color: #666;")
        layout.addWidget(label)
        return widget

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
