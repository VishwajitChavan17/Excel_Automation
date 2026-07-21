"""
app.plugins.lookup_copy_tool
==============================
Full working "Lookup & Copy Values" tool -- the most common enterprise
Excel workflow, done without writing a single VLOOKUP formula: pick a
master (authoritative) file and a target file, choose the column to match
rows on, choose one or more columns to copy across, run in a background
thread, preview the result, then either apply it to the loaded target file
in place or export it as a new workbook.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.excel_preview_widget import ExcelPreviewWidget
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.workers.lookup_worker import LookupWorker


class LookupCopyWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._last_updated_df = None
        self._last_report = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        master_box = QGroupBox("Master Excel (authoritative values)")
        master_layout = QVBoxLayout(master_box)
        self._master_picker = FileSheetPicker(self._registry, label="Master:")
        self._master_picker.selection_changed.connect(self._refresh_columns)
        master_layout.addWidget(self._master_picker)
        controls_layout.addWidget(master_box)

        target_box = QGroupBox("Target Excel (receives values)")
        target_layout = QVBoxLayout(target_box)
        self._target_picker = FileSheetPicker(self._registry, label="Target:")
        self._target_picker.selection_changed.connect(self._refresh_columns)
        target_layout.addWidget(self._target_picker)
        controls_layout.addWidget(target_box)

        match_box = QGroupBox("Match Column(s) -- select more than one for composite-key matching")
        match_layout = QVBoxLayout(match_box)
        self._match_columns_list = QListWidget()
        self._match_columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        match_layout.addWidget(self._match_columns_list)
        controls_layout.addWidget(match_box)

        copy_box = QGroupBox("Column(s) to Copy")
        copy_layout = QVBoxLayout(copy_box)
        self._copy_columns_list = QListWidget()
        self._copy_columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        copy_layout.addWidget(self._copy_columns_list)
        controls_layout.addWidget(copy_box, 1)

        options_row = QHBoxLayout()
        self._ignore_case_checkbox = QCheckBox("Ignore Case")
        self._ignore_ws_checkbox = QCheckBox("Ignore Spaces")
        options_row.addWidget(self._ignore_case_checkbox)
        options_row.addWidget(self._ignore_ws_checkbox)
        controls_layout.addLayout(options_row)

        self._run_button = QPushButton("Copy Matching Values")
        self._run_button.clicked.connect(self._on_run_clicked)
        controls_layout.addWidget(self._run_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel(
            "Select a master file, a target file, a match column, and at least one column to copy."
        )
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        button_row = QHBoxLayout()
        self._apply_button = QPushButton("Apply to Loaded Target")
        self._apply_button.setEnabled(False)
        self._apply_button.clicked.connect(self._on_apply_clicked)
        button_row.addWidget(self._apply_button)

        self._export_button = QPushButton("Export Updated Workbook")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        button_row.addWidget(self._export_button)
        controls_layout.addLayout(button_row)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        self._preview_container = QVBoxLayout()
        preview_widget = QWidget()
        preview_widget.setLayout(self._preview_container)
        self._preview_container.addWidget(QLabel("Run the lookup to preview the updated target here."))
        splitter.addWidget(preview_widget)
        splitter.setSizes([360, 740])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._cleanup_done = False
        self.destroyed.connect(self._cleanup_threads)
        self._refresh_columns()

    def _cleanup_threads(self) -> None:
        self._cleanup_done = True
        for t in self._threads:
            try:
                if t.isRunning():
                    t.quit()
                    t.wait(2000)
            except RuntimeError:
                pass
        self._threads.clear()
        if self._active_worker is not None:
            try:
                self._active_worker.finished.disconnect()
            except (TypeError, RuntimeError):
                pass
            try:
                self._active_worker.failed.disconnect()
            except (TypeError, RuntimeError):
                pass
            self._active_worker = None

    def _refresh_columns(self) -> None:
        master_df = self._master_picker.selected_dataframe()
        target_df = self._target_picker.selected_dataframe()

        self._match_columns_list.clear()
        self._copy_columns_list.clear()
        if master_df is None or target_df is None:
            return

        shared = [c for c in master_df.columns if c in target_df.columns]
        for col in shared:
            self._match_columns_list.addItem(QListWidgetItem(str(col)))

        for col in master_df.columns:
            item = QListWidgetItem(str(col))
            self._copy_columns_list.addItem(item)

    def _on_run_clicked(self) -> None:
        master_df = self._master_picker.selected_dataframe()
        target_df = self._target_picker.selected_dataframe()
        match_columns = [item.text() for item in self._match_columns_list.selectedItems()]
        copy_columns = [item.text() for item in self._copy_columns_list.selectedItems()]

        if master_df is None or target_df is None:
            QMessageBox.warning(self, "Lookup & Copy", "Select both a master and a target file.")
            return
        if not match_columns:
            QMessageBox.warning(self, "Lookup & Copy", "Select at least one match column.")
            return
        if not copy_columns:
            QMessageBox.warning(self, "Lookup & Copy", "Select at least one column to copy.")
            return
        overlap = set(match_columns) & set(copy_columns)
        if overlap:
            QMessageBox.warning(
                self, "Lookup & Copy", f"Column(s) {sorted(overlap)} can't be both match and copy columns."
            )
            return

        self._run_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = LookupWorker(
            master_df,
            target_df,
            match_columns,
            copy_columns,
            master_label=self._master_picker.selected_file_name(),
            target_label=self._target_picker.selected_file_name(),
            ignore_case=self._ignore_case_checkbox.isChecked(),
            ignore_whitespace=self._ignore_ws_checkbox.isChecked(),
        )
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_run_finished)
        worker.failed.connect(self._on_run_failed)
        self._threads.append(thread)
        thread.start()

    def _on_run_finished(self, updated_df, report) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        self._last_updated_df = updated_df
        self._last_report = report

        self._summary_label.setText(
            f"<b>{report.matched_count:,}</b> row(s) matched and updated, "
            f"<b>{report.unmatched_count:,}</b> row(s) had no match in the master file."
        )
        self._apply_button.setEnabled(True)
        self._export_button.setEnabled(True)

        QTimer.singleShot(0, lambda df=updated_df: self._show_preview(df) if not getattr(self, '_cleanup_done', False) else None)

        logger.info(
            "Lookup & Copy finished: {} matched, {} unmatched",
            report.matched_count,
            report.unmatched_count,
        )

    def _show_preview(self, updated_df) -> None:
        while self._preview_container.count():
            child = self._preview_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        preview = ExcelPreviewWidget({"Preview": updated_df}, active_sheet="Preview")
        self._preview_container.addWidget(preview)

    def _on_run_failed(self, error: str) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        QMessageBox.critical(self, "Lookup & Copy", f"Lookup failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_apply_clicked(self) -> None:
        if self._last_updated_df is None:
            return
        key = self._target_picker.selected_file_key()
        sheet = self._target_picker.selected_sheet()
        self._registry.replace_sheet_data(
            key, sheet, self._last_updated_df,
            description=f"Applied Lookup & Copy ({', '.join(self._last_report.copy_columns)})",
        )
        QMessageBox.information(
            self,
            "Applied",
            f"Updated values applied to '{self._target_picker.selected_file_name()}' "
            f"({sheet}) in memory. Use File > Export or the Project Explorer context "
            f"menu to save it to disk.",
        )

    def _on_export_clicked(self) -> None:
        if self._last_updated_df is None:
            return
        from app.services.excel.lookup_service import export_updated_workbook

        default_name = f"Lookup_Updated_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Updated Workbook", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_updated_workbook(self._last_updated_df, file_path)
            QMessageBox.information(self, "Export Complete", f"Updated workbook saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export updated workbook")
            QMessageBox.critical(self, "Export Failed", str(exc))


class LookupCopyPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="transform.lookup_copy",
        display_name="Lookup && Copy Values",
        category=PluginCategory.TRANSFORM,
        description="Match rows between two workbooks and copy values across -- no formulas required.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return LookupCopyWidget(self.context, parent)
