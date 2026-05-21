"""Ctrl+K command palette — Raycast-style searcher.

Opens a frameless modal dialog centered over the main window. The user
types to filter actions; ↑/↓ navigates, Enter executes, Esc closes.

Visual rules:
- border-radius: 0 everywhere
- Glass background via `SURFACE_GLASS` color (semi-translucent dark)
- Group headers between matched rows; empty groups hidden
- Right edge shows shortcut Kbd caps if the action defines one
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..resources.theme import (
    ACCENT,
    BG,
    FONT_MONO,
    FONT_SANS,
    INK,
    INK_2,
    INK_3,
    INK_4,
    LINE,
    LINE_STRONG,
    LINE_SUBTLE,
    SURFACE_ALT,
    SURFACE_HI,
    SURFACE_TINT,
)
from .command_actions import Action, CommandRegistry
from .widgets.kbd import Kbd, KbdCombo


class _ActionRow(QFrame):
    """A single selectable action row (icon · title · subtitle · kbd)."""

    activated = pyqtSignal(object)  # emits the Action

    def __init__(self, action: Action, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action = action
        self._selected = False
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_qss()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        icon = QLabel(action.icon, self)
        icon.setStyleSheet(
            f"color: {INK_3}; font-size: 13px; font-weight: 700; min-width: 16px;"
        )
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        title = QLabel(action.title, self)
        title.setStyleSheet(
            f"color: {INK}; font-size: 13px; font-weight: 600; letter-spacing: -0.1px;"
        )
        layout.addWidget(title, 1)

        if action.subtitle:
            sub = QLabel(action.subtitle, self)
            sub.setStyleSheet(
                f"color: {INK_4}; font-size: 11px; font-weight: 600;"
                f" font-family: {FONT_MONO};"
            )
            layout.addWidget(sub, 0, Qt.AlignmentFlag.AlignVCenter)

        if action.shortcut:
            kbd = KbdCombo(list(action.shortcut), self, muted=True)
            layout.addWidget(kbd, 0, Qt.AlignmentFlag.AlignVCenter)

    def _update_qss(self) -> None:
        bg = SURFACE_TINT if self._selected else "transparent"
        left = ACCENT if self._selected else "transparent"
        self.setStyleSheet(
            f"""
            _ActionRow, QFrame#row {{ background: {bg};
                border: none;
                border-left: 2px solid {left};
            }}
            QFrame {{ background: transparent; border: none; }}
            """
        )
        self.setObjectName("row")
        # Apply via stylesheet on self only.
        self.setStyleSheet(
            f"QFrame#row {{ background: {bg}; border: none;"
            f" border-left: 2px solid {left}; }}"
            f" QFrame {{ background: transparent; border: none; }}"
        )

    def set_selected(self, on: bool) -> None:
        if self._selected == on:
            return
        self._selected = on
        self._update_qss()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.action)
        super().mouseReleaseEvent(e)

    def enterEvent(self, e) -> None:  # noqa: N802
        # Selection is keyboard-driven; hover does not select but tints.
        super().enterEvent(e)


class CommandPalette(QDialog):
    """Modal palette. Reads its actions from a `CommandRegistry`."""

    WIDTH = 640
    MAX_HEIGHT = 480

    def __init__(self, registry: CommandRegistry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = registry
        self._rows: list[_ActionRow] = []
        self._selected_idx = 0

        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(self.WIDTH)

        # Build chrome
        self.setStyleSheet(
            f"background: transparent;"
        )

        panel = QFrame(self)
        panel.setObjectName("palette")
        panel.setStyleSheet(
            f"""
            QFrame#palette {{ background: {SURFACE_HI};
                border: 1px solid {LINE_STRONG}; border-radius: 0; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        body = QVBoxLayout(panel)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # --- search field ---------------------------------------------------
        search_row = QFrame(panel)
        search_row.setFixedHeight(52)
        search_row.setStyleSheet(
            f"QFrame {{ background: transparent; border: none;"
            f" border-bottom: 1px solid {LINE}; }}"
        )
        sr_l = QHBoxLayout(search_row)
        sr_l.setContentsMargins(20, 0, 16, 0)
        sr_l.setSpacing(12)

        glyph = QLabel("⌕", search_row)
        glyph.setStyleSheet(
            f"color: {INK_3}; font-size: 16px; font-weight: 700;"
        )
        sr_l.addWidget(glyph)

        self._field = QLineEdit(search_row)
        self._field.setPlaceholderText("コマンドや章名を検索…")
        self._field.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; padding: 0;"
            f" color: {INK}; font-family: {FONT_SANS}; font-size: 15px;"
            f" font-weight: 500; letter-spacing: -0.1px; }}"
            f"QLineEdit:focus {{ border: none; }}"
        )
        self._field.textChanged.connect(self._refresh_rows)
        self._field.installEventFilter(self)
        sr_l.addWidget(self._field, 1)

        esc_lbl = QLabel("ESC", search_row)
        esc_lbl.setProperty("kbd", True)
        esc_lbl.setProperty("kbdMuted", True)
        esc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sr_l.addWidget(esc_lbl)

        body.addWidget(search_row)

        # --- scrollable rows ------------------------------------------------
        scroll = QScrollArea(panel)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("background: transparent; border: none;")
        self._scroll = scroll

        self._rows_holder = QWidget()
        self._rows_holder.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_holder)
        self._rows_layout.setContentsMargins(8, 8, 8, 8)
        self._rows_layout.setSpacing(2)
        scroll.setWidget(self._rows_holder)

        body.addWidget(scroll, 1)

        # --- footer ---------------------------------------------------------
        foot = QFrame(panel)
        foot.setFixedHeight(28)
        foot.setStyleSheet(
            f"QFrame {{ background: {BG}; border: none;"
            f" border-top: 1px solid {LINE}; }}"
        )
        fl = QHBoxLayout(foot)
        fl.setContentsMargins(16, 0, 16, 0)
        fl.setSpacing(10)

        self._count_lbl = QLabel("", foot)
        self._count_lbl.setStyleSheet(
            f"color: {INK_4}; font-size: 10px; font-weight: 700;"
            f" font-family: {FONT_MONO}; letter-spacing: 0.3px;"
        )
        fl.addWidget(self._count_lbl)
        fl.addStretch(1)

        for label, keys in [
            ("選択", ["↑", "↓"]),
            ("実行", ["↵"]),
            ("閉じる", ["Esc"]),
        ]:
            txt = QLabel(label, foot)
            txt.setStyleSheet(
                f"color: {INK_4}; font-size: 10px; font-weight: 600;"
                f" font-family: {FONT_MONO};"
            )
            fl.addWidget(txt)
            kb = KbdCombo(keys, foot, muted=True)
            fl.addWidget(kb)
            spacer = QLabel(" ", foot)
            fl.addWidget(spacer)

        body.addWidget(foot)

        # Initial population
        self._refresh_rows("")

    # ---------------------------------------------------------------------
    def _refresh_rows(self, query: str) -> None:
        # Clear current rows
        while self._rows_layout.count():
            it = self._rows_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._rows = []

        actions = self._registry.search(query)
        groups = self._registry.grouped(actions)

        total = 0
        for group_label, items in groups:
            if not items:
                continue
            head = QLabel(group_label, self._rows_holder)
            head.setStyleSheet(
                f"color: {INK_4}; font-size: 9px; font-weight: 800;"
                f" letter-spacing: 0.6px; padding: 10px 14px 4px 14px;"
            )
            self._rows_layout.addWidget(head)
            for a in items:
                row = _ActionRow(a, self._rows_holder)
                row.activated.connect(self._on_row_activated)
                self._rows_layout.addWidget(row)
                self._rows.append(row)
                total += 1
        self._rows_layout.addStretch(1)

        self._selected_idx = 0 if self._rows else -1
        self._update_selection()
        self._count_lbl.setText(f"{total} 件")

    # ---------------------------------------------------------------------
    def _update_selection(self) -> None:
        for i, row in enumerate(self._rows):
            row.set_selected(i == self._selected_idx)
        if 0 <= self._selected_idx < len(self._rows):
            row = self._rows[self._selected_idx]
            self._scroll.ensureWidgetVisible(row, 0, 40)

    def _move_selection(self, delta: int) -> None:
        if not self._rows:
            return
        self._selected_idx = (self._selected_idx + delta) % len(self._rows)
        self._update_selection()

    def _execute_selected(self) -> None:
        if not (0 <= self._selected_idx < len(self._rows)):
            return
        action = self._rows[self._selected_idx].action
        self._on_row_activated(action)

    def _on_row_activated(self, action: Action) -> None:
        self.accept()
        try:
            action.run()
        except Exception:  # noqa: BLE001
            import logging
            logging.exception("command palette action failed: %s", action.id)

    # ---------------------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._field and event.type() == event.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            key = event.key()
            if key == Qt.Key.Key_Down:
                self._move_selection(+1)
                return True
            if key == Qt.Key.Key_Up:
                self._move_selection(-1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._execute_selected()
                return True
            if key == Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(obj, event)

    # ---------------------------------------------------------------------
    def showEvent(self, e) -> None:  # noqa: N802
        # Center over parent
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + int(geo.height() * 0.18)
            self.move(x, y)

        # Compute height
        h = min(self.MAX_HEIGHT, max(180, 90 + 42 * max(1, len(self._rows))))
        self.setFixedHeight(h)

        # Fade in
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(110)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

        self._field.setFocus()
        self._field.selectAll()
        super().showEvent(e)
