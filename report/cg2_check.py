#!/usr/bin/env python3
"""report/cg2_check.py - CG2's look at the clock-gated block runs, as Markdown for the run notes (X82: none a gate).

  pixi run cg2-check inventory [--all]   the RTL zips the gated runs need, against the ungated rows' commits
  pixi run cg2-check pairs               each gated row beside its ungated row: provenance, area, cells, gating, power
  pixi run cg2-check mix                 the xbar_mix factor check at i36_b32 (topic 1's 1 % rule)

The points are CG2's probe (R2), or with --all every point of the four sources (R3): the streamer grid (168
readers) and the xbar grid (27) of strm/grid.json, xbar_mix's two i36_b32 points, the 27 of char/points.json.

inventory: per point, its zip (rtl/streamer/, rtl/xbar/, rtl/xbar_mix/, rtl/char/) and the commit its point.json
records (snax_cluster_commit; char: snax_forge_commit) against the ungated synthesis row's. A point with no zip or
another commit is listed: a strm point is rebuilt (pixi run strm-rtl --only, snax_cluster at grid.json's commit),
a char point stops the round (CG2 topic 2).

pairs: per source, every clock-gated synthesis row (clk_gate 1) beside the ungated row of its point: the same
commit, top, params, lib_md5 and dc_version (or what differs), the area and comb area ratios, seq_cells (and the
RTL's bits for streamer and xbar), clock_gating.rpt's elements, gated and ungated registers (the report zip's), and
the power rows: streamer cycles, fill, stalls and beats, xbar cycles and grants, char each window's cycles and
fires, each equal to the ungated row's or not, and the energy ratio (e_beat, e_access, e_dyn per window).

mix: the area of i36_b32_r32_w1 (32 read-only, 1 write-only of 36 inputs) over i36_b32_r0_w0 (all read-write),
ungated and gated, against xbar_kinds.json's factor form 1 - f_ro 32/36 - f_wo 1/36: if the gated ratio is within 1 %
of the ungated one, f_ro and f_wo carry over (X83); else all 30 xbar_mix points are run gated (R3).
Standard library and arc/arc.py only.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from arc import arc  # noqa: E402

TECH = "nangate45"
RES = ROOT / "results"
SOURCES = ("streamer", "xbar", "xbar_mix", "char")
PROBE = {"streamer": ["d8_l1_c1", "d8_l1_c2", "d8_l1_c4", "d8_l1_c8", "d8_l1_c16", "d8_l2_c4",
                      "d2_l1_c1", "d2_l7_c16", "d16_l1_c1", "d16_l7_c16"],
         "xbar": ["i16_b32", "i32_b32", "i64_b64"],
         "xbar_mix": ["i36_b32_r0_w0", "i36_b32_r32_w1"]}
COMMIT = {"streamer": "snax_cluster_commit", "xbar": "snax_cluster_commit", "xbar_mix": "snax_cluster_commit",
          "char": "snax_forge_commit"}
PARAMS = {"streamer": ("depth", "loops", "channels"), "xbar": ("inputs", "banks"),
          "xbar_mix": ("inputs", "banks", "ro", "wo"), "char": ("datapath", "lanes", "depth", "op")}
SAME = ("top", "lib_md5", "dc_version")
CG_SUMMARY = {"elements": r"Number of Clock gating elements\s*\|\s*(\d+)",
              "gated": r"Number of Gated registers\s*\|\s*(\d+)",
              "ungated": r"Number of Ungated registers\s*\|\s*(\d+)"}
MIX = ("i36_b32_r0_w0", "i36_b32_r32_w1", 36, 32, 1)


def gate(r: dict) -> str:
    return "1" if str(r.get("clk_gate", "")) == "1" else "0"


def synth_csv(source: str) -> Path:
    return RES / source / TECH / ("char_synth.csv" if source == "char" else "synth_dc.csv")


def power_csv(source: str) -> Path:
    return RES / source / TECH / ("char_power.csv" if source == "char" else "power_pt.csv")


def rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def all_points(source: str) -> list[str]:
    if source == "char":
        return [p["point"] for p in json.loads((ROOT / "char" / "points.json").read_text())]
    if source == "xbar_mix":
        return PROBE["xbar_mix"]
    g = json.loads((ROOT / "strm" / "grid.json").read_text())[source]
    ax = g["axes"]
    return [g["name"].format(**dict(zip(ax, v))) for v in itertools.product(*ax.values())]


def points(source: str, everything: bool) -> list[str]:
    return all_points(source) if everything or source == "char" else PROBE[source]


def table(head: list[str], body: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(x) for x in r) + " |" for r in body])


# ---------------------------------------------------------------- inventory
def inventory(everything: bool) -> list[str]:
    out = []
    for source in SOURCES:
        un = {r["point"]: r for r in rows(synth_csv(source)) if gate(r) == "0"}
        missing, other, ok = [], [], 0
        for p in points(source, everything):
            z = ROOT / "rtl" / source / f"{p}.zip"
            if not z.is_file() or not arc.has(z, "point.json"):
                missing.append(p)
                continue
            got = json.loads(arc.read_text(z, "point.json")).get(COMMIT[source], "")
            want = un.get(p, {}).get(COMMIT[source], "")
            if got != want:
                other.append(f"{p} ({got[:12] or '?'}, the ungated row's {want[:12] or 'none'})")
            else:
                ok += 1
        n = len(points(source, everything))
        out.append(f"- {source}: {n} points, {ok} zips at the ungated rows' commit, {len(missing)} missing, "
                   f"{len(other)} at another commit")
        if missing:
            out.append(f"  - missing: {', '.join(missing)}")
        if other:
            out.append(f"  - another commit: {', '.join(other)}")
    return out


# ---------------------------------------------------------------- pairs
def cg_summary(source: str, point: str) -> dict:
    """clock_gating.rpt's summary from the gated run's committed report zip ({} when not there)."""
    z = RES / source / TECH / "reports" / f"{point}_cg.zip"
    if not z.is_file() or not arc.has(z, "clock_gating.rpt"):
        return {}
    text = arc.read_text(z, "clock_gating.rpt")
    return {k: int(m.group(1)) for k, rx in CG_SUMMARY.items() if (m := re.search(rx, text))}


def _ratio(a: str, b: str) -> str:
    try:
        return f"{float(a) / float(b):.3f}"
    except (TypeError, ValueError, ZeroDivisionError):
        return ""


def synth_pairs(source: str) -> tuple[list[str], int]:
    all_rows = rows(synth_csv(source))
    un = {r["point"]: r for r in all_rows if gate(r) == "0"}
    cg = [r for r in all_rows if gate(r) == "1"]
    body = []
    for g in sorted(cg, key=lambda r: r["point"]):
        u = un.get(g["point"], {})
        diff = [k for k in (COMMIT[source], *SAME, *PARAMS[source]) if k in g and g.get(k) != u.get(k)]
        s = cg_summary(source, g["point"])
        bits = g.get("rtl_flop_bits", "")
        body.append([g["point"], g["status"], ", ".join(diff) or "same", _ratio(g["area_um2"], u.get("area_um2")),
                     _ratio(g["comb_area_um2"], u.get("comb_area_um2")), f"{u.get('seq_cells', '')} → {g['seq_cells']}",
                     bits, s.get("elements", ""), s.get("gated", ""), s.get("ungated", ""), g["slack_ns"]])
    head = ["point", "status", "provenance", "area", "comb", "seq_cells", "RTL bits", "ICGs", "gated regs",
            "ungated regs", "slack ns"]
    return ([f"{source} synthesis, gated against ungated (ratios gated / ungated):", "", table(head, body)]
            if body else [f"{source} synthesis: no gated rows"]), len(body)


def power_pairs(source: str) -> list[str]:
    if source == "xbar_mix":
        return []                                                   # area only (X70)
    all_rows = rows(power_csv(source))
    key = (lambda r: (r["point"], r["window"])) if source == "char" else (lambda r: (r["point"],))
    un = {key(r): r for r in all_rows if gate(r) == "0"}
    cg = [r for r in all_rows if gate(r) == "1"]
    same = {"streamer": ("cycles", "fill", "stalls", "beats"), "xbar": ("cycles", "grants"),
            "char": ("cycles", "fires")}[source]
    e = {"streamer": "e_beat_pj", "xbar": "e_access_pj", "char": "e_dyn_pj"}[source]
    body = []
    for g in sorted(cg, key=key):
        u = un.get(key(g), {})
        diff = [f"{k} {u.get(k, '?')} → {g.get(k)}" for k in same if str(g.get(k)) != str(u.get(k))]
        body.append([" ".join(key(g)), g["status"], "; ".join(diff) or "equal", _ratio(g[e], u.get(e)),
                     g.get("annotated", "")])
    if not body:
        return [f"{source} power: no gated rows"]
    return [f"{source} power, gated against ungated:", "",
            table(["point", "status", ", ".join(same), f"{e} gated / ungated", "annotated"], body)]


def pairs() -> list[str]:
    out = []
    for source in SOURCES:
        s, _ = synth_pairs(source)
        out += ["", *s]
        p = power_pairs(source)
        if p:
            out += ["", *p]
    return out


# ---------------------------------------------------------------- mix
def mix() -> list[str]:
    rw, mixed, n, ro, wo = MIX
    k = json.loads((RES / "strm" / TECH / "xbar_kinds.json").read_text())["factor"]
    model = 1 - k["f_ro"] * ro / n - k["f_wo"] * wo / n
    by = {(r["point"], gate(r)): float(r["area_um2"]) for r in rows(synth_csv("xbar_mix"))
          if r["status"].startswith("ok") and r["area_um2"]}
    out = [f"xbar_mix at i36_b32: area({mixed}) / area({rw}); the factor form gives {model:.4f}"]
    got = {}
    for g, name in (("0", "ungated"), ("1", "gated")):
        if (rw, g) in by and (mixed, g) in by:
            got[g] = by[(mixed, g)] / by[(rw, g)]
            out.append(f"- {name}: {by[(mixed, g)]:,.1f} / {by[(rw, g)]:,.1f} = {got[g]:.4f} "
                       f"(the factor form {100 * (model / got[g] - 1):+.2f} %)")
        else:
            out.append(f"- {name}: not both points")
    if len(got) == 2:
        d = 100 * (got["1"] / got["0"] - 1)
        out.append(f"- gated against ungated: {d:+.2f} %: " + ("within 1 %, f_ro and f_wo carry over (X83)"
                                                                  if abs(d) <= 1 else "beyond 1 %: all 30 gated in R3"))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("inventory", "pairs", "mix"))
    ap.add_argument("--all", action="store_true", help="inventory: every point (R3), not the probe")
    args = ap.parse_args()
    out = {"inventory": lambda: inventory(args.all), "pairs": pairs, "mix": mix}[args.what]()
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
