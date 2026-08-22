"""Listeners do SQLAlchemy responsáveis por manter as colunas normalizadas
de busca (sem acento/maiúscula/espaços extras) sempre sincronizadas com os
campos originais, tanto na criação quanto na edição dos registros.

Este módulo deve ser importado uma única vez, na inicialização da
aplicação (ver app/main.py), para que os listeners sejam registrados antes
de qualquer operação de banco.
"""

from __future__ import annotations

from sqlalchemy import event

from app.models.cliente import Cliente
from app.models.nome_alternativo import NomeAlternativo
from app.models.telefone import Telefone
from app.utils.text_normalizer import normalizar_telefone, normalizar_texto


def _sincronizar_cliente(_mapper, _connection, alvo: Cliente) -> None:
    alvo.nome_principal_normalizado = normalizar_texto(alvo.nome_principal)


def _sincronizar_nome_alternativo(_mapper, _connection, alvo: NomeAlternativo) -> None:
    alvo.nome_normalizado = normalizar_texto(alvo.nome)


def _sincronizar_telefone(_mapper, _connection, alvo: Telefone) -> None:
    alvo.numero_normalizado = normalizar_telefone(alvo.numero)


def registrar_listeners() -> None:
    """Registra todos os listeners de normalização. Idempotente."""
    for evento in ("before_insert", "before_update"):
        if not event.contains(Cliente, evento, _sincronizar_cliente):
            event.listen(Cliente, evento, _sincronizar_cliente)
        if not event.contains(NomeAlternativo, evento, _sincronizar_nome_alternativo):
            event.listen(NomeAlternativo, evento, _sincronizar_nome_alternativo)
        if not event.contains(Telefone, evento, _sincronizar_telefone):
            event.listen(Telefone, evento, _sincronizar_telefone)
