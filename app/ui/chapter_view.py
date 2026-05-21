"""Chapter view — sharp monochrome layout."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..content.loader import assemble_code
from ..content.schemas import Chapter, ExercisePage, ReadingPage, SamplePage
from ..db.models import ChapterStatus
from ..db.repo import Repository
from ..grading.judge import GradingResult, grade_exercise, grade_reading
from ..kernel.manager import KernelSession
from ..llm.claude_client import ClaudeClient
from ..resources.theme import (
    ACCENT,
    BG,
    INK,
    INK_3,
    INK_4,
    INK_5,
    LINE,
    LINE_STRONG,
    LINE_SUBTLE,
    PHASE_LABELS,
    SURFACE,
)
from .pages.exercise_page import ExercisePageWidget
from .pages.reading_page import ReadingPageWidget
from .pages.result_page import ResultPageWidget
from .pages.sample_page import SamplePageWidget
from .stickman import StickmanStrip
from .widgets.fade_stack import FadeStack
from .widgets.kbd import KbdCombo


def _phase_label(phase: str) -> str:
    """Return Title Case phase label (e.g. 'A' -> 'Phase A')."""
    return f"Phase {phase}"


class ChapterView(QWidget):
    back_to_launcher = pyqtSignal()

    def __init__(
        self,
        chapter: Chapter,
        repo: Repository,
        user_id: int,
        kernel: KernelSession,
        start_page_index: int = 0,
        llm: ClaudeClient | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.chapter = chapter
        self.repo = repo
        self.user_id = user_id
        self.kernel = kernel
        self.llm = llm

        # Single combined header row — left-aligned phase chevron breadcrumb,
        # right-aligned page dots / counter / close. Arc-style chevron sep.
        header = QFrame(self)
        header.setObjectName("chapterHeader")
        header.setFixedHeight(56)
        header.setStyleSheet(
            f"#chapterHeader {{ background: {BG}; border-bottom: 1px solid {LINE}; }}"
        )
        head_layout = QHBoxLayout(header)
        head_layout.setContentsMargins(28, 0, 18, 6)
        head_layout.setSpacing(10)

        # Tiny red dot indicating "live phase context"
        red_dot = QFrame(header)
        red_dot.setFixedSize(6, 6)
        red_dot.setStyleSheet(f"background: {ACCENT}; border: none;")
        head_layout.addWidget(red_dot, 0, Qt.AlignmentFlag.AlignVCenter)

        phase_lbl = QLabel(_phase_label(chapter.phase), header)
        phase_lbl.setStyleSheet(
            f"color: {INK_3}; font-size: 11px; font-weight: 700; letter-spacing: 0.2px;"
        )
        head_layout.addWidget(phase_lbl)

        # Chevron separator
        sep_b = QLabel("›", header)
        sep_b.setStyleSheet(f"color: {INK_5}; font-size: 14px; font-weight: 600;")
        head_layout.addWidget(sep_b)

        ch_num = QLabel(f"Ch {chapter.id:02d}", header)
        ch_num.setStyleSheet(
            f"color: {INK_3}; font-size: 11px; font-weight: 700; letter-spacing: 0.2px;"
        )
        head_layout.addWidget(ch_num)

        sep_c = QLabel("›", header)
        sep_c.setStyleSheet(f"color: {INK_5}; font-size: 14px; font-weight: 600;")
        head_layout.addWidget(sep_c)

        title_lbl = QLabel(chapter.title, header)
        title_lbl.setStyleSheet(
            f"color: {INK}; font-size: 14px; font-weight: 700; letter-spacing: -0.1px;"
        )
        head_layout.addWidget(title_lbl, 1)

        # Page progress dots (compact, ≤ 16 pages) — laid out into _dots_holder
        self._dots_holder = QFrame(header)
        self._dots_holder.setStyleSheet("background: transparent; border: none;")
        self._dots_layout = QHBoxLayout(self._dots_holder)
        self._dots_layout.setContentsMargins(0, 0, 0, 0)
        self._dots_layout.setSpacing(4)
        head_layout.addWidget(self._dots_holder, 0, Qt.AlignmentFlag.AlignVCenter)

        sep_d = QLabel("·", header)
        sep_d.setStyleSheet(f"color: {INK_5}; font-size: 12px; font-weight: 600;")
        head_layout.addWidget(sep_d, 0, Qt.AlignmentFlag.AlignVCenter)

        self._page_count_lbl = QLabel("", header)
        self._page_count_lbl.setStyleSheet(
            f"color: {INK_3}; font-size: 11px; font-weight: 700; letter-spacing: 0.3px;"
        )
        head_layout.addWidget(self._page_count_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        self._back_btn = QPushButton("閉じる", header)
        self._back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {INK_3};"
            f" border: 1px solid {LINE}; border-radius: 0;"
            f" padding: 5px 14px; font-size: 11px; font-weight: 700;"
            f" min-width: 0; min-height: 0; }}"
            f"QPushButton:hover {{ color: {INK}; border-color: {LINE_STRONG}; }}"
        )
        self._back_btn.clicked.connect(self.back_to_launcher.emit)
        head_layout.addWidget(self._back_btn)

        # Thin progress
        self._progress = QProgressBar(self)
        self._progress.setRange(0, len(chapter.pages))
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(2)

        # Body slot — flat BG with cross-fade between pages (Arc-style).
        self._slot_container = QWidget(self)
        self._slot_container.setStyleSheet(f"background: {BG};")
        self._slot_layout = FadeStack(self._slot_container)
        self._slot_layout.setContentsMargins(0, 0, 0, 0)

        # Footer
        self._footer = QFrame(self)
        self._footer.setStyleSheet(f"QFrame {{ background: {BG}; border-top: 1px solid {LINE}; }}")
        foot_layout = QHBoxLayout(self._footer)
        foot_layout.setContentsMargins(28, 10, 28, 10)
        foot_layout.setSpacing(8)
        _primary_qss = (
            "QPushButton {"
            f" background: {ACCENT}; color: white; border: 1px solid {ACCENT};"
            " border-radius: 0; padding: 8px 22px; font-size: 11px;"
            " font-weight: 700; min-width: 96px; min-height: 24px;"
            " }"
            "QPushButton:hover { background: #B91C1C; border-color: #B91C1C; }"
            "QPushButton:pressed { background: #991B1B; border-color: #991B1B; }"
            "QPushButton:disabled {"
            f" background: #141414; color: {LINE}; border-color: {LINE}; }}"
        )
        _secondary_qss = (
            "QPushButton {"
            f" background: #141414; color: {INK}; border: 1px solid {LINE_STRONG};"
            " border-radius: 0; padding: 8px 22px; font-size: 11px;"
            " font-weight: 700; min-width: 96px; min-height: 24px;"
            " }"
            f"QPushButton:hover {{ background: {INK}; color: #141414; border-color: {INK}; }}"
            "QPushButton:disabled {"
            f" background: #141414; color: {LINE}; border-color: {LINE}; }}"
        )
        self._prev_btn = QPushButton("戻る", self._footer)
        self._prev_btn.setStyleSheet(_secondary_qss)
        self._prev_btn.clicked.connect(self._go_prev)
        foot_layout.addWidget(self._prev_btn)
        prev_kbd = KbdCombo(["←"], self._footer, muted=True)
        foot_layout.addWidget(prev_kbd, 0, Qt.AlignmentFlag.AlignVCenter)
        foot_layout.addStretch(1)
        next_kbd = KbdCombo(["↵"], self._footer, muted=True)
        foot_layout.addWidget(next_kbd, 0, Qt.AlignmentFlag.AlignVCenter)
        self._next_btn = QPushButton("次へ", self._footer)
        self._next_btn.setStyleSheet(_primary_qss)
        self._next_btn.clicked.connect(self._on_next_clicked)
        foot_layout.addWidget(self._next_btn)

        # Inline stickman strip (above footer, never overlaps content)
        self._stickman = StickmanStrip(self)

        # Root
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(header)
        root.addWidget(self._progress)
        root.addWidget(self._slot_container, 1)
        root.addWidget(self._stickman)
        root.addWidget(self._footer)

        # Pre-build page widgets
        self._page_widgets: list[QWidget] = []
        for p in chapter.pages:
            if isinstance(p, SamplePage):
                w = SamplePageWidget(p)
                w.run_requested.connect(self._on_sample_run)
            elif isinstance(p, ExercisePage):
                w = ExercisePageWidget(p)
                w.submit_requested.connect(self._on_submit)
                w.show_solution_requested.connect(self._on_show_solution)
            elif isinstance(p, ReadingPage):
                w = ReadingPageWidget(p)
                w.submit_requested.connect(self._on_reading_submit)
            else:
                w = QLabel(f"unknown page kind: {type(p).__name__}")
            self._page_widgets.append(w)

        # Inline stickman strip (created above; reference for set_mood/set_speech)
        # NB: actually instantiated below via _create_stickman_strip and inserted
        # into the root layout above the footer.

        self._current_index = max(0, min(start_page_index, len(chapter.pages) - 1))
        self._result_overlay: ResultPageWidget | None = None
        self._show_current_page()
        self._save_progress()

    # ------------------------------------------------------------------
    def _swap_slot(self, widget: QWidget) -> None:
        # Keep previously-added widgets resident so we can fade between
        # them — adding the same widget twice is a no-op in QStackedLayout.
        if self._slot_layout.indexOf(widget) == -1:
            self._slot_layout.addWidget(widget)
        self._slot_layout.setCurrentWidget(widget)

    def _current_page_model(self):
        return self.chapter.pages[self._current_index]

    def _show_current_page(self) -> None:
        if self._result_overlay is not None:
            self._result_overlay.deleteLater()
            self._result_overlay = None
        widget = self._page_widgets[self._current_index]
        self._swap_slot(widget)
        # Restore the footer (it gets hidden while a result overlay is showing).
        self._footer.setVisible(True)
        self._progress.setValue(self._current_index + 1)
        self._page_count_lbl.setText(
            f"{self._current_index + 1:02d} / {len(self.chapter.pages):02d}"
        )
        self._refresh_page_dots()

        page = self._current_page_model()
        if isinstance(page, SamplePage):
            self._stickman.set_mood(page.stickman)
            self._stickman.set_speech(page.stickman_speech)
            self._next_btn.setText("次へ")
            self._next_btn.setEnabled(True)
        elif isinstance(page, ExercisePage):
            self._stickman.set_mood("explain")
            self._stickman.set_speech("コードの空欄を埋めて提出ボタンを押そう。")
            self._next_btn.setText("提出")
            self._next_btn.setEnabled(True)
        elif isinstance(page, ReadingPage):
            self._stickman.set_mood(page.stickman)
            self._stickman.set_speech(page.stickman_speech)
            self._next_btn.setText("提出")
            self._next_btn.setEnabled(True)
        self._prev_btn.setEnabled(self._current_index > 0)

    def _refresh_page_dots(self) -> None:
        # Clear existing dots
        while self._dots_layout.count():
            it = self._dots_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        total = len(self.chapter.pages)
        # Render dots only when page count is small (≤ 16); otherwise we'd
        # get a cramped row. The "n / m" counter to the right keeps context.
        if total > 16:
            return
        for i in range(total):
            dot = QFrame(self._dots_holder)
            dot.setFixedSize(5, 5)
            if i < self._current_index:
                color = ACCENT
            elif i == self._current_index:
                color = ACCENT
            else:
                color = LINE_STRONG
            dot.setStyleSheet(f"background: {color}; border: none;")
            self._dots_layout.addWidget(dot)

    def _save_progress(self, *, completed: bool = False) -> None:
        self.repo.upsert_progress(
            user_id=self.user_id,
            chapter_id=self.chapter.id,
            last_page_index=self._current_index,
            status=ChapterStatus.completed if completed else ChapterStatus.in_progress,
        )

    # ------------------------------------------------------------------
    def _on_sample_run(self) -> None:
        widget = self._page_widgets[self._current_index]
        if not isinstance(widget, SamplePageWidget):
            return
        result = self.kernel.execute(widget.code, timeout=15)
        widget.output_pane.render(result)
        if result.status == "ok":
            self._stickman.set_mood("happy")
            self._stickman.set_speech("実行できたね。次へ進もう。")
        else:
            self._stickman.set_mood("sad")
            self._stickman.set_speech("エラーが出たみたい。出力を確認しよう。")

    # ------------------------------------------------------------------
    def _on_submit(self) -> None:
        idx = self._current_index
        widget = self._page_widgets[idx]
        if not isinstance(widget, ExercisePageWidget):
            return
        page = widget.page
        values = widget.collect_values()

        gr = grade_exercise(page, values, self.kernel)
        # Defense against intermittent kernel cold-start: if the answer
        # looks form-correct but the kernel reported a non-ok status, the
        # most likely cause is a stale state / first-execution glitch.
        # Retry once with a fresh kernel before declaring "Incorrect".
        if (
            not gr.overall_passed
            and gr.form_passed
            and gr.execution is not None
            and gr.execution.status != "ok"
        ):
            self.kernel.restart()
            gr = grade_exercise(page, values, self.kernel)
        self.repo.record_submission(
            user_id=self.user_id,
            chapter_id=self.chapter.id,
            page_index=idx,
            code=gr.assembled_code,
            passed=gr.overall_passed,
            stdout=gr.execution.stdout if gr.execution else "",
            stderr=gr.execution.stderr if gr.execution else "",
            hint_level_shown=0,
        )

        widget.mark_results(gr.failed_blanks)
        if not gr.overall_passed:
            attempts = widget.register_wrong_attempt()
            stickman_wrong = self._pick_wrong_speech(page, attempts)
            self._stickman.set_mood("sad")
            self._stickman.set_speech(stickman_wrong)
        else:
            self._stickman.set_mood("happy")
            self._stickman.set_speech(page.stickman_feedback.correct)
            stickman_wrong = page.stickman_feedback.wrong_hint1

        self._show_result_overlay(gr, page, stickman_wrong)

    def _show_result_overlay(
        self, gr: GradingResult, page: ExercisePage, stickman_wrong: str
    ) -> None:
        self._result_overlay = ResultPageWidget(
            gr,
            stickman_speech_correct=page.stickman_feedback.correct,
            stickman_speech_wrong=stickman_wrong,
            chapter=self.chapter,
            page=page,
            llm=self.llm,
        )
        self._result_overlay.next_requested.connect(self._advance)
        self._result_overlay.retry_requested.connect(self._retry_current)
        self._swap_slot(self._result_overlay)
        # The result page provides its own Next / Retry buttons — hide the
        # chapter-level footer so the user isn't confused by two CTAs.
        self._footer.setVisible(False)

    def _pick_wrong_speech(self, page: ExercisePage, attempts: int) -> str:
        fb = page.stickman_feedback
        if attempts >= 3:
            return fb.wrong_hint3
        if attempts == 2:
            return fb.wrong_hint2
        return fb.wrong_hint1

    def _retry_current(self) -> None:
        widget = self._page_widgets[self._current_index]
        if isinstance(widget, ExercisePageWidget):
            widget.reset_for_retry()
        elif isinstance(widget, ReadingPageWidget):
            widget.reset_for_retry()
        self._show_current_page()
        self._stickman.set_mood("explain")
        self._stickman.set_speech("もう一度トライ。")

    def _on_show_solution(self) -> None:
        page = self._current_page_model()
        if not isinstance(page, ExercisePage):
            return
        canonical = {b.id: b.canonical_answer for b in page.blanks}
        full = assemble_code(page.code_template, canonical)
        QMessageBox.information(self, "模範解答", full)

    # ------------------------------------------------------------------
    def _on_next_clicked(self) -> None:
        page = self._current_page_model()
        if isinstance(page, ExercisePage):
            # Footer "SUBMIT" delegates to the exercise page submit handler.
            self._on_submit()
            return
        if isinstance(page, ReadingPage):
            self._on_reading_submit()
            return
        self._advance()

    # ------------------------------------------------------------------
    def _on_reading_submit(self) -> None:
        idx = self._current_index
        widget = self._page_widgets[idx]
        if not isinstance(widget, ReadingPageWidget):
            return
        page = widget.page
        selected = widget.selected_index()
        if selected is None:
            widget.show_unanswered_notice()
            return

        gr = grade_reading(page, selected)
        self.repo.record_submission(
            user_id=self.user_id,
            chapter_id=self.chapter.id,
            page_index=idx,
            code=f"reading: selected={selected}",
            passed=gr.overall_passed,
            stdout="",
            stderr="",
            hint_level_shown=0,
        )

        if gr.overall_passed:
            self._stickman.set_mood("happy")
            self._stickman.set_speech(page.stickman_feedback.correct)
            stickman_wrong = page.stickman_feedback.wrong_hint1
        else:
            self._stickman.set_mood("sad")
            stickman_wrong = page.stickman_feedback.wrong_hint1
            self._stickman.set_speech(stickman_wrong)

        # Reuse the exercise result overlay. ResultPageWidget tolerates a
        # ``page=None`` chapter context (it only uses page for the Ask AI
        # button, which we disable for reading by passing llm=None below).
        self._result_overlay = ResultPageWidget(
            gr,
            stickman_speech_correct=page.stickman_feedback.correct,
            stickman_speech_wrong=stickman_wrong,
            chapter=self.chapter,
            page=None,
            llm=None,
        )
        self._result_overlay.next_requested.connect(self._advance)
        self._result_overlay.retry_requested.connect(self._retry_current)
        self._swap_slot(self._result_overlay)
        self._footer.setVisible(False)

    def _go_prev(self) -> None:
        if self._current_index <= 0:
            return
        self._current_index -= 1
        self._show_current_page()
        self._save_progress()

    def _advance(self) -> None:
        if self._current_index + 1 >= len(self.chapter.pages):
            self._save_progress(completed=True)
            QMessageBox.information(
                self,
                "章クリア",
                f"第 {self.chapter.id:02d} 章「{self.chapter.title}」をクリアしました。",
            )
            self.back_to_launcher.emit()
            return
        self._current_index += 1
        self._show_current_page()
        self._save_progress()
