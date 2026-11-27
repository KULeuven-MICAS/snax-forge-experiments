#!/usr/bin/env python3
"""report/tier_check.py - tier A's designs at three levels: the graph's estimate, SNAX-GVSoC and the netlist.

    pixi run tier-check [--tech nangate45] [--md]

For every point of cluster/points.json whose id is a row of snax-forge's paper/data/{forms,limits}.csv (read through
SNAX_FORGE, default ../snax-forge), over the program window (the quiet build's windows from the first mark to the
check's): cycles; area in the eight parts (groups.json's `parts`; a point with `netlist_of` takes its twin's);
dynamic energy in the six parts the graph prices and in the core and the rest; leakage apart (X106). Per kernel, the
order of its designs at each level in four metrics (cycles, dynamic, dynamic + the design's leakage, + the fixed
cluster) and area: top-1 and Kendall's tau-a per pair of levels, a pair within TIE_PCT tied; pooled over every
design too. "Where they differ" lists every cycle gap over GAP_PCT between levels (spans and windows) and every pair
two levels order oppositely.
Writes results/cluster/<tech>/tier_check.json; --md prints the tables. Standard library and arc/arc.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = ROOT / "cluster" / "groups.json"
POINTS = ROOT / "cluster" / "points.json"
FORGE = Path(os.environ.get("SNAX_FORGE", ROOT.parent / "snax-forge")).resolve()
DYN = ("datapath", "control", "streamers", "crossbar", "memory", "dma")    # the graph's six energy parts
AREA = (*DYN, "core", "rest")
LEVELS = ("estimate", "gvsoc", "netlist")
METRICS = ("cycles", "dynamic", "dynamic_leak", "total", "area")
TIE_PCT = 1.0
GAP_PCT = 20.0


def paper_rows() -> dict[str, dict]:
    out = {}
    for s in ("forms", "limits"):
        p = FORGE / "paper" / "data" / f"{s}.csv"
        if p.is_file():
            with p.open(newline="") as fh:
                out.update({r["id"]: r for r in csv.DictReader(fh)})
    return out


def kernel_of(pid: str) -> str:
    return pid.split("_")[0]


def gvsoc_side(ge: dict, marks: set[int]) -> dict:
    """SNAX-GVSoC's energy run over the netlist's windows: cycles, the six parts' dynamic energy, the background."""
    ws = [w for w in ge["windows"] if w["mark"] in marks]
    dyn = {k: sum(w["energy"]["parts"].get(k, 0.0) for w in ws) for k in DYN}
    bg = {k: sum(w["background"][k] for w in ws) for k in ("leak_design", "leak_core", "leak_rest", "idle")}
    return {"cycles": sum(w["cycles"] for w in ws), "windows": {w["mark"]: w["cycles"] for w in ws},
            "dyn_nj": dyn, "background_nj": bg, "background_rates": ge["background"]}


def netlist_side(en: dict, br: dict, parts: dict[str, list[str]]) -> dict:
    """The netlist's windows: cycles, per part dynamic energy and leakage (nJ over the windows, µW cycle-weighted),
    area per part."""
    wins = en["windows"]
    cyc = sum(w["cycles"] for w in wins)
    dyn = {p: sum(sum(w["groups"][g] for g in gs) * w["cycles"] / 1e3 for w in wins) for p, gs in parts.items()}
    leak = {p: sum(sum(w["leak_uw"][g] for g in gs) * w["cycles"] * w["clock_ns"] * 1e-6 for w in wins)
            for p, gs in parts.items()}
    leak_uw = {p: sum(sum(w["leak_uw"][g] for g in gs) * w["cycles"] for w in wins) / cyc for p, gs in parts.items()}
    areas = {g["name"]: g["area_um2"] for g in br["groups"]}
    return {"cycles": cyc, "windows": {w["mark"]: w["cycles"] for w in wins},
            "kinds": {w["mark"]: (w["kind"], w["label"]) for w in wins},
            "dyn_nj": dyn, "leak_nj": leak, "leak_uw": leak_uw,
            "area_um2": {p: sum(areas[g] for g in gs) for p, gs in parts.items()}}


def estimate_side(r: dict, rates: dict) -> dict:
    """The graph's static estimate (paper/ CSV), its leakage over its own cycles and the fixed cluster's at the
    energy run's rates (core and rest leakage, idle floor)."""
    c = int(r["est_cycles"])
    t = float(rates["clock_ns"])
    return {"cycles": c,
            "dyn_nj": {k: float(r[f"static_{k}_nj"]) for k in DYN},
            "leak_uw": float(r["leak_uw"]), "leak_nj": float(r["static_leak_nj"]),
            "leak_part_uw": {k: float(r[f"leak_{k}_uw"]) for k in AREA if r.get(f"leak_{k}_uw")},
            "fixed_nj": (rates["core_uw"] + rates["rest_uw"]) * c * t * 1e-6 + rates["idle_pj_cycle"] * c / 1e3,
            "area_um2": {k: float(r[f"area_{k}_um2"]) for k in AREA}}


def metrics(e: dict, g: dict, n: dict) -> dict[str, dict[str, float]]:
    """Each metric at each level: COST2's views at the program window (A dynamic, C + the design's leakage, D + the
    fixed cluster), the cycles and the whole area."""
    est = {"cycles": e["cycles"], "dynamic": sum(e["dyn_nj"].values())}
    est["dynamic_leak"] = est["dynamic"] + e["leak_nj"]
    est["total"] = est["dynamic_leak"] + e["fixed_nj"]
    est["area"] = sum(e["area_um2"].values())
    gv = {"cycles": g["cycles"], "dynamic": sum(g["dyn_nj"].values())}
    b = g["background_nj"]
    gv["dynamic_leak"] = gv["dynamic"] + b["leak_design"]
    gv["total"] = gv["dynamic_leak"] + b["leak_core"] + b["leak_rest"] + b["idle"]
    gv["area"] = None
    nl = {"cycles": n["cycles"], "dynamic": sum(n["dyn_nj"][k] for k in DYN)}
    nl["dynamic_leak"] = nl["dynamic"] + sum(n["leak_nj"][k] for k in DYN)
    nl["total"] = nl["dynamic_leak"] + sum(n["dyn_nj"][k] + n["leak_nj"][k] for k in ("core", "rest"))
    nl["area"] = sum(n["area_um2"].values())
    return {"estimate": est, "gvsoc": gv, "netlist": nl}


def _sign(a: float, b: float) -> int:
    if abs(a - b) <= TIE_PCT / 100 * max(abs(a), abs(b)):
        return 0
    return 1 if a > b else -1


def kendall(xs: list[float], ys: list[float]) -> tuple[float | None, list[tuple[int, int]]]:
    """tau-a over the pairs, a pair within TIE_PCT at either level neither concordant nor discordant; and the
    discordant pairs (indices)."""
    pairs = list(combinations(range(len(xs)), 2))
    if not pairs:
        return None, []
    nc = nd = 0
    disc = []
    for i, j in pairs:
        s = _sign(xs[i], xs[j]) * _sign(ys[i], ys[j])
        nc += s > 0
        if s < 0:
            nd += 1
            disc.append((i, j))
    return (nc - nd) / len(pairs), disc


def best(xs: list[float]) -> list[int]:
    """The design(s) within TIE_PCT of the lowest."""
    lo = min(xs)
    return [i for i, x in enumerate(xs) if _sign(x, lo) == 0]


def order(rows: list[dict]) -> dict:
    """Per metric: each level's values, top-1 (the lowest, ties kept) and tau-a per pair of levels."""
    out = {}
    names = [r["id"] for r in rows]
    for m in METRICS:
        vals = {lv: [r["metrics"][lv][m] for r in rows] for lv in LEVELS}
        have = [lv for lv in LEVELS if all(v is not None for v in vals[lv])]
        top = {lv: [names[i] for i in best(vals[lv])] for lv in have}
        taus = {}
        for a, b in combinations(have, 2):
            t, disc = kendall(vals[a], vals[b])
            taus[f"{a}-{b}"] = {"tau": t, "discordant": [(names[i], names[j]) for i, j in disc]}
        same = len({tuple(sorted(v)) for v in top.values()}) == 1 or all(
            set(top["netlist"]) & set(v) for v in top.values()) if "netlist" in top else None
        out[m] = {"top": top, "top_agrees": same, "tau": taus}
    return out


def gaps(rows: list[dict]) -> list[dict]:
    """Every cycle gap over GAP_PCT: the span of each level against the netlist's, and each window SNAX-GVSoC
    against the netlist (the RTL's cycles, X108)."""
    out = []
    for r in rows:
        n = r["netlist"]["cycles"]
        for lv in ("estimate", "gvsoc"):
            c = r[lv]["cycles"]
            pct = 100 * (c - n) / n
            if abs(pct) > GAP_PCT:
                out.append({"id": r["id"], "where": f"span, {lv}", "level": c, "netlist": n, "pct": round(pct, 1)})
        for mark, c_nl in r["netlist"]["windows"].items():
            c_gv = r["gvsoc"]["windows"].get(mark)
            if c_gv is None:
                continue
            pct = 100 * (c_gv - c_nl) / c_nl if c_nl else 0.0
            if abs(pct) > GAP_PCT and max(c_gv, c_nl) > 20:
                kind, label = r["netlist"]["kinds"][mark]
                out.append({"id": r["id"], "where": f"window {mark} {kind} ({label})", "level": c_gv,
                            "netlist": c_nl, "pct": round(pct, 1)})
    return out


def check(tech: str) -> dict:
    cfg = json.loads(GROUPS.read_text())
    parts = cfg["parts"]
    points = json.loads(POINTS.read_text())["points"]
    res = ROOT / "results" / "cluster" / tech
    br, en = json.loads((res / "breakdown.json").read_text()), json.loads((res / "energy.json").read_text())
    paper = paper_rows()
    rows, missing = [], []
    for p in points:
        name = p["point"]
        pid = name.removesuffix("_cg")
        if pid not in paper:
            continue
        ge_path = res / "ge" / f"{name}.json"
        area = br.get(name) or br.get(p.get("netlist_of", ""))  # an adopted netlist's area is its twin's
        if name not in en or area is None or not ge_path.is_file():
            missing.append(name)
            continue
        ge = json.loads(ge_path.read_text())
        n = netlist_side(en[name], area, parts)
        g = gvsoc_side(ge, set(n["windows"]))
        e = estimate_side(paper[pid], ge["background"])
        rows.append({"id": pid, "point": name, "kernel": kernel_of(pid), "estimate": e, "gvsoc": g, "netlist": n,
                     "metrics": metrics(e, g, n),
                     "paper_cycles": int(paper[pid]["cycles"]), "paper_dynamic_nj": float(paper[pid]["dynamic_nj"])})
    kernels = {}
    for k in dict.fromkeys(r["kernel"] for r in rows):
        kernels[k] = order([r for r in rows if r["kernel"] == k])
    return {"tech": tech, "snax_forge": str(FORGE), "tie_pct": TIE_PCT, "gap_pct": GAP_PCT, "missing": missing,
            "points": rows, "kernels": kernels, "pooled": order(rows), "gaps": gaps(rows)}


def _n(x: float | None, nd: int = 1) -> str:
    return "–" if x is None else f"{x:,.{nd}f}"


def _r(a: float | None, b: float | None) -> str:
    return "–" if a is None or not b else f"{a / b:.2f}"


def markdown(j: dict) -> str:
    L = ["## Per design, over the program window", "",
         "| design | cycles est / GVSoC / netlist | dynamic nJ est / GVSoC / netlist | + design leakage | + fixed cluster "
         "| area mm² est / netlist |", "|---|---|---|---|---|---|"]
    for r in j["points"]:
        m = r["metrics"]
        L.append(f"| `{r['id']}` | {m['estimate']['cycles']} / {m['gvsoc']['cycles']} / {m['netlist']['cycles']} | "
                 + " | ".join(" / ".join(_n(m[lv][k]) for lv in LEVELS) for k in ("dynamic", "dynamic_leak", "total"))
                 + f" | {m['estimate']['area'] / 1e6:.3f} / {m['netlist']['area'] / 1e6:.3f} |")
    L += ["", "## Per part, over the program window (ratio to the netlist)", "",
          "| design | " + " | ".join(DYN) + " | core dyn | rest dyn |", "|---|" + "---|" * (len(DYN) + 2)]
    for r in j["points"]:
        e, g, n = r["estimate"]["dyn_nj"], r["gvsoc"]["dyn_nj"], r["netlist"]["dyn_nj"]
        cells = [f"{_n(n[k], 2)} ({_r(e[k], n[k])}, {_r(g[k], n[k])})" for k in DYN]
        L.append(f"| `{r['id']}` | " + " | ".join(cells) + f" | {_n(n['core'], 1)} | {_n(n['rest'], 1)} |")
    L += ["", "Each cell: the netlist's dynamic nJ (estimate / netlist, SNAX-GVSoC / netlist).", "",
          "## Leakage per part (µW, the netlist's cycle-weighted over the window; estimate / netlist)", "",
          "| design | " + " | ".join(AREA) + " | six parts |", "|---|" + "---|" * (len(AREA) + 1)]
    for r in j["points"]:
        u, e = r["netlist"]["leak_uw"], r["estimate"].get("leak_part_uw", {})
        six = sum(u[k] for k in DYN)
        L.append(f"| `{r['id']}` | " + " | ".join(f"{_n(u[k], 0)} ({_r(e.get(k), u[k])})" for k in AREA)
                 + f" | {_n(six, 0)} ({_r(r['estimate']['leak_uw'], six)}) |")
    L += ["", "## Area per part (µm², estimate / netlist)", "",
          "| design | " + " | ".join(AREA) + " |", "|---|" + "---|" * len(AREA)]
    for r in j["points"]:
        e, n = r["estimate"]["area_um2"], r["netlist"]["area_um2"]
        L.append(f"| `{r['id']}` | " + " | ".join(f"{_n(e[k], 0)} / {_n(n[k], 0)}" for k in AREA) + " |")
    L += ["", "## Order per kernel", "",
          "| kernel | metric | top-1 estimate | top-1 GVSoC | top-1 netlist | τ est–GVSoC | τ est–netlist | τ GVSoC–netlist |",
          "|---|---|---|---|---|---:|---:|---:|"]
    for k, o in [*j["kernels"].items(), ("pooled", j["pooled"])]:
        for m in METRICS:
            x = o[m]
            tops = [", ".join(f"`{t}`" for t in x["top"].get(lv, [])) or "–" for lv in LEVELS]
            ts = [x["tau"].get(p, {}).get("tau") for p in ("estimate-gvsoc", "estimate-netlist", "gvsoc-netlist")]
            L.append(f"| {k} | {m} | " + " | ".join(tops) + " | " + " | ".join(_n(t, 2) for t in ts) + " |")
    L += ["", "## Where they differ", "", "### Pairs ordered oppositely", ""]
    for k, o in j["kernels"].items():
        for m in METRICS:
            for pair, v in o[m]["tau"].items():
                for a, b in v["discordant"]:
                    L.append(f"- {k}, {m}, {pair}: `{a}` against `{b}`")
    L += ["", f"### Cycle gaps over {GAP_PCT:.0f} % (against the netlist)", "",
          "| design | where | level | netlist | gap |", "|---|---|---:|---:|---:|"]
    L += [f"| `{x['id']}` | {x['where']} | {x['level']} | {x['netlist']} | {x['pct']:+.1f} % |" for x in j["gaps"]]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args()
    j = check(a.tech)
    out = ROOT / "results" / "cluster" / a.tech / "tier_check.json"
    out.write_text(json.dumps(j, indent=1, default=list) + "\n")
    print(f"{out.relative_to(ROOT)}: {len(j['points'])} designs; missing {j['missing'] or 'none'}")
    if a.md:
        print(markdown(j))
    return 0


if __name__ == "__main__":
    sys.exit(main())
