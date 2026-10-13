"""Tela de Saldos (PySide6), visível apenas para Administrador.

Reúne a situação **atual** das contas do negócio — nada aqui depende de
uma data escolhida (diferente da tela de Início). De cima para baixo:

- três cartões (Total em Aberto, Clientes com saldo, Acima do Limite);
- "Evolução de Vendas" (janela fixa dos últimos 6 meses);
- "Clientes Acima do Limite de Fiado" e "Clientes com Maior Atraso" (com
  o filtro de dias e o botão "Lembretes em lote") — quem precisa de atenção;
- "Clientes com Maior Saldo em Aberto";
- "Saldo em Aberto" (tabela completa, com busca e exportação para CSV/Excel).

Clicar num cliente de qualquer tabela abre a Ficha do Cliente.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.logging_config import logger
from app.controllers.relatorio_controller import RelatorioController
from app.services.auth_service import UsuarioAutenticado
from app.services.relatorio_service import SaldoClienteResumo
from app.utils.exceptions import ErroDeNegocio
from app.utils.formatacao import formatar_reais
from app.utils.graficos import GraficoColunas, ItemRanking, ListaRanking, PontoColuna
from app.utils.icons import icone
from app.utils.tabelas import ajustar_altura_as_linhas, ajustar_colunas, aplicar_estado_vazio, item_valor
from app.views.ficha_cliente_view import FichaClienteView
from app.views.lembretes_em_lote_view import LembretesEmLoteDialog

# Altura mínima da tabela de "Saldo em Aberto", calculada para caber pelo
# menos 10 linhas visíveis sem precisar rolar dentro da própria tabela
# (~32px por linha + ~34px do cabeçalho). Sem isso, como o addStretch()
# no fim do layout absorve o espaço sobrando, a tabela ficava espremida
# numa altura quase nula — as linhas existiam, só não tinham espaço
# visível pra aparecer (mesmo problema que as tabelas de
# app.views.painel_inicio_view já evitam com o mesmo cálculo).
_ALTURA_TABELA_10_LINHAS = 10 * 32 + 34


_MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def _ponto_do_mes(mes: str, total) -> PontoColuna:
    """Coluna de um mês: ``"2026-10"`` vira os rótulos "out" / "2026"."""
    ano, numero = mes.split("-")
    return PontoColuna(rotulo=_MESES[int(numero) - 1], valor=total, sub_rotulo=ano)


class SaldosView(QWidget):
    """Tela de Saldos: situação atual das contas do negócio (somente Administrador)."""

    def __init__(self, usuario_logado: UsuarioAutenticado) -> None:
        super().__init__()
        self._usuario_logado = usuario_logado
        self._controller = RelatorioController(usuario_logado)
        self._saldos_carregados: list[SaldoClienteResumo] = []
        self._atrasos_carregados: list = []
        self._dias_atraso_carregado = 30

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
        # De cima para baixo: cartões e evolução de vendas (refeitos a cada
        # carga), as duas listas de quem precisa de atenção (fixas, para o
        # filtro de dias não se perder ao atualizar) e o resto (maiores
        # saldos e tabela, refeitos a cada carga).
        layout_container = QVBoxLayout(self._container)
        self._layout_cards = QVBoxLayout()
        self._layout_evolucao = QVBoxLayout()
        self._layout_conteudo = QVBoxLayout()
        layout_container.addLayout(self._layout_cards)
        layout_container.addLayout(self._layout_evolucao)
        layout_container.addWidget(self._construir_caixa_acima_do_limite())
        layout_container.addWidget(self._construir_caixa_maior_atraso())
        layout_container.addLayout(self._layout_conteudo)
        self._area_scroll.setWidget(self._container)

        layout = QVBoxLayout()
        layout.addLayout(layout_topo)
        layout.addWidget(self._area_scroll)
        self.setLayout(layout)

        self._carregar()

    def _limpar_conteudo(self) -> None:
        for layout in (self._layout_cards, self._layout_evolucao, self._layout_conteudo):
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _abrir_ficha(self, cliente_id: str) -> None:
        FichaClienteView(self._usuario_logado, cliente_id, self).exec()
        self._carregar()  # um pagamento/edição feito na ficha pode ter mudado os saldos

    @staticmethod
    def _criar_card(titulo: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setProperty("papel", "card")
        layout = QVBoxLayout(card)
        label_titulo = QLabel(titulo)
        label_titulo.setProperty("papel", "secundario")
        label_valor = QLabel("-")
        label_valor.setStyleSheet("font-size: 22px; font-weight: 700;")
        layout.addWidget(label_titulo)
        layout.addWidget(label_valor)
        return card, label_valor

    def _carregar(self) -> None:
        self._limpar_conteudo()

        try:
            painel = self._controller.obter_saldos()
            saldos = self._controller.listar_saldos_em_aberto()
            acima_do_limite = self._controller.listar_clientes_acima_do_limite()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a tela de Saldos.")
            QMessageBox.critical(self, "Erro inesperado", "Não foi possível carregar os saldos.")
            return

        self._saldos_carregados = saldos

        # -- Cartões ----------------------------------------------------------
        card_total, label_total = self._criar_card("TOTAL EM ABERTO")
        label_total.setText(f"{formatar_reais(painel.total_em_aberto_geral)}")
        card_clientes, label_clientes = self._criar_card("CLIENTES COM SALDO")
        label_clientes.setText(str(len(saldos)))
        card_limite, label_limite = self._criar_card("ACIMA DO LIMITE")
        label_limite.setText(str(len(acima_do_limite)))

        linha_cards = QWidget()
        layout_cards = QHBoxLayout(linha_cards)
        layout_cards.setContentsMargins(0, 0, 0, 0)
        for card in (card_total, card_clientes, card_limite):
            layout_cards.addWidget(card)
        self._layout_cards.addWidget(linha_cards)
        self._carregar_acima_do_limite()
        self._carregar_maiores_atrasos()

        if painel.evolucao_mensal:
            caixa = QGroupBox("Evolução de Vendas (últimos 6 meses)")
            layout_caixa = QVBoxLayout(caixa)
            pontos = painel.evolucao_mensal
            layout_caixa.addWidget(
                GraficoColunas(
                    [_ponto_do_mes(p.mes, p.total) for p in pontos],
                    indice_destaque=len(pontos) - 1,  # o último é o mês atual
                )
            )
            self._layout_evolucao.addWidget(caixa)

        if painel.maiores_saldos_em_aberto:
            caixa = QGroupBox("Clientes com Maior Saldo em Aberto")
            layout_caixa = QVBoxLayout(caixa)
            layout_caixa.addWidget(
                ListaRanking(
                    [ItemRanking(c.nome_principal, c.valor) for c in painel.maiores_saldos_em_aberto],
                    titulo_valor="Saldo em aberto",
                )
            )
            self._layout_conteudo.addWidget(caixa)

        caixa_saldo_em_aberto = QGroupBox("Saldo em Aberto")
        layout_caixa = QVBoxLayout(caixa_saldo_em_aberto)

        self._campo_busca = QLineEdit()
        self._campo_busca.setPlaceholderText("Buscar por nome...")
        self._campo_busca.textChanged.connect(self._filtrar_tabela)

        botao_exportar_csv = QPushButton("Exportar CSV")
        botao_exportar_csv.setIcon(icone("DOWNLOAD"))
        botao_exportar_csv.clicked.connect(self._exportar_csv)

        botao_exportar_xlsx = QPushButton("Exportar Excel")
        botao_exportar_xlsx.setIcon(icone("DOWNLOAD"))
        botao_exportar_xlsx.clicked.connect(self._exportar_xlsx)

        layout_botoes_exportar = QHBoxLayout()
        layout_botoes_exportar.addWidget(self._campo_busca)
        layout_botoes_exportar.addStretch()
        layout_botoes_exportar.addWidget(botao_exportar_csv)
        layout_botoes_exportar.addWidget(botao_exportar_xlsx)

        self._tabela_saldos = QTableWidget(len(saldos), 3)
        self._tabela_saldos.setHorizontalHeaderLabels(["Código", "Cliente", "Total em Aberto"])
        self._tabela_saldos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_saldos.setMinimumHeight(_ALTURA_TABELA_10_LINHAS)
        self._tabela_saldos.cellDoubleClicked.connect(self._abrir_ficha_da_linha)
        ajustar_colunas(self._tabela_saldos, 1)  # Cliente

        self._label_saldos_vazio = QLabel("Nenhum cliente com saldo em aberto.")
        self._label_saldos_vazio.setProperty("papel", "secundario")
        self._label_saldos_vazio.setVisible(False)

        self._preencher_tabela(saldos)

        layout_caixa.addLayout(layout_botoes_exportar)
        layout_caixa.addWidget(self._tabela_saldos)
        layout_caixa.addWidget(self._label_saldos_vazio)
        self._layout_conteudo.addWidget(caixa_saldo_em_aberto)

        self._layout_conteudo.addStretch()

    # -- Clientes com Maior Atraso --------------------------------------------
    #
    # Fora do ciclo de recarregamento por período (_carregar/_limpar_conteudo)
    # de propósito: tem seu próprio filtro (dias em atraso) e não deve ser
    # reconstruída/perder o valor do filtro sempre que o período do resto do
    # painel for atualizado.

    def _construir_caixa_maior_atraso(self) -> QGroupBox:
        caixa = QGroupBox("Clientes com Maior Atraso")

        self._campo_dias_atraso = QSpinBox()
        self._campo_dias_atraso.setRange(1, 365)
        self._campo_dias_atraso.setValue(30)
        self._campo_dias_atraso.setSuffix(" dias")
        # Sem botão próprio de atualizar: mudar o número já refaz a lista
        # (só quando termina de digitar, não a cada tecla).
        self._campo_dias_atraso.setKeyboardTracking(False)
        self._campo_dias_atraso.valueChanged.connect(lambda _dias: self._carregar_maiores_atrasos())

        layout_filtro = QHBoxLayout()
        layout_filtro.addWidget(QLabel("Considerar em atraso compras com mais de:"))
        layout_filtro.addWidget(self._campo_dias_atraso)
        self._botao_lembretes_em_lote = QPushButton("Lembretes em lote")
        self._botao_lembretes_em_lote.setIcon(icone("BRAND_WHATSAPP"))
        self._botao_lembretes_em_lote.clicked.connect(self._abrir_lembretes_em_lote)

        layout_filtro.addStretch()
        layout_filtro.addWidget(self._botao_lembretes_em_lote)

        self._tabela_atrasos = QTableWidget(0, 6)
        self._tabela_atrasos.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Em atraso há", "Total Atrasado", "Total em Aberto", ""]
        )
        self._tabela_atrasos.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_atrasos.cellDoubleClicked.connect(
            lambda linha, _coluna: self._abrir_ficha(self._tabela_atrasos.item(linha, 0).data(Qt.ItemDataRole.UserRole))
        )
        ajustar_colunas(self._tabela_atrasos, 0)  # Cliente

        self._label_atrasos_vazio = QLabel("Nenhum cliente com saldo atrasado no momento.")
        self._label_atrasos_vazio.setProperty("papel", "secundario")
        self._label_atrasos_vazio.setVisible(False)

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_filtro)
        layout_caixa.addWidget(QLabel(
            "Sem data de vencimento própria no fiado, a data da compra é usada como "
            "referência: quanto mais antiga uma compra ainda em aberto, mais atrasada conta."
        ))
        layout_caixa.addWidget(self._tabela_atrasos)
        layout_caixa.addWidget(self._label_atrasos_vazio)
        return caixa

    def _abrir_lembretes_em_lote(self) -> None:
        """Lembrete para vários clientes da lista de atrasos, um por vez."""
        LembretesEmLoteDialog(self._atrasos_carregados, self._dias_atraso_carregado, self).exec()

    def _carregar_maiores_atrasos(self) -> None:
        try:
            saldos = self._controller.listar_saldos_em_atraso(self._campo_dias_atraso.value())
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de clientes com maior atraso.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar os clientes com maior atraso."
            )
            return

        self._atrasos_carregados = saldos
        self._dias_atraso_carregado = self._campo_dias_atraso.value()
        self._botao_lembretes_em_lote.setEnabled(bool(saldos))
        self._tabela_atrasos.setRowCount(len(saldos))
        for linha, saldo in enumerate(saldos):
            item_nome = QTableWidgetItem(saldo.nome_principal)
            item_nome.setData(Qt.ItemDataRole.UserRole, saldo.id)
            self._tabela_atrasos.setItem(linha, 0, item_nome)
            self._tabela_atrasos.setItem(linha, 1, QTableWidgetItem(saldo.telefone or "-"))
            self._tabela_atrasos.setItem(
                linha, 2, QTableWidgetItem(f"{saldo.dias_desde_a_compra_mais_antiga} dias")
            )
            self._tabela_atrasos.setItem(
                linha, 3, item_valor(formatar_reais(saldo.total_em_atraso))
            )
            self._tabela_atrasos.setItem(
                linha, 4, item_valor(formatar_reais(saldo.total_em_aberto))
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, s=saldo: self._abrir_ficha(s.id))
            self._tabela_atrasos.setCellWidget(linha, 5, botao_ver)

        ajustar_altura_as_linhas(self._tabela_atrasos)
        aplicar_estado_vazio(self._tabela_atrasos, self._label_atrasos_vazio)

    # -- Clientes Acima do Limite de Fiado -----------------------------------
    #
    # Mesmo raciocínio da caixa de maior atraso: fora do ciclo de
    # recarregamento por período, com filtro/atualização próprios.

    def _construir_caixa_acima_do_limite(self) -> QGroupBox:
        caixa = QGroupBox("Clientes Acima do Limite de Fiado")

        layout_topo = QHBoxLayout()
        layout_topo.addWidget(QLabel(
            "Clientes com limite de fiado definido (ver Editar Cliente) cujo saldo "
            "em aberto já passou do combinado."
        ))
        layout_topo.addStretch()

        self._tabela_acima_do_limite = QTableWidget(0, 6)
        self._tabela_acima_do_limite.setHorizontalHeaderLabels(
            ["Cliente", "Telefone", "Limite", "Total em Aberto", "Excesso", ""]
        )
        self._tabela_acima_do_limite.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._tabela_acima_do_limite.cellDoubleClicked.connect(
            lambda linha, _coluna: self._abrir_ficha(
                self._tabela_acima_do_limite.item(linha, 0).data(Qt.ItemDataRole.UserRole)
            )
        )
        ajustar_colunas(self._tabela_acima_do_limite, 0)  # Cliente

        self._label_acima_limite_vazio = QLabel("Nenhum cliente acima do limite no momento.")
        self._label_acima_limite_vazio.setProperty("papel", "secundario")
        self._label_acima_limite_vazio.setVisible(False)

        layout_caixa = QVBoxLayout(caixa)
        layout_caixa.addLayout(layout_topo)
        layout_caixa.addWidget(self._tabela_acima_do_limite)
        layout_caixa.addWidget(self._label_acima_limite_vazio)
        return caixa

    def _carregar_acima_do_limite(self) -> None:
        try:
            clientes = self._controller.listar_clientes_acima_do_limite()
        except (ErroDeNegocio, ValueError) as exc:
            QMessageBox.warning(self, "Não foi possível carregar", str(exc))
            return
        except Exception:
            logger.exception("Falha inesperada ao carregar a lista de clientes acima do limite.")
            QMessageBox.critical(
                self, "Erro inesperado", "Não foi possível carregar os clientes acima do limite."
            )
            return

        self._tabela_acima_do_limite.setRowCount(len(clientes))
        for linha, item in enumerate(clientes):
            item_nome = QTableWidgetItem(item.nome_principal)
            item_nome.setData(Qt.ItemDataRole.UserRole, item.id)
            self._tabela_acima_do_limite.setItem(linha, 0, item_nome)
            self._tabela_acima_do_limite.setItem(linha, 1, QTableWidgetItem(item.telefone or "-"))
            self._tabela_acima_do_limite.setItem(
                linha, 2, item_valor(formatar_reais(item.limite_fiado))
            )
            self._tabela_acima_do_limite.setItem(
                linha, 3, item_valor(formatar_reais(item.total_em_aberto))
            )
            self._tabela_acima_do_limite.setItem(
                linha, 4, item_valor(formatar_reais(item.excesso))
            )

            botao_ver = QPushButton()
            botao_ver.setIcon(icone("CHEVRON_RIGHT"))
            botao_ver.setFlat(True)
            botao_ver.setToolTip("Abrir ficha do cliente")
            botao_ver.clicked.connect(lambda _checked=False, i=item: self._abrir_ficha(i.id))
            self._tabela_acima_do_limite.setCellWidget(linha, 5, botao_ver)

        ajustar_altura_as_linhas(self._tabela_acima_do_limite)
        aplicar_estado_vazio(self._tabela_acima_do_limite, self._label_acima_limite_vazio)

    def _preencher_tabela(self, saldos: list[SaldoClienteResumo]) -> None:
        self._tabela_saldos.setRowCount(len(saldos))
        for linha, saldo in enumerate(saldos):
            item_codigo = QTableWidgetItem(str(saldo.id_visivel))
            item_codigo.setData(Qt.ItemDataRole.UserRole, saldo.id)
            self._tabela_saldos.setItem(linha, 0, item_codigo)
            self._tabela_saldos.setItem(linha, 1, QTableWidgetItem(saldo.nome_principal))
            self._tabela_saldos.setItem(linha, 2, item_valor(formatar_reais(saldo.total_em_aberto)))
        aplicar_estado_vazio(self._tabela_saldos, self._label_saldos_vazio)

    def _filtrar_tabela(self, termo: str) -> None:
        termo_normalizado = termo.strip().lower()
        filtrados = [
            s for s in self._saldos_carregados if termo_normalizado in s.nome_principal.lower()
        ] if termo_normalizado else self._saldos_carregados
        self._preencher_tabela(filtrados)

    def _abrir_ficha_da_linha(self, linha: int, _coluna: int) -> None:
        item = self._tabela_saldos.item(linha, 0)
        if item is None:
            return
        cliente_id = item.data(Qt.ItemDataRole.UserRole)
        dialogo = FichaClienteView(self._usuario_logado, cliente_id, self)
        dialogo.exec()
        self._carregar()  # o pagamento/edição feito na ficha pode ter mudado o saldo

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
