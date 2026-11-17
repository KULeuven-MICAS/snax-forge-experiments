#!/usr/bin/env python3
"""report/snb_report.py - E11's Snitch-only numbers: area in coarse parts, cycles, efficiency, energy per task.

    pixi run snb-report [--tech nangate45] [--md]

Per config of cluster/snb_points.json with its DC reports (results/snb/<tech>/reports/<config>.zip), the area in
cluster/groups.json's groups summed into four coarse parts (COARSE). Per run of results/snb/<tech>/runs.csv with
a PASS RTL run, n_op from its kernel's maths, C_run (the plain RTL run's `cycles run`) and eta_A; where
power_pt.csv has the run window, E_run (its dynamic energy), eta_E and, as a side number, E_leak from the window's
power.rpt (X92). Writes results/snb/<tech>/e11.json; --md prints the tables. The measures are in cluster/README.md,
"snb". Standard library, arc/arc.py and report/cluster_breakdown.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "arc"), str(ROOT / "cluster"), str(ROOT / "report")]
import arc  # noqa: E402
import cluster_breakdown as cb  # noqa: E402  groups(), the area's groups
import tree  # noqa: E402

POINTS = ROOT / "cluster" / "snb_points.json"
GROUPS = ROOT / "cluster" / "groups.json"
T_CLK_NS = 10.0
COARSE = {"memory": ("tcdm_banks", "tcdm_logic"),
          "interconnect": ("tcdm_interconnect",),
          "cores": ("cores", "icache_macros", "icache_logic", "peripherals"),
          "rest": ("dma", "axi", "others", "acc_interface")}
NONE_HERE = ("acc_datapath", "acc_control", "acc_csr", "streamers")     # forge's accelerator: zero in these clusters
SUM_TOL_UM2 = 1.0
NUM = r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"


# ---------------------------------------------------------------- area
def coarse(areas: dict[str, float]) -> dict[str, float]:
    """groups.json's groups summed into COARSE's four parts; every group in exactly one part or in NONE_HERE."""
    named = [g for gs in COARSE.values() for g in gs] + list(NONE_HERE)
    left = sorted(set(areas) - set(named))
    if left or len(named) != len(set(named)):
        raise ValueError(f"groups not in exactly one coarse part: {left or 'a group twice'}")
    return {k: sum(areas[g] for g in gs) for k, gs in COARSE.items()}


def config_area(rows: list[dict], cfg: dict) -> dict:
    """A config's total, groups and coarse parts (µm²); the parts must add up to the total and the accelerator's
    groups must be empty."""
    areas = cb.groups(rows, cfg)
    total = rows[0]["total"]
    parts = coarse(areas)
    stray = {g: areas[g] for g in NONE_HERE if abs(areas[g]) > SUM_TOL_UM2}
    return {"total_um2": total, "parts_um2": parts, "groups_um2": areas,
            "sum_check": {"parts_um2": sum(parts.values()), "ok": abs(sum(parts.values()) - total) < SUM_TOL_UM2},
            "accelerator_groups": {"um2": stray, "ok": not stray}}


# ---------------------------------------------------------------- the measures
def eta_a(n_op: int, cycles: int, area_um2: float, t_clk_ns: float = T_CLK_NS) -> float:
    """Operations per second per mm², in GOPS/mm²: n_op / (C_run t_clk A)."""
    return n_op / (cycles * t_clk_ns * 1e-9) / (area_um2 * 1e-6) / 1e9


def eta_e(n_op: int, e_pj: float) -> float:
    """Operations per pJ: n_op / E_run."""
    return n_op / e_pj


def leakage(power_rpt: str, units_rpt: str) -> dict:
    """The window's leakage power in µW from PT's power.rpt: in all (Cell Leakage Power) and the macros' part
    (black_box and memory, as PT measures the macros)."""
    m = re.search(rf"User Specified Power Unit\s*:\s*({NUM})\s*Watt", units_rpt)
    tot = re.search(rf"^\s*Cell Leakage Power\s*=\s*({NUM})", power_rpt, re.M)
    if not m or not tot:
        raise ValueError("no power unit in units.rpt or no Cell Leakage Power in power.rpt")
    to_uw = float(m.group(1)) * 1e6
    macro = 0.0
    for g in ("black_box", "memory"):
        r = re.search(rf"^{g}\s+{NUM}\s+{NUM}\s+({NUM})", power_rpt, re.M)
        macro += float(r.group(1)) if r else 0.0
    return {"p_leak_uw": float(tot.group(1)) * to_uw, "p_leak_macro_uw": macro * to_uw}


def run_row(r: dict, k: dict, area_um2: float | None, win: dict | None, leak: dict | None) -> dict:
    """One run's E11 numbers from its runs.csv row, its kernel, its config's area, its run window's power_pt.csv
    row and its leakage."""
    sizes = {kv.split("=")[0]: int(kv.split("=")[1]) for kv in r["sizes"].split()}
    n = int(r["n_op"])
    c_run = int(r["rtl_run"])
    out = {"config": r["config"], "kernel": r["kernel"], "type": r["type"], "sizes": sizes, "workers": int(r["workers"]),
           "n_op": n, "n_op_rule": k["n_op"], "c_run": c_run, "c_run_gls": int(r["gls_run"]) if r.get("gls_run") else None,
           "dma_in": int(r["rtl_dma_in"]), "dma_out": int(r["rtl_dma_out"]), "area_um2": area_um2,
           "eta_a_gops_mm2": eta_a(n, c_run, area_um2) if area_um2 else None}
    if win is not None:
        cyc = int(win["cycles"])
        e_run = float(win["e_win_pj"])
        out.update({"window_cycles": cyc, "p_dyn_uw": float(win["p_dyn_uw"]), "e_run_pj": e_run,
                    "e_run_macro_pj": float(win["e_macro_pj"]) * cyc, "eta_e_op_pj": eta_e(n, e_run),
                    "ann_pct": float(win["ann_pct"])})
        if leak is not None:
            out.update({**leak, "e_leak_pj": leak["p_leak_uw"] * cyc * T_CLK_NS / 1000.0,
                        "e_leak_macro_pj": leak["p_leak_macro_uw"] * cyc * T_CLK_NS / 1000.0})
    return out


# ---------------------------------------------------------------- reading the results
def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def report(tech: str) -> dict:
    pts = json.loads(POINTS.read_text())
    cfg = json.loads(GROUPS.read_text())
    res = results(tech)
    out: dict = {"tech": tech, "t_clk_ns": T_CLK_NS, "configs": {}, "runs": {}}
    syn = {r["point"]: r for r in read_csv(res / "synth_dc.csv")}
    for c in pts["configs"]:
        z = res / "reports" / f"{c['config']}.zip"
        if not z.is_file():
            continue
        a = config_area(tree.parse(arc.read_text(z, "area_hierarchy.rpt", errors="replace")), cfg)
        row = syn.get(c["config"])
        if row is not None:
            a["synth_dc"] = {"area_um2": float(row["area_um2"]), "macro_um2": float(row["macro_um2"]),
                             "status": row["status"], "slack_ns": float(row["slack_ns"]),
                             "ok": abs(float(row["area_um2"]) - a["total_um2"]) < SUM_TOL_UM2}
        out["configs"][c["config"]] = {"cores": c["cores"], "workers": c["workers"], **a}
    wins = {r["point"]: r for r in read_csv(res / "power_pt.csv") if r["kind"] == "run" and r["status"] == "ok"}
    for r in read_csv(res / "runs.csv"):
        if r["rtl_status"] != "PASS":
            continue
        area = out["configs"].get(r["config"], {}).get("total_um2")
        win, leak = wins.get(r["run"]), None
        rz = res / "power_reports" / f"{r['run']}.zip"
        if win is not None and rz.is_file():
            n = f"{win['mark']}_{win['kind']}"
            leak = leakage(arc.read_text(rz, f"{n}/power.rpt"), arc.read_text(rz, f"{n}/units.rpt"))
        out["runs"][r["run"]] = run_row(r, pts["kernels"][r["kernel"]], area, win, leak)
    return out


def results(tech: str) -> Path:
    return ROOT / "results" / "snb" / tech


# ---------------------------------------------------------------- Markdown
def _n(x: float | None, d: int = 0) -> str:
    return "" if x is None else f"{x:,.{d}f}"


def _g(x: float | None) -> str:
    return "" if x is None else f"{x:.3g}"


def markdown(rep: dict) -> str:
    out = ["### Area", "", "| config | total µm² | memory | interconnect | cores | rest | parts add up |",
           "|---|---|---|---|---|---|---|"]
    for name, c in rep["configs"].items():
        p = c["parts_um2"]
        out.append(f"| {name} | {_n(c['total_um2'])} | {_n(p['memory'])} | {_n(p['interconnect'])} | "
                   f"{_n(p['cores'])} | {_n(p['rest'])} | {'yes' if c['sum_check']['ok'] else 'NO'} |")
    out += ["", "### Runs", "", f"$t_\\text{{clk}}$ = {rep['t_clk_ns']:g} ns; C_run is the plain RTL run's run section.",
            "", "| run | n_op | C_run | GLS C_run | η_A (GOPS/mm²) | E_run (nJ) | η_E (op/pJ) | E_leak (nJ) |",
            "|---|---|---|---|---|---|---|---|"]
    for name, r in rep["runs"].items():
        e = r.get("e_run_pj")
        lk = r.get("e_leak_pj")
        out.append(f"| {name} | {r['n_op']} | {r['c_run']} | {r['c_run_gls'] or ''} | {_g(r['eta_a_gops_mm2'])} | "
                   f"{'' if e is None else f'{e / 1000:.2f}'} | {_g(r.get('eta_e_op_pj'))} | "
                   f"{'' if lk is None else f'{lk / 1000:.2f}'} |")
    return "\n".join(out) + "\n"


def rounded(x, digits: int = 6):
    """Floats to `digits` significant digits, so a rerun on another Python gives the same file."""
    if isinstance(x, float):
        return float(f"{x:.{digits}g}")
    if isinstance(x, dict):
        return {k: rounded(v, digits) for k, v in x.items()}
    if isinstance(x, list):
        return [rounded(v, digits) for v in x]
    return x


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    rep = report(a.tech)
    if not rep["configs"]:
        print(f"no config with reports in {results(a.tech).relative_to(ROOT)}/reports/", file=sys.stderr)
        return 1
    path = results(a.tech) / "e11.json"
    path.write_text(json.dumps(rounded(rep), indent=1) + "\n")
    bad = [k for k, c in rep["configs"].items()
           if not (c["sum_check"]["ok"] and c["accelerator_groups"]["ok"] and c.get("synth_dc", {"ok": True})["ok"])]
    print(f"{path.relative_to(ROOT)}: {len(rep['configs'])} configs, {len(rep['runs'])} runs, "
          f"{sum('e_run_pj' in r for r in rep['runs'].values())} with energy"
          + (f"; area check FAILED for {bad}" if bad else ""))
    if a.md:
        print(markdown(rep))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
