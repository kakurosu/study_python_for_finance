"""Expand `explanation` blocks of all reading-chapter Q&A.

For each `content/chapters/{11,16,22,26,29,32}_reading_phase_?.yaml`:

1. Update **titles** that reference an old chapter number
   (e.g. "（章 11 復習）" → "（章 12 復習）") to the current numbering.
   The Reading review chapters were renumbered earlier (see commit history)
   but the in-title references were not migrated.

2. Rewrite **explanation** to end with the canonical 4-section footer:
       <original explanation>
       **ありがちな誤り**: <phase-specific hint>
       **詳しくは**: 章 NN を再確認してください。
   where `NN` is the **specific chapter** this question reviews
   (taken from the renumbered title), not a phase range.

The script is idempotent — re-running it does not duplicate the footer.

Usage:
    uv run python scripts/expand_readings.py
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "content" / "chapters"
# A marker file recording that title-chapter-number remapping has been
# applied. Without this guard, re-running the script would shift a title
# that's already on the "new" side a second time (e.g. 「章 12 復習」→「章 13 復習」).
TITLE_MIGRATION_DONE = ROOT / "scripts" / ".reading_titles_migrated"

# Reading review chapters: (chapter_id, phase, {old_ref: new_ref}).
# The old_ref → new_ref maps the chapter number referenced in question titles
# (which were not updated when the review chapters were renumbered) to the
# real chapter number in today's layout.
TARGETS: list[tuple[int, str, dict[int, int]]] = [
    (11, "A", {}),  # Phase A: 01-10 unchanged
    (16, "B", {11: 12, 12: 13, 13: 14, 14: 15}),  # Phase B: shifted by +1
    (22, "C", {15: 17, 16: 18, 17: 19, 18: 20, 19: 21}),  # Phase C: shifted by +2
    (26, "D", {20: 23, 21: 24, 22: 25}),  # Phase D: shifted by +3
    (29, "E", {23: 27, 24: 28}),  # Phase E: shifted by +4
    (32, "F", {25: 30, 26: 31}),  # Phase F: shifted by +5
]

# Phase-specific "ありがちな誤り" line (no chapter ref — that goes on the next line)
COMMON_MISTAKE = {
    "A": (
        "**ありがちな誤り**: クォート抜け・インデント崩れ・型混同 (`int` と `str` を `+` する等)。"
        "コードを 1 行ずつ追って読みましょう。"
    ),
    "B": (
        "**ありがちな誤り**: NumPy の `axis=0 / axis=1` 取り違え、pandas の `loc` と `iloc` の混同、"
        "matplotlib で `plt.show()` を忘れる等。`print(df.shape)` で形を確認する癖を。"
    ),
    "C": (
        "**ありがちな誤り**: 年率換算で √12 を忘れる、`ddof=0/1` の取り違え、"
        "リターンと価格の混同。**CMA 試験頻出論点**なので一度紙で導出を追ってみましょう。"
    ),
    "D": (
        "**ありがちな誤り**: train データで前処理 fit→test を transform するのを忘れる (リーケージ)、"
        "PyTorch で `model.eval()` 忘れ、ARIMA の `order` を順不同で指定する等。"
    ),
    "E": (
        "**ありがちな誤り**: スクレイピングで間隔を空けない (規約違反)、LLM API でキーをコード直書き、"
        "レート制限・タイムアウトを考慮しないリトライ無し実装等。"
    ),
    "F": (
        "**ありがちな誤り**: Streamlit の再実行モデルを意識せず重い処理を毎回走らせる、"
        "自動化で `FAILSAFE` を切ってしまう、Playwright で `headless=True` を忘れる等。"
    ),
}

MARKER = "**ありがちな誤り**"
LINK_PREFIX = "**詳しくは**:"

# Regex to find an existing footer block to strip (idempotency).
# Matches one blank line + the **ありがちな誤り** line + the **詳しくは** line.
FOOTER_RE = re.compile(
    r"\n+\s*\*\*ありがちな誤り\*\*[\s\S]*?\*\*詳しくは\*\*:[^\n]*\.?\s*$",
)

# Title chapter reference: "（章 NN 復習）" or "(章 NN 復習)"
TITLE_REF_RE = re.compile(r"[(（]\s*章\s*0*(\d+)\s*復習\s*[)）]")


class LiteralBlock(str):
    pass


def literal_repr(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlock, literal_repr)


def coerce(node):
    if isinstance(node, dict):
        return {k: coerce(v) for k, v in node.items()}
    if isinstance(node, list):
        return [coerce(v) for v in node]
    if isinstance(node, str) and "\n" in node:
        return LiteralBlock(node)
    return node


def remap_title(title: str, mapping: dict[int, int]) -> tuple[str, int | None]:
    """Update the chapter number in title and return (new_title, current_ref).

    `current_ref` is the chapter number that the question reviews **after**
    remapping — used to build the "詳しくは" footer line.
    """
    m = TITLE_REF_RE.search(title)
    if not m:
        return title, None
    old = int(m.group(1))
    new = mapping.get(old, old)  # if not in mapping, assume already current
    if new != old:
        title = TITLE_REF_RE.sub(f"（章 {new:02d} 復習）", title, count=1)
    return title, new


def expand_chapter(
    path: Path,
    phase: str,
    mapping: dict[int, int],
    *,
    migrate_titles: bool,
) -> int:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    mistake_line = COMMON_MISTAKE[phase]
    n_changed = 0
    for page in raw.get("pages", []):
        if page.get("kind") != "reading":
            continue
        # 1) update title chapter ref (only on first run)
        old_title = page.get("title", "")
        if migrate_titles:
            new_title, ref_ch = remap_title(old_title, mapping)
        else:
            # Just read the current chapter number; do NOT shift it.
            m = TITLE_REF_RE.search(old_title)
            ref_ch = int(m.group(1)) if m else None
            new_title = old_title
        if new_title != old_title:
            page["title"] = new_title
            n_changed += 1

        # 2) rewrite explanation footer
        original_full = (page.get("explanation") or "").rstrip()
        # Strip any existing footer block (idempotent re-run)
        body_only = FOOTER_RE.sub("", original_full).rstrip()
        if ref_ch is not None:
            link_line = f"{LINK_PREFIX} 章 {ref_ch:02d} を再確認してください。"
        else:
            link_line = f"{LINK_PREFIX} 該当章を再確認してください。"
        new_text = (body_only + "\n\n" + mistake_line + "\n" + link_line).strip()
        if new_text != original_full:
            page["explanation"] = new_text
            n_changed += 1

    path.write_text(
        yaml.dump(
            coerce(raw),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=1000,
        ),
        encoding="utf-8",
    )
    return n_changed


def main() -> None:
    migrate_titles = not TITLE_MIGRATION_DONE.exists()
    if migrate_titles:
        print("First run: migrating title chapter references (marker will be created).")
    else:
        print("Title chapter references already migrated; only re-applying explanation footers.")
    total = 0
    for ch_id, phase, mapping in TARGETS:
        path = next(CHAPTERS_DIR.glob(f"{ch_id:02d}_*.yaml"))
        n = expand_chapter(path, phase, mapping, migrate_titles=migrate_titles)
        print(f"  [OK] {path.name}: {n} field(s) updated (Phase {phase})")
        total += n
    if migrate_titles:
        TITLE_MIGRATION_DONE.write_text(
            "This file marks that scripts/expand_readings.py has run its one-time "
            "title-chapter-number migration. Do not delete unless you intend to "
            "re-migrate (which would shift already-correct titles).\n",
            encoding="utf-8",
        )
    print(f"\nTotal updates: {total}")


if __name__ == "__main__":
    main()
