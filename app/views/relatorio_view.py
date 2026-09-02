"""Tela de Histórico e Relatórios (PySide6).

Visível apenas para Administrador. Reúne três sub-abas: Histórico de
Alterações (auditoria), Log de Erros e Saldo em Aberto (com exportação
para CSV/Excel).

``LembreteWhatsAppDialog`` continua definido aqui (usado também pela tela
de Início, que reaproveita esta classe) mesmo com a antiga sub-aba
"Lembretes" tendo sido movida para lá — ver ``app.views.painel_inicio_view``,
seção "Clientes com Maior Atraso".
"""

from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.relatorio_controller import RelatorioController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.text_normalizer import normalizar_telefone
from app.utils.whatsapp import montar_link_whatsapp

_ENTIDADES_FILTRO = ["Todas", "Cliente", "Compra", "Pagamento", "Usuario"]


class LembreteWhatsAppDialog(QDialog):
    """Diálogo de revisão da mensagem de lembrete antes de abrir no WhatsApp.

    Não envia nada sozinho: mostra a mensagem já pronta (montada pelo
    chamador — ver ``app.utils.whatsapp``), deixa o usuário editar e, ao
    confirmar, abre o WhatsApp (app ou web) com a conversa já preenchida —
    o envio em si continua sendo uma ação manual do usuário dentro do
    WhatsApp. Não depende de nenhum tipo de "resumo" específico (saldo em
    atraso, limite excedido, etc.) — cada tela que o abre monta a mensagem
    do jeito que fizer sentido para o motivo do lembrete.
    """

    def __init__(
        self,
        nome_cliente: str,
        telefone: str | None,
        mensagem_inicial: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Lembrete — {nome_cliente}")
        self.setMinimumSize(420, 280)
        self._telefone_normalizado = normalizar_telefone(telefone or "")

        self._campo_mensagem = QTextEdit()
        self._campo_mensagem.setPlainText(mensagem_inicial)

        botao_abrir = QPushButton("Abrir no WhatsApp")
        botao_abrir.setIcon(icone("BRAND_WHATSAPP"))
        botao_abrir.setMinimumHeight(42)
        botao_abrir.clicked.connect(self._abrir_whatsapp)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Telefone: {telefone or 'não cadastrado'}"))
        layout.addWidget(QLabel("Mensagem (edite se quiser antes de abrir o WhatsApp):"))
        layout.addWidget(self._campo_mensagem)
        layout.addWidget(botao_abrir)
        layout.addWidget(botao_cancelar)
        self.setLayout(layout)

    def _abrir_whatsapp(self) -> None:
        mensagem = self._campo_mensagem.toPlainText().strip()
        if not mensagem:
            QMessageBox.warning(self, "Mensagem vazia", "Escreva uma mensagem antes de continuar.")
            return

        link = montar_link_whatsapp(self._telefone_normalizado, mensagem)
        QDesktopServices.openUrl(QUrl(link))
        self.accept()


class RelatorioView(QWidget):
    """Tela com as sub-abas de histórico e relatórios."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = RelatorioController(usuario_logado)

        abas = QTabWidget()
        abas.addTab(self._construir_aba_historico(), "Histórico de Alterações")
        abas.addTab(self._construir_aba_log_erros(), "Log de Erros")
        abas.addTab(self._construir_aba_saldo_em_aberto(), "Saldo em Aberto")

        titulo = QLabel("Histórico e Relatórios")
        titulo.setProperty("papel", "titulo")

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(abas)
        self.setLayout(layout)

    # -- Sub-aba: Histórico de Alterações ------------------------------------

    def _construir_aba_historico(self) -> QWidget:
        pagina = QWidget()

        self._campo_filtro_entidade = QComboBox()
        self._campo_filtro_entidade.addItems(_ENTIDADES_FILTRO)
        self._campo_filtro_entidade.currentTextChanged.connect(self._carregar_historico)

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_historico)

        self._tabela_historico = QTableWidget(0, 6)
        self._tabela_historico.setHorizontalHeaderLabels(
            ["Data/Hora", "Entidade", "Ação", "Usuário", "De", "Para"]
        )
        self._tabela_historico.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout_filtro = QHBoxLayout()
        layout_filtro.addWidget(QLabel("Entidade:"))
        layout_filtro.addWidget(self._campo_filtro_entidade)
        layout_filtro.addStretch()
        layout_filtro.addWidget(botao_atualizar)

        layout = QVBoxLayout(pagina)
        layout.addLayout(layout_filtro)
        layout.addWidget(self._tabela_historico)

        self._carregar_historico()
        return pagina

    def _carregar_historico(self) -> None:
        entidade = self._campo_filtro_entidade.currentText()
        filtro = None if entidade == "Todas" else entidade

        try:
            registros = self._controller.listar_historico(entidade=filtro)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o histórico", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o histórico de alterações.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o histórico.")
            return

        self._tabela_historico.setRowCount(len(registros))
        for linha, registro in enumerate(registros):
            valores = [
                registro.data_hora.strftime("%d/%m/%Y %H:%M"),
                registro.entidade,
                registro.acao,
                registro.usuario_nome,
                registro.valor_antigo or "-",
                registro.valor_novo or "-",
            ]
            for coluna, valor in enumerate(valores):
                self._tabela_historico.setItem(linha, coluna, QTableWidgetItem(valor))

    # -- Sub-aba: Log de Erros -----------------------------------------------

    def _construir_aba_log_erros(self) -> QWidget:
        pagina = QWidget()

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_log_erros)

        self._tabela_log_erros = QTableWidget(0, 3)
        self._tabela_log_erros.setHorizontalHeaderLabels(["Data/Hora", "Usuário", "Erro"])
        self._tabela_log_erros.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_log_erros.itemDoubleClicked.connect(self._exibir_stacktrace)

        layout = QVBoxLayout(pagina)
        layout.addWidget(QLabel("Dê duplo clique em um erro para ver o stacktrace completo."))
        layout.addWidget(botao_atualizar)
        layout.addWidget(self._tabela_log_erros)

        self._log_erros_carregados: list = []
        self._carregar_log_erros()
        return pagina

    def _carregar_log_erros(self) -> None:
        try:
            registros = self._controller.listar_log_erros()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o log de erros", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o log de erros.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o log de erros.")
            return

        self._log_erros_carregados = registros
        self._tabela_log_erros.setRowCount(len(registros))
        for linha, registro in enumerate(registros):
            self._tabela_log_erros.setItem(
                linha, 0, QTableWidgetItem(registro.data_hora.strftime("%d/%m/%Y %H:%M"))
            )
            self._tabela_log_erros.setItem(linha, 1, QTableWidgetItem(registro.usuario))
            self._tabela_log_erros.setItem(linha, 2, QTableWidgetItem(registro.erro))

    def _exibir_stacktrace(self) -> None:
        linha = self._tabela_log_erros.currentRow()
        if linha < 0 or linha >= len(self._log_erros_carregados):
            return
        registro = self._log_erros_carregados[linha]
        QMessageBox.information(
            self, "Detalhes do erro", registro.stacktrace or "Sem stacktrace disponível."
        )

    # -- Sub-aba: Saldo em Aberto --------------------------------------------

    def _construir_aba_saldo_em_aberto(self) -> QWidget:
        pagina = QWidget()

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_saldos)

        botao_exportar_csv = QPushButton("Exportar CSV")
        botao_exportar_csv.setIcon(icone("DOWNLOAD"))
        botao_exportar_csv.clicked.connect(self._exportar_csv)

        botao_exportar_xlsx = QPushButton("Exportar Excel")
        botao_exportar_xlsx.setIcon(icone("DOWNLOAD"))
        botao_exportar_xlsx.clicked.connect(self._exportar_xlsx)

        self._tabela_saldos = QTableWidget(0, 3)
        self._tabela_saldos.setHorizontalHeaderLabels(["Código", "Cliente", "Total em Aberto"])
        self._tabela_saldos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_atualizar)
        layout_botoes.addStretch()
        layout_botoes.addWidget(botao_exportar_csv)
        layout_botoes.addWidget(botao_exportar_xlsx)

        layout = QVBoxLayout(pagina)
        layout.addLayout(layout_botoes)
        layout.addWidget(self._tabela_saldos)

        self._carregar_saldos()
        return pagina

    def _carregar_saldos(self) -> None:
        try:
            saldos = self._controller.listar_saldos_em_aberto()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o relatório", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o relatório de saldo em aberto.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o relatório.")
            return

        self._tabela_saldos.setRowCount(len(saldos))
        for linha, saldo in enumerate(saldos):
            self._tabela_saldos.setItem(linha, 0, QTableWidgetItem(str(saldo.id_visivel)))
            self._tabela_saldos.setItem(linha, 1, QTableWidgetItem(saldo.nome_principal))
            self._tabela_saldos.setItem(
                linha, 2, QTableWidgetItem(f"R$ {saldo.total_em_aberto:.2f}")
            )

    def _exportar_csv(self) -> None:
        caminho_arquivo, _ = QFileDialog.getSaveFileName(
            self, "Exportar Saldo em Aberto", "saldo_em_aberto.csv", "CSV (*.csv)"
        )
        if not caminho_arquivo:
            return

        try:
            self._controller.exportar_saldos_em_aberto_csv(caminho_arquivo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível exportar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao exportar o relatório de saldo em aberto para CSV.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível exportar o relatório.")
            return

        QMessageBox.information(self, "Exportado", f"Relatório exportado para:\n{caminho_arquivo}")

    def _exportar_xlsx(self) -> None:
        caminho_arquivo, _ = QFileDialog.getSaveFileName(
            self, "Exportar Saldo em Aberto", "saldo_em_aberto.xlsx", "Excel (*.xlsx)"
        )
        if not caminho_arquivo:
            return

        try:
            self._controller.exportar_saldos_em_aberto_xlsx(caminho_arquivo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível exportar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao exportar o relatório de saldo em aberto para Excel.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível exportar o relatório.")
            return

        QMessageBox.information(self, "Exportado", f"Relatório exportado para:\n{caminho_arquivo}")
