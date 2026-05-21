"""QStackedLayout subclass that cross-fades the incoming widget.

Used by `ChapterView` for inter-page transitions. Each switch fades the
new widget from opacity 0 → 1 over `DURATION_MS` with an OutCubic easing.

Notes:
- Effect is removed after the animation finishes (`finished` slot), so the
  child keeps its normal paint pipeline once the transition completes.
- Setting an opacity effect repeatedly on the same widget is safe; we
  reuse `setGraphicsEffect(None)` to detach.
"""

from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QStackedLayout, QWidget


class FadeStack(QStackedLayout):
    DURATION_MS = 140

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._anim: QPropertyAnimation | None = None

    def setCurrentWidget(self, w: QWidget) -> None:  # noqa: N802
        old = self.currentWidget()
        super().setCurrentWidget(w)
        if old is None or old is w:
            return
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self.parent())
        anim.setDuration(self.DURATION_MS)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _cleanup() -> None:
            try:
                w.setGraphicsEffect(None)
            except RuntimeError:
                pass

        anim.finished.connect(_cleanup)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._anim = anim

    def setCurrentIndex(self, idx: int) -> None:  # noqa: N802
        w = self.widget(idx)
        if w is not None:
            self.setCurrentWidget(w)
        else:
            super().setCurrentIndex(idx)
