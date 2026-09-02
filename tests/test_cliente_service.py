"""Testes de integração de app.services.cliente_service.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import cliente_service, compra_service
from app.utils.date_utils import obter_data_padrao

pytestmark = pytest.mark.integration


def test_cadastrar_cliente_com_nome_vazio_e_rejeitado(usuario_admin_teste) -> None:
    with pytest.raises(ValueError):
        cliente_service.cadastrar_cliente(usuario_admin_teste, "   ", [], [], [])


def test_cadastrar_e_buscar_cliente_por_nome_principal(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Busca Principal", [], [], []
    )

    resultados = cliente_service.buscar_clientes("Teste Automatizado Busca Principal")
    assert any(r.id == cliente.id and r.nome_alternativo_encontrado is None for r in resultados)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_buscar_cliente_por_nome_alternativo_mostra_qual_bateu(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste,
        "Teste Automatizado Maria Fernanda",
        ["Mariazinha Automatizada"],
        [],
        [],
    )

    resultados = cliente_service.buscar_clientes("Mariazinha Automatizada")
    encontrado = next((r for r in resultados if r.id == cliente.id), None)
    assert encontrado is not None
    assert encontrado.nome_alternativo_encontrado == "Mariazinha Automatizada"

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_busca_ignora_cliente_excluido(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Cliente Excluido", [], [], []
    )
    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)

    resultados = cliente_service.buscar_clientes("Teste Automatizado Cliente Excluido")
    assert not any(r.id == cliente.id for r in resultados)


def test_editar_cliente_atualiza_nome_principal(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Nome Antigo", [], [], []
    )

    ficha = cliente_service.editar_cliente(
        usuario_admin_teste, cliente.id, "Teste Automatizado Nome Novo", [], [], []
    )
    assert ficha.nome_principal == "Teste Automatizado Nome Novo"

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_cadastrar_cliente_com_limite_fiado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Limite Cadastro", [], [], [],
        limite_fiado=Decimal("150.00"),
    )

    ficha = cliente_service.obter_ficha(cliente.id)
    assert ficha.limite_fiado == Decimal("150.00")

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_cadastrar_cliente_sem_limite_fiado_fica_sem_limite(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Sem Limite Cadastro", [], [], []
    )

    ficha = cliente_service.obter_ficha(cliente.id)
    assert ficha.limite_fiado is None

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_cadastrar_cliente_com_limite_fiado_zero_e_rejeitado(usuario_admin_teste) -> None:
    with pytest.raises(ValueError):
        cliente_service.cadastrar_cliente(
            usuario_admin_teste, "Teste Automatizado Limite Invalido", [], [], [],
            limite_fiado=Decimal("0"),
        )


def test_editar_cliente_define_e_depois_remove_o_limite_fiado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Limite Edicao", [], [], []
    )

    ficha = cliente_service.editar_cliente(
        usuario_admin_teste, cliente.id, cliente.nome_principal, [], [], [],
        limite_fiado=Decimal("300.00"),
    )
    assert ficha.limite_fiado == Decimal("300.00")

    ficha = cliente_service.editar_cliente(
        usuario_admin_teste, cliente.id, cliente.nome_principal, [], [], [], limite_fiado=None
    )
    assert ficha.limite_fiado is None

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_mesclar_clientes_duplicados_move_compras_para_o_principal(usuario_admin_teste) -> None:
    principal = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Duplicado Merge", [], [], []
    )
    duplicado = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Duplicado Merge", [], [], []
    )
    compra_service.registrar_compra(
        usuario_admin_teste, duplicado.id, Decimal("5.00"), obter_data_padrao(), None
    )

    cliente_service.mesclar_clientes(usuario_admin_teste, principal.id, [duplicado.id])

    ficha_principal = cliente_service.obter_ficha(principal.id)
    assert len(ficha_principal.compras) == 1
    assert ficha_principal.compras[0].valor == Decimal("5.00")

    with pytest.raises(ValueError):
        cliente_service.obter_ficha(duplicado.id)  # inativado pela mesclagem

    cliente_service.excluir_cliente(usuario_admin_teste, principal.id)


def test_listar_grupos_duplicados_encontra_o_grupo_criado(usuario_admin_teste) -> None:
    c1 = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Grupo Duplicado", [], [], []
    )
    c2 = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Grupo Duplicado", [], [], []
    )

    grupos = cliente_service.listar_grupos_duplicados(usuario_admin_teste)
    grupo = next(
        (g for g in grupos if g.nome_normalizado == "teste automatizado grupo duplicado"), None
    )
    assert grupo is not None
    assert len(grupo.clientes) == 2

    cliente_service.mesclar_clientes(usuario_admin_teste, c1.id, [c2.id])
    cliente_service.excluir_cliente(usuario_admin_teste, c1.id)
