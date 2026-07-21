"""
app.plugins.workflow_recorder_tool
=====================================
Full working Workflow Recorder / batch-processing tool: build an ordered
list of steps (Remove Duplicates, Validate, Column Map) against a sample
file's columns, save/load the workflow as JSON, then run it against any
number of loaded files at once -- the "run the same workflow on 100+
files automatically" requirement.
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
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.services.excel import workflow_service
from app.services.excel.models import WorkflowStep
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.workers.workflow_worker import WorkflowBatchWorker

KEEP_STRATEGIES = [("First Occurrence", "first"), ("Latest Occurrence", "last"), ("Highest Value", "highest")]
VALIDATION_RULE_TYPES = [
    ("Required (not blank)", "required"),
    ("Unique (no duplicates)", "unique"),
    ("No Negative Values", "no_negative"),
    ("Must Be Numeric", "dtype_numeric"),
    ("Must Be a Valid Date", "dtype_date"),
]


class WorkflowRecorderWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._steps: list[WorkflowStep] = []
        self._last_results = None
        self._last_result_frames = {}

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        # -- left: step builder --
        builder = QWidget()
        builder_layout = QVBoxLayout(builder)

        sample_box = QGroupBox("Sample File (for column suggestions)")
        sample_layout = QVBoxLayout(sample_box)
        self._sample_picker = FileSheetPicker(self._registry, label="Sample:")
        self._sample_picker.selection_changed.connect(self._refresh_column_widgets)
        sample_layout.addWidget(self._sample_picker)
        builder_layout.addWidget(sample_box)

        step_box = QGroupBox("Add Step")
        step_layout = QVBoxLayout(step_box)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Step Type:"))
        self._step_type_combo = QComboBox()
        self._step_type_combo.addItem("Remove Duplicates", userData="remove_duplicates")
        self._step_type_combo.addItem("Validate", userData="validate")
        self._step_type_combo.addItem("Column Map (auto identical names)", userData="column_map")
        self._step_type_combo.currentIndexChanged.connect(self._on_step_type_changed)
        type_row.addWidget(self._step_type_combo)
        step_layout.addLayout(type_row)

        self._step_params_stack = QStackedWidget()

        # -- Remove Duplicates params --
        dup_params = QWidget()
        dup_layout = QVBoxLayout(dup_params)
        dup_layout.addWidget(QLabel("Columns:"))
        self._dup_columns_list = QListWidget()
        self._dup_columns_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        dup_layout.addWidget(self._dup_columns_list)
        keep_row = QHBoxLayout()
        keep_row.addWidget(QLabel("Keep:"))
        self._dup_keep_combo = QComboBox()
        for label, value in KEEP_STRATEGIES:
            self._dup_keep_combo.addItem(label, userData=value)
        keep_row.addWidget(self._dup_keep_combo)
        dup_layout.addLayout(keep_row)
        self._step_params_stack.addWidget(dup_params)

        # -- Validate params --
        val_params = QWidget()
        val_layout = QVBoxLayout(val_params)
        val_layout.addWidget(QLabel("Rule Type:"))
        self._val_rule_combo = QComboBox()
        for label, value in VALIDATION_RULE_TYPES:
            self._val_rule_combo.addItem(label, userData=value)
        val_layout.addWidget(self._val_rule_combo)
        val_layout.addWidget(QLabel("Column:"))
        self._val_column_combo = QComboBox()
        val_layout.addWidget(self._val_column_combo)
        self._step_params_stack.addWidget(val_params)

        # -- Column Map params (auto identical-name mapping against sample columns) --
        map_params = QWidget()
        map_layout = QVBoxLayout(map_params)
        map_layout.addWidget(
            QLabel(
                "Columns present in the sample file will be kept (renamed to "
                "themselves). Use the Column Mapper tool directly for custom renames."
            )
        )
        self._step_params_stack.addWidget(map_params)

        step_layout.addWidget(self._step_params_stack)

        add_step_button = QPushButton("Add Step")
        add_step_button.clicked.connect(self._on_add_step_clicked)
        step_layout.addWidget(add_step_button)

        builder_layout.addWidget(step_box)

        builder_layout.addWidget(QLabel("Workflow Steps (run in order):"))
        self._steps_list = QListWidget()
        builder_layout.addWidget(self._steps_list, 1)

        remove_step_button = QPushButton("Remove Selected Step")
        remove_step_button.clicked.connect(self._on_remove_step_clicked)
        builder_layout.addWidget(remove_step_button)

        template_row = QHBoxLayout()
        save_button = QPushButton("Save Workflow...")
        save_button.clicked.connect(self._on_save_workflow_clicked)
        template_row.addWidget(save_button)

        self._workflow_combo = QComboBox()
        self._refresh_workflows()
        template_row.addWidget(self._workflow_combo, 1)

        load_button = QPushButton("Load")
        load_button.clicked.connect(self._on_load_workflow_clicked)
        template_row.addWidget(load_button)
        builder_layout.addLayout(template_row)

        splitter.addWidget(builder)

        # -- right: batch run --
        runner = QWidget()
        runner_layout = QVBoxLayout(runner)

        runner_layout.addWidget(QLabel("Select loaded files to run this workflow on:"))
        self._target_files_list = QListWidget()
        self._target_files_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._registry.workbook_added.connect(self._refresh_target_files)
        self._registry.workbook_removed.connect(self._refresh_target_files)
        runner_layout.addWidget(self._target_files_list, 1)

        self._run_button = QPushButton("Run Workflow on Selected Files")
        self._run_button.clicked.connect(self._on_run_clicked)
        runner_layout.addWidget(self._run_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        runner_layout.addWidget(self._progress)

        self._summary_label = QLabel(
            "Build a workflow on the left, select target files, then run."
        )
        self._summary_label.setWordWrap(True)
        runner_layout.addWidget(self._summary_label)

        self._results_table = QTableWidget(0, 5)
        self._results_table.setHorizontalHeaderLabels(["Source", "Rows Before", "Rows After", "Status", "Detail"])
        self._results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._results_table.setEditTriggers(QTableWidget.NoEditTriggers)
        runner_layout.addWidget(self._results_table, 1)

        button_row = QHBoxLayout()
        self._apply_button = QPushButton("Apply Results to Loaded Files")
        self._apply_button.setEnabled(False)
        self._apply_button.clicked.connect(self._on_apply_clicked)
        button_row.addWidget(self._apply_button)

        self._export_button = QPushButton("Export Batch Report (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        button_row.addWidget(self._export_button)
        runner_layout.addLayout(button_row)

        splitter.addWidget(runner)
        splitter.setSizes([440, 660])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._on_step_type_changed()
        self._refresh_target_files()

    # -- step builder ------------------------------------------------------

    def _refresh_column_widgets(self) -> None:
        df = self._sample_picker.selected_dataframe()
        self._dup_columns_list.clear()
        self._val_column_combo.clear()
        if df is None:
            return
        for col in df.columns:
            self._dup_columns_list.addItem(QListWidgetItem(str(col)))
        self._val_column_combo.addItems([str(c) for c in df.columns])

    def _on_step_type_changed(self) -> None:
        step_type = self._step_type_combo.currentData()
        index = {"remove_duplicates": 0, "validate": 1, "column_map": 2}.get(step_type, 0)
        self._step_params_stack.setCurrentIndex(index)

    def _on_add_step_clicked(self) -> None:
        step_type = self._step_type_combo.currentData()

        if step_type == "remove_duplicates":
            columns = [item.text() for item in self._dup_columns_list.selectedItems()]
            if not columns:
                QMessageBox.warning(self, "Workflow Recorder", "Select at least one column.")
                return
            keep = self._dup_keep_combo.currentData()
            step = WorkflowStep(
                step_type="remove_duplicates",
                parameters={"columns": columns, "keep": keep},
                description=f"Remove duplicates on {', '.join(columns)} (keep={keep})",
            )
        elif step_type == "validate":
            column = self._val_column_combo.currentText()
            if not column:
                QMessageBox.warning(self, "Workflow Recorder", "Select a sample file with columns first.")
                return
            rule_type = self._val_rule_combo.currentData()
            step = WorkflowStep(
                step_type="validate",
                parameters={"rules": [{"rule_type": rule_type, "column": column}]},
                description=f"Validate '{column}' ({self._val_rule_combo.currentText()})",
            )
        else:  # column_map -- identity mapping over the sample file's columns
            df = self._sample_picker.selected_dataframe()
            if df is None:
                QMessageBox.warning(self, "Workflow Recorder", "Select a sample file first.")
                return
            mappings = [{"source_column": str(c), "destination_column": str(c)} for c in df.columns]
            step = WorkflowStep(
                step_type="column_map",
                parameters={"mappings": mappings, "keep_unmapped": False},
                description=f"Keep columns: {', '.join(str(c) for c in df.columns)}",
            )

        self._steps.append(step)
        self._steps_list.addItem(QListWidgetItem(f"{len(self._steps)}. {step.description}"))

    def _on_remove_step_clicked(self) -> None:
        row = self._steps_list.currentRow()
        if row < 0:
            return
        self._steps_list.takeItem(row)
        del self._steps[row]
        self._renumber_steps()

    def _renumber_steps(self) -> None:
        for i in range(self._steps_list.count()):
            self._steps_list.item(i).setText(f"{i + 1}. {self._steps[i].description}")

    # -- save / load workflow ------------------------------------------

    def _refresh_workflows(self) -> None:
        self._workflow_combo.clear()
        for path in workflow_service.list_workflows(paths.workflows_dir()):
            self._workflow_combo.addItem(path.stem, userData=str(path))

    def _on_save_workflow_clicked(self) -> None:
        if not self._steps:
            QMessageBox.warning(self, "Workflow Recorder", "Add at least one step before saving.")
            return
        name, ok = QInputDialog.getText(self, "Save Workflow", "Workflow name:")
        if not ok or not name.strip():
            return
        try:
            workflow_service.save_workflow(name.strip(), self._steps, paths.workflows_dir())
            self._refresh_workflows()
            QMessageBox.information(self, "Saved", f"Workflow '{name}' saved.")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save workflow")
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _on_load_workflow_clicked(self) -> None:
        path_str = self._workflow_combo.currentData()
        if not path_str:
            QMessageBox.information(self, "Workflow Recorder", "No saved workflows found.")
            return
        try:
            _name, steps = workflow_service.load_workflow(path_str)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load workflow")
            QMessageBox.critical(self, "Load Failed", str(exc))
            return

        self._steps = list(steps)
        self._steps_list.clear()
        for i, step in enumerate(self._steps, start=1):
            self._steps_list.addItem(QListWidgetItem(f"{i}. {step.description}"))

    # -- batch run -----------------------------------------------------

    def _refresh_target_files(self, *_args) -> None:
        self._target_files_list.clear()
        for key, name in self._registry.display_names().items():
            for sheet_name in self._registry.get_sheet_names(key):
                label = name if len(self._registry.get_sheet_names(key)) == 1 else f"{name} -- {sheet_name}"
                item = QListWidgetItem(label)
                item.setData(1000, (key, sheet_name))
                self._target_files_list.addItem(item)

    def _on_run_clicked(self) -> None:
        if not self._steps:
            QMessageBox.warning(self, "Workflow Recorder", "Add at least one step to the workflow.")
            return
        selected = self._target_files_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Workflow Recorder", "Select at least one target file.")
            return

        sources = []
        for item in selected:
            key, sheet_name = item.data(1000)
            df = self._registry.get_dataframe(key, sheet_name)
            handle = self._registry.get_handle(key)
            label = handle.display_name if handle else key
            sources.append((label, key, sheet_name, df))

        self._run_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = WorkflowBatchWorker(sources, list(self._steps))
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_run_finished)
        worker.failed.connect(self._on_run_failed)
        self._threads.append(thread)
        thread.start()

    def _on_run_finished(self, results, result_frames) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        self._last_results = results
        self._last_result_frames = result_frames

        error_count = sum(1 for r in results if r.error)
        self._summary_label.setText(
            f"Processed {len(results)} source(s): {len(results) - error_count} succeeded, {error_count} failed."
        )

        self._results_table.setRowCount(len(results))
        for row, result in enumerate(results):
            detail = result.error or "; ".join(f"{s.step_type}: {s.detail}" for s in result.step_results)
            values = [
                result.source_label,
                str(result.row_count_before),
                str(result.row_count_after),
                "Error" if result.error else "OK",
                detail,
            ]
            for col, value in enumerate(values):
                self._results_table.setItem(row, col, QTableWidgetItem(value))

        self._apply_button.setEnabled(bool(result_frames))
        self._export_button.setEnabled(True)
        logger.info("Workflow batch run finished: {} source(s), {} error(s)", len(results), error_count)

    def _on_run_failed(self, error: str) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        QMessageBox.critical(self, "Workflow Recorder", f"Batch run failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_apply_clicked(self) -> None:
        if not self._last_result_frames:
            return
        for (key, sheet_name), df in self._last_result_frames.items():
            self._registry.replace_sheet_data(key, sheet_name, df, description="Applied Workflow (batch run)")
        QMessageBox.information(
            self, "Applied", f"Workflow results applied to {len(self._last_result_frames)} loaded file/sheet(s)."
        )

    def _on_export_clicked(self) -> None:
        if not self._last_results:
            return
        default_name = f"Workflow_Batch_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Batch Report", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            workflow_service.export_batch_report(self._last_results, file_path)
            QMessageBox.information(self, "Export Complete", f"Batch report saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export batch report")
            QMessageBox.critical(self, "Export Failed", str(exc))


class WorkflowRecorderPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="automation.workflow_recorder",
        display_name="Workflow Recorder",
        category=PluginCategory.AUTOMATION,
        description="Build, save, and batch-run multi-step workflows across many files.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return WorkflowRecorderWidget(self.context, parent)
