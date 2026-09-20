"""Testes de integração do serviço de histórico/auditoria.

``historico_service.registrar_historico`` é usado internamente por outros
serviços (nunca chamado diretamente pela interface) — por isso, é
exercitado aqui indiretamente através de uma ação que o aciona
(cadastro de cliente) e verificado via ``relatorio_service.listar_historico``.

``HistoricoResumo`` não expõe mais ``entidade``/``entidade_id``/``acao``
brutos (ver ``app.services.relatorio_service._descrever_acao``) — os
testes abaixo conferem o texto já formatado em ``descricao``.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import pytest

from app.services import cliente_service, relatorio_service

pytestmark = pytest.mark.integration


def test_cadastrar_cliente_gera_entrada_no_historico(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Cliente", [], [], []
    )

    historico = relatorio_service.listar_historico(usuario_admin_teste, entidade="Cliente")
    entrada = next(
        (h for h in historico if "Teste Automatizado Historico Cliente" in h.descricao), None
    )

    assert entrada is not None
    assert "Cadastrou o cliente" in entrada.descricao
    assert entrada.usuario_nome == usuario_admin_teste.nome

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_excluir_cliente_gera_entrada_de_exclusao_no_historico(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Exclusao", [], [], []
    )
    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)

    historico = relatorio_service.listar_historico(usuario_admin_teste, entidade="Cliente")
    descricoes = [
        h.descricao for h in historico if "Teste Automatizado Historico Exclusao" in h.descricao
    ]

    assert any("Cadastrou" in d for d in descricoes)
    assert any("Excluiu" in d for d in descricoes)


def test_listar_historico_filtra_por_entidade(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Filtro", [], [], []
    )

    historico_cliente = relatorio_service.listar_historico(usuario_admin_teste, entidade="Cliente")
    historico_usuario = relatorio_service.listar_historico(usuario_admin_teste, entidade="Usuario")

    assert any("Teste Automatizado Historico Filtro" in h.descricao for h in historico_cliente)
    # O filtro por "Usuario" nunca deveria trazer nada sobre este cliente.
    assert not any("Teste Automatizado Historico Filtro" in h.descricao for h in historico_usuario)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
