"""
app.workers.duplicate_worker
==============================
Runs duplicate_service on a background QThread so scanning large sheets
(100k-500k+ rows) never blocks the UI.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import duplicate_service
from app.services.excel.models import DuplicateReport


class DuplicateFinderWorker(QObject):
    finished = Signal(object, object)  # (DuplicateReport, mask as list[bool])
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, df: pd.DataFrame, columns: list[str], keep: str) -> None:
        super().__init__()
        self._df = df
        self._columns = columns
        self._keep = keep

    def run(self) -> None:
        try:
            self.progress.emit(20)
            mask = duplicate_service.find_duplicate_mask(self._df, self._columns, keep=self._keep)
            self.progress.emit(70)
            report = DuplicateReport(
                columns_checked=list(self._columns),
                total_rows=len(self._df),
                duplicate_row_count=int(mask.sum()),
                duplicate_row_indices=self._df.index[mask].tolist(),
                keep_strategy=self._keep,
            )
            self.progress.emit(100)
            self.finished.emit(report, mask.tolist())
        except Exception as exc:  # noqa: BLE001
            logger.exception("Duplicate Finder worker failed")
            self.failed.emit(str(exc))
