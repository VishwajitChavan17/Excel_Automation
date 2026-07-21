"""
app.services.excel.merge_service
===================================
Pure business logic for "Excel Merge" and "Consolidation Tool":

- union_merge / join_merge: combine two or more DataFrames via a simple
  stacking union or a SQL-style join (inner/left/right/outer).
- consolidate: given many (file_label, sheet_name, DataFrame) sources,
  auto-detect which ones share an identical header signature, concatenate
  the largest matching group into one master DataFrame, and stamp every
  row with its source filename, source sheet, and import timestamp.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import ConsolidationGroup, ConsolidationReport, MergeReport

JoinMode = str  # "inner" | "left" | "right" | "outer"

SOURCE_FILE_COL = "__source_file__"
SOURCE_SHEET_COL = "__source_sheet__"
IMPORT_TIMESTAMP_COL = "__import_timestamp__"


def union_merge(
    frames: list[pd.DataFrame], source_labels: list[str]
) -> tuple[pd.DataFrame, MergeReport]:
    """Stack frames on top of each other, aligning columns by name (outer
    union of columns -- missing values become NaN). Adds a Source File
    column so provenance is never lost."""
    if not frames:
        raise ValueError("At least one file is required to merge.")
    if len(frames) != len(source_labels):
        raise ValueError("frames and source_labels must be the same length.")

    tagged = []
    for df, label in zip(frames, source_labels):
        d = df.copy()
        d["Source File"] = label
        tagged.append(d)

    result = pd.concat(tagged, ignore_index=True, sort=False)
    report = MergeReport(
        mode="union",
        source_count=len(frames),
        result_row_count=len(result),
        result_column_count=result.shape[1],
    )
    logger.info("Union merge: {} source(s) -> {} rows", len(frames), len(result))
    return result, report


def join_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    key_columns: list[str],
    mode: JoinMode,
) -> tuple[pd.DataFrame, MergeReport]:
    """SQL-style join of two DataFrames on one or more key columns."""
    if mode not in ("inner", "left", "right", "outer"):
        raise ValueError(f"Unknown join mode: {mode!r}")
    if not key_columns:
        raise ValueError("At least one key column is required for a join.")
    missing_left = [c for c in key_columns if c not in left.columns]
    missing_right = [c for c in key_columns if c not in right.columns]
    if missing_left or missing_right:
        raise ValueError(
            f"Key column(s) missing -- left: {missing_left}, right: {missing_right}"
        )

    result = left.merge(right, on=key_columns, how=mode, suffixes=("_left", "_right"))
    report = MergeReport(
        mode=mode,
        key_columns=list(key_columns),
        source_count=2,
        result_row_count=len(result),
        result_column_count=result.shape[1],
    )
    logger.info("{} join on {}: {} rows", mode, key_columns, len(result))
    return result, report


def detect_header_groups(
    sources: list[tuple[str, str, pd.DataFrame]],
) -> dict[tuple[str, ...], list[tuple[str, str, pd.DataFrame]]]:
    """Group sources by their exact column signature (name + order)."""
    groups: dict[tuple[str, ...], list[tuple[str, str, pd.DataFrame]]] = {}
    for label, sheet, df in sources:
        key = tuple(str(c) for c in df.columns)
        groups.setdefault(key, []).append((label, sheet, df))
    return groups


def consolidate(
    sources: list[tuple[str, str, pd.DataFrame]],
) -> tuple[pd.DataFrame, ConsolidationReport]:
    """
    Auto-detect which sources share an identical header signature and
    concatenate the largest matching group, stamping every row with its
    source filename, source sheet, and import timestamp. Sources whose
    headers don't match the chosen group are reported as mismatched but
    not included in the output (the report lists every group found so the
    user can see exactly what didn't line up).
    """
    if not sources:
        raise ValueError("At least one file is required to consolidate.")

    groups = detect_header_groups(sources)
    sorted_groups = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    chosen_columns, chosen_sources = sorted_groups[0]

    timestamp = datetime.now().isoformat(timespec="seconds")
    frames = []
    for label, sheet, df in chosen_sources:
        d = df.copy()
        d[SOURCE_FILE_COL] = label
        d[SOURCE_SHEET_COL] = sheet
        d[IMPORT_TIMESTAMP_COL] = timestamp
        frames.append(d)

    consolidated = pd.concat(frames, ignore_index=True)

    report_groups = [
        ConsolidationGroup(columns=cols, sources=[(label, sheet) for label, sheet, _ in group])
        for cols, group in sorted_groups
    ]
    report = ConsolidationReport(
        groups=report_groups,
        chosen_group_index=0,
        consolidated_row_count=len(consolidated),
        consolidated_source_count=len(chosen_sources),
        mismatched_source_count=len(sources) - len(chosen_sources),
    )
    logger.info(
        "Consolidation: {} source(s) matched the dominant header signature "
        "({} column(s)), {} mismatched, {} total row(s).",
        len(chosen_sources),
        len(chosen_columns),
        report.mismatched_source_count,
        report.consolidated_row_count,
    )
    return consolidated, report


def export_result(df: pd.DataFrame, output_path: str | Path, sheet_name: str = "Result") -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    logger.info("Merge/consolidation result written to {}", output_path)
    return output_path
