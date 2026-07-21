"""
app.core.audit_log
=====================
Persistent audit trail, backed by SQLite. Distinct from
WorkbookRegistry's in-memory undo/redo history (which holds full
DataFrame snapshots and is cleared on exit) -- this only stores compact
descriptive rows (timestamp, file, sheet, operation) and survives across
application restarts, which is what "enterprise audit log" actually
requires: a durable record of what happened, when, regardless of whether
the app crashed afterward.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class AuditEntry:
    id: int | None
    timestamp: str
    file_key: str
    sheet_name: str
    operation: str


class AuditLog:
    """Thin wrapper around a single-table SQLite database. Opens a new
    connection per call (audit writes are infrequent -- one per user
    operation -- so connection-per-call simplicity outweighs the cost of a
    persistent connection, and it makes this class trivially safe to touch
    from any thread without a shared-connection lock)."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self._db_path))

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    file_key TEXT NOT NULL,
                    sheet_name TEXT NOT NULL,
                    operation TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def log(self, file_key: str, sheet_name: str, operation: str, *, timestamp: datetime | None = None) -> None:
        ts = (timestamp or datetime.now()).isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_entries (timestamp, file_key, sheet_name, operation) VALUES (?, ?, ?, ?)",
                (ts, file_key, sheet_name, operation),
            )
            conn.commit()

    def query(self, *, limit: int = 500, search: str | None = None) -> list[AuditEntry]:
        """Most-recent-first. `search` filters on file_key/sheet_name/operation
        (case-insensitive substring match)."""
        sql = "SELECT id, timestamp, file_key, sheet_name, operation FROM audit_entries"
        params: tuple = ()
        if search:
            needle = f"%{search.lower()}%"
            sql += " WHERE lower(file_key) LIKE ? OR lower(sheet_name) LIKE ? OR lower(operation) LIKE ?"
            params = (needle, needle, needle)
        sql += " ORDER BY id DESC LIMIT ?"
        params = params + (limit,)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [AuditEntry(id=r[0], timestamp=r[1], file_key=r[2], sheet_name=r[3], operation=r[4]) for r in rows]

    def count(self) -> int:
        with self._connect() as conn:
            (n,) = conn.execute("SELECT COUNT(*) FROM audit_entries").fetchone()
        return n

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM audit_entries")
            conn.commit()

    def prune_older_than(self, days: int) -> int:
        """Delete entries older than `days` days; returns the number removed."""
        cutoff = datetime.now().timestamp() - days * 86400
        with self._connect() as conn:
            rows = conn.execute("SELECT id, timestamp FROM audit_entries").fetchall()
            to_delete = [
                row_id for row_id, ts in rows if datetime.fromisoformat(ts).timestamp() < cutoff
            ]
            if to_delete:
                conn.executemany("DELETE FROM audit_entries WHERE id = ?", [(i,) for i in to_delete])
                conn.commit()
        return len(to_delete)


def export_audit_log_excel(entries: list[AuditEntry], output_path: str | Path) -> Path:
    import pandas as pd

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(
        {
            "Timestamp": [e.timestamp for e in entries],
            "File": [e.file_key for e in entries],
            "Sheet": [e.sheet_name for e in entries],
            "Operation": [e.operation for e in entries],
        }
    )
    with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="Audit Log", index=False)
    return output_path
