"""
app.plugins.coming_soon
=========================
Every ribbon tab must expose *something* real -- either a working tool or a
clear, professional statement of what's planned and when. As of Phase 5,
every ribbon category has a full implementation; this module is kept
(rather than deleted) as the template for any future category that needs
a "planned, not broken" placeholder before its real implementation lands.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.core.plugin_base import Plugin, PluginCategory, PluginMetadata


class ComingSoonWidget(QWidget):
    def __init__(self, title: str, phase_label: str, planned_features: list[str], parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(heading)

        status = QLabel(f"Status: Planned -- {phase_label}")
        status.setStyleSheet("color: #d29922; font-weight: bold;")
        layout.addWidget(status)

        layout.addWidget(QLabel("Planned capabilities:"))
        for feature in planned_features:
            item = QLabel(f"   -  {feature}")
            layout.addWidget(item)

        note = QLabel(
            "This tool is on the roadmap and intentionally not yet implemented -- "
            "it is not broken. See README.md for the full phase plan."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #8b949e; margin-top: 12px;")
        layout.addWidget(note)

        layout.addStretch(1)


def _make_plugin(plugin_id, display_name, category, description, title, phase_label, features):
    class _ComingSoonPlugin(Plugin):
        metadata = PluginMetadata(
            plugin_id=plugin_id,
            display_name=display_name,
            category=category,
            description=description,
            version="0.0.0-planned",
        )

        def create_widget(self, parent=None):
            return ComingSoonWidget(title, phase_label, features, parent)

    _ComingSoonPlugin.__name__ = f"ComingSoon_{plugin_id.replace('.', '_')}"
    return _ComingSoonPlugin
