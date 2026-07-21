"""
app.services.excel.compare_service
=====================================
Pure business logic for the Compare Excel tool: given a master DataFrame,
a second DataFrame, and one or more key columns, classify every row as
matched / missing-in-second / new-in-second, detect modified values on
matched rows, and export a highlighted Excel comparison report.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import CompareReport


@dataclass
class RowDiff:
    key: tuple
    status: str  # "modified"
    changed_columns: list[str] = field(default_factory=list)


@dataclass
class ComparisonResult:
    report: CompareReport
    missing_in_second: pd.DataFrame  # rows in master, absent from second
    new_in_second: pd.DataFrame  # rows in second, absent from master
    modified: pd.DataFrame  # matched rows where at least one non-key value differs
    modified_diffs: list[RowDiff]


def _validate_keys(master: pd.DataFrame, second: pd.DataFrame, key_columns: list[str]) -> None:
    if not key_columns:
        raise ValueError("At least one key column is required to compare workbooks.")
    for name, df in (("master", master), ("second", second)):
        missing = [c for c in key_columns if c not in df.columns]
        if missing:
            raise ValueError(f"Key column(s) {missing} not found in {name} file.")


def compare_workbooks(
    master: pd.DataFrame,
    second: pd.DataFrame,
    key_columns: list[str],
    *,
    master_label: str = "master.xlsx",
    second_label: str = "second.xlsx",
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
) -> ComparisonResult:
    _validate_keys(master, second, key_columns)

    m = master.copy()
    s = second.copy()

    def _normalize(df: pd.DataFrame) -> pd.DataFrame:
        for col in key_columns:
            series = df[col].fillna("__NULL__").astype(str)
            if ignore_whitespace:
                series = series.str.strip()
            if ignore_case:
                series = series.str.lower()
            df[f"__key__{col}"] = series
        return df

    m = _normalize(m)
    s = _normalize(s)
    key_cols_norm = [f"__key__{c}" for c in key_columns]

    merged = m.merge(
        s,
        on=key_cols_norm,
        how="outer",
        suffixes=("_master", "_second"),
        indicator=True,
    )

    missing_in_second = merged[merged["_merge"] == "left_only"]
    new_in_second = merged[merged["_merge"] == "right_only"]
    both = merged[merged["_merge"] == "both"]

    # Determine which non-key columns exist on both sides to diff.
    shared_value_columns = [
        c for c in master.columns if c not in key_columns and c in second.columns
    ]

    # Compute each column's diff mask ONCE (vectorized). The naive version of
    # this function recomputed str(a) != str(b) per cell inside a Python
    # row-loop below, which dominated runtime on large modified sets (~14s
    # for 150k modified rows on a 250k-row compare). Reusing these masks
    # turns that into simple boolean array indexing instead.
    diff_masks: dict[str, pd.Series] = {}
    modified_row_mask = pd.Series(False, index=both.index)

    for col in shared_value_columns:
        left_col = f"{col}_master" if f"{col}_master" in both.columns else col
        right_col = f"{col}_second" if f"{col}_second" in both.columns else col
        if left_col not in both.columns or right_col not in both.columns:
            continue
        differs = (both[left_col].astype(str) != both[right_col].astype(str)) & ~(
            both[left_col].isna() & both[right_col].isna()
        )
        diff_masks[col] = differs
        modified_row_mask = modified_row_mask | differs

    modified = both[modified_row_mask]

    modified_diffs: list[RowDiff] = []
    if diff_masks and len(modified):
        diff_matrix = pd.DataFrame({col: mask.loc[modified.index] for col, mask in diff_masks.items()})
        columns_array = diff_matrix.columns.to_numpy()
        bool_array = diff_matrix.to_numpy()
        key_values = both.loc[modified.index, key_cols_norm].to_numpy()

        for row_bools, row_key in zip(bool_array, key_values):
            modified_diffs.append(
                RowDiff(key=tuple(row_key), status="modified", changed_columns=columns_array[row_bools].tolist())
            )

    report = CompareReport(
        key_columns=key_columns,
        master_file=master_label,
        second_file=second_label,
        matched_count=len(both),
        missing_in_second=len(missing_in_second),
        new_in_second=len(new_in_second),
        modified_count=len(modified),
    )

    logger.info(
        "Compare complete: {} matched, {} missing-in-second, {} new-in-second, {} modified",
        report.matched_count,
        report.missing_in_second,
        report.new_in_second,
        report.modified_count,
    )

    return ComparisonResult(
        report=report,
        missing_in_second=missing_in_second.drop(columns=key_cols_norm, errors="ignore"),
        new_in_second=new_in_second.drop(columns=key_cols_norm, errors="ignore"),
        modified=modified.drop(columns=key_cols_norm, errors="ignore"),
        modified_diffs=modified_diffs,
    )


def export_comparison_report(result: ComparisonResult, output_path: str | Path) -> Path:
    """Write a multi-sheet Excel comparison report with color-coded sheets:
    Missing In Second (red), New In Second (green), Modified (yellow),
    plus a Summary sheet."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        workbook = writer.book
        red_fmt = workbook.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        green_fmt = workbook.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
        yellow_fmt = workbook.add_format({"bg_color": "#FFEB9C", "font_color": "#9C6500"})

        def _write_sheet(df: pd.DataFrame, sheet_name: str, fmt) -> None:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            ws = writer.sheets[sheet_name]
            if len(df):
                ws.conditional_format(
                    1, 0, len(df), max(len(df.columns) - 1, 0), {"type": "no_errors", "format": fmt}
                )

        _write_sheet(result.missing_in_second, "Missing In Second", red_fmt)
        _write_sheet(result.new_in_second, "New In Second", green_fmt)
        _write_sheet(result.modified, "Modified", yellow_fmt)

        summary = pd.DataFrame(
            {
                "Metric": [
                    "Master File",
                    "Second File",
                    "Key Column(s)",
                    "Matched Rows",
                    "Missing In Second",
                    "New In Second",
                    "Modified Rows",
                ],
                "Value": [
                    result.report.master_file,
                    result.report.second_file,
                    ", ".join(result.report.key_columns),
                    result.report.matched_count,
                    result.report.missing_in_second,
                    result.report.new_in_second,
                    result.report.modified_count,
                ],
            }
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)

    logger.info("Comparison report written to {}", output_path)
    return output_path
