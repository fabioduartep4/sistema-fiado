"""Tela de Início (painel/dashboard), visível apenas para Administrador.

No topo, uma **data** (padrão: hoje) e o botão "Atualizar". A data
escolhida define:

- os cartões de vendas e de recebidos, e a tabela "Vendas do Dia" (cada
  venda daquela data);
- o gráfico dos 7 dias que terminam nela;
- os gráficos "Maior Valor Gasto" e "Mais Contas Lançadas", que mostram o
  **mês** da data escolhida.

Os demais cartões (Em Aberto, Clientes) e as seções
"Clientes Acima do Limite de Fiado", "Clientes com Maior Atraso" e
"Movimentações Recentes" são sempre a situação atual.

"Atualizar" recarrega a tela inteira e emite ``atualizacao_solicitada``,
que a janela principal usa para procurar XMLs novos na pasta configurada
(ver ``app.views.main_window``). Clicar num cliente de qualquer tabela
abre a Ficha do Cliente.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.controllers.painel_controller import PainelController
from app.controllers.relatorio_controller import RelatorioController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.graficos import construir_grafico_barras, construir_grafico_linha
from app.utils.icons import icone
from app.utils.tabelas import (
    ajustar_altura_aos_itens,
    ajustar_altura_as_linhas,
    ajustar_colunas,
    aplicar_estado_vazio,
    item_valor,
)
from app.views.ficha_cliente_view import FichaClienteView
from app.views.lembretes_em_lote_view import LembretesEmLoteDialog

# Largura máxima do conteúdo da tela de Início — limita a coluna central
# numa janela larga (senão fica esticada de ponta a ponta, com espaço
# lateral desperdiçado) e é centralizada dentro da área de rolagem.
_LARGURA_MAXIMA_CONTEUDO = 1000


def _saudacao() -> str:
    """"Bom dia"/"Boa tarde"/"Boa noite", conforme a hora atual do sistema."""
    hora = datetime.now().hour
    if hora < 12:
        return "Bom dia"
    if hora < 18:
        return "Boa tarde"
    return "Boa noite"


class PainelInicioView(QWidget):
    """Tela de Início: painel de indicadores do negócio (somente Administrador)."""

    # Emitido pelo botão "Atualizar" do topo, para a janela principal
    # procurar XMLs novos (essa busca mora lá, junto da de abertura).
    atualizacao_solicitada = Signal()

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._controller = PainelController(usuario_logado)
        self._controller_relatorio = RelatorioController(usuario_logado)
        self._controller_cliente = ClienteController(usuario_logado)
        self._atrasos_carregados: list = []
        self._dias_atraso_carregado = 30

        titulo = QLabel("Início")
        titulo.setProperty("papel", "titulo")
        saudacao = QLabel(f"{_saudacao()}, {usuario_logado.nome.split(' ')[0]}. Aqui está o resumo do seu fiado.")
        saudacao.setProperty("papel", "secundario")

        cards = self._construir_cards()

        self._campo_data = QDateEdit(QDate(date.today()))
        self._campo_data.setCalendarPopup(True)
        self._campo_data.setDisplayFormat("dd/MM/yyyy")
        self._campo_data.setMinimumWidth(130)
        # Só recarrega quando a data termina de ser digitada, não a cada tecla.
        self._campo_data.setKeyboardTracking(False)
        self._campo_data.dateChanged.connect(lambda _data: self._carregar_dependentes_da_data())

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._atualizar_tudo)

        self._label_status_xml = QLabel("")
        self._label_status_xml.setProperty("papel", "secundario")

        layout_periodo = QHBoxLayout()
        layout_periodo.addWidget(QLabel("Data:"))
        layout_periodo.addWidget(self._campo_data)
        layout_periodo.addWidget(botao_atualizar)
        layout_periodo.addWidget(self._label_status_xml)
        layout_periodo.addStretch()

        caixa_vendas_do_dia = self._construir_caixa_vendas_do_dia()
        caixa_vendas_hoje = self._construir_caixa_vendas_hoje()
        caixa_acima_do_limite = self._construir_caixa_acima_do_limite()
        caixa_maior_atraso = self._construir_caixa_maior_atraso()
        caixa_movimentacoes = self._construir_caixa_movimentacoes()

        # Tudo — as caixas fixas e os gráficos dependentes do período —
        # dentro do MESMO QScrollArea, para a rolagem do mouse funcionar de
        # forma única na tela inteira (antes, as caixas ficavam fora da
        # área de rolagem, como se fossem uma "página" à parte dos
        # gráficos, o que ficava estranho). Só o widget interno
        # (``_widget_periodo``) é limpo/reconstruído a cada período — as
        # caixas continuam fixas, sem perder o filtro delas.
        self._area_scroll = QScrollArea()
        self._area_scroll.setWidgetResizable(True)
        self._container = QWidget()
        # Largura máxima + margens laterais menores: numa janela larga, o
        # conteúdo esticado de ponta a ponta ficava com espaço lateral
        # desperdiçado e uma coluna "gorda" demais — mais confortável de
        # ler e rolar centralizado, com uma largura razoável.
        self._container.setMaximumWidth(_LARGURA_MAXIMA_CONTEUDO)
        layout_scroll = QVBoxLayout(self._container)
        layout_scroll.setContentsMargins(4, 8, 4, 8)
        layout_scroll.addWidget(cards)
        layout_scroll.addWidget(caixa_vendas_do_dia)
        layout_scroll.addWidget(caixa_vendas_hoje)
        layout_scroll.addWidget(caixa_acima_do_limite)
        layout_scroll.addWidget(caixa_maior_atraso)
        layout_scroll.addWidget(caixa_movimentacoes)

        self._widget_periodo = QWidget()
        self._layout_conteudo = QVBoxLayout(self._widget_periodo)
        layout_scroll.addWidget(self._widget_periodo)

        # Centraliza self._container (largura limitada) dentro da área de
        # rolagem (que continua ocupando a largura toda da tela).
        widget_centralizado = QWidget()
        layout_centralizado = QHBoxLayout(widget_centralizado)
        layout_centralizado.setContentsMargins(0, 0, 0, 0)
        layout_centralizado.addStretch()
        layout_centralizado.addWidget(self._container)
        layout_centralizado.addStretch()

        self._area_scroll.setWidget(widget_centralizado)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(saudacao)
        layout.addLayout(layout_periodo)
        layout.addWidget(self._area_scroll)
        self.setLayout(layout)

        self.recarregar()

    def _data_selecionada(self) -> date:
        return self._campo_data.date().toPython()

    def _carregar_dependentes_da_data(self) -> None:
        self._carregar_vendas_do_dia()
        self._carregar()

    def recarregar(self) -> None:
        """Recarrega a tela inteira (sem procurar XMLs novos)."""
        self._carregar_cards()
        self._carregar_dependentes_da_data()
        self._carregar_acima_do_limite()
        self._carregar_maiores_atrasos()
        self._carregar_movimentacoes()

    def _atualizar_tudo(self) -> None:
        self.recarregar()
        self._label_status_xml.setText("Procurando XMLs novos...")
        self.atualizacao_solicitada.emit()

    def informar_resultado_xml(self, quantidade: int) -> None:
        """Mostra, ao lado do botão Atualizar, o resultado da busca de XMLs."""
        if quantidade <= 0:
            self._label_status_xml.setText("Nenhum XML novo.")
        elif quantidade == 1:
            self._label_status_xml.setText("1 XML novo encontrado.")
        else:
            self._label_status_xml.setText(f"{quantidade} XMLs novos encontrados.")

    def _limpar_conteudo(self) -> None:
        while self._layout_conteudo.count():
            item = self._layout_conteudo.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _abrir_ficha(self, cliente_id: str) -> None:
        """Abre a Ficha do Cliente — é ali que fica o botão "Enviar Lembrete"
        agora, em vez de um botão por linha nas tabelas deste painel."""
        dialogo = FichaClienteView(self._usuario_logado, cliente_id, self)
        dialogo.exec()
        self._carregar_cards()
        self._carregar_vendas_do_dia()
        self._carregar_acima_do_limite()
        self._carregar_maiores_atrasos()

    # -- Cartões de indicador ---------------------------------------------------
    #
    # Em Aberto e Clientes são sempre a situação atual. Os cartões de vendas
    # e de recebidos seguem a data escolhida no topo (ver
    # _carregar_vendas_do_dia).

    def _construir_cards(self) -> QWidget:
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 0, 0, 0)

        self._card_em_aberto, self._label_em_aberto_valor, self._label_em_aberto_sub = self._criar_card(
            "EM ABERTO"
        )
        self._card_vendas_hoje, self._label_vendas_hoje_valor, self._label_vendas_hoje_sub = (
            self._criar_card("VENDAS HOJE")
        )
        self._card_clientes, self._label_clientes_valor, self._label_clientes_sub = self._criar_card(
            "CLIENTES"
        )
        self._card_recebidos, self._label_recebidos_valor, self._label_recebidos_sub = self._criar_card(
            "RECEBIDOS HOJE"
        )

        self._label_vendas_titulo = self._card_vendas_hoje.findChild(QLabel)
        self._label_recebidos_titulo = self._card_recebidos.findChild(QLabel)

        for card in (
            self._card_em_aberto,
            self._card_vendas_hoje,
            self._card_clientes,
            self._card_recebidos,
        ):
            layout.addWidget(card)

        return linha

    @staticmethod
    def _criar_card(titulo: str) -> tuple[QFrame, QLabel, QLabel]:
        card = QFrame()
        card.setProperty("papel", "card")
        layout = QVBoxLayout(card)

        label_titulo = QLabel(titulo)
        label_titulo.setProperty("papel", "secundario")
        label_valor = QLabel("-")
        label_valor.setStyleSheet("font-size: 22px; font-weight: 700;")
        label_sub = QLabel("")
        label_sub.setProperty("papel", "secundario")

        layout.addWidget(label_titulo)
        layout.addWidget(label_valor)
        layout.addWidget(label_sub)
        return card, label_valor, label_sub

    def _carregar_cards(self) -> None:
        try:
            saldos_painel = self._controller_relatorio.obter_saldos()
            saldos_em_aberto = self._controller_relatorio.listar_saldos_em_aberto()
            total_clientes = self._controller_cliente.contar_ativos()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar os indicadores do Início.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar os indicadores.")
            return

        self._label_em_aberto_valor.setText(f"{formatar_reais(saldos_painel.total_em_aberto_geral)}")
        self._label_em_aberto_sub.setText(f"{len(saldos_em_aberto)} clientes")

        self._label_clientes_valor.setText(str(total_clientes))
        self._label_clientes_sub.setText(f"{len(saldos_em_aberto)} com saldo")

    # -- Vendas do Dia ----------------------------------------------------------
    #
    # Tudo aqui segue a data escolhida no topo: o cartão de vendas, a
    # tabela com cada venda do dia e o gráfico dos 7 dias até ela — os
    # três vêm da mesma consulta (_carregar_vendas_do_dia).

    def _construir_caixa_vendas_do_dia(self) -> QGroupBox:
        self._caixa_vendas_do_dia = QGroupBox("Vendas do Dia")

        self._tabela_vendas_do_dia = QTableWidget(0, 4)
        self._tabela_vendas_do_dia.setHorizontalHeaderLabels(["Hora", "Cliente", "Valor", "Origem"])
        self._tabela_vendas_do_dia.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_vendas_do_dia.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._tabela_vendas_do_dia.cellDoubleClicked.connect(self._abrir_ficha_da_venda)
        ajustar_colunas(self._tabela_vendas_do_dia, 1)  # Cliente

        self._label_vendas_do_dia_vazio = QLabel("Nenhuma venda nesta data.")
        self._label_vendas_do_dia_vazio.setProperty("papel", "secundario")
        self._label_vendas_do_dia_vazio.setVisible(False)

        layout_caixa = QVBoxLayout(self._caixa_vendas_do_dia)
        layout_caixa.addWidget(self._tabela_vendas_do_dia)
        layout_caixa.addWidget(self._label_vendas_do_dia_vazio)
        return self._caixa_vendas_do_dia

    def _abrir_ficha_da_venda(self, linha: int, _coluna: int) -> None:
        item = self._tabela_vendas_do_dia.item(linha, 0)
        if item is not None:
            self._abrir_ficha(item.data(Qt.ItemDataRole.UserRole))

    def _construir_caixa_vendas_hoje(self) -> QGroupBox:
        # O total do dia já aparece no cartão de vendas do cabeçalho — aqui
        # fica só o gráfico dos 7 dias, sem repetir o número.
        self._caixa_vendas_7_dias = QGroupBox("Vendas dos Últimos 7 Dias")

        botao_atualizar_vendas_hoje = QPushButton("Atualizar")
        botao_atualizar_vendas_hoje.setIcon(icone("REFRESH"))
        botao_atualizar_vendas_hoje.clicked.connect(self._carregar_vendas_do_dia)

        layout_topo = QHBoxLayout()
        layout_topo.addStretch()
        layout_topo.addWidget(botao_atualizar_vendas_hoje)

        self._layout_grafico_vendas_hoje = QVBoxLayout()

        layout_caixa = QVBoxLayout(self._caixa_vendas_7_dias)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addLayout(self._layout_grafico_vendas_hoje)
        return self._caixa_vendas_7_dias

    def _carregar_vendas_do_dia(self) -> None:
        dia = self._data_selecionada()
        try:
            resumo = self._controller_relatorio.obter_vendas_do_dia(dia)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar as vendas do dia %s.", dia)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar as vendas do dia.")
            return

        eh_hoje = dia == date.today()
        data_formatada = dia.strftime("%d/%m/%Y")

        # Cartão
        self._label_vendas_titulo.setText("VENDAS HOJE" if eh_hoje else f"VENDAS EM {dia.strftime('%d/%m')}")
        self._label_vendas_hoje_valor.setText(formatar_reais(resumo.total_vendido))
        self._label_vendas_hoje_sub.setText(
            "1 venda" if resumo.quantidade == 1 else f"{resumo.quantidade} vendas"
        )
        self._label_recebidos_titulo.setText(
            "RECEBIDOS HOJE" if eh_hoje else f"RECEBIDOS EM {dia.strftime('%d/%m')}"
        )
        self._label_recebidos_valor.setText(formatar_reais(resumo.total_recebido))
        self._label_recebidos_sub.setText(
            "1 pagamento"
            if resumo.quantidade_recebimentos == 1
            else f"{resumo.quantidade_recebimentos} pagamentos"
        )

        # Tabela
        self._caixa_vendas_do_dia.setTitle(
            f"Vendas de Hoje ({data_formatada})" if eh_hoje else f"Vendas do Dia {data_formatada}"
        )
        self._tabela_vendas_do_dia.setRowCount(len(resumo.vendas))
        for linha, venda in enumerate(resumo.vendas):
            item_hora = QTableWidgetItem(venda.data_hora.strftime("%H:%M"))
            item_hora.setData(Qt.ItemDataRole.UserRole, venda.cliente_id)
            self._tabela_vendas_do_dia.setItem(linha, 0, item_hora)
            self._tabela_vendas_do_dia.setItem(linha, 1, QTableWidgetItem(venda.cliente_nome))
            self._tabela_vendas_do_dia.setItem(linha, 2, item_valor(formatar_reais(venda.valor)))
            self._tabela_vendas_do_dia.setItem(
                linha, 3, QTableWidgetItem("XML" if venda.via_xml else "Manual")
            )
        ajustar_altura_as_linhas(self._tabela_vendas_do_dia)
        aplicar_estado_vazio(self._tabela_vendas_do_dia, self._label_vendas_do_dia_vazio)

        # Gráfico dos 7 dias até a data
        self._caixa_vendas_7_dias.setTitle(
            "Vendas dos Últimos 7 Dias" if eh_hoje else f"Vendas dos 7 Dias até {data_formatada}"
        )
        while self._layout_grafico_vendas_hoje.count():
            item = self._layout_grafico_vendas_hoje.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._layout_grafico_vendas_hoje.addWidget(
            construir_grafico_linha(
                "Total Vendido (R$)",
                [p.dia for p in resumo.vendas_ultimos_7_dias],
                [float(p.total) for p in resumo.vendas_ultimos_7_dias],
            )
        )

    # -- Clientes com Maior Atraso (ex-aba "Lembretes") ----------------------
    #
    # Fora do ciclo de recarregamento por período (_carregar/_limpar_conteudo)
    # de propósito: tem seu próprio filtro (dias em atraso) e não deve ser
    # reconstruída/perder o valor do filtro sempre que o período do resto do
    # painel for atualizado.

    def _construir_caixa_maior_atraso(self) -> QGroupBox:
        caixa = QGroupBox("Clientes com Maior Atraso")

        self._campo_dias_atraso = QSpinBox()
        self._campo_dias_atraso.setRange(1, 365)
        self._campo_dias_atraso.setValue(30)
        self._campo_dias_atraso.setSuffix(" dias")

        botao_atualizar_atraso = QPushButton("Atualizar")
        botao_atualizar_atraso.setIcon(icone("REFRESH"))
        botao_atualizar_atraso.clicked.connect(self._carregar_maiores_atrasos)

        layout_filtro = QHBoxLayout()
        layout_filtro.addWidget(QLabel("Considerar em atraso compras com mais de:"))
        layout_filtro.addWidget(self._campo_dias_atraso)
        self._botao_lembretes_em_lote = QPushButton("Lembretes em lote")
        self._botao_lembretes_em_lote.setIcon(icone("BRAND_WHATSAPP"))
        self._botao_lembretes_em_lote.clicked.connect(self._abrir_lembretes_em_lote)

        layout_filtro.addStretch()
        layout_filtro.addWidget(self._botao_lembretes_em_lote)
        layout_filtro.addWidget(botao_atualizar_atraso)

        self._tabela_atrasos = QTableWidget(0, 6)
        self._tabela_atrasos.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Em atraso há", "Total Atrasado", "Total em Aberto", ""]
        )
        self._tabela_atrasos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_atrasos.cellDoubleClicked.connect(
            lambda linha, _coluna: self._abrir_ficha(self._tabela_atrasos.item(linha, 0).data(Qt.ItemDataRole.UserRole))
        )
        ajustar_colunas(self._tabela_atrasos, 0)  # Cliente

        self._label_atrasos_vazio = QLabel("Nenhum cliente com saldo atrasado no momento.")
        self._label_atrasos_vazio.setProperty("papel", "secundario")
        self._label_atrasos_vazio.setVisible(False)

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_filtro)
        layout_caixa.addWidget(QLabel(
            "Sem data de vencimento própria no fiado, a data da compra é usada como "
            "referência: quanto mais antiga uma compra ainda em aberto, mais atrasada conta."
        ))
        layout_caixa.addWidget(self._tabela_atrasos)
        layout_caixa.addWidget(self._label_atrasos_vazio)
        return caixa

    def _abrir_lembretes_em_lote(self) -> None:
        """Lembrete para vários clientes da lista de atrasos, um por vez."""
        LembretesEmLoteDialog(self._atrasos_carregados, self._dias_atraso_carregado, self).exec()

    def _carregar_maiores_atrasos(self) -> None:
        try:
            saldos = self._controller_relatorio.listar_saldos_em_atraso(self._campo_dias_atraso.value())
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de clientes com maior atraso.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar os clientes com maior atraso."
            )
            return

        self._atrasos_carregados = saldos
        self._dias_atraso_carregado = self._campo_dias_atraso.value()
        self._botao_lembretes_em_lote.setEnabled(bool(saldos))
        self._tabela_atrasos.setRowCount(len(saldos))
        for linha, saldo in enumerate(saldos):
            item_nome = QTableWidgetItem(saldo.nome_principal)
            item_nome.setData(Qt.ItemDataRole.UserRole, saldo.id)
            self._tabela_atrasos.setItem(linha, 0, item_nome)
            self._tabela_atrasos.setItem(linha, 1, QTableWidgetItem(saldo.telefone or "-"))
            self._tabela_atrasos.setItem(
                linha, 2, QTableWidgetItem(f"{saldo.dias_desde_a_compra_mais_antiga} dias")
            )
            self._tabela_atrasos.setItem(
                linha, 3, item_valor(formatar_reais(saldo.total_em_atraso))
            )
            self._tabela_atrasos.setItem(
                linha, 4, item_valor(formatar_reais(saldo.total_em_aberto))
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, s=saldo: self._abrir_ficha(s.id))
            self._tabela_atrasos.setCellWidget(linha, 5, botao_ver)

        ajustar_altura_as_linhas(self._tabela_atrasos)
        aplicar_estado_vazio(self._tabela_atrasos, self._label_atrasos_vazio)

    # -- Clientes Acima do Limite de Fiado -----------------------------------
    #
    # Mesmo raciocínio da caixa de maior atraso: fora do ciclo de
    # recarregamento por período, com filtro/atualização próprios.

    def _construir_caixa_acima_do_limite(self) -> QGroupBox:
        caixa = QGroupBox("Clientes Acima do Limite de Fiado")

        botao_atualizar_limite = QPushButton("Atualizar")
        botao_atualizar_limite.setIcon(icone("REFRESH"))
        botao_atualizar_limite.clicked.connect(self._carregar_acima_do_limite)

        layout_topo = QHBoxLayout()
        layout_topo.addWidget(QLabel(
            "Clientes com limite de fiado definido (ver Editar Cliente) cujo saldo "
            "em aberto já passou do combinado."
        ))
        layout_topo.addStretch()
        layout_topo.addWidget(botao_atualizar_limite)

        self._tabela_acima_do_limite = QTableWidget(0, 6)
        self._tabela_acima_do_limite.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Limite", "Total em Aberto", "Excesso", ""]
        )
        self._tabela_acima_do_limite.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_acima_do_limite.cellDoubleClicked.connect(
            lambda linha, _coluna: self._abrir_ficha(
                self._tabela_acima_do_limite.item(linha, 0).data(Qt.ItemDataRole.UserRole)
            )
        )
        ajustar_colunas(self._tabela_acima_do_limite, 0)  # Cliente

        self._label_acima_limite_vazio = QLabel("Nenhum cliente acima do limite no momento.")
        self._label_acima_limite_vazio.setProperty("papel", "secundario")
        self._label_acima_limite_vazio.setVisible(False)

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addWidget(self._tabela_acima_do_limite)
        layout_caixa.addWidget(self._label_acima_limite_vazio)
        return caixa

    def _carregar_acima_do_limite(self) -> None:
        try:
            clientes = self._controller_relatorio.listar_clientes_acima_do_limite()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de clientes acima do limite.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar os clientes acima do limite."
            )
            return

        self._tabela_acima_do_limite.setRowCount(len(clientes))
        for linha, item in enumerate(clientes):
            item_nome = QTableWidgetItem(item.nome_principal)
            item_nome.setData(Qt.ItemDataRole.UserRole, item.id)
            self._tabela_acima_do_limite.setItem(linha, 0, item_nome)
            self._tabela_acima_do_limite.setItem(linha, 1, QTableWidgetItem(item.telefone or "-"))
            self._tabela_acima_do_limite.setItem(
                linha, 2, item_valor(formatar_reais(item.limite_fiado))
            )
            self._tabela_acima_do_limite.setItem(
                linha, 3, item_valor(formatar_reais(item.total_em_aberto))
            )
            self._tabela_acima_do_limite.setItem(
                linha, 4, item_valor(formatar_reais(item.excesso))
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, i=item: self._abrir_ficha(i.id))
            self._tabela_acima_do_limite.setCellWidget(linha, 5, botao_ver)

        ajustar_altura_as_linhas(self._tabela_acima_do_limite)
        aplicar_estado_vazio(self._tabela_acima_do_limite, self._label_acima_limite_vazio)

    # -- Gráficos dependentes do período --------------------------------------

    def _carregar(self) -> None:
        self._limpar_conteudo()

        # Num dia só esses dois gráficos quase não teriam informação: mostram
        # o mês inteiro da data escolhida.
        dia = self._data_selecionada()
        data_inicio = dia.replace(day=1)
        data_fim = dia.replace(day=calendar.monthrange(dia.year, dia.month)[1])
        mes = dia.strftime("%m/%Y")

        try:
            painel = self._controller.obter_painel(data_inicio, data_fim)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o painel", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o painel de início.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o painel de início.")
            return

        # Os dois gráficos do mês lado a lado: um embaixo do outro, tomavam
        # duas telas de rolagem para pouca informação.
        linha_graficos = QWidget()
        layout_graficos = QHBoxLayout(linha_graficos)
        layout_graficos.setContentsMargins(0, 0, 0, 0)

        if painel.maior_valor_gasto:
            caixa = QGroupBox(f"Maior Valor Gasto em {mes}")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_barras(
                    "Valor Gasto (R$)",
                    [c.nome_principal for c in painel.maior_valor_gasto],
                    [float(c.valor) for c in painel.maior_valor_gasto],
                )
            )
            layout_graficos.addWidget(caixa)

        if painel.mais_contas_lancadas:
            caixa = QGroupBox(f"Mais Contas Lançadas em {mes}")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_barras(
                    "Nº de Contas",
                    [c.nome_principal for c in painel.mais_contas_lancadas],
                    [float(c.quantidade) for c in painel.mais_contas_lancadas],
                )
            )
            layout_graficos.addWidget(caixa)

        if layout_graficos.count():
            self._layout_conteudo.addWidget(linha_graficos)
        else:
            linha_graficos.deleteLater()

        self._layout_conteudo.addStretch()

    # -- Movimentações Recentes -------------------------------------------------
    #
    # Fora do ciclo de recarregamento por período: são as últimas vendas e
    # recebimentos do sistema todo, não filtradas por data — mesma fonte
    # da aba "Histórico" unificada (ver RelatorioController.listar_movimentacoes).

    def _construir_caixa_movimentacoes(self) -> QGroupBox:
        caixa = QGroupBox("Movimentações Recentes")

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar_movimentacoes)

        layout_topo = QHBoxLayout()
        layout_topo.addStretch()
        layout_topo.addWidget(botao_atualizar)

        self._lista_movimentacoes = QListWidget()

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addWidget(self._lista_movimentacoes)
        return caixa

    def _carregar_movimentacoes(self) -> None:
        try:
            itens = self._controller_relatorio.listar_movimentacoes(limite=12)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar as movimentações recentes.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar as movimentações recentes."
            )
            return

        self._lista_movimentacoes.clear()
        if not itens:
            self._lista_movimentacoes.addItem("Nenhuma movimentação registrada.")
            ajustar_altura_aos_itens(self._lista_movimentacoes)
            return
        for item in itens:
            sinal = "+" if item.tipo == "Venda" else "-"
            texto = (
                f"{item.data_hora.strftime('%d/%m %H:%M')} — {item.cliente_nome} — "
                f"{item.tipo}: {sinal} {formatar_reais(item.valor)}{item.marca}"
            )
            self._lista_movimentacoes.addItem(texto)
        ajustar_altura_aos_itens(self._lista_movimentacoes)
