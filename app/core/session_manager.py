"""
app.core.session_manager
===========================
Tracks "what files were open" so the app can offer Session Restore, and
"did the last run shut down cleanly" so it can distinguish a crash from a
normal exit and word the recovery prompt accordingly.

The mechanism is a single JSON file written at startup with
clean_shutdown=False, updated as files are loaded, and finally rewritten
with clean_shutdown=True in MainWindow.closeEvent(). If the file is read
back at the next startup and clean_shutdown is still False, the previous
run never reached its own shutdown code -- i.e. it crashed (or the OS
killed it) -- and AutoSaveManager almost certainly has more useful data to
offer than the plain file list here.

No Qt dependency -- callable from a worker thread, a script, or a test.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from loguru import logger


@dataclass
class SessionState:
    loaded_files: list[str] = field(default_factory=list)
    clean_shutdown: bool = False
    saved_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def save_session(state: SessionState, path: str | Path) -> Path | None:
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        state.saved_at = datetime.now().isoformat(timespec="seconds")
        path.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
        return path
    except OSError as exc:
        logger.error("SessionManager: failed to save session: {}", exc)
        return None


def load_session(path: str | Path) -> SessionState | None:
    path = Path(path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return SessionState(
            loaded_files=data.get("loaded_files", []),
            clean_shutdown=data.get("clean_shutdown", False),
            saved_at=data.get("saved_at", ""),
        )
    except (json.JSONDecodeError, OSError):
        return None


def clear_session(path: str | Path) -> None:
    path = Path(path)
    try:
        if path.exists():
            path.unlink()
    except OSError as exc:
        logger.error("SessionManager: failed to clear session: {}", exc)
