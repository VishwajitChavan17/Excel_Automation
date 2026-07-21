"""
app.services.excel.duplicate_service
======================================
Pure business logic for the Duplicate Finder tool: find duplicate rows by
one or more key columns, mark them for the preview grid, remove them under
a chosen keep-strategy, and export a duplicate report workbook.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import DuplicateReport

KeepStrategy = str  # "first" | "last" | "highest"


def find_duplicate_mask(
    df: pd.DataFrame, columns: list[str], *, keep: KeepStrategy = "first"
) -> pd.Series:
    """
    Return a boolean Series (same index as df) that is True for rows
    considered duplicates under `columns` and the given keep-strategy.

    keep="first"  -> pandas semantics: first occurrence kept, rest flagged
    keep="last"   -> last occurrence kept, rest flagged
    keep="highest"-> requires exactly one numeric column beyond the key
                     columns to break ties; falls back to "first" if no
                     other numeric column exists.
    """
    if not columns:
        raise ValueError("At least one column must be selected to find duplicates.")
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(f"Column(s) not found in sheet: {missing}")

    if keep in ("first", "last"):
        return df.duplicated(subset=columns, keep=keep)

    if keep == "highest":
        numeric_cols = [
            c for c in df.columns if c not in columns and pd.api.types.is_numeric_dtype(df[c])
        ]
        if not numeric_cols:
            logger.warning(
                "keep='highest' requested but no numeric column found to rank by; "
                "falling back to keep='first'."
            )
            return df.duplicated(subset=columns, keep="first")

        rank_col = numeric_cols[0]
        # Sort descending by the rank column so "first" (highest) is kept
        # per pandas.duplicated semantics, then restore original row order
        # for the returned mask.
        sorted_df = df.sort_values(by=rank_col, ascending=False, kind="mergesort")
        dup_in_sorted = sorted_df.duplicated(subset=columns, keep="first")
        return dup_in_sorted.reindex(df.index)

    raise ValueError(f"Unknown keep strategy: {keep!r}")


def build_duplicate_report(
    df: pd.DataFrame, columns: list[str], *, keep: KeepStrategy = "first"
) -> DuplicateReport:
    mask = find_duplicate_mask(df, columns, keep=keep)
    return DuplicateReport(
        columns_checked=list(columns),
        total_rows=len(df),
        duplicate_row_count=int(mask.sum()),
        duplicate_row_indices=df.index[mask].tolist(),
        keep_strategy=keep,
    )


def remove_duplicates(
    df: pd.DataFrame, columns: list[str], *, keep: KeepStrategy = "first"
) -> pd.DataFrame:
    """Return a new DataFrame with duplicate rows removed."""
    mask = find_duplicate_mask(df, columns, keep=keep)
    return df.loc[~mask].reset_index(drop=True)


def export_duplicate_report(
    df: pd.DataFrame,
    report: DuplicateReport,
    output_path: str | Path,
) -> Path:
    """Write an Excel report: one sheet with only the duplicate rows
    highlighted, one summary sheet with counts. Returns the output path."""
    import xlsxwriter  # noqa: F401 - ensures engine is available, fail fast if missing

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    duplicate_rows = df.loc[df.index.isin(report.duplicate_row_indices)]

    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        duplicate_rows.to_excel(writer, sheet_name="Duplicate Rows", index=False)
        summary = pd.DataFrame(
            {
                "Metric": [
                    "Columns Checked",
                    "Total Rows",
                    "Duplicate Rows",
                    "Keep Strategy",
                ],
                "Value": [
                    ", ".join(report.columns_checked),
                    report.total_rows,
                    report.duplicate_row_count,
                    report.keep_strategy,
                ],
            }
        )
        summary.to_excel(writer, sheet_name="Summary", index=False)

        workbook = writer.book
        red_format = workbook.add_format({"bg_color": "#F85149", "font_color": "#FFFFFF"})
        dup_sheet = writer.sheets["Duplicate Rows"]
        if len(duplicate_rows):
            dup_sheet.conditional_format(
                1,
                0,
                len(duplicate_rows),
                len(duplicate_rows.columns) - 1,
                {"type": "no_errors", "format": red_format},
            )

    logger.info("Duplicate report written to {}", output_path)
    return output_path
