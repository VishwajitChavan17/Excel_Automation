"""
tests/test_phase5_gui_smoke.py
================================
Headless (QT_QPA_PLATFORM=offscreen) smoke tests for the Phase 5 UI layer:
crash recovery / session restore through the real MainWindow, and the
Settings plugin (Plugin Manager, Performance, Auto-Save & Session, Audit
Log tabs).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_app_root(tmp_path: Path, monkeypatch):
    """Point every app.core.paths.* accessor at an isolated temp directory
    so these tests never touch the real user config/logs/database."""
    from app.core import paths

    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    return tmp_path


def _build_main_window(qapp, isolated_app_root):
    from app.core.config_manager import ConfigManager
    from app.core.plugin_manager import PluginManager
    from app.core.workbook_registry import WorkbookRegistry
    from app.core import paths
    from app.ui.main_window import MainWindow

    config = ConfigManager(config_path=paths.config_dir() / "settings.yaml")
    registry = WorkbookRegistry()
    pm = PluginManager(config, registry)
    pm.discover_and_load()
    window = MainWindow(config, pm, registry)
    window.show()
    return window


def test_crash_recovery_restores_unsaved_autosave_data(qapp, isolated_app_root, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.core import autosave_manager, paths, session_manager

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    # Simulate a previous run that crashed mid-edit.
    f1 = isolated_app_root / "important.xlsx"
    pd.DataFrame({"ID": [1, 2, 3], "Name": ["A", "B", "C"]}).to_excel(f1, index=False)

    session_manager.save_session(
        session_manager.SessionState(loaded_files=[str(f1)], clean_shutdown=False),
        paths.session_file(),
    )
    edited_df = pd.DataFrame({"ID": [1, 2, 3, 4], "Name": ["A", "B", "C", "D-edited"]})
    autosave_manager.snapshot_sheets([(str(f1), "Sheet1", "important.xlsx", edited_df)], paths.autosave_dir())

    window = _build_main_window(qapp, isolated_app_root)
    window._check_startup_recovery()

    recovered = window._registry.get_dataframe(str(f1))
    assert recovered is not None
    assert len(recovered) == 4
    assert recovered.iloc[-1]["Name"] == "D-edited"


def test_clean_session_offers_restore_not_crash_recovery(qapp, isolated_app_root, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from app.core import paths, session_manager

    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    f1 = isolated_app_root / "clean.xlsx"
    pd.DataFrame({"ID": [1, 2]}).to_excel(f1, index=False)
    session_manager.save_session(
        session_manager.SessionState(loaded_files=[str(f1)], clean_shutdown=True),
        paths.session_file(),
    )

    window = _build_main_window(qapp, isolated_app_root)
    window._check_startup_recovery()

    import time

    start = time.time()
    while time.time() - start < 5:
        qapp.processEvents()
        time.sleep(0.01)
        if window._registry.keys():
            break

    assert str(f1) in window._registry.keys()


def test_closeevent_marks_session_clean_and_clears_autosave(qapp, isolated_app_root):
    from app.core import autosave_manager, paths, session_manager

    window = _build_main_window(qapp, isolated_app_root)

    df = pd.DataFrame({"A": [1]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df)], paths.autosave_dir())
    assert autosave_manager.has_pending_autosave(paths.autosave_dir())

    window.close()

    assert not autosave_manager.has_pending_autosave(paths.autosave_dir())
    final_session = session_manager.load_session(paths.session_file())
    assert final_session.clean_shutdown is True


def test_mutation_recorded_reaches_audit_log(qapp, isolated_app_root):
    window = _build_main_window(qapp, isolated_app_root)

    df = pd.DataFrame({"ID": [1, 1, 2]})
    from app.services.excel.loader_service import load_workbook_all_sheets

    f1 = isolated_app_root / "dupes.xlsx"
    df.to_excel(f1, index=False)
    handle, sheets = load_workbook_all_sheets(f1)
    key = window._registry.add(handle, sheets)

    window._registry.replace_sheet_data(key, "Sheet1", df.drop_duplicates(), description="Removed 1 duplicate row(s)")

    entries = window.audit_log.query()
    descriptions = [e.operation for e in entries]
    assert "Removed 1 duplicate row(s)" in descriptions


def test_settings_plugin_plugin_manager_tab(qapp, isolated_app_root):
    window = _build_main_window(qapp, isolated_app_root)
    widget = window.open_plugin_tab("settings.panel")
    plugin_tab = widget.widget(0)
    assert plugin_tab._plugins_table.rowCount() == len(window.plugin_manager.all_plugins())


def test_settings_plugin_performance_tab_updates_config(qapp, isolated_app_root):
    window = _build_main_window(qapp, isolated_app_root)
    widget = window.open_plugin_tab("settings.panel")
    perf_tab = widget.widget(1)
    perf_tab._threshold_spin.setValue(77777)
    assert window._config.get("performance.large_file_row_threshold") == 77777


def test_settings_plugin_autosave_tab_updates_timer(qapp, isolated_app_root):
    window = _build_main_window(qapp, isolated_app_root)
    widget = window.open_plugin_tab("settings.panel")
    autosave_tab = widget.widget(2)
    autosave_tab._interval_spin.setValue(45)
    assert window._autosave_timer.interval() == 45_000


def test_settings_plugin_audit_log_tab_shows_entries(qapp, isolated_app_root):
    window = _build_main_window(qapp, isolated_app_root)
    window.audit_log.log("a.xlsx", "Sheet1", "Test operation")

    widget = window.open_plugin_tab("settings.panel")
    audit_tab = widget.widget(3)
    assert audit_tab._table.rowCount() == 1
