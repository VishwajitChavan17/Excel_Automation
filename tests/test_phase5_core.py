"""
tests/test_phase5_core.py
============================
Headless tests for Phase 5 enterprise-hardening core modules: audit_log
(persistent SQLite audit trail), session_manager (session restore / crash
detection), and autosave_manager (in-memory-edit recovery snapshots). No
Qt import anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.core import audit_log, autosave_manager, session_manager


# -- audit_log --------------------------------------------------------------


def test_audit_log_creates_schema_and_logs(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    log.log("file.xlsx", "Sheet1", "Removed 2 duplicate row(s)")
    entries = log.query()
    assert len(entries) == 1
    assert entries[0].operation == "Removed 2 duplicate row(s)"


def test_audit_log_persists_across_reopen(tmp_path: Path):
    db_path = tmp_path / "audit.db"
    log1 = audit_log.AuditLog(db_path)
    log1.log("a.xlsx", "Sheet1", "Loaded file")

    log2 = audit_log.AuditLog(db_path)  # simulate app restart -- reopen same file
    entries = log2.query()
    assert len(entries) == 1
    assert entries[0].file_key == "a.xlsx"


def test_audit_log_query_most_recent_first(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    log.log("a.xlsx", "Sheet1", "First")
    log.log("a.xlsx", "Sheet1", "Second")
    entries = log.query()
    assert entries[0].operation == "Second"
    assert entries[1].operation == "First"


def test_audit_log_search_filters(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    log.log("master.xlsx", "Sheet1", "Removed duplicates")
    log.log("target.xlsx", "Sheet1", "Applied lookup")
    results = log.query(search="lookup")
    assert len(results) == 1
    assert results[0].file_key == "target.xlsx"


def test_audit_log_count(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    assert log.count() == 0
    log.log("a.xlsx", "Sheet1", "Op1")
    log.log("a.xlsx", "Sheet1", "Op2")
    assert log.count() == 2


def test_audit_log_clear(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    log.log("a.xlsx", "Sheet1", "Op1")
    log.clear()
    assert log.count() == 0


def test_audit_log_export_excel(tmp_path: Path):
    log = audit_log.AuditLog(tmp_path / "audit.db")
    log.log("a.xlsx", "Sheet1", "Op1")
    entries = log.query()
    out = audit_log.export_audit_log_excel(entries, tmp_path / "export.xlsx")
    assert out.exists()
    df = pd.read_excel(out)
    assert len(df) == 1


# -- session_manager ----------------------------------------------------


def test_save_and_load_session(tmp_path: Path):
    state = session_manager.SessionState(loaded_files=["a.xlsx", "b.xlsx"], clean_shutdown=True)
    path = session_manager.save_session(state, tmp_path / "session.json")
    assert path.exists()

    loaded = session_manager.load_session(path)
    assert loaded is not None
    assert loaded.loaded_files == ["a.xlsx", "b.xlsx"]
    assert loaded.clean_shutdown is True


def test_load_session_missing_file_returns_none(tmp_path: Path):
    assert session_manager.load_session(tmp_path / "nonexistent.json") is None


def test_load_session_corrupt_file_returns_none(tmp_path: Path):
    path = tmp_path / "session.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    assert session_manager.load_session(path) is None


def test_dirty_session_indicates_unclean_shutdown(tmp_path: Path):
    """The crash-detection mechanism: a session saved with
    clean_shutdown=False and never updated means the app never reached its
    own shutdown code."""
    state = session_manager.SessionState(loaded_files=["a.xlsx"], clean_shutdown=False)
    path = session_manager.save_session(state, tmp_path / "session.json")

    loaded = session_manager.load_session(path)
    assert loaded.clean_shutdown is False


def test_clear_session(tmp_path: Path):
    path = tmp_path / "session.json"
    session_manager.save_session(session_manager.SessionState(), path)
    assert path.exists()
    session_manager.clear_session(path)
    assert not path.exists()


def test_clear_session_missing_file_is_noop(tmp_path: Path):
    session_manager.clear_session(tmp_path / "nonexistent.json")  # should not raise


# -- autosave_manager -------------------------------------------------------


def test_snapshot_sheets_and_load_manifest(tmp_path: Path):
    df1 = pd.DataFrame({"ID": [1, 2]})
    df2 = pd.DataFrame({"Name": ["A", "B"]})
    sheets = [
        ("file1.xlsx", "Sheet1", "file1.xlsx", df1),
        ("file2.xlsx", "Sheet1", "file2.xlsx", df2),
    ]
    autosave_manager.snapshot_sheets(sheets, tmp_path)

    manifest = autosave_manager.load_manifest(tmp_path)
    assert len(manifest) == 2
    assert {e.file_key for e in manifest} == {"file1.xlsx", "file2.xlsx"}


def test_has_pending_autosave(tmp_path: Path):
    assert autosave_manager.has_pending_autosave(tmp_path) is False

    df = pd.DataFrame({"A": [1]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df)], tmp_path)
    assert autosave_manager.has_pending_autosave(tmp_path) is True


def test_load_snapshot_roundtrip(tmp_path: Path):
    df = pd.DataFrame({"ID": [1, 2, 3], "Name": ["A", "B", "C"]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df)], tmp_path)

    manifest = autosave_manager.load_manifest(tmp_path)
    restored = autosave_manager.load_snapshot(manifest[0], tmp_path)
    assert restored is not None
    pd.testing.assert_frame_equal(restored, df)


def test_load_snapshot_missing_file_returns_none(tmp_path: Path):
    entry = autosave_manager.AutosaveManifestEntry(
        file_key="f.xlsx", sheet_name="Sheet1", original_display_name="f.xlsx", pickle_filename="nope.pkl"
    )
    assert autosave_manager.load_snapshot(entry, tmp_path) is None


def test_clear_autosave(tmp_path: Path):
    df = pd.DataFrame({"A": [1]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df)], tmp_path)
    assert autosave_manager.has_pending_autosave(tmp_path) is True

    autosave_manager.clear_autosave(tmp_path)
    assert autosave_manager.has_pending_autosave(tmp_path) is False


def test_clear_autosave_missing_dir_is_noop(tmp_path: Path):
    autosave_manager.clear_autosave(tmp_path / "nonexistent")  # should not raise


def test_snapshot_overwrites_previous_snapshot(tmp_path: Path):
    df_v1 = pd.DataFrame({"ID": [1]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df_v1)], tmp_path)

    df_v2 = pd.DataFrame({"ID": [1, 2, 3]})
    autosave_manager.snapshot_sheets([("f.xlsx", "Sheet1", "f.xlsx", df_v2)], tmp_path)

    manifest = autosave_manager.load_manifest(tmp_path)
    restored = autosave_manager.load_snapshot(manifest[0], tmp_path)
    assert len(restored) == 3
