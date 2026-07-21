from __future__ import annotations

from app.ui.icons import CATEGORY_COLORS

ACCENT = "#0078d4"

# ── Base QSS fragments ───────────────────────────────────────────────

SCROLLBAR_DARK = """
QScrollBar:vertical {
    background: #1e1e1e; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #424242; border-radius: 5px; min-height: 24px; margin: 2px;
}
QScrollBar::handle:vertical:hover { background: #555555; }
QScrollBar::handle:vertical:pressed { background: #666666; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #1e1e1e; height: 10px; margin: 0;
}
QScrollBar::handle:horizontal {
    background: #424242; border-radius: 5px; min-width: 24px; margin: 2px;
}
QScrollBar::handle:horizontal:hover { background: #555555; }
QScrollBar::handle:horizontal:pressed { background: #666666; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""

SCROLLBAR_LIGHT = SCROLLBAR_DARK.replace("#1e1e1e", "#f5f5f5").replace("#424242", "#c1c1c1").replace("#555555", "#a8a8a8").replace("#666666", "#888888")

BASE_TRANSITIONS = """
QPushButton, QToolButton, QTabBar::tab, QTreeView::item, QListView::item,
QHeaderView::section, QComboBox, QLineEdit, QSpinBox {
    transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
"""

DARK_QSS = f"""
QMainWindow, QWidget {{
    background-color: #1e1e1e;
    color: #cccccc;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
}}
QMainWindow::separator {{ background-color: #3c3c3c; width: 1px; height: 1px; }}
QDialog {{ background-color: #1e1e1e; }}
{SCROLLBAR_DARK}
QTabWidget::pane {{ border: none; background-color: #1e1e1e; }}
QDockWidget {{
    color: #cccccc;
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background-color: #252526;
    color: #969696;
    padding: 4px 12px;
    border-bottom: 1px solid #3c3c3c;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
}}
QSplitter::handle {{ background-color: #3c3c3c; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}
QSplitter::handle:hover {{ background-color: {ACCENT}; }}
QTreeView, QListView {{
    background-color: #252526;
    alternate-background-color: #2a2a2a;
    color: #cccccc;
    border: none;
    outline: none;
}}
QTreeView::item, QListView::item {{
    padding: 3px 6px;
    border: none;
    min-height: 22px;
}}
QTreeView::item:hover, QListView::item:hover {{ background-color: #2a2d2e; }}
QTreeView::item:selected, QListView::item:selected {{ background-color: #094771; color: #ffffff; }}
QTreeView::item:selected:focus {{ background-color: #094771; }}
QTableView, QTableWidget {{
    background-color: #1e1e1e;
    alternate-background-color: #252526;
    color: #cccccc;
    gridline-color: #2d2d2d;
    border: 1px solid #3c3c3c;
    selection-background-color: #094771;
    selection-color: #ffffff;
    outline: none;
}}
QTableView::item, QTableWidget::item {{ padding: 2px 6px; }}
QHeaderView {{ background-color: #252526; }}
QHeaderView::section {{
    background-color: #252526;
    color: #969696;
    padding: 4px 8px;
    border: none;
    border-right: 1px solid #3c3c3c;
    border-bottom: 1px solid #3c3c3c;
    font-size: 11px;
    font-weight: 600;
}}
QHeaderView::section:hover {{ background-color: #2d2d2d; color: #cccccc; }}
QPushButton {{
    background-color: #2d2d2d;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 4px 12px;
    min-height: 22px;
}}
QPushButton:hover {{ background-color: #383838; border-color: #555555; }}
QPushButton:pressed {{ background-color: #505050; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #555555; background-color: #252526; border-color: #333333; }}
QPushButton:default {{ background-color: {ACCENT}; border-color: {ACCENT}; color: #ffffff; }}
QPushButton:default:hover {{ background-color: #1a8ad4; }}
QToolButton {{
    background-color: transparent;
    color: #cccccc;
    border: 1px solid transparent;
    border-radius: 3px;
    padding: 3px 6px;
}}
QToolButton:hover {{ background-color: #2a2d2e; border-color: #3c3c3c; }}
QToolButton:pressed {{ background-color: #383838; }}
QToolButton:disabled {{ color: #555555; }}
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 3px 8px;
    selection-background-color: #264f78;
    selection-color: #ffffff;
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {ACCENT}; }}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{ background-color: #252526; color: #555555; }}
QComboBox, QSpinBox {{
    background-color: #3c3c3c;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    padding: 3px 8px;
    min-height: 22px;
}}
QComboBox:focus, QSpinBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #969696;
    margin-right: 4px;
}}
QComboBox QAbstractItemView {{
    background-color: #252526;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    selection-background-color: #094771;
    selection-color: #ffffff;
    outline: none;
}}
QProgressBar {{
    background-color: #3c3c3c;
    border: 1px solid #3c3c3c;
    border-radius: 3px;
    text-align: center;
    color: #cccccc;
    font-size: 11px;
}}
QProgressBar::chunk {{ background-color: {ACCENT}; border-radius: 2px; }}
QMenuBar {{
    background-color: #1e1e1e;
    color: #cccccc;
    border-bottom: 1px solid #3c3c3c;
    padding: 2px 0;
}}
QMenuBar::item {{ padding: 4px 10px; border-radius: 3px; }}
QMenuBar::item:selected {{ background-color: #2d2d2d; }}
QMenu {{
    background-color: #2d2d2d;
    color: #cccccc;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{ padding: 4px 32px 4px 14px; border-radius: 3px; }}
QMenu::item:selected {{ background-color: #094771; color: #ffffff; }}
QMenu::separator {{ height: 1px; background-color: #3c3c3c; margin: 4px 8px; }}
QStatusBar {{
    background-color: #007acc;
    color: #ffffff;
    font-size: 12px;
    min-height: 24px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: #ffffff; padding: 0 6px; }}
QStatusBar QPushButton {{
    background-color: transparent;
    border: 1px solid rgba(255,255,255,0.2);
    color: #ffffff;
    padding: 1px 6px;
    min-height: 18px;
    font-size: 12px;
}}
QStatusBar QPushButton:hover {{ background-color: rgba(255,255,255,0.15); }}
QStatusBar QProgressBar {{
    background-color: rgba(255,255,255,0.15);
    border: none;
    border-radius: 2px;
    max-height: 14px;
    color: transparent;
}}
QStatusBar QProgressBar::chunk {{ background-color: #ffffff; border-radius: 2px; }}
QGroupBox {{
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: #969696;
    font-size: 11px;
}}
QCheckBox, QRadioButton {{ spacing: 6px; color: #cccccc; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid #555555;
    border-radius: 3px;
    background-color: #3c3c3c;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QRadioButton::indicator:checked {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
QLabel {{ color: #cccccc; background: transparent; }}
QLabel[heading="true"] {{ font-size: 20px; font-weight: 300; color: #ffffff; padding: 8px 0; }}
QLabel[subheading="true"] {{ font-size: 12px; font-weight: 700; color: #969696; padding: 4px 0; letter-spacing: 0.5px; text-transform: uppercase; }}
QLabel[metric="true"] {{ font-size: 24px; font-weight: 200; color: #ffffff; }}
QLabel[metric-label="true"] {{ font-size: 11px; color: #969696; }}
QToolTip {{
    background-color: #2d2d2d;
    color: #cccccc;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 4px 8px;
    font-size: 12px;
}}
QToolBar {{ background-color: #252526; border: none; padding: 2px 4px; spacing: 2px; }}
QToolBar QToolButton {{ padding: 3px 6px; min-width: 24px; min-height: 24px; }}
QScrollArea {{ border: none; background-color: transparent; }}
QFrame#card {{
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 6px;
}}
QFrame#card:hover {{
    border-color: #555555;
    background-color: #2a2d2e;
}}
"""

LIGHT_QSS = DARK_QSS
# Replace dark colors with light equivalents
for d, l in [
    ("#1e1e1e", "#ffffff"),
    ("#252526", "#f5f5f5"),
    ("#2d2d2d", "#e8e8e8"),
    ("#3c3c3c", "#d0d0d0"),
    ("#424242", "#c1c1c1"),
    ("#555555", "#a0a0a0"),
    ("#666666", "#888888"),
    ("#969696", "#666666"),
    ("#cccccc", "#1e1e1e"),
    ("#ffffff", "#1e1e1e"),
    ("rgba(255,255,255,0.2)", "rgba(0,0,0,0.1)"),
    ("rgba(255,255,255,0.15)", "rgba(0,0,0,0.06)"),
    ("rgba(255,255,255,0.08)", "rgba(0,0,0,0.08)"),
    ("rgba(255,255,255,0.12)", "rgba(0,0,0,0.12)"),
    ("QStatusBar { background-color: #007acc;", "QStatusBar { background-color: #007acc;"),
]:
    LIGHT_QSS = LIGHT_QSS.replace(d, l)


def stylesheet_for(theme_name: str) -> str:
    qss = LIGHT_QSS if theme_name == "light" else DARK_QSS
    return qss


def accent_for_category(category: str) -> str:
    return CATEGORY_COLORS.get(category, ACCENT)
