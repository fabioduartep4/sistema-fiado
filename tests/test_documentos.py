"""Testes de app.utils.documentos — não tocam banco nem Qt.

Só verificam a montagem do HTML (dados já prontos são passados como
argumento); a impressão em si (``app.utils.impressao``) depende de
``QtPrintSupport`` e não é coberta aqui.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services.cliente_service import CompraResumo
from app.services.pagamento_service import PagamentoResumo
from app.utils.documentos import montar_html_extrato_cliente, montar_html_recibo_pagamento


def test_montar_html_recibo_pagamento_inclui_dados_principais() -> None:
    html = montar_html_recibo_pagamento(
        nome_cliente="Maria da Silva",
        valor_pago=Decimal("50.00"),
        data_pagamento=date(2026, 3, 10),
        recebido_por="Administrador",
        observacoes="Pagamento parcial",
        valor_resto_gerado=Decimal("0"),
    )

    assert "Maria da Silva" in html
    assert "R$ 50.00" in html
    assert "10/03/2026" in html
    assert "Administrador" in html
    assert "Pagamento parcial" in html
    assert "Resto" not in html  # não gerou resto: não deve mencionar


def test_montar_html_recibo_pagamento_menciona_resto_quando_gerado() -> None:
    html = montar_html_recibo_pagamento(
        nome_cliente="João",
        valor_pago=Decimal("30.00"),
        data_pagamento=date(2026, 3, 10),
        recebido_por="Administrador",
        observacoes=None,
        valor_resto_gerado=Decimal("15.50"),
    )

    assert "R$ 15.50" in html
    assert "Resto" in html


def test_montar_html_extrato_cliente_lista_compras_e_pagamentos() -> None:
    compras = [
        CompraResumo(
            id="c1", valor=Decimal("20.00"), data=date(2026, 1, 5),
            status="aberta", eh_resto=False, origem_nfe_xml=None,
        ),
        CompraResumo(
            id="c2", valor=Decimal("10.00"), data=date(2026, 1, 10),
            status="quitada", eh_resto=True, origem_nfe_xml=None,
        ),
    ]
    pagamentos = [
        PagamentoResumo(
            id="p1", valor_pago=Decimal("10.00"), data_pagamento=date(2026, 1, 12),
            recebido_por_nome="Administrador", observacoes=None, ativo=True,
            compras_quitadas=[],
        ),
    ]

    html = montar_html_extrato_cliente(
        nome_cliente="Maria da Silva",
        id_visivel=7,
        telefones=["35999998888"],
        total_em_aberto=Decimal("20.00"),
        compras=compras,
        pagamentos=pagamentos,
    )

    assert "Maria da Silva" in html
    assert "cod. 7" in html
    assert "35999998888" in html
    assert "R$ 20.00" in html
    assert "R$ 10.00" in html
    assert "Em aberto" in html
    assert "Quitada" in html
    assert "Ativo" in html


def test_montar_html_recibo_pagamento_escapa_caracteres_especiais_do_nome() -> None:
    html = montar_html_recibo_pagamento(
        nome_cliente="Bar & Mercearia <Centro>",
        valor_pago=Decimal("10.00"),
        data_pagamento=date(2026, 3, 10),
        recebido_por="Administrador",
        observacoes=None,
        valor_resto_gerado=Decimal("0"),
    )

    assert "Bar &amp; Mercearia &lt;Centro&gt;" in html
    assert "<Centro>" not in html  # não pode virar uma tag HTML de verdade


def test_montar_html_extrato_cliente_sem_compras_nem_pagamentos() -> None:
    html = montar_html_extrato_cliente(
        nome_cliente="Cliente Novo",
        id_visivel=1,
        telefones=[],
        total_em_aberto=Decimal("0"),
        compras=[],
        pagamentos=[],
    )

    assert "Nenhuma compra registrada." in html
    assert "Nenhum pagamento registrado." in html
