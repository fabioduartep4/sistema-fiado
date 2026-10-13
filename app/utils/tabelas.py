"""Helper de configuração de colunas de ``QTableWidget``, compartilhado
entre as telas.

Padrão do sistema: a(s) coluna(s) de texto livre (nome do cliente,
descrição, mensagem de erro etc.) ocupam o espaço sobrando ("Stretch"),
enquanto todas as outras — inclusive a coluna de botão de ação, quando
houver — ficam do tamanho exato do conteúdo ("ResizeToContents"). Assim o
nome nunca fica cortado numa janela estreita, e o botão de ação nunca
fica espremido/cortado numa janela larga.

Sem isso, o comportamento padrão do Qt sempre estica a ÚLTIMA coluna da
tabela (``stretchLastSection``) — que em várias telas daqui é justamente
a coluna do botão de ação (ex.: "Enviar Lembrete"), não a do nome, o que
faz o botão esticar de forma estranha e o nome ficar sem espaço garantido.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QLabel, QListWidget, QTableWidget, QTableWidgetItem


def item_valor(texto: str) -> QTableWidgetItem:
    """Célula de valor em dinheiro: alinhada à direita, para os números de
    uma coluna ficarem um embaixo do outro e fáceis de comparar."""
    item = QTableWidgetItem(texto)
    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return item


def ajustar_altura_as_linhas(tabela: QTableWidget, minimo: int = 2, maximo: int = 10) -> None:
    """Deixa a tabela com a altura das linhas que ela tem (entre ``minimo`` e ``maximo``).

    Para tabelas dentro de uma tela que já rola: em vez de reservar sempre
    espaço para 10 linhas (um buraco em branco quando há 1 ou 2), a tabela
    encolhe; passando de ``maximo`` linhas, ela mesma ganha rolagem.

    Chamar depois de preencher a tabela — a altura sai das linhas reais
    (uma linha com botão é mais alta que uma só de texto).
    """
    cabecalho_vertical = tabela.verticalHeader()
    visiveis = min(tabela.rowCount(), maximo)
    altura_linhas = sum(tabela.rowHeight(linha) for linha in range(visiveis))
    altura_linhas += max(minimo - visiveis, 0) * cabecalho_vertical.defaultSectionSize()
    altura = tabela.horizontalHeader().height() + altura_linhas + 2 * tabela.frameWidth()
    tabela.setFixedHeight(altura + 2)  # folga: sem ela aparece barra de rolagem por 1px


def ajustar_altura_aos_itens(lista: QListWidget, maximo: int = 12) -> None:
    """O mesmo de :func:`ajustar_altura_as_linhas`, para uma lista simples."""
    visiveis = max(1, min(lista.count(), maximo))
    altura_item = max(lista.sizeHintForRow(0), 24)
    lista.setFixedHeight(visiveis * altura_item + 2 * lista.frameWidth() + 2)


def aplicar_estado_vazio(tabela: QTableWidget, label_vazio: QLabel) -> None:
    """Alterna entre mostrar a tabela e uma mensagem amigável, conforme ela
    tem linhas ou não (ex.: "Nenhum cliente encontrado.").

    Chame depois de popular a tabela (``setRowCount``/``setItem`` já
    feitos). ``label_vazio`` é um ``QLabel`` (normalmente
    ``papel="secundario"``) que fica no lugar da tabela quando vazia —
    quem constrói a tela é responsável por criá-lo e colocá-lo no
    layout, logo abaixo ou no lugar da tabela.
    """
    vazia = tabela.rowCount() == 0
    tabela.setVisible(not vazia)
    label_vazio.setVisible(vazia)


def ajustar_colunas(tabela: QTableWidget, *colunas_para_esticar: int) -> None:
    """Configura a largura das colunas de uma tabela no padrão do sistema.

    Args:
        tabela: A tabela a configurar.
        *colunas_para_esticar: Índices das colunas que devem ocupar o
            espaço sobrando (normalmente a coluna de nome/descrição, ou a
            de mensagem/observação). Todas as demais colunas — a de botão
            de ação incluída — ficam do tamanho exato do conteúdo.
    """
    cabecalho = tabela.horizontalHeader()
    cabecalho.setStretchLastSection(False)
    cabecalho.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    for coluna in colunas_para_esticar:
        cabecalho.setSectionResizeMode(coluna, QHeaderView.ResizeMode.Stretch)
