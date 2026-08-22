"""Utilitário de datas.

Calcula a data padrão a ser sugerida em Adicionar Compra e Receber Conta,
conforme o modo configurado globalmente (``app.services.configuracao_service``):
"dia atual" (hoje) ou "dia anterior" (ontem). Em qualquer um dos modos, a
data sugerida pode sempre ser alterada manualmente pelo usuário no
formulário — este utilitário só define o valor inicial do campo.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.services.configuracao_service import ModoDataPadrao, obter_modo_data_padrao


def obter_data_padrao() -> date:
    """Calcula a data padrão a ser sugerida em um novo lançamento.

    Returns:
        A data de hoje, se o modo configurado for "dia atual"; a data de
        ontem, se o modo configurado for "dia anterior" (padrão de fábrica).
    """
    modo = obter_modo_data_padrao()
    hoje = date.today()

    if modo == ModoDataPadrao.DIA_ATUAL:
        return hoje
    return hoje - timedelta(days=1)
