"""HTTP server hosting the Study.Py web UI.

This module replaces the previous PyQt6 / QWebEngineView shell. The UI is a
single-page web app (``app/web/``) and the Python side exposes a thin JSON
API on top of FastAPI/uvicorn. The browser handles all rendering, so the
application no longer depends on Qt or any native UI toolkit.

API surface (kept intentionally close to the old ``Bridge`` slots so the JS
client only needed a small shim, not a rewrite):

    GET  /                          → index.html
    GET  /static/*                  → app/web/*  (css / js / vendor)
    GET  /resources/*               → app/resources/* (stickman art, fonts)
    GET  /api/bootstrap             → chapters + progress + tests
    GET  /api/chapter/{id}          → chapter detail
    GET  /api/tests/{id}            → test set detail
    GET  /api/practice              → cross-chapter reading problems
    POST /api/run-code              → execute python in the shared kernel
    POST /api/grade/exercise        → grade an Exercise page
    POST /api/grade/reading         → grade a Reading page
    POST /api/assemble-code         → assemble code from blanks
    POST /api/tests/{id}/grade      → grade a test question
    POST /api/tests/record-result   → persist a finished test
    POST /api/progress              → save chapter / page progress
    POST /api/clear-learning-data   → wipe all progress for the active user
    GET  /api/export-progress       → download progress.json as attachment
    POST /api/kernel/restart        → restart the IPython kernel
    GET  /api/events                → SSE feed (kernel state, etc.)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .content.loader import assemble_code
from .content.schemas import (
    Chapter,
    ExercisePage,
    ReadingPage,
    SamplePage,
)
from .db.models import ChapterStatus
from .db.repo import Repository
from .grading.judge import grade_exercise, grade_reading
from .kernel.manager import KernelSession

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


# Hard cap on submitted code size. 256 KiB is more than enough for any
# legitimate exercise / sample, and tight enough to keep a runaway client
# (or a `--insecure-lan` attacker) from streaming gigabytes into the
# Jupyter kernel's ZMQ pipe.
MAX_CODE_BYTES = 256 * 1024


class RunCodeRequest(BaseModel):
    code: str = Field(max_length=MAX_CODE_BYTES)


class GradeExerciseRequest(BaseModel):
    chapter_id: int
    page_index: int
    answers: dict[str, Any] = Field(default_factory=dict)


class GradeReadingRequest(BaseModel):
    chapter_id: int
    page_index: int
    selected: int


class AssembleCodeRequest(BaseModel):
    chapter_id: int
    page_index: int
    answers: dict[str, Any] = Field(default_factory=dict)


class GradeTestRequest(BaseModel):
    q_index: int
    answers: dict[str, Any] = Field(default_factory=dict)


class RecordTestResultRequest(BaseModel):
    test_id: str
    score: int
    total: int
    seconds: int = 0
    # noqa: N815 — wire-compat with the JS client
    perQuestion: list[dict[str, Any]] = Field(default_factory=list)  # noqa: N815
    started_at: str | None = None


class SaveProgressRequest(BaseModel):
    chapter_id: int
    page_index: int
    completed: bool


# ---------------------------------------------------------------------------
# Event bus (kernel state push to clients)
# ---------------------------------------------------------------------------


class EventBus:
    """Tiny pub/sub used by /api/events to stream kernel state to the UI.

    Publishing is thread-safe: `publish()` can be called from any worker
    thread (e.g. the kernel-bootstrap thread in app/main.py) and the
    message is scheduled onto the captured uvicorn loop via
    `call_soon_threadsafe`.

    The loop reference is captured by `attach_loop()`, which the FastAPI
    startup hook calls once the asyncio loop is actually running. Before
    that, `publish()` records `_last_state` so new subscribers still see
    the most recent value when they connect.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()
        self._last_state: dict[str, Any] = {"type": "kernel_state", "state": "starting"}
        self._loop: asyncio.AbstractEventLoop | None = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=16)
        async with self._lock:
            self._subscribers.add(q)
        await q.put(json.dumps(self._last_state))
        return q

    async def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    def publish(self, payload: dict[str, Any]) -> None:
        """Sync publish — safe to call from any thread."""
        msg = json.dumps(payload)
        if payload.get("type") == "kernel_state":
            self._last_state = payload
        # Use the loop captured at FastAPI startup, NOT
        # `asyncio.get_event_loop()` (which is deprecated when called from a
        # thread with no running loop and raises in 3.14+). If no loop is
        # captured yet (publish racing startup), drop the live push — every
        # new subscriber still gets `_last_state` on connect.
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        for q in list(self._subscribers):
            loop.call_soon_threadsafe(self._safe_put_nowait, q, msg)

    @staticmethod
    def _safe_put_nowait(q: asyncio.Queue[str], msg: str) -> None:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            # Drop the message rather than blocking — the UI will recover
            # on the next state change.
            pass


# ---------------------------------------------------------------------------
# Server context (dependency-injected into FastAPI handlers)
# ---------------------------------------------------------------------------


class ServerContext:
    def __init__(
        self,
        chapters: list[Chapter],
        repo: Repository,
        user_id: int,
        kernel: KernelSession,
        test_sets: dict[str, Any],
    ) -> None:
        self.chapters = chapters
        self.repo = repo
        self.user_id = user_id
        self.kernel = kernel
        self.test_sets = test_sets
        self.events = EventBus()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(ctx: ServerContext) -> FastAPI:
    app = FastAPI(
        title="Study.Py — Finance",
        version="0.6.0",
        docs_url=None,  # hide /docs from the loopback UI
        redoc_url=None,
        openapi_url=None,
    )

    # Capture the running asyncio loop once uvicorn has started it, so the
    # event bus can schedule pushes from worker threads without falling
    # back to the deprecated asyncio.get_event_loop().
    @app.on_event("startup")
    async def _attach_loop() -> None:  # noqa: D401
        ctx.events.attach_loop(asyncio.get_running_loop())

    # Static assets ---------------------------------------------------------
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")
    app.mount(
        "/resources",
        StaticFiles(directory=str(RESOURCES_DIR)),
        name="resources",
    )

    # Root → index.html ----------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    async def root() -> HTMLResponse:  # noqa: D401
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    # Favicon (best-effort) ------------------------------------------------
    @app.get("/favicon.ico", response_model=None)
    async def favicon():
        ico = WEB_DIR / "favicon.ico"
        if ico.exists():
            return FileResponse(str(ico))
        return JSONResponse({}, status_code=204)

    # ------------------------------------------------------------------
    # API: bootstrap (initial state)
    # ------------------------------------------------------------------
    @app.get("/api/bootstrap")
    async def bootstrap() -> JSONResponse:
        chapters = [
            {
                "id": ch.id,
                "phase": ch.phase,
                "title": ch.title,
                "desc": ch.learning_goals[0] if ch.learning_goals else "",
                "pages": len(ch.pages),
            }
            for ch in ctx.chapters
        ]
        progress: dict[int, dict[str, Any]] = {}
        for p in ctx.repo.all_progress(ctx.user_id):
            progress[p.chapter_id] = {
                "status": "done" if p.status == ChapterStatus.completed else "in_progress",
                "lastPageIndex": p.last_page_index,
            }
        test_sets = [
            {
                "id": ts.id,
                "title": ts.title,
                "phase": ts.phase,
                "questions": len(ts.questions),
                "minutes": ts.time_limit_minutes,
            }
            for ts in ctx.test_sets.values()
        ]
        test_results: list[dict[str, Any]] = []
        try:
            for r in ctx.repo.list_test_results(ctx.user_id):
                # Skip rows with total=0 so a corrupt / hand-edited record
                # doesn't render as "700% PASS" in the history view.
                if r.total <= 0:
                    continue
                ts = ctx.test_sets.get(r.test_id)
                # Emit both the pre-formatted UTC date (for compatibility
                # with consumers that just need a string) and the raw ISO
                # timestamp so the JS sparkline can bucket in the user's
                # LOCAL timezone instead of UTC — otherwise a test finished
                # at 08:30 JST lands in yesterday's bucket on the chart.
                fin = r.finished_at
                test_results.append(
                    {
                        "date": fin.strftime("%Y-%m-%d") if fin else "",
                        "finished_at": (fin.replace(tzinfo=UTC).isoformat() if fin else None),
                        "test_id": r.test_id,
                        "title": ts.title if ts else r.test_id,
                        "score": int(r.score / r.total * 100),
                        "pass": (r.score / r.total) >= 0.6,
                        "duration_sec": r.duration_sec,
                    }
                )
        except Exception:
            log.exception("test_results bootstrap failed")

        return JSONResponse(
            {
                "chapters": chapters,
                "progress": progress,
                "testSets": test_sets,
                "testResults": test_results,
            }
        )

    # ------------------------------------------------------------------
    # API: chapter detail
    # ------------------------------------------------------------------
    @app.get("/api/chapter/{chapter_id}")
    async def chapter_detail(chapter_id: int) -> JSONResponse:
        ch = next((c for c in ctx.chapters if c.id == chapter_id), None)
        if ch is None:
            raise HTTPException(status_code=404, detail=f"chapter {chapter_id} not found")
        pages: list[dict[str, Any]] = []
        for p in ch.pages:
            if isinstance(p, SamplePage):
                pages.append(
                    {
                        "kind": "sample",
                        "title": p.title,
                        "markdown": p.markdown,
                        "sample_code": p.sample_code,
                        "runnable": p.runnable,
                        "runner": p.runner,
                        "expected_output": p.expected_output,
                        "stickman": p.stickman,
                        "stickman_speech": p.stickman_speech,
                    }
                )
            elif isinstance(p, ExercisePage):
                pages.append(
                    {
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
                            }
                            for b in p.blanks
                        ],
                        "hints": p.hints,
                        "feedback": {
                            "correct": p.stickman_feedback.correct,
                            "wrong_hint1": p.stickman_feedback.wrong_hint1,
                            "wrong_hint2": p.stickman_feedback.wrong_hint2,
                            "wrong_hint3": p.stickman_feedback.wrong_hint3,
                        },
                    }
                )
            elif isinstance(p, ReadingPage):
                pages.append(
                    {
                        "kind": "reading",
                        "title": p.title,
                        "prompt": p.prompt,
                        "code": p.code,
                        "code_file_label": p.code_file_label,
                        "choices": list(p.choices),
                        "explanation": p.explanation,
                        "stickman": p.stickman,
                        "stickman_speech": p.stickman_speech,
                    }
                )
            else:
                pages.append({"kind": "unknown"})
        return JSONResponse(
            {
                "id": ch.id,
                "phase": ch.phase,
                "title": ch.title,
                "learning_goals": list(ch.learning_goals),
                "pages": pages,
            }
        )

    # ------------------------------------------------------------------
    # API: run code
    # ------------------------------------------------------------------
    @app.post("/api/run-code")
    async def run_code(req: RunCodeRequest) -> JSONResponse:
        try:
            res = await asyncio.to_thread(ctx.kernel.execute, req.code, 15)
        except Exception as e:
            return JSONResponse(
                {
                    "status": "error",
                    "stdout": "",
                    "stderr": str(e),
                    "error_name": "RuntimeError",
                    "error_value": str(e),
                }
            )
        body = res.stderr or ""
        if res.status != "ok":
            parts: list[str] = []
            head = f"{res.error_name}: {res.error_value}".strip(": ").strip()
            if head:
                parts.append(head)
            if res.traceback:
                parts.extend(_ANSI_RE.sub("", t) for t in res.traceback)
            if parts:
                detail = "\n".join(parts).strip()
                body = (body + "\n\n" + detail).strip() if body else detail
            if not body:
                body = f"{res.status}: 詳細不明"
        return JSONResponse(
            {
                "status": res.status,
                "stdout": res.stdout or "",
                "stderr": body,
                "error_name": res.error_name,
                "error_value": res.error_value,
            }
        )

    # ------------------------------------------------------------------
    # API: grading
    # ------------------------------------------------------------------
    @app.post("/api/grade/exercise")
    async def grade_exercise_ep(req: GradeExerciseRequest) -> JSONResponse:
        ch = next((c for c in ctx.chapters if c.id == req.chapter_id), None)
        if ch is None or req.page_index >= len(ch.pages):
            return JSONResponse({"ok": False, "error": "chapter / page not found"})
        page = ch.pages[req.page_index]
        if not isinstance(page, ExercisePage):
            return JSONResponse({"ok": False, "error": "not an exercise page"})
        try:
            gr = await asyncio.to_thread(grade_exercise, page, req.answers, ctx.kernel)
            # Self-heal: the form is correct but execution failed because the
            # kernel namespace was polluted by an earlier exercise. Restart the
            # kernel once and re-grade — this matches the behaviour the old
            # PyQt ChapterView had on every submit attempt.
            if (
                not gr.overall_passed
                and gr.form_passed
                and gr.execution is not None
                and gr.execution.status != "ok"
            ):
                await asyncio.to_thread(ctx.kernel.restart)
                gr = await asyncio.to_thread(grade_exercise, page, req.answers, ctx.kernel)

            # Persist the attempt so it shows up in /api/export-progress and
            # in any future analytics. The repo write is on a worker thread
            # because it's synchronous file I/O.
            await asyncio.to_thread(
                ctx.repo.record_submission,
                ctx.user_id,
                chapter_id=req.chapter_id,
                page_index=req.page_index,
                code=gr.assembled_code or "",
                passed=gr.overall_passed,
                stdout=gr.execution.stdout if gr.execution else "",
                stderr=gr.execution.stderr if gr.execution else "",
                hint_level_shown=0,
            )

            return JSONResponse(
                {
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
                }
            )
        except Exception as e:
            log.exception("grade_exercise failed")
            return JSONResponse({"ok": False, "error": str(e)})

    @app.post("/api/grade/reading")
    async def grade_reading_ep(req: GradeReadingRequest) -> JSONResponse:
        ch = next((c for c in ctx.chapters if c.id == req.chapter_id), None)
        if ch is None or req.page_index >= len(ch.pages):
            return JSONResponse({"ok": False, "error": "chapter / page not found"})
        page = ch.pages[req.page_index]
        if not isinstance(page, ReadingPage):
            return JSONResponse({"ok": False, "error": "not a reading page"})
        try:
            gr = grade_reading(page, req.selected)
            # Persist the reading attempt the same way Exercise pages do.
            await asyncio.to_thread(
                ctx.repo.record_submission,
                ctx.user_id,
                chapter_id=req.chapter_id,
                page_index=req.page_index,
                code=f"# reading: selected={req.selected}",
                passed=gr.overall_passed,
                stdout="",
                stderr="",
                hint_level_shown=0,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "passed": gr.overall_passed,
                    "correct_index": page.correct_index,
                    "explanation": page.explanation,
                }
            )
        except Exception as e:
            log.exception("grade_reading failed")
            return JSONResponse({"ok": False, "error": str(e)})

    @app.post("/api/assemble-code")
    async def assemble_code_ep(req: AssembleCodeRequest) -> JSONResponse:
        ch = next((c for c in ctx.chapters if c.id == req.chapter_id), None)
        if ch is None:
            return JSONResponse({"ok": False, "error": "chapter not found"})
        try:
            page = ch.pages[req.page_index]
        except IndexError:
            return JSONResponse({"ok": False, "error": "page not found"})
        if not isinstance(page, ExercisePage):
            return JSONResponse({"ok": False, "error": "not an exercise"})
        try:
            code = assemble_code(page.code_template, req.answers)
            return JSONResponse({"ok": True, "code": code})
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)})

    # ------------------------------------------------------------------
    # API: practice (cross-chapter reading problems)
    # ------------------------------------------------------------------
    @app.get("/api/practice")
    async def practice() -> JSONResponse:
        items: list[dict[str, Any]] = []
        for ch in ctx.chapters:
            for idx, p in enumerate(ch.pages):
                if isinstance(p, ReadingPage):
                    items.append(
                        {
                            "chapterId": ch.id,
                            "phase": ch.phase,
                            "chapterTitle": ch.title,
                            "pageIndex": idx,
                            "title": p.title,
                            "prompt": p.prompt,
                            "code": p.code,
                            "codeFileLabel": p.code_file_label,
                            "choices": list(p.choices),
                        }
                    )
        return JSONResponse({"problems": items})

    # ------------------------------------------------------------------
    # API: tests
    # ------------------------------------------------------------------
    @app.get("/api/tests/{test_id}")
    async def test_detail(test_id: str) -> JSONResponse:
        ts = ctx.test_sets.get(test_id)
        if ts is None:
            raise HTTPException(status_code=404, detail=f"test set {test_id} not found")
        questions = [
            {
                "title": q.title,
                "prompt": q.prompt,
                "code_template": q.code_template,
                "blanks": [
                    {
                        "id": b.id,
                        "placeholder": b.placeholder,
                        "canonical_answer": b.canonical_answer,
                        "hint": b.hint,
                    }
                    for b in q.blanks
                ],
            }
            for q in ts.questions
        ]
        return JSONResponse(
            {
                "id": ts.id,
                "title": ts.title,
                "description": ts.description,
                "phase": ts.phase,
                "time_limit_minutes": ts.time_limit_minutes,
                "pass_score": ts.pass_score,
                "questions": questions,
            }
        )

    @app.post("/api/tests/{test_id}/grade")
    async def test_grade(test_id: str, req: GradeTestRequest) -> JSONResponse:
        ts = ctx.test_sets.get(test_id)
        if ts is None or req.q_index >= len(ts.questions):
            return JSONResponse({"ok": False, "error": "test / question not found"})
        try:
            gr = await asyncio.to_thread(
                grade_exercise,
                ts.questions[req.q_index],
                req.answers,
                ctx.kernel,
            )
            return JSONResponse(
                {
                    "ok": True,
                    "passed": gr.overall_passed,
                    "form_passed": gr.form_passed,
                    "failed_blanks": list(gr.failed_blanks),
                    "stdout": gr.execution.stdout if gr.execution else "",
                    "stderr": gr.execution.stderr if gr.execution else "",
                }
            )
        except Exception as e:
            log.exception("test_grade failed")
            return JSONResponse({"ok": False, "error": str(e)})

    @app.post("/api/tests/record-result")
    async def record_result(req: RecordTestResultRequest) -> JSONResponse:
        try:
            now = datetime.now(UTC)
            started_at = now
            if req.started_at:
                try:
                    started_at = datetime.fromisoformat(req.started_at)
                except Exception:
                    pass
            ctx.repo.record_test_result(
                user_id=ctx.user_id,
                test_id=req.test_id,
                score=req.score,
                total=req.total,
                duration_sec=req.seconds,
                per_question_json=json.dumps(req.perQuestion, ensure_ascii=False),
                started_at=started_at,
                finished_at=now,
            )
            return JSONResponse({"ok": True})
        except Exception as e:
            log.exception("record_result failed")
            return JSONResponse({"ok": False, "error": str(e)})

    # ------------------------------------------------------------------
    # API: progress mutation / wipe
    # ------------------------------------------------------------------
    @app.post("/api/progress")
    async def save_progress(req: SaveProgressRequest) -> JSONResponse:
        try:
            status = ChapterStatus.completed if req.completed else ChapterStatus.in_progress
            ctx.repo.upsert_progress(
                user_id=ctx.user_id,
                chapter_id=req.chapter_id,
                last_page_index=req.page_index,
                status=status,
            )
            return JSONResponse({"ok": True})
        except Exception as e:
            log.exception("save_progress failed")
            return JSONResponse({"ok": False, "error": str(e)})

    @app.post("/api/kernel/restart")
    async def kernel_restart() -> JSONResponse:
        """Restart the IPython kernel so the next chapter / test starts clean.

        The legacy PyQt UI restarted the kernel on every chapter / test entry
        so cross-chapter namespace pollution couldn't masquerade as a correct
        answer or as a NameError demo. This endpoint reinstates that
        behaviour for the web client.
        """
        try:
            ctx.events.publish({"type": "kernel_state", "state": "starting"})
            await asyncio.to_thread(ctx.kernel.restart)
            ctx.events.publish({"type": "kernel_state", "state": "ready"})
            return JSONResponse({"ok": True})
        except Exception as e:
            log.exception("kernel restart failed")
            ctx.events.publish({"type": "kernel_state", "state": "error"})
            return JSONResponse({"ok": False, "error": str(e)})

    @app.post("/api/clear-learning-data")
    async def clear_data() -> JSONResponse:
        try:
            counts = ctx.repo.clear_user_data(ctx.user_id)
            return JSONResponse({"ok": True, "removed": counts})
        except Exception as e:
            log.exception("clear_user_data failed")
            return JSONResponse({"ok": False, "error": str(e)})

    @app.get("/api/export-progress")
    async def export_progress() -> Response:
        """Download all stored progress for the active user as a JSON file.

        Used to collect students' progress to a central machine for
        offline aggregation. The response is delivered with a
        ``Content-Disposition: attachment`` header so the browser saves
        the file instead of rendering it.
        """
        try:
            data = ctx.repo.export_user_data(ctx.user_id)
        except Exception as e:
            log.exception("export_user_data failed")
            return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
        body = json.dumps(data, ensure_ascii=False, indent=2)
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        filename = f"progress-{stamp}.json"
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    # ------------------------------------------------------------------
    # SSE: kernel state stream
    # ------------------------------------------------------------------
    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream():
            q = await ctx.events.subscribe()
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"data: {msg}\n\n"
                    except TimeoutError:
                        yield ": keep-alive\n\n"
            finally:
                await ctx.events.unsubscribe(q)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    return app
