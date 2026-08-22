"""Testes de integração da lógica de quitação FIFO (Receber Conta).

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.services import cliente_service, compra_service, pagamento_service
from app.utils.date_utils import obter_data_padrao

pytestmark = pytest.mark.integration


def test_fifo_gera_resto_quando_pagamento_termina_no_meio_de_uma_compra(usuario_admin_teste) -> None:
    """Reproduz o exemplo do enunciado: Geraldo com 20+30, paga 40, sobra Resto de 10."""
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado FIFO Geraldo", [], [], []
    )
    hoje = obter_data_padrao()

    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("20.00"), hoje, None)
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("30.00"), hoje, None)

    resultado = pagamento_service.registrar_pagamento(
        usuario_admin_teste, cliente.id, Decimal("40.00"), hoje, "pagamento de teste automatizado"
    )

    assert resultado.valor_resto_gerado == Decimal("10.00")

    ficha = cliente_service.obter_ficha(cliente.id)
    compras_abertas = [c for c in ficha.compras if c.status != "quitada"]
    assert len(compras_abertas) == 1
    assert compras_abertas[0].valor == Decimal("10.00")
    assert compras_abertas[0].eh_resto is True

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_fifo_pagamento_exato_nao_gera_resto(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado FIFO Exato", [], [], []
    )
    hoje = obter_data_padrao()

    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("15.00"), hoje, None)
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("25.00"), hoje, None)

    resultado = pagamento_service.registrar_pagamento(
        usuario_admin_teste, cliente.id, Decimal("40.00"), hoje, None
    )

    assert resultado.valor_resto_gerado == Decimal("0")
    ficha = cliente_service.obter_ficha(cliente.id)
    assert all(c.status == "quitada" for c in ficha.compras)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_pagamento_maior_que_total_em_aberto_e_rejeitado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado FIFO Rejeicao", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("10.00"), hoje, None)

    with pytest.raises(ValueError):
        pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("999.00"), hoje, None)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_registrar_compra_com_valor_zero_ou_negativo_e_rejeitado(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Compra Invalida", [], [], []
    )
    hoje = obter_data_padrao()

    with pytest.raises(ValueError):
        compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("0"), hoje, None)

    with pytest.raises(ValueError):
        compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("-5.00"), hoje, None)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_estorno_reabre_a_compra_quitada(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Estorno", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("15.00"), hoje, None)

    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("15.00"), hoje, None)

    pagamentos = pagamento_service.listar_pagamentos_por_cliente(cliente.id)
    assert len(pagamentos) == 1

    pagamento_service.estornar_pagamento(usuario_admin_teste, pagamentos[0].id)

    ficha = cliente_service.obter_ficha(cliente.id)
    compras_abertas = [c for c in ficha.compras if c.status != "quitada"]
    assert len(compras_abertas) == 1
    assert compras_abertas[0].valor == Decimal("15.00")

    pagamentos_apos = pagamento_service.listar_pagamentos_por_cliente(cliente.id)
    assert pagamentos_apos[0].ativo is False

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_estorno_de_pagamento_ja_estornado_levanta_erro(usuario_admin_teste) -> None:
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Estorno Duplo", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("10.00"), hoje, None)
    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("10.00"), hoje, None)

    pagamentos = pagamento_service.listar_pagamentos_por_cliente(cliente.id)
    pagamento_service.estornar_pagamento(usuario_admin_teste, pagamentos[0].id)

    with pytest.raises(ValueError):
        pagamento_service.estornar_pagamento(usuario_admin_teste, pagamentos[0].id)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)


def test_estorno_bloqueado_quando_resto_ja_foi_pago(usuario_admin_teste) -> None:
    """Se o 'Resto' gerado por um pagamento já foi quitado, não dá pra estornar o original."""
    cliente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, "Teste Automatizado Estorno Bloqueado", [], [], []
    )
    hoje = obter_data_padrao()
    compra_service.registrar_compra(usuario_admin_teste, cliente.id, Decimal("30.00"), hoje, None)

    # Paga parte da compra de 30 (20), gerando um Resto de 10.
    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("20.00"), hoje, None)
    # Quita o Resto de 10 com um segundo pagamento.
    pagamento_service.registrar_pagamento(usuario_admin_teste, cliente.id, Decimal("10.00"), hoje, None)

    pagamentos = pagamento_service.listar_pagamentos_por_cliente(cliente.id)
    # Tenta estornar o pagamento original (de 20), que gerou o Resto já quitado pelo segundo.
    pagamento_original = max(pagamentos, key=lambda p: p.valor_pago)

    with pytest.raises(pagamento_service.EstornoNaoPermitidoError):
        pagamento_service.estornar_pagamento(usuario_admin_teste, pagamento_original.id)

    cliente_service.excluir_cliente(usuario_admin_teste, cliente.id)
