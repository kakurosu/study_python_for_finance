"""Skeleton placeholder rows for loading states.

Each row is a 1-pixel solid `SURFACE_ALT` bar whose opacity pulses between
0.35 and 0.75 every 1.2 s. Sharp corners only.
"""

from __future__ import annotations

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QVBoxLayout,
    QWidget,
)

from ...resources.theme import SURFACE_ALT


class Skeleton(QWidget):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        rows: int = 3,
        row_height: int = 10,
        row_spacing: int = 8,
        duration_ms: int = 1200,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(row_spacing)
        self._effects: list[QGraphicsOpacityEffect] = []
        self._anims: list[QPropertyAnimation] = []
        for i in range(rows):
            bar = QFrame(self)
            bar.setFixedHeight(row_height)
            bar.setStyleSheet(f"background: {SURFACE_ALT}; border: none;")
            # Stagger widths so it does not look mechanical.
            width_pct = [100, 88, 72, 94, 60][i % 5]
            bar.setMaximumWidth(int(360 * width_pct / 100))
            layout.addWidget(bar)

            eff = QGraphicsOpacityEffect(bar)
            bar.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(duration_ms)
            anim.setStartValue(0.35)
            anim.setEndValue(0.75)
            anim.setEasingCurve(QEasingCurve.Type.InOutSine)
            anim.setLoopCount(-1)
            # Each row out of phase.
            anim.setCurrentTime((duration_ms // rows) * i)
            anim.start()
            self._effects.append(eff)
            self._anims.append(anim)
