from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QToolBar,
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
from app.core.session_manager import SessionState, save_session
from app.core.workbook_registry import WorkbookRegistry
from app.services.excel.models import WorkbookHandle
from app.ui.home_dashboard import HomeDashboard
from app.ui.panels.console_panel import ConsolePanel
from app.ui.panels.project_explorer import ProjectExplorerPanel
from app.ui.panels.properties_panel import PropertiesPanel
from app.ui.theme import stylesheet_for
from app.ui.widgets.command_palette import CommandPalette
from app.ui.widgets.excel_preview_widget import ExcelPreviewWidget
from app.ui.widgets.ribbon import Ribbon
from app.workers.file_load_worker import FileLoadWorker

ZOOM_STEPS = [70, 85, 100, 115, 130, 150, 175, 200]
HOME_DASHBOARD_ID = "__home_dashboard__"

QAT_STYLE = """
QPushButton {
    color: #969696; font-size: 11px; padding: 4px 8px;
    border: 1px solid transparent; border-radius: 3px;
    background: transparent;
}
QPushButton:hover { color: #cccccc; background-color: #2a2d2e; border-color: #3c3c3c; }
QPushButton:pressed { background-color: #383838; }
QPushButton:disabled { color: #555555; }
"""


class MainWindow(QMainWindow):
    def __init__(self, config: ConfigManager, plugin_manager: PluginManager, registry: WorkbookRegistry) -> None:
        super().__init__()
        self._config = config
        self._plugin_manager = plugin_manager
        self._registry = registry
        self._plugin_manager.attach_main_window(self)

        self._open_threads: list[QThread] = []
        self._open_workers: list[FileLoadWorker] = []
        self._tab_file_keys: dict[int, str] = {}
        self._zoom_index = ZOOM_STEPS.index(100)
        self._activity_log: list[tuple[str, str, str]] = []  # (time, description, type)

        self.setWindowTitle(f"{constants.APP_NAME} v{constants.APP_VERSION}")
        self.setMinimumSize(1024, 680)
        self.resize(config.get("window.width", 1600), config.get("window.height", 950))

        self._build_quick_access_toolbar()
        self._build_ribbon()
        self._build_center_workspace()
        self._build_dock_panels()
        self._build_status_bar()
        self._build_menu_bar()

        self._registry.history_changed.connect(self._on_history_changed)
        self._registry.workbook_added.connect(self._on_workbook_list_changed)
        self._registry.workbook_removed.connect(self._on_workbook_list_changed)

        self._audit_log = AuditLog(paths.audit_db_path())
        self._registry.mutation_recorded.connect(self._on_mutation_recorded)

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._perform_autosave)
        self._apply_autosave_settings()

        self.apply_theme(config.get("app.theme", constants.DEFAULT_THEME))

        if config.get("window.maximized", True):
            self.showMaximized()

        self.open_home_dashboard()

        QTimer.singleShot(200, self._check_startup_recovery)
        logger.info("MainWindow initialized.")

    # ── Quick Access Toolbar ───────────────────────────────────────────

    def _build_quick_access_toolbar(self) -> None:
        qat = QToolBar("Quick Access")
        qat.setObjectName("quickAccess")
        qat.setMovable(False)
        qat.setStyleSheet("QToolBar { border: none; border-bottom: 1px solid #3c3c3c; padding: 2px 6px; spacing: 1px; }")

        self._qat_home = self._qat_btn("\u2302", "Home")
        self._qat_home.clicked.connect(self.open_home_dashboard)
        qat.addWidget(self._qat_home)

        qat.addSeparator()

        self._qat_undo = self._qat_btn("\u21B6", "Undo Ctrl+Z")
        self._qat_undo.setEnabled(False)
        self._qat_undo.clicked.connect(self._on_undo)
        qat.addWidget(self._qat_undo)

        self._qat_redo = self._qat_btn("\u21B7", "Redo Ctrl+Y")
        self._qat_redo.setEnabled(False)
        self._qat_redo.clicked.connect(self._on_redo)
        qat.addWidget(self._qat_redo)

        qat.addSeparator()

        open_btn = self._qat_btn("\u25C9", "Open Files Ctrl+O")
        open_btn.clicked.connect(self.open_files_dialog)
        qat.addWidget(open_btn)

        save_btn = self._qat_btn("\u2714", "Save Session")
        save_btn.clicked.connect(self._save_current_session)
        qat.addWidget(save_btn)

        qat.addSeparator()

        cmd_btn = self._qat_btn("\u2315", "Command Palette Ctrl+K")
        cmd_btn.clicked.connect(self._open_command_palette)
        qat.addWidget(cmd_btn)

        # Spacer + search on right
        search_widget = QWidget()
        search_layout = QHBoxLayout(search_widget)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(4)

        cmd_hint = QLabel("\u2315")
        cmd_hint.setStyleSheet("color: #555555; font-size: 11px;")
        cmd_hint.setToolTip("Ctrl+K to open Command Palette")
        search_layout.addWidget(cmd_hint)

        cmd_label = QLabel("Quick Search (Ctrl+K)")
        cmd_label.setStyleSheet("color: #3c3c3c; font-size: 11px; padding: 4px 0;")
        search_layout.addWidget(cmd_label)

        qat.addWidget(search_widget)

        self.addToolBar(Qt.TopToolBarArea, qat)

    def _qat_btn(self, icon: str, tip: str = "") -> QPushButton:
        btn = QPushButton(icon)
        btn.setToolTip(tip)
        btn.setStyleSheet(QAT_STYLE)
        return btn

    # ── Ribbon ─────────────────────────────────────────────────────────

    def _build_ribbon(self) -> None:
        self._ribbon = Ribbon(self)
        self._ribbon.build_from_plugins(self._plugin_manager.plugins_by_category())
        self._ribbon.tool_activated.connect(self._on_ribbon_command)

        ribbon_dock = QDockWidget("", self)
        ribbon_dock.setObjectName("dock_ribbon")
        ribbon_dock.setWidget(self._ribbon)
        ribbon_dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        empty_titlebar = QWidget()
        empty_titlebar.setFixedHeight(0)
        ribbon_dock.setTitleBarWidget(empty_titlebar)
        self.addDockWidget(Qt.TopDockWidgetArea, ribbon_dock)

    def _on_ribbon_command(self, plugin_id: str) -> None:
        self._log_activity(f"Command: {plugin_id}", "command")
        self.open_plugin_tab(plugin_id)

    # ── Center Workspace ───────────────────────────────────────────────

    def _build_center_workspace(self) -> None:
        self._workspace = QTabWidget()
        self._workspace.setTabsClosable(True)
        self._workspace.setMovable(True)
        self._workspace.setElideMode(Qt.ElideRight)
        self._workspace.tabCloseRequested.connect(self._close_tab)
        self._workspace.currentChanged.connect(self._on_current_tab_changed)
        self.setCentralWidget(self._workspace)

    # ── Dock Panels ────────────────────────────────────────────────────

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

        explorer_dock = QDockWidget("EXPLORER", self)
        explorer_dock.setObjectName("dock_project_explorer")
        explorer_dock.setWidget(self._project_explorer)
        self.addDockWidget(Qt.LeftDockWidgetArea, explorer_dock)

        self._properties_panel = PropertiesPanel()
        properties_dock = QDockWidget("PROPERTIES", self)
        properties_dock.setObjectName("dock_properties")
        properties_dock.setWidget(self._properties_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, properties_dock)

        self._console_panel = ConsolePanel()
        console_dock = QDockWidget("OUTPUT", self)
        console_dock.setObjectName("dock_console")
        console_dock.setWidget(self._console_panel)
        self.addDockWidget(Qt.BottomDockWidgetArea, console_dock)

        self._view_menu_docks = {
            "EXPLORER": explorer_dock,
            "PROPERTIES": properties_dock,
            "OUTPUT": console_dock,
        }

        # Tabify explorer and properties so they share space if needed
        self.tabifyDockWidget(explorer_dock, properties_dock)

    # ── Status Bar ─────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        self._status_label = QLabel("Ready")
        self._current_file_label = QLabel("")
        self._current_file_label.setMinimumWidth(100)
        self._active_sheet_label = QLabel("")
        self._selected_cell_label = QLabel("")
        self._rows_cols_label = QLabel("")

        zoom_out_btn = QPushButton("\u2212")
        zoom_out_btn.setFixedSize(22, 20)
        zoom_out_btn.setToolTip("Zoom out")
        zoom_out_btn.clicked.connect(lambda: self._change_zoom(-1))
        self._zoom_label = QLabel("100%")
        self._zoom_label.setToolTip("Zoom level")
        self._zoom_label.setMinimumWidth(38)
        self._zoom_label.setAlignment(Qt.AlignCenter)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(22, 20)
        zoom_in_btn.setToolTip("Zoom in")
        zoom_in_btn.clicked.connect(lambda: self._change_zoom(1))

        self._progress_bar = QProgressBar()
        self._progress_bar.setMaximumWidth(140)
        self._progress_bar.setFixedHeight(16)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setVisible(False)

        bar = self.statusBar()
        bar.addWidget(self._status_label, 1)
        bar.addPermanentWidget(self._current_file_label)
        bar.addPermanentWidget(self._active_sheet_label)
        bar.addPermanentWidget(self._selected_cell_label)
        bar.addPermanentWidget(self._rows_cols_label)
        bar.addPermanentWidget(self._progress_bar)
        bar.addPermanentWidget(zoom_out_btn)
        bar.addPermanentWidget(self._zoom_label)
        bar.addPermanentWidget(zoom_in_btn)

    # ── Menu Bar ───────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        a = QAction("\u25C9  Open File(s)...", self)
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self.open_files_dialog)
        file_menu.addAction(a)

        a = QAction("\u25B8  Open Folder...", self)
        a.triggered.connect(self.open_folder_dialog)
        file_menu.addAction(a)
        file_menu.addSeparator()

        a = QAction("\u21B6  Command Palette...", self)
        a.setShortcut("Ctrl+K")
        a.triggered.connect(self._open_command_palette)
        file_menu.addAction(a)
        file_menu.addSeparator()

        a = QAction("E&xit", self)
        a.triggered.connect(self.close)
        file_menu.addAction(a)

        edit_menu = menu_bar.addMenu("&Edit")
        self._undo_action = QAction("\u21B6  &Undo", self)
        self._undo_action.setShortcut("Ctrl+Z")
        self._undo_action.setEnabled(False)
        self._undo_action.triggered.connect(self._on_undo)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction("\u21B7  &Redo", self)
        self._redo_action.setShortcut("Ctrl+Y")
        self._redo_action.setEnabled(False)
        self._redo_action.triggered.connect(self._on_redo)
        edit_menu.addAction(self._redo_action)

        view_menu = menu_bar.addMenu("&View")
        for name, dock in self._view_menu_docks.items():
            ta = dock.toggleViewAction()
            ta.setText(name.title())
            view_menu.addAction(ta)

        theme_menu = menu_bar.addMenu("&Theme")
        for t in ("dark", "light"):
            a = QAction(t.title(), self)
            a.triggered.connect(lambda _ch=False, tt=t: self.apply_theme(tt))
            theme_menu.addAction(a)

        help_menu = menu_bar.addMenu("&Help")
        a = QAction("&About", self)
        a.triggered.connect(self._show_about)
        help_menu.addAction(a)

    # ── Home Dashboard ─────────────────────────────────────────────────

    def open_home_dashboard(self) -> None:
        for i in range(self._workspace.count()):
            w = self._workspace.widget(i)
            if w and w.property("file_key") == HOME_DASHBOARD_ID:
                self._workspace.setCurrentIndex(i)
                return

        dashboard = HomeDashboard()
        dashboard.open_file_requested.connect(self.open_files_dialog)
        dashboard.open_folder_requested.connect(self.open_folder_dialog)
        dashboard.open_recent_file.connect(lambda p: self._load_files([str(p)]))

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(dashboard)
        container.setProperty("file_key", HOME_DASHBOARD_ID)

        idx = self._workspace.addTab(container, "\u2302  Home")
        self._workspace.setCurrentIndex(idx)

        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        for i in range(self._workspace.count()):
            w = self._workspace.widget(i)
            if w and w.property("file_key") == HOME_DASHBOARD_ID:
                dash = w.findChild(HomeDashboard)
                if dash:
                    handles = self._registry.all_handles()
                    total_sheets = sum(h.sheet_count for h in handles)
                    dash.set_metrics(
                        files=len(handles),
                        sheets=total_sheets,
                        operations=len(self._registry.history_entries()),
                        reports=0,
                    )
                    recent = self._config.get("recent.files", [])
                    dash.set_recent_files([(p, Path(p).name) for p in recent[:10]])
                    dash.set_activity(self._activity_log[-20:])

    # ── Command Palette ────────────────────────────────────────────────

    def _open_command_palette(self) -> None:
        commands = []
        for pid, plugin in self._plugin_manager.all().items():
            cat = plugin.metadata.category.value if hasattr(plugin.metadata.category, "value") else str(plugin.metadata.category)
            commands.append((pid, plugin.metadata.display_name, cat))
        commands.sort(key=lambda x: x[1])

        palette = CommandPalette(commands, self)
        palette.command_activated.connect(self._on_ribbon_command)
        palette.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.Popup)
        palette.setAttribute(Qt.WA_TranslucentBackground, False)
        # Center over the main window
        parent_rect = self.geometry()
        pw, ph = 560, 420
        px = parent_rect.x() + (parent_rect.width() - pw) // 2
        py = parent_rect.y() + (parent_rect.height() - ph) // 3
        palette.setGeometry(px, py, pw, ph)
        palette.exec()

    # ── Keyboard shortcut override ─────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence("Ctrl+K")):
            self._open_command_palette()
            return
        super().keyPressEvent(event)

    # ── Theme / Zoom ───────────────────────────────────────────────────

    def apply_theme(self, theme_name: str) -> None:
        self.setStyleSheet(stylesheet_for(theme_name))
        self._config.set("app.theme", theme_name)

    def _change_zoom(self, direction: int) -> None:
        self._zoom_index = max(0, min(len(ZOOM_STEPS) - 1, self._zoom_index + direction))
        zoom_pct = ZOOM_STEPS[self._zoom_index]
        self._zoom_label.setText(f"{zoom_pct}%")
        preview = self._current_preview_widget()
        if preview is not None:
            font = preview._table_view.font()
            font.setPointSizeF(max(6.0, 9.0 * zoom_pct / 100))
            preview._table_view.setFont(font)
            preview._table_view.resizeRowsToContents()

    # ── File Loading ───────────────────────────────────────────────────

    def open_files_dialog(self) -> None:
        exts = " ".join(f"*{e}" for e in constants.SUPPORTED_EXCEL_EXTENSIONS)
        paths_list, _ = QFileDialog.getOpenFileNames(
            self, "Open Excel / CSV Files", "", f"Supported Files ({exts})"
        )
        if paths_list:
            self._load_files(paths_list)

    def open_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        matches = [
            str(p) for p in Path(folder).iterdir()
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
        self._open_workers.append(worker)
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
        self._log_activity(f"Loaded {handle.display_name}", "file")
        self._refresh_dashboard()

    def _on_file_failed(self, file_path: str, error: str) -> None:
        self._console_panel.notify(f"Failed: {Path(file_path).name} — {error}", level="ERROR")
        logger.error("File load failed: {} — {}", file_path, error)

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

    # ── Workspace Tabs ─────────────────────────────────────────────────

    def _open_preview_tab(self, key: str, *, tab_title_suffix: str = "") -> None:
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        sheets = {n: self._registry.get_dataframe(key, n) for n in self._registry.get_sheet_names(key)}

        preview = ExcelPreviewWidget(sheets, active_sheet=handle.active_sheet)
        preview.cell_selected.connect(
            lambda row, col, val: self._selected_cell_label.setText(f"R{row+1}C{col+1} = {val[:24]}")
        )
        preview.sheet_changed.connect(lambda sn: self._on_preview_sheet_changed(key, sn))
        preview.row_count_changed.connect(
            lambda vis, tot: self._rows_cols_label.setText(f"{vis:,} / {tot:,} rows")
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(preview)
        container.setProperty("file_key", key)
        container.setProperty("preview_widget", preview)

        title = handle.display_name + tab_title_suffix
        idx = self._workspace.addTab(container, title)
        self._tab_file_keys[idx] = key
        self._workspace.setCurrentIndex(idx)

    def _on_preview_sheet_changed(self, key: str, sheet_name: str) -> None:
        self._registry.set_active_sheet(key, sheet_name)
        self._refresh_status_and_properties_for_current_tab()

    def _current_preview_widget(self) -> ExcelPreviewWidget | None:
        w = self._workspace.currentWidget()
        return w.property("preview_widget") if w else None

    def _on_current_tab_changed(self, index: int) -> None:
        self._refresh_status_and_properties_for_current_tab()

    def _refresh_status_and_properties_for_current_tab(self) -> None:
        w = self._workspace.currentWidget()
        key = w.property("file_key") if w is not None else None
        if not key or key == HOME_DASHBOARD_ID:
            self._current_file_label.setText("")
            self._active_sheet_label.setText("")
            self._rows_cols_label.setText("")
            self._selected_cell_label.setText("")
            self._properties_panel.clear()
            return
        handle = self._registry.get_handle(key)
        if handle is None:
            return
        self._current_file_label.setText(handle.display_name)
        self._active_sheet_label.setText(handle.active_sheet)
        self._rows_cols_label.setText(f"{handle.row_count:,} \u00d7 {handle.column_count:,}")
        self._properties_panel.show_workbook(handle)

    def _activate_file_tab(self, file_path: str) -> None:
        for i in range(self._workspace.count()):
            if self._workspace.widget(i).property("file_key") == file_path:
                self._workspace.setCurrentIndex(i)
                return
        if self._registry.get_handle(file_path) is not None:
            self._open_preview_tab(file_path)

    def _close_tab(self, index: int) -> None:
        w = self._workspace.widget(index)
        if w and w.property("file_key") == HOME_DASHBOARD_ID:
            return
        if w and w.property("has_unsaved_changes"):
            name = self._workspace.tabText(index)
            confirm = QMessageBox.question(
                self, "Unsaved Changes",
                f"'{name}' has unsaved changes.\nClose without saving?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return
        self._tab_file_keys.pop(index, None)
        self._workspace.removeTab(index)

    # ── Activity Logging ───────────────────────────────────────────────

    def _log_activity(self, description: str, activity_type: str = "info") -> None:
        now = datetime.now().strftime("%H:%M")
        self._activity_log.append((now, description, activity_type))
        if len(self._activity_log) > 200:
            self._activity_log = self._activity_log[-200:]

    def _on_workbook_list_changed(self, _key: str = "") -> None:
        self._refresh_dashboard()

    # ── Plugin Tab Router ──────────────────────────────────────────────

    @property
    def plugin_manager(self) -> PluginManager:
        return self._plugin_manager

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    def apply_autosave_settings(self) -> None:
        self._apply_autosave_settings()

    def register_generated_report(self, report_path: str) -> None:
        self._project_explorer.add_report(report_path)
        self._console_panel.notify(f"Report: {Path(report_path).name}", level="SUCCESS")
        self._log_activity(f"Report: {Path(report_path).name}", "report")
        self._refresh_dashboard()

    def open_plugin_tab(self, plugin_id: str):
        plugin = self._plugin_manager.get(plugin_id)
        if plugin is None:
            self._console_panel.notify(f"Plugin '{plugin_id}' not found.", level="ERROR")
            return None
        try:
            widget = plugin.create_widget(self)
            idx = self._workspace.addTab(widget, plugin.metadata.display_name)
            self._workspace.setCurrentIndex(idx)
            return widget
        except Exception:
            logger.exception("Plugin tab failed for {}", plugin_id)
            QMessageBox.critical(self, "Plugin Error", f"Could not open '{plugin_id}'.")
            return None

    # ── Undo / Redo ────────────────────────────────────────────────────

    def _on_undo(self) -> None:
        entry = self._registry.undo()
        if entry:
            self._console_panel.notify(f"Undo: {entry.description}", level="INFO")

    def _on_redo(self) -> None:
        entry = self._registry.redo()
        if entry:
            self._console_panel.notify(f"Redo: {entry.description}", level="INFO")

    def _on_history_changed(self) -> None:
        can_u = self._registry.can_undo()
        can_r = self._registry.can_redo()
        self._undo_action.setEnabled(can_u)
        self._redo_action.setEnabled(can_r)
        self._qat_undo.setEnabled(can_u)
        self._qat_redo.setEnabled(can_r)
        self._project_explorer.set_history_entries(self._registry.history_entries())
        self._refresh_open_preview_tabs()
        self._refresh_status_and_properties_for_current_tab()

    def _refresh_open_preview_tabs(self) -> None:
        for i in range(self._workspace.count()):
            w = self._workspace.widget(i)
            key = w.property("file_key")
            pv = w.property("preview_widget")
            if not key or not pv:
                continue
            for sn in self._registry.get_sheet_names(key):
                df = self._registry.get_dataframe(key, sn)
                if df is not None:
                    pv.set_sheet_data(sn, df)

    # ── Context Menu Handlers ──────────────────────────────────────────

    def _on_rename_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if not handle:
            return
        new_name, ok = QInputDialog.getText(self, "Rename", "Name:", text=handle.display_name)
        if ok and new_name:
            handle.display_name = new_name
            self._project_explorer.add_loaded_file(handle)
            for i in range(self._workspace.count()):
                if self._workspace.widget(i).property("file_key") == key:
                    self._workspace.setTabText(i, new_name)

    def _on_reload_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if handle:
            self._console_panel.notify(f"Reloading {handle.display_name}...", level="INFO")
            self._load_files([str(handle.file_path)])

    def _on_close_file(self, key: str) -> None:
        for i in range(self._workspace.count()):
            if self._workspace.widget(i).property("file_key") == key:
                self._close_tab(i)
                break
        self._registry.remove(key)
        self._project_explorer.remove_loaded_file(key)
        self._save_current_session()
        self._refresh_dashboard()

    def _on_export_file(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        df = self._registry.get_dataframe(key)
        if not handle or df is None:
            return
        default = str(paths.exports_dir() / f"{Path(handle.display_name).stem}_export.xlsx")
        fp, _ = QFileDialog.getSaveFileName(self, "Export", default, "Excel (*.xlsx)")
        if not fp:
            return
        df.to_excel(fp, index=False)
        self._project_explorer.add_report(fp)
        self._console_panel.notify(f"Exported to {fp}", level="SUCCESS")
        self._log_activity(f"Exported {handle.display_name}", "export")
        self._refresh_dashboard()

    def _on_duplicate_file_tab(self, key: str) -> None:
        self._open_preview_tab(key, tab_title_suffix=" (Copy)")

    def _on_compare_with(self, key: str) -> None:
        w = self.open_plugin_tab("compare.excel_compare")
        if w and hasattr(w, "preselect_master"):
            w.preselect_master(key)

    def _on_file_information(self, key: str) -> None:
        handle = self._registry.get_handle(key)
        if not handle:
            return
        QMessageBox.information(
            self, "File Information",
            f"<b>{handle.display_name}</b><br><br>"
            f"Path: {handle.file_path}<br>"
            f"Sheets: {handle.sheet_count}<br>"
            f"Active Sheet: {handle.active_sheet}<br>"
            f"Rows: {handle.row_count:,}<br>"
            f"Columns: {handle.column_count}<br>"
            f"Size: {handle.file_size_display}<br>"
            f"Modified: {handle.last_modified.strftime('%Y-%m-%d %H:%M') if handle.last_modified else '-'}<br>"
            f"Engine: {handle.engine_used}<br>"
            f"Duplicates: {handle.duplicate_row_count:,}<br>"
            f"Blank Cells: {handle.blank_cell_count:,}",
        )

    # ── Misc ───────────────────────────────────────────────────────────

    def _show_about(self) -> None:
        QMessageBox.about(
            self, f"About {constants.APP_NAME}",
            f"<b>{constants.APP_NAME}</b><br>"
            f"v{constants.APP_VERSION} ({constants.APP_BUILD})<br><br>"
            f"Rolls-Royce Power Systems (MTU)<br>"
            f"Engineering Data Platform",
        )

    def closeEvent(self, event) -> None:
        self._config.set("window.width", self.width())
        self._config.set("window.height", self.height())
        self._config.set("window.maximized", self.isMaximized())
        self._plugin_manager.shutdown()

        loaded = [str(h.file_path) for h in self._registry.all_handles()]
        save_session(SessionState(loaded_files=loaded, clean_shutdown=True), paths.session_file())
        clear_autosave(paths.autosave_dir())
        logger.info("Shutdown clean.")
        super().closeEvent(event)

    # ── Enterprise: Audit / Autosave / Recovery ────────────────────────

    def _on_mutation_recorded(self, fk: str, sn: str, desc: str) -> None:
        self._audit_log.log(fk, sn, desc)

    def _save_current_session(self) -> None:
        loaded = [str(h.file_path) for h in self._registry.all_handles()]
        save_session(SessionState(loaded_files=loaded, clean_shutdown=False), paths.session_file())

    def _apply_autosave_settings(self) -> None:
        enabled = self._config.get("app.auto_save_enabled", True)
        interval = self._config.get("app.auto_save_interval_seconds", 120)
        self._autosave_timer.stop()
        if enabled and interval > 0:
            self._autosave_timer.start(int(interval) * 1000)

    def _perform_autosave(self) -> None:
        keys = self._registry.keys()
        if not keys:
            return
        sheets = []
        for key in keys:
            handle = self._registry.get_handle(key)
            if not handle:
                continue
            for sn in self._registry.get_sheet_names(key):
                df = self._registry.get_dataframe(key, sn)
                if df is not None:
                    sheets.append((key, sn, handle.display_name, df))
        if sheets:
            snapshot_sheets(sheets, paths.autosave_dir())

    def _check_startup_recovery(self) -> None:
        session = paths.session_file()
        autodir = paths.autosave_dir()
        prev = load_session(session)

        if prev and not prev.clean_shutdown and has_pending_autosave(autodir):
            manifest = load_manifest(autodir)
            confirm = QMessageBox.question(
                self, "Recover Unsaved Work",
                f"{constants.APP_NAME} didn't close cleanly.\n\nRecover {len(manifest)} sheet(s)?",
            )
            if confirm == QMessageBox.Yes:
                self._recover_from_autosave(manifest, autodir)
                self._console_panel.notify(f"Recovered {len(manifest)} sheet(s).", level="SUCCESS")
                self._save_current_session()
                return
            clear_autosave(autodir)

        elif prev and prev.loaded_files and self._config.get("app.restore_last_session", True):
            confirm = QMessageBox.question(
                self, "Restore Session",
                f"Reopen {len(prev.loaded_files)} file(s) from last session?",
            )
            if confirm == QMessageBox.Yes:
                existing = [p for p in prev.loaded_files if Path(p).exists()]
                if existing:
                    self._load_files(existing)
        self._save_current_session()

    def _recover_from_autosave(self, manifest, directory) -> None:
        from app.services.excel.loader_service import load_workbook_all_sheets

        file_keys = {e.file_key for e in manifest}
        for fk in file_keys:
            src = Path(fk)
            if not src.exists():
                continue
            try:
                handle, sheets = load_workbook_all_sheets(src)
            except Exception:
                logger.exception("Autosave recovery failed for {}", src)
                continue
            rk = self._registry.add(handle, sheets)
            self._project_explorer.add_loaded_file(handle)
            self._open_preview_tab(rk)
            for entry in manifest:
                if entry.file_key != fk:
                    continue
                recovered = load_snapshot(entry, directory)
                if recovered is not None:
                    self._registry.replace_sheet_data(rk, entry.sheet_name, recovered, "Recovered")
