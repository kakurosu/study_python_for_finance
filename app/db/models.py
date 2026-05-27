"""Plain dataclasses representing the persisted records.

These used to be SQLAlchemy ORM mappings backed by SQLite; the store is now
a single JSON file (see ``repo.py``). The field names match the original
ORM models so any caller that previously did ``progress.last_page_index``
continues to work.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime


class ChapterStatus(enum.StrEnum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


@dataclass
class User:
    id: int
    name: str = "default"
    created_at: datetime | None = None


@dataclass
class ChapterProgress:
    id: int
    user_id: int
    chapter_id: int
    status: ChapterStatus = ChapterStatus.not_started
    last_page_index: int = 0
    updated_at: datetime | None = None


@dataclass
class CellSubmission:
    id: int
    user_id: int
    chapter_id: int
    page_index: int
    code: str = ""
    passed: bool = False
    stdout: str = ""
    stderr: str = ""
    hint_level_shown: int = 0
    submitted_at: datetime | None = None


@dataclass
class TestResult:
    id: int
    user_id: int
    test_id: str
    score: int = 0
    total: int = 0
    duration_sec: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    per_question_json: str = "[]"
