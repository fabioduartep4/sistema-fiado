"""Montagem de links "click-to-chat" do WhatsApp (``wa.me``).

Não envia nada sozinho — apenas monta a URL que, ao ser aberta (navegador
ou app do WhatsApp), já chega com o destinatário e a mensagem preenchidos,
prontos para revisão e envio manual pelo usuário. Não depende de nenhuma
API paga nem de credenciais.
"""

from __future__ import annotations

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
    nome_cliente: str, total_em_atraso: str, dias_atraso: int
) -> str:
    """Monta o texto padrão do lembrete de saldo em aberto.

    Args:
        nome_cliente: Nome principal do cliente.
        total_em_atraso: Valor já formatado (ex.: "R$ 123,45").
        dias_atraso: Há quantos dias a compra mais antiga em aberto foi feita.

    Returns:
        Mensagem pronta, editável pelo usuário antes do envio.
    """
    return (
        f"Olá, {nome_cliente}! Aqui é do Mercado Duarte. Notamos que você tem um saldo em "
        f"aberto de {total_em_atraso}, referente a uma compra de {dias_atraso} dias "
        "atrás. Assim que possível, pedimos que regularize. Qualquer dúvida, "
        "estamos à disposição!"
    )
