#!/usr/bin/env python3
"""report/cluster_fixed.py - the cluster's fixed parts: what every design pays whatever its accelerators (X103).

    pixi run cluster-fixed [--tech nangate45] [--md]

From one clock-gated cluster point (POINT) and its run window (WINDOW), per group of cluster/groups.json that is
not one of HWCOST's five parts: its area (breakdown.json), its leakage (PrimePower's power_hierarchy.rpt in the
window, the leakage column summed into groups as report/cluster_breakdown.py sums area) and its idle floor, the
dynamic energy per cycle it spends while the accelerator runs and the DMA waits (energy.json). The macros' leakage
is the lstp table's (results/ram/<tech>/ram_table.csv, X47 · X100), not the reports' (their macros are older). The
groups add up to three parts, PARTS: the core, the DMA and the rest of the cluster. The TCDM bank logic moves with
L1 traffic, so it has no idle floor here. Writes results/cluster/<tech>/cluster_fixed.json; --md prints the tables.
Standard library and arc/arc.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "arc"), str(ROOT / "report")]
import arc  # noqa: E402
import cluster_breakdown as cb  # noqa: E402
import cluster_energy as ce  # noqa: E402

GROUPS = ROOT / "cluster" / "groups.json"
POINTS = ROOT / "cluster" / "points.json"
POINT, WINDOW = "dot3_w8_cg", "5_run"
PARTS = {"core": ("cores", "icache_logic", "icache_macros"),
         "dma": ("dma",),
         "rest": ("axi", "peripherals", "tcdm_logic", "acc_csr", "acc_interface", "others")}
NO_FLOOR = ("tcdm_logic",)                       # moves with L1 traffic: priced per access later, not per cycle
MACRO_GROUPS = {"icache_macros": "icache"}       # a macro group and the word its macros' memories hold
_SRAM = re.compile(r"sram_d(\d+)_w(\d+)(?:_m\d+)?")


def leak_rows(text: str) -> list[dict]:
    """PrimePower's power_hierarchy.rpt with each node's leakage (W) as `total`, for cluster_breakdown.groups."""
    rows = []
    stack: list[tuple[int, str]] = []
    for ln in text.splitlines():
        m = ce._ROW.match(ln)
        if not m:
            continue
        depth = len(m.group(1)) // 2
        name, design = m.group(2), m.group(3) or m.group(2)
        if not rows and depth != 0:
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, name))
        rows.append({"path": "/".join(n for _, n in stack[1:]), "design": design, "total": float(m.group(6))})
    return rows


def bank_leak_uw(tech: str) -> dict[tuple[int, int], float]:
    """The lstp table's leakage per (depth, width)."""
    with (ROOT / "results" / "ram" / tech / "ram_table.csv").open(newline="") as fh:
        return {(int(r["depth"]), int(r["width"])): float(r["leak_uw"]) for r in csv.DictReader(fh)}


def macro_leak_uw(srams: dict[str, int], word: str, table: dict) -> float:
    """The leakage of the point's macros whose names say they are `word`'s: the icache's are its 128-word ones."""
    total = 0.0
    for name, n in srams.items():
        d, w = (int(x) for x in _SRAM.fullmatch(name).groups())
        if word == "icache" and d != 128:
            continue
        total += n * table[(d, -(-w // 8) * 8)]
    return total


def fixed(tech: str) -> dict:
    cfg = json.loads(GROUPS.read_text())
    point = next(p for p in json.loads(POINTS.read_text())["points"] if p["point"] == POINT)
    area = {g["name"]: g["area_um2"] for g in json.loads(
        (ROOT / "results" / "cluster" / tech / "breakdown.json").read_text())[POINT]["groups"]}
    win = next(w for w in json.loads((ROOT / "results" / "cluster" / tech / "energy.json").read_text())[POINT]["windows"]
               if w["name"] == WINDOW)
    rep = ROOT / "results" / "cluster" / tech / "power_reports" / f"{POINT}.zip"
    rows = leak_rows(arc.read_text(rep, f"{WINDOW}/power_hierarchy.rpt", errors="replace"))
    leak = {k: v * 1e6 for k, v in cb.groups(rows, cfg).items()}          # W to uW
    table = bank_leak_uw(tech)
    groups = {}
    for part, names in PARTS.items():
        for g in names:
            lk = macro_leak_uw(point["srams"], MACRO_GROUPS[g], table) if g in MACRO_GROUPS else leak[g]
            groups[g] = {"part": part, "area_um2": area[g], "leak_uw": lk,
                         "idle_pj_cycle": None if g in NO_FLOOR else win["groups"][g]}
    parts = {p: {"groups": list(ns), "area_um2": sum(groups[g]["area_um2"] for g in ns),
                 "leak_uw": sum(groups[g]["leak_uw"] for g in ns),
                 "idle_pj_cycle": sum(groups[g]["idle_pj_cycle"] or 0.0 for g in ns)} for p, ns in PARTS.items()}
    return {"tech": tech, "clock_ns": win["clock_ns"],
            "source": {"point": POINT, "window": WINDOW, "macros": "results/ram/<tech>/ram_table.csv (itrs-lstp)",
                       "no_idle_floor": list(NO_FLOOR)},
            "units": {"area": "um2", "leakage": "uW", "idle": "pJ per cycle"},
            "parts": parts, "groups": groups,
            "check": {"pt_leak_uw": rows[0]["total"] * 1e6, "groups_leak_uw": sum(leak.values())}}


def markdown(j: dict) -> str:
    out = [f"The fixed parts of `{j['source']['point']}` (window `{j['source']['window']}`, {j['clock_ns']} ns):", "",
           "| Part | Group | Area (µm²) | Leakage (µW) | Idle (pJ a cycle) |", "|---|---|---:|---:|---:|"]
    for g, x in j["groups"].items():
        idle = "–" if x["idle_pj_cycle"] is None else f"{x['idle_pj_cycle']:.2f}"
        out.append(f"| {x['part']} | {g} | {x['area_um2']:,.0f} | {x['leak_uw']:,.1f} | {idle} |")
    for p, x in j["parts"].items():
        out.append(f"| **{p}** | | {x['area_um2']:,.0f} | {x['leak_uw']:,.1f} | {x['idle_pj_cycle']:.2f} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the table as Markdown")
    a = ap.parse_args()
    j = fixed(a.tech)
    path = ROOT / "results" / "cluster" / a.tech / "cluster_fixed.json"
    path.write_text(json.dumps(j, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")
    if a.md:
        print(markdown(j))
    c = j["check"]
    if abs(c["groups_leak_uw"] - c["pt_leak_uw"]) > 1e-6 * c["pt_leak_uw"]:
        print(f"the groups' leakage {c['groups_leak_uw']:.3f} uW differs from the top's {c['pt_leak_uw']:.3f}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
