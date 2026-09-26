"""Testes de integração do serviço de relatórios e painel de início.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import csv
import uuid
from datetime import date, timedelta
from decimal import Decimal

import openpyxl
import pytest

from app.services import cliente_service, compra_service, pagamento_service, relatorio_service, usuario_service
from app.services.usuario_service import PermissaoNegadaError
from app.utils.date_utils import obter_data_padrao

pytestmark = pytest.mark.integration


def _criar_funcionario_teste(usuario_admin_teste):
    from app.models.usuario import PerfilUsuario
    from app.services import auth_service

    login = f"teste_func_relatorio_{uuid.uuid4().hex[:10]}"
    funcionario = usuario_service.criar_usuario(
        usuario_admin_teste, "Funcionário de Teste Relatório", login, "senha-func-123",
        PerfilUsuario.FUNCIONARIO,
    )
    usuario_funcionario = auth_service.autenticar(login, "senha-func-123")
    return funcionario, usuario_funcionario


def test_listar_historico_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_historico(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_log_erros_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_log_erros(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_saldos_em_aberto_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_saldos_em_aberto(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_saldos_em_atraso_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_saldos_em_atraso(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_saldos_em_atraso_inclui_compra_antiga_e_exclui_recente(usuario_admin_teste) -> None:
    hoje = obter_data_padrao()

    cliente_atrasado = cliente_service.cadastrar_cliente(
        usuario_admin_teste,
        "Teste Automatizado Relatorio Atraso",
        [],
        ["(35) 99999-1234"],
        [],
    )
    compra_service.registrar_compra(
        usuario_admin_teste, cliente_atrasado.id, Decimal("90.00"), hoje - timedelta(days=40), None
    )
    # Uma segunda compra recente (não atrasada) na MESMA conta: deve
    # entrar em total_em_aberto, mas não em total_em_atraso.
    compra_service.registrar_compra(
        usuario_admin_teste, cliente_atrasado.id, Decimal("15.00"), hoje, None
    )

    cliente_recente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio Recente", [], [], []
    )
    compra_service.registrar_compra(
        usuario_admin_teste, cliente_recente.id, Decimal("20.00"), hoje, None
    )

    atrasados = relatorio_service.listar_saldos_em_atraso(usuario_admin_teste, dias_atraso=30)
    nomes_atrasados = [s.nome_principal for s in atrasados]

    assert cliente_atrasado.nome_principal in nomes_atrasados
    assert cliente_recente.nome_principal not in nomes_atrasados

    saldo_atrasado = next(s for s in atrasados if s.nome_principal == cliente_atrasado.nome_principal)
    assert saldo_atrasado.total_em_atraso == Decimal("90.00")
    assert saldo_atrasado.total_em_aberto == Decimal("105.00")
    assert saldo_atrasado.dias_desde_a_compra_mais_antiga >= 40
    assert saldo_atrasado.telefone is not None
    assert "99999" in saldo_atrasado.telefone

    cliente_service.excluir_cliente(usuario_admin_teste, cliente_atrasado.id)
    cliente_service.excluir_cliente(usuario_admin_teste, cliente_recente.id)


def test_listar_clientes_acima_do_limite_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_clientes_acima_do_limite(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_clientes_acima_do_limite_encontra_quem_ultrapassou(usuario_admin_teste) -> None:
    hoje = obter_data_padrao()

    cliente_acima = cliente_service.cadastrar_cliente(
        usuario_admin_teste,
        "Teste Automatizado Relatorio Limite Acima",
        [],
        ["(35) 99999-5678"],
        [],
        limite_fiado=Decimal("50.00"),
    )
    compra_service.registrar_compra(usuario_admin_teste, cliente_acima.id, Decimal("80.00"), hoje, None)

    cliente_dentro = cliente_service.cadastrar_cliente(
        usuario_admin_teste,
        "Teste Automatizado Relatorio Limite Dentro",
        [],
        [],
        [],
        limite_fiado=Decimal("100.00"),
    )
    compra_service.registrar_compra(usuario_admin_teste, cliente_dentro.id, Decimal("50.00"), hoje, None)

    cliente_sem_limite = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio Sem Limite", [], [], []
    )
    compra_service.registrar_compra(
        usuario_admin_teste, cliente_sem_limite.id, Decimal("999.00"), hoje, None
    )

    acima_do_limite = relatorio_service.listar_clientes_acima_do_limite(usuario_admin_teste)
    nomes = [c.nome_principal for c in acima_do_limite]

    assert cliente_acima.nome_principal in nomes
    assert cliente_dentro.nome_principal not in nomes
    assert cliente_sem_limite.nome_principal not in nomes  # sem limite definido, nunca aparece

    item = next(c for c in acima_do_limite if c.nome_principal == cliente_acima.nome_principal)
    assert item.limite_fiado == Decimal("50.00")
    assert item.total_em_aberto == Decimal("80.00")
    assert item.excesso == Decimal("30.00")
    assert item.telefone is not None
    assert "99999" in item.telefone

    cliente_service.excluir_cliente(usuario_admin_teste, cliente_acima.id)
    cliente_service.excluir_cliente(usuario_admin_teste, cliente_dentro.id)
    cliente_service.excluir_cliente(usuario_admin_teste, cliente_sem_limite.id)


def test_listar_saldos_em_aberto_reflete_compra_em_aberto(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio Saldo", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("48.00"), hoje, None)

    saldos = relatorio_service.listar_saldos_em_aberto(usuario_admin_teste)
    saldo_cliente = next((s for s in saldos if s.nome_principal == cliente.nome_principal), None)

    assert saldo_cliente is not None
    assert saldo_cliente.total_em_aberto == Decimal("48.00")

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_exportar_saldos_em_aberto_csv_gera_arquivo_correto(usuario_admin_teste, tmp_path) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio CSV", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("12.34"), hoje, None)

    caminho_csv = tmp_path / "saldo_em_aberto.csv"
    relatorio_service.exportar_saldos_em_aberto_csv(usuario_admin_teste, str(caminho_csv))

    assert caminho_csv.exists()
    with open(caminho_csv, encoding="utf-8-sig", newline="") as arquivo:
        linhas = list(csv.reader(arquivo, delimiter=";"))

    assert linhas[0] == ["Código", "Cliente", "Total em Aberto (R$)"]
    linha_cliente = next((l for l in linhas[1:] if l[1] == cliente.nome_principal), None)
    assert linha_cliente is not None
    assert linha_cliente[2] == "12.34"

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_exportar_saldos_em_aberto_xlsx_gera_planilha_formatada(usuario_admin_teste, tmp_path) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio XLSX", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("56.70"), hoje, None)

    caminho_xlsx = tmp_path / "saldo_em_aberto.xlsx"
    relatorio_service.exportar_saldos_em_aberto_xlsx(usuario_admin_teste, str(caminho_xlsx))

    assert caminho_xlsx.exists()
    pasta_trabalho = openpyxl.load_workbook(caminho_xlsx)
    planilha = pasta_trabalho.active

    cabecalho = [celula.value for celula in planilha[1]]
    assert cabecalho == ["Código", "Cliente", "Total em Aberto (R$)"]
    assert planilha["A1"].font.bold is True

    linha_cliente = next(
        (linha for linha in planilha.iter_rows(min_row=2) if linha[1].value == cliente.nome_principal),
        None,
    )
    assert linha_cliente is not None
    assert linha_cliente[2].value == pytest.approx(56.70)

    ultima_linha = list(planilha.iter_rows(min_row=2))[-1]
    assert ultima_linha[0].value == "Total"

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_obter_painel_inicio_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.obter_painel_inicio(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_obter_painel_inicio_periodo_e_preenchido_corretamente(usuario_admin_teste) -> None:
    hoje = obter_data_padrao()

    painel = relatorio_service.obter_painel_inicio(
        usuario_admin_teste, data_inicio=hoje, data_fim=hoje
    )

    assert painel.periodo_inicio == hoje
    assert painel.periodo_fim == hoje


def test_obter_painel_saldos_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.obter_painel_saldos(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_obter_painel_saldos_total_em_aberto_reflete_nova_compra(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Relatorio Painel", [], [], []
    )
    hoje = obter_data_padrao()

    painel_antes = relatorio_service.obter_painel_saldos(usuario_admin_teste)
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("77.00"), hoje, None)
    painel_depois = relatorio_service.obter_painel_saldos(usuario_admin_teste)

    assert painel_depois.total_em_aberto_geral - painel_antes.total_em_aberto_geral == Decimal("77.00")

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_obter_vendas_hoje_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.obter_vendas_hoje(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_obter_vendas_hoje_total_reflete_nova_compra(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Vendas Hoje", [], [], []
    )
    # Aqui precisa ser a data real de hoje (não ``obter_data_padrao()``,
    # que pode ser "ontem" dependendo do modo configurado) — é o que
    # ``obter_vendas_hoje`` usa internamente como referência.
    hoje = date.today()

    resumo_antes = relatorio_service.obter_vendas_hoje(usuario_admin_teste)
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("42.00"), hoje, None)
    resumo_depois = relatorio_service.obter_vendas_hoje(usuario_admin_teste)

    assert resumo_depois.total_vendido_hoje - resumo_antes.total_vendido_hoje == Decimal("42.00")
    assert resumo_depois.quantidade_vendida_hoje - resumo_antes.quantidade_vendida_hoje == 1
    assert len(resumo_depois.vendas_ultimos_7_dias) == 7
    assert resumo_depois.vendas_ultimos_7_dias[-1].dia == hoje.strftime("%d/%m")
    assert (
        resumo_depois.vendas_ultimos_7_dias[-1].total - resumo_antes.vendas_ultimos_7_dias[-1].total
        == Decimal("42.00")
    )

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_historico_vendas_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_historico_vendas(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_historico_vendas_reflete_compra_registrada(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Vendas", [], [], []
    )
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("63.50"), date.today(), None)

    historico = relatorio_service.listar_historico_vendas(usuario_admin_teste)
    entrada = next((h for h in historico if h.cliente_nome == "Teste Automatizado Historico Vendas"), None)

    assert entrada is not None
    assert entrada.valor == Decimal("63.50")
    assert entrada.usuario_nome == usuario_admin_teste.nome
    assert entrada.tipo == "Venda"
    assert entrada.estornado is False

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_historico_vendas_filtra_por_data_e_por_cliente(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Vendas Filtro", [], [], []
    )
    hoje = date.today()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("10.00"), hoje, None)

    amanha = hoje + timedelta(days=1)
    depois_de_amanha = hoje + timedelta(days=2)
    fora_do_periodo = relatorio_service.listar_historico_vendas(
        usuario_admin_teste, data_inicio=amanha, data_fim=depois_de_amanha
    )
    assert not any(
        h.cliente_nome == "Teste Automatizado Historico Vendas Filtro" for h in fora_do_periodo
    )

    dentro_do_periodo = relatorio_service.listar_historico_vendas(
        usuario_admin_teste, data_inicio=hoje, data_fim=hoje
    )
    assert any(
        h.cliente_nome == "Teste Automatizado Historico Vendas Filtro" for h in dentro_do_periodo
    )

    por_nome = relatorio_service.listar_historico_vendas(
        usuario_admin_teste, cliente_nome="Historico Vendas Filtro"
    )
    assert any(h.cliente_nome == "Teste Automatizado Historico Vendas Filtro" for h in por_nome)

    por_nome_errado = relatorio_service.listar_historico_vendas(
        usuario_admin_teste, cliente_nome="Nome Que Nao Bate Com Nada"
    )
    assert not any(
        h.cliente_nome == "Teste Automatizado Historico Vendas Filtro" for h in por_nome_errado
    )

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_historico_recebimentos_funcionario_e_rejeitado(usuario_admin_teste) -> None:
    funcionario, usuario_funcionario = _criar_funcionario_teste(usuario_admin_teste)

    with pytest.raises(PermissaoNegadaError):
        relatorio_service.listar_historico_recebimentos(usuario_funcionario)

    usuario_service.definir_ativo(usuario_admin_teste, funcionario.id, False)


def test_listar_historico_recebimentos_reflete_pagamento_registrado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Recebimentos", [], [], []
    )
    hoje = date.today()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("100.00"), hoje, None)
    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("40.00"), hoje)

    historico = relatorio_service.listar_historico_recebimentos(usuario_admin_teste)
    entrada = next(
        (h for h in historico if h.cliente_nome == "Teste Automatizado Historico Recebimentos"), None
    )

    assert entrada is not None
    assert entrada.valor == Decimal("40.00")
    assert entrada.usuario_nome == usuario_admin_teste.nome
    assert entrada.tipo == "Recebimento"
    assert entrada.estornado is False

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_historico_recebimentos_marca_pagamento_estornado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Historico Recebimento Estornado", [], [], []
    )
    hoje = date.today()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("50.00"), hoje, None)
    pagamento = pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("50.00"), hoje)
    pagamento_service.estornar_pagamento(usuario_admin_teste, pagamento.id)

    historico = relatorio_service.listar_historico_recebimentos(usuario_admin_teste)
    entrada = next(
        (
            h
            for h in historico
            if h.cliente_nome == "Teste Automatizado Historico Recebimento Estornado"
        ),
        None,
    )

    assert entrada is not None
    assert entrada.estornado is True

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_listar_movimentacoes_combina_vendas_e_recebimentos_ordenado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Movimentacoes Combinadas", [], [], []
    )
    hoje = date.today()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("70.00"), hoje, None)
    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("25.00"), hoje)

    movimentacoes = relatorio_service.listar_movimentacoes(usuario_admin_teste)
    do_cliente = [
        m for m in movimentacoes if m.cliente_nome == "Teste Automatizado Movimentacoes Combinadas"
    ]

    assert {m.tipo for m in do_cliente} == {"Venda", "Recebimento"}
    # mais recente primeiro: o pagamento (registrado por último) vem antes da compra.
    assert do_cliente[0].tipo == "Recebimento"
    assert do_cliente[1].tipo == "Venda"

    apenas_vendas = relatorio_service.listar_movimentacoes(usuario_admin_teste, tipo="Venda")
    assert all(m.tipo == "Venda" for m in apenas_vendas)
    assert any(m.cliente_nome == "Teste Automatizado Movimentacoes Combinadas" for m in apenas_vendas)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
