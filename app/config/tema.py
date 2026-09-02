"""Folha de estilo (QSS) dos temas claro e escuro.

Os dois temas compartilham a mesma estrutura de regras (``_construir_qss``)
— só a paleta de cores muda — para nunca ficarem "desalinhados" um do
outro (antes, só o tema escuro tinha QSS; o claro usava a aparência crua
do Windows). Aplicado uma única vez em ``app/main.py`` na inicialização,
conforme a configuração salva em ``app.services.configuracao_service``.

Duas convenções extras, opcionais, para telas que quiserem uma hierarquia
visual mais clara (não é automático — precisa marcar o widget):

- ``label.setProperty("papel", "titulo")`` (ou ``"subtitulo"``,
  ``"secundario"``) para textos que não sejam corpo normal.
- ``botao.setProperty("importancia", "primaria")`` para a ação principal
  de uma tela/diálogo (ex.: "Salvar", "Confirmar") se destacar das
  secundárias (ex.: "Cancelar").

Chame ``widget.style().unpolish(widget); widget.style().polish(widget)``
se precisar trocar uma dessas propriedades depois que o widget já foi
exibido (definir antes de mostrar, o caso mais comum, não precisa disso).
"""

from __future__ import annotations

from app.services.configuracao_service import ModoTema

# Fonte do sistema no Windows (a maioria das instalações já usa isso por
# padrão via "MS Shell Dlg 2", mas fixar explicitamente evita variação e
# garante o fallback numa instalação sem Segoe UI).
_FAMILIA_FONTE = '"Segoe UI", "Century Gothic", sans-serif'

_CORES_ESCURO = {
    "fundo": "#1e1e1e",
    "fundo_alt": "#2b2b2b",
    "fundo_hover": "#333a45",
    "borda": "#3f3f3f",
    "texto": "#e5e5e5",
    "texto_secundario": "#9ca3af",
    "texto_desativado": "#6b7280",
    "destaque": "#3b82f6",
    "destaque_hover": "#2563eb",
    "destaque_texto": "#ffffff",
    "erro": "#ef4444",
}

_CORES_CLARO = {
    "fundo": "#f5f6f8",
    "fundo_alt": "#ffffff",
    "fundo_hover": "#eef2ff",
    "borda": "#d7dbe1",
    "texto": "#1f2328",
    "texto_secundario": "#667085",
    "texto_desativado": "#9aa1ab",
    "destaque": "#2563eb",
    "destaque_hover": "#1d4ed8",
    "destaque_texto": "#ffffff",
    "erro": "#dc2626",
}


def _construir_qss(c: dict[str, str]) -> str:
    """Monta o QSS completo a partir de uma paleta de cores.

    Mantida como uma função só (em vez de duas strings quase idênticas)
    para os dois temas nunca ficarem incoerentes entre si — mudar uma
    regra aqui afeta claro e escuro igualmente; só a paleta (``c``) muda.
    """
    return f"""
QWidget {{
    background-color: {c["fundo"]};
    color: {c["texto"]};
    font-family: {_FAMILIA_FONTE};
    selection-background-color: {c["destaque"]};
    selection-color: {c["destaque_texto"]};
}}

QMainWindow, QDialog {{
    background-color: {c["fundo"]};
}}

QLabel {{
    background-color: transparent;
}}

QLabel[papel="titulo"] {{
    font-size: 17px;
    font-weight: 700;
}}

QLabel[papel="subtitulo"] {{
    font-size: 13px;
    font-weight: 600;
    color: {c["texto_secundario"]};
}}

QLabel[papel="secundario"] {{
    font-size: 12px;
    color: {c["texto_secundario"]};
}}

QPushButton {{
    background-color: {c["fundo_alt"]};
    border: 1px solid {c["borda"]};
    border-radius: 6px;
    padding: 7px 16px;
}}

QPushButton:hover {{
    background-color: {c["fundo_hover"]};
    border-color: {c["destaque"]};
}}

QPushButton:pressed {{
    background-color: {c["destaque"]};
    color: {c["destaque_texto"]};
}}

QPushButton:disabled {{
    color: {c["texto_desativado"]};
    background-color: {c["fundo_alt"]};
    border-color: {c["borda"]};
}}

QPushButton[importancia="primaria"] {{
    background-color: {c["destaque"]};
    border: 1px solid {c["destaque"]};
    color: {c["destaque_texto"]};
    font-weight: 600;
}}

QPushButton[importancia="primaria"]:hover {{
    background-color: {c["destaque_hover"]};
    border-color: {c["destaque_hover"]};
}}

QPushButton[importancia="primaria"]:pressed {{
    background-color: {c["destaque_hover"]};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background-color: {c["fundo_alt"]};
    border: 1px solid {c["borda"]};
    border-radius: 6px;
    padding: 6px 8px;
    color: {c["texto"]};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 1px solid {c["destaque"]};
}}

QLineEdit:disabled, QTextEdit:disabled, QComboBox:disabled {{
    color: {c["texto_desativado"]};
}}

QComboBox QAbstractItemView {{
    background-color: {c["fundo_alt"]};
    color: {c["texto"]};
    border: 1px solid {c["borda"]};
    selection-background-color: {c["destaque"]};
    selection-color: {c["destaque_texto"]};
}}

QTableWidget, QListWidget, QTreeWidget {{
    background-color: {c["fundo_alt"]};
    alternate-background-color: {c["fundo"]};
    border: 1px solid {c["borda"]};
    border-radius: 6px;
    gridline-color: {c["borda"]};
}}

QTableWidget::item, QListWidget::item, QTreeWidget::item {{
    padding: 4px;
}}

QTableWidget::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {{
    background-color: {c["destaque"]};
    color: {c["destaque_texto"]};
}}

QHeaderView::section {{
    background-color: {c["fundo"]};
    color: {c["texto_secundario"]};
    border: 1px solid {c["borda"]};
    padding: 6px;
    font-weight: 600;
}}

QTabWidget::pane {{
    border: 1px solid {c["borda"]};
    border-radius: 6px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {c["fundo"]};
    color: {c["texto_secundario"]};
    padding: 8px 16px;
    border: 1px solid {c["borda"]};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}

QTabBar::tab:hover {{
    color: {c["texto"]};
}}

QTabBar::tab:selected {{
    background-color: {c["destaque"]};
    color: {c["destaque_texto"]};
    font-weight: 600;
}}

QGroupBox {{
    background-color: {c["fundo_alt"]};
    border: 1px solid {c["borda"]};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 14px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {c["destaque"]};
    font-weight: 700;
}}

QMenuBar, QMenu {{
    background-color: {c["fundo_alt"]};
    color: {c["texto"]};
}}

QMenu {{
    border: 1px solid {c["borda"]};
}}

QMenu::item:selected {{
    background-color: {c["destaque"]};
    color: {c["destaque_texto"]};
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {c["fundo"]};
    border: none;
}}

QScrollBar::handle {{
    background-color: {c["borda"]};
    border-radius: 4px;
}}

QScrollBar::handle:hover {{
    background-color: {c["destaque"]};
}}
"""


_QSS_ESCURO = _construir_qss(_CORES_ESCURO)
_QSS_CLARO = _construir_qss(_CORES_CLARO)


def obter_stylesheet(tema: ModoTema) -> str:
    """Retorna o QSS a aplicar em ``QApplication.setStyleSheet``.

    Args:
        tema: Tema atualmente configurado.

    Returns:
        O QSS do tema claro ou escuro — os dois têm estilo próprio agora
        (antes, o claro usava a aparência nativa crua do Windows, sem
        stylesheet nenhum).
    """
    return _QSS_ESCURO if tema == ModoTema.ESCURO else _QSS_CLARO
