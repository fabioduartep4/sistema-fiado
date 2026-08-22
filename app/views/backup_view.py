"""Tela de Backup (PySide6).

Visível apenas para Administrador (aba só é adicionada nesse caso — ver
``app.views.main_window``). A checagem de permissão também é reforçada na
camada de serviço (``app.services.backup_service``/``configuracao_service``).

O backup automático diário roda em segundo plano, sem UI própria — é
disparado pela janela principal (``app.views.main_window``). Esta tela
cobre apenas backup manual, restauração e a pasta de destino.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.backup_controller import BackupController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone


class BackupView(QWidget):
    """Tela de gestão de backups (pasta, backup manual, restauração)."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = BackupController(usuario_logado)

        titulo = QLabel("Backup")
        titulo.setStyleSheet("font-size: 16px; font-weight: bold;")

        self._campo_pasta = QLineEdit()
        self._campo_pasta.setReadOnly(True)
        self._campo_pasta.setMinimumHeight(36)

        botao_escolher_pasta = QPushButton("Escolher Pasta de Backup")
        botao_escolher_pasta.setIcon(icone("FOLDER"))
        botao_escolher_pasta.setMinimumHeight(40)
        botao_escolher_pasta.clicked.connect(self._escolher_pasta)

        botao_backup_manual = QPushButton("Fazer Backup Agora")
        botao_backup_manual.setIcon(icone("DOWNLOAD"))
        botao_backup_manual.setMinimumHeight(44)
        botao_backup_manual.clicked.connect(self._fazer_backup_manual)

        botao_restaurar = QPushButton("Restaurar Backup")
        botao_restaurar.setIcon(icone("UPLOAD"))
        botao_restaurar.setMinimumHeight(44)
        botao_restaurar.clicked.connect(self._restaurar_backup)

        aviso = QLabel(
            "O backup automático diário roda em segundo plano ao abrir o sistema. "
            "Requer que 'pg_dump' e 'psql' (ferramentas do PostgreSQL) estejam "
            "instalados e no PATH deste computador."
        )
        aviso.setWordWrap(True)
        aviso.setStyleSheet("color: #666;")

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(QLabel("Pasta de backup:"))
        layout.addWidget(self._campo_pasta)
        layout.addWidget(botao_escolher_pasta)
        layout.addSpacing(12)
        layout.addWidget(botao_backup_manual)
        layout.addWidget(botao_restaurar)
        layout.addSpacing(12)
        layout.addWidget(aviso)
        layout.addStretch()
        self.setLayout(layout)

        self._carregar_pasta_atual()

    def _carregar_pasta_atual(self) -> None:
        try:
            self._campo_pasta.setText(self._controller.obter_pasta_backup())
        except Exception:
            logger.exception("Falha ao carregar a pasta de backup configurada.")
            self._campo_pasta.setText("")

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Escolher Pasta de Backup", self._campo_pasta.text())
        if not pasta:
            return

        try:
            self._controller.definir_pasta_backup(pasta)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível salvar a pasta", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao salvar a pasta de backup.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível salvar a pasta de backup.")
            return

        self._campo_pasta.setText(pasta)

    def _fazer_backup_manual(self) -> None:
        try:
            resultado = self._controller.fazer_backup_manual()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível fazer o backup", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao fazer backup manual.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível fazer o backup.")
            return

        QMessageBox.information(
            self, "Backup concluído", f"Backup salvo em:\n{resultado.caminho_arquivo}"
        )

    def _restaurar_backup(self) -> None:
        caminho_arquivo, _ = QFileDialog.getOpenFileName(
            self, "Selecionar Arquivo de Backup", self._campo_pasta.text(), "Backups (*.zip)"
        )
        if not caminho_arquivo:
            return

        resposta = QMessageBox.question(
            self,
            "Confirmar restauração",
            "Restaurar um backup substitui os dados atuais do banco pelos dados do "
            "arquivo selecionado. Esta ação não pode ser desfeita.\n\n"
            "Deseja realmente continuar?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.restaurar_backup(caminho_arquivo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível restaurar o backup", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao restaurar backup.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível restaurar o backup.")
            return

        QMessageBox.information(
            self,
            "Backup restaurado",
            "Backup restaurado com sucesso. Recomenda-se reiniciar o sistema.",
        )
