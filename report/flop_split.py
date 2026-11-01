#!/usr/bin/env python3
"""report/flop_split.py - SYN1's control/datapath split of every n2048 point, HLS and forge, both technologies.

  pixi run split pt [--tech T] [--source hls|forge] [--points G] [-j N] [--force]   PrimePower per point
  pixi run split collect                                                 the checks, then the committed CSVs

pt: PrimePower again on each point's mapped netlist (syn/runs/) with the SAIF its power run kept
(sim/runs/.../n2048_s0/busy.saif), read in place: sim/scripts/pt_cells.tcl runs sim/scripts/pt_power.tcl
unchanged and then writes every leaf cell's area and power, and whether the cell is in the forward cone
of the data input ports (Vitis *_TDATA, forge stream2acc_*_data_i). Its Power Group table must equal the
committed run's (sim/runs/.../pt/power.rpt). Parallel runs: min(-j, free PrimeTime, free PrimePower
licences) (X16). Writes only under sim/split_runs/ (git ignores it); nothing under syn/runs/ or sim/runs/.

collect: per point, the cells by kind (flop, comb), cone (data: in the cone; control: the rest) and unit
(HLS flops: section 3's register class by name, from hls-exercises' Verilog; HLS comb: top, core (a Vitis
core instance *_U<n>) or sub (another instance); forge: the wrapper's instance csr, ctrl, dp, or top).
Checks, each a failure: the cells' area equals synth_dc.csv's area_um2; their dynamic energy per cycle
equals power_pt.csv's e_dyn_pj (all) and e_flop_pj (flops); the flop count equals flop_bits; every HLS
flop is a Verilog register of the point (one Vitis name, _reg or _reg[<bit>] added by DC) and no register
has more flops than bits. Writes results/analysis/syn1/split_<tech>.csv, split_checks_<tech>.csv and
split_regs_<tech>.csv (per register: its hierarchy path and name, side, flops, internal and switching energy
per cycle; a flop's internal power includes its clock pin's).
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analysis_syn1 import hls_reg_entries  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "analysis" / "syn1"
RUNS = ROOT / "sim" / "split_runs"
SCRIPT = ROOT / "sim" / "scripts" / "pt_cells.tcl"
TECHS = ["nangate45", "nangate15"]
SIZE = "n2048"
CLOCK_NS = 10.0
DATA_PORTS = {"hls": "*_TDATA", "forge": "stream2acc_*_data_i"}
SYN = {"hls": ROOT / "syn" / "runs" / "hls", "forge": ROOT / "syn" / "runs" / "forge"}
SIM = {"hls": ROOT / "sim" / "runs", "forge": ROOT / "sim" / "runs" / "forge"}
LMUTIL_DEFAULT = "/esat/micas-data/software/Mentor/questasim_2022.4/linux_x86_64/lmutil"
COLUMNS = ["point", "side", "kernel", "case", "W", "tech", "cycles", "kind", "cone", "unit", "cells", "area_um2",
           "e_dyn_pj"]
REG_COLUMNS = ["point", "side", "kernel", "case", "W", "tech", "cycles", "cone", "register", "flops", "e_int_pj",
               "e_sw_pj"]
CHECK_COLUMNS = ["point", "side", "tech", "cells", "area_um2", "area_dc_um2", "e_dyn_pj", "e_dyn_csv_pj",
                 "e_flop_pj", "e_flop_csv_pj", "flops", "flop_bits", "verilog_bits", "removed_bits",
                 "data_flops", "data_cells", "mismatch_cells", "mismatch_area_um2", "mismatch_e_pj"]


class Fail(Exception):
    pass


def read(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def points(tech: str, side: str) -> list[dict]:
    """The committed n2048 power rows with status ok."""
    return [r for r in read(RES / side / tech / "power_pt.csv") if r["size"] == SIZE and r["status"] == "ok"]


# ---------------------------------------------------------------- pt
def free_licences() -> dict:
    lm = os.environ.get("LMUTIL") or shutil.which("lmutil") or LMUTIL_DEFAULT
    out = {}
    for feat in ("PrimeTime", "PrimePower"):
        r = subprocess.run([lm, "lmstat", "-c", "1709@licserv", "-f", feat], capture_output=True, text=True,
                           timeout=120)
        m = re.search(r"Users of %s:.*Total of (\d+) licenses? issued;\s+Total of (\d+) licenses? in use" % feat,
                      r.stdout)
        if not m:
            raise Fail(f"lmstat: no count for {feat}")
        out[feat] = int(m.group(1)) - int(m.group(2))
    return out


def groups(rpt: Path) -> list[str]:
    """The Power Group table and the totals of a power.rpt, as lines."""
    t = rpt.read_text()
    m = re.search(r"^Power Group.*?^Total Power.*?$", t, re.S | re.M)
    if not m:
        raise Fail(f"{rpt}: no Power Group table")
    return [ln.rstrip() for ln in m.group(0).splitlines()]


def run_pt(side: str, tech: str, point: str, force: bool) -> tuple[str, str, float]:
    d = RUNS / side / tech / point
    if (d / "cells.tsv").is_file() and (d / "ok").is_file() and not force:
        return point, "kept", 0.0
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    saif = SIM[side] / tech / point / f"{SIZE}_s0" / "busy.saif"
    ref = SIM[side] / tech / point / f"{SIZE}_s0" / "pt" / "power.rpt"
    if not saif.is_file() or not ref.is_file():
        return point, f"FAIL: no {saif.relative_to(ROOT)} or {ref.relative_to(ROOT)}", 0.0
    env = {**os.environ, "PWR_RUN": str(SYN[side] / tech / point), "PWR_MODE": "saif", "PWR_ACT": str(saif),
           "PWR_STRIP": "tb/dut", "PWR_OUT": str(d), "PWR_THREADS": "1", "SPLIT_DATA_PORTS": DATA_PORTS[side]}
    t = time.time()
    with (d / "pt_stdout.log").open("w") as fh:
        try:
            rc = subprocess.run(["pt_shell", "-no_init", "-f", str(SCRIPT), "-output_log_file",
                                 str(d / "pt_shell.log")], cwd=d, env=env, stdin=subprocess.DEVNULL, stdout=fh,
                                stderr=subprocess.STDOUT, timeout=1800).returncode
        except subprocess.TimeoutExpired:
            return point, "FAIL: timeout 1800 s", time.time() - t
    dt = time.time() - t
    if rc or not (d / "cells.tsv").is_file():
        return point, f"FAIL: pt_shell rc {rc} ({(d / 'pt_stdout.log').relative_to(ROOT)})", dt
    if groups(d / "power.rpt") != groups(ref):
        return point, "FAIL: Power Group table differs from the committed run's", dt
    (d / "ok").write_text("power.rpt's Power Group table equals the committed run's\n")
    return point, "ok", dt


def cmd_pt(a) -> int:
    lic = free_licences()
    jobs = max(1, min(a.jobs, lic["PrimeTime"], lic["PrimePower"]))
    print(f"free licences: PrimeTime {lic['PrimeTime']}, PrimePower {lic['PrimePower']}; -j {a.jobs} -> {jobs} parallel")
    todo = [(s, t, r["point"]) for t in a.tech for s in a.source for r in points(t, s)
            if fnmatch.fnmatch(r["point"], a.points)]
    print(f"{len(todo)} points")
    fails = []
    t0 = time.time()
    with ThreadPoolExecutor(jobs) as ex:
        futs = {ex.submit(run_pt, s, t, p, a.force): (s, t, p) for s, t, p in todo}
        for i, f in enumerate(futs, 1):
            s, t, p = futs[f]
            point, st, dt = f.result()
            print(f"[{i}/{len(todo)}] {s} {t} {p}: {st} ({dt:.0f} s)", flush=True)
            if st.startswith("FAIL"):
                fails.append((s, t, p, st))
    print(f"done in {time.time() - t0:.0f} s; {len(todo) - len(fails)} ok, {len(fails)} failed")
    for f in fails:
        print("  ", *f)
    return 1 if fails else 0


# ---------------------------------------------------------------- collect
def leaf_reg(cell: str) -> str:
    leaf = cell.split("/")[-1]
    m = re.match(r"^(.*)_reg(\[\d+\])?$", leaf)
    return m.group(1) if m else leaf


def hls_unit_comb(cell: str) -> str:
    if "/" not in cell:
        return "top"
    return "core" if re.search(r"_U\d+$", cell.split("/")[0]) else "sub"


def collect_point(side: str, tech: str, prow: dict, srow: dict) -> tuple[list[dict], dict, list[dict]]:
    point = prow["point"]
    _, kernel, pt_ = point.split("/")
    case, w = pt_.rsplit("_w", 1)
    cells = read_tsv(RUNS / side / tech / point / "cells.tsv")
    if side == "hls":
        entries, _ = hls_reg_entries(kernel, case, int(w))
        cls, bits = {}, defaultdict(int)
        for _, n, k, b in entries:
            if cls.setdefault(n, k) != k:
                raise Fail(f"{point}: register {n} has classes {cls[n]} and {k}")
            bits[n] += b or 0
    agg = defaultdict(lambda: [0, 0.0, 0.0])
    per_reg = defaultdict(int)
    regs = defaultdict(lambda: [0, 0.0, 0.0])     # (cone, register path) -> flops, internal, switching (pJ/cycle)
    unmatched = []
    n_flops = 0
    area = e_all = e_flop = 0.0
    data_flops = data_cells = 0
    mis = [0, 0.0, 0.0]
    for c in cells:
        a = float(c["area"])
        e = (float(c["internal_w"] or 0) + float(c["switching_w"] or 0)) * CLOCK_NS * 1e-9 * 1e12
        seq = c["seq"] == "true"
        data = c["data"] == "1"
        kind = "flop" if seq else "comb"
        if side == "hls":
            if seq:
                reg = leaf_reg(c["cell"])
                if reg not in cls:
                    unmatched.append(c["cell"])
                    continue
                unit = cls[reg]
                per_reg[reg] += 1
            else:
                unit = hls_unit_comb(c["cell"])
        else:
            unit = c["cell"].split("/")[0] if "/" in c["cell"] else "top"
            if unit not in ("csr", "ctrl", "dp"):
                unit = "top"
            if (unit == "dp") != data and unit != "top":
                mis[0] += 1
                mis[1] += a
                mis[2] += e
        k = (kind, "data" if data else "control", unit)
        agg[k][0] += 1
        agg[k][1] += a
        agg[k][2] += e
        area += a
        e_all += e
        if seq:
            n_flops += 1
            e_flop += e
            data_flops += data
            parts = c["cell"].split("/")
            rk = regs[("data" if data else "control", "/".join(parts[:-1] + [leaf_reg(c["cell"])]))]
            rk[0] += 1
            rk[1] += float(c["internal_w"] or 0) * CLOCK_NS * 1e3
            rk[2] += float(c["switching_w"] or 0) * CLOCK_NS * 1e3
        data_cells += data
    if unmatched:
        raise Fail(f"{point} ({tech}): {len(unmatched)} flops match no Verilog register: {unmatched[:8]}")
    removed = 0
    if side == "hls":
        for reg, n in per_reg.items():
            if n > bits[reg] and bits[reg]:
                raise Fail(f"{point} ({tech}): {reg} has {n} flops, {bits[reg]} bits in the Verilog")
        removed = sum(b - per_reg.get(r, 0) for r, b in bits.items() if b and per_reg.get(r, 0) < b)
    area_dc = float(srow["area_um2"])
    e_dyn, e_fl, fb = float(prow["e_dyn_pj"]), float(prow["e_flop_pj"]), int(prow["flop_bits"])
    if abs(area - area_dc) > 0.01 + 1e-6 * area_dc:
        raise Fail(f"{point} ({tech}): cells' area {area:.4f}, synth_dc.csv {area_dc:.4f}")
    if abs(e_all - e_dyn) > 2e-5 * e_dyn + 1e-6:
        raise Fail(f"{point} ({tech}): cells' e_dyn {e_all:.6f} pJ, power_pt.csv {e_dyn:.6f}")
    if abs(e_flop - e_fl) > 2e-5 * e_fl + 1e-6:
        raise Fail(f"{point} ({tech}): flops' e_dyn {e_flop:.6f} pJ, power_pt.csv e_flop {e_fl:.6f}")
    if n_flops != fb:
        raise Fail(f"{point} ({tech}): {n_flops} flops, power_pt.csv flop_bits {fb}")
    rows = [{"point": point, "side": side, "kernel": kernel, "case": case, "W": w, "tech": tech,
             "cycles": prow["cycles"], "kind": k[0], "cone": k[1], "unit": k[2], "cells": v[0],
             "area_um2": f"{v[1]:.4f}", "e_dyn_pj": f"{v[2]:.6f}"} for k, v in sorted(agg.items())]
    chk = {"point": point, "side": side, "tech": tech, "cells": len(cells), "area_um2": f"{area:.4f}",
           "area_dc_um2": f"{area_dc:.4f}", "e_dyn_pj": f"{e_all:.6f}", "e_dyn_csv_pj": prow["e_dyn_pj"],
           "e_flop_pj": f"{e_flop:.6f}", "e_flop_csv_pj": prow["e_flop_pj"], "flops": n_flops, "flop_bits": fb,
           "verilog_bits": sum(bits.values()) if side == "hls" else "", "removed_bits": removed if side == "hls" else "",
           "data_flops": data_flops, "data_cells": data_cells,
           "mismatch_cells": mis[0] if side == "forge" else "", "mismatch_area_um2": f"{mis[1]:.4f}" if side == "forge" else "",
           "mismatch_e_pj": f"{mis[2]:.6f}" if side == "forge" else ""}
    regrows = [{"point": point, "side": side, "kernel": kernel, "case": case, "W": w, "tech": tech,
                "cycles": prow["cycles"], "cone": k[0], "register": k[1], "flops": v[0], "e_int_pj": f"{v[1]:.6f}",
                "e_sw_pj": f"{v[2]:.6f}"} for k, v in sorted(regs.items())]
    return rows, chk, regrows


def read_tsv(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def cmd_collect(a) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for tech in TECHS:
        rows, checks, regrows = [], [], []
        for side in ("hls", "forge"):
            syn = {r["point"]: r for r in read(RES / side / tech / "synth_dc.csv")}
            for prow in points(tech, side):
                if not (RUNS / side / tech / prow["point"] / "ok").is_file():
                    raise Fail(f"{side} {tech} {prow['point']}: no checked PT run in sim/split_runs (pixi run split pt)")
                r, c, g = collect_point(side, tech, prow, syn[prow["point"]])
                rows += r
                checks.append(c)
                regrows += g
        for name, cols, data in ((f"split_{tech}.csv", COLUMNS, rows), (f"split_checks_{tech}.csv", CHECK_COLUMNS, checks),
                                 (f"split_regs_{tech}.csv", REG_COLUMNS, regrows)):
            with (OUT / name).open("w", newline="") as fh:
                wr = csv.DictWriter(fh, cols, lineterminator="\n")
                wr.writeheader()
                wr.writerows(sorted(data, key=lambda r: (r["side"], r["point"], r.get("kind", ""), r.get("cone", ""), r.get("unit", ""), r.get("register", ""))))
        print(f"{tech}: {len(checks)} points, {len(rows)} rows -> {(OUT / f'split_{tech}.csv').relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pt")
    p.add_argument("--tech", nargs="+", default=TECHS, choices=TECHS)
    p.add_argument("--source", nargs="+", default=["hls", "forge"], choices=["hls", "forge"])
    p.add_argument("-j", "--jobs", type=int, default=8)
    p.add_argument("--force", action="store_true")
    p.add_argument("--points", default="*", help="a glob on the point, e.g. 'done/dot/*'")
    sub.add_parser("collect")
    a = ap.parse_args()
    try:
        return cmd_pt(a) if a.cmd == "pt" else cmd_collect(a)
    except Fail as e:
        print(f"FAIL: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
