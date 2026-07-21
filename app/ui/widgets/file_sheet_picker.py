"""
app.ui.widgets.file_sheet_picker
===================================
Reusable "pick a loaded file, then pick one of its sheets" control used by
every tool that operates on already-loaded workbooks (Compare, Lookup &
Copy, Duplicate Finder). Populated from the WorkbookRegistry and kept live
via its workbook_added/workbook_removed signals, so newly loaded files
appear in open tool tabs without needing to reopen them.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QWidget

from app.core.workbook_registry import WorkbookRegistry


class FileSheetPicker(QWidget):
    selection_changed = Signal()  # emitted whenever the resolved (file, sheet) changes

    def __init__(self, registry: WorkbookRegistry, label: str = "File:", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry

        self._file_combo = QComboBox()
        self._sheet_combo = QComboBox()

        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow(label, self._file_combo)
        form.addRow("Sheet:", self._sheet_combo)

        self._file_combo.currentIndexChanged.connect(self._on_file_changed)
        self._sheet_combo.currentIndexChanged.connect(lambda _i: self.selection_changed.emit())

        registry.workbook_added.connect(self.refresh)
        registry.workbook_removed.connect(self.refresh)
        self.destroyed.connect(self._disconnect_registry)

        self.refresh()

    def _disconnect_registry(self) -> None:
        try:
            self._registry.workbook_added.disconnect(self.refresh)
        except (TypeError, RuntimeError):
            pass
        try:
            self._registry.workbook_removed.disconnect(self.refresh)
        except (TypeError, RuntimeError):
            pass

    def refresh(self, *_args) -> None:
        previous_key = self.selected_file_key()
        self._file_combo.blockSignals(True)
        self._file_combo.clear()
        for key, name in self._registry.display_names().items():
            self._file_combo.addItem(name, userData=key)
        self._file_combo.blockSignals(False)

        if previous_key:
            idx = self._file_combo.findData(previous_key)
            if idx >= 0:
                self._file_combo.setCurrentIndex(idx)
        self._on_file_changed(self._file_combo.currentIndex())

    def _on_file_changed(self, _index: int) -> None:
        key = self.selected_file_key()
        self._sheet_combo.blockSignals(True)
        self._sheet_combo.clear()
        if key:
            for sheet_name in self._registry.get_sheet_names(key):
                self._sheet_combo.addItem(sheet_name)
        self._sheet_combo.blockSignals(False)
        self.selection_changed.emit()

    def selected_file_key(self) -> str | None:
        return self._file_combo.currentData()

    def selected_file_name(self) -> str:
        return self._file_combo.currentText()

    def selected_sheet(self) -> str | None:
        return self._sheet_combo.currentText() or None

    def selected_dataframe(self):
        key = self.selected_file_key()
        sheet = self.selected_sheet()
        if not key or not sheet:
            return None
        return self._registry.get_dataframe(key, sheet)

    def set_selected_file(self, file_key: str) -> None:
        idx = self._file_combo.findData(file_key)
        if idx >= 0:
            self._file_combo.setCurrentIndex(idx)
