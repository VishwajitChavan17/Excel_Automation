"""
app.plugins.template_manager_tool
====================================
The Template Engine's browsing UI: lists every saved Column Mapping
template and Validation Rule Set template, shows a JSON preview of the
selected one, and lets the user delete templates they no longer need.
Saving happens from the Column Mapper and Validation Rules tools
themselves (where the data being templated already lives); this tool is
the central place to see everything that's been saved across both.
"""

from __future__ import annotations

import json

from loguru import logger
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core import paths
from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata
from app.services.excel import column_mapper_service, validation_service


class TemplateManagerWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)

        splitter = QSplitter()
        splitter.setChildrenCollapsible(False)

        lists_panel = QWidget()
        lists_layout = QVBoxLayout(lists_panel)

        mapping_box = QGroupBox("Column Mapping Templates")
        mapping_layout = QVBoxLayout(mapping_box)
        self._mapping_list = QListWidget()
        self._mapping_list.currentItemChanged.connect(self._on_mapping_selected)
        mapping_layout.addWidget(self._mapping_list)
        mapping_buttons = QHBoxLayout()
        delete_mapping_button = QPushButton("Delete Selected")
        delete_mapping_button.clicked.connect(self._on_delete_mapping_clicked)
        mapping_buttons.addWidget(delete_mapping_button)
        mapping_layout.addLayout(mapping_buttons)
        lists_layout.addWidget(mapping_box)

        validation_box = QGroupBox("Validation Rule Set Templates")
        validation_layout = QVBoxLayout(validation_box)
        self._validation_list = QListWidget()
        self._validation_list.currentItemChanged.connect(self._on_validation_selected)
        validation_layout.addWidget(self._validation_list)
        validation_buttons = QHBoxLayout()
        delete_validation_button = QPushButton("Delete Selected")
        delete_validation_button.clicked.connect(self._on_delete_validation_clicked)
        validation_buttons.addWidget(delete_validation_button)
        validation_layout.addLayout(validation_buttons)
        lists_layout.addWidget(validation_box)

        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_all)
        lists_layout.addWidget(refresh_button)

        splitter.addWidget(lists_panel)

        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.addWidget(QLabel("Template Preview:"))
        self._preview_text = QPlainTextEdit()
        self._preview_text.setReadOnly(True)
        preview_layout.addWidget(self._preview_text)
        splitter.addWidget(preview_panel)
        splitter.setSizes([380, 620])

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(splitter)

        self._refresh_all()

    def _validation_templates_dir(self):
        return paths.templates_dir() / "validation"

    def _refresh_all(self) -> None:
        self._mapping_list.clear()
        for path in column_mapper_service.list_mapping_templates(paths.templates_dir()):
            self._mapping_list.addItem(path.stem)
            self._mapping_list.item(self._mapping_list.count() - 1).setData(1000, str(path))

        self._validation_list.clear()
        for path in validation_service.list_validation_templates(self._validation_templates_dir()):
            self._validation_list.addItem(path.stem)
            self._validation_list.item(self._validation_list.count() - 1).setData(1000, str(path))

        self._preview_text.clear()

    def _on_mapping_selected(self, current, _previous) -> None:
        if current is None:
            return
        self._show_preview(current.data(1000))

    def _on_validation_selected(self, current, _previous) -> None:
        if current is None:
            return
        self._show_preview(current.data(1000))

    def _show_preview(self, path_str: str) -> None:
        try:
            from pathlib import Path

            content = json.loads(Path(path_str).read_text(encoding="utf-8"))
            self._preview_text.setPlainText(json.dumps(content, indent=2))
        except Exception as exc:  # noqa: BLE001
            self._preview_text.setPlainText(f"Could not read template: {exc}")

    def _on_delete_mapping_clicked(self) -> None:
        self._delete_selected(self._mapping_list, "column mapping template")

    def _on_delete_validation_clicked(self) -> None:
        self._delete_selected(self._validation_list, "validation rule set template")

    def _delete_selected(self, list_widget: QListWidget, kind: str) -> None:
        item = list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Template Manager", f"Select a {kind} to delete.")
            return
        confirm = QMessageBox.question(self, "Delete Template", f"Delete '{item.text()}'? This cannot be undone.")
        if confirm != QMessageBox.Yes:
            return
        try:
            from pathlib import Path

            Path(item.data(1000)).unlink(missing_ok=True)
            self._refresh_all()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to delete template")
            QMessageBox.critical(self, "Delete Failed", str(exc))


class TemplateManagerPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="templates.engine",
        display_name="Template Manager",
        category=PluginCategory.TEMPLATES,
        description="Browse, preview, and manage saved column mapping and validation rule templates.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return TemplateManagerWidget(self.context, parent)
