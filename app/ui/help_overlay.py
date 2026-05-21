"""? key — keyboard shortcut reference overlay.

Reuses the same GlassPanel visual language as `CommandPalette` so the
two modals feel like a system. Two columns of rows: navigation and
in-page actions.
"""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    Qt,
)
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ..resources.theme import (
    BG,
    FONT_SANS_DISPLAY,
    INK,
    INK_3,
    INK_4,
    LINE,
    LINE_STRONG,
    SURFACE_HI,
)
from .widgets.kbd import KbdCombo


SHORTCUTS_NAV: list[tuple[list[str], str]] = [
    (["Ctrl", "K"],  "コマンドパレット"),
    (["Ctrl", "B"],  "サイドバーを切替"),
    (["Ctrl", "1"],  "ダッシュボード"),
    (["Ctrl", "2"],  "章一覧"),
    (["Ctrl", "4"],  "実力テスト"),
    (["Ctrl", "5"],  "学習履歴"),
    (["Ctrl", "R"],  "つづきから再開"),
    (["?"],          "このヘルプ"),
]

SHORTCUTS_PAGE: list[tuple[list[str], str]] = [
    (["↵"],          "実行 / 提出"),
    (["Esc"],        "閉じる / 戻る"),
    (["←"],          "前のページ"),
    (["→"],          "次のページ"),
    (["↑"], "コマンド選択 上"),
    (["↓"], "コマンド選択 下"),
    (["Tab"], "次のフィールド"),
]


class _ShortcutTable(QWidget):
    def __init__(
        self,
        title: str,
        rows: list[tuple[list[str], str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        head = QLabel(title, self)
        head.setStyleSheet(
            f"color: {INK_4}; font-size: 10px; font-weight: 800;"
            f" letter-spacing: 0.6px;"
        )
        layout.addWidget(head)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        layout.addLayout(grid)

        for i, (keys, label) in enumerate(rows):
            kb = KbdCombo(keys, self)
            grid.addWidget(kb, i, 0, Qt.AlignmentFlag.AlignLeft)
            lbl = QLabel(label, self)
            lbl.setStyleSheet(
                f"color: {INK}; font-size: 12px; font-weight: 500;"
                f" letter-spacing: -0.1px;"
            )
            grid.addWidget(lbl, i, 1, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)


class HelpOverlay(QDialog):
    WIDTH = 640
    HEIGHT = 460

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setStyleSheet("background: transparent;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame(self)
        panel.setObjectName("helpPanel")
        panel.setStyleSheet(
            f"QFrame#helpPanel {{ background: {SURFACE_HI};"
            f" border: 1px solid {LINE_STRONG}; border-radius: 0; }}"
        )
        outer.addWidget(panel)

        body = QVBoxLayout(panel)
        body.setContentsMargins(28, 24, 28, 24)
        body.setSpacing(18)

        title = QLabel("ショートカット", panel)
        title.setStyleSheet(
            f"color: {INK}; font-family: {FONT_SANS_DISPLAY};"
            f" font-size: 22px; font-weight: 800; letter-spacing: -0.4px;"
        )
        body.addWidget(title)

        rule = QFrame(panel)
        rule.setStyleSheet(f"background: {LINE}; max-height: 1px; min-height: 1px;")
        body.addWidget(rule)

        cols = QHBoxLayout()
        cols.setContentsMargins(0, 0, 0, 0)
        cols.setSpacing(36)
        cols.addWidget(_ShortcutTable("ナビゲーション", SHORTCUTS_NAV, panel))
        cols.addWidget(_ShortcutTable("ページ操作", SHORTCUTS_PAGE, panel))
        body.addLayout(cols, 1)

        footer = QFrame(panel)
        footer.setFixedHeight(28)
        footer.setStyleSheet(
            f"QFrame {{ background: {BG}; border: none;"
            f" border-top: 1px solid {LINE}; }}"
        )
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(16, 0, 16, 0)
        fl.setSpacing(8)
        close_hint = QLabel("Esc で閉じる", footer)
        close_hint.setStyleSheet(
            f"color: {INK_3}; font-size: 10px; font-weight: 700; letter-spacing: 0.4px;"
        )
        fl.addWidget(close_hint)
        fl.addStretch(1)
        body.addWidget(footer)

    def showEvent(self, e) -> None:  # noqa: N802
        parent = self.parentWidget()
        if parent is not None:
            geo = parent.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + int(geo.height() * 0.18)
            self.move(x, y)
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(110)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda: self.setGraphicsEffect(None))
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        super().showEvent(e)

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(e)
