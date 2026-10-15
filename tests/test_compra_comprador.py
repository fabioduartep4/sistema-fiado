"""Testes de integração do cadastro de comprador na hora da compra
(``compra_service.criar_comprador``).

Gravam de verdade no banco de testes. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import uuid
from dataclasses import replace

import pytest

from app.models.usuario import PerfilUsuario
from app.services import cliente_service, compra_service, relatorio_service

pytestmark = pytest.mark.integration


@pytest.fixture
def cliente_teste(usuario_admin_teste):
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, f"Teste Comprador {uuid.uuid4().hex[:8]}", [], [], ["Ana Teste"]
    )
    yield cliente
    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def _nomes(cliente_id: str) -> list[str]:
    return [c.nome for c in compra_service.listar_compradores(cliente_id)]


def test_funcionario_cadastra_comprador_e_ele_aparece_na_lista(usuario_admin_teste, cliente_teste) -> None:
    funcionario = replace(usuario_admin_teste, perfil=PerfilUsuario.FUNCIONARIO)

    comprador = compra_service.criar_comprador(funcionario, cliente_teste.id, "  Joao   Teste ")

    assert comprador.nome == "Joao Teste"
    assert sorted(_nomes(cliente_teste.id)) == ["Ana Teste", "Joao Teste"]

    historico = relatorio_service.listar_historico(usuario_admin_teste, "Cliente", limite=20)
    assert any(
        h.descricao == f'Cadastrou o comprador "Joao Teste" no cliente "{cliente_teste.nome_principal}".'
        for h in historico
    )


def test_nome_repetido_devolve_o_comprador_existente(usuario_admin_teste, cliente_teste) -> None:
    existente = compra_service.listar_compradores(cliente_teste.id)[0]

    comprador = compra_service.criar_comprador(usuario_admin_teste, cliente_teste.id, "ana teste")

    assert comprador.id == existente.id
    assert _nomes(cliente_teste.id) == ["Ana Teste"]


def test_comprador_removido_volta_ao_cadastrar_de_novo(usuario_admin_teste, cliente_teste) -> None:
    removido = compra_service.listar_compradores(cliente_teste.id)[0]
    cliente_service.editar_cliente(
        usuario_admin_teste, cliente_teste.id, cliente_teste.nome_principal, [], [], []
    )
    assert _nomes(cliente_teste.id) == []

    comprador = compra_service.criar_comprador(usuario_admin_teste, cliente_teste.id, "Ana Teste")

    assert comprador.id == removido.id
    assert _nomes(cliente_teste.id) == ["Ana Teste"]


def test_compra_pode_usar_o_comprador_recem_cadastrado(usuario_admin_teste, cliente_teste) -> None:
    from datetime import date
    from decimal import Decimal

    comprador = compra_service.criar_comprador(usuario_admin_teste, cliente_teste.id, "Pedro Teste")
    compra = compra_service.registrar_compra(
        usuario_admin_teste, cliente_teste.id, Decimal("10.00"), date.today(), comprador.id
    )
    assert compra.valor == Decimal("10.00")


@pytest.mark.parametrize("nome", ["", "   ", "x" * 151])
def test_nome_invalido_e_rejeitado(usuario_admin_teste, cliente_teste, nome) -> None:
    with pytest.raises(ValueError):
        compra_service.criar_comprador(usuario_admin_teste, cliente_teste.id, nome)
    assert _nomes(cliente_teste.id) == ["Ana Teste"]
