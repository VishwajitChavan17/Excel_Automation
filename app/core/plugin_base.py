"""
app.core.plugin_base
=====================
Every feature in Excel Automation Studio -- Compare, Merge, Consolidate,
Duplicate Finder, and every future engineering tool (DBC Comparator, CAN
Matrix Merger, etc.) -- is implemented as a plugin that subclasses `Plugin`.

This is what makes "adding a future tool require almost no code
modification": drop a new module in app/plugins/, subclass Plugin, and the
PluginManager will discover, validate, and register it automatically at
startup. No changes to the main window, ribbon, or core app are required.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtWidgets import QWidget


class PluginCategory(str, Enum):
    HOME = "Home"
    IMPORT = "Import"
    EXCEL = "Excel"
    COMPARE = "Compare"
    MERGE = "Merge"
    TRANSFORM = "Transform"
    VALIDATION = "Validation"
    REPORTS = "Reports"
    AUTOMATION = "Automation"
    TEMPLATES = "Templates"
    SETTINGS = "Settings"
    ENGINEERING = "Engineering"  # DBC/CAN/HIL/TPT-style specialized plugins
    OTHER = "Other"


@dataclass(frozen=True)
class PluginMetadata:
    """Static, declarative description of a plugin -- used for the ribbon,
    the plugin manager panel, and dependency/version checks. Kept separate
    from plugin *behavior* so it can be inspected without instantiating
    (or importing heavy dependencies of) the plugin itself."""

    plugin_id: str  # unique, stable, e.g. "excel.compare"
    display_name: str  # e.g. "Compare Excel"
    category: PluginCategory
    description: str = ""
    version: str = "1.0.0"
    author: str = "MTU Engineering Tools Team"
    icon: str = "plugin_default.svg"
    requires: tuple[str, ...] = field(default_factory=tuple)  # other plugin_ids
    enabled_by_default: bool = True


class Plugin(ABC):
    """
    Abstract base class for all Excel Automation Studio plugins.

    Lifecycle called by PluginManager:
        1. __init__()             -- cheap, no I/O
        2. on_load(context)       -- register services, subscribe to events
        3. create_widget(parent)  -- called lazily, first time the user
                                      opens this plugin's tab
        4. on_unload()            -- called on app shutdown / plugin disable
    """

    #: Must be overridden by every concrete plugin.
    metadata: PluginMetadata

    def __init__(self) -> None:
        if not hasattr(self, "metadata"):
            raise NotImplementedError(
                f"{type(self).__name__} must define a class-level `metadata` "
                f"attribute of type PluginMetadata."
            )
        self._loaded = False
        self._context: "PluginContext | None" = None

    def on_load(self, context: "PluginContext") -> None:
        """Called once, at application startup, after discovery. Override to
        register menu actions, listen for app-wide signals, etc. Default:
        stores the context (accessible via self.context) and marks loaded."""
        self._context = context
        self._loaded = True

    @property
    def context(self) -> "PluginContext | None":
        return self._context

    def on_unload(self) -> None:
        """Called on shutdown or when the user disables the plugin. Override
        to release resources (file handles, DB connections, threads)."""
        self._loaded = False

    @abstractmethod
    def create_widget(self, parent: QWidget | None = None) -> QWidget:
        """Build and return the QWidget shown inside this plugin's workspace
        tab. Called lazily -- only when the user actually opens the tool --
        so startup stays fast even with dozens of plugins installed."""
        raise NotImplementedError

    @property
    def is_loaded(self) -> bool:
        return self._loaded


@dataclass
class PluginContext:
    """
    Passed to every plugin's on_load(). Gives plugins controlled access to
    shared application services without importing the main window directly
    (keeps plugins decoupled and independently testable).
    """

    config: "object"  # app.core.config_manager.ConfigManager, typed loosely
                        # here to avoid a circular import at module load time
    registry: "object" = None  # app.core.workbook_registry.WorkbookRegistry
    main_window: "object" = None  # app.ui.main_window.MainWindow, set at runtime
