"""
app.ui.widgets.ribbon
======================
A lightweight ribbon-style toolbar (Power BI / Office-inspired) built from
QToolBar + QTabWidget rather than a heavyweight custom widget -- keeps
Phase 1 dependency-free while still delivering the "Home / Excel / Compare
/ Merge / ..." tabbed-toolbar look.

Each ribbon tab is auto-populated from the PluginManager's category
grouping, so adding a new plugin automatically gets it a button on the
correct ribbon tab with zero changes to this file.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QTabWidget, QVBoxLayout, QWidget

from app.core.plugin_base import Plugin


class RibbonTabContent(QWidget):
    """One page of the ribbon: a horizontal row of large tool buttons."""

    tool_activated = Signal(str)  # emits plugin_id

    def __init__(self, plugins: list[Plugin], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for plugin in plugins:
            button = QPushButton(plugin.metadata.display_name)
            button.setToolTip(plugin.metadata.description or plugin.metadata.display_name)
            button.setMinimumHeight(48)
            button.setMinimumWidth(120)
            button.clicked.connect(
                lambda _checked=False, pid=plugin.metadata.plugin_id: self.tool_activated.emit(pid)
            )
            layout.addWidget(button)

        layout.addStretch(1)


class Ribbon(QTabWidget):
    tool_activated = Signal(str)

    #: Fixed display order for known categories; anything else is appended
    #: alphabetically after these.
    CATEGORY_ORDER = [
        "Home",
        "Import",
        "Excel",
        "Compare",
        "Merge",
        "Transform",
        "Validation",
        "Reports",
        "Automation",
        "Templates",
        "Settings",
        "Engineering",
    ]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMaximumHeight(96)
        self.setDocumentMode(True)

    def build_from_plugins(self, plugins_by_category: dict[str, list[Plugin]]) -> None:
        self.clear()

        ordered_categories = [c for c in self.CATEGORY_ORDER if c in plugins_by_category]
        remaining = sorted(set(plugins_by_category) - set(ordered_categories))
        ordered_categories += remaining

        for category in ordered_categories:
            plugins = plugins_by_category[category]
            page = RibbonTabContent(plugins)
            page.tool_activated.connect(self.tool_activated)
            self.addTab(page, category)
