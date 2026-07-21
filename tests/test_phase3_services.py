"""
tests/test_phase3_services.py
===============================
Headless tests for the Phase 3 business-logic services: merge_service,
validation_service, column_mapper_service, plus the composite-key
extension to lookup_service. No Qt import anywhere in this file.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.services.excel import column_mapper_service, lookup_service, merge_service, validation_service
from app.services.excel.models import ColumnMapping, ValidationRule


# -- merge_service: union -----------------------------------------------


def test_union_merge_basic():
    a = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    b = pd.DataFrame({"ID": [3], "Name": ["C"], "Extra": ["x"]})
    result, report = merge_service.union_merge([a, b], ["a.xlsx", "b.xlsx"])
    assert len(result) == 3
    assert "Source File" in result.columns
    assert report.mode == "union"
    assert report.result_row_count == 3


def test_union_merge_requires_frames():
    with pytest.raises(ValueError):
        merge_service.union_merge([], [])


def test_union_merge_length_mismatch_raises():
    a = pd.DataFrame({"ID": [1]})
    with pytest.raises(ValueError):
        merge_service.union_merge([a], ["a.xlsx", "b.xlsx"])


# -- merge_service: joins -------------------------------------------------


@pytest.mark.parametrize(
    "mode,expected_rows",
    [("inner", 1), ("left", 2), ("right", 2), ("outer", 3)],
)
def test_join_merge_modes(mode, expected_rows):
    left = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    right = pd.DataFrame({"ID": [2, 3], "Dept": ["Eng", "Sales"]})
    result, report = merge_service.join_merge(left, right, ["ID"], mode)
    assert len(result) == expected_rows
    assert report.mode == mode


def test_join_merge_missing_key_raises():
    left = pd.DataFrame({"ID": [1]})
    right = pd.DataFrame({"OtherID": [1]})
    with pytest.raises(ValueError):
        merge_service.join_merge(left, right, ["ID"], "inner")


def test_join_merge_invalid_mode_raises():
    left = pd.DataFrame({"ID": [1]})
    right = pd.DataFrame({"ID": [1]})
    with pytest.raises(ValueError):
        merge_service.join_merge(left, right, ["ID"], "cross")


# -- merge_service: consolidation ------------------------------------------


def test_consolidate_groups_by_identical_headers():
    df_a = pd.DataFrame({"Signal": ["S1"], "Unit": ["V"]})
    df_b = pd.DataFrame({"Signal": ["S2"], "Unit": ["A"]})
    df_mismatch = pd.DataFrame({"Different": [1]})

    sources = [
        ("file_a.xlsx", "Sheet1", df_a),
        ("file_b.xlsx", "Sheet1", df_b),
        ("file_c.xlsx", "Sheet1", df_mismatch),
    ]
    consolidated, report = merge_service.consolidate(sources)

    assert report.consolidated_source_count == 2
    assert report.mismatched_source_count == 1
    assert len(consolidated) == 2
    assert merge_service.SOURCE_FILE_COL in consolidated.columns
    assert merge_service.SOURCE_SHEET_COL in consolidated.columns
    assert merge_service.IMPORT_TIMESTAMP_COL in consolidated.columns
    assert len(report.groups) == 2  # one group of 2 matching, one group of 1 mismatched


def test_consolidate_requires_sources():
    with pytest.raises(ValueError):
        merge_service.consolidate([])


def test_export_merge_result(tmp_path: Path):
    df = pd.DataFrame({"A": [1, 2]})
    out = merge_service.export_result(df, tmp_path / "merged.xlsx")
    assert out.exists()


# -- validation_service ----------------------------------------------------


def test_validation_required_rule():
    df = pd.DataFrame({"ID": [1, None, 3]})
    rules = [ValidationRule(rule_type="required", column="ID")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 1
    assert report.issues[0].row_index == 1


def test_validation_unique_rule():
    df = pd.DataFrame({"ID": [1, 1, 2]})
    rules = [ValidationRule(rule_type="unique", column="ID")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 2  # both rows sharing the duplicate value


def test_validation_regex_rule():
    df = pd.DataFrame({"Code": ["AB123", "bad", "CD456"]})
    rules = [ValidationRule(rule_type="regex", column="Code", parameter=r"^[A-Z]{2}\d{3}$")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 1
    assert report.issues[0].row_index == 1


def test_validation_dtype_numeric_rule():
    df = pd.DataFrame({"Qty": ["10", "abc", "5"]})
    rules = [ValidationRule(rule_type="dtype_numeric", column="Qty")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 1


def test_validation_dtype_date_rule():
    df = pd.DataFrame({"Date": ["2024-01-01", "not-a-date"]})
    rules = [ValidationRule(rule_type="dtype_date", column="Date")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 1


def test_validation_no_negative_rule():
    df = pd.DataFrame({"Balance": [10, -5, 0]})
    rules = [ValidationRule(rule_type="no_negative", column="Balance")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 1
    assert report.issues[0].row_index == 1


def test_validation_custom_expression_rule():
    df = pd.DataFrame({"Qty": [10, 0, 5], "Price": [1, 2, -1]})
    rules = [ValidationRule(rule_type="custom_expression", column=None, parameter="Qty > 0 and Price >= 0")]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 2  # row 1 (Qty=0) and row 2 (Price=-1)


def test_validation_multiple_rules_combined():
    df = pd.DataFrame({"ID": [1, None], "Qty": ["10", "x"]})
    rules = [
        ValidationRule(rule_type="required", column="ID"),
        ValidationRule(rule_type="dtype_numeric", column="Qty"),
    ]
    report = validation_service.run_validation(df, rules)
    assert report.issue_count == 2


def test_validation_requires_rules():
    df = pd.DataFrame({"ID": [1]})
    with pytest.raises(ValueError):
        validation_service.run_validation(df, [])


def test_validation_unknown_column_raises():
    df = pd.DataFrame({"ID": [1]})
    rules = [ValidationRule(rule_type="required", column="NoSuchColumn")]
    with pytest.raises(ValueError):
        validation_service.run_validation(df, rules)


def test_export_validation_report(tmp_path: Path):
    df = pd.DataFrame({"ID": [1, None]})
    rules = [ValidationRule(rule_type="required", column="ID")]
    report = validation_service.run_validation(df, rules)
    out = validation_service.export_validation_report(df, report, tmp_path / "validation.xlsx")
    assert out.exists()
    xls = pd.ExcelFile(out)
    assert set(xls.sheet_names) >= {"Summary", "Issues"}


# -- column_mapper_service ------------------------------------------------


def test_apply_mapping_basic():
    df = pd.DataFrame({"SignalName": ["S1"], "Unit": ["V"], "Owner": ["X"]})
    mappings = [ColumnMapping("SignalName", "Signal"), ColumnMapping("Unit", "Engineering Unit")]
    result = column_mapper_service.apply_mapping(df, mappings)
    assert list(result.columns) == ["Signal", "Engineering Unit"]
    assert "Owner" not in result.columns


def test_apply_mapping_keep_unmapped():
    df = pd.DataFrame({"A": [1], "B": [2], "C": [3]})
    mappings = [ColumnMapping("A", "Alpha")]
    result = column_mapper_service.apply_mapping(df, mappings, keep_unmapped=True)
    assert set(result.columns) == {"Alpha", "B", "C"}


def test_apply_mapping_missing_source_raises():
    df = pd.DataFrame({"A": [1]})
    mappings = [ColumnMapping("NoSuchCol", "X")]
    with pytest.raises(ValueError):
        column_mapper_service.apply_mapping(df, mappings)


def test_apply_mapping_requires_mappings():
    df = pd.DataFrame({"A": [1]})
    with pytest.raises(ValueError):
        column_mapper_service.apply_mapping(df, [])


def test_auto_map_identical_names():
    source = ["SignalName", "Unit", "Extra"]
    dest = ["SignalName", "Unit", "Other"]
    mappings = column_mapper_service.auto_map_identical_names(source, dest)
    assert len(mappings) == 2
    assert {(m.source_column, m.destination_column) for m in mappings} == {
        ("SignalName", "SignalName"),
        ("Unit", "Unit"),
    }


def test_save_and_load_mapping_template(tmp_path: Path):
    mappings = [ColumnMapping("A", "Alpha"), ColumnMapping("B", "Beta")]
    path = column_mapper_service.save_mapping_template("My Mapping", mappings, tmp_path)
    assert path.exists()

    loaded = column_mapper_service.load_mapping_template(path)
    assert len(loaded) == 2
    assert loaded[0].source_column == "A"
    assert loaded[0].destination_column == "Alpha"


def test_list_mapping_templates(tmp_path: Path):
    column_mapper_service.save_mapping_template("Template One", [ColumnMapping("A", "B")], tmp_path)
    column_mapper_service.save_mapping_template("Template Two", [ColumnMapping("C", "D")], tmp_path)
    templates = column_mapper_service.list_mapping_templates(tmp_path)
    assert len(templates) == 2


def test_list_mapping_templates_missing_dir(tmp_path: Path):
    templates = column_mapper_service.list_mapping_templates(tmp_path / "nonexistent")
    assert templates == []


# -- composite-key lookup (Multi Column Matching) --------------------------


def test_lookup_composite_key_two_columns():
    master = pd.DataFrame(
        {"VIN": ["V1", "V1", "V2"], "Engine": ["E1", "E2", "E1"], "Owner": ["Alice", "Bob", "Carol"]}
    )
    target = pd.DataFrame({"VIN": ["V1", "V1", "V2"], "Engine": ["E1", "E2", "E9"]})

    updated, report = lookup_service.lookup_and_copy(master, target, ["VIN", "Engine"], ["Owner"])
    assert report.matched_count == 2
    assert report.unmatched_count == 1
    assert report.match_column == "VIN + Engine"
    assert updated.loc[0, "Owner"] == "Alice"
    assert updated.loc[1, "Owner"] == "Bob"


def test_lookup_single_column_still_works_as_string():
    """Backward compatibility: passing a plain string still works exactly
    as before the composite-key extension."""
    master = pd.DataFrame({"ID": [1, 2], "Name": ["A", "B"]})
    target = pd.DataFrame({"ID": [1, 3]})
    updated, report = lookup_service.lookup_and_copy(master, target, "ID", ["Name"])
    assert report.match_column == "ID"
    assert report.matched_count == 1


# -- validation rule-set templates (Phase 4 addition, tested here since it
# extends validation_service from Phase 3) --------------------------------


def test_save_and_load_validation_template(tmp_path: Path):
    from app.services.excel import validation_service

    rules = [
        ValidationRule(rule_type="required", column="ID"),
        ValidationRule(rule_type="regex", column="Code", parameter=r"^[A-Z]{2}\d{3}$"),
    ]
    path = validation_service.save_validation_template("My Rules", rules, tmp_path)
    assert path.exists()

    loaded = validation_service.load_validation_template(path)
    assert len(loaded) == 2
    assert loaded[0].rule_type == "required"
    assert loaded[1].parameter == r"^[A-Z]{2}\d{3}$"


def test_list_validation_templates(tmp_path: Path):
    from app.services.excel import validation_service

    rules = [ValidationRule(rule_type="required", column="ID")]
    validation_service.save_validation_template("Set One", rules, tmp_path)
    validation_service.save_validation_template("Set Two", rules, tmp_path)
    assert len(validation_service.list_validation_templates(tmp_path)) == 2


def test_list_validation_templates_missing_dir(tmp_path: Path):
    from app.services.excel import validation_service

    assert validation_service.list_validation_templates(tmp_path / "nope") == []
