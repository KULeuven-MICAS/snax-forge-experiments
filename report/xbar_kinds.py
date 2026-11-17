#!/usr/bin/env python3
"""report/xbar_kinds.py - the interconnect's read-only and write-only inputs, in two forms HWCOST can use.

  pixi run xbar-kinds [--tech nangate45]

Reads results/xbar_mix/<tech>/synth_dc.csv and power_pt.csv, results/strm/<tech>/xbar.csv and, for the check
against the cluster, a cluster point's area_hierarchy.rpt; writes results/strm/<tech>/xbar_kinds.json: the area's
factor form (the default, A = A_table(n, b) (1 - f_ro n_ro / n - f_wo n_wo / n)) and crosspoint form (a
least-squares cost per crosspoint of each kind) with their checks against the two i36_b32 points and the cluster's
sparse_interconnect_i (X71), and the energy's factor form by bank count (e_k(b) = e_access(b, b) (1 - g_k(b)), X93).
The fits and worked examples are in docs/cost_tables.md. Standard library, numpy and arc/arc.py.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "arc"))
sys.path.insert(0, str(ROOT / "report"))
import arc  # noqa: E402
import strm_table  # noqa: E402

CLUSTER = ("dot3_w16_cg", "sparse_interconnect_i", 35, 32, 32, 1)   # point, instance, n, b, n_ro, n_wo


def rows(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        out = []
        for r in csv.DictReader(fh):
            if r["status"] != "ok":
                continue
            out.append({"point": r["point"], "n": int(r["inputs"]), "b": int(r["banks"]), "ro": int(r["ro"]),
                        "wo": int(r["wo"]), "area": float(r["area_um2"])})
        return out


def factor(rs: list[dict]) -> dict:
    """f_ro and f_wo: the mean over (n, b) pairs that have all three kinds of 1 - A(kind) / A(rw)."""
    by = {(r["n"], r["b"], r["ro"], r["wo"]): r["area"] for r in rs}
    per = []
    for (n, b, ro, wo), a_rw in sorted(by.items()):
        if ro or wo or (n, b, n, 0) not in by or (n, b, 0, n) not in by:
            continue
        per.append({"inputs": n, "banks": b, "f_ro": 1 - by[(n, b, n, 0)] / a_rw, "f_wo": 1 - by[(n, b, 0, n)] / a_rw})
    if not per:
        raise ValueError("no (inputs, banks) pair with all read-write, all read-only and all write-only points")
    f = {k: float(np.mean([p[k] for p in per])) for k in ("f_ro", "f_wo")}
    return {**f, "f_ro_range": [min(p["f_ro"] for p in per), max(p["f_ro"] for p in per)],
            "f_wo_range": [min(p["f_wo"] for p in per), max(p["f_wo"] for p in per)], "pairs": per}


def energy_rows(path: Path) -> list[dict]:
    """The powered xbar_mix points: inputs, banks, ro, wo and the energy per access (pJ)."""
    with path.open(newline="") as fh:
        return [{"point": r["point"], "n": int(r["inputs"]), "b": int(r["banks"]), "ro": int(r["ro"]),
                 "wo": int(r["wo"]), "e": float(r["e_access_pj"])}
                for r in csv.DictReader(fh) if r["status"] == "ok"]


def energy_factor(rs: list[dict]) -> dict:
    """g_ro(b) and g_wo(b): 1 - e(all read-only or all write-only) / e(all read-write) at inputs = banks, per bank
    count (the price is read at (b, b), X54); every powered (n, b) pair's ratios as well, for the trend."""
    by = {(r["n"], r["b"], r["ro"], r["wo"]): r["e"] for r in rs}
    pairs = []
    for (n, b, ro, wo), e_rw in sorted(by.items()):
        if ro or wo or (n, b, n, 0) not in by or (n, b, 0, n) not in by:
            continue
        pairs.append({"inputs": n, "banks": b, "e_rw": e_rw, "e_ro": by[(n, b, n, 0)], "e_wo": by[(n, b, 0, n)],
                      "g_ro": 1 - by[(n, b, n, 0)] / e_rw, "g_wo": 1 - by[(n, b, 0, n)] / e_rw})
    banks = {p["banks"]: p for p in pairs if p["inputs"] == p["banks"]}
    if not banks:
        raise ValueError("no bank count with all read-write, all read-only and all write-only points at inputs = banks")
    return {"by_banks": banks, "pairs": pairs}


def g_at(ef: dict, b: int) -> tuple[float, float]:
    """(g_ro, g_wo) at b banks: linear in b between the measured bank counts, the nearest one's outside them."""
    bs = sorted(ef["by_banks"])
    lo = max([x for x in bs if x <= b], default=bs[0])
    hi = min([x for x in bs if x >= b], default=bs[-1])
    t = 0.0 if hi == lo else (b - lo) / (hi - lo)
    a, z = ef["by_banks"][lo], ef["by_banks"][hi]
    return a["g_ro"] + t * (z["g_ro"] - a["g_ro"]), a["g_wo"] + t * (z["g_wo"] - a["g_wo"])


def design(n: int, b: int, ro: int, wo: int) -> list[float]:
    return [b * (n - ro - wo), b * ro, b * wo, n, b, 1.0]


COEF = ("c_rw", "c_ro", "c_wo", "d", "e", "g")


def crosspoint(rs: list[dict], hold_out: set[str]) -> dict:
    fit = [r for r in rs if r["point"] not in hold_out]
    x = np.array([design(r["n"], r["b"], r["ro"], r["wo"]) for r in fit])
    y = np.array([r["area"] for r in fit])
    c, *_ = np.linalg.lstsq(x, y, rcond=None)
    res = (x @ c - y) / y * 100
    return {**dict(zip(COEF, map(float, c))), "points": len(fit), "max_residual_pct": float(abs(res).max())}


def predict_factor(f: dict, a_table: float, n: int, ro: int, wo: int) -> float:
    return a_table * (1 - f["f_ro"] * ro / n - f["f_wo"] * wo / n)


def predict_crosspoint(cp: dict, n: int, b: int, ro: int, wo: int) -> float:
    return float(np.dot(design(n, b, ro, wo), [cp[k] for k in COEF]))


def cluster_area(tech: str) -> float | None:
    """The cluster's interconnect area from its committed area_hierarchy.rpt, or None when the zip is not there."""
    z = ROOT / "results" / "cluster" / tech / "reports" / f"{CLUSTER[0]}.zip"
    if not z.is_file():
        return None
    for ln in arc.read(z, "area_hierarchy.rpt").decode().splitlines():
        f = ln.split()
        if f and f[0].endswith("/" + CLUSTER[1]):
            return float(f[1])
    return None


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(tech: str) -> dict:
    mix = ROOT / "results" / "xbar_mix" / tech / "synth_dc.csv"
    pwr = ROOT / "results" / "xbar_mix" / tech / "power_pt.csv"
    tab = ROOT / "results" / "strm" / tech / "xbar.csv"
    rs = rows(mix)
    ef = energy_factor(energy_rows(pwr))
    held = {r["point"] for r in rs if r["n"] == 36}
    f, cp = factor(rs), crosspoint(rs, held)
    t = strm_table.complete_xbar(strm_table.load(tab, strm_table.XBAR_AXES, ("area_um2", "e_access_pj"),
                                                 strm_table.XBAR_SCALES))
    checks = []
    targets = [(r["point"], r["n"], r["b"], r["ro"], r["wo"], r["area"]) for r in rs if r["point"] in held]
    ca = cluster_area(tech)
    if ca is not None:
        targets.append((f"cluster {CLUSTER[0]} {CLUSTER[1]}", *CLUSTER[2:], ca))
    for name, n, b, ro, wo, area in targets:
        a_tab = strm_table.xbar_cost(t, n, b)[0]
        pf, pc = predict_factor(f, a_tab, n, ro, wo), predict_crosspoint(cp, n, b, ro, wo)
        checks.append({"what": name, "inputs": n, "banks": b, "ro": ro, "wo": wo, "area_um2": area,
                       "a_table_um2": a_tab, "factor_um2": pf, "factor_err_pct": (pf / area - 1) * 100,
                       "crosspoint_um2": pc, "crosspoint_err_pct": (pc / area - 1) * 100})
    r6 = lambda v: round(v, 6)  # noqa: E731  # enough digits that the worked examples' sums hold to 1 um2
    return {
        "_doc": "The sparse interconnect's read-only and write-only inputs (X71, report/xbar_kinds.py). factor is "
                "the default: A = A_table(n, b) * (1 - f_ro * n_ro / n - f_wo * n_wo / n), A_table from xbar.csv. "
                "crosspoint is the option: A = b * (c_rw * n_rw + c_ro * n_ro + c_wo * n_wo) + d * n + e * b + g. "
                "n = n_rw + n_ro + n_wo inputs, b banks; a reader's channel is read-only, a writer's write-only, the "
                "cores and the AXI port read-write. Areas in um2. energy is the energy's factor form by bank count "
                "(X93): e_k(b) = e_access(b, b) * (1 - g_k(b)); energies in pJ per access.",
        "tech": tech,
        "factor": {"f_ro": r6(f["f_ro"]), "f_wo": r6(f["f_wo"]), "f_ro_range": list(map(r6, f["f_ro_range"])),
                   "f_wo_range": list(map(r6, f["f_wo_range"])), "pairs": len(f["pairs"]),
                   "method": "mean over the (inputs, banks) pairs of 1 - A(all read-only or all write-only) / "
                             "A(all read-write), both from xbar_mix"},
        "crosspoint": {**{k: round(cp[k], 4) for k in COEF}, "points": cp["points"],
                       "max_residual_pct": round(cp["max_residual_pct"], 2),
                       "method": "ordinary least squares (numpy.linalg.lstsq), unweighted, the i36_b32 points held "
                                 "out", "grid": {"inputs": sorted({r["n"] for r in rs if r["point"] not in held}),
                                                 "banks": sorted({r["b"] for r in rs})}},
        "checks": [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in c.items()} for c in checks],
        "energy": {"by_banks": {str(b): {k: r6(v) for k, v in p.items() if k not in ("inputs", "banks")}
                                for b, p in sorted(ef["by_banks"].items())},
                   "pairs": [{k: (r6(v) if isinstance(v, float) else v) for k, v in p.items()} for p in ef["pairs"]],
                   "method": "per bank count b, 1 - e_access(all read-only or all write-only) / e_access(all "
                             "read-write) on the xbar_mix points with inputs = banks, powered with the xbar stimulus "
                             "by input kind; pairs: every powered (inputs, banks) pair's, for the trend, not priced",
                   "read": "e_k(b) = e_access(b, b) * (1 - g_k(b)), k = ro or wo (g_rw = 0), e_access from xbar.csv; "
                           "g_k linear in b between the measured bank counts, the nearest one's outside them"},
        "sources": {"xbar_mix": {"path": str(mix.relative_to(ROOT)), "sha256": sha256(mix)},
                    "xbar_mix_power": {"path": str(pwr.relative_to(ROOT)), "sha256": sha256(pwr)},
                    "xbar": {"path": str(tab.relative_to(ROOT)), "sha256": sha256(tab)}},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    a = ap.parse_args()
    out = build(a.tech)
    path = ROOT / "results" / "strm" / a.tech / "xbar_kinds.json"
    path.write_text(json.dumps(out, indent=1) + "\n")
    f, cp = out["factor"], out["crosspoint"]
    print(f"factor: f_ro {f['f_ro']} ({f['f_ro_range'][0]}-{f['f_ro_range'][1]}), "
          f"f_wo {f['f_wo']} ({f['f_wo_range'][0]}-{f['f_wo_range'][1]}), {f['pairs']} pairs")
    print("crosspoint: " + ", ".join(f"{k} {cp[k]}" for k in COEF)
          + f"; {cp['points']} points, worst residual {cp['max_residual_pct']} %")
    for b, g in out["energy"]["by_banks"].items():
        print(f"energy at {b} banks: g_ro {g['g_ro']}, g_wo {g['g_wo']} (e_rw {g['e_rw']}, e_ro {g['e_ro']}, "
              f"e_wo {g['e_wo']} pJ)")
    for c in out["checks"]:
        print(f"  {c['what']:42s} {c['area_um2']:>11,.0f}  factor {c['factor_um2']:>11,.0f} "
              f"({c['factor_err_pct']:+.1f} %)  crosspoint {c['crosspoint_um2']:>11,.0f} "
              f"({c['crosspoint_err_pct']:+.1f} %)")
    print(f"wrote {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
