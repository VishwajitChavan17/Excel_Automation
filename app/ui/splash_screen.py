"""
app.ui.splash_screen
=====================
Startup splash screen: shows the app name/version and a live status label
that main.py updates as it walks through dependency checks, config load,
and plugin discovery.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QSplashScreen

from app.core.constants import APP_NAME, APP_VERSION


def build_splash_pixmap(width: int = 560, height: int = 320) -> QPixmap:
    """Programmatically draws the splash background so Phase 1 has zero
    dependency on external image assets. Replace with a designed PNG under
    assets/ later without touching any call site."""
    from PySide6.QtGui import QLinearGradient, QPainter

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor("#0d1117"))
    gradient.setColorAt(1.0, QColor("#161b22"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, width, height, 12, 12)

    painter.setPen(QColor("#3fb950"))
    painter.setBrush(QColor("#3fb950"))
    painter.drawRoundedRect(0, 0, 6, height, 3, 3)

    painter.setPen(QColor("#e6edf3"))
    painter.setFont(QFont("Segoe UI", 22, QFont.Bold))
    painter.drawText(40, 130, APP_NAME)

    painter.setPen(QColor("#8b949e"))
    painter.setFont(QFont("Segoe UI", 11))
    painter.drawText(40, 160, "Rolls-Royce Power Systems (MTU) - Engineering Tools")

    painter.setPen(QColor("#58a6ff"))
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(40, height - 24, f"Version {APP_VERSION}")

    painter.end()
    return pixmap


class StudioSplashScreen(QSplashScreen):
    def __init__(self) -> None:
        super().__init__(build_splash_pixmap())
        self.setWindowFlag(Qt.FramelessWindowHint, True)

    def show_status(self, message: str) -> None:
        self.showMessage(
            message,
            Qt.AlignBottom | Qt.AlignRight,
            QColor("#c9d1d9"),
        )
        # Force a repaint so the message appears even while the main thread
        # is doing blocking startup work (config load, plugin discovery).
        self.repaint()
