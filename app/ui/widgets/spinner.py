"""Hairline arc spinner.

Renders a 1px-thick arc (270°) that rotates 360° every ``period_ms``.
Sharp corners only — the arc itself is a stroke, not a rounded rect, so
the border-radius: 0 invariant is preserved.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QTimer, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from ...resources.theme import INK_4, LINE_FOCUS


class Spinner(QWidget):
    DEFAULT_DIAMETER = 14

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        diameter: int = DEFAULT_DIAMETER,
        period_ms: int = 800,
        color: str = LINE_FOCUS,
        rail_color: str | None = INK_4,
    ) -> None:
        super().__init__(parent)
        self._diameter = diameter
        self._color = QColor(color)
        self._rail_color = QColor(rail_color) if rail_color else None
        self._angle = 0
        self.setFixedSize(diameter + 2, diameter + 2)
        self._timer = QTimer(self)
        self._timer.setInterval(max(16, period_ms // 30))
        self._timer.timeout.connect(self._tick)
        self._step = 360 // 30
        self.start()

    def start(self) -> None:
        if not self._timer.isActive():
            self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._angle = (self._angle + self._step) % 360
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self._diameter, self._diameter)
        if self._rail_color is not None:
            rail_pen = QPen(self._rail_color)
            rail_pen.setWidth(1)
            p.setPen(rail_pen)
            p.drawArc(rect, 0, 360 * 16)
        pen = QPen(self._color)
        pen.setWidth(2)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        # Start at top, sweep 270° clockwise.
        p.drawArc(rect, (90 - self._angle) * 16, -270 * 16)
        p.end()
