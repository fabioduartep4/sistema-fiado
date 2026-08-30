"""Leitura de arquivos XML de NF-e/NFC-e.

Este módulo **nunca escreve** nos arquivos XML — apenas lê e extrai os
dados necessários (nome do destinatário, natureza da operação, forma de
pagamento, data, valor total e produtos). A chave de acesso (atributo
``Id`` de ``infNFe``) é usada como identificador único de cada nota, para
detectar duplicidade de importação de forma robusta (independe do nome ou
localização do arquivo).

A natureza da operação sozinha ("Venda a prazo") **não** identifica só
vendas fiado — vendas no cartão de crédito/débito também usam essa mesma
natureza de operação neste sistema (confirmado com dados reais: uma
cliente com só compras no cartão tinha 100% das notas marcadas "Venda a
prazo"). O sinal confiável é a forma de pagamento (``tPag``, tabela oficial
da SEFAZ): ``"05"`` = Crédito Loja (fiado de verdade); outros valores
(``"01"``=Dinheiro, ``"02"``=Cheque, ``"03"``=Cartão de Crédito,
``"04"``=Cartão de Débito, ``"99"``=Outros etc.) não são fiado, mesmo
quando a nota também está marcada como "Venda a prazo". Ver
:attr:`NotaFiscalXml.eh_fiado`.

Usa ``lxml.etree.iterparse`` (leitura incremental, evento a evento) em vez
de carregar o arquivo inteiro em memória de uma vez: cada elemento é
descartado (``clear()``) assim que processado. Isso é bem mais rápido que
a biblioteca padrão ``xml.etree.ElementTree`` (``lxml`` usa a libxml2, em
C) e mantém o uso de memória baixo mesmo com muitos produtos por nota ou
muitos arquivos processados em sequência — importante porque a varredura
da pasta de XMLs roda em uma ``QThread`` separada (ver
``app.services.xml_importacao_service``), e um parser lento ali significa
a tela "Importar XMLs"/"Ver Produtos" demorar mais para responder.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree as ET

from app.utils.text_normalizer import normalizar_texto


class NfeXmlInvalidoError(Exception):
    """Lançada quando um arquivo não é um XML de NF-e válido/completo."""


@dataclass(frozen=True)
class ProdutoXml:
    """Um item (produto) de uma nota fiscal."""

    nome: str
    quantidade: Decimal
    valor: Decimal


_CODIGO_TPAG_CREDITO_LOJA = "05"

# Maior valor absoluto que as colunas de valor do banco aceitam (Numeric(12,2)
# — 10 dígitos antes da vírgula, 2 depois). Um <vNF> fora dessa faixa é dado
# corrompido/errado no próprio XML (nenhuma venda de loja chega perto disso),
# não algo que o sistema deva tentar gravar — travaria a indexação/importação
# em lote (INSERT falha para o arquivo inteiro em vez de só recusar essa nota).
_LIMITE_VALOR_TOTAL = Decimal("10000000000")


@dataclass(frozen=True)
class NotaFiscalXml:
    """Dados extraídos de um arquivo de NF-e, relevantes para o sistema."""

    caminho_arquivo: str
    chave: str
    natureza_operacao: str
    nome_cliente: str
    data_emissao: date
    valor_total: Decimal
    produtos: list[ProdutoXml]
    formas_pagamento: list[str]

    @property
    def eh_venda_a_prazo(self) -> bool:
        """True se a natureza da operação for 'Venda a prazo' (ignora acento/maiúscula).

        Não usar sozinho para decidir se é fiado — ver :attr:`eh_fiado`.
        """
        return normalizar_texto(self.natureza_operacao) == "venda a prazo"

    @property
    def eh_fiado(self) -> bool:
        """True se a nota for de fato uma venda fiado.

        Exige as duas coisas: natureza de operação "Venda a prazo" **e**
        forma de pagamento "Crédito Loja" (``tPag=05``, tabela oficial da
        SEFAZ) em pelo menos uma das formas de pagamento da nota. Só a
        natureza da operação não basta — vendas no cartão também usam essa
        mesma natureza de operação neste sistema.
        """
        return self.eh_venda_a_prazo and _CODIGO_TPAG_CREDITO_LOJA in self.formas_pagamento


def listar_arquivos_xml(pasta: Path) -> list[Path]:
    """Lista os arquivos ``.xml`` diretamente dentro de uma pasta (sem recursão).

    Args:
        pasta: Pasta configurada para os XMLs.

    Returns:
        Lista de caminhos de arquivos ``.xml``, em ordem alfabética.
    """
    if not pasta.exists():
        return []
    return sorted(pasta.glob("*.xml"))


def _texto(elemento: ET._Element) -> str:
    return (elemento.text or "").strip()


def _decimal(texto: str) -> Decimal:
    try:
        return Decimal(texto) if texto else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _tag_sem_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def ler_nfe(caminho_arquivo: Path) -> NotaFiscalXml:
    """Lê e interpreta um arquivo de NF-e, em uma única passada incremental.

    Usa ``lxml.etree.iterparse`` para nunca manter o XML inteiro em memória:
    cada elemento é descartado logo depois de lido. Mais rápido e mais leve
    que carregar a árvore inteira, especialmente em notas com muitos
    produtos ou quando várias notas são processadas em sequência (ex.:
    varredura da pasta de XMLs pendentes de importação).

    Args:
        caminho_arquivo: Caminho do arquivo ``.xml``.

    Returns:
        Os dados extraídos, como :class:`NotaFiscalXml`.

    Raises:
        NfeXmlInvalidoError: Se o arquivo não puder ser lido como XML, não
            for uma NF-e, faltar algum dado essencial (chave ou data de
            emissão), ou o valor total vier fora da faixa que as colunas
            de valor do banco aceitam (``_LIMITE_VALOR_TOTAL``) — dado
            corrompido no próprio XML; deixar passar quebraria a
            indexação/importação em lote (o banco rejeitaria o lote
            inteiro, não só essa nota). O nome do cliente **não** é
            exigido aqui — uma NFC-e de venda no balcão sem cliente
            identificado (sem ``<dest>``) é um XML completo e válido, só
            não é candidata a fiado (ver ``NotaFiscalXml.eh_fiado``);
            tratá-la como inválida fazia a imensa maioria das vendas de
            uma loja ficar marcada para releitura eterna (ver
            ``xml_indexado_repository``).
    """
    chave = ""
    natureza_operacao = ""
    nome_cliente = ""
    dh_emi_texto = ""
    valor_total_texto = ""
    produtos: list[ProdutoXml] = []
    formas_pagamento: list[str] = []

    dentro_dest = False
    dentro_prod = False
    produto_atual: dict[str, str] = {}

    try:
        contexto = ET.iterparse(str(caminho_arquivo), events=("start", "end"))
        for evento, elemento in contexto:
            tag = _tag_sem_namespace(elemento.tag)

            if evento == "start":
                if tag == "infNFe":
                    id_attr = elemento.get("Id", "")
                    chave = id_attr[3:] if id_attr.startswith("NFe") else id_attr
                elif tag == "dest":
                    dentro_dest = True
                elif tag == "prod":
                    dentro_prod = True
                    produto_atual = {}
                continue

            # evento == "end": os dados de texto já estão disponíveis; extrai
            # e libera o elemento (nunca mais precisamos dele).
            if tag == "natOp":
                natureza_operacao = _texto(elemento)
            elif tag == "dhEmi":
                dh_emi_texto = _texto(elemento)
            elif tag == "xNome" and dentro_dest:
                nome_cliente = _texto(elemento)
            elif tag == "vNF":
                valor_total_texto = _texto(elemento)
            elif tag == "tPag":
                formas_pagamento.append(_texto(elemento))
            elif dentro_prod and tag == "xProd":
                produto_atual["nome"] = _texto(elemento)
            elif dentro_prod and tag == "qCom":
                produto_atual["quantidade"] = _texto(elemento)
            elif dentro_prod and tag == "vProd":
                produto_atual["valor"] = _texto(elemento)
            elif tag == "prod":
                dentro_prod = False
            elif tag == "dest":
                dentro_dest = False
            elif tag == "det":
                # <det> é o elemento que realmente se repete (um por
                # produto), como filho direto de <infNFe> — é ele que
                # acumula em memória numa nota com muitos itens, não o
                # <prod> (filho único de cada <det>). Além de descartar
                # o próprio elemento, remove os irmãos <det>/<ide>/<dest>
                # já processados do pai: sem isso, `clear()` sozinho
                # esvazia cada nó mas o pai continua guardando a lista
                # crescente de filhos (vazios) na árvore.
                produtos.append(
                    ProdutoXml(
                        nome=produto_atual.get("nome") or "Produto sem nome",
                        quantidade=_decimal(produto_atual.get("quantidade", "")),
                        valor=_decimal(produto_atual.get("valor", "")),
                    )
                )
                elemento.clear()
                while elemento.getprevious() is not None:
                    del elemento.getparent()[0]
                continue

            elemento.clear()
    except ET.XMLSyntaxError as exc:
        raise NfeXmlInvalidoError(f"XML inválido: {caminho_arquivo.name}") from exc

    if not chave:
        raise NfeXmlInvalidoError(f"Não é uma NF-e válida: {caminho_arquivo.name}")

    data_emissao: date | None = None
    if dh_emi_texto:
        try:
            data_emissao = datetime.fromisoformat(dh_emi_texto).date()
        except ValueError:
            data_emissao = None

    if not chave or data_emissao is None:
        raise NfeXmlInvalidoError(
            f"XML incompleto (faltam dados essenciais): {caminho_arquivo.name}"
        )

    valor_total = _decimal(valor_total_texto)
    if abs(valor_total) >= _LIMITE_VALOR_TOTAL:
        raise NfeXmlInvalidoError(
            f"Valor total fora da faixa esperada ({valor_total}): {caminho_arquivo.name}"
        )

    return NotaFiscalXml(
        caminho_arquivo=str(caminho_arquivo),
        chave=chave,
        natureza_operacao=natureza_operacao,
        nome_cliente=nome_cliente,
        data_emissao=data_emissao,
        valor_total=valor_total,
        produtos=produtos,
        formas_pagamento=formas_pagamento,
    )


def ler_chave_rapida(caminho_arquivo: Path) -> str | None:
    """Lê apenas a chave de acesso de um XML, sem interpretar o restante do arquivo.

    Muito mais rápido que ``ler_nfe()`` quando o objetivo é só localizar um
    arquivo específico (pela chave) entre muitos — por exemplo, "Ver
    Produtos" na Ficha do Cliente, que precisa achar o XML certo numa pasta
    que pode ter centenas de notas. Para a leitura (``break`` implícito no
    ``return``) assim que encontra a tag ``infNFe``, sem sequer continuar
    processando o restante do arquivo.

    Args:
        caminho_arquivo: Caminho do arquivo ``.xml``.

    Returns:
        A chave de acesso (44 dígitos), ou None se o arquivo não puder
        ser lido ou não for uma NF-e.
    """
    try:
        for _evento, elemento in ET.iterparse(str(caminho_arquivo), events=("start",)):
            tag = _tag_sem_namespace(elemento.tag)
            if tag == "infNFe":
                id_attr = elemento.get("Id", "")
                chave = id_attr[3:] if id_attr.startswith("NFe") else id_attr
                return chave or None
    except ET.XMLSyntaxError:
        return None
    return None
