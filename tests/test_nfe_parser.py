"""Testes de app.utils.nfe_parser — não tocam em banco nem em Qt.

Usa XMLs sintéticos em ``tests/fixtures/`` (dados fictícios, não os dados
reais de nenhuma nota fiscal do usuário).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.utils.nfe_parser import NfeXmlInvalidoError, ler_nfe

_PASTA_FIXTURES = Path(__file__).parent / "fixtures"


def test_ler_nfe_extrai_todos_os_dados_corretamente() -> None:
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml")

    assert nota.chave == "11111111111111111111111111111111111111111111"
    assert nota.nome_cliente == "CLIENTE DE TESTE"
    assert nota.natureza_operacao == "Venda a prazo"
    assert nota.valor_total == Decimal("35.50")
    assert nota.data_emissao.isoformat() == "2026-01-15"


def test_ler_nfe_reconhece_venda_a_prazo() -> None:
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml")
    assert nota.eh_venda_a_prazo is True


def test_ler_nfe_venda_a_vista_nao_e_reconhecida_como_a_prazo() -> None:
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo_venda_a_vista.xml")
    assert nota.eh_venda_a_prazo is False


def test_ler_nfe_extrai_forma_de_pagamento() -> None:
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml")
    assert nota.formas_pagamento == ["05"]


def test_ler_nfe_venda_a_prazo_com_pagamento_credito_loja_e_fiado() -> None:
    """Caso confirmado com dado real: tPag=05 (Crédito Loja) é o sinal
    correto de fiado, junto com a natureza de operação "Venda a prazo"."""
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml")
    assert nota.eh_venda_a_prazo is True
    assert nota.eh_fiado is True


def test_ler_nfe_venda_a_prazo_paga_no_cartao_nao_e_fiado() -> None:
    """Regressão: uma nota com natOp="Venda a prazo" mas paga no cartão
    (tPag=04, com bloco <card>) não é fiado, mesmo com a mesma natureza de
    operação de uma venda fiado de verdade — encontrado com dado real
    (cliente com várias notas "Venda a prazo", todas no cartão, nenhuma
    fiado de verdade)."""
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo_venda_a_prazo_cartao.xml")
    assert nota.eh_venda_a_prazo is True  # a natureza de operação engana
    assert nota.formas_pagamento == ["04"]
    assert nota.eh_fiado is False  # mas a forma de pagamento desfaz o engano


def test_ler_nfe_venda_a_vista_nunca_e_fiado_mesmo_com_pagamento_credito_loja() -> None:
    """Caso hipotético (não observado nos dados reais, mas coberto por
    segurança): eh_fiado exige as duas condições, não só o tPag."""
    from app.utils.nfe_parser import NotaFiscalXml

    nota = NotaFiscalXml(
        caminho_arquivo="fake.xml",
        chave="0" * 44,
        natureza_operacao="Venda à Vista",
        nome_cliente="Cliente Hipotetico",
        data_emissao=ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml").data_emissao,
        valor_total=Decimal("10.00"),
        produtos=[],
        formas_pagamento=["05"],
    )
    assert nota.eh_fiado is False


def test_ler_nfe_sem_cliente_identificado_nao_e_invalido() -> None:
    """Regressão: uma NFC-e de venda no balcão sem cliente identificado (sem
    <dest>) é um XML completo e válido — não deve levantar
    NfeXmlInvalidoError. Confirmado com dados reais: era o motivo de 121 mil
    dos ~123 mil arquivos de uma pasta real ficarem marcados como
    "inválidos" e serem relidos em toda varredura, para sempre (retry
    infinito de arquivo inválido)."""
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo_sem_cliente.xml")
    assert nota.chave == "44444444444444444444444444444444444444444444"
    assert nota.nome_cliente == ""
    assert nota.eh_venda_a_prazo is True
    assert nota.eh_fiado is False  # tPag=03 (cartão de crédito), não é fiado


def test_ler_nfe_extrai_produtos_com_quantidade_e_valor() -> None:
    nota = ler_nfe(_PASTA_FIXTURES / "nfe_exemplo.xml")

    assert len(nota.produtos) == 2
    assert nota.produtos[0].nome == "Produto de Teste A"
    assert nota.produtos[0].quantidade == Decimal("2.0000")
    assert nota.produtos[0].valor == Decimal("20.00")
    assert nota.produtos[1].nome == "Produto de Teste B"


def test_ler_nfe_arquivo_com_xml_malformado_levanta_erro(tmp_path) -> None:
    caminho = tmp_path / "invalido.xml"
    caminho.write_text("isto nao e um xml valido <<<", encoding="utf-8")

    with pytest.raises(NfeXmlInvalidoError):
        ler_nfe(caminho)


def test_ler_nfe_sem_dados_essenciais_levanta_erro(tmp_path) -> None:
    caminho = tmp_path / "incompleto.xml"
    caminho.write_text(
        '<?xml version="1.0"?>'
        '<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe">'
        '<NFe><infNFe Id="NFe123"><ide></ide></infNFe></NFe>'
        "</nfeProc>",
        encoding="utf-8",
    )

    with pytest.raises(NfeXmlInvalidoError):
        ler_nfe(caminho)


def test_listar_arquivos_xml_ignora_pasta_inexistente(tmp_path) -> None:
    from app.utils.nfe_parser import listar_arquivos_xml

    resultado = listar_arquivos_xml(tmp_path / "pasta_que_nao_existe")
    assert resultado == []


def test_listar_arquivos_xml_encontra_apenas_xml(tmp_path) -> None:
    from app.utils.nfe_parser import listar_arquivos_xml

    (tmp_path / "nota1.xml").write_text("<a/>", encoding="utf-8")
    (tmp_path / "nota2.xml").write_text("<a/>", encoding="utf-8")
    (tmp_path / "nao_e_xml.txt").write_text("texto", encoding="utf-8")

    resultado = listar_arquivos_xml(tmp_path)
    nomes = sorted(caminho.name for caminho in resultado)
    assert nomes == ["nota1.xml", "nota2.xml"]


def test_ler_chave_rapida_bate_com_a_chave_do_parse_completo() -> None:
    from app.utils.nfe_parser import ler_chave_rapida

    caminho = _PASTA_FIXTURES / "nfe_exemplo.xml"
    assert ler_chave_rapida(caminho) == ler_nfe(caminho).chave


def test_ler_chave_rapida_distingue_arquivos_diferentes() -> None:
    from app.utils.nfe_parser import ler_chave_rapida

    chave1 = ler_chave_rapida(_PASTA_FIXTURES / "nfe_exemplo.xml")
    chave2 = ler_chave_rapida(_PASTA_FIXTURES / "nfe_exemplo_venda_a_vista.xml")
    assert chave1 != chave2


def test_ler_chave_rapida_com_arquivo_invalido_retorna_none(tmp_path) -> None:
    from app.utils.nfe_parser import ler_chave_rapida

    caminho = tmp_path / "invalido.xml"
    caminho.write_text("isto nao e um xml valido <<<", encoding="utf-8")

    assert ler_chave_rapida(caminho) is None


def test_ler_nfe_com_muitos_produtos_extrai_todos_em_ordem(tmp_path) -> None:
    """Nota com muitos itens: exercita bastante a limpeza incremental de
    memória do iterparse (cada <det> processado remove os <det>/<ide>/
    <dest> anteriores já lidos da árvore) — precisa continuar extraindo
    tudo certo, na ordem certa, mesmo descartando nós pelo caminho."""
    quantidade_produtos = 50
    itens = "".join(
        f"""
      <det nItem="{i}">
        <prod>
          <xProd>Produto {i}</xProd>
          <qCom>{i}.0000</qCom>
          <vProd>{i}.50</vProd>
        </prod>
      </det>"""
        for i in range(1, quantidade_produtos + 1)
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
  <NFe>
    <infNFe Id="NFe22222222222222222222222222222222222222222222" versao="4.00">
      <ide>
        <natOp>Venda a prazo</natOp>
        <dhEmi>2026-02-20T09:00:00-03:00</dhEmi>
      </ide>
      <dest>
        <xNome>CLIENTE COM MUITOS PRODUTOS</xNome>
      </dest>{itens}
      <total>
        <ICMSTot>
          <vNF>999.99</vNF>
        </ICMSTot>
      </total>
    </infNFe>
  </NFe>
</nfeProc>
"""
    caminho = tmp_path / "muitos_produtos.xml"
    caminho.write_text(xml, encoding="utf-8")

    nota = ler_nfe(caminho)

    assert nota.chave == "22222222222222222222222222222222222222222222"
    assert nota.nome_cliente == "CLIENTE COM MUITOS PRODUTOS"
    assert nota.valor_total == Decimal("999.99")
    assert len(nota.produtos) == quantidade_produtos
    for i, produto in enumerate(nota.produtos, start=1):
        assert produto.nome == f"Produto {i}"
        assert produto.quantidade == Decimal(f"{i}.0000")
        assert produto.valor == Decimal(f"{i}.50")
