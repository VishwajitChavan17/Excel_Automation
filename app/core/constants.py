"""
app.core.constants
===================
Central location for application-wide constants. Nothing in this file
should ever import from elsewhere in the application, to avoid circular
imports -- every other module is allowed to import from here.
"""

from __future__ import annotations

APP_NAME = "Excel Automation Studio"
APP_ORG = "Rolls-Royce Power Systems (MTU)"
APP_VERSION = "1.0.0"
APP_BUILD = "PHASE-6-RELEASE"

# Directories relative to the project root. Resolved to absolute paths at
# runtime by app.core.paths so packaged (PyInstaller) and source execution
# behave identically.
DIR_LOGS = "logs"
DIR_CONFIG = "config"
DIR_TEMPLATES = "templates"
DIR_WORKFLOWS = "workflows"
DIR_AUTOSAVE = "autosave"
FILE_SESSION = "session.json"
FILE_AUDIT_DB = "audit.db"
DIR_EXPORTS = "exports"
DIR_DATABASE = "database"
DIR_PLUGINS = "app/plugins"

SUPPORTED_EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".ods")

# Rows above this threshold trigger the Polars-backed fast-load path instead
# of pandas/openpyxl.
LARGE_FILE_ROW_THRESHOLD = 100_000

DEFAULT_THEME = "dark"
