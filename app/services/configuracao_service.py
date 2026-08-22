"""Serviço de configurações globais do sistema.

Expõe o modo de data padrão usado em Adicionar Compra e Receber Conta
("dia atual" ou "dia anterior"), a pasta de destino dos backups e a data
do último backup automático — todas configurações globais (armazenadas no
PostgreSQL central, válidas para todos os computadores da rede). A tela de
Configurações (etapa 8) reaproveitará este mesmo serviço para permitir a
edição pela interface.
"""

from __future__ import annotations

import enum
from datetime import date

from app.config.settings import settings
from app.database.connection import session_scope
from app.repositories import configuracao_repository
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros

CHAVE_MODO_DATA_PADRAO = "modo_data_padrao"
CHAVE_PASTA_BACKUP = "pasta_backup"
CHAVE_DATA_ULTIMO_BACKUP_AUTOMATICO = "data_ultimo_backup_automatico"
CHAVE_PASTA_XML = "pasta_xml"
CHAVE_TEMA = "tema"


class ModoDataPadrao(str, enum.Enum):
    """Modos disponíveis para a data padrão sugerida em compras/pagamentos."""

    DIA_ATUAL = "dia_atual"
    DIA_ANTERIOR = "dia_anterior"


_MODO_PADRAO_DE_FABRICA = ModoDataPadrao.DIA_ANTERIOR


class ModoTema(str, enum.Enum):
    """Temas disponíveis para a aparência do sistema."""

    CLARO = "claro"
    ESCURO = "escuro"


_TEMA_PADRAO_DE_FABRICA = ModoTema.CLARO


@tratar_erros
def obter_modo_data_padrao() -> ModoDataPadrao:
    """Obtém o modo de data padrão configurado.

    Se a configuração ainda não tiver sido definida (ex.: instalação
    nova), retorna o padrão de fábrica: "dia anterior" — já que os
    lançamentos costumam ser feitos na manhã seguinte ao movimento.

    Returns:
        O :class:`ModoDataPadrao` atualmente configurado.
    """
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(session, CHAVE_MODO_DATA_PADRAO)
        if configuracao is None:
            return _MODO_PADRAO_DE_FABRICA
        try:
            return ModoDataPadrao(configuracao.valor)
        except ValueError:
            return _MODO_PADRAO_DE_FABRICA


@tratar_erros
def definir_modo_data_padrao(usuario_logado: UsuarioAutenticado, modo: ModoDataPadrao) -> None:
    """Define o modo de data padrão (configuração global).

    Args:
        usuario_logado: Usuário autenticado que está alterando a configuração.
        modo: Novo modo a ser aplicado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem alterar configurações do sistema.")

    with session_scope() as session:
        configuracao_repository.definir(session, CHAVE_MODO_DATA_PADRAO, modo.value)


@tratar_erros
def obter_tema() -> ModoTema:
    """Obtém o tema configurado (claro ou escuro).

    Se a configuração ainda não tiver sido definida (ex.: instalação
    nova), retorna o padrão de fábrica: tema claro.

    Returns:
        O :class:`ModoTema` atualmente configurado.
    """
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(session, CHAVE_TEMA)
        if configuracao is None:
            return _TEMA_PADRAO_DE_FABRICA
        try:
            return ModoTema(configuracao.valor)
        except ValueError:
            return _TEMA_PADRAO_DE_FABRICA


@tratar_erros
def definir_tema(usuario_logado: UsuarioAutenticado, tema: ModoTema) -> None:
    """Define o tema do sistema (configuração global).

    Como o tema é aplicado uma única vez, na inicialização (``app/main.py``),
    a alteração só tem efeito depois que o sistema for reiniciado.

    Args:
        usuario_logado: Usuário autenticado que está alterando a configuração.
        tema: Novo tema a ser aplicado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem alterar configurações do sistema.")

    with session_scope() as session:
        configuracao_repository.definir(session, CHAVE_TEMA, tema.value)


@tratar_erros
def obter_pasta_backup() -> str:
    """Obtém a pasta configurada para salvar os backups.

    Se ainda não tiver sido definida, retorna a pasta padrão (mesma usada
    pela etapa 1: ``settings.backup_dir``).

    Returns:
        Caminho (como texto) da pasta de backup.
    """
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(session, CHAVE_PASTA_BACKUP)
        if configuracao is None:
            return str(settings.backup_dir)
        return configuracao.valor


@tratar_erros
def definir_pasta_backup(usuario_logado: UsuarioAutenticado, pasta: str) -> None:
    """Define a pasta onde os backups serão salvos (configuração global).

    Args:
        usuario_logado: Usuário autenticado que está alterando a configuração.
        pasta: Novo caminho de pasta.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se ``pasta`` estiver em branco.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem alterar configurações do sistema.")
    if not pasta.strip():
        raise ValueError("Informe uma pasta válida.")

    with session_scope() as session:
        configuracao_repository.definir(session, CHAVE_PASTA_BACKUP, pasta.strip())


def obter_data_ultimo_backup_automatico() -> date | None:
    """Obtém a data em que o backup automático diário foi executado pela
    última vez (usado para decidir se ele precisa rodar de novo hoje).

    Não é decorada com ``tratar_erros`` propositalmente: é chamada pela
    verificação silenciosa em segundo plano (``app.services.backup_service``),
    que trata suas próprias exceções sem poluir o log de erros a cada
    verificação periódica.

    Returns:
        A data do último backup automático, ou None se nunca tiver ocorrido
        (ou se o valor salvo estiver corrompido).
    """
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(
            session, CHAVE_DATA_ULTIMO_BACKUP_AUTOMATICO
        )
        if configuracao is None:
            return None
        try:
            return date.fromisoformat(configuracao.valor)
        except ValueError:
            return None


def definir_data_ultimo_backup_automatico(data_backup: date) -> None:
    """Registra a data em que o backup automático diário foi executado.

    Assim como a função acima, não usa ``tratar_erros`` (chamada apenas
    internamente pelo fluxo de backup automático).

    Args:
        data_backup: Data em que o backup automático foi concluído.
    """
    with session_scope() as session:
        configuracao_repository.definir(
            session, CHAVE_DATA_ULTIMO_BACKUP_AUTOMATICO, data_backup.isoformat()
        )


@tratar_erros
def obter_pasta_xml() -> str:
    """Obtém a pasta configurada onde os XMLs de NF-e devem ser buscados.

    Se ainda não tiver sido definida, retorna a pasta de backup como
    referência de diretório base (apenas para dar um valor inicial
    razoável) — na prática, o Administrador deve configurar a pasta real
    dos XMLs na tela de Configurações antes de usar a importação.

    Returns:
        Caminho (como texto) da pasta de XMLs.
    """
    with session_scope() as session:
        configuracao = configuracao_repository.buscar_por_chave(session, CHAVE_PASTA_XML)
        if configuracao is None:
            return str(settings.base_dir)
        return configuracao.valor


@tratar_erros
def definir_pasta_xml(usuario_logado: UsuarioAutenticado, pasta: str) -> None:
    """Define a pasta onde os XMLs de NF-e serão buscados (configuração global).

    Args:
        usuario_logado: Usuário autenticado que está alterando a configuração.
        pasta: Novo caminho de pasta.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se ``pasta`` estiver em branco.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem alterar configurações do sistema.")
    if not pasta.strip():
        raise ValueError("Informe uma pasta válida.")

    with session_scope() as session:
        configuracao_repository.definir(session, CHAVE_PASTA_XML, pasta.strip())
