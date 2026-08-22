"""Ponto de entrada da aplicação.

Inicializa configuração, logging e conexão com o banco, garante que o
esquema do banco de dados esteja atualizado (cria as tabelas automaticamente
se o banco estiver vazio), exibe a tela de login e, em caso de sucesso,
abre a janela principal (PySide6).
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.config.logging_config import logger
from app.config.tema import obter_stylesheet
from app.database.connection import testar_conexao
from app.database.listeners import registrar_listeners
from app.database.migrar import aplicar_esquema_banco
from app.services import configuracao_service
from app.views.login_view import LoginView
from app.views.main_window import MainWindow


def main() -> int:
    """Inicializa e executa a aplicação gráfica.

    Returns:
        Código de saída do processo (0 = sucesso).
    """
    registrar_listeners()

    app = QApplication(sys.argv)

    if not testar_conexao():
        QMessageBox.critical(
            None,
            "Erro de conexão",
            "Não foi possível conectar ao banco de dados PostgreSQL.\n\n"
            "Verifique o arquivo .env (host, porta, usuário, senha) e se o "
            "servidor está acessível pela rede.\nDetalhes em app/logs/erros.log.",
        )
        return 1

    try:
        aplicar_esquema_banco()
    except Exception:
        logger.exception("Falha ao preparar automaticamente o esquema do banco de dados.")
        QMessageBox.critical(
            None,
            "Erro ao preparar o banco de dados",
            "Não foi possível criar/atualizar as tabelas do banco de dados automaticamente.\n\n"
            "Verifique se o usuário configurado no .env tem permissão para criar tabelas "
            "nesse banco.\nDetalhes em app/logs/erros.log.",
        )
        return 1

    logger.info("Aplicação iniciada; conexão e esquema do banco de dados verificados.")

    try:
        tema = configuracao_service.obter_tema()
    except Exception:
        logger.exception("Falha ao carregar a configuração de tema; usando o tema claro (padrão).")
        tema = configuracao_service.ModoTema.CLARO
    app.setStyleSheet(obter_stylesheet(tema))

    login_view = LoginView()
    if login_view.exec() != LoginView.DialogCode.Accepted or login_view.usuario_autenticado is None:
        return 0  # usuário fechou/cancelou a tela de login

    janela_principal = MainWindow(login_view.usuario_autenticado)
    janela_principal.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
