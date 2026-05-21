"""Web-based application shell.

A `QWebEngineView` hosts `app/web/index.html` (a single-page app) and a
`Bridge` QObject is exposed over `QWebChannel` so JavaScript can request
chapter data, submit code, and receive kernel state updates.

This is the modern shell that replaces the QSS-styled PyQt6 widgets. The
old shell still works (selected via env var / CLI), so the migration is
non-destructive.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from ..content.loader import assemble_code
from ..content.schemas import (
    Chapter,
    ExercisePage,
    ReadingPage,
    SamplePage,
)
from ..db.models import ChapterStatus
from ..db.repo import Repository
from ..grading.judge import grade_exercise, grade_reading
from ..kernel.manager import KernelSession


# Path to bundled web assets (HTML / CSS / JS).
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# ---------------------------------------------------------------------------
# Bridge — exposed to JavaScript over QWebChannel
# ---------------------------------------------------------------------------


class Bridge(QObject):
    """Exposes a small JSON-shaped API to the web layer.

    On the JS side the object is reached via:

        new QWebChannel(qt.webChannelTransport, (ch) => {
            const b = ch.objects.bridge;
            b.bootstrapJson((json) => { ... });
        });
    """

    kernelState = pyqtSignal(str)
    chapterUpdated = pyqtSignal(int)        # chapter id

    def __init__(
        self,
        chapters: list[Chapter],
        repo: Repository,
        user_id: int,
        kernel: KernelSession,
        test_sets: dict,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._chapters = chapters
        self._repo = repo
        self._user_id = user_id
        self._kernel = kernel
        self._test_sets = test_sets

    # ----- Initial data ------------------------------------------------
    @pyqtSlot(result=str)
    def bootstrapJson(self) -> str:  # noqa: N802
        chapters = []
        for ch in self._chapters:
            chapters.append({
                "id": ch.id,
                "phase": ch.phase,
                "title": ch.title,
                "desc": ch.learning_goals[0] if ch.learning_goals else "",
                "pages": len(ch.pages),
            })

        progress = {}
        for p in self._repo.all_progress(self._user_id):
            progress[p.chapter_id] = {
                "status": "done" if p.status == ChapterStatus.completed
                           else "in_progress",
                "lastPageIndex": p.last_page_index,
            }

        test_sets = []
        for ts in self._test_sets.values():
            test_sets.append({
                "id": ts.id,
                "title": ts.title,
                "phase": ts.phase,
                "questions": len(ts.questions),
                "minutes": ts.time_limit_minutes,
            })

        test_results = []
        try:
            for r in self._repo.list_test_results(self._user_id):
                # Map test_id -> human title from loaded sets if available
                ts = self._test_sets.get(r.test_id)
                test_results.append({
                    "date": r.finished_at.strftime("%Y-%m-%d") if r.finished_at else "",
                    "test_id": r.test_id,
                    "title": ts.title if ts else r.test_id,
                    "score": int(r.score / max(r.total, 1) * 100),
                    "pass": (r.score / max(r.total, 1)) >= 0.6,
                    "duration_sec": r.duration_sec,
                })
        except Exception:  # noqa: BLE001
            logging.exception("test results bootstrap failed")

        data = {
            "chapters": chapters,
            "progress": progress,
            "testSets": test_sets,
            "testResults": test_results,
        }
        return json.dumps(data, ensure_ascii=False)

    # ----- Code execution ---------------------------------------------
    @pyqtSlot(str, result=str)
    def runCode(self, code: str) -> str:  # noqa: N802
        import re
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        try:
            res = self._kernel.execute(code, timeout=15)
            # Compose a human-readable error body when execution failed —
            # the kernel exposes ename/evalue/traceback but stderr is often
            # empty, so we synthesize a message here.
            body = res.stderr or ""
            if res.status != "ok":
                parts: list[str] = []
                head = f"{res.error_name}: {res.error_value}".strip(": ").strip()
                if head:
                    parts.append(head)
                if res.traceback:
                    parts.extend(ansi_re.sub("", t) for t in res.traceback)
                if parts:
                    detail = "\n".join(parts).strip()
                    body = (body + "\n\n" + detail).strip() if body else detail
                if not body:
                    body = f"{res.status}: 詳細不明"
            return json.dumps({
                "status": res.status,
                "stdout": res.stdout or "",
                "stderr": body,
                "error_name":  res.error_name,
                "error_value": res.error_value,
            }, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps({"status": "error", "stdout": "", "stderr": str(e)})

    # ----- Chapter detail ---------------------------------------------
    @pyqtSlot(int, result=str)
    def chapterDetailJson(self, chapter_id: int) -> str:  # noqa: N802
        """Return JSON describing every page of `chapter_id`."""
        ch = next((c for c in self._chapters if c.id == chapter_id), None)
        if ch is None:
            return json.dumps({"error": f"chapter {chapter_id} not found"})
        pages = []
        for idx, p in enumerate(ch.pages):
            if isinstance(p, SamplePage):
                pages.append({
                    "kind": "sample",
                    "title": p.title,
                    "markdown": p.markdown,
                    "sample_code": p.sample_code,
                    "runnable": p.runnable,
                    "runner": p.runner,
                    "expected_output": p.expected_output,
                    "stickman": p.stickman,
                    "stickman_speech": p.stickman_speech,
                })
            elif isinstance(p, ExercisePage):
                pages.append({
                    "kind": "exercise",
                    "title": p.title,
                    "prompt": p.prompt,
                    "code_template": p.code_template,
                    "blanks": [
                        {
                            "id": b.id,
                            "placeholder": b.placeholder,
                            "width": b.width,
                            "canonical_answer": b.canonical_answer,
                            "hint": b.hint,
                        } for b in p.blanks
                    ],
                    "hints": p.hints,
                    "feedback": {
                        "correct": p.stickman_feedback.correct,
                        "wrong_hint1": p.stickman_feedback.wrong_hint1,
                        "wrong_hint2": p.stickman_feedback.wrong_hint2,
                        "wrong_hint3": p.stickman_feedback.wrong_hint3,
                    },
                })
            elif isinstance(p, ReadingPage):
                pages.append({
                    "kind": "reading",
                    "title": p.title,
                    "prompt": p.prompt,
                    "code": p.code,
                    "code_file_label": p.code_file_label,
                    "choices": list(p.choices),
                    "explanation": p.explanation,
                    "stickman": p.stickman,
                    "stickman_speech": p.stickman_speech,
                })
            else:
                pages.append({"kind": "unknown"})
        return json.dumps({
            "id": ch.id,
            "phase": ch.phase,
            "title": ch.title,
            "learning_goals": list(ch.learning_goals),
            "pages": pages,
        }, ensure_ascii=False)

    # ----- Grading ----------------------------------------------------
    @pyqtSlot(int, int, str, result=str)
    def gradeExercise(self, chapter_id: int, page_index: int, answers_json: str) -> str:  # noqa: N802
        ch = next((c for c in self._chapters if c.id == chapter_id), None)
        if ch is None or page_index >= len(ch.pages):
            return json.dumps({"ok": False, "error": "chapter / page not found"})
        page = ch.pages[page_index]
        if not isinstance(page, ExercisePage):
            return json.dumps({"ok": False, "error": "not an exercise page"})
        try:
            answers = json.loads(answers_json or "{}")
        except Exception:  # noqa: BLE001
            answers = {}
        try:
            gr = grade_exercise(page, answers, self._kernel)
            return json.dumps({
                "ok": True,
                "passed": gr.overall_passed,
                "form_passed": gr.form_passed,
                "failed_blanks": list(gr.failed_blanks),
                "assembled_code": gr.assembled_code,
                "stdout": gr.execution.stdout if gr.execution else "",
                "stderr": gr.execution.stderr if gr.execution else "",
                "feedback": {
                    "correct": page.stickman_feedback.correct,
                    "wrong_hint1": page.stickman_feedback.wrong_hint1,
                },
            }, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logging.exception("gradeExercise failed")
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(int, int, int, result=str)
    def gradeReading(self, chapter_id: int, page_index: int, selected: int) -> str:  # noqa: N802
        ch = next((c for c in self._chapters if c.id == chapter_id), None)
        if ch is None or page_index >= len(ch.pages):
            return json.dumps({"ok": False, "error": "chapter / page not found"})
        page = ch.pages[page_index]
        if not isinstance(page, ReadingPage):
            return json.dumps({"ok": False, "error": "not a reading page"})
        try:
            gr = grade_reading(page, selected)
            return json.dumps({
                "ok": True,
                "passed": gr.overall_passed,
                "correct_index": page.correct_index,
                "explanation": page.explanation,
            }, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logging.exception("gradeReading failed")
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(str, result=str)
    def assembleCode(self, payload_json: str) -> str:  # noqa: N802
        """Given {chapter_id, page_index, answers}, return assembled code."""
        try:
            data = json.loads(payload_json)
            cid = int(data["chapter_id"])
            pidx = int(data["page_index"])
            answers = data.get("answers", {}) or {}
            ch = next((c for c in self._chapters if c.id == cid), None)
            if ch is None:
                return json.dumps({"ok": False, "error": "chapter not found"})
            page = ch.pages[pidx]
            if not isinstance(page, ExercisePage):
                return json.dumps({"ok": False, "error": "not an exercise"})
            code = assemble_code(page.code_template, answers)
            return json.dumps({"ok": True, "code": code})
        except Exception as e:  # noqa: BLE001
            return json.dumps({"ok": False, "error": str(e)})

    # ----- Data management --------------------------------------------
    @pyqtSlot(result=str)
    def clearLearningData(self) -> str:  # noqa: N802
        """Wipe all chapter progress / submissions / test results for the active user."""
        try:
            counts = self._repo.clear_user_data(self._user_id)
            return json.dumps({"ok": True, "removed": counts}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logging.exception("clearLearningData failed")
            return json.dumps({"ok": False, "error": str(e)})

    # ----- Practice problems (cross-chapter reading quizzes) -----------
    @pyqtSlot(result=str)
    def practiceProblemsJson(self) -> str:  # noqa: N802
        """Return every ReadingPage across all chapters, grouped-ready for the practice view."""
        items = []
        for ch in self._chapters:
            for idx, p in enumerate(ch.pages):
                if isinstance(p, ReadingPage):
                    items.append({
                        "chapterId": ch.id,
                        "phase": ch.phase,
                        "chapterTitle": ch.title,
                        "pageIndex": idx,
                        "title": p.title,
                        "prompt": p.prompt,
                        "code": p.code,
                        "codeFileLabel": p.code_file_label,
                        "choices": list(p.choices),
                    })
        return json.dumps({"problems": items}, ensure_ascii=False)

    # ----- Test set detail / submission -------------------------------
    @pyqtSlot(str, result=str)
    def testSetDetailJson(self, test_id: str) -> str:  # noqa: N802
        ts = self._test_sets.get(test_id)
        if ts is None:
            return json.dumps({"error": f"test set {test_id} not found"})
        questions = []
        for q in ts.questions:
            questions.append({
                "title": q.title,
                "prompt": q.prompt,
                "code_template": q.code_template,
                "blanks": [
                    {
                        "id": b.id,
                        "placeholder": b.placeholder,
                        "canonical_answer": b.canonical_answer,
                        "hint": b.hint,
                    } for b in q.blanks
                ],
            })
        return json.dumps({
            "id": ts.id,
            "title": ts.title,
            "description": ts.description,
            "phase": ts.phase,
            "time_limit_minutes": ts.time_limit_minutes,
            "pass_score": ts.pass_score,
            "questions": questions,
        }, ensure_ascii=False)

    @pyqtSlot(str, int, str, result=str)
    def gradeTestQuestion(self, test_id: str, q_index: int, answers_json: str) -> str:  # noqa: N802
        ts = self._test_sets.get(test_id)
        if ts is None or q_index >= len(ts.questions):
            return json.dumps({"ok": False, "error": "test / question not found"})
        try:
            answers = json.loads(answers_json or "{}")
        except Exception:  # noqa: BLE001
            answers = {}
        try:
            gr = grade_exercise(ts.questions[q_index], answers, self._kernel)
            return json.dumps({
                "ok": True,
                "passed": gr.overall_passed,
                "form_passed": gr.form_passed,
                "failed_blanks": list(gr.failed_blanks),
                "stdout": gr.execution.stdout if gr.execution else "",
                "stderr": gr.execution.stderr if gr.execution else "",
            }, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            logging.exception("gradeTestQuestion failed")
            return json.dumps({"ok": False, "error": str(e)})

    @pyqtSlot(str, result=str)
    def recordTestResult(self, payload_json: str) -> str:  # noqa: N802
        """payload: {test_id, score, total, seconds, perQuestion: [{passed:bool, skipped:bool}]}"""
        try:
            data = json.loads(payload_json)
            now = datetime.now(timezone.utc)
            started = data.get("started_at")
            try:
                started_at = datetime.fromisoformat(started) if started else now
            except Exception:  # noqa: BLE001
                started_at = now
            self._repo.record_test_result(
                user_id=self._user_id,
                test_id=str(data["test_id"]),
                score=int(data["score"]),
                total=int(data["total"]),
                duration_sec=int(data.get("seconds", 0)),
                per_question_json=json.dumps(data.get("perQuestion", []), ensure_ascii=False),
                started_at=started_at,
                finished_at=now,
            )
            return json.dumps({"ok": True})
        except Exception as e:  # noqa: BLE001
            logging.exception("recordTestResult failed")
            return json.dumps({"ok": False, "error": str(e)})

    # ----- Progress mutation ------------------------------------------
    @pyqtSlot(int, int, bool)
    def saveProgress(self, chapter_id: int, page_index: int, completed: bool) -> None:  # noqa: N802
        try:
            status = ChapterStatus.completed if completed else ChapterStatus.in_progress
            self._repo.upsert_progress(
                user_id=self._user_id,
                chapter_id=chapter_id,
                last_page_index=page_index,
                status=status,
            )
            self.chapterUpdated.emit(chapter_id)
        except Exception:  # noqa: BLE001
            logging.exception("saveProgress failed")


# ---------------------------------------------------------------------------
# WebShell — replaces AppShell when the web mode is on
# ---------------------------------------------------------------------------


class WebShell(QWidget):
    """QWidget container that mounts a `QWebEngineView` filling its surface."""

    def __init__(
        self,
        chapters: list[Chapter],
        repo: Repository,
        user_id: int,
        kernel: KernelSession,
        test_sets: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.bridge = Bridge(chapters, repo, user_id, kernel, test_sets, self)
        self.channel = QWebChannel(self)
        self.channel.registerObject("bridge", self.bridge)

        self.view = QWebEngineView(self)
        self.view.page().setWebChannel(self.channel)

        index_path = WEB_DIR / "index.html"
        if not index_path.exists():
            logging.error("web assets not found at %s", WEB_DIR)
        self.view.load(QUrl.fromLocalFile(str(index_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view)

    def notify_kernel_state(self, state: str) -> None:
        self.bridge.kernelState.emit(state)
