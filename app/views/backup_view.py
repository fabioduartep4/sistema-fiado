"""Tela de Backup (PySide6).

Visível apenas para Administrador (aba só é adicionada nesse caso — ver
``app.views.main_window``). A checagem de permissão também é reforçada na
camada de serviço (``app.services.backup_service``/``configuracao_service``).

O backup automático diário roda em segundo plano, sem UI própria — é
disparado pela janela principal (``app.views.main_window``). Esta tela
cobre apenas backup manual, restauração, a pasta de destino e a cópia na
nuvem (uma pasta sincronizada pelo Google Drive — ver
``app.services.nuvem_service``).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
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
from app.services.nuvem_service import QUANTIDADE_MANTIDA_NA_NUVEM
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone


class BackupView(QWidget):
    """Tela de gestão de backups (pasta, backup manual, restauração)."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = BackupController(usuario_logado)

        titulo = QLabel("Backup")
        titulo.setProperty("papel", "titulo")

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

        # -- Cópia na nuvem ----------------------------------------------------
        titulo_nuvem = QLabel("Cópia na nuvem (Google Drive)")
        titulo_nuvem.setProperty("papel", "subtitulo")

        explicacao_nuvem = QLabel(
            "Instale o \"Google Drive para computador\" nesta máquina e escolha abaixo uma "
            "pasta de dentro dele. Cada backup feito aqui é copiado para essa pasta, e o "
            "Google Drive envia para a nuvem. Ficam guardados os "
            f"{QUANTIDADE_MANTIDA_NA_NUVEM} mais recentes. Vale só para este computador."
        )
        explicacao_nuvem.setWordWrap(True)
        explicacao_nuvem.setProperty("papel", "secundario")

        self._campo_pasta_nuvem = QLineEdit()
        self._campo_pasta_nuvem.setReadOnly(True)
        self._campo_pasta_nuvem.setMinimumHeight(36)
        self._campo_pasta_nuvem.setPlaceholderText("Desativada neste computador")

        botao_escolher_nuvem = QPushButton("Escolher Pasta do Google Drive")
        botao_escolher_nuvem.setIcon(icone("CLOUD_UPLOAD"))
        botao_escolher_nuvem.setMinimumHeight(40)
        botao_escolher_nuvem.clicked.connect(self._escolher_pasta_nuvem)

        self._botao_desativar_nuvem = QPushButton("Desativar")
        self._botao_desativar_nuvem.setIcon(icone("CLOUD_OFF"))
        self._botao_desativar_nuvem.setMinimumHeight(40)
        self._botao_desativar_nuvem.clicked.connect(self._desativar_nuvem)

        layout_botoes_nuvem = QHBoxLayout()
        layout_botoes_nuvem.addWidget(botao_escolher_nuvem, 1)
        layout_botoes_nuvem.addWidget(self._botao_desativar_nuvem)

        self._label_status_nuvem = QLabel()
        self._label_status_nuvem.setWordWrap(True)

        aviso = QLabel(
            "O backup automático diário roda em segundo plano ao abrir o sistema. "
            "Requer que 'pg_dump' e 'psql' (ferramentas do PostgreSQL) estejam "
            "instalados e no PATH deste computador."
        )
        aviso.setWordWrap(True)
        aviso.setProperty("papel", "secundario")

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
        layout.addSpacing(16)
        layout.addWidget(titulo_nuvem)
        layout.addWidget(explicacao_nuvem)
        layout.addWidget(self._campo_pasta_nuvem)
        layout.addLayout(layout_botoes_nuvem)
        layout.addWidget(self._label_status_nuvem)
        layout.addStretch()
        self.setLayout(layout)

        self._carregar_pasta_atual()
        self._carregar_status_nuvem()

    # -- Cópia na nuvem --------------------------------------------------------

    def _carregar_status_nuvem(self) -> None:
        status = self._controller.status_nuvem()
        self._campo_pasta_nuvem.setText(status.pasta or "")
        self._botao_desativar_nuvem.setEnabled(status.pasta is not None)

        if status.pasta is None:
            texto, papel = "", "secundario"
        elif status.ultimo_erro:
            texto = f"A última cópia para a nuvem FALHOU: {status.ultimo_erro}"
            if status.ultima_copia:
                texto += f" (a última que deu certo foi em {status.ultima_copia:%d/%m/%Y às %H:%M})"
            papel = "perigo"
        elif status.ultima_copia:
            texto, papel = f"Última cópia para a nuvem: {status.ultima_copia:%d/%m/%Y às %H:%M}", "sucesso"
        else:
            texto = "Ainda nenhum backup foi copiado. O próximo backup já vai para a nuvem."
            papel = "secundario"
        self._label_status_nuvem.setText(texto)
        self._label_status_nuvem.setProperty("papel", papel)
        # A cor vem do "papel": o estilo precisa ser reaplicado quando ele muda.
        self._label_status_nuvem.style().unpolish(self._label_status_nuvem)
        self._label_status_nuvem.style().polish(self._label_status_nuvem)

    def _salvar_pasta_nuvem(self, pasta: str | None) -> None:
        try:
            self._controller.definir_pasta_nuvem(pasta)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível salvar a pasta da nuvem", str(exc))
        except Exception:
            logger.exception("Falha inesperada ao salvar a pasta da nuvem.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível salvar a pasta da nuvem.")
        self._carregar_status_nuvem()

    def _escolher_pasta_nuvem(self) -> None:
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher a pasta do Google Drive", self._campo_pasta_nuvem.text()
        )
        if pasta:
            self._salvar_pasta_nuvem(pasta)

    def _desativar_nuvem(self) -> None:
        self._salvar_pasta_nuvem(None)

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

        self._carregar_status_nuvem()
        status = self._controller.status_nuvem()
        mensagem = f"Backup salvo em:\n{resultado.caminho_arquivo}"
        if status.pasta and status.ultimo_erro:
            mensagem += f"\n\nATENÇÃO: a cópia para a nuvem falhou.\n{status.ultimo_erro}"
        elif status.pasta:
            mensagem += f"\n\nCopiado também para a pasta da nuvem:\n{status.pasta}"
        QMessageBox.information(self, "Backup concluído", mensagem)

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
