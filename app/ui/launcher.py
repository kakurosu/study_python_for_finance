"""Launcher (TOP) screen — quiet, business-grade, sharp monochrome layout.

Design intent:
- A wide top bar that reads like a SaaS dashboard.
- A two-column body: left = "CONTINUE" main card (prominent), right = small
  metrics stack.
- A clean tabular list of action rows for the rest. No gimmicks.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from ..content.schemas import Chapter
from ..db.models import ChapterStatus
from ..db.repo import Repository
from ..resources.theme import (
    ACCENT,
    ACCENT_SOFT,
    ACCENT_TINT,
    BG,
    BG_ALT,
    FONT_MONO,
    FONT_SANS_DISPLAY,
    INK,
    INK_2,
    INK_3,
    INK_4,
    INK_5,
    LINE,
    LINE_STRONG,
    PHASE_LABELS,
    SUCCESS,
    SURFACE,
    SURFACE_ALT,
)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


class _Rule(QFrame):
    def __init__(self, variant: str = "rule", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("variant", variant)
        self.setFixedHeight(2 if variant != "rule" else 1)


class _Kicker(QLabel):
    def __init__(self, text: str, *, color: str = ACCENT, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: 800; letter-spacing: 0;"
        )


class TopBar(QFrame):
    """SaaS-style top bar. Left: wordmark. Right: optional context."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setStyleSheet(
            f"QFrame {{ background: {BG}; border: none; border-bottom: 1px solid {LINE}; }}"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(40, 0, 40, 0)
        layout.setSpacing(20)

        mark = QLabel(self)
        mark.setText(
            f'<span style="color:{INK}; font-weight:800; letter-spacing:-0.4px;">Study</span>'
            f'<span style="color:{ACCENT}; font-weight:800;">.</span>'
            f'<span style="color:{INK}; font-weight:800; letter-spacing:-0.4px;">Py</span>'
        )
        mark.setStyleSheet("font-size: 16px;")
        layout.addWidget(mark)

        sep = QFrame(self)
        sep.setStyleSheet(f"background: {LINE};")
        sep.setFixedSize(1, 24)
        layout.addWidget(sep)

        sub = QLabel("Finance Edition", self)
        sub.setStyleSheet(
            f"color: {INK_3}; font-size: 10px; font-weight: 700; letter-spacing: 0;"
        )
        layout.addWidget(sub)

        layout.addStretch(1)

        version = QLabel("v0.1 · 2026", self)
        version.setStyleSheet(
            f"color: {INK_4}; font-size: 11px; font-weight: 600; letter-spacing: 0;"
            f" font-family: 'Cascadia Mono', 'Consolas', monospace;"
        )
        layout.addWidget(version)


class ContinueCard(QFrame):
    """Prominent card: continue from where the user left off.

    Design: white default with a thin red left bar that thickens on hover.
    Hover paints a soft pink wash over the card and shifts text to red — same
    "marker highlight" language used by every other interactive row.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        last_chapter: Chapter | None,
        last_page_index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ContinueCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # White-based stylish game splash. Inspired by Lumines / Apple Arcade
        # quiz UIs — clean white panel, big display title, mono HUD accents,
        # red corner notch in the top-right, and a "> PRESS TO RESUME" marquee.
        self.setStyleSheet(
            f"""
            #ContinueCard {{
                background: #141414;
                border: 1px solid {INK};
                border-left: 6px solid {ACCENT};
            }}
            #ContinueCard:hover {{
                background: {ACCENT_SOFT};
            }}
            #ContinueCard:hover #cccTitle {{ color: {ACCENT}; }}
            #ContinueCard:hover #cccArrow {{ color: {ACCENT}; }}
            """
        )

        # Corner notch (top-right) — small red square that hints at "this is selectable"
        notch = QFrame(self)
        notch.setStyleSheet(f"background: {ACCENT}; border: none;")
        notch.setFixedSize(14, 14)
        notch.move(0, 0)  # placed in resizeEvent
        self._notch = notch

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(0)

        # Top tag row: [ CONTINUE ] · save tag
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        tag = QLabel("Continue", self)
        tag.setStyleSheet(
            f"color: {ACCENT}; background: transparent;"
            f" font-size: 10px; font-weight: 800; letter-spacing: 0;"
        )
        top.addWidget(tag)
        top.addStretch(1)
        save_lbl = QLabel("Save 01", self)
        save_lbl.setStyleSheet(
            f"color: {INK_4}; background: transparent;"
            f" font-size: 9px; font-weight: 700; letter-spacing: 0;"
        )
        top.addWidget(save_lbl)
        layout.addLayout(top)
        layout.addSpacing(14)

        if last_chapter is None:
            title = QLabel("Begin Your Journey", self)
            title.setObjectName("cccTitle")
            title.setStyleSheet(
                f"color: {INK}; background: transparent;"
                f" font-size: 30px; font-weight: 900; letter-spacing: -0.8px;"
            )
            layout.addWidget(title)
            layout.addSpacing(6)
            sub = QLabel("New Game / 第 1 章 から学習を始めます", self)
            sub.setStyleSheet(
                f"color: {INK_3}; background: transparent;"
                f" font-size: 11px; font-weight: 700; letter-spacing: 0;"
                )
            layout.addWidget(sub)
        else:
            title = QLabel(last_chapter.title, self)
            title.setObjectName("cccTitle")
            title.setStyleSheet(
                f"color: {INK}; background: transparent;"
                f" font-size: 28px; font-weight: 900; letter-spacing: -0.6px;"
            )
            title.setWordWrap(True)
            layout.addWidget(title)
            layout.addSpacing(8)

            crumb = QLabel(
                f"{PHASE_LABELS[last_chapter.phase]} · Ch {last_chapter.id:02d} · "
                f"Page {last_page_index + 1:02d} / {len(last_chapter.pages):02d}",
                self,
            )
            crumb.setStyleSheet(
                f"color: {INK_3}; background: transparent;"
                f" font-size: 11px; font-weight: 700; letter-spacing: 0;"
                )
            layout.addWidget(crumb)

        layout.addStretch(1)
        layout.addSpacing(12)

        # "> PRESS TO RESUME →"
        cta_row = QHBoxLayout()
        cta_row.setContentsMargins(0, 0, 0, 0)
        cta_row.setSpacing(8)
        marker = QLabel(">", self)
        marker.setStyleSheet(
            f"color: {ACCENT}; background: transparent; font-size: 14px;"
            f" font-weight: 800; font-family: {FONT_MONO};"
        )
        cta_row.addWidget(marker)
        cta_label = QLabel("Press to resume", self)
        cta_label.setStyleSheet(
            f"color: {ACCENT}; background: transparent;"
            f" font-size: 11px; font-weight: 800; letter-spacing: 0;"
        )
        cta_row.addWidget(cta_label)
        cta_row.addStretch(1)
        arrow = QLabel("→", self)
        arrow.setObjectName("cccArrow")
        arrow.setStyleSheet(
            f"color: {ACCENT}; background: transparent; font-size: 22px; font-weight: 400;"
        )
        cta_row.addWidget(arrow)
        layout.addLayout(cta_row)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        # Pin the corner notch to the top-right inside the card border.
        if hasattr(self, "_notch"):
            self._notch.move(self.width() - self._notch.width() - 8, 8)
            self._notch.raise_()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class StatRow(QFrame):
    """HUD-style stat row: LABEL · ascii progress bar · NN

    All three columns have fixed widths so values from different rows align
    perfectly, and the bar gives a game-y "loading" feel.
    """

    def __init__(
        self,
        label: str,
        value: int,
        total: int,
        *,
        color: str = INK,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(14)

        lab = QLabel(label, self)
        lab.setStyleSheet(
            f"color: {INK_3}; background: transparent;"
            f" font-size: 10px; font-weight: 700; letter-spacing: 0;"
        )
        lab.setFixedWidth(96)
        layout.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)

        # Dot bar — Linear / Notion style. Filled dots use accent, empty
        # dots use a stronger muted color so the contrast holds on dark bg.
        bar_total = 12
        filled = 0 if total == 0 else int(round((value / total) * bar_total))
        filled = max(0, min(bar_total, filled))
        bar_text = (
            f'<span style="color:{ACCENT}">{"●" * filled}</span>'
            f'<span style="color:{INK_5}">{"○" * (bar_total - filled)}</span>'
        )
        bar = QLabel(bar_text, self)
        bar.setStyleSheet(
            f"background: transparent; font-size: 14px; font-weight: 700;"
            f" letter-spacing: 3px; font-family: {FONT_MONO};"
        )
        bar.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(bar, 1, Qt.AlignmentFlag.AlignVCenter)

        val = QLabel(f"{value:02d}", self)
        val.setStyleSheet(
            f"color: {color}; background: transparent;"
            f" font-size: 18px; font-weight: 800;"
        )
        val.setFixedWidth(44)
        val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(val, 0, Qt.AlignmentFlag.AlignVCenter)


class ActionRow(QFrame):
    """List row with a "marker highlight" hover state.

    Design language (matches Linear / Vercel / modern docs):
    - Default: white, hairline bottom border.
    - Hover: soft pink wash (#FEF2F2) + 4px red left bar + red title text + red arrow.
      The left bar is the unmistakable "you are about to act on this" marker.
    """

    clicked = pyqtSignal()

    def __init__(
        self,
        index: str,
        title: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ActionRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            #ActionRow {{
                background: #141414;
                border-left: 4px solid transparent;
                border-bottom: 1px solid {LINE};
            }}
            #ActionRow:hover {{
                background: {ACCENT_SOFT};
                border-left: 4px solid {ACCENT};
                border-bottom: 1px solid {ACCENT};
            }}
            #ActionRow:hover #actionRowTitle {{ color: {ACCENT}; }}
            #ActionRow:hover #actionRowArrow {{ color: {ACCENT}; }}
            """
        )
        self.setMinimumHeight(72)

        layout = QHBoxLayout(self)
        # Left margin compensates for the 4px border-left so content doesn't shift on hover
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(24)

        idx_lbl = QLabel(index, self)
        idx_lbl.setStyleSheet(
            f"color: {INK_4}; background: transparent;"
            f" font-size: 11px; font-weight: 800; letter-spacing: 0;"
        )
        idx_lbl.setMinimumWidth(36)
        layout.addWidget(idx_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_lbl = QLabel(title, self)
        title_lbl.setObjectName("actionRowTitle")
        title_lbl.setStyleSheet(
            f"color: {INK}; background: transparent;"
            f" font-size: 15px; font-weight: 700; letter-spacing: -0.2px;"
        )
        text_col.addWidget(title_lbl)
        sub_lbl = QLabel(subtitle, self)
        sub_lbl.setStyleSheet(
            f"color: {INK_3}; background: transparent; font-size: 12px;"
        )
        sub_lbl.setWordWrap(True)
        text_col.addWidget(sub_lbl)
        layout.addLayout(text_col, 1)

        arrow = QLabel("→", self)
        arrow.setObjectName("actionRowArrow")
        arrow.setStyleSheet(
            f"color: {INK_4}; background: transparent;"
            f" font-size: 18px; font-weight: 400;"
        )
        layout.addWidget(arrow, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(e)


class ChapterRow(QFrame):
    """Same marker-bar hover language as ActionRow."""

    clicked = pyqtSignal(int)

    def __init__(self, chapter: Chapter, status: ChapterStatus, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.chapter = chapter
        self.setObjectName("ChapterRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            #ChapterRow {{
                background: #141414;
                border-left: 4px solid transparent;
                border-bottom: 1px solid {LINE};
            }}
            #ChapterRow:hover {{
                background: {ACCENT_SOFT};
                border-left: 4px solid {ACCENT};
                border-bottom: 1px solid {ACCENT};
            }}
            #ChapterRow:hover #chapterRowTitle {{ color: {ACCENT}; }}
            #ChapterRow:hover #chapterRowNum {{ color: {ACCENT}; }}
            """
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(20)

        num = QLabel(f"{chapter.id:02d}", self)
        num.setObjectName("chapterRowNum")
        num.setStyleSheet(
            f"color: {INK}; background: transparent;"
            f" font-size: 16px; font-weight: 800; letter-spacing: -0.5px;"
        )
        num.setMinimumWidth(32)
        layout.addWidget(num, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(chapter.title, self)
        title.setObjectName("chapterRowTitle")
        title.setStyleSheet(
            f"color: {INK}; background: transparent; font-size: 14px; font-weight: 600;"
        )
        col.addWidget(title)
        if chapter.learning_goals:
            sub = QLabel(chapter.learning_goals[0], self)
            sub.setStyleSheet(
                f"color: {INK_3}; background: transparent; font-size: 12px;"
            )
            sub.setWordWrap(True)
            col.addWidget(sub)
        layout.addLayout(col, 1)

        if status == ChapterStatus.completed:
            status_text = "Completed"
            status_color = SUCCESS
        elif status == ChapterStatus.in_progress:
            status_text = "In Progress"
            status_color = ACCENT
        else:
            status_text = "—"
            status_color = INK_4
        st = QLabel(status_text, self)
        st.setStyleSheet(
            f"color: {status_color}; background: transparent;"
            f" font-size: 10px; font-weight: 800; letter-spacing: 0;"
        )
        layout.addWidget(st, 0, Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.chapter.id)
        super().mousePressEvent(e)


# ---------------------------------------------------------------------------
# Launcher screen
# ---------------------------------------------------------------------------


class LauncherScreen(QWidget):
    chapter_selected = pyqtSignal(int, int)
    test_requested = pyqtSignal(str)
    history_requested = pyqtSignal()

    def __init__(
        self,
        chapters: list[Chapter],
        repo: Repository,
        user_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chapters = chapters
        self.repo = repo
        self.user_id = user_id

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(TopBar(self))

        self._stack = QStackedLayout()
        body = QWidget(self)
        body.setLayout(self._stack)
        root.addWidget(body, 1)

        self._build_main_panel()
        self._build_chapter_picker_panel()
        self._stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    def _build_main_panel(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(40, 28, 40, 40)
        layout.setSpacing(0)

        # Hero band — large display kicker + title + subtitle, Linear/Vercel feel
        layout.addWidget(_Kicker("Dashboard"))
        layout.addSpacing(10)

        h = QLabel("Welcome back.", inner)
        h.setStyleSheet(
            f"color: {INK}; font-size: 44px; font-weight: 800; letter-spacing: -1.4px;"
            f" font-family: {FONT_SANS_DISPLAY};"
        )
        layout.addWidget(h)

        sub = QLabel("学習を再開する。続きから、または新しい章へ。", inner)
        sub.setStyleSheet(
            f"color: {INK_3}; font-size: 13px; font-weight: 500; letter-spacing: -0.1px;"
            f" padding-top: 4px;"
        )
        layout.addWidget(sub)

        # Bright red 2px rule pinned to the left
        rule_hero = QFrame(inner)
        rule_hero.setStyleSheet(f"background: {ACCENT};")
        rule_hero.setFixedHeight(2)
        rule_hero.setMaximumWidth(48)
        layout.addSpacing(16)
        layout.addWidget(rule_hero)
        layout.addSpacing(28)

        # Two-column band: continue card (left) + stats column (right)
        progress = self.repo.all_progress(self.user_id)
        completed = sum(1 for p in progress if p.status == ChapterStatus.completed)
        in_prog = sum(1 for p in progress if p.status == ChapterStatus.in_progress)
        latest = self.repo.latest_in_progress(self.user_id)
        latest_chapter = None
        latest_page = 0
        if latest is not None:
            latest_chapter = next((c for c in self.chapters if c.id == latest.chapter_id), None)
            latest_page = latest.last_page_index

        cols = QHBoxLayout()
        cols.setSpacing(28)

        cont = ContinueCard(latest_chapter, latest_page)
        cont.setMinimumHeight(170)
        cont.clicked.connect(self._on_resume)
        cols.addWidget(cont, 3)

        # HUD-style stats panel — no box border, just a black top rule like a
        # heads-up display. Each row is LABEL · BAR · VALUE.
        stats = QFrame(inner)
        stats.setStyleSheet("QFrame { background: transparent; border: none; }")
        s_layout = QVBoxLayout(stats)
        s_layout.setContentsMargins(0, 0, 0, 0)
        s_layout.setSpacing(0)

        # Header strip with kicker + 1px black rule
        head_row = QHBoxLayout()
        head_row.setContentsMargins(0, 0, 0, 0)
        head_kicker = QLabel("Status", stats)
        head_kicker.setStyleSheet(
            f"color: {ACCENT}; background: transparent;"
            f" font-size: 10px; font-weight: 800; letter-spacing: 0;"
        )
        head_row.addWidget(head_kicker)
        head_row.addStretch(1)
        sys_lbl = QLabel("System Online", stats)
        sys_lbl.setStyleSheet(
            f"color: {INK_3}; background: transparent;"
            f" font-size: 9px; font-weight: 700; letter-spacing: 0;"
        )
        head_row.addWidget(sys_lbl)
        s_layout.addLayout(head_row)
        s_layout.addSpacing(8)

        rule = QFrame(stats)
        rule.setStyleSheet(f"background: {INK};")
        rule.setFixedHeight(2)
        s_layout.addWidget(rule)
        s_layout.addSpacing(8)

        s_layout.addWidget(StatRow("Chapters",    len(self.chapters), len(self.chapters), color=INK))
        s_layout.addWidget(StatRow("Completed",   completed,           max(len(self.chapters), 1),
                                   color=SUCCESS if completed else INK_4))
        s_layout.addWidget(StatRow("In Progress", in_prog,             max(len(self.chapters), 1),
                                   color=ACCENT if in_prog else INK_4))
        s_layout.addStretch(1)
        cols.addWidget(stats, 2)

        layout.addLayout(cols)
        layout.addSpacing(32)

        # Action list
        layout.addWidget(_Kicker("Quick Actions"))
        layout.addSpacing(6)
        layout.addWidget(_Rule("rule-strong"))

        actions = [
            ("01", "章を選ぶ",   "Phase A 〜 F から好きな章を選んで学習する。", self._on_browse),
            ("02", "実力テスト", "PHASE ごとの 10 問テストで習熟度を確認する。", self._on_test),
            ("03", "テスト結果", "過去のスコアの履歴と推移を見る。",         self._on_history),
            ("04", "はじめから", "進捗をリセットして第 1 章から始める。",   self._on_start_over),
        ]
        for idx, title, desc, slot in actions:
            item = ActionRow(idx, title, desc)
            item.clicked.connect(slot)
            layout.addWidget(item)
        layout.addStretch(1)

        scroll.setWidget(inner)
        self._stack.addWidget(scroll)

    # ------------------------------------------------------------------
    def _build_chapter_picker_panel(self) -> None:
        outer = QWidget(self)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header = QFrame(outer)
        header.setFixedHeight(64)
        header.setStyleSheet(f"QFrame {{ background: {BG}; border-bottom: 1px solid {LINE}; }}")
        head_layout = QHBoxLayout(header)
        head_layout.setContentsMargins(48, 0, 48, 0)
        back = QPushButton("Back", header)
        back.setProperty("variant", "ghost")
        back.clicked.connect(lambda: self._stack.setCurrentIndex(0))
        head_layout.addWidget(back)

        sep = QFrame(header)
        sep.setStyleSheet(f"background: {LINE};")
        sep.setFixedSize(1, 24)
        head_layout.addWidget(sep)

        title = QLabel("Chapters", header)
        title.setStyleSheet(
            f"color: {INK}; font-size: 14px; font-weight: 800; letter-spacing: 0;"
        )
        head_layout.addWidget(title)
        head_layout.addStretch(1)

        outer_layout.addWidget(header)

        scroll = QScrollArea(outer)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self._picker_body = QVBoxLayout(body)
        self._picker_body.setContentsMargins(40, 32, 40, 48)
        self._picker_body.setSpacing(32)
        scroll.setWidget(body)
        outer_layout.addWidget(scroll, 1)

        self._stack.addWidget(outer)

    def refresh(self) -> None:
        while self._picker_body.count():
            it = self._picker_body.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                la = it.layout()
                if la is not None:
                    self._clear_layout(la)

        progress_by_chapter = {p.chapter_id: p for p in self.repo.all_progress(self.user_id)}
        phase_descriptions = {
            "A": "PYTHON 文法基礎",
            "B": "数値・データライブラリ",
            "C": "金融計算 (CMA 対応)",
            "D": "時系列・機械学習・深層学習",
            "E": "外部連携",
            "F": "アプリ開発・自動操作",
        }
        for phase, desc in phase_descriptions.items():
            chapters_in_phase = [c for c in self.chapters if c.phase == phase]
            if not chapters_in_phase:
                continue

            section = QVBoxLayout()
            section.setSpacing(0)

            head = QHBoxLayout()
            head.setSpacing(20)
            label = QLabel(PHASE_LABELS[phase], None)
            label.setStyleSheet(
                f"color: {ACCENT}; font-size: 11px; font-weight: 800; letter-spacing: 0;"
            )
            head.addWidget(label)
            sub = QLabel(desc, None)
            sub.setStyleSheet(f"color: {INK_3}; font-size: 12px; letter-spacing: 0;")
            head.addWidget(sub)
            head.addStretch(1)
            count = QLabel(f"{len(chapters_in_phase)} chapters", None)
            count.setStyleSheet(
                f"color: {INK_3}; font-size: 10px; font-weight: 700; letter-spacing: 0;"
                f" font-family: 'Cascadia Mono', 'Consolas', monospace;"
            )
            head.addWidget(count)
            section.addLayout(head)
            section.addSpacing(8)
            section.addWidget(_Rule("rule-strong"))

            for ch in chapters_in_phase:
                prog = progress_by_chapter.get(ch.id)
                status = prog.status if prog else ChapterStatus.not_started
                row = ChapterRow(ch, status)
                row.clicked.connect(self._on_chapter_card_clicked)
                section.addWidget(row)

            self._picker_body.addLayout(section)

        self._picker_body.addStretch(1)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
            else:
                child = it.layout()
                if child is not None:
                    self._clear_layout(child)

    # ------------------------------------------------------------------
    def _on_start_over(self) -> None:
        confirm = QMessageBox.question(
            self,
            "確認",
            "現在の進捗をリセットして第 1 章から始めますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.repo.reset_all(self.user_id)
        first = self.chapters[0] if self.chapters else None
        if first is not None:
            self.chapter_selected.emit(first.id, 0)

    def _on_resume(self) -> None:
        prog = self.repo.latest_in_progress(self.user_id)
        if prog is None:
            done = {p.chapter_id for p in self.repo.all_progress(self.user_id)
                    if p.status == ChapterStatus.completed}
            for ch in self.chapters:
                if ch.id not in done:
                    self.chapter_selected.emit(ch.id, 0)
                    return
            QMessageBox.information(self, "つづきから", "全章クリア済みです。")
            return
        self.chapter_selected.emit(prog.chapter_id, prog.last_page_index)

    def _on_browse(self) -> None:
        self.refresh()
        self._stack.setCurrentIndex(1)

    def _on_chapter_card_clicked(self, chapter_id: int) -> None:
        prog = self.repo.get_progress(self.user_id, chapter_id)
        start = prog.last_page_index if prog else 0
        self.chapter_selected.emit(chapter_id, start)

    def _on_test(self) -> None:
        self.test_requested.emit("phase_a_test")

    def _on_history(self) -> None:
        self.history_requested.emit()
