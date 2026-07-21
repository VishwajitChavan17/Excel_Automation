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
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core import paths


class OutputPane(QPlainTextEdit):
    """A single output pane (Console, Errors, Warnings) with colored text."""

    LEVEL_COLORS = {
        "DEBUG": "#569cd6",
        "INFO": "#cccccc",
        "SUCCESS": "#4ec9b0",
        "WARNING": "#ce9178",
        "ERROR": "#f14c4c",
        "CRITICAL": "#f14c4c",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(10000)
        self.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.setStyleSheet(
            "QPlainTextEdit { background-color: #1e1e1e; color: #cccccc; border: none; font-family: 'Cascadia Code', 'Consolas', monospace; font-size: 12px; }"
        )

    def append_line(self, text: str, level: str = "INFO") -> None:
        color = self.LEVEL_COLORS.get(level, "#cccccc")
        self.appendHtml(f'<span style="color:{color}">{text}</span>')
        self.moveCursor(QTextCursor.End)


class ConsolePanel(QTabWidget):
    _log_line_received = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._log_lines: list[str] = []
        self._log_line_received.connect(self._on_log_line)

        # Console pane
        self._console = OutputPane()
        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Filter output...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._apply_filter)

        console_container = QWidget()
        console_layout = QVBoxLayout(console_container)
        console_layout.setContentsMargins(0, 0, 0, 0)
        console_layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)
        toolbar.addWidget(self._search_box, 1)
        export_btn = QPushButton("Export")
        export_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(export_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        clear_btn.clicked.connect(self._clear_logs)
        toolbar.addWidget(clear_btn)
        console_layout.addLayout(toolbar)

        console_layout.addWidget(self._console, 1)

        self.addTab(console_container, "\u25C9  Console")

        # Notifications pane
        notify_container = QWidget()
        notify_layout = QVBoxLayout(notify_container)
        notify_layout.setContentsMargins(0, 0, 0, 0)

        notify_toolbar = QHBoxLayout()
        notify_toolbar.setContentsMargins(8, 4, 8, 4)
        notify_toolbar.addStretch()
        clear_notify_btn = QPushButton("Clear All")
        clear_notify_btn.setStyleSheet("font-size: 11px; padding: 2px 10px;")
        clear_notify_btn.clicked.connect(self._clear_notifications)
        notify_toolbar.addWidget(clear_notify_btn)
        notify_layout.addLayout(notify_toolbar)

        self._notifications = QListWidget()
        self._notifications.setAlternatingRowColors(True)
        self._notifications.setWordWrap(True)
        self._notifications.setStyleSheet("QListWidget { border: none; }")
        notify_layout.addWidget(self._notifications, 1)

        self.addTab(notify_container, "\u25CB  Notifications")

        logger.add(self._sink, level="DEBUG", format="{time:HH:mm:ss} | {level: <8} | {message}")

    def _sink(self, message) -> None:
        self._log_line_received.emit(message.rstrip())

    def _on_log_line(self, plain: str) -> None:
        self._log_lines.append(plain)
        if self._search_box.text().lower() in plain.lower():
            self._console.append_line(plain)

    def _apply_filter(self, text: str) -> None:
        self._console.clear()
        needle = text.lower()
        for line in self._log_lines:
            if needle in line.lower():
                self._console.append_line(line)
        self._console.moveCursor(QTextCursor.End)

    def _export_logs(self) -> None:
        default_path = str(paths.exports_dir() / f"console_{datetime.now():%Y%m%d_%H%M%S}.txt")
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Console Log", default_path, "Text Files (*.txt)")
        if not file_path:
            return
        Path(file_path).write_text("\n".join(self._log_lines), encoding="utf-8")
        self.notify(f"Console log exported to {file_path}", level="SUCCESS")

    def _clear_logs(self) -> None:
        self._log_lines.clear()
        self._console.clear()

    def _clear_notifications(self) -> None:
        self._notifications.clear()

    def notify(self, text: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}] {text}")
        item.setForeground(QColor(OutputPane.LEVEL_COLORS.get(level, "#cccccc")))
        self._notifications.insertItem(0, item)
