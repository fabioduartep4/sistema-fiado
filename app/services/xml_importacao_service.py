"""Serviço de importação de XMLs de NF-e (venda a prazo).

Varre a pasta de XMLs configurada, identifica notas com natureza de
operação "Venda a prazo" ainda não importadas (pela chave de acesso) e
resolve, para cada uma, se o nome do destinatário corresponde a um
cliente já cadastrado (reaproveitando a mesma busca usada em Buscar
Cliente) ou se um novo cadastro (pendente de confirmação) deve ser criado.

Os arquivos XML nunca são alterados — apenas lidos (ver
``app.utils.nfe_parser``).

Instalações com um volume muito grande de arquivos acumulados (dezenas ou
centenas de milhares) tornam inviável reler a pasta inteira a cada
operação — por isso os dados já extraídos de cada arquivo são guardados
permanentemente em ``app.models.xml_indexado.XmlIndexado`` (compartilhado
via PostgreSQL entre todos os computadores da rede). A partir da segunda
vez que qualquer computador varre a pasta, só os arquivos genuinamente
novos desde a última varredura (de qualquer computador) precisam ser
abertos e processados — ver ``_atualizar_indice``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from app.database.connection import session_scope
from app.repositories import cliente_repository, compra_repository, xml_indexado_repository
from app.services import cliente_service, configuracao_service, historico_service
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import ClienteBusca
from app.utils import nfe_parser
from app.utils.error_handler import tratar_erros
from app.utils.nfe_parser import ProdutoXml
from app.utils.text_normalizer import normalizar_texto

ProgressoCallback = Callable[[int, int], None]

# Quantos arquivos são processados (lidos + gravados no índice) por
# transação, ao indexar arquivos novos. Mantém as transações curtas (uma
# pasta com muitos arquivos novos de uma vez não vira uma transação
# gigante) e garante que o progresso já feito sobrevive caso a indexação
# seja interrompida no meio (o app fechado, o computador desligado etc.) —
# na próxima varredura, só os arquivos ainda não gravados são reprocessados.
_TAMANHO_LOTE_INDEXACAO = 200


@dataclass(frozen=True)
class CandidatoImportacao:
    """Um XML de venda a prazo pendente de importação, com os clientes candidatos.

    Attributes:
        valor: Só a parte da nota marcada como fiado (``NotaFiscalXml.valor_fiado``)
            — numa nota com pagamento misto (parte em dinheiro/cartão,
            parte na conta), é sempre esse valor, nunca o total da nota.
    """

    caminho_arquivo: str
    chave: str
    nome_cliente_xml: str
    valor: Decimal
    data: date
    candidatos_cliente: list[ClienteBusca]


@dataclass(frozen=True)
class EscolhaImportacao:
    """Decisão do usuário sobre a quem vincular um candidato de importação."""

    caminho_arquivo: str
    cliente_id: Optional[str]  # None = criar um cliente novo (pendente)


@dataclass(frozen=True)
class ResultadoImportacao:
    """Resultado da importação de um único XML."""

    compra_id: str
    cliente_id: str
    cliente_criado: bool


def _chave_ja_importada(chave: str) -> bool:
    with session_scope() as session:
        return compra_repository.buscar_por_origem_nfe(session, chave) is not None


def _linha_indice_para_arquivo(caminho: Path) -> dict[str, Any]:
    """Lê um XML e monta a linha correspondente para gravar no índice."""
    try:
        nota = nfe_parser.ler_nfe(caminho)
    except nfe_parser.NfeXmlInvalidoError:
        return {
            "caminho_arquivo": str(caminho),
            "nome_arquivo": caminho.name,
            "chave": None,
            "natureza_operacao": None,
            "eh_venda_a_prazo": False,
            "forma_pagamento": None,
            "eh_fiado": False,
            "nome_cliente_xml": None,
            "valor_total": None,
            "valor_fiado": None,
            "data_emissao": None,
            "xml_invalido": True,
        }

    return {
        "caminho_arquivo": str(caminho),
        "nome_arquivo": caminho.name,
        "chave": nota.chave,
        "natureza_operacao": nota.natureza_operacao,
        "eh_venda_a_prazo": nota.eh_venda_a_prazo,
        "forma_pagamento": nota.formas_pagamento[0] if nota.formas_pagamento else None,
        "eh_fiado": nota.eh_fiado,
        "nome_cliente_xml": nota.nome_cliente,
        "valor_total": nota.valor_total,
        "valor_fiado": nota.valor_fiado,
        "data_emissao": nota.data_emissao,
        "xml_invalido": False,
    }


def _atualizar_indice(pasta: Path, progresso: Optional[ProgressoCallback] = None) -> None:
    """Garante que todo arquivo atualmente na pasta esteja no índice permanente.

    Só processa (abre e interpreta) os arquivos que ainda não constam no
    índice **com sucesso** — arquivos já indexados por este ou por outro
    computador da rede são pulados sem serem reabertos. É isso que torna
    viável operar sobre pastas com um volume muito grande de arquivos
    acumulados: o custo de uma varredura completa só é pago uma vez, no
    total. Um arquivo que ficou marcado como inválido numa varredura
    anterior (ex.: estava sendo gravado por outro sistema no meio da
    leitura, incompleto naquele momento) é tentado de novo a cada
    varredura futura, até dar certo — nunca fica permanentemente
    "esquecido" por causa de uma falha de leitura pontual.

    Args:
        pasta: Pasta de XMLs configurada.
        progresso: Chamado a cada arquivo processado, com
            ``(quantos já processados, total de arquivos a processar
            nesta varredura)``. Nunca chamado se não houver nada a
            processar.
    """
    arquivos = nfe_parser.listar_arquivos_xml(pasta)

    with session_scope() as session:
        resolvidos = xml_indexado_repository.listar_caminhos_resolvidos(session)

    a_processar = [caminho for caminho in arquivos if str(caminho) not in resolvidos]
    total_a_processar = len(a_processar)
    if total_a_processar == 0:
        return

    processados = 0
    for inicio in range(0, total_a_processar, _TAMANHO_LOTE_INDEXACAO):
        lote = a_processar[inicio : inicio + _TAMANHO_LOTE_INDEXACAO]
        linhas = [_linha_indice_para_arquivo(caminho) for caminho in lote]

        with session_scope() as session:
            xml_indexado_repository.inserir_lote(session, linhas)

        processados += len(lote)
        if progresso is not None:
            progresso(processados, total_a_processar)


@tratar_erros
def listar_candidatos_importacao(
    usuario_logado: UsuarioAutenticado, progresso: Optional[ProgressoCallback] = None
) -> list[CandidatoImportacao]:
    """Varre a pasta de XMLs configurada em busca de notas pendentes de importação.

    Ignora silenciosamente: XMLs inválidos/incompletos, notas cuja
    natureza da operação não seja "Venda a prazo", e notas cuja chave já
    esteja vinculada a uma compra existente.

    Args:
        usuario_logado: Usuário autenticado que está solicitando a listagem
            (reservado para uso futuro; hoje não há restrição de perfil
            aqui — ver observação na análise de requisitos).
        progresso: Ver :func:`_atualizar_indice`.

    Returns:
        Lista de :class:`CandidatoImportacao`, uma por XML pendente.
    """
    pasta = Path(configuracao_service.obter_pasta_xml())
    _atualizar_indice(pasta, progresso)

    with session_scope() as session:
        pendentes = xml_indexado_repository.listar_pendentes_de_importacao(session, str(pasta))
        # Extrai os dados enquanto a sessão está aberta, antes de resolver
        # os clientes candidatos (consulta separada, fora desta sessão).
        dados_pendentes = [
            # valor_fiado (não valor_total): numa nota com pagamento misto
            # (parte em dinheiro/cartão, parte marcada na conta), só a
            # parte marcada é dívida do cliente — ver NotaFiscalXml.valor_fiado.
            (item.caminho_arquivo, item.chave, item.nome_cliente_xml, item.valor_fiado, item.data_emissao)
            for item in pendentes
        ]

    return [
        CandidatoImportacao(
            caminho_arquivo=caminho_arquivo,
            chave=chave,
            nome_cliente_xml=nome_cliente_xml,
            valor=valor,
            data=data_emissao,
            candidatos_cliente=cliente_service.buscar_clientes(nome_cliente_xml),
        )
        for caminho_arquivo, chave, nome_cliente_xml, valor, data_emissao in dados_pendentes
    ]


@tratar_erros
def importar_xmls(
    usuario_logado: UsuarioAutenticado, escolhas: list[EscolhaImportacao]
) -> list[ResultadoImportacao]:
    """Importa os XMLs escolhidos, criando a compra (e o cliente, se necessário).

    Args:
        usuario_logado: Usuário autenticado que está confirmando a importação.
        escolhas: Uma escolha por XML (cliente já existente ou "criar novo").

    Returns:
        Lista de :class:`ResultadoImportacao`, uma por XML efetivamente
        importado (XMLs já importados nesse meio-tempo, ou inválidos, são
        ignorados silenciosamente).

    Raises:
        ValueError: Se um ``cliente_id`` escolhido não for encontrado.
    """
    resultados: list[ResultadoImportacao] = []
    # Guarda, dentro deste mesmo lote, qual cliente já foi criado para cada
    # nome (normalizado) — evita criar "Geraldo", "Geraldo" e "Geraldo" de
    # novo quando vários XMLs do mesmo lote não batem com ninguém já
    # cadastrado, mas batem entre si.
    clientes_criados_no_lote: dict[str, uuid.UUID] = {}

    for escolha in escolhas:
        try:
            nota = nfe_parser.ler_nfe(Path(escolha.caminho_arquivo))
        except nfe_parser.NfeXmlInvalidoError:
            continue

        if _chave_ja_importada(nota.chave):
            continue  # segurança extra contra duplicidade (ex.: tela aberta há muito tempo)

        with session_scope() as session:
            cliente_criado = False

            if escolha.cliente_id:
                cliente = cliente_repository.buscar_por_id(session, uuid.UUID(escolha.cliente_id))
                if cliente is None or not cliente.ativo:
                    raise ValueError(
                        f"O cliente selecionado para '{nota.nome_cliente}' não foi encontrado."
                    )
            else:
                nome_normalizado = normalizar_texto(nota.nome_cliente)
                cliente_id_do_lote = clientes_criados_no_lote.get(nome_normalizado)

                if cliente_id_do_lote is not None:
                    cliente = cliente_repository.buscar_por_id(session, cliente_id_do_lote)
                else:
                    cliente = cliente_repository.criar_cliente_pendente(session, nota.nome_cliente)
                    cliente_criado = True
                    clientes_criados_no_lote[nome_normalizado] = cliente.id
                    historico_service.registrar_historico(
                        session,
                        entidade="Cliente",
                        entidade_id=cliente.id,
                        usuario_id=uuid.UUID(usuario_logado.id),
                        acao="criacao_via_xml",
                        valor_novo=f"nome_principal={nota.nome_cliente}",
                    )

            # valor_fiado (não valor_total): numa nota com pagamento misto
            # (parte em dinheiro/cartão, parte marcada na conta), só a
            # parte marcada é dívida do cliente — ver NotaFiscalXml.valor_fiado.
            compra = compra_repository.criar_compra(
                session, cliente_id=cliente.id, valor=nota.valor_fiado, data=nota.data_emissao
            )
            compra.origem_nfe_xml = nota.chave
            session.flush()

            historico_service.registrar_historico(
                session,
                entidade="Compra",
                entidade_id=compra.id,
                usuario_id=uuid.UUID(usuario_logado.id),
                acao="criacao_via_xml",
                valor_novo=(
                    f"valor={nota.valor_fiado}, data={nota.data_emissao}, chave_nfe={nota.chave}"
                ),
            )

            resultados.append(
                ResultadoImportacao(
                    compra_id=str(compra.id), cliente_id=str(cliente.id), cliente_criado=cliente_criado
                )
            )

    return resultados


@tratar_erros
def obter_produtos(chave: str, progresso: Optional[ProgressoCallback] = None) -> list[ProdutoXml]:
    """Lê, ao vivo, os produtos de uma nota já importada, a partir do XML original.

    Não duplicamos os produtos no banco — o XML continua sendo a fonte da
    verdade, e nunca é alterado. Para localizar o arquivo certo entre
    todos os XMLs da pasta configurada, consulta primeiro o índice
    permanente (``XmlIndexado``); se a chave ainda não estiver lá (arquivo
    novo desde a última varredura de qualquer computador) ou o arquivo
    indexado não existir mais (movido/apagado), atualiza o índice (só os
    arquivos novos, não a pasta inteira) e tenta de novo antes de desistir.

    Args:
        chave: Chave de acesso da NF-e (salva em ``Compra.origem_nfe_xml``).
        progresso: Ver :func:`_atualizar_indice`.

    Returns:
        Lista de :class:`ProdutoXml`.

    Raises:
        ValueError: Se o arquivo XML original não for encontrado na pasta
            de XMLs atualmente configurada.
    """
    pasta = Path(configuracao_service.obter_pasta_xml())

    with session_scope() as session:
        entrada = xml_indexado_repository.buscar_por_chave(session, chave)
        caminho_str = entrada.caminho_arquivo if entrada is not None else None

    if caminho_str is None or not Path(caminho_str).exists():
        _atualizar_indice(pasta, progresso)
        with session_scope() as session:
            entrada = xml_indexado_repository.buscar_por_chave(session, chave)
            caminho_str = entrada.caminho_arquivo if entrada is not None else None

    if caminho_str is None or not Path(caminho_str).exists():
        raise ValueError(
            f"Arquivo XML original (chave {chave}) não foi encontrado na pasta de XMLs "
            f"configurada atualmente ({pasta}). Verifique, em Configurações, se a pasta "
            "configurada é a mesma onde os XMLs importados ficam guardados."
        )

    try:
        nota = nfe_parser.ler_nfe(Path(caminho_str))
    except nfe_parser.NfeXmlInvalidoError as exc:
        raise ValueError(
            f"O arquivo XML encontrado ({Path(caminho_str).name}) não pôde ser lido "
            "(pode estar corrompido ou incompleto)."
        ) from exc

    return nota.produtos
