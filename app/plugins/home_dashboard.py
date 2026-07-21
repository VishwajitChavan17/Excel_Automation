"""
app.plugins.home_dashboard
============================
The functional Home dashboard: large action cards that jump straight into
the most-used workflows (Load, Compare, Consolidate, Lookup & Copy, Merge,
Data Cleaning), plus live Recent Files and Recent Workflows lists pulled
from the app configuration.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata


class ActionCard(QFrame):
    clicked = Signal()

    def __init__(self, icon: str, title: str, description: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("actionCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            "#actionCard { background-color: #161b22; border: 1px solid #30363d; "
            "border-radius: 8px; } "
            "#actionCard:hover { border: 1px solid #58a6ff; background-color: #1c2128; }"
        )
        self.setMinimumSize(220, 130)

        layout = QVBoxLayout(self)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 28px;")
        layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)

        desc_label = QLabel(description)
        desc_label.setStyleSheet("color: #8b949e; font-size: 12px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        layout.addStretch(1)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.clicked.emit()
        super().mousePressEvent(event)


class HomeDashboardWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 24, 24, 24)
        content_layout.setSpacing(16)

        title = QLabel("Excel Automation Studio")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        content_layout.addWidget(title)

        subtitle = QLabel("Rolls-Royce Power Systems (MTU) - Engineering Tools")
        subtitle.setStyleSheet("color: #8b949e; font-size: 13px;")
        content_layout.addWidget(subtitle)

        content_layout.addWidget(QLabel(""))  # spacer

        cards_label = QLabel("Quick Actions")
        cards_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        content_layout.addWidget(cards_label)

        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)
        card_specs = [
            ("📂", "Load Excel Files", "Open one or more workbooks/CSVs.", self._on_load_files),
            ("🔍", "Compare Files", "Diff two workbooks by key column(s).", lambda: self._open_plugin("compare.excel_compare")),
            ("🧩", "Consolidate Files", "Merge many files into one master sheet.", lambda: self._open_plugin("merge.excel_merge")),
            ("🔗", "Lookup & Copy Values", "Copy matching values across workbooks.", lambda: self._open_plugin("transform.lookup_copy")),
            ("🔀", "Merge Files", "Union / join workbooks together.", lambda: self._open_plugin("merge.excel_merge")),
            ("🧹", "Data Cleaning", "Trim, replace, split, and normalize data.", lambda: self._open_plugin("excel.duplicate_finder")),
            ("📁", "Recent Projects", "Jump back into a recently loaded file.", self._on_load_files),
        ]
        for i, (icon, title_text, desc, handler) in enumerate(card_specs):
            card = ActionCard(icon, title_text, desc)
            card.clicked.connect(handler)
            cards_grid.addWidget(card, i // 4, i % 4)
        content_layout.addLayout(cards_grid)

        lists_row = QHBoxLayout()

        recent_files_box = QVBoxLayout()
        recent_files_label = QLabel("Recent Files")
        recent_files_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        recent_files_box.addWidget(recent_files_label)
        self._recent_files_list = QListWidget()
        self._recent_files_list.setMaximumHeight(180)
        self._populate_recent_files()
        recent_files_box.addWidget(self._recent_files_list)
        lists_row.addLayout(recent_files_box)

        recent_workflows_box = QVBoxLayout()
        recent_workflows_label = QLabel("Recently Executed Workflows")
        recent_workflows_label.setStyleSheet("font-size: 15px; font-weight: bold;")
        recent_workflows_box.addWidget(recent_workflows_label)
        self._recent_workflows_list = QListWidget()
        self._recent_workflows_list.setMaximumHeight(180)
        self._recent_workflows_list.addItem("No workflows executed yet -- see Automation tab (Phase 4).")
        recent_workflows_box.addWidget(self._recent_workflows_list)
        lists_row.addLayout(recent_workflows_box)

        content_layout.addLayout(lists_row)
        content_layout.addStretch(1)

    def _populate_recent_files(self) -> None:
        self._recent_files_list.clear()
        recents = self._context.config.get("recent_files", []) if self._context.config else []
        if not recents:
            self._recent_files_list.addItem("No files loaded yet.")
            return
        for path in recents[:10]:
            self._recent_files_list.addItem(path)

    def _on_load_files(self) -> None:
        if self._context.main_window is not None:
            self._context.main_window.open_files_dialog()

    def _open_plugin(self, plugin_id: str) -> None:
        if self._context.main_window is not None:
            self._context.main_window.open_plugin_tab(plugin_id)


class HomeDashboardPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="home.dashboard",
        display_name="Welcome",
        category=PluginCategory.HOME,
        description="Studio welcome / quick-start dashboard.",
        version="2.0.0",
    )

    def create_widget(self, parent=None):
        return HomeDashboardWidget(self.context, parent)
