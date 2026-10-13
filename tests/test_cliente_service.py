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


def test_busca_por_codigo_e_por_telefone(usuario_admin_teste) -> None:
    import uuid as _uuid

    # Telefone único por execução, para não casar com sobras de execuções anteriores.
    telefone = "359" + str(_uuid.uuid4().int)[:8]
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Busca Telefone", [], [f"({telefone[:2]}) {telefone[2:]}"], []
    )
    try:
        codigo = cliente_service.obter_ficha(cliente.id).id_visivel

        por_codigo = cliente_service.buscar_clientes(str(codigo))
        assert por_codigo[0].id == cliente.id  # o código digitado vem sempre em primeiro
        assert por_codigo[0].nome_alternativo_encontrado == f"código {codigo}"

        por_telefone = cliente_service.buscar_clientes(telefone[3:])  # só um pedaço do número
        assert [c.id for c in por_telefone] == [cliente.id]
        assert por_telefone[0].nome_alternativo_encontrado.startswith("tel. ")

        formatado = cliente_service.buscar_clientes(f"({telefone[:2]}) {telefone[2:7]}-{telefone[7:]}")
        assert [c.id for c in formatado] == [cliente.id]

        # A tela Clientes do administrador usa outra consulta: tem que achar igual.
        for termo in (str(codigo), telefone[3:]):
            status = cliente_service.listar_clientes_com_status(usuario_admin_teste, termo=termo)
            assert cliente.id in [c.id for c in status]

        # Poucos dígitos não viram busca por telefone (casariam com quase todo mundo).
        assert cliente.id not in [c.id for c in cliente_service.buscar_clientes(telefone[3:6])] or str(codigo) == telefone[3:6]
    finally:
        cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_lembrete_escolhe_a_mensagem_pela_situacao_da_conta(usuario_admin_teste) -> None:
    """Regra única da ficha e dos lembretes em lote: limite > atraso > só o total."""
    from app.services import lembrete_service

    hoje = obter_data_padrao()
    em_dia = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Lembrete Em Dia", [], ["35999990001"], []
    )
    atrasado = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Lembrete Atrasado", [], [], []
    )
    estourado = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Lembrete Limite", [], [], [], limite_fiado=Decimal("50.00")
    )
    try:
        compra_service.registrar_compra(usuario_admin_teste, em_dia.id, Decimal("15.00"), hoje, None)
        compra_service.registrar_compra(
            usuario_admin_teste, atrasado.id, Decimal("90.00"), hoje - timedelta(days=45), None
        )
        # Atrasado E acima do limite: vale a mensagem de limite.
        compra_service.registrar_compra(
            usuario_admin_teste, estourado.id, Decimal("80.00"), hoje - timedelta(days=45), None
        )

        lembrete = lembrete_service.montar_lembrete(em_dia.id)
        assert lembrete.telefone == "35999990001"
        assert "R$ 15,00" in lembrete.mensagem and "atraso" not in lembrete.mensagem

        lembrete = lembrete_service.montar_lembrete(atrasado.id)
        assert lembrete.telefone is None
        assert "em atraso" in lembrete.mensagem and "R$ 90,00" in lembrete.mensagem

        # Com um prazo maior que a idade da compra, deixa de contar como atraso.
        assert "atraso" not in lembrete_service.montar_lembrete(atrasado.id, dias_atraso=60).mensagem

        lembrete = lembrete_service.montar_lembrete(estourado.id)
        assert "limite combinado de R$ 50,00" in lembrete.mensagem
    finally:
        for cliente in (em_dia, atrasado, estourado):
            cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
