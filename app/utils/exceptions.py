"""Exceções de negócio compartilhadas.

``ErroDeNegocio`` é a classe-base para erros esperados de validação/regra
de negócio (ex.: "login já existe", "permissão negada", "cliente não
encontrado"). Esses erros **não** são registrados no log de erros do
sistema (arquivo + tabela ``log_erros``) pelo decorator
``app.utils.error_handler.tratar_erros`` — apenas relançados, para a
camada de view mostrar a mensagem ao usuário. ``ValueError`` também é
tratado como erro de negócio, pelo mesmo motivo.

Isso mantém o log de erros útil (reservado para falhas técnicas reais,
como banco de dados fora do ar), em vez de poluído por validações comuns
do dia a dia (senha errada, campo obrigatório vazio, etc.).
"""

from __future__ import annotations


class ErroDeNegocio(Exception):
    """Classe-base para erros esperados de regra de negócio."""
