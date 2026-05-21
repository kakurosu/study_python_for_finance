"""Command palette actions — data model + registry.

An `Action` is a single executable command (e.g. "ダッシュボードを開く").
The `CommandRegistry` is a flat list that the palette searches. The host
application (`MainWindow`) populates it on startup via
`register_default_actions()`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Action:
    id: str
    title: str                # 日本語主体
    group: str                # "ナビゲート" / "章" / "テスト" / "設定"
    icon: str = "·"           # single text glyph
    subtitle: str = ""        # right-aligned descriptor (e.g. "Phase A")
    shortcut: tuple[str, ...] | None = None
    keywords: tuple[str, ...] = field(default_factory=tuple)
    run: Callable[[], None] = field(default=lambda: None)


class CommandRegistry:
    """Holds the live list of actions. Mutable; the palette rebuilds rows
    each time it opens, so dynamic re-registration is fine."""

    GROUP_ORDER = ("ナビゲート", "章", "テスト", "ヘルプ", "設定")

    def __init__(self) -> None:
        self._actions: list[Action] = []

    def register(self, action: Action) -> None:
        # Replace by id if it already exists, so dynamic chapter listings
        # don't accumulate duplicates across reopens.
        existing = next((i for i, a in enumerate(self._actions) if a.id == action.id), None)
        if existing is not None:
            self._actions[existing] = action
        else:
            self._actions.append(action)

    def register_many(self, actions: Iterable[Action]) -> None:
        for a in actions:
            self.register(a)

    def clear(self) -> None:
        self._actions.clear()

    def all(self) -> Sequence[Action]:
        return tuple(self._actions)

    # ------------------------------------------------------------------
    def search(self, query: str) -> list[Action]:
        """Return actions ranked by simple substring + prefix score.

        Empty query returns everything in group order. Scoring favours:
        - title prefix match (3)
        - title substring match (2)
        - keyword exact match (1.5)
        - keyword substring match (1)
        - subtitle substring match (0.5)
        """
        q = query.strip().lower()
        if not q:
            return self._sorted_default()

        scored: list[tuple[float, int, Action]] = []
        for idx, a in enumerate(self._actions):
            t = a.title.lower()
            s = a.subtitle.lower()
            score = 0.0
            if t.startswith(q):
                score += 3.0
            elif q in t:
                score += 2.0
            for kw in a.keywords:
                kl = kw.lower()
                if kl == q:
                    score += 1.5
                elif q in kl:
                    score += 1.0
            if q in s:
                score += 0.5
            if score > 0:
                scored.append((score, idx, a))
        scored.sort(key=lambda r: (-r[0], r[1]))
        return [a for _, _, a in scored]

    def _sorted_default(self) -> list[Action]:
        rank = {g: i for i, g in enumerate(self.GROUP_ORDER)}
        return sorted(
            self._actions,
            key=lambda a: (rank.get(a.group, 99), self._actions.index(a)),
        )

    def grouped(self, actions: Sequence[Action]) -> list[tuple[str, list[Action]]]:
        """Return ``[(group, [actions...]), ...]`` preserving GROUP_ORDER."""
        bucket: dict[str, list[Action]] = {}
        for a in actions:
            bucket.setdefault(a.group, []).append(a)
        ordered: list[tuple[str, list[Action]]] = []
        for g in self.GROUP_ORDER:
            if g in bucket:
                ordered.append((g, bucket[g]))
        # Catch-all for any unknown group.
        for g, items in bucket.items():
            if g not in self.GROUP_ORDER:
                ordered.append((g, items))
        return ordered
