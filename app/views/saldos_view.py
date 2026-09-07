"""Tela de Saldos (PySide6), visível apenas para Administrador.

Reúne indicadores da situação **atual** das contas do negócio — nenhum
deles depende de um período selecionável (diferente da tela de Início,
que tem indicadores por período): "Total em aberto no negócio",
"Evolução de Vendas" (janela fixa dos últimos 6 meses), "Clientes com
Maior Saldo em Aberto" e "Saldo em Aberto" (tabela completa, exportável
para CSV/Excel).

Essas quatro funcionalidades já existiam antes — as três primeiras na
tela de Início, a última na sub-aba "Saldo em Aberto" de "Histórico e
Relatórios" — só foram reunidas aqui, sem mudar a lógica de negócio por
trás de nenhuma delas (ver ``app.services.relatorio_service.obter_painel_saldos``
e ``listar_saldos_em_aberto``).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.relatorio_controller import RelatorioController
from app.services.auth_service import UsuarioAutenticado
from app.utils.exceptions import ErroDeNegocio
from app.utils.graficos import construir_grafico_barras, construir_grafico_linha
from app.utils.icons import icone

# Altura mínima da tabela de "Saldo em Aberto", calculada para caber pelo
# menos 10 linhas visíveis sem precisar rolar dentro da própria tabela
# (~32px por linha + ~34px do cabeçalho). Sem isso, como o addStretch()
# no fim do layout absorve o espaço sobrando, a tabela ficava espremida
# numa altura quase nula — as linhas existiam, só não tinham espaço
# visível pra aparecer (mesmo problema que as tabelas de
# app.views.painel_inicio_view já evitam com o mesmo cálculo).
_ALTURA_TABELA_10_LINHAS = 10 * 32 + 34


class SaldosView(QWidget):
    """Tela de Saldos: situação atual das contas do negócio (somente Administrador)."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._controller = RelatorioController(usuario_logado)

        titulo = QLabel("Saldos")
        titulo.setProperty("papel", "titulo")

        botao_atualizar = QPushButton("Atualizar")
        botao_atualizar.setIcon(icone("REFRESH"))
        botao_atualizar.clicked.connect(self._carregar)

        layout_topo = QHBoxLayout()
        layout_topo.addWidget(titulo)
        layout_topo.addStretch()
        layout_topo.addWidget(botao_atualizar)

        self._area_scroll = QScrollArea()
        self._area_scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._layout_conteudo = QVBoxLayout(self._container)
        self._area_scroll.setWidget(self._container)

        layout = QVBoxLayout()
        layout.addLayout(layout_topo)
        layout.addWidget(self._area_scroll)
        self.setLayout(layout)

        self._carregar()

    def _limpar_conteudo(self) -> None:
        while self._layout_conteudo.count():
            item = self._layout_conteudo.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _carregar(self) -> None:
        self._limpar_conteudo()

        try:
            painel = self._controller.obter_saldos()
            saldos = self._controller.listar_saldos_em_aberto()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a tela de Saldos.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar os saldos.")
            return

        label_total_aberto = QLabel(f"Total em aberto (geral do negócio): R$ {painel.total_em_aberto_geral:.2f}")
        label_total_aberto.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        self._layout_conteudo.addWidget(label_total_aberto)

        if painel.evolucao_mensal:
            caixa = QGroupBox("Evolução de Vendas (últimos 6 meses)")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_linha(
                    "Total Vendido (R$)",
                    [p.mes for p in painel.evolucao_mensal],
                    [float(p.total) for p in painel.evolucao_mensal],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        if painel.maiores_saldos_em_aberto:
            caixa = QGroupBox("Clientes com Maior Saldo em Aberto")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                construir_grafico_barras(
                    "Saldo em Aberto (R$)",
                    [c.nome_principal for c in painel.maiores_saldos_em_aberto],
                    [float(c.valor) for c in painel.maiores_saldos_em_aberto],
                )
            )
            self._layout_conteudo.addWidget(caixa)

        caixa_saldo_em_aberto = QGroupBox("Saldo em Aberto")
        layout_caixa = QVBoxLayout(caixa_saldo_em_aberto)

        botao_exportar_csv = QPushButton("Exportar CSV")
        botao_exportar_csv.setIcon(icone("DOWNLOAD"))
        botao_exportar_csv.clicked.connect(self._exportar_csv)

        botao_exportar_xlsx = QPushButton("Exportar Excel")
        botao_exportar_xlsx.setIcon(icone("DOWNLOAD"))
        botao_exportar_xlsx.clicked.connect(self._exportar_xlsx)

        layout_botoes_exportar = QHBoxLayout()
        layout_botoes_exportar.addStretch()
        layout_botoes_exportar.addWidget(botao_exportar_csv)
        layout_botoes_exportar.addWidget(botao_exportar_xlsx)

        tabela_saldos = QTableWidget(len(saldos), 3)
        tabela_saldos.setHorizontalHeaderLabels(["Código", "Cliente", "Total em Aberto"])
        tabela_saldos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tabela_saldos.setMinimumHeight(_ALTURA_TABELA_10_LINHAS)
        for linha, saldo in enumerate(saldos):
            tabela_saldos.setItem(linha, 0, QTableWidgetItem(str(saldo.id_visivel)))
            tabela_saldos.setItem(linha, 1, QTableWidgetItem(saldo.nome_principal))
            tabela_saldos.setItem(linha, 2, QTableWidgetItem(f"R$ {saldo.total_em_aberto:.2f}"))

        layout_caixa.addLayout(layout_botoes_exportar)
        layout_caixa.addWidget(tabela_saldos)
        self._layout_conteudo.addWidget(caixa_saldo_em_aberto)

        self._layout_conteudo.addStretch()

    def _exportar_csv(self) -> None:
        caminho_arquivo, _ = QFileDialog.getSaveFileName(
            self, "Exportar Saldo em Aberto", "saldo_em_aberto.csv", "CSV (*.csv)"
        )
        if not caminho_arquivo:
            return

        try:
            self._controller.exportar_saldos_em_aberto_csv(caminho_arquivo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível exportar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao exportar o relatório de saldo em aberto para CSV.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível exportar o relatório.")
            return

        QMessageBox.information(self, "Exportado", f"Relatório exportado para:\n{caminho_arquivo}")

    def _exportar_xlsx(self) -> None:
        caminho_arquivo, _ = QFileDialog.getSaveFileName(
            self, "Exportar Saldo em Aberto", "saldo_em_aberto.xlsx", "Excel (*.xlsx)"
        )
        if not caminho_arquivo:
            return

        try:
            self._controller.exportar_saldos_em_aberto_xlsx(caminho_arquivo)
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível exportar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao exportar o relatório de saldo em aberto para Excel.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível exportar o relatório.")
            return

        QMessageBox.information(self, "Exportado", f"Relatório exportado para:\n{caminho_arquivo}")
