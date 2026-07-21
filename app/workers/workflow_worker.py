"""
app.workers.workflow_worker
==============================
Runs a workflow across many sources on a background QThread so applying a
saved workflow to many files never blocks the UI. Returns both per-source
metrics (WorkflowRunResult, for the results grid / batch report) and the
actual resulting DataFrames (so the UI can offer "Apply results to loaded
files" -- writing the mapped/deduplicated/validated data back into the
registry, not just reporting on it).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel import workflow_service
from app.services.excel.models import WorkflowRunResult, WorkflowStep


class WorkflowBatchWorker(QObject):
    # (list[WorkflowRunResult], {(file_key, sheet_name): result_df})
    # NOTE: `dict` cannot be used directly as a Signal argument type in
    # PySide6 -- it fails to copy-convert to a C++ type at emit time.
    # `object` is the standard way to pass an arbitrary Python container
    # through a signal/slot connection.
    finished = Signal(object, object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        sources: list[tuple[str, str, str, pd.DataFrame]],  # (label, file_key, sheet_name, df)
        steps: list[WorkflowStep],
        export_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._sources = sources
        self._steps = steps
        self._export_path = export_path

    def run(self) -> None:
        try:
            results: list[WorkflowRunResult] = []
            result_frames: dict[tuple[str, str], pd.DataFrame] = {}
            total = len(self._sources) or 1

            for index, (label, file_key, sheet_name, df) in enumerate(self._sources, start=1):
                try:
                    result_df, step_results = workflow_service.run_workflow(df, self._steps)
                    results.append(
                        WorkflowRunResult(
                            source_label=label,
                            row_count_before=len(df),
                            row_count_after=len(result_df),
                            step_results=step_results,
                        )
                    )
                    result_frames[(file_key, sheet_name)] = result_df
                except Exception as exc:  # noqa: BLE001 - one bad source shouldn't stop the batch
                    logger.exception("Workflow failed for source '{}'", label)
                    results.append(
                        WorkflowRunResult(
                            source_label=label, row_count_before=len(df), row_count_after=len(df), error=str(exc)
                        )
                    )
                self.progress.emit(int(index / total * 90))

            if self._export_path is not None:
                workflow_service.export_batch_report(results, self._export_path)
            self.progress.emit(100)
            self.finished.emit(results, result_frames)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Workflow batch worker failed")
            self.failed.emit(str(exc))
