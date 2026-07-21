from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QMenu, QTreeView, QVBoxLayout, QWidget

from app.services.excel.models import WorkbookHandle

FILE_PATH_ROLE = 1000
MAX_HISTORY_ENTRIES = 100

# Professional unicode icons (monochrome, render consistently)
ICO_FILE = "\u25C9"        # ◉
ICO_SHEET = "\u25A1"       # □
ICO_REPORT = "\u25B6"      # ▶
ICO_WORKFLOW = "\u2699"    # ⚙
ICO_TEMPLATE = "\u2691"    # ⚑
ICO_HISTORY = "\u29D6"     # ⧖
ICO_FAVORITE = "\u2605"    # ★
ICO_RECENT = "\u29D7"      # ⧗
ICO_FOLDER = "\u25B8"      # ▸
ICO_GROUP = "\u25B6"       # ▸


def _group_icon(name: str) -> str:
    icons = {
        "Loaded Excel Files": ICO_FILE,
        "Recent Files": ICO_RECENT,
        "Saved Workflows": ICO_WORKFLOW,
        "Templates": ICO_TEMPLATE,
        "Reports": ICO_REPORT,
        "History": ICO_HISTORY,
        "Favorites": ICO_FAVORITE,
    }
    return f"{icons.get(name, ICO_FOLDER)}  {name}"


class ProjectExplorerPanel(QWidget):
    file_activated = Signal(str)
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
            item = QStandardItem(_group_icon(group_name))
            item.setEditable(False)
            item.setSelectable(False)
            font = item.font()
            font.setPointSize(11)
            font.setBold(True)
            item.setFont(font)
            self._model.appendRow(item)
            self._groups[group_name] = item

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(True)
        self._tree.expandAll()
        self._tree.setIndentation(16)
        self._tree.setAnimated(True)
        self._tree.setExpandsOnDoubleClick(False)
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
        label = f"{ICO_FILE}  {handle.display_name}"
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
            self._add_sheet_children(item, handle)
        else:
            item.setText(label)
            item.removeRows(0, item.rowCount())
            self._add_sheet_children(item, handle)

        item.setToolTip(tooltip)
        self._update_group_count(self.GROUP_LOADED_FILES)
        self._tree.expandAll()

    def _add_sheet_children(self, parent_item: QStandardItem, handle: WorkbookHandle) -> None:
        for sheet in handle.sheets:
            sheet_item = QStandardItem(f"  {ICO_SHEET}  {sheet.name}")
            sheet_item.setEditable(False)
            sheet_item.setToolTip(
                f"<b>{sheet.name}</b><br>"
                f"Rows: {sheet.row_count:,}<br>"
                f"Columns: {sheet.column_count}<br>"
                f"{'Hidden' if sheet.is_hidden else 'Visible'}"
            )
            parent_item.appendRow(sheet_item)

    def _update_group_count(self, group_name: str) -> None:
        group = self._groups[group_name]
        count = group.rowCount()
        base = _group_icon(group_name)
        group.setText(f"{base}   [{count}]")

    def remove_loaded_file(self, file_path: str) -> None:
        item = self._loaded_file_items.pop(file_path, None)
        if item is not None:
            group = self._groups[self.GROUP_LOADED_FILES]
            group.removeRow(item.row())
            self._update_group_count(self.GROUP_LOADED_FILES)

    def add_recent_file(self, file_path: str) -> None:
        import os

        item = QStandardItem(f"{ICO_RECENT}  {os.path.basename(file_path)}")
        item.setEditable(False)
        item.setData(file_path, role=FILE_PATH_ROLE)
        item.setToolTip(file_path)
        self._groups[self.GROUP_RECENT].appendRow(item)

    def add_report(self, report_path: str) -> None:
        import os

        item = QStandardItem(f"{ICO_REPORT}  {os.path.basename(report_path)}")
        item.setEditable(False)
        item.setData(report_path, role=FILE_PATH_ROLE)
        item.setToolTip(report_path)
        self._groups[self.GROUP_REPORTS].appendRow(item)

    def add_workflow(self, workflow_path: str) -> None:
        import os

        item = QStandardItem(f"{ICO_WORKFLOW}  {os.path.basename(workflow_path)}")
        item.setEditable(False)
        item.setData(workflow_path, role=FILE_PATH_ROLE)
        item.setToolTip(workflow_path)
        self._groups[self.GROUP_WORKFLOWS].appendRow(item)

    def add_history_entry(self, description: str) -> None:
        group = self._groups[self.GROUP_HISTORY]
        while group.rowCount() >= MAX_HISTORY_ENTRIES:
            group.removeRow(0)
        item = QStandardItem(f"{ICO_HISTORY}  {description}")
        item.setEditable(False)
        group.appendRow(item)

    def set_history_entries(self, entries) -> None:
        group = self._groups[self.GROUP_HISTORY]
        group.removeRows(0, group.rowCount())
        for entry in entries:
            timestamp = entry.timestamp.strftime("%H:%M:%S")
            item = QStandardItem(f"{ICO_HISTORY}  [{timestamp}] {entry.description}")
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
            return

        menu = QMenu(self._tree)

        action = menu.addAction(f"{ICO_FILE}  Preview")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.preview_requested.emit(fp))
        action = menu.addAction(f"{ICO_TEMPLATE}  Rename")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.rename_requested.emit(fp))
        action = menu.addAction(f"\u21BB  Reload")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.reload_requested.emit(fp))
        action = menu.addAction(f"\u2716  Close")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.close_requested.emit(fp))

        menu.addSeparator()

        action = menu.addAction(f"{ICO_REPORT}  Export")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.export_requested.emit(fp))
        action = menu.addAction(f"\u25A2  Duplicate")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.duplicate_requested.emit(fp))

        menu.addSeparator()

        action = menu.addAction(f"\u2261  Compare With...")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.compare_with_requested.emit(fp))

        menu.addSeparator()

        action = menu.addAction(f"\u24D8  File Information")
        action.triggered.connect(lambda _checked=False, fp=file_path: self.file_info_requested.emit(fp))

        menu.exec(self._tree.viewport().mapToGlobal(point))
