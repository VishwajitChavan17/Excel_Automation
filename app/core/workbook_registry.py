"""
app.core.workbook_registry
============================
Single source of truth for "what files are currently loaded". MainWindow
populates it as files are loaded; every plugin (Compare, Lookup, Duplicate
Finder, ...) reads from it via PluginContext instead of reaching into
MainWindow directly. This keeps plugins independently testable and
decoupled from the UI shell, per the plugin-architecture design goal.

Holds every sheet of every loaded workbook in memory (not just the active
sheet), since Compare/Lookup/Duplicate Finder all need to let the user pick
*which* sheet of *which* file to operate on.

Also owns the application's Undo/Redo history: every in-place data mutation
(remove duplicates, apply lookup, apply column mapping, run a workflow
step, ...) goes through replace_sheet_data(), which snapshots the prior
DataFrame before overwriting it. undo()/redo() restore snapshots and are
wired to Ctrl+Z / Ctrl+Y in MainWindow. This is a full-DataFrame snapshot
approach (not a diff/patch log) -- simple and correct, at the cost of
memory for very large sheets. Acceptable for the row counts this app
targets; a diff-based history could replace this later without changing
the public API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel.loader_service import reprofile_for_sheet
from app.services.excel.models import WorkbookHandle


@dataclass
class HistoryEntry:
    file_key: str
    sheet_name: str
    description: str
    dataframe_before: pd.DataFrame
    timestamp: datetime = field(default_factory=datetime.now)


class WorkbookRegistry(QObject):
    workbook_added = Signal(str)  # file_path key
    workbook_removed = Signal(str)
    workbook_updated = Signal(str)  # e.g. active sheet changed, or data mutated in place
    history_changed = Signal()  # undo/redo stack changed -- UI refreshes History panel + Edit menu
    mutation_recorded = Signal(str, str, str)  # (file_key, sheet_name, description) -- fires once per
    # genuine new operation (NOT on undo/redo replays), for the persistent audit log to subscribe to

    def __init__(self) -> None:
        super().__init__()
        self._handles: dict[str, WorkbookHandle] = {}
        self._sheets: dict[str, dict[str, pd.DataFrame]] = {}
        self._undo_stack: list[HistoryEntry] = []
        self._redo_stack: list[HistoryEntry] = []

    # -- mutation ------------------------------------------------------

    def add(self, handle: WorkbookHandle, sheets: dict[str, pd.DataFrame]) -> str:
        key = str(handle.file_path)
        self._handles[key] = handle
        self._sheets[key] = sheets
        self.workbook_added.emit(key)
        logger.debug("WorkbookRegistry: added {} ({} sheet(s))", key, len(sheets))
        return key

    def remove(self, key: str) -> None:
        self._handles.pop(key, None)
        self._sheets.pop(key, None)
        self.workbook_removed.emit(key)

    def set_active_sheet(self, key: str, sheet_name: str) -> None:
        handle = self._handles.get(key)
        sheets = self._sheets.get(key)
        if handle is None or sheets is None or sheet_name not in sheets:
            return
        reprofile_for_sheet(handle, sheets, sheet_name)
        self.workbook_updated.emit(key)

    def replace_sheet_data(
        self, key: str, sheet_name: str, df: pd.DataFrame, *, description: str = "Edit", record_history: bool = True
    ) -> None:
        """Used after an in-place operation (e.g. remove duplicates, apply
        lookup, apply column mapping, run a workflow step) so the preview
        grid and Properties panel reflect the new data. Snapshots the prior
        DataFrame onto the undo stack unless record_history is False (used
        internally by undo()/redo() themselves, to avoid re-recording)."""
        if key not in self._sheets:
            return

        if record_history:
            previous = self._sheets[key].get(sheet_name)
            if previous is not None:
                self._undo_stack.append(HistoryEntry(key, sheet_name, description, previous))
                self._redo_stack.clear()
                self.history_changed.emit()
            self.mutation_recorded.emit(key, sheet_name, description)

        self._sheets[key][sheet_name] = df
        if self._handles[key].active_sheet == sheet_name:
            reprofile_for_sheet(self._handles[key], self._sheets[key], sheet_name)
        self.workbook_updated.emit(key)

    # -- undo / redo -------------------------------------------------------

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def undo(self) -> HistoryEntry | None:
        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        current = self._sheets.get(entry.file_key, {}).get(entry.sheet_name)
        if current is not None:
            self._redo_stack.append(HistoryEntry(entry.file_key, entry.sheet_name, entry.description, current))
        self.replace_sheet_data(entry.file_key, entry.sheet_name, entry.dataframe_before, record_history=False)
        self.history_changed.emit()
        logger.info("Undo: reverted '{}' on {} ({})", entry.description, entry.file_key, entry.sheet_name)
        return entry

    def redo(self) -> HistoryEntry | None:
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        current = self._sheets.get(entry.file_key, {}).get(entry.sheet_name)
        if current is not None:
            self._undo_stack.append(HistoryEntry(entry.file_key, entry.sheet_name, entry.description, current))
        self.replace_sheet_data(entry.file_key, entry.sheet_name, entry.dataframe_before, record_history=False)
        self.history_changed.emit()
        logger.info("Redo: reapplied '{}' on {} ({})", entry.description, entry.file_key, entry.sheet_name)
        return entry

    def history_entries(self) -> list[HistoryEntry]:
        """Most-recent-first, for display in the History panel."""
        return list(reversed(self._undo_stack))

    # -- access ----------------------------------------------------------

    def keys(self) -> list[str]:
        return list(self._handles.keys())

    def get_handle(self, key: str) -> WorkbookHandle | None:
        return self._handles.get(key)

    def get_dataframe(self, key: str, sheet_name: str | None = None) -> pd.DataFrame | None:
        sheets = self._sheets.get(key)
        if sheets is None:
            return None
        if sheet_name is None:
            sheet_name = self._handles[key].active_sheet
        return sheets.get(sheet_name)

    def get_sheet_names(self, key: str) -> list[str]:
        sheets = self._sheets.get(key)
        return list(sheets.keys()) if sheets else []

    def all_handles(self) -> list[WorkbookHandle]:
        return list(self._handles.values())

    def display_names(self) -> dict[str, str]:
        """{key: display_name} -- convenient for populating file pickers."""
        return {key: h.display_name for key, h in self._handles.items()}
