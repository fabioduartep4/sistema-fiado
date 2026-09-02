"""Tela de login (PySide6)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.config.logging_config import logger
from app.controllers.login_controller import LoginController
from app.services.auth_service import CredenciaisInvalidasError, UsuarioAutenticado
from app.utils.icons import icone


class LoginView(QDialog):
    """Janela de login exibida ao iniciar a aplicação.

    Attributes:
        usuario_autenticado: Preenchido com o usuário logado após um login
            bem-sucedido (``None`` até lá, ou se a janela for fechada sem
            logar).
    """

    def __init__(self) -> None:
        super().__init__()
        self._controller = LoginController()
        self.usuario_autenticado: UsuarioAutenticado | None = None

        self.setWindowTitle("Sistema de Fiado — Login")
        self.setMinimumWidth(360)
        self.setModal(True)

        self._campo_login = QLineEdit()
        self._campo_login.setPlaceholderText("Login")
        self._campo_login.setMinimumHeight(36)

        self._campo_senha = QLineEdit()
        self._campo_senha.setPlaceholderText("Senha")
        self._campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self._campo_senha.setMinimumHeight(36)

        self._label_erro = QLabel("")
        self._label_erro.setStyleSheet("color: #c0392b;")
        self._label_erro.setWordWrap(True)

        self._botao_entrar = QPushButton("Entrar")
        self._botao_entrar.setIcon(icone("LOGIN"))
        self._botao_entrar.setMinimumHeight(42)
        self._botao_entrar.setDefault(True)
        self._botao_entrar.setAutoDefault(True)
        self._botao_entrar.setProperty("importancia", "primaria")
        self._botao_entrar.clicked.connect(self._on_entrar_clicado)

        self._botao_cancelar = QPushButton("Cancelar")
        self._botao_cancelar.setIcon(icone("X"))
        self._botao_cancelar.setMinimumHeight(42)
        self._botao_cancelar.clicked.connect(self.reject)

        titulo = QLabel("Sistema de Gestão de Fiado")
        titulo.setProperty("papel", "titulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(self._botao_cancelar)
        layout_botoes.addWidget(self._botao_entrar)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addSpacing(12)
        layout.addWidget(QLabel("Login:"))
        layout.addWidget(self._campo_login)
        layout.addWidget(QLabel("Senha:"))
        layout.addWidget(self._campo_senha)
        layout.addWidget(self._label_erro)
        layout.addSpacing(8)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

        self._campo_login.setFocus()

    def _on_entrar_clicado(self) -> None:
        """Trata o clique no botão Entrar (ou Enter, via botão padrão)."""
        login = self._campo_login.text()
        senha = self._campo_senha.text()

        try:
            self.usuario_autenticado = self._controller.tentar_login(login, senha)
        except CredenciaisInvalidasError as exc:
            self._label_erro.setText(str(exc))
            self._campo_senha.clear()
            self._campo_senha.setFocus()
            return
        except Exception:
            logger.exception("Falha inesperada ao tentar login (login='%s').", login)
            self._label_erro.setText(
                "Não foi possível conectar ao banco de dados. Verifique a "
                "configuração de rede e tente novamente."
            )
            return

        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (nome exigido pelo Qt)
        """Permite confirmar o login com a tecla Enter em qualquer campo."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_entrar_clicado()
            return
        super().keyPressEvent(event)
