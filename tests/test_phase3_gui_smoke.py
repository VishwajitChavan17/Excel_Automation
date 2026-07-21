"""
tests/test_phase3_gui_smoke.py
================================
Headless (QT_QPA_PLATFORM=offscreen) smoke tests for the Phase 3 UI layer:
Merge Files (union + join), Consolidate Files, Validation Rules, and
Column Mapper. Follows the same pattern as test_phase2_gui_smoke.py --
plugin widgets are built against a bare WorkbookRegistry, no MainWindow
required, and background workers are driven end-to-end.
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _pump(app, condition, timeout_s: float = 8.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        app.processEvents()
        time.sleep(0.01)
        if condition():
            return True
    return False


@pytest.fixture
def registry_with_three_files(tmp_path: Path):
    from app.core.workbook_registry import WorkbookRegistry
    from app.services.excel.loader_service import load_workbook_all_sheets

    registry = WorkbookRegistry()
    f1 = tmp_path / "f1.xlsx"
    f2 = tmp_path / "f2.xlsx"
    f3 = tmp_path / "f3.xlsx"
    pd.DataFrame({"ID": [1, 2, 3], "Name": ["Alice", "Bob", "Carol"], "Dept": ["Eng", "Sales", "Eng"]}).to_excel(
        f1, index=False
    )
    pd.DataFrame({"ID": [2, 3, 4], "Name": ["Bob", "Caroline", "Dave"], "Dept": ["Sales", "Eng", "HR"]}).to_excel(
        f2, index=False
    )
    pd.DataFrame({"ID": [5, 6], "Name": ["Eve", "Frank"], "Dept": ["HR", "Eng"]}).to_excel(f3, index=False)
    for p in (f1, f2, f3):
        handle, sheets = load_workbook_all_sheets(p)
        registry.add(handle, sheets)
    return registry, f1, f2, f3


def _make_context(registry, tmp_path, settings_name="settings.yaml"):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext

    config = ConfigManager(config_path=tmp_path / settings_name)
    return PluginContext(config=config, registry=registry)


def test_union_merge_via_widget(qapp, registry_with_three_files, tmp_path):
    from app.plugins.merge_tool import MergeFilesTab

    registry, f1, f2, _f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s1.yaml")

    tab = MergeFilesTab(ctx)
    tab._first_picker.set_selected_file(str(f1))
    tab._second_picker.set_selected_file(str(f2))
    tab._on_merge_clicked()

    assert _pump(qapp, lambda: tab._last_report is not None)
    assert tab._last_report.mode == "union"
    assert tab._last_report.result_row_count == 6


def test_inner_join_via_widget(qapp, registry_with_three_files, tmp_path):
    from app.plugins.merge_tool import MergeFilesTab

    registry, f1, f2, _f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s2.yaml")

    tab = MergeFilesTab(ctx)
    tab._first_picker.set_selected_file(str(f1))
    tab._second_picker.set_selected_file(str(f2))
    idx = tab._mode_combo.findData("inner")
    tab._mode_combo.setCurrentIndex(idx)
    tab._refresh_key_columns()
    for i in range(tab._key_columns_list.count()):
        item = tab._key_columns_list.item(i)
        if item.text() == "ID":
            item.setSelected(True)
    tab._on_merge_clicked()

    assert _pump(qapp, lambda: tab._last_report is not None)
    assert tab._last_report.mode == "inner"
    assert tab._last_report.result_row_count == 2  # IDs 2 and 3


def test_consolidate_via_widget(qapp, registry_with_three_files, tmp_path):
    from app.plugins.merge_tool import ConsolidateFilesTab

    registry, f1, f2, f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s3.yaml")

    tab = ConsolidateFilesTab(ctx)
    for i in range(tab._files_list.count()):
        tab._files_list.item(i).setSelected(True)
    tab._on_consolidate_clicked()

    assert _pump(qapp, lambda: tab._last_report is not None)
    assert tab._last_report.consolidated_source_count == 3
    assert tab._last_report.consolidated_row_count == 8  # 3 + 3 + 2


def test_validation_via_widget(qapp, registry_with_three_files, tmp_path):
    from app.plugins.validation_tool import ValidationToolWidget

    registry, f1, _f2, _f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s4.yaml")

    widget = ValidationToolWidget(ctx)
    widget._picker.set_selected_file(str(f1))
    widget._on_selection_changed()

    idx = widget._rule_type_combo.findData("required")
    widget._rule_type_combo.setCurrentIndex(idx)
    widget._on_rule_type_changed()
    col_idx = widget._column_combo.findText("Name")
    widget._column_combo.setCurrentIndex(col_idx)
    widget._on_add_rule_clicked()
    assert len(widget._rules) == 1

    widget._on_run_clicked()
    assert _pump(qapp, lambda: widget._last_report is not None)
    assert widget._last_report.issue_count == 0  # Name has no blanks in this fixture


def test_column_mapper_via_widget(qapp, registry_with_three_files, tmp_path):
    from app.plugins.column_mapper_tool import ColumnMapperWidget

    registry, f1, _f2, _f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s5.yaml")

    widget = ColumnMapperWidget(ctx)
    widget._source_picker.set_selected_file(str(f1))
    widget._on_auto_map_clicked()
    assert widget._mapping_table.rowCount() == 3  # ID, Name, Dept all self-map

    widget._on_apply_clicked()
    assert widget._last_mapped_df is not None
    assert list(widget._last_mapped_df.columns) == ["ID", "Name", "Dept"]


def test_column_mapper_save_and_load_template(qapp, registry_with_three_files, tmp_path, monkeypatch):
    from app.core import paths
    from app.plugins.column_mapper_tool import ColumnMapperWidget
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    registry, f1, _f2, _f3 = registry_with_three_files
    ctx = _make_context(registry, tmp_path, "s6.yaml")

    template_dir = tmp_path / "templates"
    monkeypatch.setattr(paths, "templates_dir", lambda: template_dir)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("MyMapping", True)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))

    widget = ColumnMapperWidget(ctx)
    widget._source_picker.set_selected_file(str(f1))
    widget._on_auto_map_clicked()
    widget._on_save_template_clicked()

    assert (template_dir / "MyMapping.json").exists()

    widget._mapping_table.setRowCount(0)
    widget._refresh_templates()
    idx = widget._template_combo.findText("MyMapping")
    assert idx >= 0
    widget._template_combo.setCurrentIndex(idx)
    widget._on_load_template_clicked()
    assert widget._mapping_table.rowCount() == 3
