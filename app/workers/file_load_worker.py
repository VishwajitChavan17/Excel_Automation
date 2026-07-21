"""
app.workers.file_load_worker
=============================
Runs loader_service.load_workbook() on a background QThread so the UI
thread never blocks -- critical for the "hundreds of thousands of rows"
requirement, where a synchronous load would freeze the whole application.

Usage (from the UI thread):

    worker = FileLoadWorker(file_paths)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.file_loaded.connect(on_file_loaded)
    worker.progress.connect(progress_bar.setValue)
    worker.finished.connect(thread.quit)
    thread.start()
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal

from app.services.excel.loader_service import load_workbook_all_sheets
from app.services.excel.models import WorkbookHandle


class FileLoadWorker(QObject):
    # Emitted once per successfully loaded file: (WorkbookHandle, {sheet_name: DataFrame})
    file_loaded = Signal(object, object)
    # Emitted once per failed file: (file_path, error_message)
    file_failed = Signal(str, str)
    # Emitted after each file, 0-100, for the overall batch
    progress = Signal(int)
    # Emitted once, after every file has been attempted
    finished = Signal()
    # Emitted to allow cooperative cancellation checks
    status_message = Signal(str)

    def __init__(self, file_paths: list[str | Path]) -> None:
        super().__init__()
        self._file_paths = [Path(p) for p in file_paths]
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        total = len(self._file_paths) or 1
        for index, path in enumerate(self._file_paths, start=1):
            if self._cancelled:
                logger.info("File load batch cancelled by user.")
                break
            try:
                self.status_message.emit(f"Loading {path.name}...")
                handle, sheets = load_workbook_all_sheets(path)
                self.file_loaded.emit(handle, sheets)
                logger.info(
                    "Loaded {} ({} sheet(s), active {} rows x {} cols) via {} engine",
                    path.name,
                    handle.sheet_count,
                    handle.row_count,
                    handle.column_count,
                    handle.engine_used,
                )
            except Exception as exc:  # noqa: BLE001 - report, don't crash the batch
                logger.exception("Failed to load {}", path)
                self.file_failed.emit(str(path), str(exc))
            finally:
                self.progress.emit(int(index / total * 100))

        self.finished.emit()
