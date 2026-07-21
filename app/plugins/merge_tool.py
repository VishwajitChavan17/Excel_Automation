"""
app.plugins.merge_tool
========================
Full working Merge & Consolidate tool, combining two related workflows on
one ribbon tab:

- Merge Files: union (stack) or SQL-style join (inner/left/right/outer) of
  exactly two loaded files.
- Consolidate Files: auto-detect which of many loaded files/sheets share an
  identical header signature and combine the largest matching group into
  one master workbook, stamping every row with its source filename, sheet,
  and import timestamp.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtCore import QTimer
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.excel_preview_widget import ExcelPreviewWidget
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.workers.merge_worker import ConsolidationWorker, JoinMergeWorker, UnionMergeWorker


class MergeFilesTab(QWidget):
    """Union or SQL-style join of exactly two loaded files."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._last_result_df = None
        self._last_report = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Merge Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItem("Union (stack rows)", userData="union")
        self._mode_combo.addItem("Inner Join", userData="inner")
        self._mode_combo.addItem("Left Join", userData="left")
        self._mode_combo.addItem("Right Join", userData="right")
        self._mode_combo.addItem("Outer Join", userData="outer")
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_row.addWidget(self._mode_combo)
        controls_layout.addLayout(mode_row)

        first_box = QGroupBox("File A")
        first_layout = QVBoxLayout(first_box)
        self._first_picker = FileSheetPicker(self._registry, label="File A:")
        self._first_picker.selection_changed.connect(self._refresh_key_columns)
        first_layout.addWidget(self._first_picker)
        controls_layout.addWidget(first_box)

        second_box = QGroupBox("File B")
        second_layout = QVBoxLayout(second_box)
        self._second_picker = FileSheetPicker(self._registry, label="File B:")
        self._second_picker.selection_changed.connect(self._refresh_key_columns)
        second_layout.addWidget(self._second_picker)
        controls_layout.addWidget(second_box)

        self._key_box = QGroupBox("Join Key Column(s)")
        key_layout = QVBoxLayout(self._key_box)
        self._key_columns_list = QListWidget()
        self._key_columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        key_layout.addWidget(self._key_columns_list)
        controls_layout.addWidget(self._key_box, 1)

        self._merge_button = QPushButton("Merge")
        self._merge_button.clicked.connect(self._on_merge_clicked)
        controls_layout.addWidget(self._merge_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel("Select two files and a merge mode.")
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        self._export_button = QPushButton("Export Result (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self._export_button)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        self._preview_container = QVBoxLayout()
        preview_widget = QWidget()
        preview_widget.setLayout(self._preview_container)
        self._preview_container.addWidget(QLabel("Run a merge to preview the result here."))
        splitter.addWidget(preview_widget)
        splitter.setSizes([360, 740])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._cleanup_done = False
        self.destroyed.connect(self._cleanup_threads)
        self._on_mode_changed()

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

    def _on_mode_changed(self) -> None:
        is_union = self._mode_combo.currentData() == "union"
        self._key_box.setVisible(not is_union)
        if not is_union:
            self._refresh_key_columns()

    def _refresh_key_columns(self) -> None:
        self._key_columns_list.clear()
        a = self._first_picker.selected_dataframe()
        b = self._second_picker.selected_dataframe()
        if a is None or b is None:
            return
        shared = [c for c in a.columns if c in b.columns]
        for col in shared:
            self._key_columns_list.addItem(QListWidgetItem(str(col)))

    def _on_merge_clicked(self) -> None:
        a = self._first_picker.selected_dataframe()
        b = self._second_picker.selected_dataframe()
        if a is None or b is None:
            QMessageBox.warning(self, "Merge Files", "Select both File A and File B.")
            return

        mode = self._mode_combo.currentData()
        self._merge_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        if mode == "union":
            worker = UnionMergeWorker(
                [a, b], [self._first_picker.selected_file_name(), self._second_picker.selected_file_name()]
            )
        else:
            key_columns = [item.text() for item in self._key_columns_list.selectedItems()]
            if not key_columns:
                QMessageBox.warning(self, "Merge Files", "Select at least one join key column.")
                self._merge_button.setEnabled(True)
                self._progress.setVisible(False)
                return
            worker = JoinMergeWorker(a, b, key_columns, mode)

        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_merge_finished)
        worker.failed.connect(self._on_merge_failed)
        self._threads.append(thread)
        thread.start()

    def _on_merge_finished(self, result_df, report) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._merge_button.setEnabled(True)
        self._last_result_df = result_df
        self._last_report = report

        self._summary_label.setText(
            f"<b>{report.mode}</b> merge complete: {report.result_row_count:,} row(s), "
            f"{report.result_column_count} column(s) from {report.source_count} source(s)."
        )
        self._export_button.setEnabled(True)
        QTimer.singleShot(0, lambda df=result_df: self._show_preview(df) if not getattr(self, '_cleanup_done', False) else None)

        logger.info("Merge finished: mode={}, rows={}", report.mode, report.result_row_count)

    def _show_preview(self, df) -> None:
        while self._preview_container.count():
            child = self._preview_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        preview = ExcelPreviewWidget({"Merged Result": df}, active_sheet="Merged Result")
        self._preview_container.addWidget(preview)

    def _on_merge_failed(self, error: str) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._merge_button.setEnabled(True)
        QMessageBox.critical(self, "Merge Files", f"Merge failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_export_clicked(self) -> None:
        if self._last_result_df is None:
            return
        from app.services.excel.merge_service import export_result

        default_name = f"Merged_Output_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Merged Result", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_result(self._last_result_df, file_path)
            QMessageBox.information(self, "Export Complete", f"Merged result saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export merge result")
            QMessageBox.critical(self, "Export Failed", str(exc))


class ConsolidateFilesTab(QWidget):
    """Auto-detect matching headers across many loaded files and combine
    the largest matching group, with source tracking."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._last_result_df = None
        self._last_report = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        controls_layout.addWidget(QLabel("Select loaded files to consolidate:"))
        self._files_list = QListWidget()
        self._files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._registry.workbook_added.connect(self._refresh_file_list)
        self._registry.workbook_removed.connect(self._refresh_file_list)
        controls_layout.addWidget(self._files_list, 1)

        self._consolidate_button = QPushButton("Consolidate")
        self._consolidate_button.clicked.connect(self._on_consolidate_clicked)
        controls_layout.addWidget(self._consolidate_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel(
            "Select two or more loaded files (all sheets). Files/sheets sharing an "
            "identical header signature will be combined into one master workbook; "
            "mismatched ones are reported but excluded."
        )
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        self._groups_list = QListWidget()
        self._groups_list.setMaximumHeight(140)
        controls_layout.addWidget(QLabel("Header groups detected:"))
        controls_layout.addWidget(self._groups_list)

        self._export_button = QPushButton("Export Consolidated File (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self._export_button)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        self._preview_container = QVBoxLayout()
        preview_widget = QWidget()
        preview_widget.setLayout(self._preview_container)
        self._preview_container.addWidget(QLabel("Run Consolidate to preview the result here."))
        splitter.addWidget(preview_widget)
        splitter.setSizes([380, 720])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._cleanup_done = False
        self.destroyed.connect(self._cleanup_threads)
        self._refresh_file_list()

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

    def _refresh_file_list(self, *_args) -> None:
        self._files_list.clear()
        for key, name in self._registry.display_names().items():
            for sheet_name in self._registry.get_sheet_names(key):
                label = name if len(self._registry.get_sheet_names(key)) == 1 else f"{name} -- {sheet_name}"
                item = QListWidgetItem(label)
                item.setData(1000, (key, sheet_name))
                self._files_list.addItem(item)

    def _on_consolidate_clicked(self) -> None:
        selected = self._files_list.selectedItems()
        if len(selected) < 2:
            QMessageBox.warning(self, "Consolidate Files", "Select at least two files/sheets to consolidate.")
            return

        sources = []
        for item in selected:
            key, sheet_name = item.data(1000)
            df = self._registry.get_dataframe(key, sheet_name)
            handle = self._registry.get_handle(key)
            label = handle.display_name if handle else key
            sources.append((label, sheet_name, df))

        self._consolidate_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = ConsolidationWorker(sources)
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_consolidate_finished)
        worker.failed.connect(self._on_consolidate_failed)
        self._threads.append(thread)
        thread.start()

    def _on_consolidate_finished(self, result_df, report) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._consolidate_button.setEnabled(True)
        self._last_result_df = result_df
        self._last_report = report

        self._summary_label.setText(
            f"Consolidated <b>{report.consolidated_source_count}</b> source(s) into "
            f"<b>{report.consolidated_row_count:,}</b> row(s). "
            f"{report.mismatched_source_count} source(s) had a different header and were excluded."
        )
        self._groups_list.clear()
        for i, group in enumerate(report.groups):
            marker = "[USED] " if i == report.chosen_group_index else "[skipped] "
            sources_desc = ", ".join(f"{label} ({sheet})" for label, sheet in group.sources)
            self._groups_list.addItem(
                f"{marker}{len(group.columns)} column(s), {len(group.sources)} source(s): {sources_desc}"
            )

        self._export_button.setEnabled(True)
        QTimer.singleShot(0, lambda df=result_df: self._show_preview(df) if not getattr(self, '_cleanup_done', False) else None)

        logger.info(
            "Consolidation finished: {} sources, {} rows",
            report.consolidated_source_count,
            report.consolidated_row_count,
        )

    def _show_preview(self, df) -> None:
        while self._preview_container.count():
            child = self._preview_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        preview = ExcelPreviewWidget({"Consolidated": df}, active_sheet="Consolidated")
        self._preview_container.addWidget(preview)

    def _on_consolidate_failed(self, error: str) -> None:
        if getattr(self, '_cleanup_done', False):
            return
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._consolidate_button.setEnabled(True)
        QMessageBox.critical(self, "Consolidate Files", f"Consolidation failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_export_clicked(self) -> None:
        if self._last_result_df is None:
            return
        from app.services.excel.merge_service import export_result

        default_name = f"Consolidated_File_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Consolidated File", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_result(self._last_result_df, file_path, sheet_name="Consolidated")
            QMessageBox.information(self, "Export Complete", f"Consolidated file saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export consolidated file")
            QMessageBox.critical(self, "Export Failed", str(exc))


class MergeConsolidateWidget(QTabWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.addTab(MergeFilesTab(context, self), "Merge Files")
        self.addTab(ConsolidateFilesTab(context, self), "Consolidate Files")


class MergeToolPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="merge.excel_merge",
        display_name="Merge Files",
        category=PluginCategory.MERGE,
        description="Union/join two files, or auto-consolidate many files sharing the same header.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return MergeConsolidateWidget(self.context, parent)
