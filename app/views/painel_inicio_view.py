"""Tela de Início (painel/dashboard), visível apenas para Administrador.

Mostra, para um período selecionável (padrão: mês atual): os clientes que
mais gastaram (maior valor total em compras), os que mais lançaram contas
(mais vezes foram ao mercado), a evolução de vendas dos últimos 6 meses,
o total geral em aberto do negócio e os clientes com maior saldo em
aberto.
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
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.painel_controller import PainelController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone


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

        self._area_scroll = QScrollArea()
        self._area_scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._layout_conteudo = QVBoxLayout(self._container)
        self._area_scroll.setWidget(self._container)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addLayout(layout_periodo)
        layout.addWidget(self._area_scroll)
        self.setLayout(layout)

        self._carregar()

    def _limpar_conteudo(self) -> None:
        while self._layout_conteudo.count():
            item = self._layout_conteudo.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

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
