"""
app.ui.panels.console_panel
=============================
Bottom dock panel with two tabs: a live Console (mirrors Loguru output via
a custom sink, with search/export/clear) and a Notifications list (task
completion / error toasts).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger
from PySide6.QtCore import Signal
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import paths


class ConsolePanel(QTabWidget):
    LEVEL_COLORS = {
        "DEBUG": "#8b949e",
        "INFO": "#c9d1d9",
        "SUCCESS": "#3fb950",
        "WARNING": "#d29922",
        "ERROR": "#f85149",
        "CRITICAL": "#f85149",
    }

    # Loguru sinks run synchronously on WHATEVER THREAD calls logger.*() --
    # including every background worker thread in this app (compare_service,
    # duplicate_service, lookup_service, loader_service all log). Mutating a
    # QPlainTextEdit directly from a non-GUI thread is undefined behavior in
    # Qt. This signal is the fix: emitting a Qt signal is thread-safe, and
    # Qt automatically delivers it to _on_log_line via a queued connection
    # since the receiver (self) lives on the GUI thread.
    _log_line_received = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._log_lines: list[str] = []  # plain-text buffer, mirrors what's shown, for search/export
        self._log_line_received.connect(self._on_log_line)

        console_container = QWidget()
        console_layout = QVBoxLayout(console_container)
        console_layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search logs...")
        self._search_box.textChanged.connect(self._apply_filter)
        toolbar.addWidget(self._search_box, 1)

        export_button = QPushButton("Export Logs")
        export_button.clicked.connect(self._export_logs)
        toolbar.addWidget(export_button)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self._clear_logs)
        toolbar.addWidget(clear_button)
        console_layout.addLayout(toolbar)

        self._console = QPlainTextEdit()
        self._console.setReadOnly(True)
        self._console.setMaximumBlockCount(5000)
        console_layout.addWidget(self._console)

        self.addTab(console_container, "Console")

        self._notifications = QListWidget()
        self.addTab(self._notifications, "Notifications")

        # Hook into Loguru so every log message the app produces is mirrored
        # here in real time. The sink itself does NO widget access -- see
        # _sink()/_on_log_line() split below.
        logger.add(self._sink, level="DEBUG", format="{time:HH:mm:ss} | {level: <8} | {message}")

    def _sink(self, message) -> None:
        # Runs on whatever thread emitted the log record. Must not touch
        # any QWidget here -- only emit a signal, which Qt marshals safely
        # to the GUI thread.
        self._log_line_received.emit(message.rstrip())

    def _on_log_line(self, plain: str) -> None:
        # Runs on the GUI thread (queued connection from _sink). Safe to
        # touch self._console here.
        self._log_lines.append(plain)
        if self._search_box.text().lower() in plain.lower():
            color = self._color_for_line(plain)
            self._console.appendHtml(f'<span style="color:{color}">{plain}</span>')
            self._console.moveCursor(QTextCursor.End)

    def _color_for_line(self, line: str) -> str:
        for level, level_color in self.LEVEL_COLORS.items():
            if f"| {level:<8}" in line or f"|{level}" in line:
                return level_color
        return "#c9d1d9"

    def _apply_filter(self, text: str) -> None:
        self._console.clear()
        needle = text.lower()
        for line in self._log_lines:
            if needle in line.lower():
                color = self._color_for_line(line)
                self._console.appendHtml(f'<span style="color:{color}">{line}</span>')
        self._console.moveCursor(QTextCursor.End)

    def _export_logs(self) -> None:
        default_path = str(paths.exports_dir() / f"console_export_{datetime.now():%Y%m%d_%H%M%S}.txt")
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Console Log", default_path, "Text Files (*.txt)")
        if not file_path:
            return
        Path(file_path).write_text("\n".join(self._log_lines), encoding="utf-8")
        self.notify(f"Console log exported to {file_path}", level="SUCCESS")

    def _clear_logs(self) -> None:
        self._log_lines.clear()
        self._console.clear()

    def notify(self, text: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}] {text}")
        item.setForeground(QColor(self.LEVEL_COLORS.get(level, "#c9d1d9")))
        self._notifications.insertItem(0, item)
