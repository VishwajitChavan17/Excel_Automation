"""
app.plugins.import_tools
==========================
The Import ribbon tab's landing page. Functional (not a placeholder): its
buttons call straight into MainWindow's existing background file-loading
pipeline, so "Import" is a real, working entry point to the same loader
used by File > Open.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata


class ImportWidget(QWidget):
    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self._context = context

        layout = QVBoxLayout(self)
        title = QLabel("Import Excel / CSV Data")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Load one or more workbooks into the Studio. Loaded files appear "
            "under Project Explorer -> Loaded Excel Files and become available "
            "to every tool (Compare, Lookup & Copy, Duplicate Finder, ...)."
        )
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        open_files_btn = QPushButton("Open File(s)...")
        open_files_btn.setMinimumHeight(44)
        open_files_btn.clicked.connect(self._open_files)
        layout.addWidget(open_files_btn)

        open_folder_btn = QPushButton("Open Folder (all supported files)...")
        open_folder_btn.setMinimumHeight(44)
        open_folder_btn.clicked.connect(self._open_folder)
        layout.addWidget(open_folder_btn)

        formats = QLabel("Supported formats: .xlsx  .xlsm  .xls  .csv  .tsv  .ods")
        formats.setStyleSheet("color: #8b949e;")
        layout.addWidget(formats)

        layout.addStretch(1)

    def _open_files(self) -> None:
        if self._context.main_window is not None:
            self._context.main_window.open_files_dialog()

    def _open_folder(self) -> None:
        if self._context.main_window is not None:
            self._context.main_window.open_folder_dialog()


class ImportPlugin(Plugin):
    metadata = PluginMetadata(
        plugin_id="import.open_files",
        display_name="Open Files",
        category=PluginCategory.IMPORT,
        description="Load Excel/CSV files or an entire folder into the Studio.",
        version="1.0.0",
    )

    def create_widget(self, parent=None):
        return ImportWidget(self.context, parent)
