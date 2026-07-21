"""
Excel Automation Studio -- entry point.

Startup sequence (mirrors the splash screen requirements):
  1. Create QApplication
  2. Show splash screen
  3. Configure logging
  4. Check dependencies
  5. Load configuration
  6. Discover & load plugins
  7. Build and show the main window
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core import constants
from app.core.config_manager import get_config
from app.core.logging_setup import configure_logging
from app.core.plugin_manager import PluginManager


REQUIRED_MODULES = (
    "PySide6",
    "pandas",
    "polars",
    "openpyxl",
    "numpy",
    "loguru",
    "yaml",
    "xlsxwriter",
)


def check_dependencies() -> list[str]:
    """Return a list of missing required module names (empty = all present)."""
    import importlib

    missing = []
    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError:
            missing.append(module_name)
    return missing


def main() -> int:
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName(constants.APP_NAME)
    app.setOrganizationName(constants.APP_ORG)
    app.setApplicationVersion(constants.APP_VERSION)

    from app.ui.splash_screen import StudioSplashScreen

    splash = StudioSplashScreen()
    splash.show()
    app.processEvents()

    splash.show_status("Configuring logging...")
    configure_logging(console=True, debug=False)

    from loguru import logger

    logger.info("Starting {} v{}", constants.APP_NAME, constants.APP_VERSION)

    splash.show_status("Checking dependencies...")
    missing = check_dependencies()
    if missing:
        from PySide6.QtWidgets import QMessageBox

        splash.close()
        QMessageBox.critical(
            None,
            "Missing Dependencies",
            "The following required packages are missing:\n\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nInstall them via: pip install -r requirements.txt",
        )
        return 1

    splash.show_status("Loading configuration...")
    config = get_config()

    from app.core.workbook_registry import WorkbookRegistry

    registry = WorkbookRegistry()

    splash.show_status("Loading plugins...")
    plugin_manager = PluginManager(config, registry)
    plugin_manager.discover_and_load()

    splash.show_status("Loading templates...")
    # Template engine lands in Phase 4; placeholder status message kept here
    # so the splash sequence matches the spec even before that phase exists.

    splash.show_status("Starting dashboard...")
    from app.ui.main_window import MainWindow

    window = MainWindow(config, plugin_manager, registry)
    window.show()
    splash.finish(window)

    logger.info("Startup complete.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
