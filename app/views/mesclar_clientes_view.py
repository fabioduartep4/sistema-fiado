"""Tela de Mesclar Clientes Duplicados (PySide6).

Útil principalmente após importações de XML em lote (onde nomes iguais
que ainda não existiam no cadastro podem gerar clientes duplicados).
Agrupa os clientes ativos por nome principal (normalizado) e permite
escolher, por grupo, qual cadastro fica como principal — os demais têm
suas compras e pagamentos movidos para ele e são inativados (exclusão
lógica; nada é apagado).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.cliente_controller import ClienteController
from app.services.auth_service import UsuarioAutenticado
from app.services.cliente_service import GrupoDuplicados
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone


class _GrupoDuplicadosWidget(QGroupBox):
    """Um grupo de clientes com o mesmo nome, com opção de mesclar."""

    def __init__(
        self,
        grupo: GrupoDuplicados,
        controller: ClienteController,
        ao_mesclar_callback,
        parent: QWidget | None = None,
    ) -> None:
        primeiro_nome = grupo.clientes[0].nome_principal
        super().__init__(f"{primeiro_nome}  ({len(grupo.clientes)} cadastros)", parent)
        self._controller = controller
        self._ao_mesclar_callback = ao_mesclar_callback

        self._combo_principal = QComboBox()
        for cliente in grupo.clientes:
            self._combo_principal.addItem(
                f"{cliente.nome_principal} (código {cliente.id_visivel})", userData=cliente.id
            )

        self._checkboxes: dict[str, QCheckBox] = {}
        layout_checkboxes = QVBoxLayout()
        for cliente in grupo.clientes:
            checkbox = QCheckBox(f"{cliente.nome_principal} (código {cliente.id_visivel})")
            checkbox.setChecked(True)
            self._checkboxes[cliente.id] = checkbox
            layout_checkboxes.addWidget(checkbox)

        botao_mesclar = QPushButton("Mesclar Este Grupo")
        botao_mesclar.setIcon(icone("GIT_MERGE"))
        botao_mesclar.setMinimumHeight(36)
        botao_mesclar.clicked.connect(self._mesclar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Cliente principal (fica com as contas):"))
        layout.addWidget(self._combo_principal)
        layout.addWidget(QLabel("Marque quais devem ser mesclados nele:"))
        layout.addLayout(layout_checkboxes)
        layout.addWidget(botao_mesclar)
        self.setLayout(layout)

    def _mesclar(self) -> None:
        principal_id = self._combo_principal.currentData()
        duplicados_ids = [
            cliente_id
            for cliente_id, checkbox in self._checkboxes.items()
            if checkbox.isChecked() and cliente_id != principal_id
        ]

        if not duplicados_ids:
            QMessageBox.information(
                self, "Nada para mesclar", "Selecione ao menos um cliente diferente do principal."
            )
            return

        resposta = QMessageBox.question(
            self,
            "Confirmar mesclagem",
            f"Mesclar {len(duplicados_ids)} cadastro(s) em '{self._combo_principal.currentText()}'?\n\n"
            "As compras e pagamentos deles serão movidos para o cliente principal. Os "
            "duplicados ficarão inativos (nada é apagado).",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.mesclar(principal_id, duplicados_ids)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível mesclar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao mesclar clientes duplicados (principal=%s).", principal_id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível mesclar os clientes.")
            return

        QMessageBox.information(self, "Mesclado", "Grupo mesclado com sucesso.")
        self._ao_mesclar_callback()


class MesclarClientesDialog(QDialog):
    """Tela principal de detecção e mesclagem de clientes duplicados."""

    def __init__(self, usuario_logado: UsuarioAutenticado, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = ClienteController(usuario_logado)

        self.setWindowTitle("Mesclar Clientes Duplicados")
        self.setMinimumSize(560, 600)

        self._label_status = QLabel()
        self._label_status.setWordWrap(True)

        self._area_scroll = QScrollArea()
        self._area_scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._layout_grupos = QVBoxLayout(self._container)
        self._area_scroll.setWidget(self._container)

        botao_atualizar = QPushButton("Atualizar Lista")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.setMinimumHeight(38)
        botao_atualizar.clicked.connect(self._carregar)

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Grupos de clientes ativos com o mesmo nome principal:"))
        layout.addWidget(self._label_status)
        layout.addWidget(self._area_scroll)
        layout.addWidget(botao_atualizar)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)

        self._carregar()

    def _limpar_grupos(self) -> None:
        while self._layout_grupos.count():
            item = self._layout_grupos.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _carregar(self) -> None:
        self._limpar_grupos()

        try:
            grupos = self._controller.listar_grupos_duplicados()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao listar grupos de clientes duplicados.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível verificar clientes duplicados."
            )
            return

        if not grupos:
            self._label_status.setText("Nenhum cliente duplicado encontrado.")
            return

        self._label_status.setText(f"{len(grupos)} grupo(s) de possíveis duplicados encontrados.")
        for grupo in grupos:
            widget_grupo = _GrupoDuplicadosWidget(grupo, self._controller, self._carregar, self)
            self._layout_grupos.addWidget(widget_grupo)
        self._layout_grupos.addStretch()
