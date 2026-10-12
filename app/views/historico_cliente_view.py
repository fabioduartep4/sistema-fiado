"""Diálogo de Histórico do Cliente (PySide6).

Aberto pelo botão "Histórico" da Ficha do Cliente. Mostra a linha do tempo
completa do cliente — todas as compras (em aberto e já quitadas) e todos
os pagamentos (inclusive estornados), do mais novo para o mais antigo.

A partir daqui dá para:

- ver os produtos de uma compra vinda de XML;
- reimprimir o comprovante de um pagamento (sai marcado como "2ª VIA";
  pagamento estornado não pode ser reimpresso);
- abrir os detalhes de um pagamento — as compras que ele quitou e o
  estorno (``app.views.historico_pagamentos_view``).
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
from app.utils.documentos import montar_html_recibo_pagamento
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.views.historico_pagamentos_view import HistoricoPagamentosDialog
from app.views.xml_importacao_view import BotaoVerProdutos

_TIPO_COMPRA = "compra"
_TIPO_PAGAMENTO = "pagamento"


class HistoricoClienteDialog(QDialog):
    """Linha do tempo de compras e pagamentos de um cliente."""

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
        dica = QLabel("Compras e pagamentos, do mais novo para o mais antigo.")
        dica.setProperty("papel", "secundario")

        self._lista = QListWidget()
        self._lista.itemSelectionChanged.connect(self._atualizar_botoes)
        self._lista.itemDoubleClicked.connect(self._item_ativado)

        self._botao_ver_produtos = BotaoVerProdutos(XmlImportacaoController(usuario_logado))

        self._botao_reimprimir = QPushButton("Reimprimir Comprovante")
        self._botao_reimprimir.setIcon(icone("PRINTER"))
        self._botao_reimprimir.clicked.connect(self._reimprimir)

        self._botao_detalhes = QPushButton("Detalhes / Estornar")
        self._botao_detalhes.setIcon(icone("CASH_BANKNOTE"))
        self._botao_detalhes.clicked.connect(self._abrir_detalhes_pagamento)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.clicked.connect(self.accept)

        for botao in (self._botao_ver_produtos, self._botao_reimprimir, self._botao_detalhes, botao_fechar):
            botao.setMinimumHeight(38)

        layout_acoes = QHBoxLayout()
        layout_acoes.addWidget(self._botao_ver_produtos)
        layout_acoes.addWidget(self._botao_reimprimir)
        layout_acoes.addWidget(self._botao_detalhes)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(dica)
        layout.addWidget(self._lista, 1)
        layout.addLayout(layout_acoes)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)

        self._carregar()

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

        itens = []
        for compra in ficha.compras:
            marca_resto = " [Resto]" if compra.eh_resto else ""
            marca_xml = " 📄" if compra.origem_nfe_xml else ""
            marca_quitada = " (quitada)" if compra.status == "quitada" else ""
            texto = (
                f"{compra.data.strftime('%d/%m/%Y')} — Compra: + {formatar_reais(compra.valor)}"
                f"{marca_resto}{marca_xml}{marca_quitada}"
            )
            if compra.descricao:
                texto += f"\n      Obs.: {compra.descricao}"
            itens.append((compra.data, texto, _TIPO_COMPRA, compra))
        for pagamento in pagamentos:
            marca_estorno = " [Estornado]" if not pagamento.ativo else ""
            texto = (
                f"{pagamento.data_pagamento.strftime('%d/%m/%Y')} — Pagamento: "
                f"- {formatar_reais(pagamento.valor_pago)}{marca_estorno}"
            )
            itens.append((pagamento.data_pagamento, texto, _TIPO_PAGAMENTO, pagamento))
        itens.sort(key=lambda item: item[0], reverse=True)

        self._lista.clear()
        if not itens:
            self._lista.addItem("Nenhuma movimentação registrada.")
        for _data, texto, tipo, dado in itens:
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, (tipo, dado))
            self._lista.addItem(item)
        self._atualizar_botoes()

    def _selecionado(self) -> tuple:
        """(tipo, dado) do item selecionado, ou (None, None)."""
        item = self._lista.currentItem()
        dado = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return dado if dado else (None, None)

    def _atualizar_botoes(self) -> None:
        tipo, dado = self._selecionado()
        self._botao_ver_produtos.definir_chave(dado.origem_nfe_xml if tipo == _TIPO_COMPRA else None)
        eh_pagamento = tipo == _TIPO_PAGAMENTO
        self._botao_detalhes.setEnabled(eh_pagamento)
        # Pagamento estornado não vale mais: não se reimprime comprovante dele.
        self._botao_reimprimir.setEnabled(eh_pagamento and dado.ativo)
        self._botao_reimprimir.setToolTip(
            "Pagamento estornado não pode ser reimpresso." if eh_pagamento and not dado.ativo else ""
        )

    def _item_ativado(self, _item: QListWidgetItem) -> None:
        if self._selecionado()[0] == _TIPO_PAGAMENTO:
            self._abrir_detalhes_pagamento()

    def _abrir_detalhes_pagamento(self) -> None:
        if self._selecionado()[0] != _TIPO_PAGAMENTO:
            return
        HistoricoPagamentosDialog(
            self._usuario_logado, self._cliente_id, self._nome_principal, self
        ).exec()
        self._carregar()  # um estorno muda a lista (pagamento estornado, compras reabertas)

    def _reimprimir(self) -> None:
        tipo, pagamento = self._selecionado()
        if tipo != _TIPO_PAGAMENTO or not pagamento.ativo:
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
