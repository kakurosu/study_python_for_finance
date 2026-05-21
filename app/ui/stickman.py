"""Mascot strip — a permanent inline bar that sits *between* the page
content and the footer. Never overlaps any interactive UI.

Layout (left → right):
    [Mentor label] · [dog PNG] · [speech bubble (left-accent + tint bg)]

The dog moved from the right side to the left so the reader's eye flows
from the mascot into the spoken message (left-to-right reading order).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedLayout,
    QWidget,
)

from ..resources.theme import (
    ACCENT,
    ACCENT_TINT,
    BG,
    FONT_SANS,
    INK,
    INK_3,
    LINE,
    LINE_SUBTLE,
    SURFACE_ALT,
)

Mood = Literal["normal", "happy", "sad", "explain"]
_RESOURCE_DIR = Path(__file__).resolve().parent.parent / "resources" / "stickman"

# Mood → mascot image mapping. The dog PNGs supersede the legacy stick-figure
# SVGs when present; the SVG path is kept as a fallback so the widget still
# renders something if a PNG is missing.
#
# Mapping rationale (set 2026-05-13):
#   normal  → dog1 (smile)   — neutral/default expression
#   happy   → dog4 (laugh)   — celebrate a correct answer
#   sad     → dog3 (cry)     — wrong answer / runtime error
#   explain → dog2 (angry)   — focused/serious while explaining
_MASCOT_PNG_SIZE = (44, 44)


class StickmanStrip(QFrame):
    """Fixed-height mascot strip + speech text.

    Place it directly above the footer in a vertical layout. It will never
    overlap with any other UI element because it occupies its own row.
    """

    HEIGHT = 68

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setObjectName("StickmanStrip")
        # Same BG as the body — only the hairline top border marks this row.
        self.setStyleSheet(
            f"""
            #StickmanStrip {{
                background: {BG};
                border: none;
                border-top: 1px solid {LINE};
            }}
            """
        )
        # The bubble has its own SURFACE_ALT background so the speech reads
        # as a distinct "container" while the strip itself stays flat.

        layout = QHBoxLayout(self)
        layout.setContentsMargins(32, 10, 32, 10)
        layout.setSpacing(14)

        # 1) "Mentor" label on the very left
        self._mood_lbl = QLabel("Mentor", self)
        self._mood_lbl.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-weight: 800; letter-spacing: 0.2px;"
            f" background: transparent;"
        )
        self._mood_lbl.setFixedWidth(56)
        layout.addWidget(self._mood_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        # 2) Mascot dog (PNG / SVG fallback) — moved to LEFT so the eye flows
        #    mascot → speech.
        self._mascot_holder = QWidget(self)
        self._mascot_holder.setFixedSize(*_MASCOT_PNG_SIZE)
        mascot_stack = QStackedLayout(self._mascot_holder)
        mascot_stack.setContentsMargins(0, 0, 0, 0)
        self._mascot_stack = mascot_stack

        self._pix_label = QLabel(self._mascot_holder)
        self._pix_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pix_label.setStyleSheet("background: transparent; border: none;")
        mascot_stack.addWidget(self._pix_label)

        self._svg = QSvgWidget(self._mascot_holder)
        mascot_stack.addWidget(self._svg)

        layout.addWidget(self._mascot_holder, 0, Qt.AlignmentFlag.AlignVCenter)

        # 3) Speech bubble — distinct surface with a red left bar so it reads
        #    as "the mascot is speaking", not just a status line.
        self._bubble = QFrame(self)
        self._bubble.setObjectName("SpeechBubble")
        self._bubble.setStyleSheet(
            f"""
            #SpeechBubble {{
                background: {SURFACE_ALT};
                border: 1px solid {LINE_SUBTLE};
                border-left: 2px solid {ACCENT};
            }}
            """
        )
        bubble_layout = QHBoxLayout(self._bubble)
        bubble_layout.setContentsMargins(14, 6, 14, 6)
        bubble_layout.setSpacing(0)

        self._speech = QLabel("", self._bubble)
        self._speech.setWordWrap(False)
        self._speech.setFont(QFont("Segoe UI", 10))
        self._speech.setStyleSheet(
            f"color: {INK}; padding: 0; background: transparent; border: none;"
            f" font-family: {FONT_SANS}; font-size: 13px; letter-spacing: -0.1px;"
        )
        self._speech.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bubble_layout.addWidget(self._speech)

        layout.addWidget(self._bubble, 1, Qt.AlignmentFlag.AlignVCenter)

        # 4) Tiny live-status dot on the very right — reads as "online"
        status = QFrame(self)
        status.setFixedSize(8, 8)
        status.setStyleSheet(f"background: {ACCENT}; border: none;")
        layout.addWidget(status, 0, Qt.AlignmentFlag.AlignVCenter)

        self._mood: Mood = "normal"
        self.set_mood("normal")
        self.set_speech("")

    def set_mood(self, mood: Mood) -> None:
        self._mood = mood
        png = _RESOURCE_DIR / f"{mood}.png"
        if png.exists():
            pix = QPixmap(str(png))
            if not pix.isNull():
                scaled = pix.scaled(
                    _MASCOT_PNG_SIZE[0],
                    _MASCOT_PNG_SIZE[1],
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._pix_label.setPixmap(scaled)
                self._mascot_stack.setCurrentWidget(self._pix_label)
                # Subtly tint the bubble border when mood is happy/sad so the
                # speech color matches the mascot's emotion.
                accent = ACCENT_TINT if mood in ("sad", "explain") else "transparent"
                _ = accent  # reserved for future hue shifts
                return
        # PNG missing or unreadable — fall back to the legacy stick-figure SVG.
        svg = _RESOURCE_DIR / f"{mood}.svg"
        if svg.exists():
            self._svg.load(str(svg))
            self._mascot_stack.setCurrentWidget(self._svg)

    def set_speech(self, text: str) -> None:
        self._speech.setText(text or "—")
