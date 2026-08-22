"""Ficha do Cliente (PySide6).

Aberta ao dar duplo clique em um resultado da tela de Busca de Cliente.
Mostra os dados do cliente, suas compras e o total em aberto, além dos
botões de ação: Adicionar Compra, Receber Conta, Editar Cliente, Excluir
Conta, Histórico, Extrato (pré-visualização de impressão com compras e
pagamentos) e Fechar. Se a compra selecionada veio de um XML importado, o
botão "Ver Produtos" (abaixo da lista de compras) fica habilitado e abre
os produtos da nota. Se o cliente ainda não foi confirmado (criado
automaticamente por importação de XML), a ficha pergunta se o cadastro
deve ser confirmado assim que é aberta.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.controllers.pagamento_controller import PagamentoController
from app.controllers.xml_importacao_controller import XmlImportacaoController
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import ClienteFicha
from app.utils.documentos import montar_html_extrato_cliente
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.views.adicionar_compra_view import AdicionarCompraDialog
from app.views.editar_cliente_dialog import EditarClienteDialog
from app.views.historico_pagamentos_view import HistoricoPagamentosDialog
from app.views.receber_conta_view import ReceberContaDialog
from app.views.xml_importacao_view import ObterProdutosWorker, ProdutosXmlDialog


class FichaClienteView(QDialog):
    """Janela da ficha de um cliente."""

    def __init__(self, usuario_logado: UsuarioAutenticado, cliente_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado
        self._controller = ClienteController(usuario_logado)
        self._pagamento_controller = PagamentoController(usuario_logado)
        self._xml_controller = XmlImportacaoController(usuario_logado)
        self._cliente_id = cliente_id
        self._ficha: ClienteFicha | None = None
        self._prompt_confirmacao_ja_exibido = False
        self._worker_produtos: ObterProdutosWorker | None = None
        self._encerrada = False

        self.setWindowTitle("Ficha do Cliente")
        self.setMinimumSize(540, 500)

        self._label_nome = QLabel()
        self._label_nome.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._label_alternativos = QLabel()
        self._label_telefones = QLabel()
        self._label_compradores = QLabel()

        self._lista_compras = QListWidget()
        self._lista_compras.itemSelectionChanged.connect(self._atualizar_botao_ver_produtos)
        self._label_total = QLabel()
        self._label_total.setStyleSheet("font-size: 14px; font-weight: bold;")

        self._botao_ver_produtos = QPushButton("Ver Produtos")
        self._botao_ver_produtos.setIcon(icone("FILE_INVOICE"))
        self._botao_ver_produtos.setEnabled(False)
        self._botao_ver_produtos.clicked.connect(self._ver_produtos_xml)

        botao_adicionar_compra = QPushButton("Adicionar Compra")
        botao_adicionar_compra.setIcon(icone("SHOPPING_CART_PLUS"))
        botao_receber_conta = QPushButton("Receber Conta")
        botao_receber_conta.setIcon(icone("CASH_BANKNOTE"))
        botao_editar = QPushButton("Editar Cliente")
        botao_editar.setIcon(icone("EDIT"))
        botao_excluir = QPushButton("Excluir Conta")
        botao_excluir.setIcon(icone("TRASH"))
        botao_historico = QPushButton("Histórico")
        botao_historico.setIcon(icone("HISTORY"))
        botao_extrato = QPushButton("Extrato")
        botao_extrato.setIcon(icone("PRINTER"))
        self._botao_fechar = QPushButton("Fechar")
        self._botao_fechar.setIcon(icone("X"))

        for botao in (
            self._botao_ver_produtos,
            botao_adicionar_compra,
            botao_receber_conta,
            botao_editar,
            botao_excluir,
            botao_historico,
            botao_extrato,
            self._botao_fechar,
        ):
            botao.setMinimumHeight(40)

        botao_adicionar_compra.clicked.connect(self._adicionar_compra)
        botao_receber_conta.clicked.connect(self._receber_conta)
        botao_editar.clicked.connect(self._editar_cliente)
        botao_excluir.clicked.connect(self._excluir_cliente)
        botao_historico.clicked.connect(self._ver_historico)
        botao_extrato.clicked.connect(self._imprimir_extrato)
        self._botao_fechar.clicked.connect(self.accept)

        layout_botoes_principais = QHBoxLayout()
        layout_botoes_principais.addWidget(botao_adicionar_compra)
        layout_botoes_principais.addWidget(botao_receber_conta)

        layout_botoes_secundarios = QHBoxLayout()
        layout_botoes_secundarios.addWidget(botao_editar)
        layout_botoes_secundarios.addWidget(botao_excluir)
        layout_botoes_secundarios.addWidget(botao_historico)
        layout_botoes_secundarios.addWidget(botao_extrato)
        layout_botoes_secundarios.addStretch()
        layout_botoes_secundarios.addWidget(self._botao_fechar)

        layout = QVBoxLayout()
        layout.addWidget(self._label_nome)
        layout.addWidget(self._label_alternativos)
        layout.addWidget(self._label_telefones)
        layout.addWidget(self._label_compradores)
        layout.addWidget(QLabel("Compras:"))
        layout.addWidget(self._lista_compras)
        layout.addWidget(self._botao_ver_produtos)
        layout.addWidget(self._label_total)
        layout.addLayout(layout_botoes_principais)
        layout.addLayout(layout_botoes_secundarios)
        self.setLayout(layout)

        self._carregar_ficha()

    def _carregar_ficha(self) -> None:
        try:
            self._ficha = self._controller.ficha(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Cliente não encontrado", str(exc))
            self.reject()
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a ficha do cliente %s.", self._cliente_id)
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar os dados do cliente."
            )
            self.reject()
            return

        ficha = self._ficha
        self.setWindowTitle(f"Ficha do Cliente — {ficha.nome_principal}")
        self._label_nome.setText(f"{ficha.nome_principal}  (código {ficha.id_visivel})")
        self._label_alternativos.setText(
            "Nomes alternativos: " + (", ".join(ficha.nomes_alternativos) or "-")
        )
        self._label_telefones.setText("Telefones: " + (", ".join(ficha.telefones) or "-"))
        self._label_compradores.setText("Compradores: " + (", ".join(ficha.compradores) or "-"))

        self._lista_compras.clear()
        if not ficha.compras:
            self._lista_compras.addItem("Nenhuma compra registrada.")
        for compra in ficha.compras:
            rotulo_resto = " [Resto]" if compra.eh_resto else ""
            rotulo_xml = " 📄" if compra.origem_nfe_xml else ""
            data_formatada = compra.data.strftime("%d/%m")
            item = QListWidgetItem(
                f"R$ {compra.valor:.2f} — {data_formatada}{rotulo_resto} ({compra.status}){rotulo_xml}"
            )
            item.setData(Qt.ItemDataRole.UserRole, compra.origem_nfe_xml)
            self._lista_compras.addItem(item)

        self._label_total.setText(f"Total em aberto: R$ {ficha.total_em_aberto:.2f}")
        self._atualizar_botao_ver_produtos()

        if not ficha.confirmado and not self._prompt_confirmacao_ja_exibido:
            self._prompt_confirmacao_ja_exibido = True
            self._perguntar_confirmacao_cliente()

    def _adicionar_compra(self) -> None:
        if self._ficha is None:
            return

        dialogo = AdicionarCompraDialog(
            self._usuario_logado, self._cliente_id, self._ficha.nome_principal, self
        )
        dialogo.exec()
        self._carregar_ficha()  # atualiza a lista de compras e o total em aberto

    def _receber_conta(self) -> None:
        if self._ficha is None:
            return

        dialogo = ReceberContaDialog(
            self._usuario_logado, self._cliente_id, self._ficha.nome_principal, self
        )
        dialogo.exec()
        self._carregar_ficha()  # atualiza a lista de compras e o total em aberto

    def _ver_historico(self) -> None:
        if self._ficha is None:
            return

        dialogo = HistoricoPagamentosDialog(
            self._usuario_logado, self._cliente_id, self._ficha.nome_principal, self
        )
        dialogo.exec()
        self._carregar_ficha()  # um estorno pode ter reaberto compras: atualiza a ficha

    def _imprimir_extrato(self) -> None:
        if self._ficha is None:
            return

        try:
            pagamentos = self._pagamento_controller.listar_pagamentos(self._cliente_id)
        except Exception:
            logger.exception("Falha ao carregar pagamentos para o extrato do cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível montar o extrato.")
            return

        html = montar_html_extrato_cliente(
            nome_cliente=self._ficha.nome_principal,
            id_visivel=self._ficha.id_visivel,
            telefones=self._ficha.telefones,
            total_em_aberto=self._ficha.total_em_aberto,
            compras=self._ficha.compras,
            pagamentos=pagamentos,
        )
        exibir_pre_visualizacao_impressao(self, f"Extrato — {self._ficha.nome_principal}", html)

    def _editar_cliente(self) -> None:
        if self._ficha is None:
            return

        dialogo = EditarClienteDialog(self._ficha, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        nome_principal, nomes_alternativos, telefones, compradores = dialogo.dados()
        try:
            self._controller.editar(
                self._cliente_id, nome_principal, nomes_alternativos, telefones, compradores
            )
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível editar o cliente", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao editar cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível editar o cliente.")
            return

        self._carregar_ficha()

    def _excluir_cliente(self) -> None:
        if self._ficha is None:
            return

        resposta = QMessageBox.question(
            self,
            "Confirmar exclusão",
            f"Deseja realmente excluir a conta de '{self._ficha.nome_principal}'?\n\n"
            "O histórico e as compras não serão apagados, mas o cliente deixará de "
            "aparecer nas buscas.",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.excluir(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível excluir", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao excluir cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível excluir o cliente.")
            return

        QMessageBox.information(self, "Cliente excluído", "Conta excluída com sucesso.")
        self.accept()

    def _atualizar_botao_ver_produtos(self) -> None:
        item = self._lista_compras.currentItem()
        chave = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._botao_ver_produtos.setEnabled(bool(chave))

    def _ver_produtos_xml(self) -> None:
        item = self._lista_compras.currentItem()
        chave = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if not chave:
            return  # compra não veio de um XML importado

        self._botao_ver_produtos.setEnabled(False)
        self._botao_ver_produtos.setText("Carregando produtos...")

        # Sem parent (None): a busca roda em segundo plano de verdade — se
        # o usuário fechar a ficha antes de terminar (pasta com muitos
        # XMLs pode demorar bastante), a janela fecha na hora, sem travar
        # nem esperar. A QThread não fica presa ao ciclo de vida da janela
        # (evita o crash de "destruir thread ainda em execução"), e os
        # callbacks abaixo conferem ``self._encerrada`` antes de mexer em
        # qualquer widget, para não tentar atualizar uma ficha já fechada.
        worker = ObterProdutosWorker(self._xml_controller, chave)
        worker.produtos_prontos.connect(self._exibir_produtos_xml)
        worker.erro_ocorrido.connect(self._erro_ao_obter_produtos_xml)
        worker.progresso.connect(self._atualizar_progresso_produtos)
        worker.finished.connect(self._finalizar_busca_produtos)
        worker.finished.connect(worker.deleteLater)
        self._worker_produtos = worker
        worker.start()

    def _atualizar_progresso_produtos(self, atual: int, total: int) -> None:
        if self._encerrada:
            return
        self._botao_ver_produtos.setText(f"Verificando {atual}/{total}...")

    def _finalizar_busca_produtos(self) -> None:
        if self._encerrada:
            return
        self._botao_ver_produtos.setText("Ver Produtos")
        self._atualizar_botao_ver_produtos()

    def _exibir_produtos_xml(self, produtos: list) -> None:
        if self._encerrada:
            return
        dialogo = ProdutosXmlDialog(produtos, self)
        dialogo.exec()

    def _erro_ao_obter_produtos_xml(self, mensagem: str) -> None:
        if self._encerrada:
            return
        QMessageBox.warning(self, "Não foi possível abrir os produtos", mensagem)

    def closeEvent(self, event) -> None:  # noqa: N802 (nome exigido pelo Qt)
        self._encerrada = True
        super().closeEvent(event)

    def accept(self) -> None:
        self._encerrada = True
        super().accept()

    def reject(self) -> None:
        self._encerrada = True
        super().reject()

    def _perguntar_confirmacao_cliente(self) -> None:
        resposta = QMessageBox.question(
            self,
            "Cliente pendente de confirmação",
            "Esse cliente foi criado automaticamente através do XML e não foi confirmado, "
            "deseja confirmar o cliente?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.confirmar(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível confirmar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao confirmar cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível confirmar o cliente.")
            return

        self._carregar_ficha()  # atualiza a ficha para refletir o cadastro confirmado
