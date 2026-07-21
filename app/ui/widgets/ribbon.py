from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from app.core.plugin_base import Plugin
from app.ui.icons import CATEGORY_COLORS, CATEGORY_ICONS, RIBBON_GROUPS, icon_for, group_for_plugin

GROUP_STYLE = """
QPushButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    color: #cccccc;
    font-size: 11px;
    padding: 4px 6px;
    min-width: 36px;
    min-height: 32px;
}}
QPushButton:hover {{
    background-color: rgba(255,255,255,0.08);
    border-color: rgba(255,255,255,0.12);
}}
QPushButton:pressed {{
    background-color: rgba(255,255,255,0.15);
}}
"""


class RibbonGroup(QWidget):
    tool_activated = Signal(str)

    def __init__(self, title: str, accent: str = "#0078d4", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 2)
        layout.setSpacing(2)

        self._button_layout = QHBoxLayout()
        self._button_layout.setSpacing(2)
        self._button_layout.setAlignment(Qt.AlignLeft)
        layout.addLayout(self._button_layout)

        sep = QLabel()
        sep.setFixedWidth(1)
        sep.setStyleSheet("background-color: rgba(255,255,255,0.08); margin: 4px 0;")

        title_lbl = QLabel(title.upper())
        title_lbl.setAlignment(Qt.AlignCenter)
        title_lbl.setStyleSheet(
            f"color: {accent}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 0.8px; border: none; background: transparent; padding: 2px 0;"
        )
        layout.addWidget(title_lbl)
        self._title = title_lbl
        self._sep = sep

    def add_button(self, label: str, plugin_id: str, icon_char: str = "") -> None:
        display = f"{icon_char}  {label}" if icon_char else label
        btn = QPushButton(display)
        btn.setToolTip(f"{label}  ({plugin_id})")
        btn.setMinimumHeight(34)
        btn.setMinimumWidth(40)
        btn.setStyleSheet(GROUP_STYLE)
        btn.clicked.connect(lambda _checked=False, pid=plugin_id: self.tool_activated.emit(pid))
        self._button_layout.addWidget(btn)

    def add_stretch(self) -> None:
        self._button_layout.addStretch(1)


class RibbonTabContent(QWidget):
    tool_activated = Signal(str)

    def __init__(
        self,
        category: str,
        plugins: list[Plugin],
        accent: str = "#0078d4",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)

        groups: dict[str, RibbonGroup] = {}
        group_order = list(RIBBON_GROUPS.get(category, {}).keys())

        for plugin in plugins:
            gname = group_for_plugin(category, plugin.metadata.plugin_id)
            if gname not in groups:
                grp = RibbonGroup(gname, accent)
                groups[gname] = grp
                grp.tool_activated.connect(self.tool_activated)
            else:
                grp = groups[gname]
            ico = icon_for(plugin.metadata.plugin_id)
            grp.add_button(plugin.metadata.display_name, plugin.metadata.plugin_id, ico)

        # Render groups in defined order, then any extras
        seen = set()
        for gname in group_order:
            if gname in groups:
                if layout.count() > 0:
                    sep = QLabel()
                    sep.setFixedWidth(1)
                    sep.setStyleSheet("background-color: rgba(255,255,255,0.08); margin: 4px 0;")
                    layout.addWidget(sep)
                layout.addWidget(groups[gname])
                seen.add(gname)
        for gname, grp in groups.items():
            if gname not in seen:
                if layout.count() > 0:
                    sep = QLabel()
                    sep.setFixedWidth(1)
                    sep.setStyleSheet("background-color: rgba(255,255,255,0.08); margin: 4px 0;")
                    layout.addWidget(sep)
                layout.addWidget(grp)
                seen.add(gname)

        if not plugins:
            empty = QLabel("No tools available")
            empty.setStyleSheet("color: #555555; padding: 12px;")
            layout.addWidget(empty)

        layout.addStretch(1)


class Ribbon(QTabWidget):
    tool_activated = Signal(str)

    CATEGORY_ORDER = [
        "Home", "Import", "Excel", "Compare", "Merge", "Transform",
        "Validation", "Reports", "Automation", "Templates", "Settings", "Engineering",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(130)
        self.setDocumentMode(True)
        self.currentChanged.connect(self._on_tab_changed)
        self._pages: dict[str, RibbonTabContent] = {}

    def build_from_plugins(self, plugins_by_category: dict[str, list[Plugin]]) -> None:
        for i in range(self.count()):
            w = self.widget(i)
            if w:
                w.deleteLater()
        self.clear()
        self._pages.clear()

        ordered_categories = [c for c in self.CATEGORY_ORDER if c in plugins_by_category]
        remaining = sorted(set(plugins_by_category) - set(ordered_categories))
        ordered_categories += remaining

        for i, category in enumerate(ordered_categories):
            plugins = plugins_by_category[category]
            accent = CATEGORY_COLORS.get(category, "#0078d4")
            page = RibbonTabContent(category, plugins, accent)
            page.tool_activated.connect(self.tool_activated)
            icon_char = CATEGORY_ICONS.get(category, "")
            label = f"{icon_char}  {category}" if icon_char else category
            self.addTab(page, label)
            self._pages[category] = page

        if ordered_categories:
            self._apply_tab_style(ordered_categories[0])

    def _on_tab_changed(self, index: int) -> None:
        categories = list(self._pages.keys())
        if 0 <= index < len(categories):
            self._apply_tab_style(categories[index])

    def _apply_tab_style(self, category: str) -> None:
        accent = CATEGORY_COLORS.get(category, "#0078d4")
        self.setStyleSheet(
            f"""
            QTabWidget::pane {{ border: none; background-color: #1e1e1e; }}
            QTabBar {{
                background-color: #252526;
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background-color: #2d2d2d;
                color: #969696;
                padding: 6px 14px;
                border: none;
                border-right: 1px solid #1e1e1e;
                font-size: 11px;
                font-weight: 600;
                min-height: 22px;
            }}
            QTabBar::tab:selected {{
                background-color: #1e1e1e;
                color: #ffffff;
                border-top: 2px solid {accent};
            }}
            QTabBar::tab:hover:!selected {{
                background-color: #383838;
                color: #cccccc;
            }}
            """
        )
