"""
app.workers.validation_worker
================================
Runs validation_service on a background QThread so checking large sheets
against many rules never blocks the UI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import validation_service
from app.services.excel.models import ValidationRule


class ValidationWorker(QObject):
    finished = Signal(object)  # ValidationReport
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, df: pd.DataFrame, rules: list[ValidationRule], export_path: Path | None = None) -> None:
        super().__init__()
        self._df = df
        self._rules = rules
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(25)
            report = validation_service.run_validation(self._df, self._rules)
            self.progress.emit(80)
            if self._export_path is not None:
                report.output_path = validation_service.export_validation_report(
                    self._df, report, self._export_path
                )
            self.progress.emit(100)
            self.finished.emit(report)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Validation worker failed")
            self.failed.emit(str(exc))
