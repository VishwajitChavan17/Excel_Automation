"""
app.plugins.report_generator_tool
====================================
Full working Report Generator: pick a loaded file, choose one or more
output formats (Excel/CSV/HTML/PDF -- the PDF includes a chart), generate
in the background, and also produce a standalone Audit Report from the
application's operation history.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.ui.widgets.background_task import start_worker
from app.ui.widgets.file_sheet_picker import FileSheetPicker
from app.workers.report_worker import ReportGenerationWorker


class ReportGeneratorWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._context = context
        self._threads = []
        self._active_thread = None
        self._active_worker = None

        layout = QVBoxLayout(self)

        summary_box = QGroupBox("Summary Report")
        summary_layout = QVBoxLayout(summary_box)

        self._picker = FileSheetPicker(self._registry, label="File:")
        summary_layout.addWidget(self._picker)

        formats_row = QHBoxLayout()
        formats_row.addWidget(QLabel("Formats:"))
        self._excel_checkbox = QCheckBox("Excel (.xlsx)")
        self._excel_checkbox.setChecked(True)
        self._csv_checkbox = QCheckBox("CSV")
        self._html_checkbox = QCheckBox("HTML")
        self._pdf_checkbox = QCheckBox("PDF (with chart)")
        for cb in (self._excel_checkbox, self._csv_checkbox, self._html_checkbox, self._pdf_checkbox):
            formats_row.addWidget(cb)
        summary_layout.addLayout(formats_row)

        generate_button = QPushButton("Generate Summary Report")
        generate_button.clicked.connect(self._on_generate_clicked)
        summary_layout.addWidget(generate_button)

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        summary_layout.addWidget(self._progress)

        layout.addWidget(summary_box)

        audit_box = QGroupBox("Audit Report (operation history)")
        audit_layout = QVBoxLayout(audit_box)
        audit_layout.addWidget(
            QLabel(f"{len(self._registry.history_entries())} operation(s) recorded so far in this session.")
        )
        audit_button = QPushButton("Generate Audit Report")
        audit_button.clicked.connect(self._on_audit_clicked)
        audit_layout.addWidget(audit_button)
        layout.addWidget(audit_box)

        layout.addWidget(QLabel("Generated Reports:"))
        self._generated_list = QListWidget()
        layout.addWidget(self._generated_list, 1)

        self._summary_label = QLabel("Select a file and at least one format, then Generate.")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)

    def _on_generate_clicked(self) -> None:
        handle = self._registry.get_handle(self._picker.selected_file_key() or "")
        if handle is None:
            QMessageBox.warning(self, "Report Generator", "Select a loaded file.")
            return

        formats = []
        if self._excel_checkbox.isChecked():
            formats.append("excel")
        if self._csv_checkbox.isChecked():
            formats.append("csv")
        if self._html_checkbox.isChecked():
            formats.append("html")
        if self._pdf_checkbox.isChecked():
            formats.append("pdf")
        if not formats:
            QMessageBox.warning(self, "Report Generator", "Select at least one output format.")
            return

        worker = ReportGenerationWorker(handle, paths.exports_dir(), formats)
        thread = start_worker(self, worker)
        self._active_thread = thread
        self._active_worker = worker  # keep alive -- see background_task module note
        worker.progress.connect(self._progress.setValue)
        worker.finished.connect(self._on_generate_finished)
        worker.failed.connect(self._on_generate_failed)
        self._threads.append(thread)

        self._progress.setVisible(True)
        self._progress.setValue(0)
        thread.start()

    def _on_generate_finished(self, written_paths) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)

        for path in written_paths:
            self._generated_list.addItem(str(path))
            if self._context.main_window is not None:
                self._context.main_window.register_generated_report(str(path))

        self._summary_label.setText(f"Generated {len(written_paths)} report file(s).")
        logger.info("Report generation finished: {} file(s)", len(written_paths))

    def _on_generate_failed(self, error: str) -> None:
        thread = self._active_thread
        self._teardown_thread(thread)
        self._progress.setVisible(False)
        QMessageBox.critical(self, "Report Generator", f"Report generation failed:\n{error}")

    def _teardown_thread(self, thread) -> None:
        thread.quit()
        thread.wait()
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_audit_clicked(self) -> None:
        entries = self._registry.history_entries()
        if not entries:
            QMessageBox.information(self, "Audit Report", "No operations have been recorded yet this session.")
            return
        from app.services.excel.report_service import export_audit_report

        default_name = f"Audit_Report_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        output_path = paths.exports_dir() / default_name
        try:
            path = export_audit_report(entries, output_path)
            self._generated_list.addItem(str(path))
            if self._context.main_window is not None:
                self._context.main_window.register_generated_report(str(path))
            QMessageBox.information(self, "Audit Report Generated", f"Saved to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export audit report")
            QMessageBox.critical(self, "Export Failed", str(exc))


class ReportGeneratorPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="reports.generator",
        display_name="Report Generator",
        category=PluginCategory.REPORTS,
        description="Generate summary reports (Excel/CSV/HTML/PDF with charts) and audit reports.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return ReportGeneratorWidget(self.context, parent)
