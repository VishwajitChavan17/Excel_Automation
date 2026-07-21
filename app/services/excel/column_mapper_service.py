"""
app.services.excel.column_mapper_service
===========================================
Pure business logic for the Column Mapper tool: rename/select columns
according to a source -> destination mapping, and save/load reusable
mapping templates as JSON files under templates/.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from loguru import logger

from app.services.excel.models import ColumnMapping


def apply_mapping(
    df: pd.DataFrame, mappings: list[ColumnMapping], *, keep_unmapped: bool = False
) -> pd.DataFrame:
    """Return a new DataFrame with only the mapped columns, renamed to
    their destination names (in mapping order). If keep_unmapped is True,
    any source columns not covered by a mapping are appended unchanged."""
    if not mappings:
        raise ValueError("At least one column mapping is required.")

    missing = [m.source_column for m in mappings if m.source_column not in df.columns]
    if missing:
        raise ValueError(f"Source column(s) not found: {missing}")

    ordered_sources = [m.source_column for m in mappings]
    rename_map = {m.source_column: m.destination_column for m in mappings}
    result = df[ordered_sources].rename(columns=rename_map)

    if keep_unmapped:
        leftover = [c for c in df.columns if c not in ordered_sources]
        if leftover:
            result = pd.concat([result, df[leftover]], axis=1)

    logger.info("Applied {} column mapping(s) -> {} column(s) in result", len(mappings), result.shape[1])
    return result


def auto_map_identical_names(source_columns: list[str], destination_columns: list[str]) -> list[ColumnMapping]:
    """Convenience helper: map every source column to a destination column
    of the exact same name, where one exists. Used for the "Auto-map"
    button so the user doesn't have to hand-map obviously-identical fields."""
    dest_set = set(destination_columns)
    return [ColumnMapping(col, col) for col in source_columns if col in dest_set]


def save_mapping_template(name: str, mappings: list[ColumnMapping], directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip() or "mapping"
    path = directory / f"{safe_name}.json"
    payload = [{"source": m.source_column, "destination": m.destination_column} for m in mappings]
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Saved column mapping template '{}' ({} mapping(s)) to {}", name, len(mappings), path)
    return path


def load_mapping_template(path: str | Path) -> list[ColumnMapping]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ColumnMapping(item["source"], item["destination"]) for item in data]


def list_mapping_templates(directory: str | Path) -> list[Path]:
    directory = Path(directory)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))
