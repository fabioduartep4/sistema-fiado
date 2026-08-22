"""Diálogo de Histórico de Pagamentos (PySide6).

Aberto pelo botão "Histórico" da Ficha do Cliente. Mostra todos os
pagamentos do cliente (inclusive estornados). O estorno de um pagamento só
fica disponível para Administrador — a checagem também é reforçada na
camada de serviço (``app.services.pagamento_service``).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.pagamento_controller import PagamentoController
from app.services.auth_service import UsuarioAutenticado
from app.services.pagamento_service import PagamentoResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone


class HistoricoPagamentosDialog(QDialog):
    """Janela com o histórico de pagamentos de um cliente."""

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_id: str,
        nome_principal: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado
        self._controller = PagamentoController(usuario_logado)
        self._cliente_id = cliente_id
        self._pagamentos_carregados: list[PagamentoResumo] = []

        self.setWindowTitle(f"Histórico de Pagamentos — {nome_principal}")
        self.setMinimumSize(580, 420)

        self._tabela = QTableWidget(0, 5)
        self._tabela.setHorizontalHeaderLabels(["Data", "Valor", "Recebido por", "Observações", "Status"])
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self._botao_estornar = QPushButton("Estornar Pagamento Selecionado")
        self._botao_estornar.setIcon(icone("ARROW_BACK_UP"))
        self._botao_estornar.setMinimumHeight(40)
        self._botao_estornar.clicked.connect(self._estornar)
        self._botao_estornar.setVisible(usuario_logado.eh_administrador)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self._tabela)
        layout.addWidget(self._botao_estornar)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)

        self._carregar()

    def _carregar(self) -> None:
        try:
            self._pagamentos_carregados = self._controller.listar_pagamentos(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar histórico de pagamentos do cliente %s.", self._cliente_id)
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar o histórico de pagamentos."
            )
            return

        self._tabela.setRowCount(len(self._pagamentos_carregados))
        if not self._pagamentos_carregados:
            self._tabela.setRowCount(1)
            self._tabela.setItem(0, 0, QTableWidgetItem("Nenhum pagamento registrado ainda."))
            return

        for linha, pagamento in enumerate(self._pagamentos_carregados):
            self._tabela.setItem(
                linha, 0, QTableWidgetItem(pagamento.data_pagamento.strftime("%d/%m/%Y"))
            )
            self._tabela.setItem(linha, 1, QTableWidgetItem(f"R$ {pagamento.valor_pago:.2f}"))
            self._tabela.setItem(linha, 2, QTableWidgetItem(pagamento.recebido_por_nome))
            self._tabela.setItem(linha, 3, QTableWidgetItem(pagamento.observacoes or "-"))
            self._tabela.setItem(
                linha, 4, QTableWidgetItem("Ativo" if pagamento.ativo else "Estornado")
            )

    def _estornar(self) -> None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._pagamentos_carregados):
            QMessageBox.information(self, "Selecione um pagamento", "Selecione um pagamento na lista.")
            return

        pagamento = self._pagamentos_carregados[linha]
        if not pagamento.ativo:
            QMessageBox.information(self, "Já estornado", "Este pagamento já foi estornado.")
            return

        resposta = QMessageBox.question(
            self,
            "Confirmar estorno",
            f"Deseja realmente estornar o pagamento de R$ {pagamento.valor_pago:.2f} de "
            f"{pagamento.data_pagamento.strftime('%d/%m/%Y')}?\n\n"
            "As compras quitadas por ele voltarão a ficar em aberto.",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.estornar(pagamento.id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível estornar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao estornar pagamento %s.", pagamento.id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível estornar o pagamento.")
            return

        QMessageBox.information(self, "Pagamento estornado", "Pagamento estornado com sucesso.")
        self._carregar()
