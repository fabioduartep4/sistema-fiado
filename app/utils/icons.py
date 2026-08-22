"""Utilitário de ícones para os botões do sistema.

Usa a biblioteca ``pytablericons`` (conjunto Tabler Icons, estilo
*outline*, discreto) para carregar ícones e convertê-los em ``QIcon``,
prontos para uso em qualquer ``QPushButton``. A paleta é preto/cinza
(``_COR_PADRAO``), consistente com o tema claro do sistema.

Os ícones são identificados pelo nome (texto), não pelo membro do enum
diretamente — se um nome não existir no conjunto outline do Tabler Icons
(erro de digitação, ou um ícone que não existe com esse nome), o botão
simplesmente fica sem ícone (só com o texto), em vez de travar a
aplicação inteira. Isso é importante porque o texto de cada botão
continua sempre presente — o ícone é um complemento visual, nunca a
única forma de identificar a ação.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtGui import QIcon
from pytablericons import OutlineIcon, TablerIcons

from app.config.logging_config import logger

_COR_PADRAO = "#4b5563"  # cinza escuro discreto, combina com o tema claro
_TAMANHO_PADRAO = 18


@lru_cache(maxsize=None)
def icone(nome: str, tamanho: int = _TAMANHO_PADRAO, cor: str = _COR_PADRAO) -> QIcon:
    """Carrega um ícone do Tabler Icons (estilo outline) como QIcon.

    Args:
        nome: Nome do ícone no conjunto outline (ex.: ``"SEARCH"``,
            ``"USER_PLUS"``) — mesmo nome do enum ``OutlineIcon`` da
            biblioteca ``pytablericons``.
        tamanho: Tamanho em pixels (largura e altura).
        cor: Cor do traço, em hexadecimal.

    Returns:
        Um ``QIcon`` pronto para ``QPushButton.setIcon(...)``. Se o nome
        não existir no conjunto de ícones, retorna um ``QIcon()`` vazio
        (o botão fica só com o texto, sem travar a aplicação).
    """
    try:
        icone_enum = getattr(OutlineIcon, nome)
    except AttributeError:
        logger.warning("Ícone '%s' não encontrado no conjunto Tabler Icons (outline).", nome)
        return QIcon()

    imagem = TablerIcons.load(icone_enum, size=tamanho, color=cor)
    return QIcon(imagem.toqpixmap())
