#!/usr/bin/env python3
"""syn/syn.py - ASIC synthesis of bench points with Design Compiler on FreePDK45.

A point is a folder in hls-exercises' rtl/ (a checkout next to this repo,
../hls-exercises), named <tier>/<kernel>/<point> (e.g. done/vecadd/opt_w8, one
hardware point: case and W, every size runs on it), holding Vitis's Verilog and
a filelist.f that hls-exercises' bench/bench.py writes. Patterns are shell
globs over those names.

  python3 syn/syn.py list    [PATTERN ...]
  python3 syn/syn.py run     PATTERN ... [--clock NS] [--cores N] [-j N] [--dry-run]
  python3 syn/syn.py summary [PATTERN ...]

Each run works in syn/runs/hls/<tier>/<kernel>/<point>[_c<clock>]/ (the clock tag
only for a clock other than the default): WORK/, logs/, reports/ and out/ (the
mapped netlist and sdf). Every run also writes one row into
syn/runs/hls/summary.csv: area, critical path, slack and power. git ignores
syn/runs/ entirely; only a copy of the summary, results/hls/synth_dc.csv, is
committed, so the numbers can be read without the runs.

A point whose filelist.f has '# ram:' lines holds a memory Vitis built (e.g.
DaCe's dot buffer). gscl45nm has no RAM, and DC would build it from flops,
which takes hours and gives no fair area, so `run` parks it: no DC run, and a
summary row with status "skipped: needs a RAM macro (...)". --with-ram runs it
anyway (for when a macro or a black-box stub is in place).

Tools and files, all overridable from the environment:
  DC_SHELL        dc_shell                               (Design Compiler)
  SYN_RTL         ../hls-exercises/rtl                  (the points)
  SYN_LIB         ../RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db, next to this repo
                  alternatively use ../RTL_flow_Nangate15/tech/nangate15/NangateOpenCellLibrary_typical.db
Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYN = Path(__file__).resolve().parent
ROOT = SYN.parent
RTL = Path(os.environ.get("SYN_RTL", ROOT.parent / "hls-exercises" / "rtl")).resolve()
RUNS = SYN / "runs" / "hls"
SCRIPT = SYN / "scripts" / "dc_syn.tcl"
SUMMARY = RUNS / "summary.csv"
RESULTS_COPY = ROOT / "results" / "hls" / "synth_dc.csv"  # the committed copy of SUMMARY
DEFAULT_LIB = ROOT.parent / "RTL_flow_Nangate15" / "tech" / "nangate45" / "NangateOpenCellLibrary_typical.db"
DEFAULT_CLOCK = "10"

COLUMNS = ["point", "top", "clock_ns", "status", "errors", "area", "comb_area", "seq_area", "cells",
           "crit_path_ns", "slack_ns", "maxcap_nets", "dyn_power", "leak_power", "date", "run"]


# ---------------------------------------------------------------- points
def all_points() -> list[str]:
    return sorted(str(f.parent.relative_to(RTL)) for f in RTL.glob("*/*/*/filelist.f"))


def select(patterns: list[str]) -> list[str]:
    pts = all_points()
    if not patterns:
        return pts
    return [p for p in pts if any(fnmatch.fnmatchcase(p, pat) for pat in patterns)]


def top_of(point: str) -> str:
    m = re.search(r"^#\s*top:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)
    return m.group(1) if m else ""


def rams_of(point: str) -> list[str]:
    return re.findall(r"^#\s*ram:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)


def parked_row(point: str, clock: str, rams: list[str]) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"point": point, "top": top_of(point), "clock_ns": clock,
                "status": f"skipped: needs a RAM macro ({', '.join(rams)}); gscl45nm has none, "
                          "generate one (OpenRAM)",
                "date": dt.datetime.now().isoformat(timespec="seconds")})
    return row


def run_dir(point: str, clock: str) -> Path:
    tag = "" if clock == DEFAULT_CLOCK else "_c" + clock.replace(".", "p")
    return RUNS / f"{point}{tag}"


# ---------------------------------------------------------------- reports
def _first(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else ""


def _power(text: str, label: str) -> str:
    """'Total Dynamic Power    = 108.5871 uW  (100%)' -> '108.5871 uW'."""
    m = re.search(rf"{label}\s*=\s*([0-9.eE+-]+)\s*([munpf]?W)", text)
    return f"{m.group(1)} {m.group(2)}" if m else ""


def read_run(point: str, clock: str) -> dict:
    rdir = run_dir(point, clock)
    rep = rdir / "reports"

    def text(name: str) -> str:
        f = rep / name
        return f.read_text(errors="replace") if f.is_file() else ""

    area, qor, power = text("area.rpt"), text("qor.rpt"), text("power.rpt")
    log = rdir / "logs" / "dc_shell.log"
    errors = len(re.findall(r"^Error:", log.read_text(errors="replace"), re.M)) if log.is_file() else ""
    row = {
        "point": point, "top": top_of(point), "clock_ns": clock,
        "errors": errors,
        "area": _first(area, r"Total cell area:\s*([0-9.]+)"),
        "comb_area": _first(area, r"Combinational area:\s*([0-9.]+)"),
        "seq_area": _first(area, r"Noncombinational area:\s*([0-9.]+)"),
        "cells": _first(area, r"Number of cells:\s*([0-9]+)"),
        "crit_path_ns": _first(qor, r"Critical Path Length:\s*([0-9.-]+)"),
        "slack_ns": _first(qor, r"Critical Path Slack:\s*([0-9.-]+)"),
        "maxcap_nets": _first(qor, r"Max Cap Violations:\s*([0-9]+)"),
        "dyn_power": _power(power, "Total Dynamic Power"),
        "leak_power": _power(power, "Cell Leakage Power"),
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "run": str(rdir.relative_to(ROOT)),
    }
    if not row["area"]:
        row["status"] = "failed: no area report"
    elif row["slack_ns"] and float(row["slack_ns"]) < 0:
        row["status"] = "ok, timing violated"
    else:
        row["status"] = "ok"
    return row


def write_summary(rows: list[dict]) -> None:
    RUNS.mkdir(parents=True, exist_ok=True)
    table = {}
    if SUMMARY.is_file():
        with SUMMARY.open(newline="") as fh:
            table = {(r["point"], r["clock_ns"]): r for r in csv.DictReader(fh)}
    for r in rows:
        table[(r["point"], r["clock_ns"])] = r
    with SUMMARY.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(table.values(), key=lambda r: (r["point"], float(r["clock_ns"] or 0))))
    RESULTS_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SUMMARY, RESULTS_COPY)


def print_rows(rows: list[dict]) -> None:
    cols = ["point", "clock_ns", "status", "area", "cells", "crit_path_ns", "slack_ns", "maxcap_nets",
            "dyn_power", "leak_power"]
    t = [[str(r.get(c, "")) for c in cols] for r in rows]
    w = [max(len(c), *(len(x[i]) for x in t)) for i, c in enumerate(cols)] if t else [len(c) for c in cols]
    print("  ".join(c.ljust(n) for c, n in zip(cols, w)))
    for x in t:
        print("  ".join(v.ljust(n) for v, n in zip(x, w)))


# ---------------------------------------------------------------- commands
def cmd_list(args) -> int:
    for p in select(args.patterns):
        rams = rams_of(p)
        print(f"{p}  (top {top_of(p)})" + (f"  parked, RAM: {', '.join(rams)}" if rams else ""))
    return 0


def run_one(point: str, args, dc: str, lib: Path) -> dict | None:
    rams = rams_of(point)
    if rams and not args.with_ram:
        print(f"park {point}: it holds a RAM ({', '.join(rams)}); --with-ram runs it anyway", flush=True)
        return None if args.dry_run else parked_row(point, args.clock, rams)
    rdir = run_dir(point, args.clock)
    env = dict(os.environ, SYN_FILELIST=str(RTL / point / "filelist.f"), SYN_LIB=str(lib),
               SYN_CLOCK_NS=args.clock, SYN_CORES=str(args.cores))
    cmd = [dc, "-f", str(SCRIPT), "-output_log_file", "logs/dc_shell.log"]
    if args.dry_run:
        print(f"\n# {point}")
        for k in ("SYN_FILELIST", "SYN_LIB", "SYN_CLOCK_NS", "SYN_CORES"):
            print(f"export {k}='{env[k]}'")
        print(f"mkdir -p {rdir}/logs && cd {rdir} && {' '.join(cmd)}")
        return None
    if rdir.exists():
        shutil.rmtree(rdir)
    (rdir / "logs").mkdir(parents=True)
    print(f"run  {point} at {args.clock} ns in {rdir.relative_to(ROOT)}", flush=True)
    with (rdir / "logs" / "dc_stdout.log").open("w") as fh:
        subprocess.run(cmd, cwd=rdir, env=env, stdout=fh, stderr=subprocess.STDOUT, check=False)
    row = read_run(point, args.clock)
    print(f"done {point}: {row['status']}  area {row['area'] or '-'}  slack {row['slack_ns'] or '-'} ns"
          f"  errors {row['errors']}", flush=True)
    return row


def cmd_run(args) -> int:
    points = select(args.patterns)
    if not points:
        sys.exit("no rtl point matches (syn.py list shows them)")
    lib = Path(os.environ.get("SYN_LIB", DEFAULT_LIB)).resolve()
    dc = os.environ.get("DC_SHELL", "dc_shell")
    if not args.dry_run:
        if shutil.which(dc) is None:
            sys.exit(f"'{dc}' not found: load Design Compiler or set DC_SHELL")
        if not lib.is_file():
            sys.exit(f"no library at {lib}: put FreePDK45 next to this repo or set SYN_LIB")
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = [r for r in pool.map(lambda p: run_one(p, args, dc, lib), points) if r]
    if rows:
        write_summary(rows)
        print(f"\nwrote {SUMMARY.relative_to(ROOT)}")
        print_rows(rows)
    return 0 if rows and all(r["status"].startswith(("ok", "skipped")) for r in rows) or args.dry_run else 1


def cmd_summary(args) -> int:
    if not SUMMARY.is_file():
        sys.exit("no syn/runs/hls/summary.csv yet")
    with SUMMARY.open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh)
                if not args.patterns or any(fnmatch.fnmatchcase(r["point"], p) for p in args.patterns)]
    print_rows(rows)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("list", "run", "summary"):
        p = sub.add_parser(name)
        p.add_argument("patterns", nargs="*", help="globs over <tier>/<kernel>/<point>, e.g. done/vecadd/unopt_*")
        if name == "run":
            p.add_argument("--clock", default=DEFAULT_CLOCK, help=f"clock period in ns (default {DEFAULT_CLOCK})")
            p.add_argument("--cores", type=int, default=16, help="cores per DC run (default 16)")
            p.add_argument("-j", "--jobs", type=int, default=1, help="DC runs at once (each takes a license)")
            p.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
            p.add_argument("--with-ram", action="store_true",
                           help="also run points with a '# ram:' line (parked by default)")
    args = ap.parse_args()
    if args.cmd == "run" and not args.patterns:
        ap.error("run needs at least one pattern, e.g. done/vecadd/unopt_n512_w8")
    return {"list": cmd_list, "run": cmd_run, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
