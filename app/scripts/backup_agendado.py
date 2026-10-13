"""Backup diário sem abrir o sistema — para o agendador de tarefas do Windows.

Pensado para o computador onde o banco de dados fica (o "servidor"), que
passa o dia ligado mas onde ninguém abre o Sistema de Fiado. O Windows
roda este programa sozinho, todo dia; ele faz o backup do banco na pasta
de backup configurada e, se houver uma pasta do Google Drive configurada
neste computador, copia para ela.

Uso (rodando a partir do código-fonte):
    python -m app.scripts.backup_agendado          # no máximo um backup por dia
    python -m app.scripts.backup_agendado --agora  # faz mesmo que já tenha feito hoje

Também é empacotado como ``BackupAgendado.exe`` (ver ``fiado.spec``); o
agendamento é criado por ``instalar_backup_agendado.bat``.

Não tem janela nem pergunta nada: o resultado vai para o arquivo de log
(``app/logs``) e para o código de saída — 0 se deu certo (ou se o backup
de hoje já estava feito), 1 se falhou —, que o Agendador de Tarefas mostra
em "Resultado da última execução".
"""

from __future__ import annotations

import sys

from app.config.logging_config import logger


def main(argumentos: list[str] | None = None) -> int:
    """Executa o backup agendado e devolve o código de saída do processo."""
    argumentos = sys.argv[1:] if argumentos is None else argumentos
    forcar = "--agora" in argumentos

    try:
        # Importados aqui dentro: se a configuração (.env) estiver errada, o
        # erro cai no "except" e fica no log, em vez de o programa morrer mudo.
        from app.services import backup_service, nuvem_service

        resultado = backup_service.fazer_backup_agendado(forcar=forcar)
        if resultado is None:
            logger.info("Backup agendado: o backup de hoje já tinha sido feito.")
            return 0

        logger.info("Backup agendado concluído: %s", resultado.caminho_arquivo)
        status = nuvem_service.obter_status()
        if status.pasta and status.ultimo_erro:
            logger.error("Backup agendado: a cópia para a nuvem falhou (%s).", status.ultimo_erro)
        elif status.pasta:
            logger.info("Backup agendado: copiado para a pasta da nuvem (%s).", status.pasta)
        return 0
    except Exception:
        logger.exception("Backup agendado FALHOU.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
