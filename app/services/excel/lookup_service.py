"""
app.services.excel.lookup_service
====================================
Pure business logic for the "Lookup & Copy Values" tool -- the most common
enterprise workflow: given a master workbook containing authoritative
values and a target workbook that needs them, match rows by a chosen
column and copy one or more value columns across (VLOOKUP-style), without
the user writing a single Excel formula.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import LookupReport


def lookup_and_copy(
    master: pd.DataFrame,
    target: pd.DataFrame,
    match_column: str | list[str],
    copy_columns: list[str],
    *,
    ignore_case: bool = False,
    ignore_whitespace: bool = False,
    overwrite_existing: bool = True,
) -> tuple[pd.DataFrame, LookupReport]:
    """
    Return (updated_target_df, LookupReport). For every row in `target`,
    look up `match_column` in `master` and copy `copy_columns` across.
    Unmatched rows keep their original values (or blank if the column is
    new). Master must contain unique match key values -- duplicates are
    resolved by keeping the first occurrence, matching typical VLOOKUP
    behavior.

    `match_column` accepts either a single column name or a list of column
    names for composite-key matching (e.g. ["VIN", "Engine Number"] --
    supports the "Multi Column Matching" workflow: one row matches another
    only if *every* listed column agrees).
    """
    match_columns = [match_column] if isinstance(match_column, str) else list(match_column)
    if not match_columns:
        raise ValueError("At least one match column is required.")

    missing_master = [c for c in match_columns if c not in master.columns]
    missing_target = [c for c in match_columns if c not in target.columns]
    if missing_master:
        raise ValueError(f"Match column(s) {missing_master} not found in master file.")
    if missing_target:
        raise ValueError(f"Match column(s) {missing_target} not found in target file.")
    missing_copy_cols = [c for c in copy_columns if c not in master.columns]
    if missing_copy_cols:
        raise ValueError(f"Copy column(s) {missing_copy_cols} not found in master file.")
    if not copy_columns:
        raise ValueError("At least one column to copy must be selected.")

    result = target.copy()

    def _composite_key(df: pd.DataFrame) -> pd.Series:
        key: pd.Series | None = None
        for col in match_columns:
            s = df[col].astype(str)
            if ignore_whitespace:
                s = s.str.strip()
            if ignore_case:
                s = s.str.lower()
            key = s if key is None else key.str.cat(s, sep="||")
        return key

    master_lookup = master.copy()
    master_lookup["__key__"] = _composite_key(master_lookup)
    master_lookup = master_lookup.drop_duplicates(subset="__key__", keep="first").set_index("__key__")

    target_keys = _composite_key(result)
    matched_mask = target_keys.isin(master_lookup.index)

    for col in copy_columns:
        dest_col = col if col not in result.columns or overwrite_existing else f"{col}_copied"
        looked_up = target_keys.map(master_lookup[col])
        if dest_col in result.columns and not overwrite_existing:
            result[dest_col] = result[dest_col]
        else:
            if dest_col in result.columns:
                result.loc[matched_mask, dest_col] = looked_up[matched_mask]
            else:
                result[dest_col] = looked_up

    report = LookupReport(
        master_file="master",
        target_file="target",
        match_column=" + ".join(match_columns),
        copy_columns=list(copy_columns),
        matched_count=int(matched_mask.sum()),
        unmatched_count=int((~matched_mask).sum()),
    )

    logger.info(
        "Lookup complete: {} matched, {} unmatched, match key: {}, columns copied: {}",
        report.matched_count,
        report.unmatched_count,
        match_columns,
        copy_columns,
    )

    return result, report


def export_updated_workbook(df: pd.DataFrame, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Updated", index=False)
    logger.info("Updated workbook written to {}", output_path)
    return output_path
