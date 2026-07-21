"""
app.core.paths
===============
Resolves runtime paths in a way that behaves identically whether the app is
run from source (`python main.py`) or from a frozen PyInstaller onefile EXE.

PyInstaller onefile executables unpack to a temporary directory exposed via
`sys._MEIPASS`. Anything that must persist across runs (logs, config, user
templates, the SQLite database, exports) must NOT live inside that temp
directory -- it is deleted after the process exits. Instead, persistent data
lives next to the EXE itself (or next to main.py in source mode).
"""

from __future__ import annotations

import sys
from pathlib import Path

from app.core import constants


def is_frozen() -> bool:
    """True when running as a PyInstaller-built executable."""
    return getattr(sys, "frozen", False)


def app_root() -> Path:
    """
    Directory the EXE (or main.py) lives in. This is where persistent,
    user-writable folders (logs/, config/, templates/, exports/, database/)
    are created -- never inside the PyInstaller temp unpack directory.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def bundle_root() -> Path:
    """
    Directory containing bundled read-only resources (icons, default
    config templates shipped with the app). Under PyInstaller onefile this
    is sys._MEIPASS; in source mode it's the same as app_root().
    """
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_root()))
    return app_root()


def persistent_dir(name: str) -> Path:
    """Return (and create if missing) a persistent, writable directory."""
    path = app_root() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    return persistent_dir(constants.DIR_LOGS)


def config_dir() -> Path:
    return persistent_dir(constants.DIR_CONFIG)


def templates_dir() -> Path:
    return persistent_dir(constants.DIR_TEMPLATES)


def workflows_dir() -> Path:
    return persistent_dir(constants.DIR_WORKFLOWS)


def autosave_dir() -> Path:
    return persistent_dir(constants.DIR_AUTOSAVE)


def session_file() -> Path:
    return config_dir() / constants.FILE_SESSION


def audit_db_path() -> Path:
    return database_dir() / constants.FILE_AUDIT_DB


def exports_dir() -> Path:
    return persistent_dir(constants.DIR_EXPORTS)


def database_dir() -> Path:
    return persistent_dir(constants.DIR_DATABASE)


def plugins_dir() -> Path:
    """Plugins ship inside the bundle (read-only, discovered at import time)."""
    return bundle_root() / constants.DIR_PLUGINS


def assets_dir() -> Path:
    return bundle_root() / "assets"
