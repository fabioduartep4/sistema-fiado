"""Configuração compartilhada dos testes automatizados (pytest).

Os testes são divididos em duas categorias:

- **Testes puros** (ex.: ``test_text_normalizer.py``, ``test_nfe_parser.py``):
  não tocam no banco de dados nem no PySide6. Rodam sempre, em qualquer
  máquina com as dependências instaladas.
- **Testes de integração** (ex.: ``test_pagamento_service_fifo.py``):
  exercitam a camada de serviço de verdade, contra um PostgreSQL. **Só
  rodam se a variável de ambiente ``RODAR_TESTES_INTEGRACAO`` estiver
  definida como "1"** — um ``pytest`` comum roda só os testes puros.

**Os testes de integração nunca gravam no banco da loja.** Eles usam um
banco separado, no mesmo servidor do ``.env``, com o nome do banco
configurado mais o sufixo ``_teste`` (ex.: ``fiado_db`` → ``fiado_db_teste``).
Esse banco é criado sozinho na primeira vez (o usuário do ``.env`` precisa
poder criar bancos) e as tabelas dele são criadas/atualizadas a cada
execução. Se ``DB_NAME`` já for um banco de testes (termina em ``_teste``,
``_test`` ou ``_ci``, como no CI), é usado como está.

Para rodar TUDO, inclusive os testes de integração:

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

_SUFIXOS_BANCO_DE_TESTE = ("_teste", "_test", "_ci")


def _preparar_banco_de_testes() -> None:
    """Aponta a aplicação para o banco de testes, criando-o se ainda não existir.

    Precisa rodar ANTES de qualquer import de ``app.*``: é ``app.config.settings``
    que lê ``DB_NAME``, uma única vez, quando é importado.
    """
    from pathlib import Path

    import psycopg
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    nome = os.environ["DB_NAME"]
    if not nome.endswith(_SUFIXOS_BANCO_DE_TESTE):
        nome = f"{nome}_teste"
        os.environ["DB_NAME"] = nome

    with psycopg.connect(
        host=os.environ["DB_HOST"],
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        dbname="postgres",
        autocommit=True,
    ) as conexao:
        existe = conexao.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,)).fetchone()
        if not existe:
            conexao.execute(psycopg.sql.SQL("CREATE DATABASE {}").format(psycopg.sql.Identifier(nome)))

    from app.config.settings import settings
    from app.database.migrar import aplicar_esquema_banco

    # Última trava: se por qualquer motivo a aplicação não estiver apontando
    # para um banco de testes, para tudo antes de gravar uma linha sequer.
    if not settings.database.name.endswith(_SUFIXOS_BANCO_DE_TESTE):
        raise RuntimeError(
            f"Os testes de integração iam rodar no banco '{settings.database.name}', "
            "que não é um banco de testes. Abortado."
        )
    aplicar_esquema_banco()


if _RODAR_INTEGRACAO:
    _preparar_banco_de_testes()

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
