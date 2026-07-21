"""
app.workers.report_worker
============================
Runs report_service exports on a background QThread so generating a PDF
with charts (the slowest format) never blocks the UI.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import report_service
from app.services.excel.models import WorkbookHandle


class ReportGenerationWorker(QObject):
    finished = Signal(object)  # list[Path] of every file written -- see workflow_worker.py note on Signal typing
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, handle: WorkbookHandle, output_dir: Path, formats: list[str]) -> None:
        super().__init__()
        self._handle = handle
        self._output_dir = Path(output_dir)
        self._formats = formats  # subset of {"excel", "csv", "html", "pdf"}

    def run(self) -> None:
        try:
            written: list[Path] = []
            stem = Path(self._handle.display_name).stem
            total = len(self._formats) or 1

            exporters = {
                "excel": (report_service.export_summary_excel, f"{stem}_Summary.xlsx"),
                "csv": (report_service.export_summary_csv, f"{stem}_Summary.csv"),
                "html": (report_service.export_summary_html, f"{stem}_Summary.html"),
                "pdf": (report_service.export_summary_pdf, f"{stem}_Summary.pdf"),
            }

            for index, fmt in enumerate(self._formats, start=1):
                if fmt not in exporters:
                    continue
                exporter, filename = exporters[fmt]
                path = exporter(self._handle, self._output_dir / filename)
                written.append(path)
                self.progress.emit(int(index / total * 100))

            self.finished.emit(written)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Report generation worker failed")
            self.failed.emit(str(exc))
