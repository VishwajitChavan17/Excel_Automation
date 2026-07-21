"""
app.ui.widgets.pandas_table_model
===================================
QAbstractTableModel wrapping a pandas DataFrame, used by the Excel-like
preview grid (Center Workspace tabs).

Supports:
- Correct numeric/date sorting when wrapped in a QSortFilterProxyModel with
  sortRole=Qt.EditRole (DisplayRole stays a formatted string).
- Null-cell highlighting (always on).
- Optional duplicate-row highlighting via `set_duplicate_mask()`, used by
  the Duplicate Finder tool to visually flag rows in the shared preview
  grid without needing a separate widget.
"""

from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

class PandasTableModel(QAbstractTableModel):
    NULL_HIGHLIGHT = QColor("#3d1f1f")
    DUPLICATE_HIGHLIGHT = QColor("#4a3a12")
    def __init__(self, df: pd.DataFrame, parent=None) -> None:
        super().__init__(parent)
        self._df = df
        self._duplicate_mask: pd.Series | None = None

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def set_duplicate_mask(self, mask: pd.Series | None) -> None:
        self._duplicate_mask = mask
        if len(self._df):
            top_left = self.index(0, 0)
            bottom_right = self.index(len(self._df) - 1, max(self.columnCount() - 1, 0))
            self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole])

    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt override
        return 0 if parent.isValid() else len(self._df.index)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: N802 - Qt override
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None

        if role == Qt.DisplayRole:
            value = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(value) else str(value)

        if role == Qt.EditRole:
            value = self._df.iat[index.row(), index.column()]
            if pd.isna(value):
                return ""
            # Return native types so QSortFilterProxyModel(sortRole=EditRole)
            # compares numbers/dates correctly instead of lexicographically.
            if isinstance(value, (int, float)):
                return value
            return str(value)

        if role == Qt.ToolTipRole:
            value = self._df.iat[index.row(), index.column()]
            return "" if pd.isna(value) else str(value)

        if role == Qt.BackgroundRole:
            value = self._df.iat[index.row(), index.column()]
            if pd.isna(value):
                return self.NULL_HIGHLIGHT
            if self._duplicate_mask is not None:
                try:
                    if bool(self._duplicate_mask.iloc[index.row()]):
                        return self.DUPLICATE_HIGHLIGHT
                except IndexError:
                    pass
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        return str(section + 1)

