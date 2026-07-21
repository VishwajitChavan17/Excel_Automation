"""
app.workers.lookup_worker
============================
Runs lookup_service on a background QThread so copying values across a
large target workbook never blocks the UI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import lookup_service


class LookupWorker(QObject):
    finished = Signal(object, object)  # (updated_df, LookupReport)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        master: pd.DataFrame,
        target: pd.DataFrame,
        match_column: str | list[str],
        copy_columns: list[str],
        *,
        master_label: str,
        target_label: str,
        ignore_case: bool = False,
        ignore_whitespace: bool = False,
        export_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._master = master
        self._target = target
        self._match_column = match_column
        self._copy_columns = copy_columns
        self._master_label = master_label
        self._target_label = target_label
        self._ignore_case = ignore_case
        self._ignore_whitespace = ignore_whitespace
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(20)
            updated, report = lookup_service.lookup_and_copy(
                self._master,
                self._target,
                self._match_column,
                self._copy_columns,
                ignore_case=self._ignore_case,
                ignore_whitespace=self._ignore_whitespace,
            )
            report.master_file = self._master_label
            report.target_file = self._target_label
            self.progress.emit(75)
            if self._export_path is not None:
                report.output_path = lookup_service.export_updated_workbook(
                    updated, self._export_path
                )
            self.progress.emit(100)
            self.finished.emit(updated, report)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Lookup worker failed")
            self.failed.emit(str(exc))
