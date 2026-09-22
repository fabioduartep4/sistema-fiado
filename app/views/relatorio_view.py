"""Tela de Histórico (PySide6).

Visível apenas para Administrador. Reúne três sub-abas, nesta ordem:

- "Vendas e Recebimentos" — compras e pagamentos combinados numa tabela
  só (Data/Cliente/Tipo/Valor/Usuário), com filtros de período, cliente
  e tipo (antes eram duas sub-abas separadas, "Vendas" e
  "Recebimentos" — ver ``app.services.relatorio_service.listar_movimentacoes``,
  que já normaliza os dois formatos num só).
- "Alterações" — auditoria genérica do resto do sistema:
  cadastro/edição/exclusão de cliente, gestão de usuários, estorno de
  pagamento — com uma descrição em texto já pronta pra cada ação (ver
  ``app.services.relatorio_service._descrever_acao``).
- "Log de Erros".

A antiga sub-aba "Saldo em Aberto" foi movida para a aba "Saldos" — ver
``app.views.saldos_view``.

``LembreteWhatsAppDialog`` continua definido aqui (usado também pela tela
de Início, que reaproveita esta classe) mesmo com a antiga sub-aba
"Lembretes" tendo sido movida para lá — ver ``app.views.painel_inicio_view``,
seção "Clientes com Maior Atraso".
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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
from app.utils.tabelas import ajustar_colunas
from app.utils.text_normalizer import normalizar_telefone
from app.utils.whatsapp import montar_link_whatsapp

# "Compra" não entra aqui: toda entrada de histórico com essa entidade
# vira a aba "Vendas e Recebimentos" (ver app.repositories.historico_repository.listar),
# então o filtro nunca teria nada pra mostrar.
_ENTIDADES_FILTRO = ["Todas", "Cliente", "Pagamento", "Usuario"]

_TIPOS_FILTRO = ["Todos", "Venda", "Recebimento"]

# Janela padrão da aba "Vendas e Recebimentos" ao abrir — os campos de
# data continuam editáveis pra ampliar a busca; mesma ideia do período
# padrão (mês atual) já usado no seletor de período do Início.
_DIAS_PADRAO_MOVIMENTACOES = 30


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
    """Tela com as sub-abas de histórico."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = RelatorioController(usuario_logado)

        abas = QTabWidget()
        abas.addTab(self._construir_aba_movimentacoes(), "Vendas e Recebimentos")
        abas.addTab(self._construir_aba_historico(), "Alterações")
        abas.addTab(self._construir_aba_log_erros(), "Log de Erros")

        titulo = QLabel("Histórico")
        titulo.setProperty("papel", "titulo")

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(abas)
        self.setLayout(layout)

    # -- Sub-aba: Vendas e Recebimentos ------------------------------------------
    #
    # Compras e pagamentos combinados numa tabela só (mais recente
    # primeiro), com filtros de período, cliente e tipo — ver
    # RelatorioController.listar_movimentacoes.

    def _construir_aba_movimentacoes(self) -> QWidget:
        pagina = QWidget()

        hoje = date.today()
        self._campo_data_inicio_mov = QDateEdit(QDate(hoje - timedelta(days=_DIAS_PADRAO_MOVIMENTACOES)))
        self._campo_data_inicio_mov.setCalendarPopup(True)
        self._campo_data_inicio_mov.setDisplayFormat("dd/MM/yyyy")

        self._campo_data_fim_mov = QDateEdit(QDate(hoje))
        self._campo_data_fim_mov.setCalendarPopup(True)
        self._campo_data_fim_mov.setDisplayFormat("dd/MM/yyyy")

        self._campo_cliente_mov = QLineEdit()
        self._campo_cliente_mov.setPlaceholderText("Todos os clientes")

        self._campo_tipo_mov = QComboBox()
        self._campo_tipo_mov.addItems(_TIPOS_FILTRO)

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_movimentacoes)

        layout_filtro = QHBoxLayout()
        layout_filtro.addWidget(QLabel("De:"))
        layout_filtro.addWidget(self._campo_data_inicio_mov)
        layout_filtro.addWidget(QLabel("Até:"))
        layout_filtro.addWidget(self._campo_data_fim_mov)
        layout_filtro.addWidget(QLabel("Cliente:"))
        layout_filtro.addWidget(self._campo_cliente_mov)
        layout_filtro.addWidget(QLabel("Tipo:"))
        layout_filtro.addWidget(self._campo_tipo_mov)
        layout_filtro.addWidget(botao_atualizar)

        self._tabela_movimentacoes = QTableWidget(0, 5)
        self._tabela_movimentacoes.setHorizontalHeaderLabels(["Data", "Cliente", "Tipo", "Valor", "Usuário"])
        self._tabela_movimentacoes.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ajustar_colunas(self._tabela_movimentacoes, 1)  # Cliente

        layout = QVBoxLayout(pagina)
        layout.addLayout(layout_filtro)
        layout.addWidget(self._tabela_movimentacoes)

        self._carregar_movimentacoes()
        return pagina

    def _carregar_movimentacoes(self) -> None:
        data_inicio = self._campo_data_inicio_mov.date().toPython()
        data_fim = self._campo_data_fim_mov.date().toPython()
        cliente_nome = self._campo_cliente_mov.text().strip() or None
        tipo_selecionado = self._campo_tipo_mov.currentText()
        tipo = None if tipo_selecionado == "Todos" else tipo_selecionado

        try:
            registros = self._controller.listar_movimentacoes(
                data_inicio=data_inicio, data_fim=data_fim, cliente_nome=cliente_nome, tipo=tipo
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar as movimentações", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar vendas e recebimentos.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar vendas e recebimentos."
            )
            return

        self._tabela_movimentacoes.setRowCount(len(registros))
        for linha, registro in enumerate(registros):
            marca_estorno = " [Estornado]" if registro.estornado else ""
            self._tabela_movimentacoes.setItem(
                linha, 0, QTableWidgetItem(registro.data_hora.strftime("%d/%m/%Y %H:%M"))
            )
            self._tabela_movimentacoes.setItem(linha, 1, QTableWidgetItem(registro.cliente_nome))
            self._tabela_movimentacoes.setItem(linha, 2, QTableWidgetItem(registro.tipo))
            self._tabela_movimentacoes.setItem(
                linha, 3, QTableWidgetItem(f"R$ {registro.valor:.2f}{marca_estorno}")
            )
            self._tabela_movimentacoes.setItem(linha, 4, QTableWidgetItem(registro.usuario_nome))

    # -- Sub-aba: Alterações ---------------------------------------------------

    def _construir_aba_historico(self) -> QWidget:
        pagina = QWidget()

        self._campo_filtro_entidade = QComboBox()
        self._campo_filtro_entidade.addItems(_ENTIDADES_FILTRO)
        self._campo_filtro_entidade.currentTextChanged.connect(self._carregar_historico)

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_historico)

        self._tabela_historico = QTableWidget(0, 3)
        self._tabela_historico.setHorizontalHeaderLabels(["Data/Hora", "Ação", "Usuário"])
        self._tabela_historico.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        ajustar_colunas(self._tabela_historico, 1)  # Ação

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
            self._tabela_historico.setItem(
                linha, 0, QTableWidgetItem(registro.data_hora.strftime("%d/%m/%Y %H:%M"))
            )
            self._tabela_historico.setItem(linha, 1, QTableWidgetItem(registro.descricao))
            self._tabela_historico.setItem(linha, 2, QTableWidgetItem(registro.usuario_nome))

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
        ajustar_colunas(self._tabela_log_erros, 2)  # Erro

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
