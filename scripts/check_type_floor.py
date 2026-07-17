#!/usr/bin/env python3
"""Fail if any console text is written below the 12px floor.

WHY THIS EXISTS
---------------
The console drifted to 274 hand-written sub-12px sizes across 28 templates —
`text-[9px]`, `text-[10px]`, `text-[11px]` — because nothing governed them. Every
template invented its own size, so the type kept getting smaller one commit at a
time. An external reviewer called it out as unreadable for field crews, and they
were right.

Raising them once fixes nothing on its own: the next `text-[10px]` someone types
(me, probably) puts it straight back. So the floor is enforced rather than
remembered. This is the same lesson as the test-count evidence — a rule that
isn't checked is a rule that rots.

Use Tailwind's scale (text-xs = 12px and up) instead of arbitrary pixel values.

NOTE: SVG `font-size` inside the chart components is deliberately NOT checked.
Those values are in viewBox units on a chart that scales ~1.9x, so font-size="7"
renders at ~13px — measured, not assumed.

    python scripts/check_type_floor.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "frontend" / "src" / "app"

# Any arbitrary Tailwind text size below 12px.
TOO_SMALL = re.compile(r"text-\[(\d+(?:\.\d+)?)px\]")
FLOOR_PX = 12.0


def main() -> int:
    offenders: list[str] = []
    for path in list(APP.rglob("*.html")) + list(APP.rglob("*.ts")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in TOO_SMALL.finditer(line):
                if float(match.group(1)) < FLOOR_PX:
                    rel = path.relative_to(ROOT)
                    offenders.append(f"  {rel}:{lineno}  {match.group(0)}")

    if offenders:
        print(f"Text below the {FLOOR_PX:.0f}px floor — this console is meant to be")
        print("readable in a truck, in the sun, in gloves:\n")
        print("\n".join(offenders))
        print(f"\n{len(offenders)} occurrence(s). Use Tailwind's scale (text-xs = 12px) instead")
        print("of an arbitrary pixel value.")
        return 1

    print(f"type floor OK — no console text below {FLOOR_PX:.0f}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
