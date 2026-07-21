"""
app.core.plugin_manager
========================
Discovers every Plugin subclass under app/plugins/, instantiates it,
resolves declared dependencies, and calls its on_load() lifecycle hook.

Discovery is filesystem-based (pkgutil.iter_modules), not a manually
maintained registry list -- this is the mechanism that lets new tools be
added by simply dropping a file into app/plugins/, per the "future ready"
requirement.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass

from loguru import logger

from app.core.config_manager import ConfigManager
from app.core.plugin_base import Plugin, PluginContext


@dataclass
class PluginLoadError:
    module_name: str
    error: str


class PluginManager:
    """Owns the lifecycle of every discovered plugin instance."""

    def __init__(self, config: ConfigManager, registry: object | None = None) -> None:
        self._config = config
        self._registry = registry
        self._plugins: dict[str, Plugin] = {}
        self._load_errors: list[PluginLoadError] = []

    # -- discovery ---------------------------------------------------------

    def discover_and_load(self) -> None:
        """Import every module under app.plugins, find Plugin subclasses,
        instantiate them, and call on_load(). Failures in one plugin are
        isolated and logged -- they never prevent the rest of the app (or
        other plugins) from starting."""
        import app.plugins as plugins_pkg

        enabled_override = set(self._config.get("plugins.enabled", []) or [])
        disabled_override = set(self._config.get("plugins.disabled", []) or [])

        discovered = 0
        for module_info in pkgutil.iter_modules(
            plugins_pkg.__path__, prefix=f"{plugins_pkg.__name__}."
        ):
            discovered += 1
            self._load_module(module_info.name, enabled_override, disabled_override)

        logger.info(
            "Plugin discovery complete: {} module(s) scanned, {} plugin(s) "
            "loaded, {} error(s).",
            discovered,
            len(self._plugins),
            len(self._load_errors),
        )

    def _load_module(
        self, module_name: str, enabled_override: set[str], disabled_override: set[str]
    ) -> None:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - isolate arbitrary plugin errors
            logger.exception("Failed to import plugin module {}", module_name)
            self._load_errors.append(PluginLoadError(module_name, str(exc)))
            return

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj is Plugin or not issubclass(obj, Plugin):
                continue
            if obj.__module__ != module.__name__:
                continue  # skip re-exported/imported classes, only load definitions
            self._instantiate_and_load(obj, disabled_override)

    def _instantiate_and_load(self, plugin_cls: type[Plugin], disabled: set[str]) -> None:
        try:
            instance = plugin_cls()
            plugin_id = instance.metadata.plugin_id

            if plugin_id in disabled:
                logger.info("Plugin '{}' is disabled via config, skipping.", plugin_id)
                return
            if plugin_id in self._plugins:
                logger.warning(
                    "Duplicate plugin_id '{}' from {} -- keeping first registration.",
                    plugin_id,
                    plugin_cls.__module__,
                )
                return

            missing = [
                dep for dep in instance.metadata.requires if dep not in self._plugins
            ]
            if missing:
                logger.warning(
                    "Plugin '{}' declares unresolved dependencies {} -- "
                    "loading anyway (dependency ordering not yet enforced).",
                    plugin_id,
                    missing,
                )

            context = PluginContext(config=self._config, registry=self._registry)
            instance.on_load(context)
            self._plugins[plugin_id] = instance
            logger.info(
                "Loaded plugin '{}' ({}) v{}",
                plugin_id,
                instance.metadata.display_name,
                instance.metadata.version,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to instantiate/load plugin class {}", plugin_cls)
            self._load_errors.append(PluginLoadError(plugin_cls.__module__, str(exc)))

    # -- access ----------------------------------------------------------

    def attach_main_window(self, main_window: object) -> None:
        """Called once by main.py after MainWindow is constructed (plugins
        are loaded before the window exists, so this is a second pass)."""
        for plugin in self._plugins.values():
            if plugin.context is not None:
                plugin.context.main_window = main_window

    def all_plugins(self) -> list[Plugin]:
        return list(self._plugins.values())

    def get(self, plugin_id: str) -> Plugin | None:
        return self._plugins.get(plugin_id)

    def plugins_by_category(self) -> dict[str, list[Plugin]]:
        grouped: dict[str, list[Plugin]] = {}
        for plugin in self._plugins.values():
            grouped.setdefault(plugin.metadata.category.value, []).append(plugin)
        for group in grouped.values():
            group.sort(key=lambda p: p.metadata.display_name)
        return grouped

    def load_errors(self) -> list[PluginLoadError]:
        return list(self._load_errors)

    def shutdown(self) -> None:
        for plugin_id, plugin in self._plugins.items():
            try:
                plugin.on_unload()
            except Exception:
                logger.exception("Error while unloading plugin '{}'", plugin_id)
