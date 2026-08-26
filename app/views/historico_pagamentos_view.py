"""Diálogo de Histórico de Pagamentos (PySide6).

Aberto pelo botão "Histórico" da Ficha do Cliente. Mostra todos os
pagamentos do cliente (inclusive estornados) e, para o pagamento
selecionado, as compras que ele quitou — é aqui que uma compra "some" da
Ficha do Cliente quando é paga (a Ficha só mostra as em aberto). Se a
compra selecionada veio de um XML importado, "Ver Produtos" fica
disponível, igual na Ficha do Cliente. O estorno de um pagamento só fica
disponível para Administrador — a checagem também é reforçada na camada de
serviço (``app.services.pagamento_service``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.pagamento_controller import PagamentoController
from app.controllers.xml_importacao_controller import XmlImportacaoController
from app.services.auth_service import UsuarioAutenticado
from app.services.pagamento_service import PagamentoResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.views.xml_importacao_view import ObterProdutosWorker, ProdutosXmlDialog


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
        self._xml_controller = XmlImportacaoController(usuario_logado)
        self._cliente_id = cliente_id
        self._pagamentos_carregados: list[PagamentoResumo] = []
        self._worker_produtos: ObterProdutosWorker | None = None
        self._encerrado = False

        self.setWindowTitle(f"Histórico de Pagamentos — {nome_principal}")
        self.setMinimumSize(600, 560)

        self._tabela = QTableWidget(0, 5)
        self._tabela.setHorizontalHeaderLabels(["Data", "Valor", "Recebido por", "Observações", "Status"])
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.itemSelectionChanged.connect(self._atualizar_compras_quitadas)

        self._botao_estornar = QPushButton("Estornar Pagamento Selecionado")
        self._botao_estornar.setIcon(icone("ARROW_BACK_UP"))
        self._botao_estornar.setMinimumHeight(40)
        self._botao_estornar.clicked.connect(self._estornar)
        self._botao_estornar.setVisible(usuario_logado.eh_administrador)

        self._lista_compras_quitadas = QListWidget()
        self._lista_compras_quitadas.itemSelectionChanged.connect(self._atualizar_botao_ver_produtos)

        self._botao_ver_produtos = QPushButton("Ver Produtos")
        self._botao_ver_produtos.setIcon(icone("FILE_INVOICE"))
        self._botao_ver_produtos.setEnabled(False)
        self._botao_ver_produtos.clicked.connect(self._ver_produtos_xml)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(self._tabela)
        layout.addWidget(self._botao_estornar)
        layout.addWidget(QLabel("Compras quitadas pelo pagamento selecionado:"))
        layout.addWidget(self._lista_compras_quitadas)
        layout.addWidget(self._botao_ver_produtos)
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
            self._atualizar_compras_quitadas()
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
        self._atualizar_compras_quitadas()

    def _pagamento_selecionado(self) -> PagamentoResumo | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._pagamentos_carregados):
            return None
        return self._pagamentos_carregados[linha]

    def _atualizar_compras_quitadas(self) -> None:
        self._lista_compras_quitadas.clear()
        pagamento = self._pagamento_selecionado()
        if pagamento is None:
            self._lista_compras_quitadas.addItem("Selecione um pagamento acima.")
            self._atualizar_botao_ver_produtos()
            return

        if not pagamento.compras_quitadas:
            self._lista_compras_quitadas.addItem("Nenhuma compra quitada por este pagamento.")
            self._atualizar_botao_ver_produtos()
            return

        for compra in pagamento.compras_quitadas:
            rotulo_resto = " [Resto]" if compra.eh_resto else ""
            rotulo_xml = " 📄" if compra.origem_nfe_xml else ""
            data_formatada = compra.data.strftime("%d/%m")
            item = QListWidgetItem(
                f"R$ {compra.valor:.2f} — {data_formatada}{rotulo_resto} "
                f"(aplicado R$ {compra.valor_aplicado:.2f}){rotulo_xml}"
            )
            item.setData(Qt.ItemDataRole.UserRole, compra.origem_nfe_xml)
            self._lista_compras_quitadas.addItem(item)
        self._atualizar_botao_ver_produtos()

    def _estornar(self) -> None:
        pagamento = self._pagamento_selecionado()
        if pagamento is None:
            QMessageBox.information(self, "Selecione um pagamento", "Selecione um pagamento na lista.")
            return

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

    def _atualizar_botao_ver_produtos(self) -> None:
        item = self._lista_compras_quitadas.currentItem()
        chave = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._botao_ver_produtos.setEnabled(bool(chave))

    def _ver_produtos_xml(self) -> None:
        item = self._lista_compras_quitadas.currentItem()
        chave = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not chave:
            return  # compra não veio de um XML importado

        self._botao_ver_produtos.setEnabled(False)
        self._botao_ver_produtos.setText("Carregando produtos...")

        # Sem parent (None): mesmo raciocínio da Ficha do Cliente — a busca
        # roda de verdade em segundo plano, e fechar este diálogo antes de
        # terminar não trava nem espera (ver FichaClienteView._ver_produtos_xml).
        worker = ObterProdutosWorker(self._xml_controller, chave)
        worker.produtos_prontos.connect(self._exibir_produtos_xml)
        worker.erro_ocorrido.connect(self._erro_ao_obter_produtos_xml)
        worker.progresso.connect(self._atualizar_progresso_produtos)
        worker.finished.connect(self._finalizar_busca_produtos)
        worker.finished.connect(worker.deleteLater)
        self._worker_produtos = worker
        worker.start()

    def _atualizar_progresso_produtos(self, atual: int, total: int) -> None:
        if self._encerrado:
            return
        self._botao_ver_produtos.setText(f"Verificando {atual}/{total}...")

    def _finalizar_busca_produtos(self) -> None:
        if self._encerrado:
            return
        self._botao_ver_produtos.setText("Ver Produtos")
        self._atualizar_botao_ver_produtos()

    def _exibir_produtos_xml(self, produtos: list) -> None:
        if self._encerrado:
            return
        dialogo = ProdutosXmlDialog(produtos, self)
        dialogo.exec()

    def _erro_ao_obter_produtos_xml(self, mensagem: str) -> None:
        if self._encerrado:
            return
        QMessageBox.warning(self, "Não foi possível abrir os produtos", mensagem)

    def closeEvent(self, event) -> None:  # noqa: N802 (nome exigido pelo Qt)
        self._encerrado = True
        super().closeEvent(event)

    def accept(self) -> None:
        self._encerrado = True
        super().accept()

    def reject(self) -> None:
        self._encerrado = True
        super().reject()
