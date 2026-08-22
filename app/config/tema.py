"""Folha de estilo (QSS) do tema escuro.

O tema claro é o padrão nativo do sistema operacional (nenhum stylesheet
aplicado — mesmo comportamento que o sistema sempre teve). O tema escuro é
opcional, aplicado uma única vez em ``app/main.py`` na inicialização,
conforme a configuração salva em ``app.services.configuracao_service``.
"""

from __future__ import annotations

from app.services.configuracao_service import ModoTema

_COR_FUNDO = "#1e1e1e"
_COR_FUNDO_ALTERNATIVO = "#2b2b2b"
_COR_BORDA = "#3f3f3f"
_COR_TEXTO = "#e5e5e5"
_COR_TEXTO_DESATIVADO = "#8a8a8a"
_COR_DESTAQUE = "#3b82f6"
_COR_DESTAQUE_HOVER = "#2563eb"

_QSS_ESCURO = f"""
QWidget {{
    background-color: {_COR_FUNDO};
    color: {_COR_TEXTO};
    selection-background-color: {_COR_DESTAQUE};
    selection-color: #ffffff;
}}

QMainWindow, QDialog {{
    background-color: {_COR_FUNDO};
}}

QLabel {{
    background-color: transparent;
}}

QPushButton {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    border: 1px solid {_COR_BORDA};
    border-radius: 4px;
    padding: 6px 12px;
}}

QPushButton:hover {{
    background-color: {_COR_DESTAQUE};
    border-color: {_COR_DESTAQUE};
}}

QPushButton:pressed {{
    background-color: {_COR_DESTAQUE_HOVER};
}}

QPushButton:disabled {{
    color: {_COR_TEXTO_DESATIVADO};
    background-color: {_COR_FUNDO_ALTERNATIVO};
}}

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    border: 1px solid {_COR_BORDA};
    border-radius: 4px;
    padding: 4px;
    color: {_COR_TEXTO};
}}

QComboBox QAbstractItemView {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    color: {_COR_TEXTO};
    selection-background-color: {_COR_DESTAQUE};
}}

QTableWidget, QListWidget, QTreeWidget {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    alternate-background-color: {_COR_FUNDO};
    border: 1px solid {_COR_BORDA};
    gridline-color: {_COR_BORDA};
}}

QHeaderView::section {{
    background-color: {_COR_FUNDO};
    color: {_COR_TEXTO};
    border: 1px solid {_COR_BORDA};
    padding: 4px;
}}

QTabWidget::pane {{
    border: 1px solid {_COR_BORDA};
}}

QTabBar::tab {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    color: {_COR_TEXTO};
    padding: 6px 14px;
    border: 1px solid {_COR_BORDA};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: {_COR_DESTAQUE};
    color: #ffffff;
}}

QGroupBox {{
    border: 1px solid {_COR_BORDA};
    border-radius: 4px;
    margin-top: 10px;
    padding-top: 10px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}

QMenuBar, QMenu {{
    background-color: {_COR_FUNDO_ALTERNATIVO};
    color: {_COR_TEXTO};
}}

QMenu::item:selected {{
    background-color: {_COR_DESTAQUE};
}}

QScrollBar:vertical, QScrollBar:horizontal {{
    background-color: {_COR_FUNDO};
    border: none;
}}

QScrollBar::handle {{
    background-color: {_COR_BORDA};
    border-radius: 4px;
}}

QScrollBar::handle:hover {{
    background-color: {_COR_DESTAQUE};
}}
"""


def obter_stylesheet(tema: ModoTema) -> str:
    """Retorna o QSS a aplicar em ``QApplication.setStyleSheet``.

    Args:
        tema: Tema atualmente configurado.

    Returns:
        O QSS do tema escuro, ou string vazia para o tema claro (nenhum
        stylesheet — usa a aparência nativa do sistema operacional, o
        comportamento padrão de sempre).
    """
    return _QSS_ESCURO if tema == ModoTema.ESCURO else ""
