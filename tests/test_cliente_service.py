"""Testes de integração de app.services.cliente_service.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

from datetime import timedelta
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


def test_listar_clientes_com_status_inclui_cliente_sem_nenhuma_compra(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Status Sem Saldo", [], [], []
    )

    resultado = cliente_service.listar_clientes_com_status(usuario_admin_teste, termo="Teste Automatizado Status Sem Saldo")
    status = next((r for r in resultado if r.id == cliente.id), None)

    assert status is not None
    assert status.saldo == Decimal("0")
    assert status.atrasado is False
    assert status.excedido is False

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_clientes_com_status_calcula_saldo_atraso_e_excesso(usuario_admin_teste) -> None:
    hoje = obter_data_padrao()
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste,
        "Teste Automatizado Status Atrasado Excedido",
        [],
        [],
        [],
        limite_fiado=Decimal("50.00"),
    )
    compra_service.registrar_compra(
        usuario_admin_teste, cliente.id, Decimal("90.00"), hoje - timedelta(days=40), None
    )
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("15.00"), hoje, None)

    resultado = cliente_service.listar_clientes_com_status(
        usuario_admin_teste, termo="Teste Automatizado Status Atrasado Excedido", dias_atraso=30
    )
    status = next(r for r in resultado if r.id == cliente.id)

    assert status.saldo == Decimal("105.00")
    assert status.limite_fiado == Decimal("50.00")
    assert status.atrasado is True
    assert status.excedido is True

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_contar_clientes_ativos_reflete_novo_cadastro(usuario_admin_teste) -> None:
    antes = cliente_service.contar_clientes_ativos()

    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Contagem Ativos", [], [], []
    )
    depois = cliente_service.contar_clientes_ativos()
    assert depois == antes + 1

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
    apos_exclusao = cliente_service.contar_clientes_ativos()
    assert apos_exclusao == antes


def test_listar_clientes_com_status_marca_cliente_pendente_de_confirmacao(usuario_admin_teste) -> None:
    from app.database.connection import session_scope
    from app.repositories import cliente_repository as _cliente_repository

    with session_scope() as session:
        cliente_pendente = _cliente_repository.criar_cliente_pendente(
            session, "Teste Automatizado Status Pendente Confirmacao"
        )
        cliente_id = str(cliente_pendente.id)

    resultado = cliente_service.listar_clientes_com_status(
        usuario_admin_teste, termo="Teste Automatizado Status Pendente Confirmacao"
    )
    status = next(r for r in resultado if r.id == cliente_id)
    assert status.confirmado is False

    cliente_service.confirmar_cliente(usuario_admin_teste, cliente_id)
    resultado_depois = cliente_service.listar_clientes_com_status(
        usuario_admin_teste, termo="Teste Automatizado Status Pendente Confirmacao"
    )
    status_depois = next(r for r in resultado_depois if r.id == cliente_id)
    assert status_depois.confirmado is True

    cliente_service.excluir_cliente(usuario_admin_teste, cliente_id)


def test_listar_clientes_com_status_filtra_por_termo(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Status Filtro Unico", [], [], []
    )

    resultado_encontra = cliente_service.listar_clientes_com_status(usuario_admin_teste, termo="Status Filtro Unico")
    resultado_nao_encontra = cliente_service.listar_clientes_com_status(
        usuario_admin_teste, termo="Nome Que Certamente Nao Existe Em Nenhum Cliente"
    )

    assert any(r.id == cliente.id for r in resultado_encontra)
    assert not any(r.id == cliente.id for r in resultado_nao_encontra)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_funcionario_nao_pode_listar_clientes_com_status(usuario_admin_teste) -> None:
    import uuid

    from app.models.usuario import PerfilUsuario
    from app.services import auth_service, usuario_service
    from app.services.usuario_service import PermissaoNegadaError

    login = f"teste_func_status_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste Status", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    try:
        usuario_funcionario = auth_service.autenticar(login, "senha-func-123")
        with pytest.raises(PermissaoNegadaError):
            cliente_service.listar_clientes_com_status(usuario_funcionario)
    finally:
        usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)
