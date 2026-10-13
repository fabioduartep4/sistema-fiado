"""Repositório de acesso a dados da entidade Cliente.

Camada de repositório: contém apenas consultas/gravações no banco, sem
regra de negócio (validação de campos obrigatórios, etc. ficam em
``app.services.cliente_service``).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.cliente import Cliente
from app.models.comprador import Comprador
from app.models.nome_alternativo import NomeAlternativo
from app.models.telefone import Telefone


def criar_cliente(
    session: Session,
    nome_principal: str,
    nomes_alternativos: list[str],
    telefones: list[str],
    compradores: list[str],
    limite_fiado: Optional[Decimal] = None,
) -> Cliente:
    """Cria um novo cliente, com seus dados relacionados (opcionais).

    As colunas normalizadas de busca (``nome_principal_normalizado`` e
    equivalentes em ``NomeAlternativo``/``Telefone``) são preenchidas
    automaticamente pelos listeners registrados em
    ``app.database.listeners`` no momento do INSERT — não precisam ser
    calculadas aqui.

    Args:
        session: Sessão SQLAlchemy ativa (o commit é responsabilidade do
            chamador, tipicamente via ``session_scope()``).
        nome_principal: Nome principal do cliente (único, obrigatório).
        nomes_alternativos: Lista de apelidos/variações (pode ser vazia).
        telefones: Lista de telefones de contato (pode ser vazia).
        compradores: Lista de nomes de compradores autorizados na conta
            (pode ser vazia).
        limite_fiado: Limite de compra no fiado (opcional; None = sem limite).

    Returns:
        O :class:`Cliente` recém-criado (já com ``id`` e ``id_visivel``
        preenchidos, após o flush).
    """
    cliente = Cliente(
        nome_principal=nome_principal, nome_principal_normalizado="", limite_fiado=limite_fiado
    )

    for nome in nomes_alternativos:
        cliente.nomes_alternativos.append(NomeAlternativo(nome=nome, nome_normalizado=""))

    for numero in telefones:
        cliente.telefones.append(Telefone(numero=numero, numero_normalizado=""))

    for nome in compradores:
        cliente.compradores.append(Comprador(nome=nome))

    session.add(cliente)
    session.flush()  # garante que id/id_visivel sejam gerados antes de retornar
    return cliente


def travar_conta(session: Session, cliente_id: uuid.UUID) -> None:
    """Trava a conta do cliente até o fim da transação atual (``SELECT ... FOR UPDATE``).

    Quem mexe nas compras em aberto de um cliente (receber, estornar)
    chama isto primeiro. Se dois computadores fizerem
    isso ao mesmo tempo para o mesmo cliente, o segundo espera o primeiro
    terminar e só então lê as compras — já atualizadas —, em vez de os
    dois decidirem em cima da mesma foto antiga da conta.
    """
    session.execute(select(Cliente.id).where(Cliente.id == cliente_id).with_for_update())


def buscar_por_id(session: Session, cliente_id: uuid.UUID) -> Cliente | None:
    """Busca um cliente (ativo ou inativo) pelo ID.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_id: UUID do cliente.

    Returns:
        O :class:`Cliente` encontrado, ou None se não existir.
    """
    return session.get(Cliente, cliente_id)


def contar_ativos(session: Session) -> int:
    """Conta quantos clientes ativos existem no sistema (card "Clientes" do Início).

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Quantidade de clientes ativos.
    """
    stmt = select(func.count()).select_from(Cliente).where(Cliente.ativo.is_(True))
    return session.execute(stmt).scalar_one()


def buscar_por_codigo(session: Session, codigo: int) -> Cliente | None:
    """Busca um cliente ativo pelo código exibido (``id_visivel``)."""
    stmt = select(Cliente).where(Cliente.ativo.is_(True), Cliente.id_visivel == codigo)
    return session.execute(stmt).scalars().first()


def buscar_por_telefone(session: Session, digitos: str) -> list[tuple[Cliente, Telefone]]:
    """Busca clientes ativos com algum telefone que contenha esses dígitos.

    Args:
        session: Sessão SQLAlchemy ativa.
        digitos: Só os dígitos digitados (ver
            ``app.utils.text_normalizer.normalizar_telefone``).

    Returns:
        Lista de tuplas (cliente, telefone correspondente).
    """
    stmt = (
        select(Cliente, Telefone)
        .join(Telefone, Telefone.cliente_id == Cliente.id)
        .where(Cliente.ativo.is_(True), Telefone.numero_normalizado.like(f"%{digitos}%"))
    )
    return [(cliente, telefone) for cliente, telefone in session.execute(stmt).all()]


def listar_ativos(
    session: Session,
    termo_normalizado: Optional[str] = None,
    codigo: Optional[int] = None,
    digitos_telefone: Optional[str] = None,
) -> list[Cliente]:
    """Lista clientes ativos, opcionalmente filtrados por nome, ordenados por nome.

    Diferente de ``buscar_por_nome_principal``/``buscar_por_nome_alternativo``
    (usadas na busca com ranking de ``cliente_service.buscar_clientes``),
    esta é uma listagem "completa" — usada pela tela "Clientes", que
    precisa mostrar todo mundo (com um filtro de status aplicado depois,
    na camada de serviço) e não só os resultados de uma busca pontual.

    Args:
        session: Sessão SQLAlchemy ativa.
        termo_normalizado: Filtro opcional por nome principal (contém, já
            normalizado — ver ``app.utils.text_normalizer.normalizar_texto``).
            ``None``/vazio lista todos os clientes ativos.
        codigo: Também aceita quem tem este código (``id_visivel``).
        digitos_telefone: Também aceita quem tem um telefone contendo
            estes dígitos.

    Returns:
        Lista de :class:`Cliente` ativos, ordenada por nome principal.
    """
    stmt = select(Cliente).where(Cliente.ativo.is_(True))
    if termo_normalizado:
        criterios = [Cliente.nome_principal_normalizado.like(f"%{termo_normalizado}%")]
        if codigo is not None:
            criterios.append(Cliente.id_visivel == codigo)
        if digitos_telefone:
            criterios.append(
                select(Telefone.id)
                .where(
                    Telefone.cliente_id == Cliente.id,
                    Telefone.numero_normalizado.like(f"%{digitos_telefone}%"),
                )
                .exists()
            )
        stmt = stmt.where(or_(*criterios))
    stmt = stmt.order_by(Cliente.nome_principal)
    return list(session.execute(stmt).scalars().all())


def buscar_por_nome_principal(session: Session, termo_normalizado: str) -> list[Cliente]:
    """Busca clientes ativos cujo nome principal normalizado contenha o termo.

    Args:
        session: Sessão SQLAlchemy ativa.
        termo_normalizado: Termo de busca já normalizado (sem
            acento/maiúscula/espaços extras — ver
            ``app.utils.text_normalizer.normalizar_texto``).

    Returns:
        Lista de :class:`Cliente` correspondentes (sem ordenação — o
        ranking é responsabilidade da camada de serviço).
    """
    padrao = f"%{termo_normalizado}%"
    stmt = select(Cliente).where(
        Cliente.ativo.is_(True), Cliente.nome_principal_normalizado.like(padrao)
    )
    return list(session.execute(stmt).scalars().all())


def buscar_por_nome_alternativo(
    session: Session, termo_normalizado: str
) -> list[tuple[Cliente, NomeAlternativo]]:
    """Busca clientes ativos que tenham um nome alternativo contendo o termo.

    Note que a busca **não** inclui compradores — apenas nome principal e
    nomes alternativos entram na busca de clientes, conforme definido no
    requisito.

    Args:
        session: Sessão SQLAlchemy ativa.
        termo_normalizado: Termo de busca já normalizado.

    Returns:
        Lista de tuplas (cliente, nome_alternativo correspondente).
    """
    padrao = f"%{termo_normalizado}%"
    stmt = (
        select(Cliente, NomeAlternativo)
        .join(NomeAlternativo, NomeAlternativo.cliente_id == Cliente.id)
        .where(
            Cliente.ativo.is_(True),
            NomeAlternativo.ativo.is_(True),
            NomeAlternativo.nome_normalizado.like(padrao),
        )
    )
    return list(session.execute(stmt).all())


def atualizar_cliente(
    session: Session,
    cliente: Cliente,
    nome_principal: str,
    nomes_alternativos: list[str],
    telefones: list[str],
    compradores: list[str],
    limite_fiado: Optional[Decimal] = None,
) -> None:
    """Atualiza os dados de um cliente existente.

    Nomes alternativos e telefones são substituídos por completo (a lista
    antiga é removida via cascade ``delete-orphan`` e a nova é criada).
    Compradores **não** são excluídos fisicamente: os que saíram da nova
    lista são apenas inativados (``ativo=False``), e os que já existiam
    (mesmo inativos) são reaproveitados/reativados em vez de duplicados —
    isso preserva o vínculo com compras já lançadas para aquele comprador.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente: Instância do cliente a ser atualizada (já carregada).
        nome_principal: Novo nome principal.
        nomes_alternativos: Nova lista completa de nomes alternativos.
        telefones: Nova lista completa de telefones.
        compradores: Nova lista completa de nomes de compradores ativos.
        limite_fiado: Novo limite de compra no fiado (None = sem limite —
            também usado para remover um limite definido antes).
    """
    cliente.nome_principal = nome_principal
    cliente.limite_fiado = limite_fiado

    cliente.nomes_alternativos.clear()
    for nome in nomes_alternativos:
        cliente.nomes_alternativos.append(NomeAlternativo(nome=nome, nome_normalizado=""))

    cliente.telefones.clear()
    for numero in telefones:
        cliente.telefones.append(Telefone(numero=numero, numero_normalizado=""))

    compradores_existentes = {c.nome.strip().lower(): c for c in cliente.compradores}
    nomes_novos_normalizados = {nome.strip().lower() for nome in compradores}

    for chave, comprador in compradores_existentes.items():
        comprador.ativo = chave in nomes_novos_normalizados

    for nome in compradores:
        chave = nome.strip().lower()
        if chave not in compradores_existentes:
            cliente.compradores.append(Comprador(nome=nome))

    session.flush()


def definir_ativo(session: Session, cliente: Cliente, ativo: bool) -> None:
    """Inativa (exclusão lógica) ou reativa um cliente.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente: Instância do cliente (já carregada).
        ativo: True para reativar, False para inativar (excluir logicamente).
    """
    cliente.ativo = ativo
    session.flush()


def criar_cliente_pendente(session: Session, nome_principal: str) -> Cliente:
    """Cria um cliente automaticamente a partir de um XML de NF-e não reconhecido.

    O cliente é criado apenas com o nome principal (sem nomes
    alternativos, telefones ou compradores) e ``confirmado=False``, para
    ser destacado na interface até que um humano confirme o cadastro.

    Args:
        session: Sessão SQLAlchemy ativa.
        nome_principal: Nome extraído do campo ``xNome`` do XML.

    Returns:
        O :class:`Cliente` recém-criado (já com ``id``/``id_visivel``
        preenchidos).
    """
    cliente = Cliente(
        nome_principal=nome_principal, nome_principal_normalizado="", confirmado=False
    )
    session.add(cliente)
    session.flush()
    return cliente


def confirmar(session: Session, cliente: Cliente) -> None:
    """Marca um cliente criado via XML como confirmado por um humano.

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente: Instância do cliente (já carregada).
    """
    cliente.confirmado = True
    session.flush()


def listar_ativos_agrupaveis(session: Session) -> list[Cliente]:
    """Lista todos os clientes ativos, ordenados por nome normalizado.

    Usado pela detecção de duplicados (agrupamento por nome é feito na
    camada de serviço).

    Args:
        session: Sessão SQLAlchemy ativa.

    Returns:
        Lista de :class:`Cliente` ativos.
    """
    stmt = (
        select(Cliente)
        .where(Cliente.ativo.is_(True))
        .order_by(Cliente.nome_principal_normalizado, Cliente.criado_em)
    )
    return list(session.execute(stmt).scalars().all())


def mesclar_em(session: Session, cliente_principal: Cliente, cliente_duplicado: Cliente) -> None:
    """Move nomes alternativos, telefones e compradores do duplicado para o principal.

    Compras e pagamentos são movidos separadamente (ver
    ``app.repositories.compra_repository.reatribuir_cliente`` e o
    equivalente em ``pagamento_repository``, chamados antes desta função
    pelo serviço). O cliente duplicado é inativado ao final (exclusão
    lógica — nada é apagado).

    Args:
        session: Sessão SQLAlchemy ativa.
        cliente_principal: Cliente que permanece ativo e recebe os dados.
        cliente_duplicado: Cliente que será inativado após a mesclagem.
    """
    for nome_alt in list(cliente_duplicado.nomes_alternativos):
        nome_alt.cliente_id = cliente_principal.id
    for telefone in list(cliente_duplicado.telefones):
        telefone.cliente_id = cliente_principal.id
    for comprador in list(cliente_duplicado.compradores):
        comprador.cliente_id = cliente_principal.id

    cliente_duplicado.ativo = False
    session.flush()
