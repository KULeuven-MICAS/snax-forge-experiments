"""cluster/tree.py - DC's area_hierarchy.rpt as an indented tree (CSYN1 Part B, X67).

    pixi run python cluster/tree.py AREA_HIERARCHY_RPT [--depth 4] [-o tree.txt]

One line per instance down to --depth (the top is depth 0): its name indented two spaces per level, its total
area (um2, children included), its share of the top's total, and its reference (the design it instantiates).
Children follow their parent in the report's order. Standard library only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEPTH = 4


def _floats(xs: list[str]) -> bool:
    try:
        [float(x) for x in xs]
        return True
    except ValueError:
        return False


def parse(text: str) -> list[dict]:
    """The hierarchical cells: path (the top as '' ), total area, design; in the report's order."""
    rows = []
    for ln in text.split("Hierarchical cell", 1)[-1].splitlines():
        t = ln.split()
        if len(t) == 7 and _floats(t[1:6]):
            rows.append({"path": t[0], "total": float(t[1]), "design": t[6]})
    if rows:
        rows[0]["path"] = ""            # the top's line holds its design name, not a path
    return rows


def tree(rows: list[dict], depth: int = DEPTH) -> list[str]:
    """The indented lines, down to depth (top 0); a child after its parent, siblings in the report's order."""
    if not rows:
        return []
    top_total = rows[0]["total"] or 1.0
    kids: dict[str, list[dict]] = {}
    for r in rows[1:]:
        parent = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
        kids.setdefault(parent, []).append(r)
    out: list[tuple[str, dict]] = []

    def visit(r: dict, d: int) -> None:
        name = r["design"] if d == 0 else r["path"].rsplit("/", 1)[-1]
        out.append(("  " * d + name, r))
        if d < depth:
            for k in kids.get(r["path"], []):
                visit(k, d + 1)

    visit(rows[0], 0)
    w = max(len(n) for n, _ in out)
    return [f"{n:<{w}}  {r['total']:>14.4f}  {100 * r['total'] / top_total:6.2f} %  {r['design']}" for n, r in out]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("report", type=Path)
    ap.add_argument("--depth", type=int, default=DEPTH)
    ap.add_argument("-o", "--out", type=Path)
    a = ap.parse_args()
    lines = tree(parse(a.report.read_text(errors="replace")), a.depth)
    text = "".join(f"{ln}\n" for ln in lines)
    if a.out:
        a.out.write_text(text)
    else:
        sys.stdout.write(text)
    return 0 if lines else 1


if __name__ == "__main__":
    sys.exit(main())
