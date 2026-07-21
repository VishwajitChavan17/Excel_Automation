"""
app.workers.merge_worker
==========================
Runs merge_service (union or SQL-style join) on a background QThread so
merging large workbooks never blocks the UI.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import merge_service


class UnionMergeWorker(QObject):
    finished = Signal(object, object)  # (result_df, MergeReport)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, frames: list[pd.DataFrame], source_labels: list[str], export_path: Path | None = None) -> None:
        super().__init__()
        self._frames = frames
        self._source_labels = source_labels
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(30)
            result, report = merge_service.union_merge(self._frames, self._source_labels)
            self.progress.emit(80)
            if self._export_path is not None:
                report.output_path = merge_service.export_result(result, self._export_path)
            self.progress.emit(100)
            self.finished.emit(result, report)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Union merge worker failed")
            self.failed.emit(str(exc))


class JoinMergeWorker(QObject):
    finished = Signal(object, object)  # (result_df, MergeReport)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        left: pd.DataFrame,
        right: pd.DataFrame,
        key_columns: list[str],
        mode: str,
        export_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._left = left
        self._right = right
        self._key_columns = key_columns
        self._mode = mode
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(30)
            result, report = merge_service.join_merge(self._left, self._right, self._key_columns, self._mode)
            self.progress.emit(80)
            if self._export_path is not None:
                report.output_path = merge_service.export_result(result, self._export_path)
            self.progress.emit(100)
            self.finished.emit(result, report)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Join merge worker failed")
            self.failed.emit(str(exc))


class ConsolidationWorker(QObject):
    finished = Signal(object, object)  # (result_df, ConsolidationReport)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, sources: list[tuple[str, str, pd.DataFrame]], export_path: Path | None = None) -> None:
        super().__init__()
        self._sources = sources
        self._export_path = export_path

    def run(self) -> None:
        try:
            self.progress.emit(20)
            result, report = merge_service.consolidate(self._sources)
            self.progress.emit(80)
            if self._export_path is not None:
                report.output_path = merge_service.export_result(result, self._export_path, sheet_name="Consolidated")
            self.progress.emit(100)
            self.finished.emit(result, report)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Consolidation worker failed")
            self.failed.emit(str(exc))
