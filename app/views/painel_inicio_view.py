"""Tela de Início (painel/dashboard), visível apenas para Administrador.

Cabeçalho com uma saudação e quatro cartões de indicador (Em Aberto,
Vendas Hoje, Clientes, Acima do Limite — nenhum depende de período,
sempre a situação atual). Clicar num cliente das tabelas "Acima do
Limite"/"Maior Atraso" abre a Ficha do Cliente (onde mora o botão
"Enviar Lembrete" agora — ver ``app.views.ficha_cliente_view``), em vez
do antigo botão de lembrete embutido na própria linha da tabela.

Mostra, para um período selecionável (padrão: mês atual): os clientes que
mais gastaram (maior valor total em compras) e os que mais lançaram
contas (mais vezes foram ao mercado) — os únicos dois indicadores que
realmente dependem do período escolhido. "Total em aberto", "Evolução de
Vendas" e "Clientes com Maior Saldo em Aberto" (situação atual, não
histórico de um intervalo) ficam na aba "Saldos" — ver
``app.views.saldos_view``.

Também traz seções fora do ciclo de recarregamento por período (são
sobre o dia atual ou a situação atual das contas, não histórico de um
intervalo — cada uma com seu próprio filtro/atualização independente),
nesta ordem:

- "Vendas de Hoje" — gráfico com os últimos 7 dias (o total do dia já
  aparece no cartão "Vendas Hoje" do cabeçalho, não repetido aqui).
- "Clientes Acima do Limite de Fiado" — clientes com um limite de compra
  no fiado definido (``Cliente.limite_fiado``) cujo saldo em aberto já
  passou desse limite.
- "Clientes com Maior Atraso" — antes era uma sub-aba pouco visível
  dentro de "Histórico e Relatórios"; trazida pra cá para ficar visível
  assim que o sistema abre.
- "Movimentações Recentes" — últimas vendas e recebimentos do sistema
  todo, combinados (mesma fonte da aba Histórico unificada, ver
  ``RelatorioController.listar_movimentacoes``).
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QDate, Qt
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
from app.utils.tabelas import aplicar_estado_vazio, ajustar_colunas
from app.views.ficha_cliente_view import FichaClienteView

# Altura mínima das tabelas de "Clientes com Maior Atraso" e "Clientes
# Acima do Limite de Fiado", calculada para caber pelo menos 10 linhas
# visíveis sem precisar rolar dentro da própria tabela (~32px por linha +
# ~34px do cabeçalho) — a caixa toda já está dentro da área de rolagem da
# tela, então crescer aqui não atrapalha, só evita ficar pequena demais
# com poucos clientes visíveis de cada vez.
_ALTURA_TABELA_10_LINHAS = 10 * 32 + 34

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

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._controller = PainelController(usuario_logado)
        self._controller_relatorio = RelatorioController(usuario_logado)
        self._controller_cliente = ClienteController(usuario_logado)

        titulo = QLabel("Início")
        titulo.setProperty("papel", "titulo")
        saudacao = QLabel(f"{_saudacao()}, {usuario_logado.nome.split(' ')[0]}. Aqui está o resumo do seu fiado.")
        saudacao.setProperty("papel", "secundario")

        cards = self._construir_cards()

        hoje = date.today()
        self._campo_data_inicio = QDateEdit(QDate(hoje.replace(day=1)))
        self._campo_data_inicio.setCalendarPopup(True)
        self._campo_data_inicio.setDisplayFormat("dd/MM/yyyy")

        self._campo_data_fim = QDateEdit(QDate(hoje))
        self._campo_data_fim.setCalendarPopup(True)
        self._campo_data_fim.setDisplayFormat("dd/MM/yyyy")

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar)

        layout_periodo = QHBoxLayout()
        layout_periodo.addWidget(QLabel("Período:"))
        layout_periodo.addWidget(self._campo_data_inicio)
        layout_periodo.addWidget(QLabel("até"))
        layout_periodo.addWidget(self._campo_data_fim)
        layout_periodo.addWidget(botao_atualizar)
        layout_periodo.addStretch()

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

        self._carregar()
        self._carregar_cards()
        self._carregar_vendas_hoje()
        self._carregar_acima_do_limite()
        self._carregar_maiores_atrasos()
        self._carregar_movimentacoes()

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
        self._carregar_acima_do_limite()
        self._carregar_maiores_atrasos()

    # -- Cartões de indicador ---------------------------------------------------
    #
    # Nenhum depende de período — sempre a situação atual, igual às caixas
    # de Vendas de Hoje/Acima do Limite/Maior Atraso logo abaixo.

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
        self._card_acima_limite, self._label_acima_limite_valor, self._label_acima_limite_sub = (
            self._criar_card("ACIMA DO LIMITE")
        )

        for card in (
            self._card_em_aberto,
            self._card_vendas_hoje,
            self._card_clientes,
            self._card_acima_limite,
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
            vendas_hoje = self._controller_relatorio.obter_vendas_hoje()
            total_clientes = self._controller_cliente.contar_ativos()
            acima_do_limite = self._controller_relatorio.listar_clientes_acima_do_limite()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar os indicadores do Início.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar os indicadores.")
            return

        self._label_em_aberto_valor.setText(f"{formatar_reais(saldos_painel.total_em_aberto_geral)}")
        self._label_em_aberto_sub.setText(f"{len(saldos_em_aberto)} clientes")

        self._label_vendas_hoje_valor.setText(f"{formatar_reais(vendas_hoje.total_vendido_hoje)}")
        self._label_vendas_hoje_sub.setText(f"{vendas_hoje.quantidade_vendida_hoje} lançamentos")

        self._label_clientes_valor.setText(str(total_clientes))
        self._label_clientes_sub.setText(f"{len(saldos_em_aberto)} com saldo")

        self._label_acima_limite_valor.setText(str(len(acima_do_limite)))
        self._label_acima_limite_sub.setText(
            "precisam atenção" if acima_do_limite else "nenhum no momento"
        )

    # -- Vendas de Hoje -------------------------------------------------------
    #
    # Fora do ciclo de recarregamento por período de propósito: "hoje" e
    # "últimos 7 dias" já são, por definição, uma janela fixa — não haveria
    # sentido em oferecer um período selecionável pra eles.

    def _construir_caixa_vendas_hoje(self) -> QGroupBox:
        # O total de hoje já aparece no cartão "Vendas Hoje" do cabeçalho —
        # aqui fica só o gráfico dos últimos 7 dias, sem repetir o número.
        caixa = QGroupBox("Vendas dos Últimos 7 Dias")

        botao_atualizar_vendas_hoje = QPushButton("Atualizar")
        botao_atualizar_vendas_hoje.setIcon(icone("REFRESH"))
        botao_atualizar_vendas_hoje.clicked.connect(self._carregar_vendas_hoje)

        layout_topo = QHBoxLayout()
        layout_topo.addStretch()
        layout_topo.addWidget(botao_atualizar_vendas_hoje)

        self._layout_grafico_vendas_hoje = QVBoxLayout()

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addLayout(self._layout_grafico_vendas_hoje)
        return caixa

    def _carregar_vendas_hoje(self) -> None:
        while self._layout_grafico_vendas_hoje.count():
            item = self._layout_grafico_vendas_hoje.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            resumo = self._controller_relatorio.obter_vendas_hoje()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar as vendas de hoje.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar as vendas de hoje.")
            return

        grafico = construir_grafico_linha(
            "Total Vendido (R$)",
            [p.dia for p in resumo.vendas_ultimos_7_dias],
            [float(p.total) for p in resumo.vendas_ultimos_7_dias],
        )
        self._layout_grafico_vendas_hoje.addWidget(grafico)

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
        layout_filtro.addStretch()
        layout_filtro.addWidget(botao_atualizar_atraso)

        self._tabela_atrasos = QTableWidget(0, 6)
        self._tabela_atrasos.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Em atraso há", "Total Atrasado", "Total em Aberto", ""]
        )
        self._tabela_atrasos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_atrasos.setMinimumHeight(_ALTURA_TABELA_10_LINHAS)
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
                linha, 3, QTableWidgetItem(f"{formatar_reais(saldo.total_em_atraso)}")
            )
            self._tabela_atrasos.setItem(
                linha, 4, QTableWidgetItem(f"{formatar_reais(saldo.total_em_aberto)}")
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, s=saldo: self._abrir_ficha(s.id))
            self._tabela_atrasos.setCellWidget(linha, 5, botao_ver)

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
        self._tabela_acima_do_limite.setMinimumHeight(_ALTURA_TABELA_10_LINHAS)
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
                linha, 2, QTableWidgetItem(f"{formatar_reais(item.limite_fiado)}")
            )
            self._tabela_acima_do_limite.setItem(
                linha, 3, QTableWidgetItem(f"{formatar_reais(item.total_em_aberto)}")
            )
            self._tabela_acima_do_limite.setItem(
                linha, 4, QTableWidgetItem(f"{formatar_reais(item.excesso)}")
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, i=item: self._abrir_ficha(i.id))
            self._tabela_acima_do_limite.setCellWidget(linha, 5, botao_ver)

        aplicar_estado_vazio(self._tabela_acima_do_limite, self._label_acima_limite_vazio)

    # -- Gráficos dependentes do período --------------------------------------

    def _carregar(self) -> None:
        self._limpar_conteudo()

        data_inicio = self._campo_data_inicio.date().toPython()
        data_fim = self._campo_data_fim.date().toPython()

        try:
            painel = self._controller.obter_painel(data_inicio, data_fim)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar o painel", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar o painel de início.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar o painel de início.")
            return

        if painel.maior_valor_gasto:
            caixa = QGroupBox("Maior Valor Gasto no Período")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_barras(
                    "Valor Gasto (R$)",
                    [c.nome_principal for c in painel.maior_valor_gasto],
                    [float(c.valor) for c in painel.maior_valor_gasto],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        if painel.mais_contas_lancadas:
            caixa = QGroupBox("Mais Contas Lançadas no Período")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_barras(
                    "Nº de Contas",
                    [c.nome_principal for c in painel.mais_contas_lancadas],
                    [float(c.quantidade) for c in painel.mais_contas_lancadas],
                )
            )
            self._layout_conteudo.addWidget(caixa)

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
            return
        for item in itens:
            sinal = "+" if item.tipo == "Venda" else "-"
            marca_estorno = " [Estornado]" if item.estornado else ""
            texto = (
                f"{item.data_hora.strftime('%d/%m %H:%M')} — {item.cliente_nome} — "
                f"{item.tipo}: {sinal} {formatar_reais(item.valor)}{marca_estorno}"
            )
            self._lista_movimentacoes.addItem(texto)
