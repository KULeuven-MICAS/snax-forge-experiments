#!/usr/bin/env python3
"""report/ctrl2_summary.py - the ratios behind results/compare/README.md's summary table (hand-written), per kernel and W.

  pixi run python report/ctrl2_summary.py [REV]

forge's energy per element and area against the lowest HLS case (Vitis opt, Vitis dace, Bambu, XLS), each metric apart,
nangate45, n2048. Two bases: forge's total without csr (X63, X65: the peripherals in) and forge's ctrl + datapath. REV
reads that commit's compare CSVs (git show); without it, the working tree's.
"""
import csv, io, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ROWS = [("dot (forge 3)", "dot", "forge3"), ("vecmul", "vecmul", "forge"), ("axpy (α from a CSR)", "axpy", "forge"),
        ("vecadd", "vecadd", "forge"), ("matadd", "matadd", "forge"), ("vsum", "vsum", "forge"),
        ("rowsum", "rowsum", "forge"), ("relu", "relu", "forge")]
HLS = ("opt", "dace", "bambu", "xls")


def load(rev):
    out = []
    for t in ("done", "untiered"):
        p = f"results/compare_{t}.csv"
        text = subprocess.run(["git", "show", f"{rev}:{p}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout \
            if rev else (ROOT / p).read_text()
        out += [r for r in csv.DictReader(io.StringIO(text)) if r["tech"] == "nangate45" and r["size"] == "n2048" and r["status"] == "ok"]
    return {(r["kernel"], r["case"], int(r["W"])): r for r in out}


def main():
    d = load(sys.argv[1] if len(sys.argv) > 1 else None)
    f = lambda r, k: float(r[k])  # noqa: E731
    print("| Kernel | " + " | ".join(f"W = {w}" for w in (1, 2, 4, 8, 16)) + " |")
    for lab, k, c in ROWS:
        cells, cells2, best = [], [], []
        for w in (1, 2, 4, 8, 16):
            r = d[(k, c, w)]
            cyc, el = int(r["cycles"]), int(r["elements"])
            e_nocsr = (f(r, "e_run_pj") - f(r, "e_dyn_csr_pj") * cyc) / el
            a_nocsr = f(r, "area_um2") - f(r, "csr_um2")
            e_cd = (f(r, "e_dyn_ctrl_pj") + f(r, "e_dyn_datapath_pj")) * cyc / el
            a_cd = f(r, "ctrl_um2") + f(r, "datapath_um2")
            hl = [d[(k, h, w)] for h in HLS if (k, h, w) in d]
            be = min(hl, key=lambda x: f(x, "e_run_pj") / int(x["elements"]))
            ba = min(hl, key=lambda x: f(x, "area_um2"))
            eb, ab = f(be, "e_run_pj") / int(be["elements"]), f(ba, "area_um2")
            cells.append(f"{e_nocsr / eb:.2f} / {a_nocsr / ab:.2f}")
            cells2.append(f"{e_cd / eb:.2f} / {a_cd / ab:.2f}")
            best.append(f"{be['case']}/{ba['case']}")
        print(f"| {lab} | " + " | ".join(cells) + " |   ctrl+dp: " + " | ".join(cells2) + "   best: " + " ".join(best))


main()
