"""
app.ui.panels.project_explorer
================================
Left dock panel. Tree of Loaded Files / Recent Files / Saved Workflows /
Templates / Reports / History / Favorites, with icons, rich per-file
tooltips (sheet count, rows, columns, size, last modified), and a
right-click context menu (Preview, Rename, Reload, Close, Export,
Duplicate, Compare With..., File Information).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QMenu, QTreeView, QVBoxLayout, QWidget

from app.services.excel.models import WorkbookHandle

FILE_PATH_ROLE = 1000


def _group_icon(name: str) -> str:
    return {
        "Loaded Excel Files": "📊",
        "Recent Files": "🕒",
        "Saved Workflows": "⚙️",
        "Templates": "📐",
        "Reports": "📄",
        "History": "🕓",
        "Favorites": "⭐",
    }.get(name, "📁")


class ProjectExplorerPanel(QWidget):
    file_activated = Signal(str)  # double-click -> preview

    # context-menu actions, all emit the file_path key
    preview_requested = Signal(str)
    rename_requested = Signal(str)
    reload_requested = Signal(str)
    close_requested = Signal(str)
    export_requested = Signal(str)
    duplicate_requested = Signal(str)
    compare_with_requested = Signal(str)
    file_info_requested = Signal(str)

    GROUP_LOADED_FILES = "Loaded Excel Files"
    GROUP_RECENT = "Recent Files"
    GROUP_WORKFLOWS = "Saved Workflows"
    GROUP_TEMPLATES = "Templates"
    GROUP_REPORTS = "Reports"
    GROUP_HISTORY = "History"
    GROUP_FAVORITES = "Favorites"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._model = QStandardItemModel()
        self._model.setHorizontalHeaderLabels(["Project Explorer"])

        self._groups: dict[str, QStandardItem] = {}
        for group_name in (
            self.GROUP_LOADED_FILES,
            self.GROUP_RECENT,
            self.GROUP_WORKFLOWS,
            self.GROUP_TEMPLATES,
            self.GROUP_REPORTS,
            self.GROUP_HISTORY,
            self.GROUP_FAVORITES,
        ):
            item = QStandardItem(f"{_group_icon(group_name)}  {group_name}")
            item.setEditable(False)
            self._model.appendRow(item)
            self._groups[group_name] = item

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(False)
        self._tree.expandAll()
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._tree)

        self._loaded_file_items: dict[str, QStandardItem] = {}
        self._favorites: set[str] = set()

    # -- population ----------------------------------------------------

    def add_loaded_file(self, handle: WorkbookHandle) -> None:
        file_key = str(handle.file_path)
        label = f"📈 {handle.display_name}   ({handle.row_count:,} rows x {handle.column_count} cols)"
        tooltip = (
            f"<b>{handle.display_name}</b><br>"
            f"Sheets: {handle.sheet_count}<br>"
            f"Rows: {handle.row_count:,}<br>"
            f"Columns: {handle.column_count}<br>"
            f"Size: {handle.file_size_display}<br>"
            f"Modified: {handle.last_modified.strftime('%Y-%m-%d %H:%M') if handle.last_modified else '-'}<br>"
            f"Engine: {handle.engine_used}"
        )

        item = self._loaded_file_items.get(file_key)
        if item is None:
            item = QStandardItem(label)
            item.setEditable(False)
            item.setData(file_key, role=FILE_PATH_ROLE)
            self._groups[self.GROUP_LOADED_FILES].appendRow(item)
            self._loaded_file_items[file_key] = item
        else:
            item.setText(label)

        item.setToolTip(tooltip)
        self._tree.expandAll()

    def remove_loaded_file(self, file_path: str) -> None:
        item = self._loaded_file_items.pop(file_path, None)
        if item is not None:
            group = self._groups[self.GROUP_LOADED_FILES]
            group.removeRow(item.row())

    def add_recent_file(self, file_path: str) -> None:
        import os

        item = QStandardItem(f"🕒 {os.path.basename(file_path)}")
        item.setEditable(False)
        item.setData(file_path, role=FILE_PATH_ROLE)
        item.setToolTip(file_path)
        self._groups[self.GROUP_RECENT].appendRow(item)

    def add_report(self, report_path: str) -> None:
        import os

        item = QStandardItem(f"📄 {os.path.basename(report_path)}")
        item.setEditable(False)
        item.setData(report_path, role=FILE_PATH_ROLE)
        item.setToolTip(report_path)
        self._groups[self.GROUP_REPORTS].appendRow(item)

    def add_workflow(self, workflow_path: str) -> None:
        import os

        item = QStandardItem(f"⚙️ {os.path.basename(workflow_path)}")
        item.setEditable(False)
        item.setData(workflow_path, role=FILE_PATH_ROLE)
        item.setToolTip(workflow_path)
        self._groups[self.GROUP_WORKFLOWS].appendRow(item)

    def add_history_entry(self, description: str) -> None:
        item = QStandardItem(f"🕓 {description}")
        item.setEditable(False)
        self._groups[self.GROUP_HISTORY].appendRow(item)

    def set_history_entries(self, entries) -> None:
        """Clear and repopulate the History group from a list of objects
        exposing .description and .timestamp (e.g. HistoryEntry). Called
        after every undo/redo since the stack can change non-incrementally."""
        group = self._groups[self.GROUP_HISTORY]
        group.removeRows(0, group.rowCount())
        for entry in entries:
            timestamp = entry.timestamp.strftime("%H:%M:%S")
            item = QStandardItem(f"🕓 [{timestamp}] {entry.description}")
            item.setEditable(False)
            group.appendRow(item)

    # -- interaction -----------------------------------------------------

    def _on_double_click(self, index) -> None:
        item = self._model.itemFromIndex(index)
        file_path = item.data(role=FILE_PATH_ROLE)
        if file_path:
            self.file_activated.emit(file_path)

    def _on_context_menu(self, point) -> None:
        index = self._tree.indexAt(point)
        if not index.isValid():
            return
        item = self._model.itemFromIndex(index)
        file_path = item.data(role=FILE_PATH_ROLE)
        if not file_path or file_path not in self._loaded_file_items:
            return  # context menu only applies to Loaded Files entries

        menu = QMenu(self._tree)
        actions = {
            "Preview": self.preview_requested,
            "Rename": self.rename_requested,
            "Reload": self.reload_requested,
            "Close": self.close_requested,
            "Export": self.export_requested,
            "Duplicate": self.duplicate_requested,
            "Compare With...": self.compare_with_requested,
            "File Information": self.file_info_requested,
        }
        for label, signal in actions.items():
            action = menu.addAction(label)
            action.triggered.connect(lambda _checked=False, s=signal, fp=file_path: s.emit(fp))
            if label in ("Rename", "Duplicate"):
                menu.addSeparator() if label == "Duplicate" else None

        menu.exec(self._tree.viewport().mapToGlobal(point))
