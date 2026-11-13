#!/usr/bin/env python3
"""report/cluster_energy.py - a cluster's dynamic energy per program section in groups, the run phase against HWCOST.

    pixi run cluster-energy [--tech nangate45] [--md]
    pixi run cluster-energy-test                    report/test_cluster_energy.py

For every point of cluster/points.json that has PWR1's PrimePower reports (results/cluster/<tech>/power_reports/
<point>.zip, `pixi run cluster pwr` part 2, X74), reads each window's power_hierarchy.rpt and sums each node's own
dynamic power (internal + switching, its total minus its children's; leakage out, X13) into cluster/groups.json's
groups by X72's rules (report/cluster_breakdown.py's `groups`), so the groups add up to the top's dynamic power.
A window w of C_w cycles at t_clk (10 ns as the cuts read the run, X76) gives each group g

    E_g,w = (P_int + P_sw)_g,w * C_w * t_clk,    E_w = sum_g E_g,w,    E_span = sum_w E_w

over the span's windows (X73: the first mark to the end of the last DMA out). Then, where they exist:

  run     the run phase: each run window against the acc_config window before it (the idle reference, the same
          cluster with nothing moving but the clock): per group the energy per cycle in both, the run window's
          energy, and its part above idle, (e_run - e_idle) * C_run, which may be negative where the clock's
          booking moves (PITFALLS PT10's run note)
  hwcost  snax-forge's five energy parts (results/cluster/<tech>/hwcost/<point>.json, nJ per task) against the
          groups groups.json's `hwcost` maps them to, in the run window(s): the run's energy and its part above
          idle, each side's shares of its own five-part sum. HWCOST is an estimate with no bit-level switching;
          the shares are what is compared, not the absolute numbers
  alone   the accelerator's shell in the run window against its point measured alone (points.json's `alone`, a
          row of results/forge/<tech>/power_pt.csv, X23's busy window): energy and energy per cycle

Each window's top dynamic power must equal power_pt.csv's `e_dyn_pj` (the same report, PT's groups) within
0.01 %, or the point fails. Writes results/cluster/<tech>/energy.json; --md also prints the tables as Markdown.
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
sys.path.insert(0, str(ROOT / "arc"))
sys.path.insert(0, str(ROOT / "report"))
import arc  # noqa: E402
import cluster_breakdown as cb  # noqa: E402

GROUPS = ROOT / "cluster" / "groups.json"
POINTS = ROOT / "cluster" / "points.json"
PARTS = cb.PARTS
TOL_PCT = 0.01
_NUM = r"([-+0-9.eE]+)"
_ROW = re.compile(rf"^( *)(\S+)(?: \((\S+)\))?\s+{_NUM}\s+{_NUM}\s+{_NUM}\s+{_NUM}\s+(?:[-+0-9.eE]+|N/A)\s*$")


def parse_hierarchy(text: str) -> list[dict]:
    """PT's `report_power -hierarchy -nosplit`: path (the top as ''), design, dynamic power (W) as `total`, in order.

    Two spaces of indent per level; a name is followed by its design in brackets (the top's line is the design).
    `total` is internal + switching, leakage left out (X13), so cluster_breakdown's `own` and `groups` apply.
    """
    rows: list[dict] = []
    stack: list[tuple[int, str]] = []
    for ln in text.splitlines():
        m = _ROW.match(ln)
        if not m:
            continue
        depth = len(m.group(1)) // 2
        name, design = m.group(2), m.group(3) or m.group(2)
        if not rows and depth != 0:
            continue
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, name))
        path = "/".join(n for _, n in stack[1:])
        rows.append({"path": path, "design": design, "total": float(m.group(4)) + float(m.group(5)),
                     "int": float(m.group(4)), "sw": float(m.group(5))})
    return rows


def pj_per_cycle(watts: float, clock_ns: float) -> float:
    return watts * clock_ns * 1e3            # W * ns = nJ; * 1e3 = pJ


def share(x: float, total: float) -> float:
    return 100 * x / total if total else 0.0


def window_groups(rows: list[dict], cfg: dict, clock_ns: float) -> dict[str, float]:
    """pJ per cycle per group, in groups.json's order; they add up to the top's dynamic power."""
    return {k: pj_per_cycle(v, clock_ns) for k, v in cb.groups(rows, cfg).items()}


def idle_for(wins: list[dict], i: int) -> int | None:
    """The acc_config window last before window i, the run's idle reference."""
    return next((j for j in range(i - 1, -1, -1) if wins[j]["kind"] == "acc_config"), None)


def run_phase(wins: list[dict]) -> list[dict]:
    """Per run window: its groups, energy and part above its idle reference (nJ)."""
    out = []
    for i, w in enumerate(wins):
        if w["kind"] != "run":
            continue
        j = idle_for(wins, i)
        idle = wins[j] if j is not None else None
        c = w["cycles"]
        rows = [{"group": g, "run_pj_cycle": e, "idle_pj_cycle": idle["groups"][g] if idle else None,
                 "run_nj": e * c / 1e3,
                 "above_idle_nj": (e - idle["groups"][g]) * c / 1e3 if idle else None}
                for g, e in w["groups"].items()]
        out.append({"window": w["name"], "cycles": c, "idle_window": idle["name"] if idle else None, "groups": rows})
    return out


def hwcost_rows(cost: dict, runs: list[dict], cfg: dict) -> dict:
    """HWCOST's five energy parts (nJ per task) against the run windows' groups, each side's shares of its own sum."""
    hw = {k: cost["parts"][k]["energy"] for k in PARTS}
    run = {k: 0.0 for k in PARTS}
    above: dict[str, float | None] = {k: 0.0 for k in PARTS}
    for r in runs:
        by = {x["group"]: x for x in r["groups"]}
        for k in PARTS:
            run[k] += sum(by[g]["run_nj"] for g in cfg["hwcost"][k])
            vals = [by[g]["above_idle_nj"] for g in cfg["hwcost"][k]]
            above[k] = None if above[k] is None or any(v is None for v in vals) else above[k] + sum(vals)
    th, tr = sum(hw.values()), sum(run.values())
    ta = None if any(v is None for v in above.values()) else sum(above.values())
    rows = [{"part": k, "groups": cfg["hwcost"][k], "hwcost_nj": hw[k], "hwcost_share_pct": share(hw[k], th),
             "run_nj": run[k], "run_share_pct": share(run[k], tr),
             "above_idle_nj": above[k], "above_idle_share_pct": share(above[k], ta) if ta else None}
            for k in PARTS]
    return {"parts": rows, "hwcost_nj": th, "run_nj": tr, "above_idle_nj": ta}


def alone_row(rows: list[dict], cycles: int, clock_ns: float, alone: dict) -> dict:
    """The shell in the run window against the same point measured alone over X23's busy window."""
    shell = next(r for r in rows if cb.SHELL.fullmatch(r["path"]))
    e = pj_per_cycle(shell["total"], clock_ns)
    return {"point": alone["point"], "snax_forge_commit": alone["snax_forge_commit"], "seed": alone.get("seed"),
            "shell": shell["path"],
            "cluster": {"cycles": cycles, "pj_cycle": e, "nj": e * cycles / 1e3},
            "alone": {"cycles": int(alone["cycles"]), "pj_cycle": float(alone["e_dyn_pj"]),
                      "nj": float(alone["e_run_pj"]) / 1e3}}


def csv_rows(path: Path, point: str, ungated: bool = False) -> list[dict]:
    """The point's rows; with `ungated`, its ungated ones (clk_gate not 1, X79): the `alone` point as X23 ran it."""
    if not path.is_file():
        return []
    with path.open(newline="") as fh:
        return [r for r in csv.DictReader(fh)
                if r["point"] == point and not (ungated and r.get("clk_gate", "") == "1")]


def point_energy(point: dict, tech: str, cfg: dict) -> dict | None:
    name = point["point"]
    rep = ROOT / "results" / "cluster" / tech / "power_reports" / f"{name}.zip"
    if not rep.is_file():
        return None
    pt = {int(r["mark"]): r for r in csv_rows(ROOT / "results" / "cluster" / tech / "power_pt.csv", name)}
    raw = json.loads(arc.read_text(rep, "windows.json"))
    labels = {g["name"]: g["label"] for g in cfg["groups"]}
    wins, bad, run_rows = [], [], {}
    for w in raw:
        wname = f"{w['mark']}_{w['kind']}"
        row = pt.get(int(w["mark"]))
        clock_ns = float(row["clock_ns"]) if row else 10.0
        rows = parse_hierarchy(arc.read_text(rep, f"{wname}/power_hierarchy.rpt", errors="replace"))
        g = window_groups(rows, cfg, clock_ns)
        top = pj_per_cycle(rows[0]["total"], clock_ns)
        want = float(row["e_dyn_pj"]) if row else None
        ok = want is not None and abs(top - want) <= TOL_PCT / 100 * want
        if not ok:
            bad.append(wname)
        c = int(w["cycles"])
        wins.append({"name": wname, "mark": w["mark"], "kind": w["kind"], "label": w["label"], "cycles": c,
                     "clock_ns": clock_ns, "pj_cycle": top, "nj": top * c / 1e3, "groups": g,
                     "check": {"power_pt_e_dyn_pj": want, "ok": ok}})
        if w["kind"] == "run":
            run_rows[wname] = (rows, c, clock_ns)
    span = sum(w["nj"] for w in wins)
    by_group = {k: sum(w["groups"][k] * w["cycles"] / 1e3 for w in wins) for k in labels}
    out: dict = {"windows": wins, "labels": labels,
                 "span": {"cycles": sum(w["cycles"] for w in wins), "nj": span,
                          "groups": [{"name": k, "nj": v, "share_pct": share(v, span)} for k, v in by_group.items()]},
                 "run": run_phase(wins), "failed": bad}
    if pt:
        any_row = next(iter(pt.values()))
        out["snax_forge_commit"], out["snax_cluster_commit"] = any_row["snax_forge_commit"], any_row["snax_cluster_commit"]
    hw = ROOT / "results" / "cluster" / tech / "hwcost" / f"{name}.json"
    if hw.is_file() and out["run"]:
        h = json.loads(hw.read_text())
        out["hwcost"] = {"snax_forge_commit": h["snax_forge_commit"], "platform": h["platform"],
                         "stimulus": h["cost"].get("source", {}).get("stimulus"),
                         **hwcost_rows(h["cost"], out["run"], cfg)}
    if point.get("alone") and len(run_rows) == 1:
        a = next((r for r in csv_rows(ROOT / "results" / "forge" / tech / "power_pt.csv", point["alone"], ungated=True)),
                 None)
        if a is not None:
            rows, c, clock_ns = next(iter(run_rows.values()))
            out["alone"] = alone_row(rows, c, clock_ns, a)
    return out


def _e(x: float | None, nd: int = 2) -> str:
    return "" if x is None else f"{x:,.{nd}f}"


def _s(x: float | None) -> str:
    return "" if x is None else f"{x:.1f} %"


def markdown(name: str, b: dict) -> str:
    lab = b["labels"]
    wins = b["windows"]
    out = [f"### {name}", "", "Per window, pJ per cycle (internal + switching, leakage out):", "",
           "| group | " + " | ".join(w["name"] for w in wins) + " |", "|---|" + "---|" * len(wins)]
    out += [f"| {lab[g]} | " + " | ".join(_e(w["groups"][g], 1) for w in wins) + " |" for g in lab]
    out += ["| total | " + " | ".join(_e(w["pj_cycle"], 1) for w in wins) + " |",
            "| cycles | " + " | ".join(str(w["cycles"]) for w in wins) + " |",
            "| window nJ | " + " | ".join(_e(w["nj"]) for w in wins) + " |"]
    s = b["span"]
    out += ["", f"The span: {s['cycles']} cycles, {_e(s['nj'])} nJ.", "", "| group | nJ | share |", "|---|---|---|"]
    out += [f"| {lab[g['name']]} | {_e(g['nj'])} | {_s(g['share_pct'])} |" for g in s["groups"]]
    for r in b["run"]:
        out += ["", f"The run phase, `{r['window']}` ({r['cycles']} cycles) against the idle `{r['idle_window']}`:", "",
                "| group | idle pJ/cycle | run pJ/cycle | run nJ | above idle nJ |", "|---|---|---|---|---|"]
        out += [f"| {lab[x['group']]} | {_e(x['idle_pj_cycle'], 1)} | {_e(x['run_pj_cycle'], 1)} | {_e(x['run_nj'])} | "
                f"{_e(x['above_idle_nj'])} |" for x in r["groups"]]
    if "hwcost" in b:
        h = b["hwcost"]
        out += ["", f"HWCOST's energy (snax-forge `{h['snax_forge_commit'][:8]}`, stimulus {h['stimulus']}) against the "
                    "run phase; the shares are each side's of its own five parts:", "",
                "| part | HWCOST nJ | share | run nJ | share | above idle nJ | share |", "|---|---|---|---|---|---|---|"]
        out += [f"| {r['part']} | {_e(r['hwcost_nj'])} | {_s(r['hwcost_share_pct'])} | {_e(r['run_nj'])} | "
                f"{_s(r['run_share_pct'])} | {_e(r['above_idle_nj'])} | {_s(r['above_idle_share_pct'])} |"
                for r in h["parts"]]
        out += [f"| the five parts | {_e(h['hwcost_nj'])} | | {_e(h['run_nj'])} | | {_e(h['above_idle_nj'])} | |"]
    if "alone" in b:
        a = b["alone"]
        out += ["", f"The accelerator's shell in the run window against `{a['point']}` alone (snax-forge "
                    f"`{a['snax_forge_commit'][:8]}`, seed {a['seed']}, X23's busy window):", "",
                "| | cycles | pJ/cycle | nJ |", "|---|---|---|---|",
                f"| in the cluster | {a['cluster']['cycles']} | {_e(a['cluster']['pj_cycle'], 1)} | {_e(a['cluster']['nj'])} |",
                f"| alone | {a['alone']['cycles']} | {_e(a['alone']['pj_cycle'], 1)} | {_e(a['alone']['nj'])} |"]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    cfg = json.loads(GROUPS.read_text())
    res = {}
    for p in json.loads(POINTS.read_text())["points"]:
        b = point_energy(p, a.tech, cfg)
        if b is not None:
            res[p["point"]] = b
    if not res:
        print(f"no point with reports in results/cluster/{a.tech}/power_reports/", file=sys.stderr)
        return 1
    path = ROOT / "results" / "cluster" / a.tech / "energy.json"
    path.write_text(json.dumps(res, indent=1) + "\n")
    bad = {k: b["failed"] for k, b in res.items() if b["failed"]}
    print(f"{path.relative_to(ROOT)}: {', '.join(res)}" + (f"; e_dyn check FAILED for {bad}" if bad else ""))
    if a.md:
        print("".join(markdown(k, b) for k, b in res.items()))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
