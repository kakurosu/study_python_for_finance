"""Expand `explanation` blocks of all reading-chapter Q&A to 3+ lines.

Reads each `content/chapters/{11,16,22,26,29,32}_reading_phase_?.yaml`,
appends a standardised "ありがちな誤り + 該当章リンク" suffix to each
ReadingPage.explanation (unless already expanded), and writes the chapter
back out as YAML.

The suffix is tailored per phase so the cross-reference makes sense.

Usage:
    uv run python scripts/expand_readings.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CHAPTERS_DIR = ROOT / "content" / "chapters"

# (chapter_id, phase) — reading review chapter
TARGETS = [
    (11, "A"),
    (16, "B"),
    (22, "C"),
    (26, "D"),
    (29, "E"),
    (32, "F"),
]

# Phase-specific "ありがちな誤り" + リンク文
SUFFIX_TEMPLATES = {
    "A": (
        "\n\n**ありがちな誤り**: クォート抜け・インデント崩れ・型混同（`int` と `str` を `+` する等）。"
        "コードを 1 行ずつ声に出して読むと早く気付けます。\n"
        "**詳しくは**: 章 01〜10 (Phase A) で同じ書き方を多角的に練習しています。"
    ),
    "B": (
        "\n\n**ありがちな誤り**: NumPy の `axis=0 / axis=1` 取り違え、pandas の `loc` と `iloc` の混同、"
        "matplotlib で `plt.show()` を忘れる等。`print(df.shape)` で形を確認する癖をつけましょう。\n"
        "**詳しくは**: 章 12〜15 (Phase B) の各章 sample に同じパターンが出てきます。"
    ),
    "C": (
        "\n\n**ありがちな誤り**: 年率換算で √12 を忘れる（分散は線形、標準偏差は √）、`ddof=0/1` の取り違え、"
        "リターンと価格の混同。**CMA 試験で頻出論点**なので、紙でも一度導出を追ってみてください。\n"
        "**詳しくは**: 章 17〜21 (Phase C) で実装と一緒に学べます。"
    ),
    "D": (
        "\n\n**ありがちな誤り**: train データで前処理 fit→test を transform するのを忘れる（リーケージ）、"
        "PyTorch で `model.eval()` 忘れ、ARIMA の `order` を順不同で指定する等。\n"
        "**詳しくは**: 章 23〜25 (Phase D) の参考実装 sample で標準フローが確認できます。"
    ),
    "E": (
        "\n\n**ありがちな誤り**: スクレイピングで間隔を空けない（サイト規約違反）、LLM API でキーをコードに直書き、"
        "レート制限・タイムアウトを考慮しないリトライ無し実装等。\n"
        "**詳しくは**: 章 27〜28 (Phase E) で安全な書き方を解説しています。"
    ),
    "F": (
        "\n\n**ありがちな誤り**: Streamlit の再実行モデルを意識せず重い処理を毎回走らせる、"
        "自動化で `pyautogui.FAILSAFE` を切ってしまう、Playwright で `headless=True` を忘れる等。\n"
        "**詳しくは**: 章 30〜31 (Phase F) で実装パターンと安全装置を扱っています。"
    ),
}

MARKER = "**ありがちな誤り**"  # idempotency guard


class LiteralBlock(str):
    """Marker subclass so PyYAML emits | block scalars for multi-line text."""


def literal_representer(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlock, literal_representer)


def expand_chapter(path: Path, phase: str) -> int:
    """Expand explanations in one reading chapter. Returns count modified."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    suffix = SUFFIX_TEMPLATES[phase]
    n_changed = 0
    for page in raw.get("pages", []):
        if page.get("kind") != "reading":
            continue
        original = (page.get("explanation") or "").rstrip()
        if MARKER in original:
            continue  # already expanded
        new_text = (original + suffix).strip()
        page["explanation"] = new_text
        n_changed += 1

    # Re-emit YAML with | block scalars for any multi-line string field.
    def coerce(node):
        if isinstance(node, dict):
            return {k: coerce(v) for k, v in node.items()}
        if isinstance(node, list):
            return [coerce(v) for v in node]
        if isinstance(node, str) and "\n" in node:
            return LiteralBlock(node)
        return node

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
    total = 0
    for ch_id, phase in TARGETS:
        path = next(CHAPTERS_DIR.glob(f"{ch_id:02d}_*.yaml"))
        n = expand_chapter(path, phase)
        print(f"  [OK] {path.name}: +{n} explanations expanded (Phase {phase})")
        total += n
    print(f"\nTotal expanded: {total}")


if __name__ == "__main__":
    main()
