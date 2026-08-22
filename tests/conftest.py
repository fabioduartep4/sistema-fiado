"""Configuração compartilhada dos testes automatizados (pytest).

Os testes são divididos em duas categorias:

- **Testes puros** (ex.: ``test_text_normalizer.py``, ``test_nfe_parser.py``):
  não tocam no banco de dados nem no PySide6. Rodam sempre, em qualquer
  máquina com as dependências instaladas.
- **Testes de integração** (ex.: ``test_pagamento_service_fifo.py``):
  exercitam a camada de serviço de verdade, contra o PostgreSQL
  configurado em ``.env``. Por segurança, **só rodam se a variável de
  ambiente ``RODAR_TESTES_INTEGRACAO`` estiver definida como "1"** — um
  ``pytest`` comum roda só os testes puros, para nunca gravar dados de
  teste sem querer no banco configurado.

Para rodar TUDO, inclusive os testes de integração (aponte o ``.env``
para um banco de testes descartável, não para o banco de produção da
loja, já que esses testes criam e apagam usuários/clientes de verdade):

    # Linux/Mac
    RODAR_TESTES_INTEGRACAO=1 pytest

    # Windows (cmd)
    set RODAR_TESTES_INTEGRACAO=1
    pytest

    # Windows (PowerShell)
    $env:RODAR_TESTES_INTEGRACAO="1"; pytest
"""

from __future__ import annotations

import os
import uuid

import pytest

_RODAR_INTEGRACAO = os.getenv("RODAR_TESTES_INTEGRACAO") == "1"

_SENHA_USUARIO_TESTE = "senha-teste-automatizado-123"

if _RODAR_INTEGRACAO:
    # Fora do app.main (que registra isso na inicialização), os listeners
    # que preenchem as colunas normalizadas de busca (nome_principal_normalizado
    # etc.) nunca são ligados — sem isso, testes de integração que dependem de
    # busca por nome falhariam mesmo com a lógica de negócio correta.
    from app.database.listeners import registrar_listeners

    registrar_listeners()


def pytest_collection_modifyitems(config, items):  # noqa: ANN001 (assinatura exigida pelo pytest)
    """Pula testes marcados como 'integration', a menos que explicitamente habilitados."""
    if _RODAR_INTEGRACAO:
        return
    marcador_pular = pytest.mark.skip(
        reason="Teste de integração: defina RODAR_TESTES_INTEGRACAO=1 e configure um "
        "banco de testes em .env para rodar (veja o docstring deste conftest.py)."
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(marcador_pular)


def pytest_configure(config):  # noqa: ANN001 (assinatura exigida pelo pytest)
    config.addinivalue_line(
        "markers", "integration: teste que grava de verdade no banco configurado em .env"
    )


@pytest.fixture
def usuario_admin_teste():
    """Cria um usuário Administrador descartável para os testes de integração.

    É removido (inativado — exclusão lógica, o mesmo padrão do resto do
    sistema) ao final do teste, mesmo se o teste falhar.
    """
    from app.database.connection import session_scope
    from app.models.usuario import PerfilUsuario
    from app.repositories import usuario_repository
    from app.services.auth_service import UsuarioAutenticado, gerar_hash_senha

    login = f"teste_admin_{uuid.uuid4().hex[:10]}"
    with session_scope() as session:
        usuario = usuario_repository.criar_usuario(
            session,
            nome="Administrador de Teste (automatizado)",
            login=login,
            senha_hash=gerar_hash_senha(_SENHA_USUARIO_TESTE),
            perfil=PerfilUsuario.ADMINISTRADOR,
        )
        usuario_id = usuario.id

    yield UsuarioAutenticado(
        id=str(usuario_id), nome="Administrador de Teste (automatizado)",
        login=login, perfil=PerfilUsuario.ADMINISTRADOR,
    )

    with session_scope() as session:
        usuario = usuario_repository.buscar_por_id(session, usuario_id)
        if usuario is not None:
            usuario.ativo = False


@pytest.fixture
def senha_usuario_teste() -> str:
    """Senha em texto puro usada pela fixture ``usuario_admin_teste``."""
    return _SENHA_USUARIO_TESTE
