"""Helpers de montagem de gráficos simples (``QtCharts``), reaproveitados
pelas telas de Início e Saldos (``app.views.painel_inicio_view`` /
``app.views.saldos_view``) — extraídos daqui pra não duplicar a mesma
lógica de eixos/série nas duas telas.
"""

from __future__ import annotations

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter

# Altura padrão dos gráficos — reduzida no redesign (antes 280px): um
# gráfico não deve dominar a tela, é só um complemento visual aos
# números que já aparecem nos cartões/tabelas ao redor dele.
_ALTURA_PADRAO = 160


def construir_grafico_barras(
    titulo_serie: str, rotulos: list[str], valores: list[float], altura: int = _ALTURA_PADRAO
) -> QChartView:
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
    view.setMinimumHeight(altura)
    return view


def construir_grafico_linha(
    titulo_serie: str, rotulos: list[str], valores: list[float], altura: int = _ALTURA_PADRAO
) -> QChartView:
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
    view.setMinimumHeight(altura)
    return view
