"""Repositório de acesso a dados do índice permanente de XMLs.

Ver ``app.models.xml_indexado`` para o propósito desse índice (evitar
reler a pasta de XMLs inteira a cada operação em instalações com um
volume muito grande de arquivos acumulados).
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import bindparam, exists, func, select
from sqlalchemy import update as sqlalchemy_update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.compra import Compra
from app.models.xml_indexado import XmlIndexado

_TAMANHO_LOTE_INSERCAO = 1000


def listar_caminhos_resolvidos(session: Session) -> set[str]:
    """Lista os caminhos de arquivo que já foram lidos **com sucesso**.

    Usado para descobrir, por diferença, quais arquivos de uma varredura
    atual ainda precisam ser (re)processados: arquivos genuinamente novos
    **e** arquivos que já foram vistos antes mas ficaram marcados como
    inválidos (``xml_invalido=True``) — por exemplo, um XML que estava
    sendo gravado por outro sistema no meio da varredura, incompleto
    naquele momento, mas completo agora. Só um arquivo já indexado **e**
    lido com sucesso é pulado; um que falhou antes é tentado de novo em
    toda varredura futura, até dar certo.

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Conjunto de ``caminho_arquivo`` que não precisam ser reprocessados.
    """
    stmt = select(XmlIndexado.caminho_arquivo).where(XmlIndexado.xml_invalido.is_(False))
    return set(session.execute(stmt).scalars().all())


def buscar_por_chave(session: Session, chave: str) -> XmlIndexado | None:
    """Busca a entrada indexada de uma chave de acesso específica.

    Em condições normais existe no máximo uma linha por chave. Mas como o
    índice é identificado por ``caminho_arquivo`` (não por ``chave``), o
    mesmo arquivo físico visto por dois caminhos diferentes (ex.: a pasta
    de XMLs reconfigurada de um caminho local para um caminho de rede que
    aponta para os mesmos arquivos) pode gerar mais de uma linha para a
    mesma chave antes que ``inserir_lote`` tenha a chance de unificá-las.
    Por isso não se usa aqui uma busca que exige exatamente uma linha —
    isso nunca deve travar com erro; sempre devolve a mais recentemente
    atualizada, que é a que reflete o caminho válido mais atual.

    Args:
        session: Sessão SQLAlchemy ativa.
        chave: Chave de acesso da NF-e.

    Returns:
        O :class:`XmlIndexado` correspondente, ou None se a chave ainda
        não tiver sido indexada.
    """
    stmt = (
        select(XmlIndexado)
        .where(XmlIndexado.chave == chave)
        .order_by(XmlIndexado.atualizado_em.desc())
        .limit(1)
    )
    return session.execute(stmt).scalars().first()


_COLUNAS_ATUALIZAVEIS = (
    "nome_arquivo",
    "chave",
    "natureza_operacao",
    "eh_venda_a_prazo",
    "forma_pagamento",
    "eh_fiado",
    "nome_cliente_xml",
    "valor_total",
    "data_emissao",
    "xml_invalido",
)


def _localizar_caminhos_atuais_por_chave(session: Session, chaves: set[str]) -> dict[str, str]:
    """Para cada chave já indexada, devolve o caminho de arquivo mais recente.

    Usado por :func:`inserir_lote` para detectar arquivos que continuam
    sendo a mesma nota fiscal (mesma chave), mas passaram a ser vistos por
    um caminho diferente — o caso real que motivou esta função: a pasta de
    XMLs reconfigurada de um caminho local para um caminho de rede/servidor
    que aponta para os mesmos arquivos.
    """
    if not chaves:
        return {}
    stmt = (
        select(XmlIndexado.chave, XmlIndexado.caminho_arquivo)
        .where(XmlIndexado.chave.in_(chaves))
        .order_by(XmlIndexado.atualizado_em.asc())
    )
    caminho_por_chave: dict[str, str] = {}
    for chave, caminho in session.execute(stmt).all():
        # A última linha processada (mais recentemente atualizada) prevalece.
        caminho_por_chave[chave] = caminho
    return caminho_por_chave


def inserir_lote(session: Session, entradas: list[dict[str, Any]]) -> None:
    """Insere (ou atualiza) em lote os arquivos recém-(re)processados no índice.

    Usa ``ON CONFLICT ... DO UPDATE`` em ``caminho_arquivo``: cobre tanto
    dois computadores da rede indexando o mesmo arquivo novo ao mesmo
    tempo (sem erro de duplicidade — os dois extraem os mesmos dados do
    mesmo arquivo, então a atualização é equivalente) quanto a releitura
    de um arquivo que já estava no índice, mas marcado como inválido antes
    (atualiza a entrada existente em vez de tentar inserir uma segunda).
    Insere em lotes menores (não tudo de uma vez) para não estourar o
    limite de parâmetros de uma única instrução SQL quando há muitos
    arquivos novos (ex.: a primeira indexação de uma pasta grande).

    Antes de inserir, separa as entradas cuja chave já existe no índice sob
    um caminho **diferente** do desta entrada — nesse caso, a linha
    existente é atualizada para o novo caminho (nunca se cria uma segunda
    linha para a mesma nota fiscal). Isso nunca lê nem grava nos arquivos
    XML em si — só ajusta o índice interno do sistema.

    Args:
        session: Sessão SQLAlchemy ativa.
        entradas: Lista de dicionários, um por arquivo, com as colunas de
            :class:`XmlIndexado` a inserir/atualizar.
    """
    chaves = {entrada["chave"] for entrada in entradas if entrada.get("chave")}
    caminho_atual_por_chave = _localizar_caminhos_atuais_por_chave(session, chaves)

    entradas_normais: list[dict[str, Any]] = []
    entradas_realocadas: list[dict[str, Any]] = []
    for entrada in entradas:
        caminho_anterior = caminho_atual_por_chave.get(entrada.get("chave"))
        if caminho_anterior is not None and caminho_anterior != entrada["caminho_arquivo"]:
            entradas_realocadas.append(entrada)
        else:
            entradas_normais.append(entrada)

    if entradas_realocadas:
        stmt_realocacao = (
            sqlalchemy_update(XmlIndexado)
            .where(
                XmlIndexado.chave == bindparam("p_chave"),
                XmlIndexado.caminho_arquivo == bindparam("p_caminho_anterior"),
            )
            .values(
                caminho_arquivo=bindparam("p_caminho_novo"),
                **{coluna: bindparam(f"p_{coluna}") for coluna in _COLUNAS_ATUALIZAVEIS},
            )
        )
        parametros = [
            {
                "p_chave": entrada["chave"],
                "p_caminho_anterior": caminho_atual_por_chave[entrada["chave"]],
                "p_caminho_novo": entrada["caminho_arquivo"],
                **{f"p_{coluna}": entrada[coluna] for coluna in _COLUNAS_ATUALIZAVEIS},
            }
            for entrada in entradas_realocadas
        ]
        # Executa via a Connection (não via session.execute) para que isso
        # seja tratado como um UPDATE... WHERE parametrizado comum (estilo
        # executemany), não como o recurso de "ORM Bulk UPDATE por chave
        # primária" do SQLAlchemy 2.0 — que exigiria o "id" de cada linha
        # em cada dicionário de parâmetros, algo que não temos aqui (o
        # critério de correspondência é chave + caminho antigo).
        conexao = session.connection()
        for inicio in range(0, len(parametros), _TAMANHO_LOTE_INSERCAO):
            conexao.execute(stmt_realocacao, parametros[inicio : inicio + _TAMANHO_LOTE_INSERCAO])

    for inicio in range(0, len(entradas_normais), _TAMANHO_LOTE_INSERCAO):
        lote = entradas_normais[inicio : inicio + _TAMANHO_LOTE_INSERCAO]
        stmt = pg_insert(XmlIndexado).values(lote)
        stmt = stmt.on_conflict_do_update(
            index_elements=["caminho_arquivo"],
            set_={coluna: getattr(stmt.excluded, coluna) for coluna in _COLUNAS_ATUALIZAVEIS},
        )
        session.execute(stmt)
    session.flush()


def listar_pendentes_de_importacao(session: Session, pasta: str) -> list[XmlIndexado]:
    """Lista os XMLs indexados que são fiado de verdade e ainda não foram importados.

    "Fiado de verdade" = ``eh_fiado`` (natureza de operação "Venda a
    prazo" **e** forma de pagamento "Crédito Loja"/``tPag=05``) — a
    natureza de operação sozinha não basta, vendas no cartão também usam
    essa mesma natureza de operação neste sistema (ver
    ``app.models.xml_indexado.XmlIndexado.eh_fiado``).

    "Ainda não importado" = nenhuma :class:`Compra` ativa tem
    ``origem_nfe_xml`` igual à chave desse XML. Restrito à pasta
    informada — o índice é permanente e guarda tudo que já viu, então sem
    esse filtro, arquivos de uma pasta configurada no passado (se a Pasta
    de XMLs for reconfigurada mais tarde) continuariam aparecendo como
    pendentes mesmo não fazendo mais parte da pasta atual.

    Args:
        session: Sessão SQLAlchemy ativa.
        pasta: Pasta de XMLs atualmente configurada (``str(Path)``) — só
            arquivos diretamente dentro dela entram no resultado.

    Returns:
        Lista de :class:`XmlIndexado` pendentes de importação.
    """
    prefixo = pasta.rstrip("/\\") + os.sep
    ja_importado = select(Compra.id).where(Compra.origem_nfe_xml == XmlIndexado.chave)
    stmt = select(XmlIndexado).where(
        XmlIndexado.eh_fiado.is_(True),
        XmlIndexado.xml_invalido.is_(False),
        XmlIndexado.chave.is_not(None),
        # Comparação exata de prefixo (não LIKE): caminhos do Windows têm
        # barra invertida, que o LIKE do Postgres trata como caractere de
        # escape por padrão — um LIKE com "%" aqui nunca bateria certo.
        func.left(XmlIndexado.caminho_arquivo, len(prefixo)) == prefixo,
        ~exists(ja_importado),
    )
    return list(session.execute(stmt).scalars().all())
