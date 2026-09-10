"""Tela de Configurações (PySide6).

Visível apenas para Administrador. Permite editar o modo de data padrão
(configuração global usada em Adicionar Compra e Receber Conta) e a pasta
de XMLs de NF-e (usada na importação de vendas a prazo), além de oferecer
um botão para disparar a importação manualmente. A pasta de backup já é
editável na própria aba "Backup" (etapa 7).

Conexão com o banco é exibida apenas de forma informativa — alterá-la
exige reiniciar o sistema (é lida do arquivo ``.env`` na inicialização),
então não é editável por aqui. O tema (claro/escuro) já é editável, mas
também só tem efeito depois de reiniciar o sistema (é aplicado uma única
vez, na inicialização, em ``app/main.py``).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.config.settings import settings
from app.controllers.configuracao_controller import ConfiguracaoController
from app.controllers.xml_importacao_controller import XmlImportacaoController
from app.services.auth_service import UsuarioAutenticado
from app.services.configuracao_service import ModoDataPadrao, ModoTema
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.views.mesclar_clientes_view import MesclarClientesDialog
from app.views.xml_importacao_view import ImportarXmlDialog

_ROTULOS_MODO_DATA = {
    ModoDataPadrao.DIA_ATUAL: "Dia atual",
    ModoDataPadrao.DIA_ANTERIOR: "Dia anterior",
}

_ROTULOS_TEMA = {
    ModoTema.CLARO: "Claro",
    ModoTema.ESCURO: "Escuro",
}


class ConfiguracoesView(QWidget):
    """Tela de configurações globais do sistema."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = ConfiguracaoController(usuario_logado)
        self._xml_controller = XmlImportacaoController(usuario_logado)
        self._usuario_logado = usuario_logado

        titulo = QLabel("Configurações")
        titulo.setProperty("papel", "titulo")

        info_conexao = QLabel(
            f"Servidor: {settings.database.host}:{settings.database.port}  •  "
            f"Banco: {settings.database.name}\n"
            "(Editável apenas no arquivo .env deste computador — requer reiniciar o sistema.)"
        )
        info_conexao.setWordWrap(True)
        info_conexao.setProperty("papel", "secundario")

        self._campo_modo_data = QComboBox()
        for modo, rotulo in _ROTULOS_MODO_DATA.items():
            self._campo_modo_data.addItem(rotulo, userData=modo)
        self._campo_modo_data.setMinimumHeight(36)

        botao_salvar_modo_data = QPushButton("Salvar Modo de Data")
        botao_salvar_modo_data.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar_modo_data.setMinimumHeight(40)
        botao_salvar_modo_data.clicked.connect(self._salvar_modo_data)

        self._campo_tema = QComboBox()
        for tema, rotulo in _ROTULOS_TEMA.items():
            self._campo_tema.addItem(rotulo, userData=tema)
        self._campo_tema.setMinimumHeight(36)

        botao_salvar_tema = QPushButton("Salvar Tema")
        botao_salvar_tema.setIcon(icone("DEVICE_FLOPPY"))
        botao_salvar_tema.setMinimumHeight(40)
        botao_salvar_tema.clicked.connect(self._salvar_tema)

        self._campo_pasta_xml = QLineEdit()
        self._campo_pasta_xml.setReadOnly(True)
        self._campo_pasta_xml.setMinimumHeight(36)

        botao_escolher_pasta_xml = QPushButton("Escolher Pasta de XMLs")
        botao_escolher_pasta_xml.setIcon(icone("FOLDER"))
        botao_escolher_pasta_xml.setMinimumHeight(40)
        botao_escolher_pasta_xml.clicked.connect(self._escolher_pasta_xml)

        botao_importar_xml_agora = QPushButton("Importar XMLs Agora")
        botao_importar_xml_agora.setIcon(icone("UPLOAD"))
        botao_importar_xml_agora.setMinimumHeight(42)
        botao_importar_xml_agora.clicked.connect(self._importar_xml_agora)

        botao_mesclar_duplicados = QPushButton("Verificar Clientes Duplicados")
        botao_mesclar_duplicados.setIcon(icone("GIT_MERGE"))
        botao_mesclar_duplicados.setMinimumHeight(42)
        botao_mesclar_duplicados.clicked.connect(self._verificar_duplicados)

        layout = QVBoxLayout()
        layout.addWidget(titulo)
        layout.addWidget(QLabel("Conexão com o banco de dados:"))
        layout.addWidget(info_conexao)
        layout.addSpacing(12)
        layout.addWidget(
            QLabel(
                "Modo de data padrão sugerida em Adicionar Compra e Receber Conta\n"
                "(a data sempre pode ser alterada manualmente em cada lançamento):"
            )
        )
        layout.addWidget(self._campo_modo_data)
        layout.addWidget(botao_salvar_modo_data)
        layout.addSpacing(12)
        layout.addWidget(QLabel("Tema (requer reiniciar o sistema para ter efeito):"))
        layout.addWidget(self._campo_tema)
        layout.addWidget(botao_salvar_tema)
        layout.addSpacing(12)
        layout.addWidget(QLabel("Pasta de XMLs de NF-e (importação de vendas a prazo):"))
        layout.addWidget(self._campo_pasta_xml)
        layout.addWidget(botao_escolher_pasta_xml)
        layout.addWidget(botao_importar_xml_agora)
        layout.addWidget(botao_mesclar_duplicados)
        layout.addStretch()
        self.setLayout(layout)

        self._carregar_modo_data_atual()
        self._carregar_tema_atual()
        self._carregar_pasta_xml_atual()

    def _carregar_tema_atual(self) -> None:
        try:
            tema_atual = self._controller.obter_tema()
        except Exception:
            logger.exception("Falha ao carregar o tema configurado.")
            return
        indice = self._campo_tema.findData(tema_atual)
        if indice >= 0:
            self._campo_tema.setCurrentIndex(indice)

    def _salvar_tema(self) -> None:
        tema_selecionado: ModoTema = self._campo_tema.currentData()
        try:
            self._controller.definir_tema(tema_selecionado)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao salvar o tema.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível salvar a configuração.")
            return

        QMessageBox.information(
            self, "Configuração salva", "Tema atualizado. Reinicie o sistema para aplicar."
        )

    def _carregar_modo_data_atual(self) -> None:
        try:
            modo_atual = self._controller.obter_modo_data_padrao()
        except Exception:
            logger.exception("Falha ao carregar o modo de data padrão configurado.")
            return
        indice = self._campo_modo_data.findData(modo_atual)
        if indice >= 0:
            self._campo_modo_data.setCurrentIndex(indice)

    def _salvar_modo_data(self) -> None:
        modo_selecionado: ModoDataPadrao = self._campo_modo_data.currentData()
        try:
            self._controller.definir_modo_data_padrao(modo_selecionado)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível salvar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao salvar o modo de data padrão.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível salvar a configuração.")
            return

        QMessageBox.information(self, "Configuração salva", "Modo de data padrão atualizado.")

    def _carregar_pasta_xml_atual(self) -> None:
        try:
            self._campo_pasta_xml.setText(self._xml_controller.obter_pasta_xml())
        except Exception:
            logger.exception("Falha ao carregar a pasta de XMLs configurada.")
            self._campo_pasta_xml.setText("")

    def _escolher_pasta_xml(self) -> None:
        pasta = QFileDialog.getExistingDirectory(
            self, "Escolher Pasta de XMLs", self._campo_pasta_xml.text()
        )
        if not pasta:
            return

        try:
            self._xml_controller.definir_pasta_xml(pasta)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível salvar a pasta", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao salvar a pasta de XMLs.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível salvar a pasta de XMLs.")
            return

        self._campo_pasta_xml.setText(pasta)

    def _importar_xml_agora(self) -> None:
        dialogo = ImportarXmlDialog(self._usuario_logado, self)
        dialogo.exec()

    def _verificar_duplicados(self) -> None:
        dialogo = MesclarClientesDialog(self._usuario_logado, self)
        dialogo.exec()
