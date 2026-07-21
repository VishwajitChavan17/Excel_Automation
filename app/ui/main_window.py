"""
app.ui.main_window
====================
The main dashboard window: ribbon on top, dockable Project Explorer
(left) and Properties (right) panels, a tabbed center workspace where every
loaded file / operation result gets its own Excel-like preview tab, a
bottom Console dock, and a status bar reporting current file/sheet/cell/
zoom/row-col counts plus background task progress.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core import constants, paths
from app.core.audit_log import AuditLog
from app.core.autosave_manager import (
    clear_autosave,
    has_pending_autosave,
    load_manifest,
    load_snapshot,
    snapshot_sheets,
)
from app.core.config_manager import ConfigManager
from app.core.plugin_manager import PluginManager
from app.core.session_manager import SessionState, clear_session, load_session, save_session
from app.core.workbook_registry import WorkbookRegistry
from app.services.excel.models import WorkbookHandle
from app.ui.panels.console_panel import ConsolePanel
from app.ui.panels.project_explorer import ProjectExplorerPanel
from app.ui.panels.properties_panel import PropertiesPanel
from app.ui.theme import stylesheet_for
from app.ui.widgets.excel_preview_widget import ExcelPreviewWidget
from app.ui.widgets.ribbon import Ribbon
from app.workers.file_load_worker import FileLoadWorker

ZOOM_STEPS = [70, 85, 100, 115, 130, 150, 175, 200]


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, plugin_manager: PluginManager, registry: WorkbookRegistry) -> None:
        super().__init__()
        self._config = config
        self._plugin_manager = plugin_manager
        self._registry = registry
        self._plugin_manager.attach_main_window(self)

        self._open_threads: list[QThread] = []
        self._open_workers: list[FileLoadWorker] = []  # prevents premature GC of workers mid-run
        self._tab_file_keys: dict[int, str] = {}  # workspace tab index -> registry key
        self._zoom_index = ZOOM_STEPS.index(100)

        self.setWindowTitle(f"{constants.APP_NAME} v{constants.APP_VERSION}")
        self.resize(config.get("window.width", 1600), config.get("window.height", 950))

        self._build_ribbon()
        self._build_center_workspace()
        self._build_dock_panels()
        self._build_status_bar()
        self._build_menu_bar()

        self._registry.history_changed.connect(self._on_history_changed)

        self._audit_log = AuditLog(paths.audit_db_path())
        self._registry.mutation_recorded.connect(self._on_mutation_recorded)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._perform_autosave)
        self._apply_autosave_settings()

        self.apply_theme(config.get("app.theme", constants.DEFAULT_THEME))

        if config.get("window.maximized", True):
            self.showMaximized()

        self.open_plugin_tab("home.dashboard")

        # Fires shortly after the window is visible, rather than blocking
        # construction with a modal dialog before the user sees anything.
        QTimer.singleShot(200, self._check_startup_recovery)

        logger.info("MainWindow initialized.")

    # -- construction ------------------------------------------------------

    def _build_ribbon(self) -> None:
        self._ribbon = Ribbon(self)
        self._ribbon.build_from_plugins(self._plugin_manager.plugins_by_category())
        self._ribbon.tool_activated.connect(self.open_plugin_tab)

        ribbon_dock = QDockWidget("", self)
        ribbon_dock.setObjectName("dock_ribbon")
        ribbon_dock.setWidget(self._ribbon)
        ribbon_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        empty_titlebar = QWidget()
        empty_titlebar.setFixedHeight(0)
        ribbon_dock.setTitleBarWidget(empty_titlebar)
        self.addDockWidget(Qt.TopDockWidgetArea, ribbon_dock)

    def _build_center_workspace(self) -> None:
        self._workspace = QTabWidget()
        self._workspace.setTabsClosable(True)
        self._workspace.setMovable(True)
        self._workspace.tabCloseRequested.connect(self._close_tab)
        self._workspace.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self._workspace)

    def _build_dock_panels(self) -> None:
        self._project_explorer = ProjectExplorerPanel()
        self._project_explorer.file_activated.connect(self._activate_file_tab)
        self._project_explorer.preview_requested.connect(self._activate_file_tab)
        self._project_explorer.rename_requested.connect(self._on_rename_file)
        self._project_explorer.reload_requested.connect(self._on_reload_file)
        self._project_explorer.close_requested.connect(self._on_close_file)
        self._project_explorer.export_requested.connect(self._on_export_file)
        self._project_explorer.duplicate_requested.connect(self._on_duplicate_file_tab)
        self._project_explorer.compare_with_requested.connect(self._on_compare_with)
        self._project_explorer.file_info_requested.connect(self._on_file_information)

        explorer_dock = QDockWidget("Project Explorer", self)
        explorer_dock.setObjectName("dock_project_explorer")
        explorer_dock.setWidget(self._project_explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, explorer_dock)

        self._properties_panel = PropertiesPanel()
        properties_dock = QDockWidget("Properties", self)
        properties_dock.setObjectName("dock_properties")
        properties_dock.setWidget(self._properties_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, properties_dock)

        self._console_panel = ConsolePanel()
        console_dock = QDockWidget("Console / Notifications", self)
        console_dock.setObjectName("dock_console")
        console_dock.setWidget(self._console_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, console_dock)

        self._view_menu_docks = {
            "Project Explorer": explorer_dock,
            "Properties": properties_dock,
            "Console / Notifications": console_dock,
        }

    def _build_status_bar(self) -> None:
        self._status_label = QLabel("Ready")
        self._current_file_label = QLabel("File: -")
        self._active_sheet_label = QLabel("Sheet: -")
        self._selected_cell_label = QLabel("Cell: -")
        self._rows_cols_label = QLabel("Rows: - | Cols: -")

        zoom_out_btn = QToolButton()
        zoom_out_btn.setText("-")
        zoom_out_btn.clicked.connect(lambda: self._change_zoom(-1))
        self._zoom_label = QLabel("Zoom: 100%")
        zoom_in_btn = QToolButton()
        zoom_in_btn.setText("+")
        zoom_in_btn.clicked.connect(lambda: self._change_zoom(1))

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(180)
        self._progress_bar.setVisible(False)

        status_bar = self.statusBar()
        status_bar.addWidget(self._status_label, 1)
        status_bar.addPermanentWidget(self._current_file_label)
        status_bar.addPermanentWidget(self._active_sheet_label)
        status_bar.addPermanentWidget(self._selected_cell_label)
        status_bar.addPermanentWidget(self._rows_cols_label)
        status_bar.addPermanentWidget(zoom_out_btn)
        status_bar.addPermanentWidget(self._zoom_label)
        status_bar.addPermanentWidget(zoom_in_btn)
        status_bar.addPermanentWidget(self._progress_bar)

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        open_action = QAction("&Open File(s)...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_files_dialog)
        file_menu.addAction(open_action)

        open_folder_action = QAction("Open &Folder...", self)
        open_folder_action.triggered.connect(self.open_folder_dialog)
        file_menu.addAction(open_folder_action)

        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menu_bar.addMenu("&Edit")
        self._undo_action = QAction("&Undo", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("&Redo", self)
        self._redo_action.setShortcut("Ctrl+Y")
        self._redo_action.setEnabled(False)
        self._redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menu_bar.addMenu("&View")
        for name, dock in self._view_menu_docks.items():
            toggle_action = dock.toggleViewAction()
            toggle_action.setText(name)
            view_menu.addAction(toggle_action)

        theme_menu = menu_bar.addMenu("&Theme")
        dark_action = QAction("Dark", self)
        dark_action.triggered.connect(lambda: self.apply_theme("dark"))
        light_action = QAction("Light", self)
        light_action.triggered.connect(lambda: self.apply_theme("light"))
        theme_menu.addAction(dark_action)
        theme_menu.addAction(light_action)

        help_menu = menu_bar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    # -- theme / zoom -----------------------------------------------------

    def apply_theme(self, theme_name: str) -> None:
        self.setStyleSheet(stylesheet_for(theme_name))
        self._config.set("app.theme", theme_name)

    def _change_zoom(self, direction: int) -> None:
        self._zoom_index = max(0, min(len(ZOOM_STEPS) - 1, self._zoom_index + direction))
        zoom_pct = ZOOM_STEPS[self._zoom_index]
        self._zoom_label.setText(f"Zoom: {zoom_pct}%")
        preview = self._current_preview_widget()
        if preview is not None:
            font = preview._table_view.font()
            font.setPointSizeF(max(6.0, 9.0 * zoom_pct / 100))
            preview._table_view.setFont(font)
            preview._table_view.resizeRowsToContents()

    # -- file loading ----------------------------------------------------

    def open_files_dialog(self) -> None:
        extensions = " ".join(f"*{ext}" for ext in constants.SUPPORTED_EXCEL_EXTENSIONS)
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "Open Excel / CSV Files", "", f"Supported Files ({extensions})"
        )
        if file_paths:
            self._load_files(file_paths)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        matches = [
            str(p)
            for p in Path(folder).iterdir()
            if p.suffix.lower() in constants.SUPPORTED_EXCEL_EXTENSIONS
        ]
        if not matches:
            QMessageBox.information(self, "No Files Found", "No supported files in that folder.")
            return
        self._load_files(matches)

    def _load_files(self, file_paths: list[str]) -> None:
        thread = QThread(self)
        worker = FileLoadWorker(file_paths)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.file_loaded.connect(self._on_file_loaded)
        worker.file_failed.connect(self._on_file_failed)
        worker.progress.connect(self._on_load_progress)
        worker.status_message.connect(self._status_label.setText)
        worker.finished.connect(lambda: self._on_load_finished(thread, worker))

        self._progress_bar.setVisible(True)
        self._progress_bar.setValue(0)
        self._open_threads.append(thread)
        self._open_workers.append(worker)  # keep alive -- see background_task module note
        thread.start()

    def _on_file_loaded(self, handle: WorkbookHandle, sheets: dict) -> None:
        key = self._registry.add(handle, sheets)
        self._project_explorer.add_loaded_file(handle)
        self._project_explorer.add_history_entry(f"Loaded {handle.display_name}")
        self._config.add_recent_file(key)
        self._console_panel.notify(f"Loaded {handle.display_name}", level="SUCCESS")
        self._audit_log.log(key, handle.active_sheet, f"Loaded {handle.display_name}")
        self._save_current_session()
        self._open_preview_tab(key)

    def _on_file_failed(self, file_path: str, error: str) -> None:
        self._console_panel.notify(f"Failed to load {Path(file_path).name}: {error}", level="ERROR")
        logger.error("File load failed: {} -- {}", file_path, error)

    def _on_load_progress(self, value: int) -> None:
        self._progress_bar.setValue(value)

    def _on_load_finished(self, thread: QThread, worker: FileLoadWorker) -> None:
        self._status_label.setText("Ready")
        self._progress_bar.setVisible(False)
        thread.quit()
        thread.wait()
        if thread in self._open_threads:
            self._open_threads.remove(thread)
        if worker in self._open_workers:
            self._open_workers.remove(worker)

    # -- workspace tabs -------------------------------------------------

    def _open_preview_tab(self, key: str, *, tab_title_suffix: str = "") -> None:
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        sheets = {name: self._registry.get_dataframe(key, name) for name in self._registry.get_sheet_names(key)}

        preview = ExcelPreviewWidget(sheets, active_sheet=handle.active_sheet)
        preview.cell_selected.connect(
            lambda row, col, value: self._selected_cell_label.setText(f"Cell: R{row + 1}C{col + 1} = {value[:24]}")
        )
        preview.sheet_changed.connect(lambda sheet_name: self._on_preview_sheet_changed(key, sheet_name))
        preview.row_count_changed.connect(
            lambda visible, total: self._rows_cols_label.setText(
                f"Rows: {visible:,}/{total:,} | Cols: {handle.column_count}"
            )
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(preview)
        container.setProperty("file_key", key)
        container.setProperty("preview_widget", preview)

        title = handle.display_name + tab_title_suffix
        index = self._workspace.addTab(container, title)
        self._tab_file_keys[index] = key
        self._workspace.setCurrentIndex(index)

    def _on_preview_sheet_changed(self, key: str, sheet_name: str) -> None:
        self._registry.set_active_sheet(key, sheet_name)
        self._refresh_status_and_properties_for_current_tab()

    def _current_preview_widget(self) -> ExcelPreviewWidget | None:
        widget = self._workspace.currentWidget()
        if widget is None:
            return None
        return widget.property("preview_widget")

    def _on_current_tab_changed(self, index: int) -> None:
        self._refresh_status_and_properties_for_current_tab()

    def _refresh_status_and_properties_for_current_tab(self) -> None:
        widget = self._workspace.currentWidget()
        key = widget.property("file_key") if widget is not None else None
        if not key:
            self._current_file_label.setText("File: -")
            self._active_sheet_label.setText("Sheet: -")
            self._rows_cols_label.setText("Rows: - | Cols: -")
            self._properties_panel.clear()
            return

        handle = self._registry.get_handle(key)
        if handle is None:
            return
        self._current_file_label.setText(f"File: {handle.display_name}")
        self._active_sheet_label.setText(f"Sheet: {handle.active_sheet}")
        self._rows_cols_label.setText(f"Rows: {handle.row_count:,} | Cols: {handle.column_count}")
        self._properties_panel.show_workbook(handle)

    def _activate_file_tab(self, file_path: str) -> None:
        for index in range(self._workspace.count()):
            if self._workspace.widget(index).property("file_key") == file_path:
                self._workspace.setCurrentIndex(index)
                return
        if self._registry.get_handle(file_path) is not None:
            self._open_preview_tab(file_path)

    def _close_tab(self, index: int) -> None:
        self._tab_file_keys.pop(index, None)
        self._workspace.removeTab(index)

    # -- public accessors for plugins ---------------------------------------

    @property
    def plugin_manager(self) -> PluginManager:
        return self._plugin_manager

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    def apply_autosave_settings(self) -> None:
        """Called by the Settings plugin after the user changes auto-save
        configuration, so the change takes effect immediately rather than
        only on next launch."""
        self._apply_autosave_settings()

    def register_generated_report(self, report_path: str) -> None:
        """Called by the Report Generator (and any future) plugin after
        writing a report file, so it shows up in Project Explorer -> Reports
        and gets a console notification -- keeps that bookkeeping out of
        plugin code."""
        self._project_explorer.add_report(report_path)
        self._console_panel.notify(f"Report generated: {Path(report_path).name}", level="SUCCESS")

    def open_plugin_tab(self, plugin_id: str):
        """Open (or focus, if already open) the tab for a given plugin. Returns
        the created widget, or None on failure -- callers like the Project
        Explorer's "Compare With..." action use the return value to pre-fill
        the new tool tab."""
        plugin = self._plugin_manager.get(plugin_id)
        if plugin is None:
            self._console_panel.notify(f"Plugin '{plugin_id}' not found.", level="ERROR")
            return None
        try:
            widget = plugin.create_widget(self)
            index = self._workspace.addTab(widget, plugin.metadata.display_name)
            self._workspace.setCurrentIndex(index)
            return widget
        except Exception:
            logger.exception("Failed to open plugin tab for {}", plugin_id)
            QMessageBox.critical(
                self, "Plugin Error", f"Could not open '{plugin_id}'. See logs for details."
            )
            return None

    # -- undo / redo -------------------------------------------------------

    def _on_undo(self) -> None:
        entry = self._registry.undo()
        if entry is not None:
            self._console_panel.notify(f"Undo: {entry.description}", level="INFO")

    def _on_redo(self) -> None:
        entry = self._registry.redo()
        if entry is not None:
            self._console_panel.notify(f"Redo: {entry.description}", level="INFO")

    def _on_history_changed(self) -> None:
        self._undo_action.setEnabled(self._registry.can_undo())
        self._redo_action.setEnabled(self._registry.can_redo())
        self._project_explorer.set_history_entries(self._registry.history_entries())
        self._refresh_open_preview_tabs()
        self._refresh_status_and_properties_for_current_tab()

    def _refresh_open_preview_tabs(self) -> None:
        """After an undo/redo, any already-open preview tab for the affected
        file must show the restored data -- ExcelPreviewWidget caches its
        own DataFrame reference and isn't otherwise notified of registry
        mutations."""
        for index in range(self._workspace.count()):
            widget = self._workspace.widget(index)
            key = widget.property("file_key")
            preview = widget.property("preview_widget")
            if not key or preview is None:
                continue
            for sheet_name in self._registry.get_sheet_names(key):
                df = self._registry.get_dataframe(key, sheet_name)
                if df is not None:
                    preview.set_sheet_data(sheet_name, df)

    # -- project explorer context menu handlers --------------------------

    def _on_rename_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        new_name, ok = QInputDialog.getText(self, "Rename File", "Display name:", text=handle.display_name)
        if ok and new_name:
            handle.display_name = new_name
            self._project_explorer.add_loaded_file(handle)
            for index in range(self._workspace.count()):
                if self._workspace.widget(index).property("file_key") == key:
                    self._workspace.setTabText(index, new_name)

    def _on_reload_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        self._console_panel.notify(f"Reloading {handle.display_name}...", level="INFO")
        self._load_files([str(handle.file_path)])

    def _on_close_file(self, key: str) -> None:
        for index in range(self._workspace.count()):
            if self._workspace.widget(index).property("file_key") == key:
                self._close_tab(index)
                break
        self._registry.remove(key)
        self._project_explorer.remove_loaded_file(key)
        self._save_current_session()

    def _on_export_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        df = self._registry.get_dataframe(key)
        if handle is None or df is None:
            return
        default_path = str(paths.exports_dir() / f"{Path(handle.display_name).stem}_export.xlsx")
        file_path, _ = QFileDialog.getSaveFileName(self, "Export File", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        df.to_excel(file_path, index=False)
        self._project_explorer.add_report(file_path)
        self._console_panel.notify(f"Exported {handle.display_name} to {file_path}", level="SUCCESS")

    def _on_duplicate_file_tab(self, key: str) -> None:
        self._open_preview_tab(key, tab_title_suffix=" (Copy)")

    def _on_compare_with(self, key: str) -> None:
        widget = self.open_plugin_tab("compare.excel_compare")
        if widget is not None and hasattr(widget, "preselect_master"):
            widget.preselect_master(key)

    def _on_file_information(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        QMessageBox.information(
            self,
            "File Information",
            f"<b>{handle.display_name}</b><br><br>"
            f"Path: {handle.file_path}<br>"
            f"Sheets: {handle.sheet_count}<br>"
            f"Active Sheet: {handle.active_sheet}<br>"
            f"Rows: {handle.row_count:,}<br>"
            f"Columns: {handle.column_count}<br>"
            f"Size: {handle.file_size_display}<br>"
            f"Last Modified: {handle.last_modified.strftime('%Y-%m-%d %H:%M') if handle.last_modified else '-'}<br>"
            f"Load Engine: {handle.engine_used}<br>"
            f"Duplicate Rows: {handle.duplicate_row_count:,}<br>"
            f"Blank Cells: {handle.blank_cell_count:,}",
        )

    # -- misc --------------------------------------------------------------

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"About {constants.APP_NAME}",
            f"<b>{constants.APP_NAME}</b><br>"
            f"Version {constants.APP_VERSION} ({constants.APP_BUILD})<br><br>"
            f"Rolls-Royce Power Systems (MTU) - Internal Engineering Tools",
        )

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._config.set("window.width", self.width())
        self._config.set("window.height", self.height())
        self._config.set("window.maximized", self.isMaximized())
        self._plugin_manager.shutdown()

        loaded_paths = [str(h.file_path) for h in self._registry.all_handles()]
        save_session(SessionState(loaded_files=loaded_paths, clean_shutdown=True), paths.session_file())
        clear_autosave(paths.autosave_dir())

        logger.info("Application shutting down cleanly.")
        super().closeEvent(event)

    # -- enterprise hardening: audit log / autosave / session recovery -----

    def _on_mutation_recorded(self, file_key: str, sheet_name: str, description: str) -> None:
        self._audit_log.log(file_key, sheet_name, description)

    def _save_current_session(self) -> None:
        loaded_paths = [str(h.file_path) for h in self._registry.all_handles()]
        save_session(SessionState(loaded_files=loaded_paths, clean_shutdown=False), paths.session_file())

    def _apply_autosave_settings(self) -> None:
        enabled = self._config.get("app.auto_save_enabled", True)
        interval_seconds = self._config.get("app.auto_save_interval_seconds", 120)
        self._autosave_timer.stop()
        if enabled and interval_seconds > 0:
            self._autosave_timer.start(int(interval_seconds) * 1000)

    def _perform_autosave(self) -> None:
        keys = self._registry.keys()
        if not keys:
            return
        sheets = []
        for key in keys:
            handle = self._registry.get_handle(key)
            if handle is None:
                continue
            for sheet_name in self._registry.get_sheet_names(key):
                df = self._registry.get_dataframe(key, sheet_name)
                if df is not None:
                    sheets.append((key, sheet_name, handle.display_name, df))
        if sheets:
            snapshot_sheets(sheets, paths.autosave_dir())
            logger.debug("Autosave: {} sheet(s) snapshotted", len(sheets))

    def _check_startup_recovery(self) -> None:
        session_path = paths.session_file()
        autosave_directory = paths.autosave_dir()
        previous = load_session(session_path)

        if previous is not None and not previous.clean_shutdown and has_pending_autosave(autosave_directory):
            manifest = load_manifest(autosave_directory)
            confirm = QMessageBox.question(
                self,
                "Recover Unsaved Work",
                f"{constants.APP_NAME} didn't close cleanly last time.\n\n"
                f"Recover {len(manifest)} sheet(s) with unsaved changes from autosave?",
            )
            if confirm == QMessageBox.Yes:
                self._recover_from_autosave(manifest, autosave_directory)
                self._console_panel.notify(f"Recovered {len(manifest)} sheet(s) from autosave.", level="SUCCESS")
                self._save_current_session()
                return
            else:
                clear_autosave(autosave_directory)

        elif (
            previous is not None
            and previous.loaded_files
            and self._config.get("app.restore_last_session", True)
        ):
            confirm = QMessageBox.question(
                self,
                "Restore Previous Session",
                f"Reopen the {len(previous.loaded_files)} file(s) from your last session?",
            )
            if confirm == QMessageBox.Yes:
                existing = [p for p in previous.loaded_files if Path(p).exists()]
                if existing:
                    self._load_files(existing)

        self._save_current_session()

    def _recover_from_autosave(self, manifest, directory) -> None:
        from app.services.excel.loader_service import load_workbook_all_sheets

        file_keys = {entry.file_key for entry in manifest}
        for file_key in file_keys:
            source_path = Path(file_key)
            if not source_path.exists():
                logger.warning("Autosave recovery: original file no longer exists: {}", source_path)
                continue
            try:
                handle, sheets = load_workbook_all_sheets(source_path)
            except Exception:
                logger.exception("Autosave recovery: failed to reload {}", source_path)
                continue

            registry_key = self._registry.add(handle, sheets)
            self._project_explorer.add_loaded_file(handle)
            self._open_preview_tab(registry_key)

            for entry in manifest:
                if entry.file_key != file_key:
                    continue
                recovered_df = load_snapshot(entry, directory)
                if recovered_df is not None:
                    self._registry.replace_sheet_data(
                        registry_key, entry.sheet_name, recovered_df, description="Recovered from autosave"
                    )
