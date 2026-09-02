"""Testes de integração da orquestração de importação de XML de NF-e.

Diferente de ``tests/test_nfe_parser.py`` (que testa só a leitura do XML),
este arquivo cobre ``app.services.xml_importacao_service``: varredura da
pasta configurada, dedução de cliente, dedução por lote, deduplicação por
chave e leitura de produtos de uma nota já importada.

Cada teste escreve uma cópia do XML de exemplo com uma chave de acesso e um
nome de cliente únicos (gerados na hora), para nunca colidir com dados de
execuções anteriores da suíte.

Gravam de verdade no banco configurado em ``.env``. Só rodam com
``RODAR_TESTES_INTEGRACAO=1`` (ver ``tests/conftest.py``).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.database.connection import session_scope
from app.models.xml_indexado import XmlIndexado
from app.repositories import xml_indexado_repository
from app.services import cliente_service, configuracao_service, xml_importacao_service
from app.services.xml_importacao_service import EscolhaImportacao

pytestmark = pytest.mark.integration

_PASTA_FIXTURES = Path(__file__).parent / "fixtures"
_CHAVE_ORIGINAL = 'Id="NFe11111111111111111111111111111111111111111111"'
_NOME_ORIGINAL = "<xNome>CLIENTE DE TESTE</xNome>"
_CHAVE_ORIGINAL_CARTAO = 'Id="NFe33333333333333333333333333333333333333333333"'
_NOME_ORIGINAL_CARTAO = "<xNome>CLIENTE CARTAO DE TESTE</xNome>"
_CHAVE_ORIGINAL_MISTO = 'Id="NFe66666666666666666666666666666666666666666666"'
_NOME_ORIGINAL_MISTO = "<xNome>CLIENTE PAGAMENTO MISTO</xNome>"


def _gerar_chave() -> str:
    return (uuid.uuid4().hex + uuid.uuid4().hex)[:44]


def _escrever_xml_teste(pasta: Path, nome_arquivo: str, chave: str, nome_cliente: str) -> Path:
    texto = (_PASTA_FIXTURES / "nfe_exemplo.xml").read_text(encoding="utf-8")
    texto = texto.replace(_CHAVE_ORIGINAL, f'Id="NFe{chave}"')
    texto = texto.replace(_NOME_ORIGINAL, f"<xNome>{nome_cliente}</xNome>")
    caminho = pasta / nome_arquivo
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _escrever_xml_cartao_teste(pasta: Path, nome_arquivo: str, chave: str, nome_cliente: str) -> Path:
    """Mesma ideia de ``_escrever_xml_teste``, mas com a fixture de "Venda a
    prazo" paga no cartão (não fiado) — ver ``nfe_exemplo_venda_a_prazo_cartao.xml``."""
    texto = (_PASTA_FIXTURES / "nfe_exemplo_venda_a_prazo_cartao.xml").read_text(encoding="utf-8")
    texto = texto.replace(_CHAVE_ORIGINAL_CARTAO, f'Id="NFe{chave}"')
    texto = texto.replace(_NOME_ORIGINAL_CARTAO, f"<xNome>{nome_cliente}</xNome>")
    caminho = pasta / nome_arquivo
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _escrever_xml_pagamento_misto_teste(pasta: Path, nome_arquivo: str, chave: str, nome_cliente: str) -> Path:
    """Mesma ideia de ``_escrever_xml_teste``, mas com a fixture de nota com
    pagamento misto (parte dinheiro, parte fiado) — ver
    ``nfe_exemplo_pagamento_misto.xml``."""
    texto = (_PASTA_FIXTURES / "nfe_exemplo_pagamento_misto.xml").read_text(encoding="utf-8")
    texto = texto.replace(_CHAVE_ORIGINAL_MISTO, f'Id="NFe{chave}"')
    texto = texto.replace(_NOME_ORIGINAL_MISTO, f"<xNome>{nome_cliente}</xNome>")
    caminho = pasta / nome_arquivo
    caminho.write_text(texto, encoding="utf-8")
    return caminho


@pytest.fixture
def _pasta_xml_configurada(usuario_admin_teste, tmp_path):
    """Aponta a configuração global de pasta de XMLs para uma pasta temporária
    durante o teste, restaurando o valor original ao final."""
    pasta_original = configuracao_service.obter_pasta_xml()
    configuracao_service.definir_pasta_xml(usuario_admin_teste, str(tmp_path))
    yield tmp_path
    configuracao_service.definir_pasta_xml(usuario_admin_teste, pasta_original)


def test_listar_candidatos_encontra_xml_pendente(usuario_admin_teste, _pasta_xml_configurada) -> None:
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)

    candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
    candidato = next((c for c in candidatos if c.chave == chave), None)

    assert candidato is not None
    assert candidato.nome_cliente_xml == nome_cliente
    assert candidato.valor == Decimal("35.50")


def test_venda_a_prazo_paga_no_cartao_nao_aparece_como_candidato(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Regressão do caso real (cliente MARIA INES RIBEIRO): uma nota com
    natureza de operação "Venda a prazo" mas paga no cartão (tPag != 05)
    não deve entrar na lista de candidatos a importação como fiado."""
    chave = _gerar_chave()
    nome_cliente = f"Teste Cartao XML {uuid.uuid4().hex[:8]}"
    _escrever_xml_cartao_teste(_pasta_xml_configurada, "nota_cartao.xml", chave, nome_cliente)

    candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
    candidato = next((c for c in candidatos if c.chave == chave), None)

    assert candidato is None


def test_candidatos_pendentes_nao_vazam_de_pasta_reconfigurada(
    usuario_admin_teste, _pasta_xml_configurada, tmp_path
) -> None:
    """O índice é permanente (guarda tudo que já viu, de qualquer pasta),
    mas 'pendentes de importação' deve refletir só a pasta atualmente
    configurada — um candidato de uma pasta antiga (reconfigurada depois)
    não pode continuar aparecendo como se ainda estivesse pendente."""
    nome_pasta_antiga = f"Teste Automatizado Pasta Antiga {uuid.uuid4().hex[:8]}"
    _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", _gerar_chave(), nome_pasta_antiga)
    xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)  # indexa a pasta antiga

    # Reconfigura para uma pasta nova e diferente (vazia por enquanto).
    pasta_nova = tmp_path / "pasta_nova"
    pasta_nova.mkdir()
    configuracao_service.definir_pasta_xml(usuario_admin_teste, str(pasta_nova))
    try:
        candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
        nomes = [c.nome_cliente_xml for c in candidatos]
        assert nome_pasta_antiga not in nomes
    finally:
        configuracao_service.definir_pasta_xml(usuario_admin_teste, str(_pasta_xml_configurada))


def test_importar_cria_cliente_pendente_e_compra_vinculada(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    caminho = _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)

    resultados = xml_importacao_service.importar_xmls(
        usuario_admin_teste, [EscolhaImportacao(caminho_arquivo=str(caminho), cliente_id=None)]
    )

    assert len(resultados) == 1
    assert resultados[0].cliente_criado is True

    ficha = cliente_service.obter_ficha(resultados[0].cliente_id)
    assert ficha.nome_principal == nome_cliente
    assert ficha.confirmado is False  # criado via XML: pendente de confirmação
    assert len(ficha.compras) == 1
    assert ficha.compras[0].valor == Decimal("35.50")
    assert ficha.compras[0].origem_nfe_xml == chave

    cliente_service.excluir_cliente(usuario_admin_teste, resultados[0].cliente_id)


def test_candidato_e_compra_de_nota_com_pagamento_misto_usam_so_a_parte_fiado(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Regressão de ponta a ponta com o caso real que motivou a correção:
    nota de R$ 66,84 paga com R$ 50,00 em dinheiro + R$ 16,84 marcado na
    conta. Tanto o candidato listado quanto a compra criada precisam usar
    só os R$ 16,84 — nunca o total da nota."""
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado Pagamento Misto {uuid.uuid4().hex[:8]}"
    caminho = _escrever_xml_pagamento_misto_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)

    candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
    candidato = next((c for c in candidatos if c.chave == chave), None)
    assert candidato is not None
    assert candidato.valor == Decimal("16.84")

    resultados = xml_importacao_service.importar_xmls(
        usuario_admin_teste, [EscolhaImportacao(caminho_arquivo=str(caminho), cliente_id=None)]
    )

    assert len(resultados) == 1
    ficha = cliente_service.obter_ficha(resultados[0].cliente_id)
    assert len(ficha.compras) == 1
    assert ficha.compras[0].valor == Decimal("16.84")  # nunca R$ 66.84 (total da nota)

    cliente_service.excluir_cliente(usuario_admin_teste, resultados[0].cliente_id)


def test_importar_mesma_chave_duas_vezes_nao_duplica(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    caminho = _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)
    escolha = EscolhaImportacao(caminho_arquivo=str(caminho), cliente_id=None)

    primeira = xml_importacao_service.importar_xmls(usuario_admin_teste, [escolha])
    segunda = xml_importacao_service.importar_xmls(usuario_admin_teste, [escolha])

    assert len(primeira) == 1
    assert len(segunda) == 0  # já importado (mesma chave): ignorado silenciosamente

    cliente_service.excluir_cliente(usuario_admin_teste, primeira[0].cliente_id)


def test_importar_lote_com_mesmo_nome_novo_cria_um_unico_cliente(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Regressão: dois XMLs do mesmo lote com o mesmo nome (ainda não
    cadastrado) devem reaproveitar o cliente recém-criado, não gerar dois."""
    nome_cliente = f"Teste Automatizado XML Lote {uuid.uuid4().hex[:8]}"
    caminho1 = _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", _gerar_chave(), nome_cliente)
    caminho2 = _escrever_xml_teste(_pasta_xml_configurada, "nota2.xml", _gerar_chave(), nome_cliente)

    resultados = xml_importacao_service.importar_xmls(
        usuario_admin_teste,
        [
            EscolhaImportacao(caminho_arquivo=str(caminho1), cliente_id=None),
            EscolhaImportacao(caminho_arquivo=str(caminho2), cliente_id=None),
        ],
    )

    assert len(resultados) == 2
    assert resultados[0].cliente_id == resultados[1].cliente_id
    assert resultados[0].cliente_criado is True
    assert resultados[1].cliente_criado is False

    cliente_service.excluir_cliente(usuario_admin_teste, resultados[0].cliente_id)


def test_importar_com_cliente_ja_existente_nao_cria_novo(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    cliente_existente = cliente_service.cadastrar_cliente(
        usuario_admin_teste, f"Teste Automatizado XML Existente {uuid.uuid4().hex[:8]}", [], [], []
    )
    caminho = _escrever_xml_teste(
        _pasta_xml_configurada, "nota1.xml", _gerar_chave(), "Nome Qualquer no XML"
    )

    resultados = xml_importacao_service.importar_xmls(
        usuario_admin_teste,
        [EscolhaImportacao(caminho_arquivo=str(caminho), cliente_id=cliente_existente.id)],
    )

    assert len(resultados) == 1
    assert resultados[0].cliente_criado is False
    assert resultados[0].cliente_id == cliente_existente.id

    cliente_service.excluir_cliente(usuario_admin_teste, cliente_existente.id)


def test_obter_produtos_le_produtos_do_xml_original(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    caminho = _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)

    resultados = xml_importacao_service.importar_xmls(
        usuario_admin_teste, [EscolhaImportacao(caminho_arquivo=str(caminho), cliente_id=None)]
    )

    produtos = xml_importacao_service.obter_produtos(chave)

    assert len(produtos) == 2
    assert produtos[0].nome == "Produto de Teste A"
    assert produtos[0].valor == Decimal("20.00")

    cliente_service.excluir_cliente(usuario_admin_teste, resultados[0].cliente_id)


def test_obter_produtos_relata_progresso_ao_indexar_arquivos_novos(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """``progresso`` só é chamado quando há arquivo novo para indexar — e só
    reporta os arquivos novos desta varredura (não a pasta inteira), já que
    os arquivos já indexados não são reabertos."""
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)
    _escrever_xml_teste(_pasta_xml_configurada, "nota2.xml", _gerar_chave(), "Outro Cliente")
    _escrever_xml_teste(_pasta_xml_configurada, "nota3.xml", _gerar_chave(), "Mais Um Cliente")

    chamadas: list[tuple[int, int]] = []
    xml_importacao_service.obter_produtos(chave, progresso=lambda atual, total: chamadas.append((atual, total)))

    # Só 3 arquivos novos (menos que um lote de indexação): uma única
    # chamada, reportando os 3 processados de 3 novos.
    assert chamadas == [(3, 3)]

    # Segunda chamada com os 3 arquivos já indexados: nenhum arquivo novo,
    # progresso não é chamado nenhuma vez.
    chamadas.clear()
    xml_importacao_service.obter_produtos(chave, progresso=lambda atual, total: chamadas.append((atual, total)))
    assert chamadas == []


def test_indexacao_so_processa_arquivos_novos_desde_a_ultima_varredura(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """O ponto central do índice permanente: uma segunda varredura, depois
    de novos arquivos aparecerem na pasta, só processa os arquivos novos —
    não reabre os que já foram indexados antes."""
    _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", _gerar_chave(), "Cliente Um")
    _escrever_xml_teste(_pasta_xml_configurada, "nota2.xml", _gerar_chave(), "Cliente Dois")

    chamadas: list[tuple[int, int]] = []
    xml_importacao_service.listar_candidatos_importacao(
        usuario_admin_teste, progresso=lambda atual, total: chamadas.append((atual, total))
    )
    assert chamadas == [(2, 2)]  # indexou os 2 arquivos iniciais

    # Adiciona só mais 1 arquivo novo — a próxima varredura deve reportar
    # progresso só para esse 1 arquivo (não para os 3 no total da pasta).
    _escrever_xml_teste(_pasta_xml_configurada, "nota3.xml", _gerar_chave(), "Cliente Tres")
    chamadas.clear()
    xml_importacao_service.listar_candidatos_importacao(
        usuario_admin_teste, progresso=lambda atual, total: chamadas.append((atual, total))
    )
    assert chamadas == [(1, 1)]


def test_arquivo_invalido_e_tentado_de_novo_na_proxima_varredura(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Cobre a releitura de arquivo inválido: um XML pego pela metade (ex.:
    outro sistema ainda gravando) fica marcado como inválido, mas não é
    "esquecido" para sempre — a próxima varredura tenta ler de novo, e se
    o arquivo já estiver completo, ele aparece normalmente."""
    caminho = _pasta_xml_configurada / "nota_incompleta.xml"
    caminho.write_text("isto nao e um xml valido <<<", encoding="utf-8")

    candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
    assert candidatos == []  # arquivo inválido: ignorado, sem candidato

    # "Termina de gravar" o arquivo (agora um XML válido, de venda a prazo).
    nome_cliente = f"Teste Automatizado XML Corrigido {uuid.uuid4().hex[:8]}"
    _escrever_xml_teste(_pasta_xml_configurada, "nota_incompleta.xml", _gerar_chave(), nome_cliente)

    candidatos = xml_importacao_service.listar_candidatos_importacao(usuario_admin_teste)
    nomes = [c.nome_cliente_xml for c in candidatos]
    assert nome_cliente in nomes


def test_obter_produtos_usa_cache_e_se_recupera_de_arquivo_removido(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Cobre o índice permanente introduzido em ``obter_produtos``: a
    primeira chamada indexa o arquivo; se ele sumir depois, uma nova
    varredura (não uma exceção não tratada) deve ser tentada antes de
    desistir."""
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    caminho = _escrever_xml_teste(_pasta_xml_configurada, "nota1.xml", chave, nome_cliente)

    # Indexa o arquivo para esta pasta.
    produtos = xml_importacao_service.obter_produtos(chave)
    assert len(produtos) == 2

    # Remove o arquivo (o índice ainda aponta para ele) e tenta de novo:
    # deve cair no caminho de "arquivo indexado não existe mais", refazer a
    # varredura e então levantar ValueError (não FileNotFoundError).
    caminho.unlink()
    with pytest.raises(ValueError):
        xml_importacao_service.obter_produtos(chave)


def test_obter_produtos_apos_mudanca_de_caminho_nao_duplica_nem_quebra(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    """Regressão: quando a pasta de XMLs é reconfigurada (ex.: de um caminho
    local para um caminho de rede/servidor) e passa a enxergar o mesmo
    arquivo por um caminho diferente, o índice não pode criar uma segunda
    linha para a mesma chave — isso fazia ``obter_produtos`` (Ver Produtos)
    quebrar com "Multiple rows were found when one or none are required"."""
    chave = _gerar_chave()
    nome_cliente = f"Teste Automatizado XML {uuid.uuid4().hex[:8]}"
    caminho_antigo = _escrever_xml_teste(_pasta_xml_configurada, "nota_caminho_antigo.xml", chave, nome_cliente)

    # Indexa o arquivo no caminho "antigo" (simula o caminho local original).
    produtos = xml_importacao_service.obter_produtos(chave)
    assert len(produtos) == 2

    # "Move" o arquivo para um caminho novo dentro da mesma pasta (simula a
    # pasta configurada trocando de um caminho local para um de rede, que
    # aponta para o mesmo arquivo físico) — mesma chave, caminho diferente.
    texto = caminho_antigo.read_text(encoding="utf-8")
    caminho_antigo.unlink()
    caminho_novo = _pasta_xml_configurada / "nota_caminho_novo.xml"
    caminho_novo.write_text(texto, encoding="utf-8")

    # Não deve levantar "Multiple rows were found..." nem nenhum outro erro.
    produtos = xml_importacao_service.obter_produtos(chave)
    assert len(produtos) == 2

    with session_scope() as session:
        entrada = xml_indexado_repository.buscar_por_chave(session, chave)
        assert entrada is not None
        assert entrada.caminho_arquivo == str(caminho_novo)

        total = session.execute(
            select(func.count()).select_from(XmlIndexado).where(XmlIndexado.chave == chave)
        ).scalar_one()
        assert total == 1


def test_obter_produtos_chave_inexistente_levanta_erro(
    usuario_admin_teste, _pasta_xml_configurada
) -> None:
    with pytest.raises(ValueError):
        xml_importacao_service.obter_produtos("chave-que-nao-existe-em-nenhum-xml-desta-pasta")
