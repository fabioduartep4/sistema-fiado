"""Serviço de backup e restauração.

Usa as ferramentas de linha de comando do PostgreSQL (``pg_dump`` para
gerar o backup, ``psql`` para restaurar), chamadas via ``subprocess``.
Essas ferramentas precisam estar instaladas e no PATH do computador que
executa o backup (fazem parte da instalação cliente padrão do PostgreSQL).

O backup automático diário é verificado ao abrir o sistema e
periodicamente enquanto ele estiver aberto (ver ``app.views.main_window``),
já que uma aplicação desktop não tem um serviço/agendador próprio rodando
em segundo plano o tempo todo.

O dump é gerado com ``--clean --if-exists``, ou seja, o arquivo de backup
já contém os comandos para apagar os dados/objetos existentes antes de
recriá-los. Além disso, antes de aplicar qualquer restauração, o schema
``public`` inteiro é apagado e recriado vazio (``_limpar_schema_public``)
— isso garante um estado 100% limpo mesmo que uma restauração anterior
tenha ficado pela metade (evita erros do tipo "tipo/tabela já existe"
causados por sobras de tentativas anteriores). A restauração
(``psql -v ON_ERROR_STOP=1``) interrompe e reporta qualquer erro real,
em vez de ignorá-lo silenciosamente.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from app.config.settings import settings
from app.services import configuracao_service
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import PermissaoNegadaError
from app.utils.error_handler import tratar_erros
from app.utils.exceptions import ErroDeNegocio


class FerramentaBackupNaoEncontradaError(ErroDeNegocio):
    """Lançada quando ``pg_dump``/``psql`` não estão instalados ou no PATH."""


class BackupError(ErroDeNegocio):
    """Lançada quando ``pg_dump``/``psql`` retornam um erro de execução."""


@dataclass(frozen=True)
class BackupResultado:
    """Dados de um backup recém-criado, para exibição."""

    caminho_arquivo: str
    data_hora: datetime


def _montar_ambiente_com_senha() -> dict[str, str]:
    """Monta as variáveis de ambiente para pg_dump/psql, incluindo a senha."""
    ambiente = os.environ.copy()
    ambiente["PGPASSWORD"] = settings.database.password
    return ambiente


def _executar_pg_dump(caminho_sql: Path) -> None:
    comando = [
        "pg_dump",
        "-h", settings.database.host,
        "-p", str(settings.database.port),
        "-U", settings.database.user,
        "-F", "p",
        "--clean",
        "--if-exists",
        "-f", str(caminho_sql),
        settings.database.name,
    ]
    try:
        resultado = subprocess.run(
            comando, env=_montar_ambiente_com_senha(), capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise FerramentaBackupNaoEncontradaError(
            "Comando 'pg_dump' não encontrado. Verifique se as ferramentas de linha de "
            "comando do PostgreSQL estão instaladas e no PATH deste computador."
        ) from exc

    if resultado.returncode != 0:
        raise BackupError(f"Falha ao gerar o backup: {resultado.stderr.strip()}")


def _limpar_schema_public() -> None:
    """Remove todos os objetos do schema padrão antes de restaurar.

    Garante um estado 100% limpo para a restauração, independente do que
    possa ter sobrado de uma tentativa de restauração anterior mal-sucedida
    (tabelas, tipos ou sequências órfãos) — evita erros como "tipo já
    existe" causados por drops individuais que não cobriram tudo.
    """
    comando = [
        "psql",
        "-h", settings.database.host,
        "-p", str(settings.database.port),
        "-U", settings.database.user,
        "-v", "ON_ERROR_STOP=1",
        "-c", "DROP SCHEMA public CASCADE; CREATE SCHEMA public;",
        settings.database.name,
    ]
    try:
        resultado = subprocess.run(
            comando, env=_montar_ambiente_com_senha(), capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise FerramentaBackupNaoEncontradaError(
            "Comando 'psql' não encontrado. Verifique se as ferramentas de linha de comando "
            "do PostgreSQL estão instaladas e no PATH deste computador."
        ) from exc

    if resultado.returncode != 0:
        raise BackupError(f"Falha ao limpar o banco antes de restaurar: {resultado.stderr.strip()}")


def _executar_psql(caminho_sql: Path) -> None:
    _limpar_schema_public()

    comando = [
        "psql",
        "-h", settings.database.host,
        "-p", str(settings.database.port),
        "-U", settings.database.user,
        "-v", "ON_ERROR_STOP=1",
        "-f", str(caminho_sql),
        settings.database.name,
    ]
    try:
        resultado = subprocess.run(
            comando, env=_montar_ambiente_com_senha(), capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise FerramentaBackupNaoEncontradaError(
            "Comando 'psql' não encontrado. Verifique se as ferramentas de linha de comando "
            "do PostgreSQL estão instaladas e no PATH deste computador."
        ) from exc

    if resultado.returncode != 0:
        raise BackupError(f"Falha ao restaurar o backup: {resultado.stderr.strip()}")


def _compactar_em_zip(caminho_sql: Path, caminho_zip: Path) -> None:
    with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as arquivo_zip:
        arquivo_zip.write(caminho_sql, arcname=caminho_sql.name)
    caminho_sql.unlink()


def _executar_backup(pasta_destino: Optional[str] = None) -> BackupResultado:
    """Executa o dump do banco e o compacta em ZIP na pasta informada."""
    pasta = Path(pasta_destino) if pasta_destino else Path(configuracao_service.obter_pasta_backup())
    pasta.mkdir(parents=True, exist_ok=True)

    agora = datetime.now()
    nome_base = f"backup_fiado_{agora.strftime('%Y%m%d_%H%M%S')}"
    caminho_sql = pasta / f"{nome_base}.sql"
    caminho_zip = pasta / f"{nome_base}.zip"

    _executar_pg_dump(caminho_sql)
    _compactar_em_zip(caminho_sql, caminho_zip)

    return BackupResultado(caminho_arquivo=str(caminho_zip), data_hora=agora)


@tratar_erros
def fazer_backup_manual(
    usuario_logado: UsuarioAutenticado, pasta_destino: Optional[str] = None
) -> BackupResultado:
    """Executa um backup manual, compactado em ZIP.

    Args:
        usuario_logado: Usuário autenticado que está solicitando o backup.
        pasta_destino: Pasta onde salvar o backup. Se omitida, usa a pasta
            configurada (``configuracao_service.obter_pasta_backup``).

    Returns:
        Um :class:`BackupResultado` com o caminho do arquivo gerado.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        FerramentaBackupNaoEncontradaError: Se ``pg_dump`` não for encontrado.
        BackupError: Se ``pg_dump`` falhar.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem realizar backup manual.")

    return _executar_backup(pasta_destino)


@tratar_erros
def restaurar_backup(usuario_logado: UsuarioAutenticado, caminho_arquivo_zip: str) -> None:
    """Restaura o banco de dados a partir de um arquivo de backup ZIP.

    Antes de aplicar o backup, todo o conteúdo atual do banco é apagado
    (schema ``public`` inteiro, recriado vazio) — a restauração sempre
    resulta num banco idêntico ao do backup, nunca numa mescla com o que
    havia antes.

    Args:
        usuario_logado: Usuário autenticado que está solicitando a restauração.
        caminho_arquivo_zip: Caminho do arquivo ``.zip`` gerado por um
            backup (manual ou automático) deste sistema.

    Raises:
        PermissaoNegadaError: Se ``usuario_logado`` não for Administrador.
        ValueError: Se o arquivo não existir ou não contiver um backup válido.
        FerramentaBackupNaoEncontradaError: Se ``psql`` não for encontrado.
        BackupError: Se a limpeza do banco ou a restauração falharem.
    """
    if not usuario_logado.eh_administrador:
        raise PermissaoNegadaError("Apenas administradores podem restaurar backups.")

    caminho_zip = Path(caminho_arquivo_zip)
    if not caminho_zip.exists():
        raise ValueError("Arquivo de backup não encontrado.")

    pasta_temporaria = caminho_zip.parent / f"_restauracao_temp_{uuid.uuid4().hex}"
    pasta_temporaria.mkdir()
    try:
        with zipfile.ZipFile(caminho_zip, "r") as arquivo_zip:
            arquivo_zip.extractall(pasta_temporaria)

        arquivos_sql = list(pasta_temporaria.glob("*.sql"))
        if not arquivos_sql:
            raise ValueError("O arquivo ZIP não contém um backup válido (nenhum .sql encontrado).")

        _executar_psql(arquivos_sql[0])
    finally:
        shutil.rmtree(pasta_temporaria, ignore_errors=True)


def verificar_e_executar_backup_automatico_se_necessario() -> Optional[BackupResultado]:
    """Executa o backup automático diário, se ainda não tiver sido feito hoje.

    Chamada silenciosamente ao abrir o sistema e periodicamente enquanto
    ele estiver aberto (ver ``app.views.main_window``). Propositalmente
    **não** é decorada com ``tratar_erros``: o chamador (``main_window``)
    trata qualquer falha em segundo plano, sem interromper nem alarmar o
    usuário comum — só registra no log de arquivo.

    Returns:
        O :class:`BackupResultado`, se um backup foi executado agora; None
        se o backup de hoje já tinha sido feito anteriormente.
    """
    ultima_data = configuracao_service.obter_data_ultimo_backup_automatico()
    hoje = date.today()

    if ultima_data == hoje:
        return None

    resultado = _executar_backup(pasta_destino=None)
    configuracao_service.definir_data_ultimo_backup_automatico(hoje)
    return resultado
