"""Ficha do Cliente (PySide6).

Aberta ao dar duplo clique em um cliente na tela "Clientes"
(``app.views.clientes_view``). Continua sendo um diálogo modal (decisão
do redesign — não virou uma página navegável). Mostra:

- Um cartão com o saldo em aberto, limite e valor disponível.
- Um histórico combinado do cliente — compras (``+ valor``) e
  pagamentos (``- valor``), do mais recente pro mais antigo, no lugar
  das duas listas separadas de antes (compras em aberto + diálogo
  próprio de histórico de pagamentos). Duplo clique num pagamento ainda
  abre o antigo :class:`~app.views.historico_pagamentos_view.HistoricoPagamentosDialog`
  (reaproveitado, é lá que mora o estorno). Se a compra selecionada veio
  de um XML importado, "Ver Produtos" fica habilitado.
- Botão "Enviar Lembrete" (novo aqui — antes só existia na tela de
  Início), visível quando o cliente está atrasado e/ou acima do limite,
  já que essa ação saiu das tabelas do dashboard.
- Ações: Nova Compra, Receber Pagamento, Editar Cliente, Excluir Conta,
  Extrato, Fechar.

Se o cliente ainda não foi confirmado (criado automaticamente por
importação de XML), a ficha pergunta se o cadastro deve ser confirmado
assim que é aberta.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
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
from app.utils.formatacao import formatar_reais
from app.utils.whatsapp import montar_mensagem_lembrete_limite, montar_mensagem_lembrete_saldo
from app.views.adicionar_compra_view import AdicionarCompraDialog
from app.views.editar_cliente_dialog import EditarClienteDialog
from app.views.historico_pagamentos_view import HistoricoPagamentosDialog
from app.views.receber_conta_view import ReceberContaDialog
from app.views.relatorio_view import LembreteWhatsAppDialog
from app.views.xml_importacao_view import ObterProdutosWorker, ProdutosXmlDialog

# Mesmo critério usado em app.views.clientes_view / app.views.painel_inicio_view
# pra considerar uma compra em aberto "atrasada".
_DIAS_ATRASO_PADRAO = 30

_TIPO_COMPRA = "compra"
_TIPO_PAGAMENTO = "pagamento"


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
        self.setMinimumSize(560, 620)

        self._label_nome = QLabel()
        self._label_nome.setProperty("papel", "titulo")

        self._botao_lembrete = QPushButton("Enviar Lembrete")
        self._botao_lembrete.setIcon(icone("BRAND_WHATSAPP"))
        self._botao_lembrete.setProperty("importancia", "primaria")
        self._botao_lembrete.clicked.connect(self._abrir_lembrete)
        self._botao_lembrete.setVisible(False)

        layout_cabecalho = QHBoxLayout()
        layout_cabecalho.addWidget(self._label_nome)
        layout_cabecalho.addStretch()
        layout_cabecalho.addWidget(self._botao_lembrete)

        self._label_alternativos = QLabel()
        self._label_alternativos.setProperty("papel", "secundario")
        self._label_telefones = QLabel()
        self._label_telefones.setProperty("papel", "secundario")
        self._label_compradores = QLabel()
        self._label_compradores.setProperty("papel", "secundario")

        self._card_saldo = QFrame()
        self._card_saldo.setProperty("papel", "card")
        layout_card = QVBoxLayout(self._card_saldo)
        label_card_titulo = QLabel("SALDO EM ABERTO")
        label_card_titulo.setProperty("papel", "secundario")
        self._label_saldo_valor = QLabel()
        self._label_saldo_valor.setStyleSheet("font-size: 24px; font-weight: 700;")
        self._label_limite_disponivel = QLabel()
        self._label_limite_disponivel.setProperty("papel", "secundario")
        layout_card.addWidget(label_card_titulo)
        layout_card.addWidget(self._label_saldo_valor)
        layout_card.addWidget(self._label_limite_disponivel)

        botao_adicionar_compra = QPushButton("+ Nova Compra")
        botao_adicionar_compra.setIcon(icone("SHOPPING_CART_PLUS"))
        botao_receber_conta = QPushButton("Receber Pagamento")
        botao_receber_conta.setIcon(icone("CASH_BANKNOTE"))
        for botao_principal in (botao_adicionar_compra, botao_receber_conta):
            botao_principal.setProperty("importancia", "primaria")
            botao_principal.setMinimumHeight(42)
        botao_adicionar_compra.clicked.connect(self._adicionar_compra)
        botao_receber_conta.clicked.connect(self._receber_conta)

        layout_botoes_principais = QHBoxLayout()
        layout_botoes_principais.addWidget(botao_adicionar_compra)
        layout_botoes_principais.addWidget(botao_receber_conta)

        label_timeline = QLabel("Histórico do cliente")
        label_timeline.setProperty("papel", "subtitulo")

        self._lista_timeline = QListWidget()
        self._lista_timeline.itemSelectionChanged.connect(self._atualizar_botao_ver_produtos)
        self._lista_timeline.itemDoubleClicked.connect(self._item_timeline_ativado)

        self._botao_ver_produtos = QPushButton("Ver Produtos")
        self._botao_ver_produtos.setIcon(icone("FILE_INVOICE"))
        self._botao_ver_produtos.setEnabled(False)
        self._botao_ver_produtos.clicked.connect(self._ver_produtos_xml)

        botao_editar = QPushButton("Editar Cliente")
        botao_editar.setIcon(icone("EDIT"))
        botao_excluir = QPushButton("Excluir Conta")
        botao_excluir.setIcon(icone("TRASH"))
        botao_extrato = QPushButton("Extrato")
        botao_extrato.setIcon(icone("PRINTER"))
        self._botao_fechar = QPushButton("Fechar")
        self._botao_fechar.setIcon(icone("X"))

        for botao in (self._botao_ver_produtos, botao_editar, botao_excluir, botao_extrato, self._botao_fechar):
            botao.setMinimumHeight(38)

        botao_editar.clicked.connect(self._editar_cliente)
        botao_excluir.clicked.connect(self._excluir_cliente)
        botao_extrato.clicked.connect(self._imprimir_extrato)
        self._botao_fechar.clicked.connect(self.accept)

        layout_botoes_secundarios = QHBoxLayout()
        layout_botoes_secundarios.addWidget(botao_editar)
        layout_botoes_secundarios.addWidget(botao_excluir)
        layout_botoes_secundarios.addWidget(botao_extrato)
        layout_botoes_secundarios.addStretch()
        layout_botoes_secundarios.addWidget(self._botao_fechar)

        layout = QVBoxLayout()
        layout.addLayout(layout_cabecalho)
        layout.addWidget(self._label_alternativos)
        layout.addWidget(self._label_telefones)
        layout.addWidget(self._label_compradores)
        layout.addWidget(self._card_saldo)
        layout.addLayout(layout_botoes_principais)
        layout.addWidget(label_timeline)
        layout.addWidget(self._lista_timeline)
        layout.addWidget(self._botao_ver_produtos)
        layout.addLayout(layout_botoes_secundarios)
        self.setLayout(layout)

        self._carregar_ficha()

    def _carregar_ficha(self) -> None:
        try:
            self._ficha = self._controller.ficha(self._cliente_id)
            pagamentos = self._pagamento_controller.listar_pagamentos(self._cliente_id)
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

        excedido = ficha.limite_fiado is not None and ficha.total_em_aberto > ficha.limite_fiado
        self._label_saldo_valor.setText(f"R$ {ficha.total_em_aberto:.2f}")
        if ficha.limite_fiado is not None:
            disponivel = ficha.limite_fiado - ficha.total_em_aberto
            texto_limite = f"Limite: R$ {ficha.limite_fiado:.2f}  •  Disponível: R$ {disponivel:.2f}"
            if excedido:
                texto_limite += "  ⚠ Acima do limite"
        else:
            texto_limite = "Sem limite de fiado definido"
        self._label_limite_disponivel.setText(texto_limite)

        data_limite_atraso = date.today() - timedelta(days=_DIAS_ATRASO_PADRAO)
        atrasado = any(
            c.status == "aberta" and c.data <= data_limite_atraso for c in ficha.compras
        )
        self._botao_lembrete.setVisible(ficha.total_em_aberto > 0)
        self._excedido, self._atrasado = excedido, atrasado

        self._preencher_timeline(ficha, pagamentos)
        self._atualizar_botao_ver_produtos()

        if not ficha.confirmado and not self._prompt_confirmacao_ja_exibido:
            self._prompt_confirmacao_ja_exibido = True
            self._perguntar_confirmacao_cliente()

    def _preencher_timeline(self, ficha: ClienteFicha, pagamentos: list) -> None:
        itens = []
        for compra in ficha.compras:
            marca_resto = " [Resto]" if compra.eh_resto else ""
            marca_xml = " 📄" if compra.origem_nfe_xml else ""
            texto = f"{compra.data.strftime('%d/%m')} — Compra: + R$ {compra.valor:.2f}{marca_resto}{marca_xml}"
            itens.append((compra.data, texto, _TIPO_COMPRA, compra))
        for pagamento in pagamentos:
            marca_estorno = " [Estornado]" if not pagamento.ativo else ""
            texto = (
                f"{pagamento.data_pagamento.strftime('%d/%m')} — Pagamento: "
                f"- R$ {pagamento.valor_pago:.2f}{marca_estorno}"
            )
            itens.append((pagamento.data_pagamento, texto, _TIPO_PAGAMENTO, pagamento))
        itens.sort(key=lambda item: item[0], reverse=True)

        self._lista_timeline.clear()
        if not itens:
            self._lista_timeline.addItem("Nenhuma movimentação registrada.")
            return
        for _data, texto, tipo, dado in itens:
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, (tipo, dado))
            self._lista_timeline.addItem(item)

    def _abrir_lembrete(self) -> None:
        if self._ficha is None:
            return
        ficha = self._ficha
        telefone = ficha.telefones[0] if ficha.telefones else None

        if self._excedido:
            mensagem = montar_mensagem_lembrete_limite(
                ficha.nome_principal,
                formatar_reais(ficha.total_em_aberto),
                formatar_reais(ficha.limite_fiado),
            )
        else:
            mensagem = montar_mensagem_lembrete_saldo(
                ficha.nome_principal,
                self._data_ultimo_pagamento() if self._atrasado else None,
                formatar_reais(ficha.total_em_aberto),
                self._atrasado,
            )

        dialogo = LembreteWhatsAppDialog(ficha.nome_principal, telefone, mensagem, self)
        dialogo.exec()

    def _data_ultimo_pagamento(self) -> str | None:
        try:
            pagamentos = self._pagamento_controller.listar_pagamentos(self._cliente_id)
        except Exception:
            logger.exception("Falha ao buscar o último pagamento do cliente %s.", self._cliente_id)
            return None
        ultimo_ativo = next((p for p in pagamentos if p.ativo), None)
        return ultimo_ativo.data_pagamento.strftime("%d/%m/%Y") if ultimo_ativo else None

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

    def _item_timeline_ativado(self, item: QListWidgetItem) -> None:
        """Duplo clique num pagamento abre o diálogo de histórico/estorno."""
        dado = item.data(Qt.ItemDataRole.UserRole)
        if not dado or dado[0] != _TIPO_PAGAMENTO or self._ficha is None:
            return
        dialogo = HistoricoPagamentosDialog(
            self._usuario_logado, self._cliente_id, self._ficha.nome_principal, self
        )
        dialogo.exec()
        self._carregar_ficha()  # um estorno pode ter reaberto compras: atualiza a ficha

    def _imprimir_extrato(self) -> None:
        if self._ficha is None:
            return

        compras_em_aberto = sorted(
            (c for c in self._ficha.compras if c.status == "aberta"), key=lambda c: c.data
        )
        html = montar_html_extrato_cliente(
            nome_cliente=self._ficha.nome_principal,
            telefones=self._ficha.telefones,
            compras=compras_em_aberto,
            total_em_aberto=self._ficha.total_em_aberto,
        )
        exibir_pre_visualizacao_impressao(self, f"Extrato — {self._ficha.nome_principal}", html)

    def _editar_cliente(self) -> None:
        if self._ficha is None:
            return

        dialogo = EditarClienteDialog(self._ficha, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        nome_principal, nomes_alternativos, telefones, compradores, limite_fiado = dialogo.dados()
        try:
            self._controller.editar(
                self._cliente_id, nome_principal, nomes_alternativos, telefones, compradores, limite_fiado
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
        item = self._lista_timeline.currentItem()
        dado = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        chave = dado[1].origem_nfe_xml if dado and dado[0] == _TIPO_COMPRA else None
        self._botao_ver_produtos.setEnabled(bool(chave))

    def _ver_produtos_xml(self) -> None:
        item = self._lista_timeline.currentItem()
        dado = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        chave = dado[1].origem_nfe_xml if dado and dado[0] == _TIPO_COMPRA else None
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
