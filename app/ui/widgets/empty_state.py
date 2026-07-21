"""Professional empty-state views for workspace, explorer, and panels."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class EmptyState(QWidget):
    """Empty-state placeholder with icon, message, and action button."""

    action_clicked = Signal()

    def __init__(
        self,
        icon: str = "\u25C9",
        title: str = "No content",
        description: str = "",
        action_text: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 48px; color: #3c3c3c;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 300; color: #666666;")
        title_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_lbl)

        if description:
            desc_lbl = QLabel(description)
            desc_lbl.setStyleSheet("font-size: 12px; color: #555555;")
            desc_lbl.setAlignment(Qt.AlignCenter)
            desc_lbl.setWordWrap(True)
            layout.addWidget(desc_lbl)

        if action_text:
            btn = QPushButton(action_text)
            btn.setStyleSheet(
                "QPushButton { padding: 8px 24px; font-size: 13px; font-weight: 600; "
                "background-color: #0078d4; border: none; color: #ffffff; border-radius: 4px; }"
                "QPushButton:hover { background-color: #1a8ad4; }"
            )
            btn.clicked.connect(self.action_clicked.emit)
            btn_container = QHBoxLayout()
            btn_container.addStretch()
            btn_container.addWidget(btn)
            btn_container.addStretch()
            layout.addLayout(btn_container)


class WorkspaceEmptyState(QWidget):
    """Full workspace empty state shown when no files are loaded."""

    open_file_requested = Signal()
    open_folder_requested = Signal()
    open_recent_requested = Signal(str)

    def __init__(self, recent_files: list[tuple[str, str]] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._recent = recent_files or []

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(0)

        # Main content
        content = QWidget()
        content.setMaximumWidth(520)
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(20)
        content_layout.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel("\u25C9")
        icon_lbl.setStyleSheet("font-size: 64px; color: #3c3c3c;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Excel Automation Studio")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 300; color: #969696;")
        title_lbl.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(title_lbl)

        subtitle = QLabel("Open an Excel file to get started, or drag & drop files here.")
        subtitle.setStyleSheet("font-size: 12px; color: #555555;")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        content_layout.addWidget(subtitle)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.setAlignment(Qt.AlignCenter)

        open_btn = QPushButton("\u25C9  Open Files")
        open_btn.setStyleSheet(
            "QPushButton { background-color: #0078d4; border: none; color: #ffffff; "
            "font-size: 13px; font-weight: 600; padding: 10px 28px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #1a8ad4; }"
        )
        open_btn.clicked.connect(self.open_file_requested.emit)
        btn_row.addWidget(open_btn)

        folder_btn = QPushButton("\u25B8  Open Folder")
        folder_btn.setStyleSheet(
            "QPushButton { background-color: #2d2d2d; border: 1px solid #3c3c3c; color: #cccccc; "
            "font-size: 13px; font-weight: 600; padding: 10px 28px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #383838; border-color: #555555; }"
        )
        folder_btn.clicked.connect(self.open_folder_requested.emit)
        btn_row.addWidget(folder_btn)
        content_layout.addLayout(btn_row)

        # Recent files section
        if self._recent:
            sep = QLabel("\u2500" * 40)
            sep.setStyleSheet("color: #3c3c3c; padding: 8px 0;")
            sep.setAlignment(Qt.AlignCenter)
            content_layout.addWidget(sep)

            recent_title = QLabel("RECENT FILES")
            recent_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #555555; letter-spacing: 1px;")
            recent_title.setAlignment(Qt.AlignCenter)
            content_layout.addWidget(recent_title)

            for path, name in self._recent[:5]:
                row = QWidget()
                row.setCursor(Qt.PointingHandCursor)
                row.setStyleSheet(
                    "QWidget { background-color: #252526; border: 1px solid #3c3c3c; "
                    "border-radius: 4px; padding: 8px 12px; }"
                    "QWidget:hover { background-color: #2a2d2e; border-color: #555555; }"
                )
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 8, 12, 8)
                row_layout.setSpacing(10)

                fi = QLabel("\u25C9")
                fi.setStyleSheet("color: #569cd6; font-size: 14px;")
                row_layout.addWidget(fi)

                col = QVBoxLayout()
                col.setSpacing(1)
                nl = QLabel(name)
                nl.setStyleSheet("color: #cccccc; font-size: 12px;")
                col.addWidget(nl)
                pl = QLabel(str(path))
                pl.setStyleSheet("color: #555555; font-size: 10px;")
                col.addWidget(pl)
                row_layout.addLayout(col, 1)

                row.mousePressEvent = lambda _e, p=path: self.open_recent_requested.emit(p)
                content_layout.addWidget(row)

        layout.addStretch()
        layout.addWidget(content)
        layout.addStretch()
