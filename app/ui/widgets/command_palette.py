"""Command Palette — Ctrl+K searchable command dialog (VS Code style)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class CommandPalette(QDialog):
    """Floating searchable command palette. Triggered by Ctrl+K."""

    command_activated = Signal(str)  # emits plugin_id

    def __init__(self, commands: list[tuple[str, str, str]], parent=None) -> None:
        """
        Parameters
        ----------
        commands : list of (plugin_id, display_name, category)
        """
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog | Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMinimumWidth(520)
        self.setMaximumWidth(640)
        self.setModal(True)

        self._commands = commands

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Type a command...")
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit {"
            "  background-color: #3c3c3c;"
            "  color: #cccccc;"
            "  border: 1px solid #0078d4;"
            "  border-radius: 4px;"
            "  font-size: 14px;"
            "  padding: 10px 14px;"
            "  margin: 8px;"
            "  selection-background-color: #264f78;"
            "}"
            "QLineEdit:focus { border-color: #0078d4; }"
        )
        self._search.textChanged.connect(self._filter)
        self._search.returnPressed.connect(self._activate_selected)
        layout.addWidget(self._search)

        info = QLabel(
            "  \u2302  Navigate with \u2191\u2193  \u23CE  Select  \u238B  Close"
        )
        info.setStyleSheet(
            "color: #555555; font-size: 10px; padding: 4px 12px;"
            "border-bottom: 1px solid #3c3c3c; background: #252526;"
        )
        layout.addWidget(info)

        self._list = QListWidget()
        self._list.setStyleSheet(
            "QListWidget {"
            "  background-color: #1e1e1e;"
            "  border: none;"
            "  border-top: 1px solid #3c3c3c;"
            "  outline: none;"
            "  padding: 4px;"
            "}"
            "QListWidget::item {"
            "  padding: 6px 12px;"
            "  border-radius: 3px;"
            "  color: #cccccc;"
            "}"
            "QListWidget::item:hover {"
            "  background-color: #2a2d2e;"
            "}"
            "QListWidget::item:selected {"
            "  background-color: #094771;"
            "  color: #ffffff;"
            "}"
        )
        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.setMinimumHeight(300)
        self._list.setMaximumHeight(400)
        layout.addWidget(self._list)

        self._populate()
        self._search.setFocus()

    def _populate(self, filter_text: str = "") -> None:
        self._list.clear()
        needle = filter_text.lower()
        for plugin_id, name, category in self._commands:
            if needle and needle not in name.lower() and needle not in plugin_id.lower():
                continue
            category_lbl = f"  [{category}]" if category else ""
            item = QListWidgetItem(f"  {name}{category_lbl}")
            item.setData(Qt.UserRole, plugin_id)
            self._list.addItem(item)

        if self._list.count() == 0:
            item = QListWidgetItem("  No matching commands")
            item.setFlags(Qt.NoItemFlags)
            item.setForeground(Qt.gray)
            self._list.addItem(item)

    def _filter(self, text: str) -> None:
        self._populate(text)

    def _activate_selected(self) -> None:
        current = self._list.currentItem()
        if current and current.data(Qt.UserRole):
            self.command_activated.emit(current.data(Qt.UserRole))
            self.accept()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        if item.data(Qt.UserRole):
            self.command_activated.emit(item.data(Qt.UserRole))
            self.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.matches(QKeySequence.MoveToPreviousLine):
            prev = self._list.currentRow() - 1
            if prev >= 0:
                self._list.setCurrentRow(prev)
        elif event.matches(QKeySequence.MoveToNextLine):
            nxt = self._list.currentRow() + 1
            if nxt < self._list.count():
                self._list.setCurrentRow(nxt)
        else:
            super().keyPressEvent(event)
