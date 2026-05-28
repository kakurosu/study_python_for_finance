"""Repository: JSON-file-backed persistence layer.

Originally this module wrapped SQLAlchemy / SQLite. The store is now a
single JSON file on disk — for a single-user local learning app with a
few thousand rows, that's faster, has zero native dependencies, and the
file is easy to back up by copy.

The public method signatures are intentionally unchanged so the FastAPI
server and the test suite need no edits beyond their import paths.

Concurrency model
-----------------
The whole file is loaded into memory on construction and flushed after
every mutation under an ``RLock``. FastAPI dispatches handlers on a
single asyncio loop, but ``asyncio.to_thread`` can run grading off the
loop concurrently with progress writes, so the lock matters even though
this is a single-process app.

Writes are atomic — we render to a sibling ``*.tmp`` and ``os.replace``
it onto the destination, so a crash mid-write cannot corrupt the
canonical file.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    CellSubmission,
    ChapterProgress,
    ChapterStatus,
    TestResult,
    User,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# datetime helpers — JSON has no native date type, so we round-trip via
# ISO-8601 strings stored without timezone info (the original SQLite schema
# stored naive datetimes too).
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dt_to_str(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat()


def _str_to_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Empty-state factory
# ---------------------------------------------------------------------------


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "users": [],
        "chapter_progress": [],
        "cell_submissions": [],
        "test_results": [],
        "next_ids": {
            "user": 1,
            "progress": 1,
            "submission": 1,
            "test_result": 1,
        },
    }


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class Repository:
    """JSON-file-backed store. Drop-in replacement for the old SQLAlchemy one."""

    def __init__(self, db_path: Path) -> None:
        db_path = Path(db_path).resolve()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        # Accept the legacy "*.db" path the SQLite store used. Swap to a
        # ``.json`` sibling so we never overwrite a real SQLite file by
        # accident.
        legacy_sqlite_path: Path | None = None
        if db_path.suffix.lower() in (".db", ".sqlite", ".sqlite3"):
            legacy_sqlite_path = db_path
            db_path = db_path.with_suffix(".json")
        self._path = db_path
        self._lock = threading.RLock()
        # One-shot migration: if a legacy SQLite store sits next to the
        # JSON path AND no JSON store exists yet, import the SQLite rows
        # into the JSON state once. This prevents silent data loss when
        # an existing user upgrades from the SQLAlchemy store.
        sqlite_sibling = self._path.with_suffix(".db")
        if not self._path.exists() and sqlite_sibling.exists():
            legacy_sqlite_path = sqlite_sibling
        self._state = self._load()
        if legacy_sqlite_path is not None and legacy_sqlite_path.exists() and self._is_empty_state():
            self._import_legacy_sqlite(legacy_sqlite_path)

    def _is_empty_state(self) -> bool:
        return (
            not self._state["users"]
            and not self._state["chapter_progress"]
            and not self._state["cell_submissions"]
            and not self._state["test_results"]
        )

    def _import_legacy_sqlite(self, sqlite_path: Path) -> None:
        """Best-effort one-shot import of a legacy SQLAlchemy/SQLite store.

        Reads via stdlib ``sqlite3`` (no SQLAlchemy dependency) and seeds the
        in-memory state. On any error we log and leave the JSON store empty
        rather than crash — the user can still re-run with a fresh store.
        The original ``.db`` file is renamed with a ``.imported`` suffix so
        the migration is idempotent and the original data is preserved.
        """
        import sqlite3

        try:
            con = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        except sqlite3.Error:
            log.exception("legacy sqlite open failed: %s", sqlite_path)
            return
        try:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            for table in ("users", "chapter_progress", "cell_submissions", "test_results"):
                try:
                    cur.execute(f"SELECT * FROM {table}")  # noqa: S608 — fixed names, no user input
                except sqlite3.Error:
                    continue
                rows = [dict(r) for r in cur.fetchall()]
                self._state[table] = rows
                if rows:
                    max_id = max(int(r.get("id", 0)) for r in rows)
                    key = {
                        "users": "user",
                        "chapter_progress": "progress",
                        "cell_submissions": "submission",
                        "test_results": "test_result",
                    }[table]
                    self._state["next_ids"][key] = max_id + 1
            self._save()
            log.info(
                "imported legacy sqlite store: %d users, %d progress, %d submissions, %d test_results",
                len(self._state["users"]),
                len(self._state["chapter_progress"]),
                len(self._state["cell_submissions"]),
                len(self._state["test_results"]),
            )
        finally:
            con.close()
        # Move the SQLite file aside so the migration is idempotent.
        try:
            sqlite_path.rename(sqlite_path.with_suffix(".db.imported"))
        except OSError:
            log.warning("could not rename %s after import", sqlite_path)

    # ------------------------------------------------------------------
    # File I/O
    # ------------------------------------------------------------------
    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return _empty_state()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.exception("progress store unreadable, starting fresh: %s", self._path)
            try:
                backup = self._path.with_suffix(f".corrupt-{int(_now().timestamp())}.json")
                self._path.rename(backup)
                log.warning("backed up corrupt store to %s", backup)
            except OSError:
                pass
            return _empty_state()
        # json.loads returns Any; pin it to the dict shape the rest of the
        # repository assumes (mypy --strict otherwise flags the implicit cast).
        if not isinstance(raw, dict):
            log.warning("progress store at %s was not a JSON object; resetting", self._path)
            return _empty_state()
        data: dict[str, Any] = raw
        # Be forgiving about missing keys so older state files still load.
        empty = _empty_state()
        for k, default in empty.items():
            data.setdefault(k, default)
        for k, default in empty["next_ids"].items():
            data["next_ids"].setdefault(k, default)
        return data

    def _save(self) -> None:
        tmp = self._path.with_name(self._path.name + ".tmp")
        payload = json.dumps(self._state, ensure_ascii=False, indent=2)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)

    def _next_id(self, key: str) -> int:
        nid = int(self._state["next_ids"].get(key, 1))
        self._state["next_ids"][key] = nid + 1
        return nid

    # ------------------------------------------------------------------
    # Row ↔ dataclass conversion
    # ------------------------------------------------------------------
    @staticmethod
    def _user_from_row(row: dict[str, Any]) -> User:
        return User(
            id=int(row["id"]),
            name=str(row.get("name", "default")),
            created_at=_str_to_dt(row.get("created_at")),
        )

    @staticmethod
    def _progress_from_row(row: dict[str, Any]) -> ChapterProgress:
        return ChapterProgress(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            chapter_id=int(row["chapter_id"]),
            status=ChapterStatus(row.get("status", ChapterStatus.not_started.value)),
            last_page_index=int(row.get("last_page_index", 0)),
            updated_at=_str_to_dt(row.get("updated_at")),
        )

    @staticmethod
    def _submission_from_row(row: dict[str, Any]) -> CellSubmission:
        return CellSubmission(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            chapter_id=int(row["chapter_id"]),
            page_index=int(row["page_index"]),
            code=str(row.get("code", "")),
            passed=bool(row.get("passed", False)),
            stdout=str(row.get("stdout", "")),
            stderr=str(row.get("stderr", "")),
            hint_level_shown=int(row.get("hint_level_shown", 0)),
            submitted_at=_str_to_dt(row.get("submitted_at")),
        )

    @staticmethod
    def _test_result_from_row(row: dict[str, Any]) -> TestResult:
        return TestResult(
            id=int(row["id"]),
            user_id=int(row["user_id"]),
            test_id=str(row["test_id"]),
            score=int(row.get("score", 0)),
            total=int(row.get("total", 0)),
            duration_sec=int(row.get("duration_sec", 0)),
            started_at=_str_to_dt(row.get("started_at")),
            finished_at=_str_to_dt(row.get("finished_at")),
            per_question_json=str(row.get("per_question_json", "[]")),
        )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    def get_or_create_default_user(self) -> User:
        with self._lock:
            for row in self._state["users"]:
                if row.get("name") == "default":
                    return self._user_from_row(row)
            new_row = {
                "id": self._next_id("user"),
                "name": "default",
                "created_at": _dt_to_str(_now()),
            }
            self._state["users"].append(new_row)
            self._save()
            return self._user_from_row(new_row)

    # ------------------------------------------------------------------
    # Chapter progress
    # ------------------------------------------------------------------
    def get_progress(self, user_id: int, chapter_id: int) -> ChapterProgress | None:
        with self._lock:
            for row in self._state["chapter_progress"]:
                if row["user_id"] == user_id and row["chapter_id"] == chapter_id:
                    return self._progress_from_row(row)
            return None

    def upsert_progress(
        self,
        user_id: int,
        chapter_id: int,
        *,
        last_page_index: int,
        status: ChapterStatus,
    ) -> None:
        with self._lock:
            now_str = _dt_to_str(_now())
            for row in self._state["chapter_progress"]:
                if row["user_id"] == user_id and row["chapter_id"] == chapter_id:
                    row["status"] = str(status)
                    row["last_page_index"] = int(last_page_index)
                    row["updated_at"] = now_str
                    self._save()
                    return
            self._state["chapter_progress"].append(
                {
                    "id": self._next_id("progress"),
                    "user_id": int(user_id),
                    "chapter_id": int(chapter_id),
                    "status": str(status),
                    "last_page_index": int(last_page_index),
                    "updated_at": now_str,
                }
            )
            self._save()

    def latest_in_progress(self, user_id: int) -> ChapterProgress | None:
        """Most recently-touched chapter for ``user_id`` that's not completed."""
        with self._lock:
            candidates = [
                row
                for row in self._state["chapter_progress"]
                if row["user_id"] == user_id and row.get("status") != ChapterStatus.completed.value
            ]
            if not candidates:
                return None
            # Sort by updated_at desc; missing timestamps sort last.
            candidates.sort(
                key=lambda r: r.get("updated_at") or "",
                reverse=True,
            )
            return self._progress_from_row(candidates[0])

    def all_progress(self, user_id: int) -> list[ChapterProgress]:
        with self._lock:
            return [
                self._progress_from_row(row)
                for row in self._state["chapter_progress"]
                if row["user_id"] == user_id
            ]

    def reset_all(self, user_id: int) -> None:
        with self._lock:
            self._state["chapter_progress"] = [
                row for row in self._state["chapter_progress"] if row["user_id"] != user_id
            ]
            self._save()

    # ------------------------------------------------------------------
    # Submissions
    # ------------------------------------------------------------------
    def record_submission(
        self,
        user_id: int,
        chapter_id: int,
        page_index: int,
        *,
        code: str,
        passed: bool,
        stdout: str,
        stderr: str,
        hint_level_shown: int,
    ) -> None:
        with self._lock:
            self._state["cell_submissions"].append(
                {
                    "id": self._next_id("submission"),
                    "user_id": int(user_id),
                    "chapter_id": int(chapter_id),
                    "page_index": int(page_index),
                    "code": str(code),
                    "passed": bool(passed),
                    "stdout": str(stdout),
                    "stderr": str(stderr),
                    "hint_level_shown": int(hint_level_shown),
                    "submitted_at": _dt_to_str(_now()),
                }
            )
            self._save()

    def submissions_for_page(
        self,
        user_id: int,
        chapter_id: int,
        page_index: int,
    ) -> list[CellSubmission]:
        with self._lock:
            rows = [
                row
                for row in self._state["cell_submissions"]
                if row["user_id"] == user_id
                and row["chapter_id"] == chapter_id
                and row["page_index"] == page_index
            ]
            rows.sort(key=lambda r: r.get("submitted_at") or "")
            return [self._submission_from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Test results
    # ------------------------------------------------------------------
    def record_test_result(
        self,
        user_id: int,
        *,
        test_id: str,
        score: int,
        total: int,
        duration_sec: int,
        per_question_json: str,
        started_at: datetime,
        finished_at: datetime,
    ) -> int:
        with self._lock:
            new_id = self._next_id("test_result")
            self._state["test_results"].append(
                {
                    "id": new_id,
                    "user_id": int(user_id),
                    "test_id": str(test_id),
                    "score": int(score),
                    "total": int(total),
                    "duration_sec": int(duration_sec),
                    "started_at": _dt_to_str(started_at),
                    "finished_at": _dt_to_str(finished_at),
                    "per_question_json": str(per_question_json),
                }
            )
            self._save()
            return new_id

    def list_test_results(self, user_id: int) -> list[TestResult]:
        with self._lock:
            rows = [row for row in self._state["test_results"] if row["user_id"] == user_id]
            rows.sort(key=lambda r: r.get("finished_at") or "", reverse=True)
            return [self._test_result_from_row(row) for row in rows]

    # ------------------------------------------------------------------
    # Wipe
    # ------------------------------------------------------------------
    def clear_user_data(self, user_id: int) -> dict[str, int]:
        """Drop progress / submissions / test results for ``user_id``.

        Returns a count summary; the user row itself is preserved.
        """
        with self._lock:
            p_count = sum(1 for r in self._state["chapter_progress"] if r["user_id"] == user_id)
            s_count = sum(1 for r in self._state["cell_submissions"] if r["user_id"] == user_id)
            t_count = sum(1 for r in self._state["test_results"] if r["user_id"] == user_id)
            self._state["chapter_progress"] = [
                r for r in self._state["chapter_progress"] if r["user_id"] != user_id
            ]
            self._state["cell_submissions"] = [
                r for r in self._state["cell_submissions"] if r["user_id"] != user_id
            ]
            self._state["test_results"] = [r for r in self._state["test_results"] if r["user_id"] != user_id]
            self._save()
            return {
                "chapter_progress": p_count,
                "submissions": s_count,
                "test_results": t_count,
            }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------
    def export_user_data(self, user_id: int) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of everything stored for ``user_id``.

        Used by ``GET /api/export-progress`` so an instructor can collect
        progress files from each student's machine and aggregate them
        offline. The returned dict re-uses the same field names as the
        on-disk store, prefixed with metadata (``exported_at``, schema
        version) for forward-compatibility.
        """
        with self._lock:
            user = next(
                (dict(r) for r in self._state["users"] if r["id"] == user_id),
                None,
            )
            return {
                "schema_version": self._state.get("schema_version", 1),
                "exported_at": _dt_to_str(_now()),
                "user": user,
                "chapter_progress": [
                    dict(r) for r in self._state["chapter_progress"] if r["user_id"] == user_id
                ],
                "cell_submissions": [
                    dict(r) for r in self._state["cell_submissions"] if r["user_id"] == user_id
                ],
                "test_results": [dict(r) for r in self._state["test_results"] if r["user_id"] == user_id],
            }
