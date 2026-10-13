"""Diálogo de Histórico do Cliente (PySide6).

Aberto pelo botão "Histórico" da Ficha do Cliente. Duas abas, cada uma
com a sua lista, do mais novo para o mais antigo:

- **Pagamentos** (abre nesta): todos os pagamentos, inclusive estornados.
  Dá para reimprimir o comprovante (sai marcado como "2ª VIA"; pagamento
  estornado não pode ser reimpresso) e abrir os detalhes — as compras que
  o pagamento quitou e o estorno (``app.views.historico_pagamentos_view``).
- **Compras**: todas as compras, em aberto e já quitadas. Dá para ver os
  produtos de uma compra vinda de XML.
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.controllers.pagamento_controller import PagamentoController
from app.controllers.xml_importacao_controller import XmlImportacaoController
from app.services.auth_service import UsuarioAutenticado
from app.utils.documentos import montar_html_recibo_pagamento
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.views.historico_pagamentos_view import HistoricoPagamentosDialog
from app.views.xml_importacao_view import BotaoVerProdutos


class HistoricoClienteDialog(QDialog):
    """Histórico de um cliente: uma aba de pagamentos e uma de compras."""

    def __init__(
        self,
        usuario_logado: UsuarioAutenticado,
        cliente_id: str,
        nome_principal: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado
        self._cliente_controller = ClienteController(usuario_logado)
        self._pagamento_controller = PagamentoController(usuario_logado)
        self._cliente_id = cliente_id
        self._nome_principal = nome_principal

        self.setWindowTitle(f"Histórico — {nome_principal}")
        self.setMinimumSize(520, 560)

        titulo = QLabel("Histórico do cliente")
        titulo.setProperty("papel", "titulo")

        self._abas = QTabWidget()
        self._abas.addTab(self._construir_aba_pagamentos(), "Pagamentos")  # a primeira é a que abre
        self._abas.addTab(self._construir_aba_compras(), "Compras")

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(self._abas, 1)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)

        self._carregar()

    # -- Aba: Pagamentos -------------------------------------------------------

    def _construir_aba_pagamentos(self) -> QWidget:
        pagina = QWidget()

        self._lista_pagamentos = QListWidget()
        self._lista_pagamentos.itemSelectionChanged.connect(self._atualizar_botoes_pagamento)
        self._lista_pagamentos.itemDoubleClicked.connect(lambda _item: self._abrir_detalhes_pagamento())

        self._botao_reimprimir = QPushButton("Reimprimir Comprovante")
        self._botao_reimprimir.setIcon(icone("PRINTER"))
        self._botao_reimprimir.clicked.connect(self._reimprimir)

        self._botao_detalhes = QPushButton("Detalhes / Estornar")
        self._botao_detalhes.setIcon(icone("CASH_BANKNOTE"))
        self._botao_detalhes.clicked.connect(self._abrir_detalhes_pagamento)

        layout_acoes = QHBoxLayout()
        for botao in (self._botao_reimprimir, self._botao_detalhes):
            botao.setMinimumHeight(38)
            layout_acoes.addWidget(botao)

        layout = QVBoxLayout(pagina)
        layout.addWidget(self._lista_pagamentos, 1)
        layout.addLayout(layout_acoes)
        return pagina

    # -- Aba: Compras ----------------------------------------------------------

    def _construir_aba_compras(self) -> QWidget:
        pagina = QWidget()

        self._lista_compras = QListWidget()
        self._lista_compras.itemSelectionChanged.connect(self._atualizar_botao_ver_produtos)

        self._botao_ver_produtos = BotaoVerProdutos(XmlImportacaoController(self._usuario_logado))
        self._botao_ver_produtos.setMinimumHeight(38)

        layout = QVBoxLayout(pagina)
        layout.addWidget(self._lista_compras, 1)
        layout.addWidget(self._botao_ver_produtos)
        return pagina

    # -- Dados -----------------------------------------------------------------

    def _carregar(self) -> None:
        try:
            ficha = self._cliente_controller.ficha(self._cliente_id)
            pagamentos = self._pagamento_controller.listar_pagamentos(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o histórico", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o histórico do cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o histórico.")
            return

        self._lista_pagamentos.clear()
        if not pagamentos:
            self._lista_pagamentos.addItem("Nenhum pagamento registrado.")
        for pagamento in sorted(pagamentos, key=lambda p: p.data_pagamento, reverse=True):
            marca_estorno = " [Estornado]" if not pagamento.ativo else ""
            texto = f"{pagamento.data_pagamento.strftime('%d/%m/%Y')} — {formatar_reais(pagamento.valor_pago)}{marca_estorno}"
            if pagamento.observacoes:
                texto += f"\n      Obs.: {pagamento.observacoes}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, pagamento)
            self._lista_pagamentos.addItem(item)

        self._lista_compras.clear()
        if not ficha.compras:
            self._lista_compras.addItem("Nenhuma compra registrada.")
        compras = sorted(
            ficha.compras,
            key=lambda c: (c.data, c.data_hora.timestamp() if c.data_hora else 0),
            reverse=True,
        )
        for compra in compras:
            marca_resto = " [Resto]" if compra.eh_resto else ""
            marca_xml = " 📄" if compra.origem_nfe_xml else ""
            marca_quitada = " (quitada)" if compra.status == "quitada" else ""
            texto = (
                f"{compra.data.strftime('%d/%m/%Y')} — {formatar_reais(compra.valor)}"
                f"{marca_resto}{marca_xml}{marca_quitada}"
            )
            if compra.descricao:
                texto += f"\n      Obs.: {compra.descricao}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, compra)
            self._lista_compras.addItem(item)

        self._abas.setTabText(0, f"Pagamentos ({len(pagamentos)})")
        self._abas.setTabText(1, f"Compras ({len(ficha.compras)})")
        self._atualizar_botoes_pagamento()
        self._atualizar_botao_ver_produtos()

    @staticmethod
    def _dado_selecionado(lista: QListWidget):
        """O pagamento/compra do item selecionado, ou None (nada selecionado ou linha de aviso)."""
        item = lista.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    # -- Ações: pagamentos -----------------------------------------------------

    def _atualizar_botoes_pagamento(self) -> None:
        pagamento = self._dado_selecionado(self._lista_pagamentos)
        self._botao_detalhes.setEnabled(pagamento is not None)
        # Pagamento estornado não vale mais: não se reimprime comprovante dele.
        self._botao_reimprimir.setEnabled(pagamento is not None and pagamento.ativo)
        self._botao_reimprimir.setToolTip(
            "Pagamento estornado não pode ser reimpresso."
            if pagamento is not None and not pagamento.ativo
            else ""
        )

    def _abrir_detalhes_pagamento(self) -> None:
        if self._dado_selecionado(self._lista_pagamentos) is None:
            return
        HistoricoPagamentosDialog(
            self._usuario_logado, self._cliente_id, self._nome_principal, self
        ).exec()
        self._carregar()  # um estorno muda as duas listas (pagamento estornado, compras reabertas)

    def _reimprimir(self) -> None:
        pagamento = self._dado_selecionado(self._lista_pagamentos)
        if pagamento is None or not pagamento.ativo:
            return
        html = montar_html_recibo_pagamento(
            nome_cliente=self._nome_principal,
            valor_pago=pagamento.valor_pago,
            data_pagamento=pagamento.data_pagamento,
            recebido_por=pagamento.recebido_por_nome,
            observacoes=pagamento.observacoes,
            valor_resto_gerado=pagamento.valor_resto_gerado,
            segunda_via=True,
        )
        exibir_pre_visualizacao_impressao(self, "Comprovante de Pagamento (2ª via)", html)

    # -- Ações: compras --------------------------------------------------------

    def _atualizar_botao_ver_produtos(self) -> None:
        compra = self._dado_selecionado(self._lista_compras)
        self._botao_ver_produtos.definir_chave(compra.origem_nfe_xml if compra is not None else None)
