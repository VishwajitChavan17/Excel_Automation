"""
app.workers.compare_worker
============================
Runs compare_service on a background QThread so comparing two large
workbooks never blocks the UI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import compare_service


class CompareWorker(QObject):
    finished = Signal(object)  # ComparisonResult
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        master: pd.DataFrame,
        second: pd.DataFrame,
        key_columns: list[str],
        *,
        master_label: str,
        second_label: str,
        ignore_case: bool = False,
        ignore_whitespace: bool = False,
        export_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._master = master
        self._second = second
        self._key_columns = key_columns
        self._master_label = master_label
        self._second_label = second_label
        self._ignore_case = ignore_case
        self._ignore_whitespace = ignore_whitespace
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(15)
            result = compare_service.compare_workbooks(
                self._master,
                self._second,
                self._key_columns,
                master_label=self._master_label,
                second_label=self._second_label,
                ignore_case=self._ignore_case,
                ignore_whitespace=self._ignore_whitespace,
            )
            self.progress.emit(70)
            if self._export_path is not None:
                result.report.output_path = compare_service.export_comparison_report(
                    result, self._export_path
                )
            self.progress.emit(100)
            self.finished.emit(result)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Compare worker failed")
            self.failed.emit(str(exc))
