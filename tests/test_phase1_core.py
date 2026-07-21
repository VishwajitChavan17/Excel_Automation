"""
tests/test_phase1_core.py
==========================
Headless smoke tests for Phase 1: config manager, plugin discovery, and the
Excel loader service. Deliberately avoids importing anything that creates a
QApplication / shows a widget, so this suite runs in CI without a display.

Run with:  pytest tests/test_phase1_core.py -v
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.core.config_manager import ConfigManager
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.services.excel.loader_service import load_workbook


# -- ConfigManager -------------------------------------------------------


def test_config_manager_creates_defaults(tmp_path: Path) -> None:
    config = ConfigManager(config_path=tmp_path / "settings.yaml")
    assert config.get("app.theme") == "dark"
    assert config.get("performance.large_file_row_threshold") == 100_000


def test_config_manager_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "settings.yaml"
    config = ConfigManager(config_path=path)
    config.set("app.theme", "light")

    reloaded = ConfigManager(config_path=path)
    assert reloaded.get("app.theme") == "light"


def test_config_manager_missing_key_returns_default(tmp_path: Path) -> None:
    config = ConfigManager(config_path=tmp_path / "settings.yaml")
    assert config.get("nonexistent.key", "fallback") == "fallback"


def test_config_manager_recent_files_dedupes(tmp_path: Path) -> None:
    config = ConfigManager(config_path=tmp_path / "settings.yaml")
    config.add_recent_file("a.xlsx")
    config.add_recent_file("b.xlsx")
    config.add_recent_file("a.xlsx")  # re-add should move to front, not duplicate
    recents = config.get("recent_files")
    assert recents == ["a.xlsx", "b.xlsx"]


# -- Plugin base -----------------------------------------------------------


class _DummyPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="test.dummy",
        display_name="Dummy",
        category=PluginCategory.OTHER,
    )

    def create_widget(self, parent=None):  # pragma: no cover - not exercised headlessly
        raise NotImplementedError


def test_plugin_requires_metadata() -> None:
    class _BadPlugin(Plugin):
        def create_widget(self, parent=None):
            return None

    with pytest.raises(NotImplementedError):
        _BadPlugin()


def test_plugin_lifecycle_flags() -> None:
    plugin = _DummyPlugin()
    assert plugin.is_loaded is False
    plugin.on_load(context=None)
    assert plugin.is_loaded is True
    plugin.on_unload()
    assert plugin.is_loaded is False


# -- Excel loader service --------------------------------------------------


def test_load_workbook_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "sample.csv"
    df = pd.DataFrame({"id": [1, 2, 3, None], "name": ["a", "b", "b", "c"]})
    df.to_csv(csv_path, index=False)

    handle, loaded_df = load_workbook(csv_path)

    assert handle.row_count == 4
    assert handle.column_count == 2
    assert handle.engine_used == "pandas"
    assert len(handle.column_profiles) == 2

    id_profile = next(p for p in handle.column_profiles if p.name == "id")
    assert id_profile.null_count == 1


def test_load_workbook_xlsx(tmp_path: Path) -> None:
    xlsx_path = tmp_path / "sample.xlsx"
    df = pd.DataFrame({"col1": range(10), "col2": [f"row{i}" for i in range(10)]})
    df.to_excel(xlsx_path, index=False, sheet_name="Data")

    handle, loaded_df = load_workbook(xlsx_path)

    assert handle.row_count == 10
    assert handle.active_sheet == "Data"
    assert handle.sheets[0].name == "Data"


def test_load_workbook_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_workbook("/nonexistent/path/does_not_exist.xlsx")


def test_load_workbook_unsupported_extension(tmp_path: Path) -> None:
    from app.services.excel.loader_service import UnsupportedFileTypeError

    bad_path = tmp_path / "sample.txt"
    bad_path.write_text("not excel")
    with pytest.raises(UnsupportedFileTypeError):
        load_workbook(bad_path)
