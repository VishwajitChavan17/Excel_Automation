"""
app.plugins.settings_tool
============================
The real Enterprise Settings tab, replacing the Phase 1-4 "coming soon"
placeholder: a Plugin Manager (view every discovered plugin and load
error, enable/disable for next launch), Performance tuning (worker
threads, large-file threshold), Auto-Save / Session Restore configuration,
and a searchable, exportable Audit Log viewer backed by the persistent
SQLite audit trail.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata


class PluginManagerTab(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Every plugin discovered at startup. Disabling one takes effect on next launch."))

        self._plugins_table = QTableWidget(0, 5)
        self._plugins_table.setHorizontalHeaderLabels(["Enabled", "Plugin ID", "Name", "Category", "Version"])
        self._plugins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self._plugins_table, 1)

        if self._context.main_window is not None:
            plugin_manager = self._context.main_window.plugin_manager
            self._populate(plugin_manager)

            if plugin_manager.load_errors():
                layout.addWidget(QLabel("Load Errors:"))
                errors_table = QTableWidget(0, 2)
                errors_table.setHorizontalHeaderLabels(["Module", "Error"])
                errors_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
                errors_table.setRowCount(len(plugin_manager.load_errors()))
                for row, err in enumerate(plugin_manager.load_errors()):
                    errors_table.setItem(row, 0, QTableWidgetItem(err.module_name))
                    errors_table.setItem(row, 1, QTableWidgetItem(err.error))
                layout.addWidget(errors_table)

    def _populate(self, plugin_manager) -> None:
        config = self._context.config
        disabled = set(config.get("plugins.disabled", []) or [])
        plugins = sorted(plugin_manager.all_plugins(), key=lambda p: p.metadata.plugin_id)

        self._plugins_table.setRowCount(len(plugins))
        for row, plugin in enumerate(plugins):
            checkbox = QCheckBox()
            checkbox.setChecked(plugin.metadata.plugin_id not in disabled)
            checkbox.toggled.connect(lambda checked, pid=plugin.metadata.plugin_id: self._on_toggle(pid, checked))
            cell_container = QWidget()
            cell_layout = QHBoxLayout(cell_container)
            cell_layout.addWidget(checkbox)
            cell_layout.setAlignment(checkbox, Qt.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            self._plugins_table.setCellWidget(row, 0, cell_container)

            self._plugins_table.setItem(row, 1, QTableWidgetItem(plugin.metadata.plugin_id))
            self._plugins_table.setItem(row, 2, QTableWidgetItem(plugin.metadata.display_name))
            self._plugins_table.setItem(row, 3, QTableWidgetItem(plugin.metadata.category.value))
            self._plugins_table.setItem(row, 4, QTableWidgetItem(plugin.metadata.version))

    def _on_toggle(self, plugin_id: str, enabled: bool) -> None:
        config = self._context.config
        disabled = set(config.get("plugins.disabled", []) or [])
        if enabled:
            disabled.discard(plugin_id)
        else:
            disabled.add(plugin_id)
        config.set("plugins.disabled", sorted(disabled))


class PerformanceTab(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._config = context.config

        layout = QVBoxLayout(self)
        box = QGroupBox("Performance Tuning")
        box_layout = QVBoxLayout(box)

        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("Large-file row threshold (switches CSV/TSV loading to Polars):"))
        self._threshold_spin = QSpinBox()
        self._threshold_spin.setRange(1_000, 5_000_000)
        self._threshold_spin.setSingleStep(10_000)
        self._threshold_spin.setValue(self._config.get("performance.large_file_row_threshold", 100_000))
        self._threshold_spin.valueChanged.connect(
            lambda v: self._config.set("performance.large_file_row_threshold", v)
        )
        threshold_row.addWidget(self._threshold_spin)
        box_layout.addLayout(threshold_row)

        threads_row = QHBoxLayout()
        threads_row.addWidget(QLabel("Max background worker threads:"))
        self._threads_spin = QSpinBox()
        self._threads_spin.setRange(1, 32)
        self._threads_spin.setValue(self._config.get("performance.max_worker_threads", 4))
        self._threads_spin.valueChanged.connect(lambda v: self._config.set("performance.max_worker_threads", v))
        threads_row.addWidget(self._threads_spin)
        box_layout.addLayout(threads_row)

        self._polars_checkbox = QCheckBox("Use Polars automatically for large CSV/TSV files")
        self._polars_checkbox.setChecked(self._config.get("performance.use_polars_for_large_files", True))
        self._polars_checkbox.toggled.connect(
            lambda checked: self._config.set("performance.use_polars_for_large_files", checked)
        )
        box_layout.addWidget(self._polars_checkbox)

        layout.addWidget(box)
        layout.addStretch(1)


class AutoSaveSessionTab(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._config = context.config
        self._context = context

        layout = QVBoxLayout(self)

        autosave_box = QGroupBox("Auto-Save & Crash Recovery")
        autosave_layout = QVBoxLayout(autosave_box)

        self._autosave_checkbox = QCheckBox("Enable periodic auto-save (recovers unsaved edits after a crash)")
        self._autosave_checkbox.setChecked(self._config.get("app.auto_save_enabled", True))
        self._autosave_checkbox.toggled.connect(self._on_autosave_toggled)
        autosave_layout.addWidget(self._autosave_checkbox)

        interval_row = QHBoxLayout()
        interval_row.addWidget(QLabel("Auto-save interval (seconds):"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(10, 3600)
        self._interval_spin.setValue(self._config.get("app.auto_save_interval_seconds", 120))
        self._interval_spin.valueChanged.connect(self._on_interval_changed)
        interval_row.addWidget(self._interval_spin)
        autosave_layout.addLayout(interval_row)

        clear_button = QPushButton("Clear Autosave Data Now")
        clear_button.clicked.connect(self._on_clear_autosave)
        autosave_layout.addWidget(clear_button)

        layout.addWidget(autosave_box)

        session_box = QGroupBox("Session")
        session_layout = QVBoxLayout(session_box)
        self._restore_checkbox = QCheckBox("Offer to restore the previous session's open files on startup")
        self._restore_checkbox.setChecked(self._config.get("app.restore_last_session", True))
        self._restore_checkbox.toggled.connect(lambda checked: self._config.set("app.restore_last_session", checked))
        session_layout.addWidget(self._restore_checkbox)
        layout.addWidget(session_box)

        layout.addStretch(1)

    def _on_autosave_toggled(self, checked: bool) -> None:
        self._config.set("app.auto_save_enabled", checked)
        self._apply_to_main_window()

    def _on_interval_changed(self, value: int) -> None:
        self._config.set("app.auto_save_interval_seconds", value)
        self._apply_to_main_window()

    def _apply_to_main_window(self) -> None:
        if self._context.main_window is not None:
            self._context.main_window.apply_autosave_settings()

    def _on_clear_autosave(self) -> None:
        from app.core.autosave_manager import clear_autosave

        clear_autosave(paths.autosave_dir())
        QMessageBox.information(self, "Autosave Cleared", "Autosave data has been cleared.")


class AuditLogTab(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search audit log...")
        self._search_box.textChanged.connect(self._refresh)
        toolbar.addWidget(self._search_box, 1)

        export_button = QPushButton("Export to Excel")
        export_button.clicked.connect(self._on_export)
        toolbar.addWidget(export_button)

        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self._on_clear)
        toolbar.addWidget(clear_button)
        layout.addLayout(toolbar)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Timestamp", "File", "Sheet", "Operation"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._table, 1)

        self._count_label = QLabel("")
        layout.addWidget(self._count_label)

        self._refresh()

    def _audit_log(self):
        return self._context.main_window.audit_log if self._context.main_window is not None else None

    def _refresh(self) -> None:
        audit_log = self._audit_log()
        if audit_log is None:
            return
        entries = audit_log.query(limit=500, search=self._search_box.text() or None)
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [entry.timestamp, entry.file_key, entry.sheet_name, entry.operation]
            for col, value in enumerate(values):
                self._table.setItem(row, col, QTableWidgetItem(value))
        self._count_label.setText(f"{len(entries)} entr(y/ies) shown ({audit_log.count()} total in log).")

    def _on_export(self) -> None:
        audit_log = self._audit_log()
        if audit_log is None:
            return
        from app.core.audit_log import export_audit_log_excel

        entries = audit_log.query(limit=10_000, search=self._search_box.text() or None)
        if not entries:
            QMessageBox.information(self, "Audit Log", "No entries to export.")
            return
        default_name = f"Audit_Log_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Audit Log", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_audit_log_excel(entries, file_path)
            QMessageBox.information(self, "Export Complete", f"Audit log saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export audit log")
            QMessageBox.critical(self, "Export Failed", str(exc))

    def _on_clear(self) -> None:
        audit_log = self._audit_log()
        if audit_log is None:
            return
        confirm = QMessageBox.question(self, "Clear Audit Log", "Permanently delete every audit log entry?")
        if confirm == QMessageBox.Yes:
            audit_log.clear()
            self._refresh()


class SettingsWidget(QTabWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.addTab(PluginManagerTab(context, self), "Plugin Manager")
        self.addTab(PerformanceTab(context, self), "Performance")
        self.addTab(AutoSaveSessionTab(context, self), "Auto-Save & Session")
        self.addTab(AuditLogTab(context, self), "Audit Log")


class SettingsPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="settings.panel",
        display_name="Application Settings",
        category=PluginCategory.SETTINGS,
        description="Plugin manager, performance tuning, auto-save/session config, and the audit log.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return SettingsWidget(self.context, parent)
