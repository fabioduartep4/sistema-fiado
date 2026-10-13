"""Gráficos do sistema, desenhados à mão (``QPainter``), usados nas telas
de Início e Saldos (``app.views.painel_inicio_view`` / ``app.views.saldos_view``).

Dois formatos, cada um para um tipo de pergunta:

- :class:`GraficoColunas` — "quanto foi em cada período?" (vendas por dia,
  vendas por mês). Uma coluna por período; período sem valor fica vazio,
  em vez de uma linha ligando os pontos (que sugeria uma subida/queda
  contínua que não existe entre dias separados). Um período pode ficar em
  destaque (o dia escolhido, o mês atual).
- :class:`ListaRanking` — "quem mais?" (quem mais comprou, quem mais
  deve). Uma linha por cliente, com o nome inteiro, uma barra
  proporcional, um detalhe opcional e o valor.

As cores vêm do tema em uso (``app.config.tema.cores_do_tema_aplicado``),
então os dois funcionam no claro e no escuro.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from app.config.tema import cores_do_tema_aplicado
from app.utils.formatacao import formatar_reais

_FAMILIA = "Segoe UI"
_LARGURA_COLUNA = 24  # teto: numa faixa larga, o resto fica como respiro
_RAIO = 4


@dataclass(frozen=True)
class PontoColuna:
    """Uma coluna do gráfico.

    Attributes:
        rotulo: Texto principal embaixo da coluna (ex.: "seg", "10/2026").
        valor: Valor em reais.
        sub_rotulo: Segunda linha embaixo da coluna, opcional (ex.: "06/10").
    """

    rotulo: str
    valor: Decimal
    sub_rotulo: str = ""


@dataclass(frozen=True)
class ItemRanking:
    """Uma linha da lista de ranking.

    Attributes:
        nome: Nome do cliente, exibido inteiro (só é abreviado se não couber).
        valor: Valor em reais — define o tamanho da barra.
        detalhe: Texto pequeno ao lado do valor, opcional (ex.: "9 compras").
    """

    nome: str
    valor: Decimal
    detalhe: str = ""


def _reais_sem_centavos(valor: float) -> str:
    return formatar_reais(Decimal(str(valor))).rsplit(",", 1)[0]


def _teto_redondo(valor: float) -> float:
    """Menor número "redondo" (1, 2, 2,5 ou 5 × 10ⁿ) que cobre o valor — o topo do eixo."""
    if valor <= 0:
        return 10.0
    base = 10 ** math.floor(math.log10(valor))
    for fator in (1, 2, 2.5, 5, 10):
        if fator * base >= valor:
            return fator * base
    return 10 * base


def _barra_arredondada(retangulo: QRectF, lado_reto: str) -> QPainterPath:
    """Barra com a ponta arredondada e o lado da base (``"baixo"``/``"esquerda"``) reto."""
    caminho = QPainterPath()
    caminho.setFillRule(Qt.FillRule.WindingFill)
    caminho.addRoundedRect(retangulo, _RAIO, _RAIO)
    if lado_reto == "baixo":
        altura = min(_RAIO, retangulo.height())
        caminho.addRect(QRectF(retangulo.left(), retangulo.bottom() - altura, retangulo.width(), altura))
    else:
        largura = min(_RAIO, retangulo.width())
        caminho.addRect(QRectF(retangulo.left(), retangulo.top(), largura, retangulo.height()))
    return caminho.simplified()


class GraficoColunas(QWidget):
    """Colunas por período, com um período opcionalmente em destaque.

    O valor é escrito só sobre a coluna em destaque e sobre a maior — os
    demais aparecem ao passar o mouse (e o eixo dá a ordem de grandeza).

    Args:
        pontos: As colunas, na ordem em que aparecem.
        indice_destaque: Posição da coluna em destaque (cor de destaque e
            rótulo em negrito); ``None`` deixa todas iguais, na cor de destaque.
        resumo: Linha de texto no topo, opcional (ex.: total e média).
    """

    _MARGEM_ESQUERDA = 78
    _MARGEM_DIREITA = 20
    _ALTURA_PLOT = 134

    def __init__(
        self,
        pontos: Sequence[PontoColuna],
        indice_destaque: Optional[int] = None,
        resumo: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pontos = list(pontos)
        self._destaque = indice_destaque
        self._resumo = resumo
        self._tem_sub_rotulo = any(p.sub_rotulo for p in self._pontos)
        self._topo = 62 if resumo else 34
        altura = self._topo + self._ALTURA_PLOT + (48 if self._tem_sub_rotulo else 32)
        self.setFixedHeight(altura)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)

    def _faixa(self) -> float:
        largura = self.width() - self._MARGEM_ESQUERDA - self._MARGEM_DIREITA
        return largura / max(len(self._pontos), 1)

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nome exigido pelo Qt)
        cores = cores_do_tema_aplicado()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.fillRect(self.rect(), QColor(cores["fundo_alt"]))
        fonte = QFont(_FAMILIA, 9)
        negrito = QFont(_FAMILIA, 9, QFont.Weight.DemiBold)
        texto, secundario = QColor(cores["texto"]), QColor(cores["texto_secundario"])

        if self._resumo:
            pintor.setFont(fonte)
            pintor.setPen(secundario)
            pintor.drawText(20, 26, self._resumo)
        if not self._pontos:
            pintor.end()
            return

        esquerda, direita = self._MARGEM_ESQUERDA, self.width() - self._MARGEM_DIREITA
        topo, base = self._topo, self._topo + self._ALTURA_PLOT
        maior = max(p.valor for p in self._pontos)
        maximo = _teto_redondo(float(maior))

        pintor.setFont(fonte)
        for passo in range(3):  # 0, metade e topo: sempre números redondos
            y = base - self._ALTURA_PLOT * passo / 2
            pintor.setPen(QPen(QColor(cores["borda"]), 1))
            pintor.drawLine(QPointF(esquerda, y), QPointF(direita, y))
            pintor.setPen(secundario)
            pintor.drawText(
                QRectF(0, y - 9, esquerda - 10, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _reais_sem_centavos(maximo * passo / 2),
            )

        faixa = self._faixa()
        largura_coluna = min(_LARGURA_COLUNA, faixa * 0.6)
        for indice, ponto in enumerate(self._pontos):
            centro = esquerda + faixa * (indice + 0.5)
            destacado = self._destaque is None or indice == self._destaque
            em_negrito = self._destaque is not None and indice == self._destaque
            if ponto.valor > 0:
                altura = max(self._ALTURA_PLOT * float(ponto.valor) / maximo, 3)
                coluna = QRectF(centro - largura_coluna / 2, base - altura, largura_coluna, altura)
                cor = cores["destaque"] if destacado else cores["grafico_neutro"]
                pintor.fillPath(_barra_arredondada(coluna, "baixo"), QColor(cor))
                if em_negrito or ponto.valor == maior:
                    pintor.setFont(negrito)
                    pintor.setPen(texto)
                    pintor.drawText(
                        QRectF(centro - 70, base - altura - 22, 140, 18),
                        Qt.AlignmentFlag.AlignCenter,
                        formatar_reais(ponto.valor),
                    )
            pintor.setFont(negrito if em_negrito else fonte)
            pintor.setPen(texto if em_negrito else secundario)
            pintor.drawText(QRectF(centro - 50, base + 8, 100, 16), Qt.AlignmentFlag.AlignCenter, ponto.rotulo)
            if ponto.sub_rotulo:
                pintor.drawText(
                    QRectF(centro - 50, base + 24, 100, 16), Qt.AlignmentFlag.AlignCenter, ponto.sub_rotulo
                )
        pintor.end()

    def mouseMoveEvent(self, evento) -> None:  # noqa: N802 (nome exigido pelo Qt)
        """Mostra o valor do período sob o mouse (a faixa inteira, não só a coluna)."""
        x = evento.position().x()
        indice = int((x - self._MARGEM_ESQUERDA) // self._faixa()) if self._pontos else -1
        dentro = self._MARGEM_ESQUERDA <= x <= self.width() - self._MARGEM_DIREITA
        if dentro and 0 <= indice < len(self._pontos):
            ponto = self._pontos[indice]
            rotulo = f"{ponto.rotulo} {ponto.sub_rotulo}".strip()
            QToolTip.showText(evento.globalPosition().toPoint(), f"{rotulo}: {formatar_reais(ponto.valor)}", self)
        else:
            QToolTip.hideText()


class ListaRanking(QWidget):
    """Lista de clientes em ordem de valor, com barra proporcional.

    Args:
        itens: Os clientes, já na ordem em que aparecem (maior primeiro).
        titulo_valor: Cabeçalho da coluna de valor (ex.: "Comprou no mês").
    """

    _ALTURA_LINHA = 34
    _ALTURA_CABECALHO = 40

    def __init__(self, itens: Sequence[ItemRanking], titulo_valor: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._itens = list(itens)
        self._titulo_valor = titulo_valor
        self._tem_detalhe = any(item.detalhe for item in self._itens)
        self.setFixedHeight(self._ALTURA_CABECALHO + self._ALTURA_LINHA * max(len(self._itens), 1) + 6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nome exigido pelo Qt)
        cores = cores_do_tema_aplicado()
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.Antialiasing)
        pintor.fillRect(self.rect(), QColor(cores["fundo_alt"]))
        fonte = QFont(_FAMILIA, 10)
        pequena = QFont(_FAMILIA, 9)
        negrito = QFont(_FAMILIA, 10, QFont.Weight.DemiBold)
        texto, secundario = QColor(cores["texto"]), QColor(cores["texto_secundario"])
        centro_vertical = Qt.AlignmentFlag.AlignVCenter
        a_direita = Qt.AlignmentFlag.AlignRight | centro_vertical

        # Colunas, da direita para a esquerda: valor, detalhe, barra; o nome fica com o resto.
        largura = self.width()
        largura_valor, largura_detalhe = 110, (96 if self._tem_detalhe else 0)
        x_valor = largura - 20 - largura_valor
        x_detalhe = x_valor - largura_detalhe
        x_nome = 46
        largura_barra = max((x_detalhe - x_nome) * 0.36, 60)
        x_barra = x_detalhe - largura_barra - 14
        largura_nome = max(x_barra - x_nome - 12, 40)

        pintor.setFont(pequena)
        pintor.setPen(secundario)
        pintor.drawText(QRectF(x_nome, 8, largura_nome, 20), centro_vertical, "Cliente")
        pintor.drawText(QRectF(x_valor - 60, 8, largura_valor + 60, 20), a_direita, self._titulo_valor)

        maior = max((item.valor for item in self._itens), default=Decimal("0"))
        y = self._ALTURA_CABECALHO
        for posicao, item in enumerate(self._itens, start=1):
            pintor.setFont(pequena)
            pintor.setPen(secundario)
            pintor.drawText(QRectF(10, y, 26, 28), a_direita, str(posicao))

            pintor.setFont(fonte)
            pintor.setPen(texto)
            nome = QFontMetrics(fonte).elidedText(item.nome, Qt.TextElideMode.ElideRight, int(largura_nome))
            pintor.drawText(QRectF(x_nome, y, largura_nome, 28), centro_vertical, nome)

            if item.valor > 0 and maior > 0:
                comprimento = max(largura_barra * float(item.valor) / float(maior), 3)
                barra = QRectF(x_barra, y + 8, comprimento, 12)
                pintor.fillPath(_barra_arredondada(barra, "esquerda"), QColor(cores["destaque"]))

            if item.detalhe:
                pintor.setFont(pequena)
                pintor.setPen(secundario)
                pintor.drawText(QRectF(x_detalhe, y, largura_detalhe, 28), a_direita, item.detalhe)

            pintor.setFont(negrito)
            pintor.setPen(texto)
            pintor.drawText(QRectF(x_valor, y, largura_valor, 28), a_direita, formatar_reais(item.valor))
            y += self._ALTURA_LINHA
        pintor.end()
