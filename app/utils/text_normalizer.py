"""Normalização de texto usada nas colunas de apoio à busca.

A busca de clientes deve ignorar acentos, maiúsculas/minúsculas e espaços
extras. Em vez de aplicar essa normalização em toda consulta (o que
impediria o uso eficiente de índices), guardamos, ao lado de cada campo
pesquisável, uma coluna "normalizada" (ex.: ``nome_principal_normalizado``)
já sem acentos, em minúsculas e sem espaços duplicados. Essa coluna é
indexada e usada nas buscas; a coluna original é usada apenas para exibição.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar_texto(texto: str) -> str:
    """Normaliza um texto para fins de busca/indexação.

    Remove acentuação, converte para minúsculas e colapsa espaços extras
    (incluindo espaços no início/fim).

    Args:
        texto: Texto original digitado pelo usuário (ex.: "  Mariázinha  ").

    Returns:
        Texto normalizado (ex.: "mariazinha").
    """
    if not texto:
        return ""

    # Decompõe caracteres acentuados (ex.: "á" -> "a" + acento) e descarta os acentos.
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))

    minusculo = sem_acento.lower()

    # Colapsa múltiplos espaços em um só e remove espaços nas bordas.
    sem_espacos_extras = re.sub(r"\s+", " ", minusculo).strip()

    return sem_espacos_extras


def normalizar_telefone(telefone: str) -> str:
    """Normaliza um telefone para busca, mantendo apenas os dígitos.

    Args:
        telefone: Telefone digitado pelo usuário (ex.: "(35) 99999-8888").

    Returns:
        Apenas os dígitos do telefone (ex.: "35999998888").
    """
    if not telefone:
        return ""
    return re.sub(r"\D", "", telefone)
