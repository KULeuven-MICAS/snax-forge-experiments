#!/usr/bin/env python3
"""report/cg2_reprice.py - CG2: dot_3's HWCOST parts priced again with the clock-gated tables (X83), in this repo.

  pixi run cg2-reprice [--tech nangate45]
  pixi run cg2-reprice-test                       report/test_cg2_reprice.py

snax-forge is not changed in CG2, so its estimate is not run on the gated tables; this script prices dot_3 the way
snax-forge's estimate/cost.py does, from one table set at a time:

  ungated  results/strm/<tech>/streamer.csv, xbar.csv and results/char/<tech>/char.json
  gated    results/strm/<tech>/streamer_cg.csv, xbar_cg.csv and results/char/<tech>/char_cg.json
  both     results/strm/<tech>/xbar_kinds.json (f_ro and f_wo carry over, X83) and the memory part as the committed
           HWCOST json gives it (CACTI's macros, unchanged)

dot_3 at W, N = 2048 (cluster/points.json's dot3_w<W>): two readers of W channels and one writer of one channel, all
FIFO depth 8 and one loop (X52: a writer priced as a reader); a mul ElementwiseLanes and a TreeAccumulate (64-bit
output register) at W lanes, N / W fires each; a control unit of 67 bits; C_acc = N / W + 1 cycles. The crossbar's
inputs, read-only and write-only inputs, banks and accesses are read from the committed
results/cluster/<tech>/hwcost/dot3_w<W>.json. Per part (area um2, energy nJ):

  streamers  2 A(8, 1, W) + A(8, 1, 1);  (2 (N / W) e_beat(8, 1, W) + e_beat(8, 1, 1)) / 1000
  crossbar   A(n_in, b) (1 - f_ro n_ro / n_in - f_wo n_wo / n_in);  n_acc e_acc(b, b) / 1000
  datapath   comb(mul) + comb(tree) + 64 A_flop;  (E_unit(mul) + E_unit(tree)) / 1000, char_export.py's e_unit
  control    2 x 67 A_flop (flops plus an equal comb part);  f_ctrl 67 C_acc e_hold / 1000
  memory     the committed json's

The tables are read with X53's and X54's rules (report/strm_table.py); a block's comb area and e_comb at W are the
point itself when the table has it, else its lanes rule (copy or interpolate), as char.json's model. W = 32 is left
out (outside the streamer grid's 16 channels). A field the gated tables cannot give yet (a point not measured) is
left empty and named.

The ungated set must give back the committed HWCOST json (printed per W; report/test_cg2_reprice.py checks it).
Writes results/cluster/<tech>/hwcost_cg.csv (point, W, tables, part, area_um2, energy_nj) and prints a Markdown
table per W (ungated, gated, gated / ungated), then at W = 8 the gated parts against dot3_w8_cg's run window
(energy.json's run and above-idle energy per part, breakdown.json's area per part). Standard library only.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import char_export as ce  # noqa: E402
import strm_table as st  # noqa: E402

ROOT = st.ROOT
PARTS = ("datapath", "control", "streamers", "crossbar", "memory")
WS = (2, 4, 8, 16)
N, DEPTH, LOOPS, OUT_BITS, CTRL_BITS = 2048, 8, 1, 64, 67
MUL = ("ElementwiseLanes", {"inTypes": ["int64", "int64"], "opType": "int64", "outType": "int64", "op": "mul"})
TREE = ("TreeAccumulate", {"inType": "int64", "outType": "int64", "op": "add"})
COLUMNS = ["point", "W", "tables", "part", "area_um2", "energy_nj"]
SETS = {"ungated": ("streamer.csv", "xbar.csv", "char.json"), "gated": ("streamer_cg.csv", "xbar_cg.csv", "char_cg.json")}


class Tables:
    """One table set: the reader and crossbar tables, the xbar factors and the char model."""

    def __init__(self, tech: str, name: str):
        s, x, c = SETS[name]
        strm = ROOT / "results" / "strm" / tech
        self.name = name
        self.missing = [p.relative_to(ROOT).as_posix() for p in (strm / s, strm / x, ROOT / "results" / "char" / tech / c)
                        if not p.is_file()]
        if self.missing:
            return
        self.reader = st.load(strm / s, st.READER_AXES, ("area_um2", "e_beat_pj"))
        self.xbar = st.complete_xbar(st.load(strm / x, st.XBAR_AXES, ("area_um2", "e_access_pj"), st.XBAR_SCALES))
        self.kinds = json.loads((strm / "xbar_kinds.json").read_text())["factor"]
        self.char = json.loads((ROOT / "results" / "char" / tech / c).read_text())


def _at(t: st.Table, field: str, gaps: list[str], what: str, **q: float) -> float | None:
    try:
        return t.at(field, **q)
    except ValueError as e:
        gaps.append(f"{what}: {e}")
        return None


def _sum(*xs: float | None, scale: float = 1.0) -> float | None:
    return None if any(x is None for x in xs) else scale * sum(xs)


def comb_at(j: dict, datapath: str, params: dict) -> float:
    """comb_um2 at params' lanes: the point when char.json has it, else the entry's lanes rule (as e_comb_at)."""
    x = ce.entry_of(j, datapath, params)
    at = {q["lanes"]: q["comb_um2"] for q in x["points"] if q.get("depth") == params.get("depth")}
    w = params["lanes"]
    if w in at:
        return at[w]
    if x["lanes_rule"] == "copy":
        return w * at[1]
    lo, hi = max(v for v in at if v <= w), min(v for v in at if v >= w)
    return at[lo] + (at[hi] - at[lo]) * (w - lo) / (hi - lo)


def price(t: Tables, w: int, cost: dict) -> tuple[dict, list[str]]:
    """{part: (area_um2, energy_nj)} of dot3_w<w> on table set t, and the fields it could not price."""
    gaps: list[str] = []
    fires, c_acc = N // w, N // w + 1
    r = t.reader
    a_rd = _at(r, "area_um2", gaps, f"reader d{DEPTH}_l{LOOPS}_c{w}", depth=DEPTH, loops=LOOPS, channels=w)
    a_wr = _at(r, "area_um2", gaps, f"writer d{DEPTH}_l{LOOPS}_c1", depth=DEPTH, loops=LOOPS, channels=1)
    e_rd = _at(r, "e_beat_pj", gaps, f"reader d{DEPTH}_l{LOOPS}_c{w}", depth=DEPTH, loops=LOOPS, channels=w)
    e_wr = _at(r, "e_beat_pj", gaps, f"writer d{DEPTH}_l{LOOPS}_c1", depth=DEPTH, loops=LOOPS, channels=1)
    xb = cost["xbar"]
    n, b, k = xb["inputs"], xb["banks"], t.kinds
    a_tab = _at(t.xbar, "area_um2", gaps, f"xbar i{n}_b{b}", inputs=n, banks=b)
    e_acc = _at(t.xbar, "e_access_pj", gaps, f"xbar i{b}_b{b}", inputs=b, banks=b)
    j = t.char
    mul, tree = {**MUL[1], "lanes": w}, {**TREE[1], "lanes": w}
    a_flop = j["flop"]["area_um2"]
    parts = {
        "streamers": (_sum(a_rd, a_rd, a_wr), None if e_rd is None or e_wr is None else (2 * fires * e_rd + e_wr) / 1000),
        "crossbar": (None if a_tab is None else
                     a_tab * (1 - k["f_ro"] * xb["read_only"] / n - k["f_wo"] * xb["write_only"] / n),
                     None if e_acc is None else xb["accesses"] * e_acc / 1000),
        "datapath": (comb_at(j, MUL[0], mul) + comb_at(j, TREE[0], tree) + OUT_BITS * a_flop,
                     (ce.e_unit(j, MUL[0], mul, fires, c_acc) + ce.e_unit(j, TREE[0], tree, fires, c_acc)) / 1000),
        "control": (2 * CTRL_BITS * a_flop, ce.e_ctrl(j, CTRL_BITS, c_acc) / 1000),
        "memory": (cost["parts"]["memory"]["area"], cost["parts"]["memory"]["energy"]),
    }
    return parts, gaps


def hwcost(tech: str, w: int) -> dict:
    return json.loads((ROOT / "results" / "cluster" / tech / "hwcost" / f"dot3_w{w}.json").read_text())["cost"]


def run(tech: str) -> tuple[list[dict], dict, dict]:
    """(the CSV rows, {(set, W): parts}, {(set, W): gaps}) for the table sets that exist."""
    rows, priced, gaps = [], {}, {}
    for name in SETS:
        t = Tables(tech, name)
        if t.missing:
            print(f"{name}: no {', '.join(t.missing)}; not priced")
            continue
        for w in WS:
            parts, g = price(t, w, hwcost(tech, w))
            priced[(name, w)], gaps[(name, w)] = parts, g
            for p in PARTS:
                a, e = parts[p]
                rows.append({"point": f"dot3_w{w}", "W": w, "tables": name, "part": p,
                             "area_um2": "" if a is None else f"{a:.6f}", "energy_nj": "" if e is None else f"{e:.9f}"})
    return rows, priced, gaps


def _v(x: float | None, nd: int) -> str:
    return "" if x is None else f"{x:,.{nd}f}"


def _r(a: float | None, b: float | None) -> str:
    return "" if a is None or not b else f"{a / b:.3f}"


def report(tech: str, priced: dict, gaps: dict) -> list[str]:
    out = []
    for w in WS:
        if ("ungated", w) in priced:
            cost = hwcost(tech, w)
            worst = max(abs(priced[("ungated", w)][p][i] / cost["parts"][p][k] - 1)
                        for p in PARTS for i, k in ((0, "area"), (1, "energy")))
            out.append(f"dot3_w{w}: the ungated set against the committed HWCOST json, worst |ratio - 1| {worst:.2e}")
    for w in WS:
        if ("gated", w) not in priced:
            continue
        u, g = priced[("ungated", w)], priced[("gated", w)]
        out += ["", f"dot3_w{w}", "", "| part | area ungated | area gated | ratio | energy ungated nJ | energy gated nJ | ratio |",
                "|---|---:|---:|---:|---:|---:|---:|"]
        for p in PARTS:
            out.append(f"| {p} | {_v(u[p][0], 0)} | {_v(g[p][0], 0)} | {_r(g[p][0], u[p][0])} | {_v(u[p][1], 2)} | "
                       f"{_v(g[p][1], 2)} | {_r(g[p][1], u[p][1])} |")
        for x in gaps[("gated", w)]:
            out.append(f"- not priced: {x}")
    if ("gated", 8) in priced:
        out += vs_cluster(tech, priced[("gated", 8)])
    return out


def vs_cluster(tech: str, g: dict) -> list[str]:
    """The gated parts at W = 8 against dot3_w8_cg's run window and area (energy.json, breakdown.json)."""
    res = ROOT / "results" / "cluster" / tech
    try:
        en = {x["part"]: x for x in json.loads((res / "energy.json").read_text())["dot3_w8_cg"]["hwcost"]["parts"]}
        ar = {x["part"]: x for x in json.loads((res / "breakdown.json").read_text())["dot3_w8_cg"]["hwcost"]["parts"]}
    except (OSError, KeyError) as e:
        return ["", f"no dot3_w8_cg in energy.json or breakdown.json ({e})"]
    out = ["", "dot3_w8_cg: the gated HWCOST against the gated cluster's run window (energy) and area", "",
           "| part | HWCOST gated nJ | run nJ | above idle nJ | HWCOST / run | HWCOST gated um2 | cluster um2 | HWCOST / cluster |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    tot = [0.0, 0.0, 0.0, 0.0, 0.0]
    for p in PARTS:
        a, e = g[p]
        run_nj, above, cl = en[p]["run_nj"], en[p]["above_idle_nj"], ar[p]["cluster_um2"]
        out.append(f"| {p} | {_v(e, 2)} | {run_nj:.2f} | {above:.2f} | {_r(e, run_nj)} | {_v(a, 0)} | {cl:,.0f} | {_r(a, cl)} |")
        for i, x in enumerate((e, run_nj, above, a, cl)):
            tot[i] = tot[i] + x if x is not None and tot[i] is not None else None
    out.append(f"| five parts | {_v(tot[0], 2)} | {tot[1]:.2f} | {tot[2]:.2f} | {_r(tot[0], tot[1])} | {_v(tot[3], 0)} | "
               f"{tot[4]:,.0f} | {_r(tot[3], tot[4])} |")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    args = ap.parse_args()
    rows, priced, gaps = run(args.tech)
    path = ROOT / "results" / "cluster" / args.tech / "hwcost_cg.csv"
    st.write(rows, path, COLUMNS)
    print(f"wrote {path.relative_to(ROOT)}: {len(rows)} rows")
    print("\n".join(report(args.tech, priced, gaps)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
