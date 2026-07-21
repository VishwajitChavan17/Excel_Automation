"""
app.plugins.compare_tool
==========================
Full working Compare Excel tool: pick a Master file and a Second file
(each with its own sheet selector), pick one or more key columns, run the
comparison in a background thread, and review Missing / New / Modified rows
in separate result grids before exporting a highlighted Excel report.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
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
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.ui.widgets.pandas_table_model import PandasTableModel
from app.workers.compare_worker import CompareWorker


class CompareToolWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._last_result = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        master_box = QGroupBox("Master File")
        master_layout = QVBoxLayout(master_box)
        self._master_picker = FileSheetPicker(self._registry, label="Master:")
        self._master_picker.selection_changed.connect(self._refresh_key_columns)
        master_layout.addWidget(self._master_picker)
        controls_layout.addWidget(master_box)

        second_box = QGroupBox("Second File")
        second_layout = QVBoxLayout(second_box)
        self._second_picker = FileSheetPicker(self._registry, label="Second:")
        self._second_picker.selection_changed.connect(self._refresh_key_columns)
        second_layout.addWidget(self._second_picker)
        controls_layout.addWidget(second_box)

        key_box = QGroupBox("Key Column(s)")
        key_layout = QVBoxLayout(key_box)
        self._key_columns_list = QListWidget()
        self._key_columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        key_layout.addWidget(self._key_columns_list)
        controls_layout.addWidget(key_box, 1)

        options_row = QHBoxLayout()
        self._ignore_case_checkbox = QCheckBox("Ignore Case")
        self._ignore_ws_checkbox = QCheckBox("Ignore Spaces")
        options_row.addWidget(self._ignore_case_checkbox)
        options_row.addWidget(self._ignore_ws_checkbox)
        controls_layout.addLayout(options_row)

        self._compare_button = QPushButton("Compare")
        self._compare_button.clicked.connect(self._on_compare_clicked)
        controls_layout.addWidget(self._compare_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel(
            "Select a master file, a second file, and at least one key column."
        )
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        self._export_button = QPushButton("Generate Comparison Report (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self._export_button)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        # -- results: three tabs --
        self._results_tabs = QTabWidget()
        self._missing_view = QTableView()
        self._new_view = QTableView()
        self._modified_view = QTableView()
        for view in (self._missing_view, self._new_view, self._modified_view):
            view.setAlternatingRowColors(True)
            view.setEditTriggers(QTableView.NoEditTriggers)
        self._results_tabs.addTab(self._missing_view, "Missing In Second")
        self._results_tabs.addTab(self._new_view, "New In Second")
        self._results_tabs.addTab(self._modified_view, "Modified")
        splitter.addWidget(self._results_tabs)
        splitter.setSizes([360, 740])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._refresh_key_columns()

    def _refresh_key_columns(self) -> None:
        master_df = self._master_picker.selected_dataframe()
        second_df = self._second_picker.selected_dataframe()
        self._key_columns_list.clear()
        if master_df is None or second_df is None:
            return
        shared = [c for c in master_df.columns if c in second_df.columns]
        for col in shared:
            self._key_columns_list.addItem(QListWidgetItem(str(col)))

    def _on_compare_clicked(self) -> None:
        master_df = self._master_picker.selected_dataframe()
        second_df = self._second_picker.selected_dataframe()
        key_columns = [item.text() for item in self._key_columns_list.selectedItems()]

        if master_df is None or second_df is None:
            QMessageBox.warning(self, "Compare Excel", "Select both a master and a second file.")
            return
        if not key_columns:
            QMessageBox.warning(self, "Compare Excel", "Select at least one key column.")
            return

        self._compare_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = CompareWorker(
            master_df,
            second_df,
            key_columns,
            master_label=self._master_picker.selected_file_name(),
            second_label=self._second_picker.selected_file_name(),
            ignore_case=self._ignore_case_checkbox.isChecked(),
            ignore_whitespace=self._ignore_ws_checkbox.isChecked(),
        )
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_compare_finished)
        worker.failed.connect(self._on_compare_failed)
        self._threads.append(thread)
        thread.start()

    def _on_compare_finished(self, result) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._compare_button.setEnabled(True)
        self._last_result = result

        report = result.report
        self._summary_label.setText(
            f"<b>Matched:</b> {report.matched_count:,} &nbsp; "
            f"<b>Missing in Second:</b> {report.missing_in_second:,} &nbsp; "
            f"<b>New in Second:</b> {report.new_in_second:,} &nbsp; "
            f"<b>Modified:</b> {report.modified_count:,}"
        )
        self._missing_view.setModel(PandasTableModel(result.missing_in_second))
        self._new_view.setModel(PandasTableModel(result.new_in_second))
        self._modified_view.setModel(PandasTableModel(result.modified))
        self._export_button.setEnabled(True)

        logger.info(
            "Compare finished: {} missing, {} new, {} modified",
            report.missing_in_second,
            report.new_in_second,
            report.modified_count,
        )

    def _on_compare_failed(self, error: str) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._compare_button.setEnabled(True)
        QMessageBox.critical(self, "Compare Excel", f"Comparison failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_export_clicked(self) -> None:
        if self._last_result is None:
            return
        from app.services.excel.compare_service import export_comparison_report

        default_name = f"Comparison_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Comparison Report", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            export_comparison_report(self._last_result, file_path)
            QMessageBox.information(self, "Export Complete", f"Comparison report saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export comparison report")
            QMessageBox.critical(self, "Export Failed", str(exc))

    def preselect_master(self, file_key: str) -> None:
        self._master_picker.set_selected_file(file_key)


class CompareToolPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="compare.excel_compare",
        display_name="Compare Excel",
        category=PluginCategory.COMPARE,
        description="Compare two workbooks by key column(s): missing, new, and modified rows.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return CompareToolWidget(self.context, parent)
