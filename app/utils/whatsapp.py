"""Montagem de links "click-to-chat" do WhatsApp (``wa.me``).

Não envia nada sozinho — apenas monta a URL que, ao ser aberta (navegador
ou app do WhatsApp), já chega com o destinatário e a mensagem preenchidos,
prontos para revisão e envio manual pelo usuário. Não depende de nenhuma
API paga nem de credenciais.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import quote

_DDI_BRASIL = "55"


def normalizar_numero_whatsapp(numero_normalizado: str) -> str:
    """Garante que um telefone (já só com dígitos) tenha o DDI do Brasil.

    Args:
        numero_normalizado: Telefone só com dígitos (DDD + número), como
            gerado por ``app.utils.text_normalizer.normalizar_telefone``.

    Returns:
        O número com o DDI ``55`` na frente, sem duplicar caso o telefone
        cadastrado já o inclua.
    """
    if numero_normalizado.startswith(_DDI_BRASIL) and len(numero_normalizado) >= 12:
        return numero_normalizado
    return f"{_DDI_BRASIL}{numero_normalizado}"


def montar_link_whatsapp(numero_normalizado: str, mensagem: str) -> str:
    """Monta a URL ``wa.me`` de um chat pré-preenchido.

    Args:
        numero_normalizado: Telefone só com dígitos (DDD + número).
        mensagem: Texto a ser preenchido na conversa (o usuário ainda
            revisa e confirma o envio dentro do WhatsApp).

    Returns:
        URL pronta para ser aberta (``QDesktopServices.openUrl`` ou
        navegador padrão).
    """
    numero = normalizar_numero_whatsapp(numero_normalizado)
    return f"https://wa.me/{numero}?text={quote(mensagem)}"


def montar_mensagem_lembrete_saldo(
    nome_cliente: str,
    data_ultimo_pagamento: Optional[str],
    total_em_aberto: str,
    atrasado: bool,
) -> str:
    """Monta o texto padrão do lembrete de conta.

    Args:
        nome_cliente: Nome principal do cliente.
        data_ultimo_pagamento: Data do último pagamento já registrado,
            formatada (ex.: "10/10/2026"). ``None`` se o cliente nunca
            tiver feito nenhum pagamento. Só usada quando ``atrasado``.
        total_em_aberto: Saldo total em aberto, já formatado (ex.: "R$ 3.000,00").
        atrasado: Se a conta tem compra em atraso — muda o tom da mensagem.

    Returns:
        Mensagem pronta, editável pelo usuário antes do envio.
    """
    if not atrasado:
        return (
            f"Olá, {nome_cliente}! Aqui é o sistema automático do Mercado Duarte. Passando para lembrar que "
            f"sua conta está no valor total de {total_em_aberto}. Qualquer dúvida, "
            "estamos à disposição!"
        )

    frase_ultimo_pagamento = (
        f"o último pagamento foi dia {data_ultimo_pagamento}"
        if data_ultimo_pagamento
        else "ainda não identificamos nenhum pagamento seu registrado"
    )
    return (
        f"Olá, {nome_cliente}! Aqui é o sistema automático do Mercado Duarte. Seu pagamento está em atraso, "
        f"{frase_ultimo_pagamento}. Atualmente sua conta está no valor total de "
        f"{total_em_aberto}. Pedimos que regularize assim que possível. Qualquer dúvida, "
        "estamos à disposição!"
    )


def montar_mensagem_lembrete_limite(nome_cliente: str, total_em_aberto: str, limite_fiado: str) -> str:
    """Monta o texto padrão do lembrete de limite de fiado excedido.

    Args:
        nome_cliente: Nome principal do cliente.
        total_em_aberto: Saldo total em aberto, já formatado (ex.: "R$ 123,45").
        limite_fiado: Limite de fiado combinado, já formatado (ex.: "R$ 100,00").

    Returns:
        Mensagem pronta, editável pelo usuário antes do envio.
    """
    return (
        f"Olá, {nome_cliente}! Aqui é o sistema automático do Mercado Duarte. Seu saldo em aberto está em "
        f"{total_em_aberto}, passando do limite combinado de {limite_fiado}. Pedimos que "
        "regularize assim que possível para continuar comprando fiado. Qualquer dúvida, "
        "estamos à disposição!"
    )
