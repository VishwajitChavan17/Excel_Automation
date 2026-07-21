"""
app.ui.theme
============
Central stylesheet definitions. Two palettes (dark/light) are provided as
Qt stylesheets (QSS). MainWindow.apply_theme() swaps between them at
runtime via the Settings tab's theme selector -- no restart required.
"""

from __future__ import annotations

DARK_QSS = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #21262d;
    background-color: #0d1117;
}

QTabBar::tab {
    background-color: #161b22;
    color: #8b949e;
    padding: 8px 18px;
    border: 1px solid #21262d;
    border-bottom: none;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #0d1117;
    color: #e6edf3;
    border-bottom: 2px solid #58a6ff;
}

QTabBar::tab:hover:!selected {
    background-color: #1c2128;
}

QDockWidget {
    color: #c9d1d9;
    titlebar-close-icon: none;
}

QDockWidget::title {
    background-color: #161b22;
    padding: 6px;
    border-bottom: 1px solid #21262d;
    font-weight: bold;
}

QTreeView, QTableView, QListView {
    background-color: #0d1117;
    alternate-background-color: #11161d;
    color: #c9d1d9;
    border: 1px solid #21262d;
    gridline-color: #21262d;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}

QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    padding: 6px;
    border: none;
    border-right: 1px solid #21262d;
    border-bottom: 1px solid #21262d;
}

QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #21262d;
    color: #8b949e;
}

QToolBar {
    background-color: #161b22;
    border: none;
    padding: 4px;
    spacing: 4px;
}

QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 6px 14px;
}

QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}

QPushButton:pressed {
    background-color: #1f6feb;
}

QPushButton:disabled {
    color: #484f58;
    background-color: #161b22;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit, QPlainTextEdit {
    background-color: #010409;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 4px 6px;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #58a6ff;
}

QProgressBar {
    background-color: #161b22;
    border: 1px solid #21262d;
    border-radius: 4px;
    text-align: center;
    color: #c9d1d9;
}

QProgressBar::chunk {
    background-color: #3fb950;
    border-radius: 4px;
}

QMenuBar {
    background-color: #0d1117;
    color: #c9d1d9;
}

QMenuBar::item:selected {
    background-color: #21262d;
}

QMenu {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
}

QMenu::item:selected {
    background-color: #1f6feb;
}

QScrollBar:vertical {
    background: #0d1117;
    width: 12px;
}

QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 6px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #484f58;
}

QSplitter::handle {
    background-color: #21262d;
}
"""

LIGHT_QSS = """
QMainWindow, QWidget {
    background-color: #ffffff;
    color: #24292f;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QTabBar::tab {
    background-color: #f6f8fa;
    color: #57606a;
    padding: 8px 18px;
    border: 1px solid #d0d7de;
    border-bottom: none;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #0969da;
    border-bottom: 2px solid #0969da;
}

QTreeView, QTableView, QListView {
    background-color: #ffffff;
    alternate-background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    selection-background-color: #218bff;
    selection-color: #ffffff;
}

QStatusBar {
    background-color: #f6f8fa;
    border-top: 1px solid #d0d7de;
}
"""


def stylesheet_for(theme_name: str) -> str:
    return LIGHT_QSS if theme_name == "light" else DARK_QSS
