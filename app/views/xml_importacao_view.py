"""Telas de importação de XML de NF-e (PySide6).

``ImportarXmlDialog``: lista os XMLs de venda a prazo pendentes, permite
revisar/ajustar a quem cada um deve ser vinculado (cliente existente ou
"criar cliente novo") e confirma a importação em lote.

``ProdutosXmlDialog``: mostra os produtos de uma nota já importada, lidos
ao vivo do arquivo XML original (nunca duplicados no banco).
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.xml_importacao_controller import XmlImportacaoController
from app.services.auth_service import UsuarioAutenticado
from app.services.xml_importacao_service import CandidatoImportacao, EscolhaImportacao
from app.utils.exceptions import ErroDeNegocio
from app.utils.icons import icone
from app.utils.nfe_parser import ProdutoXml


class ObterProdutosWorker(QThread):
    """Busca os produtos de uma nota fiscal em segundo plano, fora da thread da UI.

    A busca do arquivo certo entre todos os XMLs da pasta configurada
    pode demorar quando há muitas notas — rodar isso na thread da UI
    travaria a interface até terminar.
    """

    produtos_prontos = Signal(list)
    erro_ocorrido = Signal(str)
    progresso = Signal(int, int)

    def __init__(
        self, controller: XmlImportacaoController, chave: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._chave = chave

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            produtos = self._controller.obter_produtos(self._chave, progresso=self.progresso.emit)
        except (ErroDeNegocio, ValueError) as exc:
            self.erro_ocorrido.emit(str(exc))
        except Exception:
            logger.exception("Falha ao ler os produtos do XML de chave '%s'.", self._chave)
            self.erro_ocorrido.emit("Não foi possível ler os produtos do XML.")
        else:
            self.produtos_prontos.emit(produtos)


class _ListarCandidatosWorker(QThread):
    """Varre a pasta de XMLs e lista os candidatos pendentes, fora da thread da UI.

    Faz o parse de cada XML e uma consulta ao banco por candidato — com
    muitos arquivos na pasta, rodar isso na thread da UI trava a interface
    até terminar (mesmo motivo do ``ObterProdutosWorker``).
    """

    candidatos_prontos = Signal(list)
    erro_ocorrido = Signal(str)
    progresso = Signal(int, int)

    def __init__(self, controller: XmlImportacaoController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            candidatos = self._controller.listar_candidatos(progresso=self.progresso.emit)
        except (ErroDeNegocio, ValueError) as exc:
            self.erro_ocorrido.emit(str(exc))
        except Exception:
            logger.exception("Falha ao listar candidatos de importação de XML.")
            self.erro_ocorrido.emit("Não foi possível varrer a pasta de XMLs configurada.")
        else:
            self.candidatos_prontos.emit(candidatos)


class _ImportarWorker(QThread):
    """Confirma a importação em lote, fora da thread da UI (mesmo motivo acima)."""

    importacao_concluida = Signal(list)
    erro_ocorrido = Signal(str)

    def __init__(
        self,
        controller: XmlImportacaoController,
        escolhas: list[EscolhaImportacao],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._escolhas = escolhas

    def run(self) -> None:  # noqa: D102 (documentado na classe)
        try:
            resultados = self._controller.importar(self._escolhas)
        except (ErroDeNegocio, ValueError) as exc:
            self.erro_ocorrido.emit(str(exc))
        except Exception:
            logger.exception("Falha ao confirmar importação de XMLs.")
            self.erro_ocorrido.emit("Não foi possível concluir a importação.")
        else:
            self.importacao_concluida.emit(resultados)


class ProdutosXmlDialog(QDialog):
    """Mostra os produtos de uma nota fiscal (lidos ao vivo do XML original)."""

    def __init__(self, produtos: list[ProdutoXml], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Produtos da Nota Fiscal")
        self.setMinimumSize(420, 320)

        tabela = QTableWidget(len(produtos), 3)
        tabela.setHorizontalHeaderLabels(["Produto", "Quantidade", "Valor"])
        tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabela.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        for linha, produto in enumerate(produtos):
            tabela.setItem(linha, 0, QTableWidgetItem(produto.nome))
            tabela.setItem(linha, 1, QTableWidgetItem(str(produto.quantidade)))
            tabela.setItem(linha, 2, QTableWidgetItem(f"R$ {produto.valor:.2f}"))

        botao_fechar = QPushButton("Fechar")
        botao_fechar.setIcon(icone("X"))
        botao_fechar.setMinimumHeight(38)
        botao_fechar.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.addWidget(tabela)
        layout.addWidget(botao_fechar)
        self.setLayout(layout)


class ImportarXmlDialog(QDialog):
    """Tela de revisão e importação em lote dos XMLs de venda a prazo pendentes."""

    def __init__(self, usuario_logado: UsuarioAutenticado, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = XmlImportacaoController(usuario_logado)
        self._candidatos: list[CandidatoImportacao] = []
        self._combos: list[QComboBox] = []
        self._worker: QThread | None = None
        self._encerrado = False

        self.setWindowTitle("Importar XMLs (Venda a Prazo)")
        self.setMinimumSize(720, 440)

        self._tabela = QTableWidget(0, 4)
        self._tabela.setHorizontalHeaderLabels(["Nome no XML", "Valor", "Data", "Vincular a"])
        self._tabela.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        self._label_status = QLabel()
        self._label_status.setWordWrap(True)

        self._botao_importar = QPushButton("Confirmar Importação")
        self._botao_importar.setIcon(icone("UPLOAD"))
        self._botao_importar.setMinimumHeight(42)
        self._botao_importar.clicked.connect(self._confirmar)

        self._botao_fechar = QPushButton("Fechar")
        self._botao_fechar.setIcon(icone("X"))
        self._botao_fechar.setMinimumHeight(38)
        self._botao_fechar.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("XMLs de 'venda a prazo' pendentes de importação:"))
        layout.addWidget(self._tabela)
        layout.addWidget(self._label_status)
        layout.addWidget(self._botao_importar)
        layout.addWidget(self._botao_fechar)
        self.setLayout(layout)

        self._carregar()

    def _carregar(self) -> None:
        self._label_status.setText("Varrendo a pasta de XMLs configurada, aguarde...")
        self._botao_importar.setEnabled(False)

        # Sem parent (None): a varredura roda em segundo plano de verdade —
        # se o usuário fechar o diálogo antes de terminar (pasta com muitos
        # XMLs pode demorar bastante), a janela fecha na hora, sem travar
        # nem esperar a operação. A QThread não fica presa ao ciclo de vida
        # da janela, e os callbacks abaixo conferem ``self._encerrado``
        # antes de mexer em qualquer widget.
        worker = _ListarCandidatosWorker(self._controller)
        worker.candidatos_prontos.connect(self._candidatos_carregados)
        worker.erro_ocorrido.connect(self._erro_ao_carregar)
        worker.progresso.connect(self._atualizar_progresso_carregamento)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _atualizar_progresso_carregamento(self, atual: int, total: int) -> None:
        if self._encerrado:
            return
        self._label_status.setText(f"Verificando arquivo {atual} de {total}, aguarde...")

    def _candidatos_carregados(self, candidatos: list[CandidatoImportacao]) -> None:
        if self._encerrado:
            return

        self._candidatos = candidatos
        self._combos = []
        self._tabela.setRowCount(len(self._candidatos))

        if not self._candidatos:
            self._label_status.setText(
                "Nenhum XML novo de 'venda a prazo' encontrado na pasta configurada."
            )
            return

        self._botao_importar.setEnabled(True)
        self._label_status.setText(
            f"{len(self._candidatos)} XML(s) pendente(s). Revise o cliente de cada um antes de "
            "confirmar."
        )

        for linha, candidato in enumerate(self._candidatos):
            self._tabela.setItem(linha, 0, QTableWidgetItem(candidato.nome_cliente_xml))
            self._tabela.setItem(linha, 1, QTableWidgetItem(f"R$ {candidato.valor:.2f}"))
            self._tabela.setItem(linha, 2, QTableWidgetItem(candidato.data.strftime("%d/%m/%Y")))

            combo = QComboBox()
            for cliente_candidato in candidato.candidatos_cliente:
                rotulo = cliente_candidato.nome_principal
                if cliente_candidato.nome_alternativo_encontrado:
                    rotulo += f" ({cliente_candidato.nome_alternativo_encontrado})"
                combo.addItem(rotulo, userData=cliente_candidato.id)
            combo.addItem("Criar cliente novo", userData=None)
            self._tabela.setCellWidget(linha, 3, combo)
            self._combos.append(combo)

    def _erro_ao_carregar(self, mensagem: str) -> None:
        if self._encerrado:
            return
        QMessageBox.warning(self, "Não foi possível listar os XMLs", mensagem)

    def _confirmar(self) -> None:
        if not self._candidatos:
            return

        escolhas = [
            EscolhaImportacao(caminho_arquivo=candidato.caminho_arquivo, cliente_id=combo.currentData())
            for candidato, combo in zip(self._candidatos, self._combos)
        ]

        self._botao_importar.setEnabled(False)
        self._label_status.setText("Importando, aguarde...")

        worker = _ImportarWorker(self._controller, escolhas)
        worker.importacao_concluida.connect(self._importacao_concluida)
        worker.erro_ocorrido.connect(self._erro_ao_importar)
        worker.finished.connect(worker.deleteLater)
        self._worker = worker
        worker.start()

    def _importacao_concluida(self, resultados: list) -> None:
        if self._encerrado:
            return
        novos = sum(1 for r in resultados if r.cliente_criado)
        QMessageBox.information(
            self,
            "Importação concluída",
            f"{len(resultados)} conta(s) importada(s). {novos} cliente(s) novo(s) criado(s) "
            "(pendentes de confirmação, destacados em vermelho na busca).",
        )
        self.accept()

    def _erro_ao_importar(self, mensagem: str) -> None:
        if self._encerrado:
            return
        self._botao_importar.setEnabled(True)
        self._label_status.setText(
            f"{len(self._candidatos)} XML(s) pendente(s). Revise o cliente de cada um antes de "
            "confirmar."
        )
        QMessageBox.warning(self, "Não foi possível importar", mensagem)

    def closeEvent(self, event) -> None:  # noqa: N802 (nome exigido pelo Qt)
        self._encerrado = True
        super().closeEvent(event)

    def accept(self) -> None:
        self._encerrado = True
        super().accept()

    def reject(self) -> None:
        self._encerrado = True
        super().reject()
