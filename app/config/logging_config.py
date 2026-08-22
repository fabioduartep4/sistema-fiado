"""Configuração do logging de erros do sistema.

Requisito do projeto: todo erro deve ser registrado em arquivo contendo
data, hora, usuário, erro e stacktrace. Como o logging padrão do Python não
sabe "quem é o usuário logado", usamos uma ``ContextVar`` que é atualizada
pelo serviço de autenticação (``auth_service``) no momento do login, e um
``logging.Filter`` que injeta esse valor em todo registro de log.
"""

from __future__ import annotations

import logging
import logging.handlers
from contextvars import ContextVar
from pathlib import Path

from app.config.settings import settings

# Guarda o login do usuário atualmente autenticado nesta sessão do aplicativo.
# É atualizado por app.services.auth_service ao logar/deslogar.
_usuario_atual: ContextVar[str] = ContextVar("usuario_atual", default="não autenticado")


def definir_usuario_logado(login: str) -> None:
    """Define, para fins de log, qual usuário está autenticado no momento.

    Args:
        login: Login do usuário autenticado (ou "não autenticado" no logout).
    """
    _usuario_atual.set(login)


def obter_usuario_logado() -> str:
    """Retorna o login do usuário autenticado no momento (para fins de log).

    Returns:
        O login atual, ou "não autenticado" se ninguém estiver logado.
    """
    return _usuario_atual.get()


class _UsuarioAtualFilter(logging.Filter):
    """Injeta o login do usuário atual em cada registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.usuario = _usuario_atual.get()
        return True


def configurar_logging(log_dir: Path | None = None) -> logging.Logger:
    """Configura e retorna o logger principal da aplicação.

    Cria um arquivo de log rotativo (por tamanho) na pasta de logs, no
    formato: ``data hora | usuario | nivel | mensagem`` seguido do
    stacktrace quando aplicável (``exc_info=True``).

    Args:
        log_dir: Pasta onde o arquivo de log será criado. Se omitido, usa a
            pasta definida em ``settings.log_dir``.

    Returns:
        O logger configurado, pronto para uso via ``logging.getLogger("fiado")``.
    """
    log_dir = log_dir or settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("fiado")
    logger.setLevel(logging.INFO)

    # Evita adicionar handlers duplicados se a função for chamada mais de uma vez.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | usuario=%(usuario)s | %(levelname)s | %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "erros.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB por arquivo
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(_UsuarioAtualFilter())
    file_handler.setLevel(logging.INFO)

    logger.addHandler(file_handler)
    return logger


# Logger pronto para ser importado em qualquer módulo: `from app.config.logging_config import logger`
logger = configurar_logging()
