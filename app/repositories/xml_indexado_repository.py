"""Repositório de acesso a dados do índice permanente de XMLs.

Ver ``app.models.xml_indexado`` para o propósito desse índice (evitar
reler a pasta de XMLs inteira a cada operação em instalações com um
volume muito grande de arquivos acumulados).
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import exists, func, select
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

    Args:
        session: Sessão SQLAlchemy ativa.
        chave: Chave de acesso da NF-e.

    Returns:
        O :class:`XmlIndexado` correspondente, ou None se a chave ainda
        não tiver sido indexada.
    """
    stmt = select(XmlIndexado).where(XmlIndexado.chave == chave)
    return session.execute(stmt).scalar_one_or_none()


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

    Args:
        session: Sessão SQLAlchemy ativa.
        entradas: Lista de dicionários, um por arquivo, com as colunas de
            :class:`XmlIndexado` a inserir/atualizar.
    """
    for inicio in range(0, len(entradas), _TAMANHO_LOTE_INSERCAO):
        lote = entradas[inicio : inicio + _TAMANHO_LOTE_INSERCAO]
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
