"""
app.ui.panels.properties_panel
================================
Right dock panel. Displays metadata for whichever file is currently active
in the workspace: file identity (name, size, modified date, engine, active
sheet), row-level stats (duplicate rows, blank cells), and a full per-column
statistics table (dtype, null %, unique %, duplicate %, min/max for numeric
columns, example values).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
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
    "Example Values",
]


class PropertiesPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._identity_box = QGroupBox("Selected File Information")
        self._file_name_label = QLabel("-")
        self._sheet_label = QLabel("-")
        self._rows_label = QLabel("-")
        self._cols_label = QLabel("-")
        self._size_label = QLabel("-")
        self._modified_label = QLabel("-")
        self._memory_label = QLabel("-")
        self._engine_label = QLabel("-")

        identity_form = QFormLayout()
        identity_form.addRow("File:", self._file_name_label)
        identity_form.addRow("Active Sheet:", self._sheet_label)
        identity_form.addRow("Rows:", self._rows_label)
        identity_form.addRow("Columns:", self._cols_label)
        identity_form.addRow("File Size:", self._size_label)
        identity_form.addRow("Last Modified:", self._modified_label)
        identity_form.addRow("Memory Usage:", self._memory_label)
        identity_form.addRow("Load Engine:", self._engine_label)
        self._identity_box.setLayout(identity_form)

        self._quality_box = QGroupBox("Data Quality")
        self._duplicate_rows_label = QLabel("-")
        self._blank_cells_label = QLabel("-")
        quality_form = QFormLayout()
        quality_form.addRow("Duplicate Rows:", self._duplicate_rows_label)
        quality_form.addRow("Blank Cells:", self._blank_cells_label)
        self._quality_box.setLayout(quality_form)

        self._columns_table = QTableWidget(0, len(COLUMN_HEADERS))
        self._columns_table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._columns_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._columns_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout = QVBoxLayout(self)
        layout.addWidget(self._identity_box)
        layout.addWidget(self._quality_box)
        layout.addWidget(QLabel("Column Statistics"))
        layout.addWidget(self._columns_table)

        self.clear()

    def clear(self) -> None:
        self._file_name_label.setText("No file selected")
        for label in (
            self._sheet_label,
            self._rows_label,
            self._cols_label,
            self._size_label,
            self._modified_label,
            self._memory_label,
            self._engine_label,
            self._duplicate_rows_label,
            self._blank_cells_label,
        ):
            label.setText("-")
        self._columns_table.setRowCount(0)

    def show_workbook(self, handle: WorkbookHandle) -> None:
        self._file_name_label.setText(handle.display_name)
        self._sheet_label.setText(f"{handle.active_sheet}  ({handle.sheet_count} sheet(s) total)")
        self._rows_label.setText(f"{handle.row_count:,}")
        self._cols_label.setText(str(handle.column_count))
        self._size_label.setText(handle.file_size_display)
        self._modified_label.setText(
            handle.last_modified.strftime("%Y-%m-%d %H:%M") if handle.last_modified else "-"
        )
        self._memory_label.setText(f"{handle.memory_usage_mb} MB")
        self._engine_label.setText(handle.engine_used)

        self._duplicate_rows_label.setText(f"{handle.duplicate_row_count:,}")
        self._blank_cells_label.setText(f"{handle.blank_cell_count:,}")

        self._columns_table.setRowCount(len(handle.column_profiles))
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
                ", ".join(str(v) for v in profile.example_values[:3]),
            ]
            for col, value in enumerate(values):
                self._columns_table.setItem(row, col, QTableWidgetItem(value))
