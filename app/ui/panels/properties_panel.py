from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.services.excel.models import WorkbookHandle

COLUMN_HEADERS = [
    "Column",
    "Type",
    "Null %",
    "Unique %",
    "Duplicate %",
    "Min",
    "Max",
    "Samples",
]

SECTION_STYLE = """
QFrame#propSection {
    background-color: #252526;
    border: 1px solid #3c3c3c;
    border-radius: 4px;
    margin: 0;
}
"""


class _Section(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("propSection")
        self.setStyleSheet(SECTION_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QLabel(title)
        header.setStyleSheet("color: #969696; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; border: none; background: transparent;")
        layout.addWidget(header)

        self.content = QVBoxLayout()
        self.content.setSpacing(4)
        layout.addLayout(self.content)

    def add_row(self, label: str, value: str) -> None:
        row = QHBoxLayout()
        row.setSpacing(8)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #969696; font-size: 11px; border: none; background: transparent;")
        lbl.setFixedWidth(90)
        row.addWidget(lbl)
        val = QLabel(value)
        val.setStyleSheet("color: #cccccc; font-size: 11px; border: none; background: transparent;")
        val.setWordWrap(True)
        row.addWidget(val, 1)
        self.content.addLayout(row)


class PropertiesPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._sections: list[_Section] = []

        content = QWidget()
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(8)
        self._layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        scroll.setFrameShape(QScrollArea.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.clear()

    def clear(self) -> None:
        self._clear_sections()
        empty = QLabel("No file selected")
        empty.setStyleSheet("color: #555555; font-size: 12px; padding: 24px 8px;")
        empty.setAlignment(Qt.AlignCenter)
        self._layout.insertWidget(0, empty)
        self._empty_label = empty

    def _clear_sections(self) -> None:
        if hasattr(self, "_empty_label"):
            self._empty_label.deleteLater()
        for s in self._sections:
            self._layout.removeWidget(s)
            s.deleteLater()
        self._sections.clear()

    def _add_section(self, title: str) -> _Section:
        s = _Section(title)
        self._layout.insertWidget(self._layout.count() - 1, s)
        self._sections.append(s)
        return s

    def show_workbook(self, handle: WorkbookHandle) -> None:
        self._clear_sections()

        # File Identity
        sec = self._add_section("FILE")
        sec.add_row("Name", handle.display_name)
        sec.add_row("Sheets", f"{handle.sheet_count}")
        sec.add_row("Active Sheet", handle.active_sheet)
        sec.add_row("Size", handle.file_size_display)
        sec.add_row("Modified", handle.last_modified.strftime("%Y-%m-%d %H:%M") if handle.last_modified else "-")
        sec.add_row("Engine", handle.engine_used)
        sec.add_row("Memory", f"{handle.memory_usage_mb} MB")

        # Data Quality
        sec = self._add_section("DATA QUALITY")
        sec.add_row("Duplicate Rows", f"{handle.duplicate_row_count:,}")
        sec.add_row("Blank Cells", f"{handle.blank_cell_count:,}")
        quality_pct = 0
        total_cells = handle.row_count * handle.column_count
        if total_cells > 0:
            filled = total_cells - handle.blank_cell_count
            quality_pct = round(filled / total_cells * 100, 1)
        sec.add_row("Fill Rate", f"{quality_pct}%")

        # Column Statistics Table
        table = QTableWidget(0, len(COLUMN_HEADERS))
        table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setDefaultSectionSize(24)
        table.verticalHeader().hide()
        table.setMaximumHeight(min(len(handle.column_profiles), 12) * 26 + 28)

        for row, profile in enumerate(handle.column_profiles):
            min_display = f"{profile.min_value:g}" if profile.min_value is not None else "-"
            max_display = f"{profile.max_value:g}" if profile.max_value is not None else "-"
            values = [
                profile.name,
                profile.dtype,
                f"{profile.null_pct}%",
                f"{profile.unique_pct}%",
                f"{profile.duplicate_pct}%",
                min_display,
                max_display,
                ", ".join(str(v) for v in profile.example_values[:2]),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(f"{profile.name}: {value}")
                table.setItem(row, col, item)

        table_hdr = QLabel("COLUMN STATISTICS")
        table_hdr.setStyleSheet("color: #969696; font-size: 10px; font-weight: 600; letter-spacing: 0.5px; padding: 8px 0 4px 0; border: none; background: transparent;")
        self._layout.insertWidget(self._layout.count() - 1, table_hdr)
        self._layout.insertWidget(self._layout.count() - 1, table)
