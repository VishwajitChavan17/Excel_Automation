"""
tests/test_phase4_gui_smoke.py
================================
Headless (QT_QPA_PLATFORM=offscreen) smoke tests for the Phase 4 UI layer:
Workflow Recorder (batch run + apply), Report Generator, Template Manager.

test_workflow_batch_run_and_apply_via_widget is a regression test for a
real bug found during development: declaring a worker Signal with a `dict`
argument type causes PySide6 to fail converting the payload at emit time
("Cannot copy-convert ... (dict) to C++"), silently corrupting the
result -- the fix was declaring the signal as `Signal(object, object)`
instead. See app/workers/workflow_worker.py.
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


def _make_context(registry, tmp_path, settings_name="settings.yaml"):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext

    config = ConfigManager(config_path=tmp_path / settings_name)
    return PluginContext(config=config, registry=registry)


@pytest.fixture
def registry_with_dupes(tmp_path: Path):
    from app.core.workbook_registry import WorkbookRegistry
    from app.services.excel.loader_service import load_workbook_all_sheets

    registry = WorkbookRegistry()
    f1 = tmp_path / "f1.xlsx"
    f2 = tmp_path / "f2.xlsx"
    pd.DataFrame({"VIN": ["A1", "A1", "A2"], "Engine": ["E1", "E1", "E2"]}).to_excel(f1, index=False)
    pd.DataFrame({"VIN": ["B1", "B1", "B2", "B2"], "Engine": ["E1", "E1", "E2", "E2"]}).to_excel(f2, index=False)
    for p in (f1, f2):
        handle, sheets = load_workbook_all_sheets(p)
        registry.add(handle, sheets)
    return registry, f1, f2


def test_workflow_batch_run_and_apply_via_widget(qapp, registry_with_dupes, tmp_path, monkeypatch):
    """Regression test for the Signal(dict) -> Signal(object, object) bug:
    build a one-step workflow, run it against two loaded files, and verify
    the resulting per-source DataFrames actually arrive intact and can be
    applied back to the registry."""
    from app.core import paths
    from app.plugins.workflow_recorder_tool import WorkflowRecorderWidget
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    registry, f1, f2 = registry_with_dupes
    ctx = _make_context(registry, tmp_path, "s1.yaml")
    monkeypatch.setattr(paths, "workflows_dir", lambda: tmp_path / "workflows")
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("wf1", True)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))

    widget = WorkflowRecorderWidget(ctx)
    widget._sample_picker.set_selected_file(str(f1))
    widget._refresh_column_widgets()

    idx = widget._step_type_combo.findData("remove_duplicates")
    widget._step_type_combo.setCurrentIndex(idx)
    widget._on_step_type_changed()
    for i in range(widget._dup_columns_list.count()):
        widget._dup_columns_list.item(i).setSelected(True)
    widget._on_add_step_clicked()
    assert len(widget._steps) == 1

    for i in range(widget._target_files_list.count()):
        widget._target_files_list.item(i).setSelected(True)
    widget._on_run_clicked()

    assert _pump(qapp, lambda: widget._last_results is not None)
    assert len(widget._last_results) == 2
    results_by_label = {r.source_label: r for r in widget._last_results}
    assert results_by_label["f1.xlsx"].row_count_after == 2
    assert results_by_label["f2.xlsx"].row_count_after == 2

    # This is the specific assertion that would fail under the dict-signal bug:
    # result_frames arrived as a corrupted/empty payload.
    assert len(widget._last_result_frames) == 2

    widget._on_apply_clicked()
    assert len(registry.get_dataframe(str(f1))) == 2
    assert len(registry.get_dataframe(str(f2))) == 2


def test_workflow_save_and_load_via_widget(qapp, registry_with_dupes, tmp_path, monkeypatch):
    from app.core import paths
    from app.plugins.workflow_recorder_tool import WorkflowRecorderWidget
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    registry, f1, _f2 = registry_with_dupes
    ctx = _make_context(registry, tmp_path, "s2.yaml")
    workflows_dir = tmp_path / "workflows2"
    monkeypatch.setattr(paths, "workflows_dir", lambda: workflows_dir)
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: ("MyWorkflow", True)))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))

    widget = WorkflowRecorderWidget(ctx)
    widget._sample_picker.set_selected_file(str(f1))
    widget._refresh_column_widgets()
    idx = widget._step_type_combo.findData("remove_duplicates")
    widget._step_type_combo.setCurrentIndex(idx)
    widget._on_step_type_changed()
    for i in range(widget._dup_columns_list.count()):
        widget._dup_columns_list.item(i).setSelected(True)
    widget._on_add_step_clicked()
    widget._on_save_workflow_clicked()

    assert (workflows_dir / "MyWorkflow.json").exists()

    widget._steps.clear()
    widget._steps_list.clear()
    widget._refresh_workflows()
    idx = widget._workflow_combo.findText("MyWorkflow")
    assert idx >= 0
    widget._workflow_combo.setCurrentIndex(idx)
    widget._on_load_workflow_clicked()
    assert len(widget._steps) == 1


def test_report_generator_via_widget(qapp, registry_with_dupes, tmp_path):
    from app.plugins.report_generator_tool import ReportGeneratorWidget

    registry, f1, _f2 = registry_with_dupes
    ctx = _make_context(registry, tmp_path, "s3.yaml")

    widget = ReportGeneratorWidget(ctx)
    widget._picker.set_selected_file(str(f1))
    widget._html_checkbox.setChecked(True)
    widget._on_generate_clicked()

    assert _pump(qapp, lambda: widget._generated_list.count() > 0)
    assert widget._generated_list.count() == 2  # excel (default checked) + html


def test_template_manager_lists_saved_templates(qapp, registry_with_dupes, tmp_path, monkeypatch):
    from app.core import paths
    from app.plugins.column_mapper_tool import ColumnMapperWidget
    from app.plugins.template_manager_tool import TemplateManagerWidget
    from app.services.excel import column_mapper_service

    registry, f1, _f2 = registry_with_dupes
    templates_dir = tmp_path / "templates"
    monkeypatch.setattr(paths, "templates_dir", lambda: templates_dir)

    ctx1 = _make_context(registry, tmp_path, "s4.yaml")
    mapper = ColumnMapperWidget(ctx1)
    mapper._source_picker.set_selected_file(str(f1))
    mapper._on_auto_map_clicked()
    mappings = mapper._collect_mappings()
    column_mapper_service.save_mapping_template("TestMapping", mappings, templates_dir)

    ctx2 = _make_context(registry, tmp_path, "s5.yaml")
    manager = TemplateManagerWidget(ctx2)
    assert manager._mapping_list.count() == 1
