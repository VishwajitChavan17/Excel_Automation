"""
tests/test_phase4_report_service.py
======================================
Headless tests for report_service: summary report generation in every
supported format (Excel/CSV/HTML/PDF) and the audit report. No Qt import
anywhere in this file; matplotlib is forced to the non-interactive "Agg"
backend inside report_service itself.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from app.services.excel import report_service
from app.services.excel.loader_service import load_workbook_all_sheets


@pytest.fixture
def sample_handle(tmp_path: Path):
    path = tmp_path / "sample.xlsx"
    pd.DataFrame(
        {"ID": [1, 2, None, 4], "Name": ["Alice", "Bob", "Bob", "Carol"], "Score": [10.5, 20.0, 20.0, None]}
    ).to_excel(path, index=False)
    handle, _sheets = load_workbook_all_sheets(path)
    return handle


def test_build_summary_table(sample_handle):
    table = report_service.build_summary_table(sample_handle)
    assert len(table) == 3  # ID, Name, Score
    assert set(table["Column"]) == {"ID", "Name", "Score"}


def test_build_file_metadata(sample_handle):
    metadata = report_service.build_file_metadata(sample_handle)
    assert metadata["File Name"] == "sample.xlsx"
    assert metadata["Row Count"] == 4
    assert metadata["Column Count"] == 3


def test_export_summary_excel(sample_handle, tmp_path: Path):
    out = report_service.export_summary_excel(sample_handle, tmp_path / "summary.xlsx")
    assert out.exists()
    xls = pd.ExcelFile(out)
    assert set(xls.sheet_names) == {"Summary", "Column Statistics"}


def test_export_summary_csv(sample_handle, tmp_path: Path):
    out = report_service.export_summary_csv(sample_handle, tmp_path / "summary.csv")
    assert out.exists()
    df = pd.read_csv(out)
    assert len(df) == 3


def test_export_summary_html(sample_handle, tmp_path: Path):
    out = report_service.export_summary_html(sample_handle, tmp_path / "summary.html")
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "sample.xlsx" in content
    assert "<table" in content


def test_export_summary_pdf(sample_handle, tmp_path: Path):
    out = report_service.export_summary_pdf(sample_handle, tmp_path / "summary.pdf")
    assert out.exists()
    assert out.stat().st_size > 0
    # PDF magic bytes
    assert out.read_bytes()[:4] == b"%PDF"


def test_export_summary_pdf_handles_empty_columns(tmp_path: Path):
    """A handle with zero column_profiles (e.g. a degenerate empty sheet)
    should still produce a valid PDF, not crash on an empty chart."""
    path = tmp_path / "empty.xlsx"
    pd.DataFrame().to_excel(path, index=False)
    handle, _sheets = load_workbook_all_sheets(path)
    out = report_service.export_summary_pdf(handle, tmp_path / "empty_summary.pdf")
    assert out.exists()


class _FakeHistoryEntry:
    def __init__(self, description, timestamp=None, file_key="f.xlsx", sheet_name="Sheet1"):
        self.description = description
        self.timestamp = timestamp or datetime.now()
        self.file_key = file_key
        self.sheet_name = sheet_name


def test_export_audit_report(tmp_path: Path):
    entries = [
        _FakeHistoryEntry("Removed 2 duplicate row(s)"),
        _FakeHistoryEntry("Applied Column Mapping"),
    ]
    out = report_service.export_audit_report(entries, tmp_path / "audit.xlsx")
    assert out.exists()
    df = pd.read_excel(out)
    assert len(df) == 2
    assert "Removed 2 duplicate row(s)" in df["Operation"].values
