"""Expand Phase A/B/C test prompts, hints, and stickman_feedback.

For each question in `content/tests/phase_{a,b,c}_test.yaml`:
- Append a phase-specific "論点" footer to ``prompt`` (if not already there)
- Generate 3-step ``hints`` derived from the first blank's canonical_answer
  (only when ``hints`` is missing or has < 3 items)
- Rewrite ``stickman_feedback.wrong_hint{1,2,3}`` from parrot-back ("`X`")
  to "形 → 絞り込み → 答え" guiding text

Idempotent: the prompt footer's marker string prevents double-expansion.

Usage:
    uv run python scripts/expand_tests.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = ROOT / "content" / "tests"

PHASE_FOOTER = {
    "A": (
        "**Phase A の論点**: 文法基礎の正確さが問われます。クォートの種類・"
        "インデント幅・`**` (べき乗) と `^` (XOR) の取り違え・型変換を意識して。"
    ),
    "B": (
        "**Phase B の論点**: NumPy / pandas / matplotlib の **API 名と axis 指定** が頻出。"
        "`print(df.shape)` `print(arr.dtype)` で形と型を都度確認する癖を。"
    ),
    "C": (
        "**Phase C の論点**: 金融計算では **年率換算 (√12)・ddof・リスクフリーレート単位** を"
        "間違えやすい。CMA 試験頻出論点なので公式の **次元 (時間 / 量) を意識** しましょう。"
    ),
}

FOOTER_MARKER = "Phase {ph} の論点"


class LiteralBlock(str):
    pass


def literal_repr(dumper, data):
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")


yaml.add_representer(LiteralBlock, literal_repr)


def coerce_multiline(node):
    if isinstance(node, dict):
        return {k: coerce_multiline(v) for k, v in node.items()}
    if isinstance(node, list):
        return [coerce_multiline(v) for v in node]
    if isinstance(node, str) and "\n" in node:
        return LiteralBlock(node)
    return node


def _trim(ans: str, n: int = 30) -> str:
    return ans if len(ans) <= n else ans[:n] + "..."


def expand_question(q: dict, phase: str) -> bool:
    """Mutate one question in place. Returns True if anything changed."""
    changed = False

    # 1) prompt footer
    prompt = (q.get("prompt") or "").rstrip()
    marker = FOOTER_MARKER.format(ph=phase)
    if marker not in prompt:
        footer = PHASE_FOOTER[phase]
        q["prompt"] = (prompt + "\n\n" + footer).strip()
        changed = True

    # 2) hints (3 steps) — derived from first blank's canonical_answer
    blanks = q.get("blanks") or []
    if blanks:
        ans = blanks[0].get("canonical_answer", "")
        existing_hints = q.get("hints") or []
        if len(existing_hints) < 3:
            shape_hint = (
                f"使う API・記号を思い出して、形を絞り込もう。 答えはおそらく **{len(ans)} 文字程度** の式。"
            )
            mid_hint = f"パターンは `{_trim(ans)}` に似た形になる。"
            final_hint = f"答え: `{ans}`"
            q["hints"] = existing_hints + [
                h for h in [shape_hint, mid_hint, final_hint] if h not in existing_hints
            ]
            q["hints"] = q["hints"][:3] if len(q["hints"]) >= 3 else q["hints"] + [final_hint]
            # Ensure 3 distinct hints
            seen = set()
            q["hints"] = [h for h in q["hints"] if not (h in seen or seen.add(h))][:3]
            changed = True

    # 3) stickman_feedback wrong_hints — turn parrot-back into guided steps
    sf = q.setdefault("stickman_feedback", {})
    if blanks:
        ans = blanks[0].get("canonical_answer", "")
        # Detect parrot-back: wrong_hint1 == wrong_hint2 == wrong_hint3 == f"`{ans}`"
        parrot = f"`{ans}`"
        wh1 = sf.get("wrong_hint1", "")
        wh2 = sf.get("wrong_hint2", "")
        wh3 = sf.get("wrong_hint3", "")
        is_parrot = (wh1 == wh2 == wh3) or (wh1 == parrot and wh2 == parrot)
        if is_parrot or not wh1 or not wh2 or not wh3:
            sf["wrong_hint1"] = "形をもう一度見直してみよう。 使う関数・記号は授業で出てきたものだよ。"
            sf["wrong_hint2"] = f"パターンは `{_trim(ans)}` に近い形だね。"
            sf["wrong_hint3"] = f"答えは `{ans}` だよ。"
            changed = True

    return changed


def main() -> None:
    for path in sorted(TESTS_DIR.glob("phase_*_test.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        phase = data.get("phase", "A")
        n_changed = 0
        for q in data.get("questions", []):
            if expand_question(q, phase):
                n_changed += 1
        path.write_text(
            yaml.dump(
                coerce_multiline(data),
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
                width=1000,
            ),
            encoding="utf-8",
        )
        print(f"  [OK] {path.name}: {n_changed} questions expanded")


if __name__ == "__main__":
    main()
