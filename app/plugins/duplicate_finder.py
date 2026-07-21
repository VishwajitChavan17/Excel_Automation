"""
app.plugins.duplicate_finder
==============================
Full working Duplicate Finder: pick a loaded file + sheet, pick one or more
columns, choose a keep-strategy, find duplicates (background thread),
visually highlight them in an embedded preview grid, optionally remove them
in place, and export a duplicate report workbook.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
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
from app.workers.duplicate_worker import DuplicateFinderWorker


class DuplicateFinderWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._last_mask = None
        self._last_report = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        # -- left: controls --
        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        self._picker = FileSheetPicker(self._registry, label="File:")
        self._picker.selection_changed.connect(self._on_selection_changed)
        controls_layout.addWidget(self._picker)

        columns_box = QGroupBox("Columns to Check for Duplicates")
        columns_layout = QVBoxLayout(columns_box)
        self._columns_list = QListWidget()
        self._columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        columns_layout.addWidget(self._columns_list)
        controls_layout.addWidget(columns_box, 1)

        strategy_row = QHBoxLayout()
        strategy_row.addWidget(QLabel("Keep:"))
        self._keep_combo = QComboBox()
        self._keep_combo.addItem("First Occurrence", userData="first")
        self._keep_combo.addItem("Latest Occurrence", userData="last")
        self._keep_combo.addItem("Highest Value", userData="highest")
        strategy_row.addWidget(self._keep_combo)
        controls_layout.addLayout(strategy_row)

        self._find_button = QPushButton("Find Duplicates")
        self._find_button.clicked.connect(self._on_find_clicked)
        controls_layout.addWidget(self._find_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel("Select a file, sheet, and columns, then click Find Duplicates.")
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        button_row = QHBoxLayout()
        self._remove_button = QPushButton("Remove Duplicates")
        self._remove_button.setEnabled(False)
        self._remove_button.clicked.connect(self._on_remove_clicked)
        button_row.addWidget(self._remove_button)

        self._export_button = QPushButton("Export Report")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        button_row.addWidget(self._export_button)
        controls_layout.addLayout(button_row)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        # -- right: live preview with duplicate highlighting --
        self._preview_container = QVBoxLayout()
        self._preview_placeholder = QLabel("Load a file to preview it here.")
        preview_widget = QWidget()
        preview_widget.setLayout(self._preview_container)
        self._preview_container.addWidget(self._preview_placeholder)
        splitter.addWidget(preview_widget)

        splitter.setSizes([340, 760])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._preview: ExcelPreviewWidget | None = None
        self._cleanup_done = False
        self.destroyed.connect(self._cleanup_threads)
        self._on_selection_changed()

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

    # -- selection wiring ------------------------------------------------

    def _on_selection_changed(self) -> None:
        df = self._picker.selected_dataframe()
        self._columns_list.clear()
        self._remove_button.setEnabled(False)
        self._export_button.setEnabled(False)
        self._last_mask = None

        if df is None:
            return

        for col in df.columns:
            item = QListWidgetItem(str(col))
            self._columns_list.addItem(item)

        while self._preview_container.count():
            child = self._preview_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        sheet = self._picker.selected_sheet()
        self._preview = ExcelPreviewWidget({sheet: df}, active_sheet=sheet)
        self._preview_container.addWidget(self._preview)

    # -- find ------------------------------------------------------------

    def _on_find_clicked(self) -> None:
        df = self._picker.selected_dataframe()
        selected_columns = [item.text() for item in self._columns_list.selectedItems()]
        if df is None or not selected_columns:
            QMessageBox.warning(self, "Duplicate Finder", "Select a file and at least one column.")
            return

        keep = self._keep_combo.currentData()
        self._find_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = DuplicateFinderWorker(df, selected_columns, keep)
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_find_finished)
        worker.failed.connect(self._on_find_failed)
        self._threads.append(thread)
        thread.start()

    def _on_find_finished(self, report, mask) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        import pandas as pd

        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._find_button.setEnabled(True)
        self._last_mask = pd.Series(mask, index=self._picker.selected_dataframe().index)
        self._last_report = report

        pct = round(100 * report.duplicate_row_count / max(report.total_rows, 1), 1)
        self._summary_label.setText(
            f"<b>{report.duplicate_row_count:,}</b> duplicate row(s) found out of "
            f"{report.total_rows:,} ({pct}%), checking columns: {', '.join(report.columns_checked)}."
        )
        self._remove_button.setEnabled(report.duplicate_row_count > 0)
        self._export_button.setEnabled(report.duplicate_row_count > 0)

        if self._preview is not None:
            self._preview.highlight_duplicate_rows(self._last_mask)

        logger.info("Duplicate Finder: {} duplicates found", report.duplicate_row_count)

    def _on_find_failed(self, error: str) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._find_button.setEnabled(True)
        QMessageBox.critical(self, "Duplicate Finder", f"Failed to find duplicates:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    # -- remove / export ---------------------------------------------------

    def _on_remove_clicked(self) -> None:
        if self._last_mask is None:
            return
        confirm = QMessageBox.question(
            self,
            "Remove Duplicates",
            f"Remove {self._last_report.duplicate_row_count:,} duplicate row(s) from "
            f"'{self._picker.selected_file_name()}' ({self._picker.selected_sheet()})?\n\n"
            f"This modifies the in-memory copy only -- the original file on disk is never overwritten.",
        )
        if confirm != QMessageBox.Yes:
            return

        df = self._picker.selected_dataframe()
        cleaned = df.loc[~self._last_mask].reset_index(drop=True)

        key = self._picker.selected_file_key()
        sheet = self._picker.selected_sheet()
        self._registry.replace_sheet_data(
            key, sheet, cleaned, description=f"Removed {self._last_report.duplicate_row_count} duplicate row(s)"
        )

        if self._preview is not None:
            self._preview.set_sheet_data(sheet, cleaned)
            self._preview.highlight_duplicate_rows(None)

        self._remove_button.setEnabled(False)
        self._summary_label.setText(
            f"Removed {self._last_report.duplicate_row_count:,} duplicate row(s). "
            f"{len(cleaned):,} row(s) remain."
        )
        self._last_mask = None

    def _on_export_clicked(self) -> None:
        if self._last_report is None:
            return
        from app.services.excel.duplicate_service import export_duplicate_report

        default_name = f"Duplicate_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Duplicate Report", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_duplicate_report(self._picker.selected_dataframe(), self._last_report, file_path)
            QMessageBox.information(self, "Export Complete", f"Duplicate report saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export duplicate report")
            QMessageBox.critical(self, "Export Failed", str(exc))


class DuplicateFinderPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="excel.duplicate_finder",
        display_name="Duplicate Finder",
        category=PluginCategory.EXCEL,
        description="Find, highlight, remove, and report duplicate rows across one or more columns.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return DuplicateFinderWidget(self.context, parent)
