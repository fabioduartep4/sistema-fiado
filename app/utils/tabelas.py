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

from PySide6.QtWidgets import QHeaderView, QTableWidget


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
