"""One-shot chapter renumbering script.

After this runs, Reading review chapters slot in immediately after each
phase's regular chapters so the chapter list reads sequentially
(01..32) instead of jumping from 10 to 27.

Mapping (old id -> new id):
    01..10  unchanged    (Phase A)
    27 -> 11             (Phase A reading review)
    11 -> 12, 12 -> 13, 13 -> 14, 14 -> 15  (Phase B chapters)
    28 -> 16             (Phase B reading review)
    15 -> 17, 16 -> 18, 17 -> 19, 18 -> 20, 19 -> 21  (Phase C)
    29 -> 22             (Phase C reading review)
    20 -> 23, 21 -> 24, 22 -> 25  (Phase D)
    30 -> 26             (Phase D reading review)
    23 -> 27, 24 -> 28   (Phase E)
    31 -> 29             (Phase E reading review)
    25 -> 30, 26 -> 31   (Phase F)
    32 unchanged         (Phase F reading review)

The script:
    * reads each YAML
    * remaps the `id` and any `prerequisites` entries
    * writes the YAML back under its new prefixed filename
    * deletes the old file (after confirming new file exists)

Run from the project root:
    uv run python scripts/renumber_chapters.py
"""

from __future__ import annotations

import re
from pathlib import Path

MAPPING = {
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
    6: 6,
    7: 7,
    8: 8,
    9: 9,
    10: 10,
    27: 11,
    11: 12,
    12: 13,
    13: 14,
    14: 15,
    28: 16,
    15: 17,
    16: 18,
    17: 19,
    18: 20,
    19: 21,
    29: 22,
    20: 23,
    21: 24,
    22: 25,
    30: 26,
    23: 27,
    24: 28,
    31: 29,
    25: 30,
    26: 31,
    32: 32,
}


def main() -> None:
    chapters_dir = Path(__file__).resolve().parent.parent / "content" / "chapters"
    print(f"chapters dir: {chapters_dir}")

    # Stage 1: read every file into memory (path, old_id, new_id, body)
    plans: list[tuple[Path, int, int, str]] = []
    for path in sorted(chapters_dir.glob("*.yaml")):
        m = re.match(r"^(\d{2})_(.+)\.ya?ml$", path.name)
        if not m:
            print(f"  skip non-chapter file: {path.name}")
            continue
        old_id = int(m.group(1))
        slug = m.group(2)
        if old_id not in MAPPING:
            print(f"  WARN: no mapping for {path.name} (id={old_id})")
            continue
        new_id = MAPPING[old_id]
        body = path.read_text(encoding="utf-8")
        new_path = chapters_dir / f"{new_id:02d}_{slug}.yaml"
        plans.append((path, old_id, new_id, body))

    # Stage 2: remap content (id + prerequisites)
    for path, old_id, new_id, body in plans:
        # Rewrite top-level "id: NN" line. Anchored at start-of-line.
        body = re.sub(
            r"^(id:\s*)\d+(\s*$)",
            lambda m, _new_id=new_id: f"{m.group(1)}{_new_id}{m.group(2)}",
            body,
            count=1,
            flags=re.MULTILINE,
        )

        # Rewrite prerequisites list. Looks like:
        #   prerequisites: [1, 2, 3]
        def _remap_list(match: re.Match[str]) -> str:
            raw = match.group(1)
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            new_parts: list[str] = []
            for p in parts:
                try:
                    nid = int(p)
                    new_parts.append(str(MAPPING.get(nid, nid)))
                except ValueError:
                    new_parts.append(p)
            return f"prerequisites: [{', '.join(new_parts)}]"

        body = re.sub(
            r"prerequisites:\s*\[([^\]]*)\]",
            _remap_list,
            body,
        )
        # Persist the new file
        new_path = chapters_dir / f"{new_id:02d}_{path.name.split('_', 1)[1]}"
        new_path.write_text(body, encoding="utf-8")
        print(f"  {path.name} (id={old_id}) -> {new_path.name} (id={new_id})")

    # Stage 3: delete old files whose names changed
    for path, old_id, new_id, _ in plans:
        if old_id == new_id:
            continue
        # The file may have already been overwritten if old_path == new_path
        # path is the old name; it's only safe to delete if a new file
        # with a different name now holds the content.
        if path.exists():
            path.unlink()
            print(f"  deleted old file {path.name}")


if __name__ == "__main__":
    main()
