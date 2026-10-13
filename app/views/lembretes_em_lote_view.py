"""Lembretes em lote por WhatsApp (PySide6).

Aberto pelo botão "Lembretes em lote" da seção "Clientes com Maior Atraso"
da tela de Início. Em duas etapas:

1. **Escolher**: lista os clientes em atraso; quem tem telefone já vem
   marcado, quem não tem aparece só para constar.
2. **Enviar**: um cliente por vez — mostra a mensagem pronta (editável) e
   abre a conversa no WhatsApp. O envio em si é manual: o WhatsApp não
   permite que o programa envie sozinho sem um serviço pago. Depois de
   enviar lá, volta-se aqui para o próximo.

A mensagem de cada cliente é a mesma do botão "Enviar Lembrete" da ficha
(``app.services.lembrete_service``), montada na hora de cada um.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.services import lembrete_service
from app.services.relatorio_service import SaldoAtrasoResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.icons import icone
from app.utils.text_normalizer import normalizar_telefone
from app.utils.whatsapp import montar_link_whatsapp
from app.views.componentes import desligar_botao_padrao


def _abrir_link(link: str) -> None:
    QDesktopServices.openUrl(QUrl(link))


class LembretesEmLoteDialog(QDialog):
    """Envia o lembrete de conta para vários clientes em atraso, um por vez."""

    def __init__(
        self, atrasos: list[SaldoAtrasoResumo], dias_atraso: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._dias_atraso = dias_atraso
        self._fila: list[SaldoAtrasoResumo] = []
        self._posicao = 0
        self._abertas = 0
        self._puladas = 0
        self._lembrete_atual: lembrete_service.Lembrete | None = None
        self._estado_ao_pressionar: tuple = (None, None)

        self.setWindowTitle("Lembretes em lote")
        self.setMinimumSize(520, 520)

        self._paginas = QStackedWidget()
        self._paginas.addWidget(self._construir_pagina_escolha(atrasos))
        self._paginas.addWidget(self._construir_pagina_envio())
        self._paginas.addWidget(self._construir_pagina_fim())

        layout = QVBoxLayout(self)
        layout.addWidget(self._paginas)
        desligar_botao_padrao(self)
        self._atualizar_contagem()

    # -- Etapa 1: escolher -----------------------------------------------------

    def _construir_pagina_escolha(self, atrasos: list[SaldoAtrasoResumo]) -> QWidget:
        pagina = QWidget()

        titulo = QLabel("Lembretes em lote")
        titulo.setProperty("papel", "titulo")
        dica = QLabel(
            "Marque os clientes que vão receber o lembrete. O sistema abre a conversa de "
            "cada um no WhatsApp, com a mensagem pronta; o envio é feito por você lá."
        )
        dica.setProperty("papel", "secundario")
        dica.setWordWrap(True)

        self._lista = QListWidget()
        self._lista.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self._lista.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for atraso in atrasos:
            texto = (
                f"{atraso.nome_principal} — {formatar_reais(atraso.total_em_aberto)} — "
                f"em atraso há {atraso.dias_desde_a_compra_mais_antiga} dias"
            )
            if atraso.telefone:
                item = QListWidgetItem(f"{texto} — {atraso.telefone}")
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, atraso)
            else:
                item = QListWidgetItem(f"{texto} — sem telefone cadastrado")
                item.setFlags(Qt.ItemFlag.NoItemFlags)  # só para constar; não dá para enviar
            self._lista.addItem(item)
        if not atrasos:
            self._lista.addItem("Nenhum cliente em atraso no momento.")
        self._lista.itemChanged.connect(lambda _item: self._atualizar_contagem())
        self._lista.itemPressed.connect(self._guardar_estado_ao_pressionar)
        self._lista.itemClicked.connect(self._alternar_ao_clicar)

        self._botao_marcar = QPushButton("Desmarcar todos")
        self._botao_marcar.clicked.connect(self._alternar_todos)
        self._botao_comecar = QPushButton("Começar")
        self._botao_comecar.setIcon(icone("BRAND_WHATSAPP"))
        self._botao_comecar.setProperty("importancia", "primaria")
        self._botao_comecar.setMinimumHeight(42)
        self._botao_comecar.clicked.connect(self._comecar)
        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.clicked.connect(self.reject)

        layout = QVBoxLayout(pagina)
        layout.addWidget(titulo)
        layout.addWidget(dica)
        layout.addWidget(self._botao_marcar)
        layout.addWidget(self._lista, 1)
        layout.addWidget(self._botao_comecar)
        layout.addWidget(botao_fechar)
        return pagina

    def _itens_com_telefone(self) -> list[QListWidgetItem]:
        itens = [self._lista.item(i) for i in range(self._lista.count())]
        return [item for item in itens if item.data(Qt.ItemDataRole.UserRole) is not None]

    def _marcados(self) -> list[SaldoAtrasoResumo]:
        return [
            item.data(Qt.ItemDataRole.UserRole)
            for item in self._itens_com_telefone()
            if item.checkState() == Qt.CheckState.Checked
        ]

    def _guardar_estado_ao_pressionar(self, item: QListWidgetItem) -> None:
        self._estado_ao_pressionar = (item, item.checkState())

    def _alternar_ao_clicar(self, item: QListWidgetItem) -> None:
        """Clicar em qualquer ponto da linha marca/desmarca, não só na caixinha.

        Se o clique foi na própria caixinha, o Qt já alternou o estado
        entre o pressionar e o soltar — aí não há nada a fazer.
        """
        item_pressionado, estado_anterior = self._estado_ao_pressionar
        self._estado_ao_pressionar = (None, None)
        if item.data(Qt.ItemDataRole.UserRole) is None:
            return
        if item is item_pressionado and item.checkState() == estado_anterior:
            marcado = estado_anterior == Qt.CheckState.Checked
            item.setCheckState(Qt.CheckState.Unchecked if marcado else Qt.CheckState.Checked)

    def _alternar_todos(self) -> None:
        itens = self._itens_com_telefone()
        marcar = len(self._marcados()) != len(itens)
        estado = Qt.CheckState.Checked if marcar else Qt.CheckState.Unchecked
        self._lista.blockSignals(True)
        for item in itens:
            item.setCheckState(estado)
        self._lista.blockSignals(False)
        self._atualizar_contagem()

    def _atualizar_contagem(self) -> None:
        itens = self._itens_com_telefone()
        quantidade = len(self._marcados())
        self._botao_comecar.setEnabled(quantidade > 0)
        self._botao_comecar.setText(
            "Começar" if quantidade == 0 else f"Começar ({quantidade} cliente{'s' if quantidade != 1 else ''})"
        )
        self._botao_marcar.setEnabled(bool(itens))
        self._botao_marcar.setText(
            "Desmarcar todos" if itens and quantidade == len(itens) else "Marcar todos"
        )

    # -- Etapa 2: enviar um por vez -------------------------------------------

    def _construir_pagina_envio(self) -> QWidget:
        pagina = QWidget()

        self._label_progresso = QLabel()
        self._label_progresso.setProperty("papel", "secundario")
        self._label_cliente = QLabel()
        self._label_cliente.setProperty("papel", "titulo")
        self._label_telefone = QLabel()

        self._campo_mensagem = QTextEdit()

        self._botao_abrir = QPushButton("Abrir no WhatsApp e ir para o próximo")
        self._botao_abrir.setIcon(icone("BRAND_WHATSAPP"))
        self._botao_abrir.setProperty("importancia", "primaria")
        self._botao_abrir.setMinimumHeight(42)
        self._botao_abrir.clicked.connect(self._abrir_e_avancar)
        botao_pular = QPushButton("Pular este cliente")
        botao_pular.clicked.connect(self._pular)
        botao_parar = QPushButton("Parar")
        botao_parar.clicked.connect(self._finalizar)

        layout_secundario = QHBoxLayout()
        layout_secundario.addWidget(botao_pular)
        layout_secundario.addWidget(botao_parar)

        layout = QVBoxLayout(pagina)
        layout.addWidget(self._label_progresso)
        layout.addWidget(self._label_cliente)
        layout.addWidget(self._label_telefone)
        layout.addWidget(QLabel("Mensagem (edite se quiser antes de abrir o WhatsApp):"))
        layout.addWidget(self._campo_mensagem, 1)
        layout.addWidget(self._botao_abrir)
        layout.addLayout(layout_secundario)
        return pagina

    def _comecar(self) -> None:
        self._fila = self._marcados()
        self._posicao = 0
        self._abertas = 0
        self._puladas = 0
        self._paginas.setCurrentIndex(1)
        self._mostrar_atual()

    def _mostrar_atual(self) -> None:
        """Monta e mostra o lembrete do cliente da vez (ou encerra, se acabou a fila)."""
        while self._posicao < len(self._fila):
            atraso = self._fila[self._posicao]
            try:
                self._lembrete_atual = lembrete_service.montar_lembrete(atraso.id, self._dias_atraso)
            except (ErroDeNegocio, ValueError) as exc:
                QMessageBox.warning(self, "Cliente pulado", f"{atraso.nome_principal}: {exc}")
            except Exception:
                logger.exception("Falha inesperada ao montar o lembrete do cliente %s.", atraso.id)
                QMessageBox.warning(
                    self, "Cliente pulado", f"Não foi possível montar o lembrete de {atraso.nome_principal}."
                )
            else:
                self._label_progresso.setText(f"Cliente {self._posicao + 1} de {len(self._fila)}")
                self._label_cliente.setText(self._lembrete_atual.nome_cliente)
                self._label_telefone.setText(f"Telefone: {self._lembrete_atual.telefone or 'não cadastrado'}")
                self._campo_mensagem.setPlainText(self._lembrete_atual.mensagem)
                ultimo = self._posicao == len(self._fila) - 1
                self._botao_abrir.setText(
                    "Abrir no WhatsApp e terminar" if ultimo else "Abrir no WhatsApp e ir para o próximo"
                )
                return
            self._puladas += 1
            self._posicao += 1
        self._finalizar()

    def _abrir_e_avancar(self) -> None:
        mensagem = self._campo_mensagem.toPlainText().strip()
        if not mensagem:
            QMessageBox.warning(self, "Mensagem vazia", "Escreva uma mensagem antes de continuar.")
            return
        if self._lembrete_atual is None or not self._lembrete_atual.telefone:
            # O telefone pode ter sido apagado depois que a lista foi montada.
            QMessageBox.warning(self, "Sem telefone", "Este cliente não tem mais telefone cadastrado.")
            self._pular()
            return
        _abrir_link(montar_link_whatsapp(normalizar_telefone(self._lembrete_atual.telefone), mensagem))
        self._abertas += 1
        self._posicao += 1
        self._mostrar_atual()

    def _pular(self) -> None:
        self._puladas += 1
        self._posicao += 1
        self._mostrar_atual()

    # -- Etapa 3: resumo -------------------------------------------------------

    def _construir_pagina_fim(self) -> QWidget:
        pagina = QWidget()
        titulo = QLabel("Lembretes concluídos")
        titulo.setProperty("papel", "titulo")
        self._label_resumo = QLabel()
        self._label_resumo.setWordWrap(True)
        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(42)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout(pagina)
        layout.addWidget(titulo)
        layout.addWidget(self._label_resumo)
        layout.addStretch()
        layout.addWidget(botao_fechar)
        return pagina

    def _finalizar(self) -> None:
        restantes = max(len(self._fila) - self._posicao, 0)
        linhas = [f"Conversas abertas no WhatsApp: {self._abertas}"]
        if self._puladas:
            linhas.append(f"Clientes pulados: {self._puladas}")
        if restantes:
            linhas.append(f"Não chegaram a ser vistos: {restantes}")
        linhas.append("")
        linhas.append("Confira no WhatsApp se cada mensagem foi mesmo enviada.")
        self._label_resumo.setText("\n".join(linhas))
        self._paginas.setCurrentIndex(2)
