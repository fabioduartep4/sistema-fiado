"""Serviço de cliente.

Contém a regra de negócio de cadastro, busca (com ranking), ficha do
cliente, edição e exclusão lógica.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.database.connection import session_scope
from app.repositories import cliente_repository, compra_repository, pagamento_repository
from app.services import historico_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros
from app.utils.text_normalizer import normalizar_texto

_TAMANHO_MAXIMO_NOME = 150
_TAMANHO_MAXIMO_TELEFONE = 30


@dataclass(frozen=True)
class ClienteResumo:
    """Dados básicos de um cliente recém-cadastrado, para exibição."""

    id: str
    id_visivel: int
    nome_principal: str


def _limpar_lista(valores: list[str], tamanho_maximo: int) -> list[str]:
    """Remove espaços extras, entradas vazias e duplicadas de uma lista.

    Args:
        valores: Lista de textos (ex.: nomes alternativos digitados).
        tamanho_maximo: Tamanho máximo aceito por item (mesmo limite da
            coluna no banco), usado para validar cada entrada.

    Returns:
        Lista limpa, sem duplicatas e na ordem original de digitação.

    Raises:
        ValueError: Se algum item exceder o tamanho máximo permitido.
    """
    limpos: list[str] = []
    vistos: set[str] = set()
    for valor in valores:
        item = valor.strip()
        if not item:
            continue
        if len(item) > tamanho_maximo:
            raise ValueError(f"O valor '{item}' excede o tamanho máximo de {tamanho_maximo} caracteres.")
        if item.lower() not in vistos:
            vistos.add(item.lower())
            limpos.append(item)
    return limpos


@tratar_erros
def cadastrar_cliente(
    usuario_logado: UsuarioAutenticado,
    nome_principal: str,
    nomes_alternativos: list[str],
    telefones: list[str],
    compradores: list[str],
) -> ClienteResumo:
    """Cadastra um novo cliente.

    Args:
        usuario_logado: Usuário autenticado que está cadastrando o cliente
            (usado para registrar o histórico de auditoria).
        nome_principal: Nome principal do cliente (obrigatório, único por
            cadastro — mas repetições não são bloqueadas pelo sistema, já
            que duas pessoas podem ter o mesmo nome; a distinção fica por
            conta dos nomes alternativos/telefones, se necessário).
        nomes_alternativos: Apelidos/variações do nome (opcional, 0 ou mais).
        telefones: Telefones de contato (opcional, 0 ou mais).
        compradores: Pessoas autorizadas a comprar na conta (opcional, 0 ou mais).

    Returns:
        Um :class:`ClienteResumo` com os dados do cliente recém-criado.

    Raises:
        ValueError: Se o nome principal estiver vazio ou algum campo
            exceder o tamanho máximo permitido.
    """
    nome_principal = nome_principal.strip()
    if not nome_principal:
        raise ValueError("O nome principal é obrigatório.")
    if len(nome_principal) > _TAMANHO_MAXIMO_NOME:
        raise ValueError(f"O nome principal excede o tamanho máximo de {_TAMANHO_MAXIMO_NOME} caracteres.")

    nomes_alternativos = _limpar_lista(nomes_alternativos, _TAMANHO_MAXIMO_NOME)
    telefones = _limpar_lista(telefones, _TAMANHO_MAXIMO_TELEFONE)
    compradores = _limpar_lista(compradores, _TAMANHO_MAXIMO_NOME)

    with session_scope() as session:
        cliente = cliente_repository.criar_cliente(
            session,
            nome_principal=nome_principal,
            nomes_alternativos=nomes_alternativos,
            telefones=telefones,
            compradores=compradores,
        )
        historico_service.registrar_historico(
            session,
            entidade="Cliente",
            entidade_id=cliente.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="criacao",
            valor_novo=f"nome_principal={nome_principal}",
        )
        return ClienteResumo(
            id=str(cliente.id),
            id_visivel=cliente.id_visivel,
            nome_principal=cliente.nome_principal,
        )


@dataclass(frozen=True)
class ClienteBusca:
    """Resultado de uma busca de cliente, pronto para exibição na lista."""

    id: str
    id_visivel: int
    nome_principal: str
    nome_alternativo_encontrado: str | None
    confirmado: bool


@dataclass(frozen=True)
class CompraResumo:
    """Dados de uma compra, para exibição na ficha do cliente."""

    id: str
    valor: Decimal
    data: date
    status: str
    eh_resto: bool
    origem_nfe_xml: str | None


@dataclass(frozen=True)
class ClienteFicha:
    """Dados completos de um cliente, para exibição na ficha do cliente."""

    id: str
    id_visivel: int
    nome_principal: str
    nomes_alternativos: list[str]
    telefones: list[str]
    compradores: list[str]
    compras: list[CompraResumo]
    total_em_aberto: Decimal
    confirmado: bool


@tratar_erros
def buscar_clientes(termo: str, limite: int = 30) -> list[ClienteBusca]:
    """Busca clientes por nome principal ou nome alternativo.

    A busca ignora acentos, maiúsculas/minúsculas e espaços extras. Os
    resultados são ordenados priorizando, nesta ordem: (1) nome principal
    que começa com o termo, (2) nome alternativo que começa com o termo,
    (3) nome principal que contém o termo, (4) nome alternativo que contém
    o termo — e, dentro de cada grupo, em ordem alfabética pelo nome
    principal. A busca não considera compradores.

    Args:
        termo: Texto digitado pelo usuário.
        limite: Número máximo de resultados retornados.

    Returns:
        Lista de :class:`ClienteBusca`, já ordenada para exibição. Vazia
        se ``termo`` estiver em branco.
    """
    termo = termo.strip()
    if not termo:
        return []

    termo_normalizado = normalizar_texto(termo)

    with session_scope() as session:
        clientes_por_principal = cliente_repository.buscar_por_nome_principal(
            session, termo_normalizado
        )
        pares_por_alternativo = cliente_repository.buscar_por_nome_alternativo(
            session, termo_normalizado
        )

        candidatos: dict[str, tuple[int, str, ClienteBusca]] = {}

        for cliente in clientes_por_principal:
            prioridade = 0 if cliente.nome_principal_normalizado.startswith(termo_normalizado) else 2
            candidatos[str(cliente.id)] = (
                prioridade,
                cliente.nome_principal_normalizado,
                ClienteBusca(
                    id=str(cliente.id),
                    id_visivel=cliente.id_visivel,
                    nome_principal=cliente.nome_principal,
                    nome_alternativo_encontrado=None,
                    confirmado=cliente.confirmado,
                ),
            )

        for cliente, nome_alt in pares_por_alternativo:
            if str(cliente.id) in candidatos:
                continue  # já priorizado por corresponder ao nome principal
            prioridade = 1 if nome_alt.nome_normalizado.startswith(termo_normalizado) else 3
            candidatos[str(cliente.id)] = (
                prioridade,
                cliente.nome_principal_normalizado,
                ClienteBusca(
                    id=str(cliente.id),
                    id_visivel=cliente.id_visivel,
                    nome_principal=cliente.nome_principal,
                    nome_alternativo_encontrado=nome_alt.nome,
                    confirmado=cliente.confirmado,
                ),
            )

        resultados_ordenados = sorted(candidatos.values(), key=lambda item: (item[0], item[1]))
        return [item[2] for item in resultados_ordenados[:limite]]


def _montar_ficha(cliente_id_str: str, session) -> ClienteFicha:  # type: ignore[no-untyped-def]
    """Monta o DTO de ficha a partir de um cliente já carregado na sessão."""
    cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id_str))
    if cliente is None or not cliente.ativo:
        raise ValueError("Cliente não encontrado.")

    compras = compra_repository.listar_por_cliente(session, cliente.id)
    total_em_aberto = compra_repository.calcular_total_em_aberto(session, cliente.id)

    return ClienteFicha(
        id=str(cliente.id),
        id_visivel=cliente.id_visivel,
        nome_principal=cliente.nome_principal,
        nomes_alternativos=[n.nome for n in cliente.nomes_alternativos if n.ativo],
        telefones=[t.numero for t in cliente.telefones if t.ativo],
        compradores=[c.nome for c in cliente.compradores if c.ativo],
        compras=[
            CompraResumo(
                id=str(c.id),
                valor=c.valor,
                data=c.data,
                status=c.status.value,
                eh_resto=c.eh_resto,
                origem_nfe_xml=c.origem_nfe_xml,
            )
            for c in compras
        ],
        total_em_aberto=total_em_aberto,
        confirmado=cliente.confirmado,
    )


@tratar_erros
def obter_ficha(cliente_id: str) -> ClienteFicha:
    """Monta a ficha completa de um cliente (dados + compras + total em aberto).

    Args:
        cliente_id: UUID (como texto) do cliente.

    Returns:
        A :class:`ClienteFicha` do cliente.

    Raises:
        ValueError: Se o cliente não existir ou estiver inativo.
    """
    with session_scope() as session:
        return _montar_ficha(cliente_id, session)


@tratar_erros
def editar_cliente(
    usuario_logado: UsuarioAutenticado,
    cliente_id: str,
    nome_principal: str,
    nomes_alternativos: list[str],
    telefones: list[str],
    compradores: list[str],
) -> ClienteFicha:
    """Edita os dados de um cliente existente.

    Args:
        usuario_logado: Usuário autenticado que está editando (para o
            registro de histórico).
        cliente_id: UUID (como texto) do cliente a ser editado.
        nome_principal: Novo nome principal (obrigatório).
        nomes_alternativos: Nova lista completa de nomes alternativos.
        telefones: Nova lista completa de telefones.
        compradores: Nova lista completa de nomes de compradores.

    Returns:
        A :class:`ClienteFicha` atualizada.

    Raises:
        ValueError: Se o cliente não for encontrado, o nome principal
            estiver vazio, ou algum campo exceder o tamanho máximo.
    """
    nome_principal = nome_principal.strip()
    if not nome_principal:
        raise ValueError("O nome principal é obrigatório.")
    if len(nome_principal) > _TAMANHO_MAXIMO_NOME:
        raise ValueError(
            f"O nome principal excede o tamanho máximo de {_TAMANHO_MAXIMO_NOME} caracteres."
        )

    nomes_alternativos = _limpar_lista(nomes_alternativos, _TAMANHO_MAXIMO_NOME)
    telefones = _limpar_lista(telefones, _TAMANHO_MAXIMO_TELEFONE)
    compradores = _limpar_lista(compradores, _TAMANHO_MAXIMO_NOME)

    with session_scope() as session:
        cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id))
        if cliente is None or not cliente.ativo:
            raise ValueError("Cliente não encontrado.")

        valor_antigo = f"nome_principal={cliente.nome_principal}"
        cliente_repository.atualizar_cliente(
            session, cliente, nome_principal, nomes_alternativos, telefones, compradores
        )
        historico_service.registrar_historico(
            session,
            entidade="Cliente",
            entidade_id=cliente.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="edicao",
            valor_antigo=valor_antigo,
            valor_novo=f"nome_principal={nome_principal}",
        )
        return _montar_ficha(cliente_id, session)


@tratar_erros
def excluir_cliente(usuario_logado: UsuarioAutenticado, cliente_id: str) -> None:
    """Exclui logicamente um cliente (o histórico e as compras são preservados).

    Args:
        usuario_logado: Usuário autenticado que está excluindo (para o
            registro de histórico e para a checagem de permissão).
        cliente_id: UUID (como texto) do cliente a ser excluído.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador
            (correção aplicada na etapa 9 — a tabela de permissões original
            já previa isso, mas a checagem não tinha sido implementada).
        ValueError: Se o cliente não for encontrado ou já estiver inativo.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem excluir clientes.")

    with session_scope() as session:
        cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id))
        if cliente is None or not cliente.ativo:
            raise ValueError("Cliente não encontrado.")

        cliente_repository.definir_ativo(session, cliente, False)
        historico_service.registrar_historico(
            session,
            entidade="Cliente",
            entidade_id=cliente.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="exclusao_logica",
        )


@tratar_erros
def confirmar_cliente(usuario_logado: UsuarioAutenticado, cliente_id: str) -> None:
    """Confirma um cliente criado automaticamente pela importação de XML.

    Disponível para qualquer usuário autenticado (não é uma ação sensível
    como excluir/estornar — é só uma revisão de cadastro).

    Args:
        usuario_logado: Usuário autenticado que está confirmando (para o
            registro de histórico).
        cliente_id: UUID (como texto) do cliente a ser confirmado.

    Raises:
        ValueError: Se o cliente não for encontrado ou já estiver inativo.
    """
    with session_scope() as session:
        cliente = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_id))
        if cliente is None or not cliente.ativo:
            raise ValueError("Cliente não encontrado.")

        cliente_repository.confirmar(session, cliente)
        historico_service.registrar_historico(
            session,
            entidade="Cliente",
            entidade_id=cliente.id,
            usuario_id=uuid.UUID(usuario_logado.id),
            acao="confirmacao_xml",
        )


@dataclass(frozen=True)
class ClienteDuplicadoOpcao:
    """Um cliente candidato dentro de um grupo de possíveis duplicados."""

    id: str
    id_visivel: int
    nome_principal: str


@dataclass(frozen=True)
class GrupoDuplicados:
    """Um grupo de clientes ativos com o mesmo nome principal (normalizado)."""

    nome_normalizado: str
    clientes: list[ClienteDuplicadoOpcao]


def _exigir_administrador(usuario_logado: UsuarioAutenticado) -> None:
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem mesclar clientes duplicados.")


@tratar_erros
def listar_grupos_duplicados(usuario_logado: UsuarioAutenticado) -> list[GrupoDuplicados]:
    """Agrupa os clientes ativos por nome principal (normalizado), para detectar duplicados.

    Só entram na lista grupos com 2 ou mais clientes — ou seja, nomes que
    aparecem uma única vez não são retornados.

    Args:
        usuario_logado: Usuário autenticado que está consultando.

    Returns:
        Lista de :class:`GrupoDuplicados`, ordenada por nome.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    _exigir_administrador(usuario_logado)

    with session_scope() as session:
        clientes = cliente_repository.listar_ativos_agrupaveis(session)

        agrupados: dict[str, list] = {}
        for cliente in clientes:
            agrupados.setdefault(cliente.nome_principal_normalizado, []).append(cliente)

        grupos = [
            GrupoDuplicados(
                nome_normalizado=nome_normalizado,
                clientes=[
                    ClienteDuplicadoOpcao(
                        id=str(c.id), id_visivel=c.id_visivel, nome_principal=c.nome_principal
                    )
                    for c in lista
                ],
            )
            for nome_normalizado, lista in agrupados.items()
            if len(lista) >= 2
        ]
        grupos.sort(key=lambda g: g.nome_normalizado)
        return grupos


@tratar_erros
def mesclar_clientes(
    usuario_logado: UsuarioAutenticado,
    cliente_principal_id: str,
    clientes_duplicados_ids: list[str],
) -> None:
    """Mescla um ou mais clientes duplicados em um cliente principal.

    Move compras, pagamentos, nomes alternativos, telefones e compradores
    dos duplicados para o principal, e inativa os duplicados (exclusão
    lógica — nada é apagado do banco).

    Args:
        usuario_logado: Usuário autenticado que está mesclando (para o
            registro de histórico e para a checagem de permissão).
        cliente_principal_id: UUID (como texto) do cliente que permanece.
        clientes_duplicados_ids: UUIDs (como texto) dos clientes a mesclar
            no principal.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se a lista de duplicados estiver vazia, se o principal
            estiver nela, ou se o cliente principal não for encontrado.
    """
    _exigir_administrador(usuario_logado)

    if not clientes_duplicados_ids:
        raise ValueError("Selecione ao menos um cliente duplicado para mesclar.")
    if cliente_principal_id in clientes_duplicados_ids:
        raise ValueError("O cliente principal não pode estar na lista de duplicados.")

    with session_scope() as session:
        principal = cliente_repository.buscar_por_id(session, uuid.UUID(cliente_principal_id))
        if principal is None or not principal.ativo:
            raise ValueError("Cliente principal não encontrado.")

        for duplicado_id in clientes_duplicados_ids:
            duplicado = cliente_repository.buscar_por_id(session, uuid.UUID(duplicado_id))
            if duplicado is None or not duplicado.ativo:
                continue  # já foi mesclado/inativado antes; ignora silenciosamente

            compra_repository.reatribuir_cliente(session, duplicado.id, principal.id)
            pagamento_repository.reatribuir_cliente(session, duplicado.id, principal.id)
            cliente_repository.mesclar_em(session, principal, duplicado)

            historico_service.registrar_historico(
                session,
                entidade="Cliente",
                entidade_id=duplicado.id,
                usuario_id=uuid.UUID(usuario_logado.id),
                acao="mesclagem",
                valor_antigo=f"nome_principal={duplicado.nome_principal}",
                valor_novo=f"mesclado_em={principal.id}",
            )
