"""Tela de Início (painel/dashboard), visível apenas para Administrador.

Mostra, para um período selecionável (padrão: mês atual): os clientes que
mais gastaram (maior valor total em compras), os que mais lançaram contas
(mais vezes foram ao mercado), a evolução de vendas dos últimos 6 meses,
o total geral em aberto do negócio e os clientes com maior saldo em
aberto.

Também traz duas seções com o botão de enviar lembrete por WhatsApp,
ambas fora do ciclo de recarregamento por período (são sobre a situação
atual das contas, não histórico de um intervalo — cada uma com seu
próprio filtro/atualização independente):

- "Clientes com Maior Atraso" — antes era uma sub-aba pouco visível
  dentro de "Histórico e Relatórios"; trazida pra cá para ficar visível
  assim que o sistema abre.
- "Clientes Acima do Limite de Fiado" — clientes com um limite de compra
  no fiado definido (``Cliente.limite_fiado``) cujo saldo em aberto já
  passou desse limite.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
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
from app.controllers.painel_controller import PainelController
from app.controllers.relatorio_controller import RelatorioController
from app.services.auth_service import UsuarioAutenticado
from app.services.relatorio_service import ClienteAcimaDoLimiteResumo, SaldoAtrasoResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.whatsapp import montar_mensagem_lembrete_limite, montar_mensagem_lembrete_saldo
from app.views.relatorio_view import LembreteWhatsAppDialog

# Altura mínima das tabelas de "Clientes com Maior Atraso" e "Clientes
# Acima do Limite de Fiado", calculada para caber pelo menos 10 linhas
# visíveis sem precisar rolar dentro da própria tabela (~32px por linha +
# ~34px do cabeçalho) — a caixa toda já está dentro da área de rolagem da
# tela, então crescer aqui não atrapalha, só evita ficar pequena demais
# com poucos clientes visíveis de cada vez.
_ALTURA_TABELA_10_LINHAS = 10 * 32 + 34


def _construir_grafico_barras(titulo_serie: str, rotulos: list[str], valores: list[float]) -> QChartView:
    """Monta um gráfico de barras verticais simples (uma série)."""
    conjunto = QBarSet(titulo_serie)
    conjunto.append(valores)

    serie = QBarSeries()
    serie.append(conjunto)

    grafico = QChart()
    grafico.addSeries(serie)
    grafico.legend().hide()

    eixo_categorias = QBarCategoryAxis()
    eixo_categorias.append(rotulos)
    grafico.addAxis(eixo_categorias, Qt.AlignmentFlag.AlignBottom)
    serie.attachAxis(eixo_categorias)

    eixo_valores = QValueAxis()
    grafico.addAxis(eixo_valores, Qt.AlignmentFlag.AlignLeft)
    serie.attachAxis(eixo_valores)

    view = QChartView(grafico)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(280)
    return view


def _construir_grafico_linha(titulo_serie: str, rotulos: list[str], valores: list[float]) -> QChartView:
    """Monta um gráfico de linha simples (uma série), para séries temporais."""
    serie = QLineSeries()
    serie.setName(titulo_serie)
    for indice, valor in enumerate(valores):
        serie.append(indice, valor)

    grafico = QChart()
    grafico.addSeries(serie)
    grafico.legend().hide()

    eixo_categorias = QBarCategoryAxis()
    eixo_categorias.append(rotulos)
    grafico.addAxis(eixo_categorias, Qt.AlignmentFlag.AlignBottom)
    serie.attachAxis(eixo_categorias)

    eixo_valores = QValueAxis()
    grafico.addAxis(eixo_valores, Qt.AlignmentFlag.AlignLeft)
    serie.attachAxis(eixo_valores)

    view = QChartView(grafico)
    view.setRenderHint(QPainter.RenderHint.Antialiasing)
    view.setMinimumHeight(280)
    return view


class PainelInicioView(QWidget):
    """Tela de Início: painel de indicadores do negócio (somente Administrador)."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = PainelController(usuario_logado)
        self._controller_relatorio = RelatorioController(usuario_logado)

        titulo = QLabel("Início")
        titulo.setStyleSheet("font-size: 18px; font-weight: bold;")

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

        caixa_maior_atraso = self._construir_caixa_maior_atraso()
        caixa_acima_do_limite = self._construir_caixa_acima_do_limite()

        # Tudo — as duas caixas fixas e os gráficos dependentes do período —
        # dentro do MESMO QScrollArea, para a rolagem do mouse funcionar de
        # forma única na tela inteira (antes, as caixas ficavam fora da
        # área de rolagem, como se fossem uma "página" à parte dos
        # gráficos, o que ficava estranho). Só o widget interno
        # (``_widget_periodo``) é limpo/reconstruído a cada período — as
        # caixas continuam fixas, sem perder o filtro delas.
        self._area_scroll = QScrollArea()
        self._area_scroll.setWidgetResizable(True)
        self._container = QWidget()
        layout_scroll = QVBoxLayout(self._container)
        layout_scroll.addWidget(caixa_acima_do_limite)
        layout_scroll.addWidget(caixa_maior_atraso)

        self._widget_periodo = QWidget()
        self._layout_conteudo = QVBoxLayout(self._widget_periodo)
        layout_scroll.addWidget(self._widget_periodo)

        self._area_scroll.setWidget(self._container)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addLayout(layout_periodo)
        layout.addWidget(self._area_scroll)
        self.setLayout(layout)

        self._carregar()
        self._carregar_maiores_atrasos()
        self._carregar_acima_do_limite()

    def _limpar_conteudo(self) -> None:
        while self._layout_conteudo.count():
            item = self._layout_conteudo.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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

        self._tabela_atrasos = QTableWidget(0, 5)
        self._tabela_atrasos.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Em atraso há", "Total em Atraso", ""]
        )
        self._tabela_atrasos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_atrasos.setMinimumHeight(_ALTURA_TABELA_10_LINHAS)

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_filtro)
        layout_caixa.addWidget(QLabel(
            "Sem data de vencimento própria no fiado, a data da compra é usada como "
            "referência: quanto mais antiga uma compra ainda em aberto, mais atrasada conta."
        ))
        layout_caixa.addWidget(self._tabela_atrasos)
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
            self._tabela_atrasos.setItem(linha, 0, QTableWidgetItem(saldo.nome_principal))
            self._tabela_atrasos.setItem(linha, 1, QTableWidgetItem(saldo.telefone or "-"))
            self._tabela_atrasos.setItem(
                linha, 2, QTableWidgetItem(f"{saldo.dias_desde_a_compra_mais_antiga} dias")
            )
            self._tabela_atrasos.setItem(
                linha, 3, QTableWidgetItem(f"R$ {saldo.total_em_atraso:.2f}")
            )

            botao_lembrete = QPushButton("Enviar Lembrete")
            botao_lembrete.setIcon(icone("BRAND_WHATSAPP"))
            botao_lembrete.setEnabled(bool(saldo.telefone))
            botao_lembrete.clicked.connect(lambda _checked=False, s=saldo: self._abrir_lembrete(s))
            self._tabela_atrasos.setCellWidget(linha, 4, botao_lembrete)

    def _abrir_lembrete(self, saldo: SaldoAtrasoResumo) -> None:
        mensagem = montar_mensagem_lembrete_saldo(
            saldo.nome_principal,
            f"R$ {saldo.total_em_atraso:.2f}",
            saldo.dias_desde_a_compra_mais_antiga,
        )
        dialogo = LembreteWhatsAppDialog(saldo.nome_principal, saldo.telefone, mensagem, self)
        dialogo.exec()

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

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addWidget(self._tabela_acima_do_limite)
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
            self._tabela_acima_do_limite.setItem(linha, 0, QTableWidgetItem(item.nome_principal))
            self._tabela_acima_do_limite.setItem(linha, 1, QTableWidgetItem(item.telefone or "-"))
            self._tabela_acima_do_limite.setItem(
                linha, 2, QTableWidgetItem(f"R$ {item.limite_fiado:.2f}")
            )
            self._tabela_acima_do_limite.setItem(
                linha, 3, QTableWidgetItem(f"R$ {item.total_em_aberto:.2f}")
            )
            self._tabela_acima_do_limite.setItem(
                linha, 4, QTableWidgetItem(f"R$ {item.excesso:.2f}")
            )

            botao_lembrete = QPushButton("Enviar Lembrete")
            botao_lembrete.setIcon(icone("BRAND_WHATSAPP"))
            botao_lembrete.setEnabled(bool(item.telefone))
            botao_lembrete.clicked.connect(lambda _checked=False, i=item: self._abrir_lembrete_limite(i))
            self._tabela_acima_do_limite.setCellWidget(linha, 5, botao_lembrete)

    def _abrir_lembrete_limite(self, item: ClienteAcimaDoLimiteResumo) -> None:
        mensagem = montar_mensagem_lembrete_limite(
            item.nome_principal,
            f"R$ {item.total_em_aberto:.2f}",
            f"R$ {item.limite_fiado:.2f}",
        )
        dialogo = LembreteWhatsAppDialog(item.nome_principal, item.telefone, mensagem, self)
        dialogo.exec()

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

        label_total_aberto = QLabel(f"Total em aberto (geral do negócio): R$ {painel.total_em_aberto_geral:.2f}")
        label_total_aberto.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        self._layout_conteudo.addWidget(label_total_aberto)

        if painel.maior_valor_gasto:
            caixa = QGroupBox("Maior Valor Gasto no Período")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                _construir_grafico_barras(
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
                _construir_grafico_barras(
                    "Nº de Contas",
                    [c.nome_principal for c in painel.mais_contas_lancadas],
                    [float(c.quantidade) for c in painel.mais_contas_lancadas],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        if painel.evolucao_mensal:
            caixa = QGroupBox("Evolução de Vendas (últimos 6 meses)")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                _construir_grafico_linha(
                    "Total Vendido (R$)",
                    [p.mes for p in painel.evolucao_mensal],
                    [float(p.total) for p in painel.evolucao_mensal],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        if painel.maiores_saldos_em_aberto:
            caixa = QGroupBox("Clientes com Maior Saldo em Aberto")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                _construir_grafico_barras(
                    "Saldo em Aberto (R$)",
                    [c.nome_principal for c in painel.maiores_saldos_em_aberto],
                    [float(c.valor) for c in painel.maiores_saldos_em_aberto],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        self._layout_conteudo.addStretch()
