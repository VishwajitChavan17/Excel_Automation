"""
tests/test_phase2_services.py
===============================
Headless tests for the Phase 2 business-logic services: duplicate_service,
compare_service, lookup_service. No Qt import anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.excel import compare_service, duplicate_service, lookup_service
from app.services.excel.loader_service import load_workbook_all_sheets, reprofile_for_sheet


# -- duplicate_service ------------------------------------------------------


def _dup_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "VIN": ["A1", "A1", "A2", "A3", "A3", "A3"],
            "Engine": ["E1", "E1", "E2", "E3", "E3", "E3"],
            "Score": [10, 20, 5, 1, 9, 3],
        }
    )


def test_find_duplicate_mask_keep_first():
    df = _dup_df()
    mask = duplicate_service.find_duplicate_mask(df, ["VIN", "Engine"], keep="first")
    assert mask.tolist() == [False, True, False, False, True, True]


def test_find_duplicate_mask_keep_last():
    df = _dup_df()
    mask = duplicate_service.find_duplicate_mask(df, ["VIN", "Engine"], keep="last")
    assert mask.tolist() == [True, False, False, True, True, False]


def test_find_duplicate_mask_keep_highest():
    df = _dup_df()
    mask = duplicate_service.find_duplicate_mask(df, ["VIN", "Engine"], keep="highest")
    # For VIN=A1: scores 10,20 -> keep 20 (index1), flag index0
    # For VIN=A3: scores 1,9,3 -> keep 9 (index4), flag index3,index5
    assert mask.tolist() == [True, False, False, True, False, True]


def test_find_duplicate_mask_missing_column_raises():
    df = _dup_df()
    with pytest.raises(ValueError):
        duplicate_service.find_duplicate_mask(df, ["NoSuchColumn"])


def test_build_duplicate_report():
    df = _dup_df()
    report = duplicate_service.build_duplicate_report(df, ["VIN", "Engine"], keep="first")
    assert report.total_rows == 6
    assert report.duplicate_row_count == 3
    assert report.keep_strategy == "first"


def test_remove_duplicates():
    df = _dup_df()
    cleaned = duplicate_service.remove_duplicates(df, ["VIN", "Engine"], keep="first")
    assert len(cleaned) == 3
    assert cleaned["VIN"].tolist() == ["A1", "A2", "A3"]


def test_export_duplicate_report(tmp_path: Path):
    df = _dup_df()
    report = duplicate_service.build_duplicate_report(df, ["VIN", "Engine"])
    out = duplicate_service.export_duplicate_report(df, report, tmp_path / "dup_report.xlsx")
    assert out.exists()
    result = pd.read_excel(out, sheet_name="Duplicate Rows")
    assert len(result) == report.duplicate_row_count


# -- compare_service ---------------------------------------------------------


def test_compare_workbooks_basic():
    master = pd.DataFrame(
        {"ID": [1, 2, 3], "Name": ["Alice", "Bob", "Carol"], "Dept": ["Eng", "Sales", "Eng"]}
    )
    second = pd.DataFrame(
        {"ID": [2, 3, 4], "Name": ["Bob", "Caroline", "Dave"], "Dept": ["Sales", "Eng", "HR"]}
    )

    result = compare_service.compare_workbooks(master, second, ["ID"])
    assert result.report.missing_in_second == 1  # ID 1 only in master
    assert result.report.new_in_second == 1  # ID 4 only in second
    assert result.report.matched_count == 2  # ID 2, 3
    assert result.report.modified_count == 1  # ID 3 Name changed Carol->Caroline


def test_compare_workbooks_requires_key_columns():
    master = pd.DataFrame({"ID": [1]})
    second = pd.DataFrame({"ID": [1]})
    with pytest.raises(ValueError):
        compare_service.compare_workbooks(master, second, [])


def test_compare_workbooks_missing_key_column_raises():
    master = pd.DataFrame({"ID": [1]})
    second = pd.DataFrame({"OtherID": [1]})
    with pytest.raises(ValueError):
        compare_service.compare_workbooks(master, second, ["ID"])


def test_export_comparison_report(tmp_path: Path):
    master = pd.DataFrame({"ID": [1, 2], "Val": ["a", "b"]})
    second = pd.DataFrame({"ID": [2, 3], "Val": ["b", "c"]})
    result = compare_service.compare_workbooks(master, second, ["ID"])
    out = compare_service.export_comparison_report(result, tmp_path / "compare_report.xlsx")
    assert out.exists()
    xls = pd.ExcelFile(out)
    assert set(xls.sheet_names) >= {"Missing In Second", "New In Second", "Modified", "Summary"}


# -- lookup_service -----------------------------------------------------------


def test_lookup_and_copy_basic():
    master = pd.DataFrame(
        {"SignalName": ["Sig1", "Sig2", "Sig3"], "Unit": ["V", "A", "Hz"], "Owner": ["X", "Y", "Z"]}
    )
    target = pd.DataFrame({"SignalName": ["Sig2", "Sig3", "Sig4"], "Unit": [None, None, None]})

    updated, report = lookup_service.lookup_and_copy(master, target, "SignalName", ["Unit"])
    assert report.matched_count == 2
    assert report.unmatched_count == 1
    assert updated.loc[updated["SignalName"] == "Sig2", "Unit"].iloc[0] == "A"
    assert updated.loc[updated["SignalName"] == "Sig3", "Unit"].iloc[0] == "Hz"


def test_lookup_and_copy_new_column():
    master = pd.DataFrame({"ID": [1, 2], "Category": ["X", "Y"]})
    target = pd.DataFrame({"ID": [1, 2, 3]})

    updated, report = lookup_service.lookup_and_copy(master, target, "ID", ["Category"])
    assert "Category" in updated.columns
    assert report.matched_count == 2
    assert report.unmatched_count == 1


def test_lookup_and_copy_missing_match_column_raises():
    master = pd.DataFrame({"ID": [1]})
    target = pd.DataFrame({"OtherID": [1]})
    with pytest.raises(ValueError):
        lookup_service.lookup_and_copy(master, target, "ID", [])


def test_export_updated_workbook(tmp_path: Path):
    df = pd.DataFrame({"A": [1, 2]})
    out = lookup_service.export_updated_workbook(df, tmp_path / "updated.xlsx")
    assert out.exists()


# -- multi-sheet loader ---------------------------------------------------


def test_load_workbook_all_sheets(tmp_path: Path):
    path = tmp_path / "multi.xlsx"
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"b": [3, 4, 5]}).to_excel(writer, sheet_name="Second", index=False)

    handle, sheets = load_workbook_all_sheets(path)
    assert set(sheets.keys()) == {"First", "Second"}
    assert handle.sheet_count == 2
    assert handle.active_sheet == "First"
    assert handle.row_count == 2

    reprofile_for_sheet(handle, sheets, "Second")
    assert handle.active_sheet == "Second"
    assert handle.row_count == 3


def test_workbook_handle_file_metadata(tmp_path: Path):
    path = tmp_path / "meta.csv"
    pd.DataFrame({"x": [1, 2, 3]}).to_csv(path, index=False)
    handle, sheets = load_workbook_all_sheets(path)
    assert handle.file_size_bytes > 0
    assert handle.last_modified is not None
    assert handle.file_size_display  # non-empty string
