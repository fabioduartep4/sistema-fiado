"""Tratamento centralizado de erros.

Fornece o decorator ``tratar_erros``, usado principalmente na camada de
serviços (``app.services``). Qualquer exceção não tratada dentro da função
decorada é:

1. Registrada no arquivo de log (``app/logs/erros.log``), via
   ``app.config.logging_config``.
2. Persistida na tabela ``log_erros`` do banco, para consulta futura pela
   própria interface do sistema.
3. Relançada (re-raise), para que a camada de controller/view decida como
   apresentar o erro ao usuário (ex.: uma caixa de diálogo amigável).
"""

from __future__ import annotations

import functools
import traceback
from typing import Any, Callable, TypeVar

from app.config.logging_config import logger, obter_usuario_logado
from app.utils.exceptions import ErroDeNegocio

F = TypeVar("F", bound=Callable[..., Any])


def _persistir_log_erro(mensagem_erro: str, stacktrace: str) -> None:
    """Salva o erro na tabela ``log_erros``, isolando falhas de log."""
    # Import local para evitar dependência circular entre utils e models/database
    # (o error_handler pode ser usado por módulos que os próprios models importam).
    from app.database.connection import session_scope
    from app.models.log_erro import LogErro

    try:
        with session_scope() as session:
            session.add(
                LogErro(
                    usuario=obter_usuario_logado(),
                    erro=mensagem_erro[:500],
                    stacktrace=stacktrace,
                )
            )
    except Exception:
        # Se nem o log em banco funcionar (ex.: banco fora do ar), o arquivo
        # de log já registrou o erro original; aqui só evitamos mascarar o
        # erro real com uma falha secundária de logging.
        logger.exception("Falha ao persistir LogErro no banco de dados.")


def tratar_erros(func: F) -> F:
    """Decorator que captura, loga (arquivo + banco) e relança exceções.

    Uso::

        @tratar_erros
        def cadastrar_cliente(...):
            ...

    Args:
        func: Função a ser decorada (tipicamente um método de serviço).

    Returns:
        A função decorada, com o mesmo comportamento, porém logando
        qualquer exceção antes de relançá-la.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (ErroDeNegocio, ValueError):
            # Erro esperado de validação/regra de negócio: relança sem
            # registrar no log de erros (não é uma falha do sistema).
            raise
        except Exception as exc:
            stacktrace = traceback.format_exc()
            logger.exception("Erro em %s: %s", func.__qualname__, exc)
            _persistir_log_erro(f"{func.__qualname__}: {exc}", stacktrace)
            raise

    return wrapper  # type: ignore[return-value]
