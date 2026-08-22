"""Tela de gestão de usuários (PySide6).

Visível apenas para usuários com perfil Administrador (a aba correspondente
só é adicionada à janela principal nesse caso — ver ``app.views.main_window``).
A checagem de permissão também é reforçada na camada de serviço
(``app.services.usuario_service``).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.usuario_controller import UsuarioController
from app.models.usuario import PerfilUsuario
from app.services.auth_service import UsuarioAutenticado
from app.services.usuario_service import UsuarioResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone

_ROTULOS_PERFIL = {
    PerfilUsuario.ADMINISTRADOR: "Administrador",
    PerfilUsuario.FUNCIONARIO: "Funcionário",
}


class _CampoPerfil(QComboBox):
    """ComboBox que exibe os perfis em português e devolve o enum correspondente."""

    def __init__(self) -> None:
        super().__init__()
        for perfil, rotulo in _ROTULOS_PERFIL.items():
            self.addItem(rotulo, userData=perfil)

    def perfil_selecionado(self) -> PerfilUsuario:
        return self.currentData()

    def selecionar_perfil(self, perfil: PerfilUsuario) -> None:
        indice = self.findData(perfil)
        if indice >= 0:
            self.setCurrentIndex(indice)


class NovoUsuarioDialog(QDialog):
    """Formulário de criação de um novo usuário."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Novo Usuário")
        self.setMinimumWidth(360)

        self.campo_nome = QLineEdit()
        self.campo_login = QLineEdit()
        self.campo_senha = QLineEdit()
        self.campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_confirmar_senha = QLineEdit()
        self.campo_confirmar_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_perfil = _CampoPerfil()

        for campo in (self.campo_nome, self.campo_login, self.campo_senha, self.campo_confirmar_senha):
            campo.setMinimumHeight(34)

        botao_salvar = QPushButton("Salvar")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(40)
        botao_salvar.setDefault(True)
        botao_salvar.clicked.connect(self._validar_e_aceitar)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setIcon(icone("X"))
        botao_cancelar.setMinimumHeight(40)
        botao_cancelar.clicked.connect(self.reject)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_cancelar)
        layout_botoes.addWidget(botao_salvar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Nome completo:"))
        layout.addWidget(self.campo_nome)
        layout.addWidget(QLabel("Login:"))
        layout.addWidget(self.campo_login)
        layout.addWidget(QLabel("Senha:"))
        layout.addWidget(self.campo_senha)
        layout.addWidget(QLabel("Confirmar senha:"))
        layout.addWidget(self.campo_confirmar_senha)
        layout.addWidget(QLabel("Perfil:"))
        layout.addWidget(self.campo_perfil)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

    def _validar_e_aceitar(self) -> None:
        if self.campo_senha.text() != self.campo_confirmar_senha.text():
            QMessageBox.warning(self, "Senhas diferentes", "As senhas informadas não conferem.")
            return
        self.accept()

    def dados(self) -> tuple[str, str, str, PerfilUsuario]:
        """Retorna (nome, login, senha, perfil) preenchidos no formulário."""
        return (
            self.campo_nome.text().strip(),
            self.campo_login.text().strip(),
            self.campo_senha.text(),
            self.campo_perfil.perfil_selecionado(),
        )


class EditarUsuarioDialog(QDialog):
    """Formulário de edição de nome/perfil de um usuário existente."""

    def __init__(self, usuario: UsuarioResumo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Editar Usuário — {usuario.login}")
        self.setMinimumWidth(360)

        self.campo_nome = QLineEdit(usuario.nome)
        self.campo_nome.setMinimumHeight(34)
        self.campo_perfil = _CampoPerfil()
        self.campo_perfil.selecionar_perfil(usuario.perfil)

        botao_salvar = QPushButton("Salvar")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(40)
        botao_salvar.setDefault(True)
        botao_salvar.clicked.connect(self.accept)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setIcon(icone("X"))
        botao_cancelar.setMinimumHeight(40)
        botao_cancelar.clicked.connect(self.reject)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_cancelar)
        layout_botoes.addWidget(botao_salvar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Login: {usuario.login} (não editável)"))
        layout.addWidget(QLabel("Nome completo:"))
        layout.addWidget(self.campo_nome)
        layout.addWidget(QLabel("Perfil:"))
        layout.addWidget(self.campo_perfil)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

    def dados(self) -> tuple[str, PerfilUsuario]:
        """Retorna (nome, perfil) preenchidos no formulário."""
        return self.campo_nome.text().strip(), self.campo_perfil.perfil_selecionado()


class RedefinirSenhaDialog(QDialog):
    """Formulário de redefinição de senha de um usuário."""

    def __init__(self, usuario: UsuarioResumo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Redefinir Senha — {usuario.login}")
        self.setMinimumWidth(320)

        self.campo_senha = QLineEdit()
        self.campo_senha.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_confirmar_senha = QLineEdit()
        self.campo_confirmar_senha.setEchoMode(QLineEdit.EchoMode.Password)
        for campo in (self.campo_senha, self.campo_confirmar_senha):
            campo.setMinimumHeight(34)

        botao_salvar = QPushButton("Salvar")
        botao_salvar.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar.setMinimumHeight(40)
        botao_salvar.setDefault(True)
        botao_salvar.clicked.connect(self._validar_e_aceitar)

        botao_cancelar = QPushButton("Cancelar")
        botao_cancelar.setIcon(icone("X"))
        botao_cancelar.setMinimumHeight(40)
        botao_cancelar.clicked.connect(self.reject)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_cancelar)
        layout_botoes.addWidget(botao_salvar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Nova senha:"))
        layout.addWidget(self.campo_senha)
        layout.addWidget(QLabel("Confirmar nova senha:"))
        layout.addWidget(self.campo_confirmar_senha)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

    def _validar_e_aceitar(self) -> None:
        if self.campo_senha.text() != self.campo_confirmar_senha.text():
            QMessageBox.warning(self, "Senhas diferentes", "As senhas informadas não conferem.")
            return
        self.accept()

    def nova_senha(self) -> str:
        """Retorna a nova senha preenchida no formulário."""
        return self.campo_senha.text()


class UsuarioView(QWidget):
    """Tela principal de gestão de usuários: lista + ações."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = UsuarioController(usuario_logado)
        self._usuarios_carregados: list[UsuarioResumo] = []

        self._tabela = QTableWidget(0, 4)
        self._tabela.setHorizontalHeaderLabels(["Nome", "Login", "Perfil", "Status"])
        self._tabela.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._tabela.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tabela.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        botao_novo = QPushButton("Novo Usuário")
        botao_novo.setIcon(icone("USER_PLUS"))
        botao_editar = QPushButton("Editar")
        botao_editar.setIcon(icone("EDIT"))
        botao_redefinir_senha = QPushButton("Redefinir Senha")
        botao_redefinir_senha.setIcon(icone("KEY"))
        self._botao_ativar_inativar = QPushButton("Inativar")
        self._botao_ativar_inativar.setIcon(icone("BAN"))
        botao_atualizar = QPushButton("Atualizar Lista")
        botao_atualizar.setIcon(icone("REFRESH"))

        for botao in (
            botao_novo,
            botao_editar,
            botao_redefinir_senha,
            self._botao_ativar_inativar,
            botao_atualizar,
        ):
            botao.setMinimumHeight(38)

        botao_novo.clicked.connect(self._abrir_novo_usuario)
        botao_editar.clicked.connect(self._abrir_editar_usuario)
        botao_redefinir_senha.clicked.connect(self._abrir_redefinir_senha)
        self._botao_ativar_inativar.clicked.connect(self._alternar_ativo)
        botao_atualizar.clicked.connect(self._carregar_usuarios)

        layout_botoes = QHBoxLayout()
        layout_botoes.addWidget(botao_novo)
        layout_botoes.addWidget(botao_editar)
        layout_botoes.addWidget(botao_redefinir_senha)
        layout_botoes.addWidget(self._botao_ativar_inativar)
        layout_botoes.addStretch()
        layout_botoes.addWidget(botao_atualizar)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Usuários do sistema"))
        layout.addWidget(self._tabela)
        layout.addLayout(layout_botoes)
        self.setLayout(layout)

        self._tabela.itemSelectionChanged.connect(self._atualizar_texto_botao_ativo)
        self._carregar_usuarios()

    # -- Carregamento e exibição -------------------------------------------------

    def _carregar_usuarios(self) -> None:
        try:
            self._usuarios_carregados = self._controller.listar(incluir_inativos=True)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível listar usuários", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de usuários.")
            QMessageBox.critical(
                self,
                "Erro inesperado",
                "Não foi possível carregar a lista de usuários. Verifique a conexão "
                "com o banco de dados.",
            )
            return

        self._tabela.setRowCount(len(self._usuarios_carregados))
        for linha, usuario in enumerate(self._usuarios_carregados):
            self._tabela.setItem(linha, 0, QTableWidgetItem(usuario.nome))
            self._tabela.setItem(linha, 1, QTableWidgetItem(usuario.login))
            self._tabela.setItem(linha, 2, QTableWidgetItem(_ROTULOS_PERFIL[usuario.perfil]))
            item_status = QTableWidgetItem("Ativo" if usuario.ativo else "Inativo")
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tabela.setItem(linha, 3, item_status)
        self._atualizar_texto_botao_ativo()

    def _usuario_selecionado(self) -> UsuarioResumo | None:
        linha = self._tabela.currentRow()
        if linha < 0 or linha >= len(self._usuarios_carregados):
            return None
        return self._usuarios_carregados[linha]

    def _atualizar_texto_botao_ativo(self) -> None:
        usuario = self._usuario_selecionado()
        if usuario is None:
            self._botao_ativar_inativar.setText("Inativar/Reativar")
            return
        self._botao_ativar_inativar.setText("Reativar" if not usuario.ativo else "Inativar")

    # -- Ações ---------------------------------------------------------------

    def _abrir_novo_usuario(self) -> None:
        dialogo = NovoUsuarioDialog(self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        nome, login, senha, perfil = dialogo.dados()
        try:
            self._controller.criar(nome, login, senha, perfil)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível criar o usuário", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao criar usuário.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível criar o usuário.")
            return

        self._carregar_usuarios()

    def _abrir_editar_usuario(self) -> None:
        usuario = self._usuario_selecionado()
        if usuario is None:
            QMessageBox.information(self, "Selecione um usuário", "Selecione um usuário na lista.")
            return

        dialogo = EditarUsuarioDialog(usuario, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        nome, perfil = dialogo.dados()
        try:
            self._controller.editar(usuario.id, nome, perfil)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível editar o usuário", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao editar usuário %s.", usuario.id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível editar o usuário.")
            return

        self._carregar_usuarios()

    def _abrir_redefinir_senha(self) -> None:
        usuario = self._usuario_selecionado()
        if usuario is None:
            QMessageBox.information(self, "Selecione um usuário", "Selecione um usuário na lista.")
            return

        dialogo = RedefinirSenhaDialog(usuario, self)
        if dialogo.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self._controller.redefinir_senha(usuario.id, dialogo.nova_senha())
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível redefinir a senha", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao redefinir senha do usuário %s.", usuario.id)
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível redefinir a senha.")
            return

        QMessageBox.information(self, "Senha redefinida", "Senha redefinida com sucesso.")

    def _alternar_ativo(self) -> None:
        usuario = self._usuario_selecionado()
        if usuario is None:
            QMessageBox.information(self, "Selecione um usuário", "Selecione um usuário na lista.")
            return

        novo_status = not usuario.ativo
        acao_texto = "reativar" if novo_status else "inativar"
        resposta = QMessageBox.question(
            self,
            f"Confirmar {acao_texto}",
            f"Deseja realmente {acao_texto} o usuário '{usuario.login}'?",
        )
        if resposta != QMessageBox.StandardButton.Yes:
            return

        try:
            self._controller.definir_ativo(usuario.id, novo_status)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, f"Não foi possível {acao_texto}", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao %s usuário %s.", acao_texto, usuario.id)
            QMessageBox.critical(self, "Erro inesperado", f"Não foi possível {acao_texto} o usuário.")
            return

        self._carregar_usuarios()
