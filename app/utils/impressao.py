"""Pré-visualização/impressão de documentos HTML (recibo, extrato do cliente).

Configurado para impressora térmica não-fiscal de 80mm (bobina contínua —
ex.: Elgin i9), não para papel A4: a página é estreita e sua altura é
calculada a partir do conteúdo real de cada documento, não um tamanho fixo
(bobina contínua não tem "página" com altura definida — é o conteúdo que
decide onde a bobina termina).

Usa ``QtPrintSupport``, já incluso na instalação do PySide6 (mesmo padrão
já usado para ``QtCharts`` no painel de início) — nenhuma dependência nova.
O usuário sempre passa pela pré-visualização antes de imprimir de verdade,
podendo também "imprimir" em PDF através de uma impressora virtual (já
disponível por padrão no Windows, macOS e na maioria das distribuições
Linux).
"""

from __future__ import annotations

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

# Largura de bobina da impressora térmica em uso (Elgin i9, 80mm). Ajustar
# aqui se a loja trocar de modelo/largura de bobina no futuro (ex.: 58mm).
_LARGURA_PAPEL_MM = 80.0
_MARGEM_MM = 3.0
# Folga extra abaixo do conteúdo real, antes do corte da bobina.
_FOLGA_INFERIOR_MM = 8.0


def _montar_impressora_termica() -> QPrinter:
    impressora = QPrinter(QPrinter.PrinterMode.HighResolution)
    # Altura provisória (será recalculada a partir do conteúdo, abaixo) —
    # só precisa ser alta o bastante para medir a largura útil da página.
    tamanho_provisorio = QPageSize(QSizeF(_LARGURA_PAPEL_MM, 1000.0), QPageSize.Unit.Millimeter)
    impressora.setPageSize(tamanho_provisorio)
    impressora.setPageMargins(
        QMarginsF(_MARGEM_MM, _MARGEM_MM, _MARGEM_MM, _MARGEM_MM), QPageLayout.Unit.Millimeter
    )
    return impressora


def _ajustar_altura_ao_conteudo(impressora: QPrinter, documento: QTextDocument) -> None:
    """Recalcula a altura da página para caber exatamente o conteúdo.

    Bobina contínua não tem altura fixa como uma folha A4 — sem isso, a
    pré-visualização mostraria uma folha gigante quase toda em branco, e a
    impressão real avançaria bobina vazia desnecessariamente.
    """
    largura_util_px = impressora.pageRect(QPrinter.Unit.DevicePixel).width()
    documento.setTextWidth(largura_util_px)
    altura_conteudo_px = documento.size().height()

    dpi = impressora.resolution()
    altura_conteudo_mm = (altura_conteudo_px / dpi) * 25.4
    altura_pagina_mm = altura_conteudo_mm + (_MARGEM_MM * 2) + _FOLGA_INFERIOR_MM

    tamanho_final = QPageSize(QSizeF(_LARGURA_PAPEL_MM, altura_pagina_mm), QPageSize.Unit.Millimeter)
    impressora.setPageSize(tamanho_final)


def exibir_pre_visualizacao_impressao(parent: QWidget, titulo_janela: str, html: str) -> None:
    """Abre a pré-visualização de impressão de um documento HTML.

    Args:
        parent: Janela "dona" do diálogo de pré-visualização.
        titulo_janela: Título da janela de pré-visualização.
        html: Conteúdo do documento (ver ``app.utils.documentos`` — já
            formatado para a largura estreita da impressora térmica).
    """
    impressora = _montar_impressora_termica()

    documento = QTextDocument()
    documento.setHtml(html)
    _ajustar_altura_ao_conteudo(impressora, documento)

    dialogo = QPrintPreviewDialog(impressora, parent)
    dialogo.setWindowTitle(titulo_janela)

    def _renderizar(impressora_alvo: QPrinter) -> None:
        documento.print_(impressora_alvo)

    dialogo.paintRequested.connect(_renderizar)
    dialogo.exec()
