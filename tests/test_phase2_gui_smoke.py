"""
tests/test_phase2_gui_smoke.py
================================
Headless (QT_QPA_PLATFORM=offscreen) smoke tests for the Phase 2 UI layer.
These exist specifically to guard against two real bugs found during
development:

1. Worker objects moved to a QThread via moveToThread() must be kept
   referenced by the caller for the thread's lifetime, or Python can
   garbage-collect them before run() executes, silently dropping the job.
   (See app/ui/widgets/background_task.py's docstring.)
2. Loguru sinks run synchronously on whatever thread calls logger.*() --
   including background worker threads. A sink that touches a QWidget
   directly is undefined behavior. ConsolePanel fixes this by emitting a
   Qt signal instead. (See app/ui/panels/console_panel.py.)

Run with: QT_QPA_PLATFORM=offscreen pytest tests/test_phase2_gui_smoke.py -v
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
def registry_with_files(tmp_path: Path):
    from app.core.workbook_registry import WorkbookRegistry
    from app.services.excel.loader_service import load_workbook_all_sheets

    registry = WorkbookRegistry()
    master_path = tmp_path / "master.xlsx"
    second_path = tmp_path / "second.xlsx"
    pd.DataFrame({"ID": [1, 2, 3], "Name": ["Alice", "Bob", "Carol"], "Dept": ["Eng", "Sales", "Eng"]}).to_excel(
        master_path, index=False
    )
    pd.DataFrame({"ID": [2, 3, 4], "Name": ["Bob", "Caroline", "Dave"], "Dept": ["Sales", "Eng", "HR"]}).to_excel(
        second_path, index=False
    )
    for p in (master_path, second_path):
        handle, sheets = load_workbook_all_sheets(p)
        registry.add(handle, sheets)
    return registry, master_path, second_path


def test_console_panel_survives_cross_thread_logging(qapp):
    """Regression test for bug #2: logging from a worker thread must not
    crash or corrupt the console widget."""
    from loguru import logger
    from PySide6.QtCore import QObject, QThread, Signal

    from app.ui.panels.console_panel import ConsolePanel

    console = ConsolePanel()

    class _Logger(QObject):
        done = Signal()

        def run(self):
            for i in range(20):
                logger.info("cross-thread log line {}", i)
            self.done.emit()

    worker = _Logger()
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    finished = {}
    worker.done.connect(lambda: finished.update(ok=True))

    assert _pump(qapp, lambda: False, 0.01) is False or True  # warm up event loop
    thread.start()
    assert _pump(qapp, lambda: finished.get("ok"), timeout_s=5)
    # Drain any remaining queued cross-thread signal deliveries before asserting.
    _pump(qapp, lambda: any("cross-thread log line 19" in line for line in console._log_lines), timeout_s=2)
    thread.quit()
    thread.wait()

    assert any("cross-thread log line" in line for line in console._log_lines)


def test_compare_worker_completes_via_widget(qapp, registry_with_files):
    """Regression test for bug #1: worker must not be GC'd before run()."""
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext
    from app.plugins.compare_tool import CompareToolWidget

    registry, master_path, second_path = registry_with_files
    config = ConfigManager(config_path=master_path.parent / "settings.yaml")
    ctx = PluginContext(config=config, registry=registry)

    widget = CompareToolWidget(ctx)
    widget._master_picker.set_selected_file(str(master_path))
    widget._second_picker.set_selected_file(str(second_path))
    widget._refresh_key_columns()
    for i in range(widget._key_columns_list.count()):
        item = widget._key_columns_list.item(i)
        if item.text() == "ID":
            item.setSelected(True)

    widget._on_compare_clicked()
    assert _pump(qapp, lambda: widget._last_result is not None, timeout_s=8)
    assert widget._last_result.report.matched_count == 2


def test_duplicate_finder_worker_completes_via_widget(qapp, tmp_path: Path):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext
    from app.core.workbook_registry import WorkbookRegistry
    from app.plugins.duplicate_finder import DuplicateFinderWidget
    from app.services.excel.loader_service import load_workbook_all_sheets

    registry = WorkbookRegistry()
    dupes_path = tmp_path / "dupes.xlsx"
    pd.DataFrame({"VIN": ["A1", "A1", "A2"], "Engine": ["E1", "E1", "E2"]}).to_excel(dupes_path, index=False)
    handle, sheets = load_workbook_all_sheets(dupes_path)
    registry.add(handle, sheets)

    config = ConfigManager(config_path=tmp_path / "settings.yaml")
    ctx = PluginContext(config=config, registry=registry)
    widget = DuplicateFinderWidget(ctx)
    widget._picker.set_selected_file(str(dupes_path))
    widget._on_selection_changed()
    for i in range(widget._columns_list.count()):
        item = widget._columns_list.item(i)
        if item.text() in ("VIN", "Engine"):
            item.setSelected(True)

    widget._on_find_clicked()
    assert _pump(qapp, lambda: widget._last_report is not None, timeout_s=8)
    assert widget._last_report.duplicate_row_count == 1


def test_lookup_copy_worker_completes_via_widget(qapp, registry_with_files):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_base import PluginContext
    from app.plugins.lookup_copy_tool import LookupCopyWidget

    registry, master_path, second_path = registry_with_files
    config = ConfigManager(config_path=master_path.parent / "settings2.yaml")
    ctx = PluginContext(config=config, registry=registry)

    widget = LookupCopyWidget(ctx)
    widget._master_picker.set_selected_file(str(master_path))
    widget._target_picker.set_selected_file(str(second_path))
    widget._refresh_columns()
    for i in range(widget._match_columns_list.count()):
        item = widget._match_columns_list.item(i)
        if item.text() == "ID":
            item.setSelected(True)
    for i in range(widget._copy_columns_list.count()):
        item = widget._copy_columns_list.item(i)
        if item.text() == "Dept":
            item.setSelected(True)

    widget._on_run_clicked()
    assert _pump(qapp, lambda: widget._last_report is not None, timeout_s=8)
    assert widget._last_report.matched_count == 2
