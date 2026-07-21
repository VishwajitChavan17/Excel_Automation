from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QSplashScreen

from app.core.constants import APP_NAME, APP_VERSION


def build_splash_pixmap(width: int = 600, height: int = 360) -> QPixmap:
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor("#1e1e1e"))
    gradient.setColorAt(0.6, QColor("#252526"))
    gradient.setColorAt(1.0, QColor("#2d2d2d"))
    painter.setBrush(gradient)
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(0, 0, width, height, 8, 8)

    painter.setPen(QColor("#0078d4"))
    painter.setBrush(QColor("#0078d4"))
    painter.drawRoundedRect(0, 0, 6, height, 3, 3)

    painter.setPen(QColor("#0078d4"))
    painter.setFont(QFont("Segoe UI", 10, QFont.Normal))
    painter.drawText(48, 120, "Rolls-Royce Power Systems (MTU)")

    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 28, QFont.Light))
    painter.drawText(48, 168, APP_NAME)

    painter.setPen(QColor("#969696"))
    painter.setFont(QFont("Segoe UI", 12))
    painter.drawText(48, 200, "Engineering Data Platform")

    painter.setPen(QColor("#4ec9b0"))
    painter.setFont(QFont("Segoe UI", 9))
    painter.drawText(48, height - 28, f"Version {APP_VERSION}")

    painter.setPen(QColor("#555555"))
    painter.setFont(QFont("Segoe UI", 8))
    painter.drawText(48, height - 12, "Loading...")

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
            QColor("#969696"),
        )
        self.repaint()
