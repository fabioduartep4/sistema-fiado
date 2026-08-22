"""Montagem do HTML de documentos imprimíveis (recibo e extrato do cliente).

Formatado para uma impressora térmica não-fiscal de 80mm (bobina
contínua) — layout estreito, empilhado (sem tabelas de várias colunas,
que não cabem numa bobina desse tamanho), fonte compacta.

Mantido separado de ``app.utils.impressao`` (que depende de
``QtPrintSupport``) para que a montagem do conteúdo possa ser testada sem
precisar de Qt — só recebe dados já prontos (nenhuma consulta ao banco
aqui).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html import escape
from typing import Optional, Sequence

from app.services.cliente_service import CompraResumo
from app.services.pagamento_service import PagamentoResumo

_ESTILO_BASE = """
body { font-family: 'Courier New', Consolas, monospace; color: #000000; font-size: 11px; }
h2 { font-size: 13px; text-align: center; margin: 2px 0 6px 0; }
h3 { font-size: 11px; margin: 8px 0 2px 0; }
p { margin: 2px 0; }
hr { border: none; border-top: 1px dashed #000000; margin: 6px 0; }
.item { margin: 4px 0; }
.rodape { font-size: 9px; text-align: center; margin-top: 10px; }
"""


def montar_html_recibo_pagamento(
    nome_cliente: str,
    valor_pago: Decimal,
    data_pagamento: date,
    recebido_por: str,
    observacoes: Optional[str],
    valor_resto_gerado: Decimal,
) -> str:
    """Monta o HTML do comprovante de um pagamento recém-registrado.

    Args:
        nome_cliente: Nome principal do cliente que pagou.
        valor_pago: Valor total recebido.
        data_pagamento: Data do pagamento.
        recebido_por: Nome do usuário que registrou o recebimento.
        observacoes: Observações livres do pagamento (opcional).
        valor_resto_gerado: Valor da conta "Resto" gerada, se houver
            (``Decimal("0")`` quando o pagamento quitou tudo exatamente).

    Returns:
        HTML pronto para impressão/pré-visualização (80mm).
    """
    linha_resto = ""
    if valor_resto_gerado > 0:
        linha_resto = (
            f"<p>Pagamento parcial: gerada uma nova conta (\"Resto\") de "
            f"<strong>R$ {valor_resto_gerado:.2f}</strong>.</p>"
        )
    linha_obs = f"<p>Obs: {escape(observacoes)}</p>" if observacoes else ""

    return f"""
    <html><head><style>{_ESTILO_BASE}</style></head>
    <body>
      <h2>Comprovante de Pagamento</h2>
      <hr>
      <p>Cliente: {escape(nome_cliente)}</p>
      <p>Valor pago: R$ {valor_pago:.2f}</p>
      <p>Data: {data_pagamento.strftime('%d/%m/%Y')}</p>
      <p>Recebido por: {escape(recebido_por)}</p>
      {linha_obs}
      {linha_resto}
      <hr>
      <p class="rodape">Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </body></html>
    """


_ROTULOS_STATUS_COMPRA = {"aberta": "Em aberto", "quitada": "Quitada"}


def montar_html_extrato_cliente(
    nome_cliente: str,
    id_visivel: int,
    telefones: Sequence[str],
    total_em_aberto: Decimal,
    compras: Sequence[CompraResumo],
    pagamentos: Sequence[PagamentoResumo],
) -> str:
    """Monta o HTML do extrato completo de um cliente (compras + pagamentos).

    Args:
        nome_cliente: Nome principal do cliente.
        id_visivel: Código sequencial exibido do cliente.
        telefones: Telefones de contato cadastrados.
        total_em_aberto: Total atualmente em aberto na conta.
        compras: Todas as compras do cliente (``ClienteFicha.compras``).
        pagamentos: Todos os pagamentos do cliente, inclusive estornados.

    Returns:
        HTML pronto para impressão/pré-visualização (80mm).
    """
    linhas_compras = "".join(
        f'<div class="item">'
        f"{c.data.strftime('%d/%m/%Y')} — R$ {c.valor:.2f}<br>"
        f"{_ROTULOS_STATUS_COMPRA.get(c.status, c.status)}{' [Resto]' if c.eh_resto else ''}"
        f"</div>"
        for c in compras
    )
    if not linhas_compras:
        linhas_compras = "<p>Nenhuma compra registrada.</p>"

    linhas_pagamentos = "".join(
        f'<div class="item">'
        f"{p.data_pagamento.strftime('%d/%m/%Y')} — R$ {p.valor_pago:.2f}<br>"
        f"{escape(p.recebido_por_nome)} — {'Ativo' if p.ativo else 'Estornado'}"
        f"</div>"
        for p in pagamentos
    )
    if not linhas_pagamentos:
        linhas_pagamentos = "<p>Nenhum pagamento registrado.</p>"

    telefones_texto = escape(", ".join(telefones)) if telefones else "-"

    return f"""
    <html><head><style>{_ESTILO_BASE}</style></head>
    <body>
      <h2>Extrato do Cliente</h2>
      <hr>
      <p>{escape(nome_cliente)} (cod. {id_visivel})</p>
      <p>Tel: {telefones_texto}</p>
      <p>Total em aberto: R$ {total_em_aberto:.2f}</p>
      <hr>
      <h3>COMPRAS</h3>
      {linhas_compras}
      <hr>
      <h3>PAGAMENTOS</h3>
      {linhas_pagamentos}
      <hr>
      <p class="rodape">Emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}</p>
    </body></html>
    """
