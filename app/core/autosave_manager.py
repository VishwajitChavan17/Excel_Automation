"""
app.core.autosave_manager
============================
Session Restore (session_manager.py) only remembers which files were
open -- reloading from the original file gets you back to where you
started, not where you were when the app stopped responding. This module
is what makes crash recovery actually recover work: it periodically
snapshots every loaded sheet's current (possibly edited) DataFrame to
disk, keyed by file, so a crash mid-edit can be recovered from rather than
just reopened from scratch.

Snapshots are pandas pickles (no new dependency -- pandas ships this),
written under a manifest so a partial/corrupt snapshot from a genuine
crash can't take down recovery for everything else.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

MANIFEST_FILENAME = "manifest.json"


@dataclass
class AutosaveManifestEntry:
    file_key: str
    sheet_name: str
    original_display_name: str
    pickle_filename: str
    saved_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _slug(file_key: str, sheet_name: str) -> str:
    digest = hashlib.sha1(f"{file_key}::{sheet_name}".encode("utf-8")).hexdigest()[:16]
    return f"{digest}.pkl"


def snapshot_sheets(
    sheets: list[tuple[str, str, str, pd.DataFrame]],  # (file_key, sheet_name, display_name, df)
    directory: str | Path,
) -> Path:
    """Write every (file_key, sheet_name) DataFrame to `directory` as a
    pickle and record a manifest describing what's there. Overwrites any
    previous autosave -- this is a full snapshot, not an incremental diff,
    which keeps recovery logic simple and correct at the cost of doing a
    bit more disk I/O per autosave tick (acceptable at the row counts this
    app targets and the multi-second default autosave interval)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    entries = []
    for file_key, sheet_name, display_name, df in sheets:
        filename = _slug(file_key, sheet_name)
        try:
            df.to_pickle(directory / filename)
            entries.append(
                AutosaveManifestEntry(
                    file_key=file_key,
                    sheet_name=sheet_name,
                    original_display_name=display_name,
                    pickle_filename=filename,
                )
            )
        except Exception:  # noqa: BLE001 - one bad sheet shouldn't lose the whole autosave
            logger.exception("Autosave failed for {} / {}", file_key, sheet_name)

    manifest_path = directory / MANIFEST_FILENAME
    manifest_path.write_text(
        json.dumps([asdict(e) for e in entries], indent=2), encoding="utf-8"
    )
    logger.debug("Autosave: {} sheet(s) snapshotted to {}", len(entries), directory)
    return manifest_path


def has_pending_autosave(directory: str | Path) -> bool:
    manifest_path = Path(directory) / MANIFEST_FILENAME
    if not manifest_path.exists():
        return False
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return len(data) > 0
    except (json.JSONDecodeError, OSError):
        return False


def load_manifest(directory: str | Path) -> list[AutosaveManifestEntry]:
    manifest_path = Path(directory) / MANIFEST_FILENAME
    if not manifest_path.exists():
        return []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [AutosaveManifestEntry(**item) for item in data]


def load_snapshot(entry: AutosaveManifestEntry, directory: str | Path) -> pd.DataFrame | None:
    path = Path(directory) / entry.pickle_filename
    if not path.exists():
        return None
    try:
        return pd.read_pickle(path)
    except Exception:  # noqa: BLE001 - corrupt snapshot shouldn't crash recovery
        logger.exception("Failed to read autosave snapshot {}", path)
        return None


def clear_autosave(directory: str | Path) -> None:
    directory = Path(directory)
    if not directory.exists():
        return
    for path in directory.iterdir():
        try:
            path.unlink()
        except OSError:
            pass
    logger.debug("Autosave directory cleared: {}", directory)
