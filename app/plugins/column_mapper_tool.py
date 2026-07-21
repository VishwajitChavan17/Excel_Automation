"""
app.plugins.column_mapper_tool
=================================
Full working Column Mapper: pick a source file/sheet, map its columns to
new destination names (optionally auto-suggested from a second reference
file's headers), apply the mapping to produce a reshaped DataFrame, and
save/load the mapping itself as a reusable JSON template under templates/.
"""

from __future__ import annotations

from datetime import datetime

from loguru import logger
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.services.excel import column_mapper_service
from app.services.excel.models import ColumnMapping
from app.ui.widgets.excel_preview_widget import ExcelPreviewWidget
from app.ui.widgets.file_sheet_picker import FileSheetPicker


class ColumnMapperWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._registry = context.registry
        self._last_mapped_df = None

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        controls = QWidget()
        controls_layout = QVBoxLayout(controls)

        source_box = QGroupBox("Source File (columns to map)")
        source_layout = QVBoxLayout(source_box)
        self._source_picker = FileSheetPicker(self._registry, label="Source:")
        self._source_picker.selection_changed.connect(self._on_source_changed)
        source_layout.addWidget(self._source_picker)
        controls_layout.addWidget(source_box)

        reference_box = QGroupBox("Reference Schema (optional -- used by Auto-map)")
        reference_layout = QVBoxLayout(reference_box)
        self._reference_picker = FileSheetPicker(self._registry, label="Reference:")
        reference_layout.addWidget(self._reference_picker)
        controls_layout.addWidget(reference_box)

        mapping_box = QGroupBox("Column Mapping")
        mapping_layout = QVBoxLayout(mapping_box)
        self._mapping_table = QTableWidget(0, 2)
        self._mapping_table.setHorizontalHeaderLabels(["Source Column", "Destination Name"])
        self._mapping_table.horizontalHeader().setStretchLastSection(True)
        mapping_layout.addWidget(self._mapping_table)

        row_buttons = QHBoxLayout()
        add_row_button = QPushButton("Add Row")
        add_row_button.clicked.connect(self._on_add_row_clicked)
        row_buttons.addWidget(add_row_button)

        remove_row_button = QPushButton("Remove Row")
        remove_row_button.clicked.connect(self._on_remove_row_clicked)
        row_buttons.addWidget(remove_row_button)

        auto_map_button = QPushButton("Auto-map Identical Names")
        auto_map_button.clicked.connect(self._on_auto_map_clicked)
        row_buttons.addWidget(auto_map_button)
        mapping_layout.addLayout(row_buttons)

        controls_layout.addWidget(mapping_box, 1)

        self._keep_unmapped_checkbox = QCheckBox("Keep unmapped source columns unchanged")
        controls_layout.addWidget(self._keep_unmapped_checkbox)

        apply_row = QHBoxLayout()
        self._apply_button = QPushButton("Apply Mapping")
        self._apply_button.clicked.connect(self._on_apply_clicked)
        apply_row.addWidget(self._apply_button)

        self._apply_in_place_button = QPushButton("Apply to Loaded Source")
        self._apply_in_place_button.setEnabled(False)
        self._apply_in_place_button.clicked.connect(self._on_apply_in_place_clicked)
        apply_row.addWidget(self._apply_in_place_button)
        controls_layout.addLayout(apply_row)

        self._export_button = QPushButton("Export Mapped File (.xlsx)")
        self._export_button.setEnabled(False)
        self._export_button.clicked.connect(self._on_export_clicked)
        controls_layout.addWidget(self._export_button)

        template_row = QHBoxLayout()
        save_template_button = QPushButton("Save Mapping Template...")
        save_template_button.clicked.connect(self._on_save_template_clicked)
        template_row.addWidget(save_template_button)

        self._template_combo = QComboBox()
        self._refresh_templates()
        template_row.addWidget(self._template_combo, 1)

        load_template_button = QPushButton("Load")
        load_template_button.clicked.connect(self._on_load_template_clicked)
        template_row.addWidget(load_template_button)
        controls_layout.addLayout(template_row)

        self._summary_label = QLabel("Select a source file, map its columns, then Apply.")
        self._summary_label.setWordWrap(True)
        controls_layout.addWidget(self._summary_label)

        controls_layout.addStretch(1)
        splitter.addWidget(controls)

        self._preview_container = QVBoxLayout()
        preview_widget = QWidget()
        preview_widget.setLayout(self._preview_container)
        self._preview_container.addWidget(QLabel("Apply a mapping to preview the result here."))
        splitter.addWidget(preview_widget)
        splitter.setSizes([420, 680])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

    # -- mapping table helpers ------------------------------------------

    def _on_source_changed(self) -> None:
        self._mapping_table.setRowCount(0)

    def _add_row(self, source_column: str = "", destination: str = "") -> None:
        df = self._source_picker.selected_dataframe()
        row = self._mapping_table.rowCount()
        self._mapping_table.insertRow(row)

        combo = QComboBox()
        if df is not None:
            combo.addItems([str(c) for c in df.columns])
        if source_column:
            idx = combo.findText(source_column)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self._mapping_table.setCellWidget(row, 0, combo)

        dest_item = QTableWidgetItem(destination)
        self._mapping_table.setItem(row, 1, dest_item)

    def _on_add_row_clicked(self) -> None:
        df = self._source_picker.selected_dataframe()
        if df is None:
            QMessageBox.warning(self, "Column Mapper", "Select a source file first.")
            return
        self._add_row()

    def _on_remove_row_clicked(self) -> None:
        row = self._mapping_table.currentRow()
        if row >= 0:
            self._mapping_table.removeRow(row)

    def _on_auto_map_clicked(self) -> None:
        source_df = self._source_picker.selected_dataframe()
        if source_df is None:
            QMessageBox.warning(self, "Column Mapper", "Select a source file first.")
            return

        reference_df = self._reference_picker.selected_dataframe()
        destination_columns = list(reference_df.columns) if reference_df is not None else list(source_df.columns)

        mappings = column_mapper_service.auto_map_identical_names(list(source_df.columns), destination_columns)
        if not mappings:
            QMessageBox.information(
                self, "Column Mapper", "No identically-named columns found to auto-map."
            )
            return

        self._mapping_table.setRowCount(0)
        for mapping in mappings:
            self._add_row(mapping.source_column, mapping.destination_column)

    def _collect_mappings(self) -> list[ColumnMapping]:
        mappings = []
        for row in range(self._mapping_table.rowCount()):
            combo = self._mapping_table.cellWidget(row, 0)
            dest_item = self._mapping_table.item(row, 1)
            source_col = combo.currentText() if combo else ""
            dest_name = dest_item.text().strip() if dest_item else ""
            if source_col and dest_name:
                mappings.append(ColumnMapping(source_col, dest_name))
        return mappings

    # -- apply / export ----------------------------------------------------

    def _on_apply_clicked(self) -> None:
        df = self._source_picker.selected_dataframe()
        if df is None:
            QMessageBox.warning(self, "Column Mapper", "Select a source file.")
            return
        mappings = self._collect_mappings()
        if not mappings:
            QMessageBox.warning(self, "Column Mapper", "Add at least one complete mapping row.")
            return

        try:
            result = column_mapper_service.apply_mapping(
                df, mappings, keep_unmapped=self._keep_unmapped_checkbox.isChecked()
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Column mapping failed")
            QMessageBox.critical(self, "Column Mapper", str(exc))
            return

        self._last_mapped_df = result
        self._summary_label.setText(
            f"Mapping applied: {len(mappings)} column(s) mapped, result has {result.shape[1]} column(s), "
            f"{len(result):,} row(s)."
        )
        self._apply_in_place_button.setEnabled(True)
        self._export_button.setEnabled(True)

        while self._preview_container.count():
            child = self._preview_container.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        preview = ExcelPreviewWidget({"Mapped Result": result}, active_sheet="Mapped Result")
        self._preview_container.addWidget(preview)

    def _on_apply_in_place_clicked(self) -> None:
        if self._last_mapped_df is None:
            return
        key = self._source_picker.selected_file_key()
        sheet = self._source_picker.selected_sheet()
        self._registry.replace_sheet_data(key, sheet, self._last_mapped_df, description="Applied Column Mapping")
        QMessageBox.information(
            self,
            "Applied",
            f"Mapped columns applied to '{self._source_picker.selected_file_name()}' ({sheet}) in memory.",
        )

    def _on_export_clicked(self) -> None:
        if self._last_mapped_df is None:
            return
        default_name = f"Mapped_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
        default_path = str(paths.exports_dir() / default_name)
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Mapped File", default_path, "Excel Files (*.xlsx)")
        if not file_path:
            return
        try:
            self._last_mapped_df.to_excel(file_path, index=False)
            QMessageBox.information(self, "Export Complete", f"Mapped file saved to:\n{file_path}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to export mapped file")
            QMessageBox.critical(self, "Export Failed", str(exc))

    # -- templates ---------------------------------------------------------

    def _refresh_templates(self) -> None:
        self._template_combo.clear()
        for path in column_mapper_service.list_mapping_templates(paths.templates_dir()):
            self._template_combo.addItem(path.stem, userData=str(path))

    def _on_save_template_clicked(self) -> None:
        mappings = self._collect_mappings()
        if not mappings:
            QMessageBox.warning(self, "Column Mapper", "Add at least one complete mapping row before saving.")
            return
        name, ok = QInputDialog.getText(self, "Save Mapping Template", "Template name:")
        if not ok or not name.strip():
            return
        try:
            column_mapper_service.save_mapping_template(name.strip(), mappings, paths.templates_dir())
            self._refresh_templates()
            QMessageBox.information(self, "Saved", f"Mapping template '{name}' saved.")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to save mapping template")
            QMessageBox.critical(self, "Save Failed", str(exc))

    def _on_load_template_clicked(self) -> None:
        path_str = self._template_combo.currentData()
        if not path_str:
            QMessageBox.information(self, "Column Mapper", "No saved templates found.")
            return
        try:
            mappings = column_mapper_service.load_mapping_template(path_str)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to load mapping template")
            QMessageBox.critical(self, "Load Failed", str(exc))
            return

        self._mapping_table.setRowCount(0)
        for mapping in mappings:
            self._add_row(mapping.source_column, mapping.destination_column)


class ColumnMapperPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="transform.column_mapper",
        display_name="Column Mapper",
        category=PluginCategory.TRANSFORM,
        description="Map and rename columns from a source schema to a destination schema.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return ColumnMapperWidget(self.context, parent)
