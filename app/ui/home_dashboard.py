from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


def _metric_card(title: str, value: str, accent: str = "#0078d4") -> QFrame:
    card = QFrame()
    card.setObjectName("metricCard")
    card.setStyleSheet(
        f"QFrame#metricCard {{"
        f"  background-color: #252526; border: 1px solid #3c3c3c;"
        f"  border-left: 3px solid {accent}; border-radius: 6px; padding: 16px;"
        f"}}"
        f"QFrame#metricCard:hover {{ border-color: #555555; background-color: #2a2d2e; }}"
    )
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(4)

    title_lbl = QLabel(title.upper())
    title_lbl.setStyleSheet("color: #969696; font-size: 10px; font-weight: 700; letter-spacing: 0.5px; border: none; background: transparent;")
    layout.addWidget(title_lbl)

    value_lbl = QLabel(value)
    value_lbl.setStyleSheet(f"color: {accent}; font-size: 26px; font-weight: 200; border: none; background: transparent;")
    layout.addWidget(value_lbl)

    return card


def _section_header(title: str) -> QLabel:
    h = QLabel(title.upper())
    h.setStyleSheet("font-size: 11px; font-weight: 700; color: #969696; letter-spacing: 0.8px; padding: 8px 0 4px 0;")
    return h


class ActivityFeed(QWidget):
    """Timeline-style activity log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        empty = QLabel("No recent activity")
        empty.setStyleSheet("color: #555555; font-size: 11px; padding: 12px 0;")
        self._empty = empty
        self._layout.addWidget(empty)

    def set_entries(self, entries: list[tuple[str, str, str]]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not entries:
            self._layout.addWidget(self._empty)
            return

        for time_str, desc, typ in entries[-20:]:
            colors = {
                "file": "#569cd6",
                "command": "#0078d4",
                "report": "#881798",
                "export": "#10893e",
                "success": "#4ec9b0",
                "error": "#f14c4c",
            }
            color = colors.get(typ, "#969696")

            row = QWidget()
            row.setStyleSheet(
                "QWidget { background-color: #252526; border: 1px solid #3c3c3c; border-radius: 4px; padding: 8px 12px; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 6, 12, 6)
            row_layout.setSpacing(10)

            dot = QLabel("\u25CF")
            dot.setStyleSheet(f"color: {color}; font-size: 8px;")
            row_layout.addWidget(dot)

            desc_lbl = QLabel(desc)
            desc_lbl.setStyleSheet("color: #cccccc; font-size: 11px;")
            row_layout.addWidget(desc_lbl, 1)

            time_lbl = QLabel(time_str)
            time_lbl.setStyleSheet("color: #555555; font-size: 10px;")
            row_layout.addWidget(time_lbl)

            self._layout.addWidget(row)


class HomeDashboard(QWidget):
    open_file_requested = Signal()
    open_folder_requested = Signal()
    open_recent_file = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)

        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(32, 24, 32, 24)
        self._layout.setSpacing(20)

        self._build_header()
        self._build_quick_actions()
        self._build_metrics()
        self._build_two_column()

        self._layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_header(self) -> None:
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(0, 0, 0, 0)

        col = QVBoxLayout()
        col.setSpacing(4)
        title = QLabel("Excel Automation Studio")
        title.setProperty("heading", True)
        col.addWidget(title)

        subtitle = QLabel("Rolls-Royce Power Systems (MTU) \u2014 Engineering Data Platform")
        subtitle.setStyleSheet("color: #969696; font-size: 12px;")
        col.addWidget(subtitle)
        row.addLayout(col, 1)

        date_lbl = QLabel(datetime.now().strftime("%A, %B %d, %Y"))
        date_lbl.setStyleSheet("color: #555555; font-size: 11px;")
        row.addWidget(date_lbl, 0, Qt.AlignRight | Qt.AlignTop)

        self._layout.addWidget(header)

    def _build_quick_actions(self) -> None:
        section = QWidget()
        row = QHBoxLayout(section)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)

        open_btn = QPushButton("  \u25C9  Open Files ")
        open_btn.setMinimumHeight(38)
        open_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; border: none; color: #ffffff; "
            "font-size: 13px; font-weight: 600; padding: 8px 28px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1a8ad4; }"
        )
        open_btn.clicked.connect(self.open_file_requested.emit)
        row.addWidget(open_btn)

        folder_btn = QPushButton("  \u25B8  Open Folder ")
        folder_btn.setMinimumHeight(38)
        folder_btn.setStyleSheet(
            "QPushButton { background-color: #2d2d2d; border: 1px solid #3c3c3c; color: #cccccc; "
            "font-size: 13px; font-weight: 600; padding: 8px 28px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #383838; border-color: #555555; }"
        )
        folder_btn.clicked.connect(self.open_folder_requested.emit)
        row.addWidget(folder_btn)

        row.addStretch()
        self._layout.addWidget(section)

    def _build_metrics(self) -> None:
        grid = QWidget()
        layout = QHBoxLayout(grid)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(_metric_card("Files Loaded", "0", "#569cd6"))
        layout.addWidget(_metric_card("Sheets", "0", "#4ec9b0"))
        layout.addWidget(_metric_card("Operations", "0", "#ce9178"))
        layout.addWidget(_metric_card("Reports", "0", "#881798"))
        self._layout.addWidget(grid)

        self._metrics_widget = grid
        self._metrics_labels: dict[str, QLabel] = {}

    def set_metrics(self, files: int, sheets: int, operations: int, reports: int) -> None:
        items = [
            ("Files Loaded", f"{files}", "#569cd6"),
            ("Sheets", f"{sheets}", "#4ec9b0"),
            ("Operations", f"{operations}", "#ce9178"),
            ("Reports", f"{reports}", "#881798"),
        ]
        layout = self._metrics_widget.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for title, value, accent in items:
            layout.addWidget(_metric_card(title, value, accent))

    def _build_two_column(self) -> None:
        two = QWidget()
        cols = QHBoxLayout(two)
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(20)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(_section_header("Recent Files"))

        self._recent_list = QVBoxLayout()
        self._recent_list.setSpacing(2)
        empty = QLabel("No recent files. Open a file to get started.")
        empty.setStyleSheet("color: #555555; font-size: 12px; padding: 12px 0;")
        self._recent_list.addWidget(empty)
        left_layout.addLayout(self._recent_list)
        left_layout.addStretch()
        cols.addWidget(left, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        right_layout.addWidget(_section_header("Activity"))

        self._activity_feed = ActivityFeed()
        right_layout.addWidget(self._activity_feed, 1)
        cols.addWidget(right, 1)

        self._layout.addWidget(two)

    def set_recent_files(self, files: list[tuple[str, str]]) -> None:
        while self._recent_list.count():
            item = self._recent_list.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not files:
            empty = QLabel("No recent files. Open a file to get started.")
            empty.setStyleSheet("color: #555555; font-size: 12px; padding: 12px 0;")
            self._recent_list.addWidget(empty)
            return

        for path, name in files[:8]:
            row = QWidget()
            row.setCursor(Qt.PointingHandCursor)
            row.setStyleSheet(
                "QWidget { background-color: #252526; border: 1px solid #3c3c3c; "
                "border-radius: 4px; padding: 8px 12px; }"
                "QWidget:hover { background-color: #2a2d2e; border-color: #555555; }"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)
            row_layout.setSpacing(12)

            icon = QLabel("\u25C9")
            icon.setStyleSheet("color: #569cd6; font-size: 14px;")
            row_layout.addWidget(icon)

            col = QVBoxLayout()
            col.setSpacing(1)
            nl = QLabel(name)
            nl.setStyleSheet("color: #cccccc; font-size: 12px; font-weight: 500;")
            col.addWidget(nl)
            pl = QLabel(str(path))
            pl.setStyleSheet("color: #555555; font-size: 10px;")
            col.addWidget(pl)
            row_layout.addLayout(col, 1)

            row.mousePressEvent = lambda _e, p=path: self.open_recent_file.emit(p)
            self._recent_list.addWidget(row)

    def set_activity(self, entries: list[tuple[str, str, str]]) -> None:
        self._activity_feed.set_entries(entries)
