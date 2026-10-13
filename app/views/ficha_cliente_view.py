"""Ficha do Cliente (PySide6).

Aberta ao dar duplo clique em um cliente na tela "Clientes"
(``app.views.clientes_view``). Continua sendo um diálogo modal (decisão
do redesign — não virou uma página navegável). Mostra:

- Um cartão com o saldo em aberto, limite e valor disponível.
- O extrato do cliente: as compras em aberto, com data, hora e valor
  (as mesmas que saem no extrato impresso). Se a compra selecionada veio
  de um XML importado, "Ver Produtos" fica habilitado.
- Botão "Histórico", que abre a linha do tempo completa — compras e
  pagamentos, reimpressão de comprovante e estorno
  (:class:`~app.views.historico_cliente_view.HistoricoClienteDialog`).
- Botão "Enviar Lembrete", visível quando o cliente tem saldo em aberto.
- Ações: Nova Compra, Receber Pagamento, Imprimir Extrato, Editar
  Cliente, Excluir Conta, Fechar.

Se o cliente ainda não foi confirmado (criado automaticamente por
importação de XML), a ficha pergunta se o cadastro deve ser confirmado
assim que é aberta.
"""

from __future__ import annotations

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
from app.services import lembrete_service
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import ClienteFicha
from app.utils.documentos import formatar_data_hora_compra, montar_html_extrato_cliente
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.impressao import exibir_pre_visualizacao_impressao
from app.utils.formatacao import formatar_reais
from app.views.adicionar_compra_view import AdicionarCompraDialog
from app.views.componentes import confirmar_e_cancelar_compra
from app.views.editar_cliente_dialog import EditarClienteDialog
from app.views.historico_cliente_view import HistoricoClienteDialog
from app.views.receber_conta_view import ReceberContaDialog
from app.views.relatorio_view import LembreteWhatsAppDialog
from app.views.xml_importacao_view import BotaoVerProdutos


class FichaClienteView(QDialog):
    """Janela da ficha de um cliente."""

    def __init__(self, usuario_logado: UsuarioAutenticado, cliente_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._usuario_logado = usuario_logado
        self._controller = ClienteController(usuario_logado)
        self._pagamento_controller = PagamentoController(usuario_logado)
        self._cliente_id = cliente_id
        self._ficha: ClienteFicha | None = None
        self._prompt_confirmacao_ja_exibido = False

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

        label_extrato = QLabel("Extrato — contas em aberto")
        label_extrato.setProperty("papel", "subtitulo")

        self._lista_extrato = QListWidget()
        self._lista_extrato.itemSelectionChanged.connect(self._atualizar_botao_ver_produtos)

        self._botao_ver_produtos = BotaoVerProdutos(XmlImportacaoController(usuario_logado))

        botao_extrato = QPushButton("Imprimir Extrato")
        botao_extrato.setIcon(icone("PRINTER"))
        botao_historico = QPushButton("Histórico")
        botao_historico.setIcon(icone("HISTORY"))

        # Só Administrador cancela compra (o serviço também confere).
        self._botao_cancelar_compra = QPushButton("Cancelar Compra")
        self._botao_cancelar_compra.setIcon(icone("TRASH_X"))
        self._botao_cancelar_compra.setMinimumHeight(38)
        self._botao_cancelar_compra.setEnabled(False)
        self._botao_cancelar_compra.setVisible(usuario_logado.eh_administrador)
        self._botao_cancelar_compra.clicked.connect(self._cancelar_compra)

        botao_editar = QPushButton("Editar Cliente")
        botao_editar.setIcon(icone("EDIT"))
        botao_excluir = QPushButton("Excluir Conta")
        botao_excluir.setIcon(icone("TRASH"))
        self._botao_fechar = QPushButton("Fechar")
        self._botao_fechar.setIcon(icone("X"))

        for botao in (
            self._botao_ver_produtos,
            botao_extrato,
            botao_historico,
            botao_editar,
            botao_excluir,
            self._botao_fechar,
        ):
            botao.setMinimumHeight(38)

        botao_extrato.clicked.connect(self._imprimir_extrato)
        botao_historico.clicked.connect(self._abrir_historico)
        botao_editar.clicked.connect(self._editar_cliente)
        botao_excluir.clicked.connect(self._excluir_cliente)
        self._botao_fechar.clicked.connect(self.accept)

        layout_botoes_extrato = QHBoxLayout()
        layout_botoes_extrato.addWidget(self._botao_ver_produtos)
        layout_botoes_extrato.addWidget(self._botao_cancelar_compra)
        layout_botoes_extrato.addWidget(botao_extrato)
        layout_botoes_extrato.addWidget(botao_historico)

        layout_botoes_secundarios = QHBoxLayout()
        layout_botoes_secundarios.addWidget(botao_editar)
        layout_botoes_secundarios.addWidget(botao_excluir)
        layout_botoes_secundarios.addStretch()
        layout_botoes_secundarios.addWidget(self._botao_fechar)

        layout = QVBoxLayout()
        layout.addLayout(layout_cabecalho)
        layout.addWidget(self._label_alternativos)
        layout.addWidget(self._label_telefones)
        layout.addWidget(self._label_compradores)
        layout.addWidget(self._card_saldo)
        layout.addLayout(layout_botoes_principais)
        layout.addWidget(label_extrato)
        layout.addWidget(self._lista_extrato, 1)
        layout.addLayout(layout_botoes_extrato)
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

        excedido = ficha.limite_fiado is not None and ficha.total_em_aberto > ficha.limite_fiado
        self._label_saldo_valor.setText(f"{formatar_reais(ficha.total_em_aberto)}")
        if ficha.limite_fiado is not None:
            disponivel = ficha.limite_fiado - ficha.total_em_aberto
            texto_limite = f"Limite: {formatar_reais(ficha.limite_fiado)}  •  Disponível: {formatar_reais(disponivel)}"
            if excedido:
                texto_limite += "  ⚠ Acima do limite"
        else:
            texto_limite = "Sem limite de fiado definido"
        self._label_limite_disponivel.setText(texto_limite)

        self._botao_lembrete.setVisible(ficha.total_em_aberto > 0)

        self._preencher_extrato()

        if not ficha.confirmado and not self._prompt_confirmacao_ja_exibido:
            self._prompt_confirmacao_ja_exibido = True
            self._perguntar_confirmacao_cliente()

    def _compras_em_aberto(self) -> list:
        """Compras em aberto, da mais antiga para a mais nova (as mesmas do extrato impresso)."""
        if self._ficha is None:
            return []
        return sorted((c for c in self._ficha.compras if c.status == "aberta"), key=lambda c: c.data)

    def _preencher_extrato(self) -> None:
        self._lista_extrato.clear()
        compras = self._compras_em_aberto()
        if not compras:
            self._lista_extrato.addItem("Nenhuma conta em aberto.")
        for compra in compras:
            marca_resto = " [Resto]" if compra.eh_resto else ""
            marca_xml = " 📄" if compra.origem_nfe_xml else ""
            texto = f"{formatar_data_hora_compra(compra)} — {formatar_reais(compra.valor)}{marca_resto}{marca_xml}"
            if compra.descricao:
                texto += f"\n      Obs.: {compra.descricao}"
            item = QListWidgetItem(texto)
            item.setData(Qt.ItemDataRole.UserRole, compra)
            self._lista_extrato.addItem(item)
        self._atualizar_botao_ver_produtos()

    def _atualizar_botao_ver_produtos(self) -> None:
        item = self._lista_extrato.currentItem()
        compra = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        self._botao_ver_produtos.definir_chave(compra.origem_nfe_xml if compra is not None else None)
        # Conta "Resto" não se cancela: ela some estornando o pagamento que a gerou.
        self._botao_cancelar_compra.setEnabled(compra is not None and not compra.eh_resto)

    def _cancelar_compra(self) -> None:
        item = self._lista_extrato.currentItem()
        compra = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if compra is not None and confirmar_e_cancelar_compra(self, self._usuario_logado, compra):
            self._carregar_ficha()

    def _abrir_lembrete(self) -> None:
        try:
            lembrete = lembrete_service.montar_lembrete(self._cliente_id)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível montar o lembrete", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao montar o lembrete do cliente %s.", self._cliente_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível montar o lembrete.")
            return

        LembreteWhatsAppDialog(lembrete.nome_cliente, lembrete.telefone, lembrete.mensagem, self).exec()

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

    def _abrir_historico(self) -> None:
        """Linha do tempo completa (compras e pagamentos), reimpressão e estorno."""
        if self._ficha is None:
            return
        HistoricoClienteDialog(
            self._usuario_logado, self._cliente_id, self._ficha.nome_principal, self
        ).exec()
        self._carregar_ficha()  # um estorno pode ter reaberto compras: atualiza a ficha

    def _imprimir_extrato(self) -> None:
        if self._ficha is None:
            return

        html = montar_html_extrato_cliente(
            nome_cliente=self._ficha.nome_principal,
            telefones=self._ficha.telefones,
            compras=self._compras_em_aberto(),
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

        nome = self._ficha.nome_principal
        saldo = self._ficha.total_em_aberto
        if saldo > 0:
            resposta = QMessageBox.warning(
                self,
                "Cliente com saldo em aberto",
                f"ATENÇÃO: '{nome}' ainda deve {formatar_reais(saldo)}.\n\n"
                "Se a conta for excluída, essa dívida deixa de aparecer nos saldos e nas "
                "buscas (o histórico e as compras não são apagados).\n\n"
                "Deseja excluir mesmo assim?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
        else:
            resposta = QMessageBox.question(
                self,
                "Confirmar exclusão",
                f"Deseja realmente excluir a conta de '{nome}'?\n\n"
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
