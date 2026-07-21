"""
app.core.config_manager
========================
Loads, validates, and persists user configuration (config/settings.yaml).

Design notes:
- A hard-coded DEFAULT_CONFIG is the single source of truth for schema and
  defaults. On load, the file on disk is deep-merged on top of the defaults,
  so new config keys introduced in later app versions "just appear" with
  sane defaults instead of crashing on missing keys.
- This is a lazily-instantiated singleton (`get_config()`), not a global
  created at import time, so unit tests can point it at a temp directory.
"""

from __future__ import annotations

import copy
import threading
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from app.core import paths

DEFAULT_CONFIG: dict[str, Any] = {
    "app": {
        "theme": "dark",
        "language": "en",
        "auto_save_interval_seconds": 120,
        "auto_save_enabled": True,
        "confirm_before_overwrite": True,
        "restore_last_session": True,
    },
    "window": {
        "width": 1600,
        "height": 950,
        "maximized": True,
        "docked_panels": {
            "project_explorer": True,
            "properties": True,
            "console": True,
        },
    },
    "performance": {
        "large_file_row_threshold": 100_000,
        "max_worker_threads": 4,
        "use_polars_for_large_files": True,
    },
    "recent_files": [],
    "recent_projects": [],
    "plugins": {
        "enabled": [],
        "disabled": [],
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge `override` onto a copy of `base`. `override` wins."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class ConfigManager:
    """Thread-safe application configuration store, backed by YAML on disk."""

    def __init__(self, config_path: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._path = config_path or (paths.config_dir() / "settings.yaml")
        self._data: dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    # -- persistence ---------------------------------------------------

    def load(self) -> None:
        with self._lock:
            if self._path.exists():
                try:
                    with open(self._path, encoding="utf-8") as fh:
                        on_disk = yaml.safe_load(fh) or {}
                    self._data = _deep_merge(DEFAULT_CONFIG, on_disk)
                    logger.info("Configuration loaded from {}", self._path)
                except Exception:
                    logger.exception(
                        "Failed to parse {} -- falling back to defaults", self._path
                    )
                    self._data = copy.deepcopy(DEFAULT_CONFIG)
            else:
                logger.info("No config file found, writing defaults to {}", self._path)
                self._data = copy.deepcopy(DEFAULT_CONFIG)
                self.save()

    def save(self) -> None:
        with self._lock:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as fh:
                    yaml.safe_dump(self._data, fh, sort_keys=False, allow_unicode=True)
            except Exception:
                logger.exception("Failed to save configuration to {}", self._path)

    # -- access ----------------------------------------------------------

    def get(self, dotted_key: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for part in dotted_key.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return node

    def set(self, dotted_key: str, value: Any, *, persist: bool = True) -> None:
        with self._lock:
            parts = dotted_key.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
            if persist:
                self.save()

    def add_recent_file(self, file_path: str, *, max_items: int = 15) -> None:
        with self._lock:
            recents: list[str] = self._data.setdefault("recent_files", [])
            if file_path in recents:
                recents.remove(file_path)
            recents.insert(0, file_path)
            del recents[max_items:]
            self.save()

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)


_instance: ConfigManager | None = None
_instance_lock = threading.Lock()


def get_config() -> ConfigManager:
    """Return the process-wide ConfigManager singleton, creating it on first use."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = ConfigManager()
    return _instance
