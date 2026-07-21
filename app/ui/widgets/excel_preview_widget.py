from __future__ import annotations

import pandas as pd
from PySide6.QtCore import Qt, QSortFilterProxyModel, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from app.ui.widgets.pandas_table_model import PandasTableModel


class _FrozenColumnTableView(QTableView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.horizontalHeader().hide()
        self.verticalHeader().hide()
        self.setFrameShape(QTableView.NoFrame)
        self.setEditTriggers(QTableView.NoEditTriggers)
        self.setFocusPolicy(Qt.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("background-color: #252526;")


class ExcelPreviewWidget(QWidget):
    cell_selected = Signal(int, int, str)
    sheet_changed = Signal(str)
    row_count_changed = Signal(int, int)

    def __init__(
        self,
        sheets: dict[str, pd.DataFrame],
        active_sheet: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._sheets = sheets
        self._active_sheet = active_sheet
        self._frozen_enabled = False
        self._scroll_sync_connected = False

        self._build_ui()
        self._load_sheet(active_sheet)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 6, 8, 6)
        toolbar.setSpacing(8)

        self._search_box = QLineEdit()
        self._search_box.setPlaceholderText("Search all columns...")
        self._search_box.setClearButtonEnabled(True)
        self._search_box.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._search_box, 2)

        self._freeze_checkbox = QCheckBox("Freeze First Column")
        self._freeze_checkbox.setToolTip("Keep the first column visible while scrolling horizontally")
        self._freeze_checkbox.toggled.connect(self._on_freeze_toggled)
        toolbar.addWidget(self._freeze_checkbox)

        autofit_btn = QPushButton("Autofit")
        autofit_btn.setToolTip("Resize columns to fit content")
        autofit_btn.clicked.connect(self._autofit_columns)
        toolbar.addWidget(autofit_btn)

        toolbar.addStretch(1)

        self._row_count_label = QLabel("")
        self._row_count_label.setStyleSheet("color: #969696; font-size: 11px;")

        status_sep = QLabel("\u2502")
        status_sep.setStyleSheet("color: #3c3c3c; font-size: 11px;")
        toolbar.addWidget(status_sep)
        toolbar.addWidget(self._row_count_label)

        layout.addLayout(toolbar)

        # Sheet tabs
        self._sheet_tab_bar = QTabBar()
        self._sheet_tab_bar.setExpanding(False)
        self._sheet_tab_bar.setDocumentMode(True)
        self._sheet_tab_bar.setStyleSheet("QTabBar { background-color: #252526; }")
        for name in self._sheets:
            self._sheet_tab_bar.addTab(name)
        self._sheet_tab_bar.currentChanged.connect(self._on_sheet_tab_changed)
        if len(self._sheets) > 1:
            layout.addWidget(self._sheet_tab_bar)
        else:
            self._sheet_tab_bar.hide()

        # Data grid
        grid_row = QHBoxLayout()
        grid_row.setSpacing(0)

        self._frozen_view = _FrozenColumnTableView()
        self._frozen_view.setFixedWidth(0)
        grid_row.addWidget(self._frozen_view)

        self._table_view = QTableView()
        self._table_view.setAlternatingRowColors(True)
        self._table_view.setSortingEnabled(True)
        self._table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self._table_view.horizontalHeader().setStretchLastSection(False)
        self._table_view.setSelectionBehavior(QTableView.SelectItems)
        self._table_view.verticalHeader().setDefaultSectionSize(24)
        self._table_view.verticalHeader().setMinimumWidth(40)
        self._table_view.verticalHeader().setStyleSheet(
            "QHeaderView::section { background-color: #252526; color: #555555; font-size: 10px; border: none; border-right: 1px solid #2d2d2d; }"
        )
        grid_row.addWidget(self._table_view, 1)

        layout.addLayout(grid_row, 1)

    def _load_sheet(self, sheet_name: str) -> None:
        df = self._sheets[sheet_name]
        self._active_sheet = sheet_name

        self._model = PandasTableModel(df)
        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setSortRole(Qt.EditRole)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)

        self._table_view.setModel(self._proxy)
        self._table_view.selectionModel().currentChanged.connect(self._on_current_changed)
        self._proxy.rowsInserted.connect(self._emit_row_counts)
        self._proxy.rowsRemoved.connect(self._emit_row_counts)
        self._proxy.layoutChanged.connect(self._emit_row_counts)
        self._proxy.modelReset.connect(self._emit_row_counts)

        if self._search_box.text():
            self._proxy.setFilterFixedString(self._search_box.text())

        self._sync_frozen_column()
        self._emit_row_counts()

    def _on_sheet_tab_changed(self, index: int) -> None:
        if index < 0:
            return
        name = self._sheet_tab_bar.tabText(index)
        if name and name != self._active_sheet:
            self._load_sheet(name)
            self.sheet_changed.emit(name)

    def set_sheet_data(self, sheet_name: str, df: pd.DataFrame) -> None:
        self._sheets[sheet_name] = df
        if sheet_name == self._active_sheet:
            self._load_sheet(sheet_name)

    def highlight_duplicate_rows(self, mask: pd.Series | None) -> None:
        self._model.set_duplicate_mask(mask)

    def _on_search_changed(self, text: str) -> None:
        self._proxy.setFilterFixedString(text)

    def _on_freeze_toggled(self, checked: bool) -> None:
        self._frozen_enabled = checked
        self._sync_frozen_column()

    def _sync_frozen_column(self) -> None:
        if not self._frozen_enabled or self._model.columnCount() == 0:
            if self._scroll_sync_connected:
                try:
                    self._table_view.verticalScrollBar().valueChanged.disconnect()
                except TypeError:
                    pass
                self._scroll_sync_connected = False
            self._frozen_view.setFixedWidth(0)
            self._frozen_view.setModel(None)
            self._table_view.setColumnHidden(0, False)
            return

        self._frozen_view.setModel(self._proxy)
        for col in range(1, self._model.columnCount()):
            self._frozen_view.setColumnHidden(col, True)
        self._table_view.setColumnHidden(0, True)

        width = self._table_view.columnWidth(0) or 140
        self._frozen_view.setFixedWidth(width)
        self._frozen_view.verticalScrollBar().setValue(self._table_view.verticalScrollBar().value())
        if not self._scroll_sync_connected:
            self._table_view.verticalScrollBar().valueChanged.connect(
                self._frozen_view.verticalScrollBar().setValue
            )
            self._scroll_sync_connected = True

    def _autofit_columns(self) -> None:
        self._table_view.resizeColumnsToContents()

    def _on_current_changed(self, current, previous) -> None:
        if not current.isValid():
            return
        source_index = self._proxy.mapToSource(current)
        value = self._model.data(source_index, Qt.DisplayRole)
        self.cell_selected.emit(source_index.row(), source_index.column(), str(value))

    def _emit_row_counts(self, *_args) -> None:
        self.row_count_changed.emit(self._proxy.rowCount(), self._model.rowCount())

    @property
    def active_sheet(self) -> str:
        return self._active_sheet

    @property
    def current_dataframe(self) -> pd.DataFrame:
        return self._sheets[self._active_sheet]
