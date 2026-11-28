#!/usr/bin/env python3
"""report/refusal_fit.py - a refused request's price from the streamer and interconnect blocks alone (X116).

    pixi run refusal-fit [--tech nangate45] [--md]

Per point of the grant grid (results/streamer/, xbar/, xbar_mix/: power_pt.csv, gated, seed 0) with its idle and
refused runs (power_pt_idle.csv, power_pt_refused.csv, `pwr run --mode`): the refused run's energy less the grant
run's and the extra cycles at the idle run's energy a cycle, over its refused request-cycles, as a fraction of a
granted request's price (a reader's beat over its channels, an interconnect access):

    r = (E_ref - E_grant - (C_ref - C_grant) e_idle) / (R e_grant)

Per set the mean, range and the means by each axis; `within` says whether every point is within SPREAD of its
set's mean. r_strm is the streamer mean, r_xbar the mean of xbar and xbar_mix together, both clamped at 0 as X111's.
Beside it, the idle energy a cycle against model_fit.json's floor for the same block (k_s (1 + channels) for a
reader, a_x + b_x inputs for an interconnect), a check only.

The interconnect's refusals alone (`ab`): its refused runs against the apart runs with the same grants, cycles and
request fields (power_pt_refused.csv against power_pt_apart.csv at 2 inputs a bank, the _g4 files at 4). At 2 every
refused request waits one cycle; at 4 they wait 1 to 3. With F the first refused cycles and R all of them:

    E_ref - E_apart = e_first F + e_more (R - F),   e_first = (E_ref - E_apart) / R at 2

Writes results/strm/<tech>/refusal.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS = {"streamer": ("depth", "loops", "channels"), "xbar": ("inputs", "banks"),
        "xbar_mix": ("inputs", "banks", "ro", "wo")}
SPREAD = 0.20  # a set's points all within this of its mean: one r for the set, else a table (X116)


def _rows(path: Path) -> dict[str, dict]:
    """The gated seed-0 rows with energy, by point."""
    if not path.is_file():
        return {}
    with path.open(newline="") as f:
        return {r["point"]: r for r in csv.DictReader(f)
                if r.get("clk_gate") == "1" and r.get("seed") == "0" and r.get("e_window_pj")
                and (r["status"] == "ok" or r["status"].endswith("(energy kept)"))}


def unit_pj(kind: str, g: dict) -> float:
    """A granted request's price: a reader lane's (its beat over its channels) or an interconnect access."""
    return float(g["e_beat_pj"]) / int(g["channels"]) if kind == "streamer" else float(g["e_access_pj"])


def point_fit(kind: str, g: dict, i: dict, r: dict) -> dict:
    e_g, c_g = float(g["e_window_pj"]), int(g["cycles"])
    e_r, c_r, n = float(r["e_window_pj"]), int(r["cycles"]), int(r["refused"])
    e_idle = float(i["e_cycle_pj"])
    x = (e_r - e_g - (c_r - c_g) * e_idle) / n
    u = unit_pj(kind, g)
    return {**{a: int(g[a]) for a in SETS[kind]}, "r": x / u, "x_pj": x, "unit_pj": u, "e_idle_pj": e_idle,
            "refused": n, "cycles_grant": c_g, "cycles_refused": c_r, "e_grant_pj": e_g, "e_refused_pj": e_r}


def summary(pts: dict[str, dict], axes: tuple[str, ...]) -> dict:
    rs = [p["r"] for p in pts.values()]
    if not rs:
        return {"n": 0}
    m = statistics.fmean(rs)
    by = {a: {str(v): statistics.fmean(p["r"] for p in pts.values() if p[a] == v)
              for v in sorted({p[a] for p in pts.values()})} for a in axes}
    return {"n": len(rs), "mean": m, "min": min(rs), "max": max(rs),
            "within": all(abs(x - m) <= SPREAD * abs(m) for x in rs), "by": by}


def floor_check(kind: str, pts: dict[str, dict], floor: dict) -> dict:
    """The idle run's energy a cycle over the cluster fit's floor for the same block."""
    out = {}
    for name, p in pts.items():
        f = (floor["streamers"]["k_pj"] * (1 + p["channels"]) if kind == "streamer"
             else floor["crossbar"]["a_pj"] + floor["crossbar"]["b_pj"] * p["inputs"])
        out[name] = p["e_idle_pj"] / f
    v = list(out.values())
    return {"mean": statistics.fmean(v), "min": min(v), "max": max(v)} if v else {}


def ab_point(g: dict, a2: dict, b2: dict, a4: dict, b4: dict) -> dict:
    """e_first and e_more of one interconnect point from its four runs (pJ, and over the granted access)."""
    r2, r4, f4 = int(a2["refused"]), int(a4["refused"]), int(a4["refused_first"])
    d2 = float(a2["e_window_pj"]) - float(b2["e_window_pj"])
    d4 = float(a4["e_window_pj"]) - float(b4["e_window_pj"])
    e_first = d2 / r2
    e_more = (d4 - e_first * f4) / (r4 - f4)
    u = float(g["e_access_pj"])
    return {"e_first_pj": e_first, "e_more_pj": e_more, "r_first": e_first / u, "r_more": e_more / u,
            "x2_pj": d2 / r2, "x4_pj": d4 / r4, "unit_pj": u, "refused": [r2, r4], "first": [r2, f4],
            "cycles_off": [int(a2["cycles"]) - int(b2["cycles"]), int(a4["cycles"]) - int(b4["cycles"])]}


def ab_fit(res: Path) -> dict:
    g = _rows(res / "power_pt.csv")
    runs = [_rows(res / f"power_pt_{m}.csv") for m in ("refused", "apart", "refused_g4", "apart_g4")]
    pts = {p: ab_point(g[p], *(r[p] for r in runs)) for p in sorted(g) if all(p in r for r in runs)}
    out: dict = {"points": pts, "n": len(pts)}
    for k in ("e_first_pj", "e_more_pj", "r_first", "r_more"):
        v = [q[k] for q in pts.values()]
        if v:
            out[k] = {"mean": statistics.fmean(v), "min": min(v), "max": max(v)}
    return out


def fit(tech: str) -> dict:
    floor = json.loads((ROOT / "results" / "cluster" / tech / "model_fit.json").read_text())["floor"]
    out: dict = {"tech": tech, "spread": SPREAD, "sets": {}, "missing": {}}
    for kind, axes in SETS.items():
        res = ROOT / "results" / kind / tech
        g, i, r = (_rows(res / f) for f in ("power_pt.csv", "power_pt_idle.csv", "power_pt_refused.csv"))
        pts = {p: point_fit(kind, g[p], i[p], r[p]) for p in sorted(g) if p in i and p in r and int(r[p]["refused"])}
        out["missing"][kind] = sorted(set(g) - set(pts))
        out["sets"][kind] = {"points": pts, **summary(pts, axes), "idle_over_floor": floor_check(kind, pts, floor)}
    xs = [p["r"] for k in ("xbar", "xbar_mix") for p in out["sets"][k]["points"].values()]
    s = out["sets"]["streamer"]
    out["ab"] = {k: ab_fit(ROOT / "results" / k / tech) for k in ("xbar", "xbar_mix")}
    out["r_strm"] = max(s["mean"], 0.0) if s["n"] else None
    out["r_xbar"] = max(statistics.fmean(xs), 0.0) if xs else None
    return out


def markdown(f: dict) -> str:
    L = ["| set | points | mean r | min | max | all within ±20 % | idle / floor (mean, range) |", "|---|---:|---:|---:|---:|---|---|"]
    for k, s in f["sets"].items():
        if not s["n"]:
            L.append(f"| {k} | 0 | – | – | – | – | – |")
            continue
        fl = s["idle_over_floor"]
        L.append(f"| {k} | {s['n']} | {s['mean']:.4f} | {s['min']:.4f} | {s['max']:.4f} | {'yes' if s['within'] else 'no'}"
                 f" | {fl['mean']:.2f} ({fl['min']:.2f}–{fl['max']:.2f}) |")
    L += ["", f"r_strm = {f['r_strm']}, r_xbar = {f['r_xbar']} (clamped at 0)", ""]
    for k, s in f["sets"].items():
        for a, vals in s.get("by", {}).items():
            L += [f"| {k} by {a} | " + " | ".join(vals) + " |", "|---|" + "---:|" * len(vals),
                  "| mean r | " + " | ".join(f"{v:.4f}" for v in vals.values()) + " |", ""]
    ab = {k: a for k, a in f.get("ab", {}).items() if a["n"]}
    if ab:
        L += ["| interconnect, refused − apart | points | e_first pJ (range) | e_more pJ (range) | r_first | r_more |",
              "|---|---:|---|---|---:|---:|"]
        for k, a in ab.items():
            ef, em = a["e_first_pj"], a["e_more_pj"]
            L.append(f"| {k} | {a['n']} | {ef['mean']:.3f} ({ef['min']:.3f}–{ef['max']:.3f}) | {em['mean']:.3f} "
                     f"({em['min']:.3f}–{em['max']:.3f}) | {a['r_first']['mean']:.4f} | {a['r_more']['mean']:.4f} |")
        L.append("")
    miss = {k: v for k, v in f["missing"].items() if v}
    if miss:
        L.append("Missing (no idle or refused run): " + "; ".join(f"{k} {len(v)}: {', '.join(v[:6])}"
                                                                   for k, v in miss.items()))
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(prog="pixi run refusal-fit")
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="print the tables")
    a = ap.parse_args()
    f = fit(a.tech)
    out = ROOT / "results" / "strm" / a.tech / "refusal.json"
    out.write_text(json.dumps(f, indent=1, sort_keys=True) + "\n")
    print(f"{out.relative_to(ROOT)}: r_strm {f['r_strm']}, r_xbar {f['r_xbar']}")
    if a.md:
        print(markdown(f))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
