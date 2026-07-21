"""
tests/test_phase4_history.py
==============================
Headless tests for WorkbookRegistry's undo/redo history tracking. Requires
Qt (WorkbookRegistry is a QObject for its signals) but no QApplication
event loop is needed for these synchronous method calls.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

QtCore = pytest.importorskip("PySide6.QtCore")


def _make_registry_with_file(tmp_path: Path):
    from app.core.workbook_registry import WorkbookRegistry
    from app.services.excel.loader_service import load_workbook_all_sheets

    registry = WorkbookRegistry()
    path = tmp_path / "data.xlsx"
    pd.DataFrame({"ID": [1, 2, 3], "Name": ["A", "B", "C"]}).to_excel(path, index=False)
    handle, sheets = load_workbook_all_sheets(path)
    key = registry.add(handle, sheets)
    return registry, key


def test_replace_sheet_data_records_history(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)
    assert not registry.can_undo()

    new_df = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    registry.replace_sheet_data(key, "Sheet1", new_df, description="Removed 1 duplicate")

    assert registry.can_undo()
    assert not registry.can_redo()
    entries = registry.history_entries()
    assert len(entries) == 1
    assert entries[0].description == "Removed 1 duplicate"


def test_undo_restores_previous_dataframe(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)
    original = registry.get_dataframe(key, "Sheet1").copy()

    new_df = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    registry.replace_sheet_data(key, "Sheet1", new_df, description="Trim rows")

    entry = registry.undo()
    assert entry is not None
    assert entry.description == "Trim rows"

    restored = registry.get_dataframe(key, "Sheet1")
    assert len(restored) == len(original)
    assert not registry.can_undo()
    assert registry.can_redo()


def test_redo_reapplies_undone_change(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)

    new_df = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    registry.replace_sheet_data(key, "Sheet1", new_df, description="Trim rows")
    registry.undo()
    assert registry.can_redo()

    registry.redo()
    restored = registry.get_dataframe(key, "Sheet1")
    assert len(restored) == 2
    assert registry.can_undo()
    assert not registry.can_redo()


def test_new_edit_after_undo_clears_redo_stack(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)

    step1 = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    registry.replace_sheet_data(key, "Sheet1", step1, description="Step 1")
    registry.undo()
    assert registry.can_redo()

    step2 = pd.DataFrame({"ID": [1], "Name": ["A"]})
    registry.replace_sheet_data(key, "Sheet1", step2, description="Step 2")

    # A fresh edit after undo invalidates the redo branch, matching standard
    # editor undo/redo semantics.
    assert not registry.can_redo()


def test_multiple_undo_redo_cycle(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)

    df_a = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    df_b = pd.DataFrame({"ID": [1], "Name": ["A"]})
    registry.replace_sheet_data(key, "Sheet1", df_a, description="Step A")
    registry.replace_sheet_data(key, "Sheet1", df_b, description="Step B")

    assert len(registry.get_dataframe(key, "Sheet1")) == 1

    registry.undo()  # back to df_a state (2 rows)
    assert len(registry.get_dataframe(key, "Sheet1")) == 2

    registry.undo()  # back to original (3 rows)
    assert len(registry.get_dataframe(key, "Sheet1")) == 3
    assert not registry.can_undo()

    registry.redo()  # forward to df_a (2 rows)
    assert len(registry.get_dataframe(key, "Sheet1")) == 2

    registry.redo()  # forward to df_b (1 row)
    assert len(registry.get_dataframe(key, "Sheet1")) == 1
    assert not registry.can_redo()


def test_undo_on_empty_stack_returns_none(tmp_path: Path):
    registry, _key = _make_registry_with_file(tmp_path)
    assert registry.undo() is None
    assert registry.redo() is None


def test_history_signal_emitted(tmp_path: Path):
    registry, key = _make_registry_with_file(tmp_path)
    seen = []
    registry.history_changed.connect(lambda: seen.append(True))

    new_df = pd.DataFrame({"ID": [1], "Name": ["A"]})
    registry.replace_sheet_data(key, "Sheet1", new_df, description="Edit")
    assert len(seen) == 1

    registry.undo()
    assert len(seen) == 2


# -- Undo/Redo wired through a real plugin widget (not just the registry
# directly) -- catches integration issues between plugin apply-in-place
# code and the registry's history stack. --------------------------------


def test_duplicate_finder_apply_records_undoable_history(tmp_path: Path):
    import time

    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext
    from app.plugins.duplicate_finder import DuplicateFinderWidget

    app = QApplication.instance() or QApplication([])
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
    QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

    registry, key = _make_registry_with_file(tmp_path)
    # Overwrite with data that actually has a duplicate to remove.
    import pandas as pd

    dup_df = pd.DataFrame({"ID": [1, 1, 2], "Name": ["A", "A", "B"]})
    registry.replace_sheet_data(key, "Sheet1", dup_df, record_history=False)

    config = ConfigManager(config_path=tmp_path / "settings_dupfinder.yaml")
    ctx = PluginContext(config=config, registry=registry)
    widget = DuplicateFinderWidget(ctx)
    widget._picker.set_selected_file(key)
    widget._on_selection_changed()
    for i in range(widget._columns_list.count()):
        item = widget._columns_list.item(i)
        if item.text() == "ID":
            item.setSelected(True)

    widget._on_find_clicked()
    start = time.time()
    while time.time() - start < 8 and widget._last_report is None:
        app.processEvents()
        time.sleep(0.01)
    assert widget._last_report is not None

    widget._on_remove_clicked()
    assert len(registry.get_dataframe(key, "Sheet1")) == 2
    assert registry.can_undo()

    registry.undo()
    assert len(registry.get_dataframe(key, "Sheet1")) == 3
