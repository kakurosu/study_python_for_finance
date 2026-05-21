"""Keyboard-cap label widgets.

`Kbd` renders a single key (e.g. "Ctrl", "K", "↵") as a small monospace
key-cap. `KbdCombo` lays a sequence of caps in a row with a tiny "+" gap.

The visual style is driven entirely by `QLabel[kbd="true"]` rules declared
in `app/resources/theme.py`, which keeps the border-radius:0 constraint in
one place.
"""

from __future__ import annotations

from collections.abc import Sequence

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class Kbd(QLabel):
    """A single key-cap label."""

    def __init__(
        self,
        key: str,
        parent: QWidget | None = None,
        *,
        muted: bool = False,
    ) -> None:
        super().__init__(key, parent)
        self.setProperty("kbd", True)
        if muted:
            self.setProperty("kbdMuted", True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(16)


class KbdCombo(QFrame):
    """A horizontal sequence of `Kbd` caps (e.g. Ctrl + K)."""

    def __init__(
        self,
        keys: Sequence[str],
        parent: QWidget | None = None,
        *,
        spacing: int = 3,
        muted: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing)
        for key in keys:
            layout.addWidget(Kbd(key, self, muted=muted))
