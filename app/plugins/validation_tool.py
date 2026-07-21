"""
app.plugins.validation_tool
=============================
Full working Validation Rules tool: pick a loaded file/sheet, build a set
of rules (required, unique, regex, numeric/date dtype, no-negative, or a
custom pandas expression), run them in the background, review every issue
in a sortable grid, and export a highlighted Excel validation report.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.services.excel.models import ValidationRule
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.workers.validation_worker import ValidationWorker

RULE_TYPE_LABELS = {
    "required": "Required (not blank)",
    "unique": "Unique (no duplicates)",
    "regex": "Matches Pattern (regex)",
    "dtype_numeric": "Must Be Numeric",
    "dtype_date": "Must Be a Valid Date",
    "no_negative": "No Negative Values",
    "custom_expression": "Custom Expression",
}


class ValidationToolWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._threads = []
        self._active_thread = None
        self._active_worker = None
        self._rules: list[ValidationRule] = []
        self._last_report = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        self._picker = FileSheetPicker(self._registry, label="File:")
        self._picker.selection_changed.connect(self._on_selection_changed)
        controls_layout.addWidget(self._picker)

        builder_box = QGroupBox("Add Rule")
        builder_layout = QVBoxLayout(builder_box)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Rule Type:"))
        self._rule_type_combo = QComboBox()
        for rule_type, label in RULE_TYPE_LABELS.items():
            self._rule_type_combo.addItem(label, userData=rule_type)
        self._rule_type_combo.currentIndexChanged.connect(self._on_rule_type_changed)
        type_row.addWidget(self._rule_type_combo)
        builder_layout.addLayout(type_row)

        column_row = QHBoxLayout()
        column_row.addWidget(QLabel("Column:"))
        self._column_combo = QComboBox()
        column_row.addWidget(self._column_combo)
        builder_layout.addLayout(column_row)

        self._parameter_edit = QLineEdit()
        self._parameter_edit.setPlaceholderText("Regex pattern or expression, e.g. Qty > 0 and Price >= 0")
        builder_layout.addWidget(self._parameter_edit)

        add_rule_button = QPushButton("Add Rule")
        add_rule_button.clicked.connect(self._on_add_rule_clicked)
        builder_layout.addWidget(add_rule_button)

        controls_layout.addWidget(builder_box)

        controls_layout.addWidget(QLabel("Active Rules:"))
        self._rules_list = QListWidget()
        controls_layout.addWidget(self._rules_list, 1)

        remove_rule_button = QPushButton("Remove Selected Rule")
        remove_rule_button.clicked.connect(self._on_remove_rule_clicked)
        controls_layout.addWidget(remove_rule_button)

        template_row = QHBoxLayout()
        save_template_button = QPushButton("Save Rule Set...")
        save_template_button.clicked.connect(self._on_save_template_clicked)
        template_row.addWidget(save_template_button)

        self._template_combo = QComboBox()
        self._refresh_templates()
        template_row.addWidget(self._template_combo, 1)

        load_template_button = QPushButton("Load")
        load_template_button.clicked.connect(self._on_load_template_clicked)
        template_row.addWidget(load_template_button)
        controls_layout.addLayout(template_row)

        self._run_button = QPushButton("Run Validation")
        self._run_button.clicked.connect(self._on_run_clicked)
        controls_layout.addWidget(self._run_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        controls_layout.addWidget(self._progress)

        self._summary_label = QLabel("Select a file and sheet, add one or more rules, then run.")
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        self._export_button = QPushButton("Export Validation Report (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self._export_button)

        splitter.addWidget(controls)

        results_container = QVBoxLayout()
        results_widget = QWidget()
        results_widget.setLayout(results_container)
        results_container.addWidget(QLabel("Validation Issues"))
        self._issues_table = QTableWidget(0, 4)
        self._issues_table.setHorizontalHeaderLabels(["Row", "Column", "Rule", "Message"])
        self._issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._issues_table.setEditTriggers(QTableWidget.NoEditTriggers)
        results_container.addWidget(self._issues_table)
        splitter.addWidget(results_widget)
        splitter.setSizes([380, 720])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._on_selection_changed()
        self._on_rule_type_changed()

    def _on_selection_changed(self) -> None:
        self._column_combo.clear()
        df = self._picker.selected_dataframe()
        if df is None:
            return
        self._column_combo.addItems([str(c) for c in df.columns])

    def _on_rule_type_changed(self) -> None:
        rule_type = self._rule_type_combo.currentData()
        needs_column = rule_type != "custom_expression"
        self._column_combo.setEnabled(needs_column)
        needs_parameter = rule_type in ("regex", "custom_expression")
        self._parameter_edit.setEnabled(needs_parameter)
        if rule_type == "regex":
            self._parameter_edit.setPlaceholderText(r"Regex pattern, e.g. ^[A-Z]{2}\d{3}$")
        elif rule_type == "custom_expression":
            self._parameter_edit.setPlaceholderText("Pandas expression, e.g. Qty > 0 and Price >= 0")
        else:
            self._parameter_edit.setPlaceholderText("(not used for this rule type)")

    def _on_add_rule_clicked(self) -> None:
        rule_type = self._rule_type_combo.currentData()
        column = self._column_combo.currentText() or None
        parameter = self._parameter_edit.text().strip() or None

        if rule_type != "custom_expression" and not column:
            QMessageBox.warning(self, "Validation", "Select a column for this rule.")
            return
        if rule_type in ("regex", "custom_expression") and not parameter:
            QMessageBox.warning(self, "Validation", "This rule type requires a pattern/expression.")
            return

        rule = ValidationRule(rule_type=rule_type, column=column, parameter=parameter)
        self._rules.append(rule)
        label = RULE_TYPE_LABELS[rule_type]
        display = f"{label} -- {column}" if column else label
        if parameter:
            display += f"  [{parameter}]"
        self._rules_list.addItem(QListWidgetItem(display))
        self._parameter_edit.clear()

    def _on_remove_rule_clicked(self) -> None:
        row = self._rules_list.currentRow()
        if row < 0:
            return
        self._rules_list.takeItem(row)
        del self._rules[row]

    def _validation_templates_dir(self):
        return paths.templates_dir() / "validation"

    def _refresh_templates(self) -> None:
        from app.services.excel.validation_service import list_validation_templates

        self._template_combo.clear()
        for path in list_validation_templates(self._validation_templates_dir()):
            self._template_combo.addItem(path.stem, userData=str(path))

    def _on_save_template_clicked(self) -> None:
        if not self._rules:
            QMessageBox.warning(self, "Validation", "Add at least one rule before saving.")
            return
        name, ok = QInputDialog.getText(self, "Save Rule Set", "Template name:")
        if not ok or not name.strip():
            return
        from app.services.excel.validation_service import save_validation_template

        try:
            save_validation_template(name.strip(), self._rules, self._validation_templates_dir())
            self._refresh_templates()
            QMessageBox.information(self, "Saved", f"Rule set '{name}' saved.")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save validation template")
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _on_load_template_clicked(self) -> None:
        path_str = self._template_combo.currentData()
        if not path_str:
            QMessageBox.information(self, "Validation", "No saved rule sets found.")
            return
        from app.services.excel.validation_service import load_validation_template

        try:
            rules = load_validation_template(path_str)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load validation template")
            QMessageBox.critical(self, "Load Failed", str(exc))
            return

        self._rules = list(rules)
        self._rules_list.clear()
        for rule in self._rules:
            label = RULE_TYPE_LABELS.get(rule.rule_type, rule.rule_type)
            display = f"{label} -- {rule.column}" if rule.column else label
            if rule.parameter:
                display += f"  [{rule.parameter}]"
            self._rules_list.addItem(QListWidgetItem(display))

    def _on_run_clicked(self) -> None:
        df = self._picker.selected_dataframe()
        if df is None:
            QMessageBox.warning(self, "Validation", "Select a file and sheet.")
            return
        if not self._rules:
            QMessageBox.warning(self, "Validation", "Add at least one rule.")
            return

        self._run_button.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)

        worker = ValidationWorker(df, list(self._rules))
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_run_finished)
        worker.failed.connect(self._on_run_failed)
        self._threads.append(thread)
        thread.start()

    def _on_run_finished(self, report) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        self._last_report = report

        pct = round(100 * report.issue_count / max(report.total_rows, 1), 1)
        self._summary_label.setText(
            f"<b>{report.issue_count:,}</b> issue(s) found across {report.total_rows:,} row(s) "
            f"({pct}% of rows affected), checking {len(report.rules_checked)} rule(s)."
        )

        self._issues_table.setRowCount(len(report.issues))
        for row, issue in enumerate(report.issues):
            values = [str(issue.row_index + 1), issue.column, issue.rule_type, issue.message]
            for col, value in enumerate(values):
                self._issues_table.setItem(row, col, QTableWidgetItem(value))

        self._export_button.setEnabled(report.issue_count > 0)
        logger.info("Validation finished: {} issue(s)", report.issue_count)

    def _on_run_failed(self, error: str) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        self._run_button.setEnabled(True)
        QMessageBox.critical(self, "Validation", f"Validation failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_export_clicked(self) -> None:
        if self._last_report is None:
            return
        from app.services.excel.validation_service import export_validation_report

        default_name = f"Validation_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Validation Report", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            df = self._picker.selected_dataframe()
            export_validation_report(df, self._last_report, file_path)
            QMessageBox.information(self, "Export Complete", f"Validation report saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export validation report")
            QMessageBox.critical(self, "Export Failed", str(exc))


class ValidationToolPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="validation.rule_checker",
        display_name="Validation Rules",
        category=PluginCategory.VALIDATION,
        description="Check data against business rules: required fields, duplicates, formats, ranges.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return ValidationToolWidget(self.context, parent)
