#!/usr/bin/env python3
"""syn/syn.py - ASIC synthesis of bench points with Design Compiler, on one technology per run.

A point is a folder in hls-exercises' rtl/ (a checkout next to this repo,
../hls-exercises), named <tier>/<kernel>/<point> (e.g. done/vecadd/opt_w8, one
hardware point: case and W, every size runs on it), holding Vitis's Verilog and
a filelist.f that hls-exercises' bench/bench.py writes. Patterns are shell
globs over those names.

  pixi run syn list    [PATTERN ...] [--tech T] [--source S]
  pixi run syn run     PATTERN ... --tech T [--clock NS] [--cores N] [-j N] [--dry-run] [--source S]
  pixi run syn summary [PATTERN ...] [--tech T] [--source S]

--source picks where the points come from: hls (the default, as above) or
forge, snax-forge's accelerator bundles that forge/bundles.py (pixi run
forge-rtl) writes into rtl/forge/ in this repo. A forge point is a folder
there holding a bundle.json, named as an HLS point (e.g. done/dot/forge3_w4);
its top is bundle.json's "top", and run writes the point's filelist.f into
the run folder: '# top: <top>', then rtl/files.f's paths made absolute. Forge
RTL is SystemVerilog with clock clk_i and an asynchronous active-low reset
rst_ni (SYN_FORMAT, SYN_CLK_PORT, SYN_RST_PORT below). Runs go to
syn/runs/forge/<tech>/, results to results/forge/<tech>/, and a forge row has
more columns: recipe, W, snax_forge_commit (from point.json and
bundle.json), and csr_um2, ctrl_um2, datapath_um2 (the area of the wrapper's
three modules, bundle.json's "modules", from synth_dc_modules.csv's rows) and
glue_um2 = area_um2 minus the three (the cells DC leaves at the top's own
level); run reports a glue that is negative or above 1 % of the total.

A DC run that fails on a licence (LICENCE_ERROR in logs/dc_shell.log or
logs/dc_stdout.log) is rerun once (docs X17); the retry is printed and
counted. After a second licence failure the row's status is
"failed: licence (<the matched line>)".

A technology is a file syn/tech/<tech>.json: the library (.db path and the
library name it must hold), its time and capacitance units, the driving cell,
the output load in fF, the max transition in ns and the wire-load setting.
`run` needs --tech; list and summary take it as a filter. The constraints are
written in ns and fF; syn.py passes T_SCALE (library time units per ns) and
C_SCALE (library capacitance units per fF), and dc_syn.tcl stops before reading
any RTL if the library's own name or units differ from the tech file.

  syn/tech/nangate45.json  ../RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db
  syn/tech/nangate15.json  ../RTL_flow_Nangate15/tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db

Each run works in syn/runs/hls/<tech>/<tier>/<kernel>/<point>[_c<clock>]/ (the
clock tag only for a clock other than the default): WORK/, logs/, reports/,
out/ (the mapped netlist and sdf) and tech.json (the tech file, the resolved
values, the .db's md5 and what DC read from the library). Every run also writes
one row into syn/runs/hls/<tech>/summary.csv. git ignores syn/runs/ entirely;
results/hls/<tech>/ keeps what is committed: synth_dc.csv (a copy of the
summary), synth_dc_modules.csv (one row per hierarchical cell) and reports/
(KEPT_REPORTS of every run: area, power, reference, qor, tech.json, lib_info.txt).

A point whose filelist.f has '# ram:' lines holds a memory Vitis built (e.g.
DaCe's dot buffer). Neither library has RAM cells, and DC would build it from
flops, which takes hours and gives no fair area, so `run` parks it: no DC run,
and a summary row with status "skipped: needs a RAM macro (...)". --with-ram
runs it anyway (for when a macro or a black-box stub is in place).

Environment, all optional:
  DC_SHELL            dc_shell                 (Design Compiler)
  SYN_RTL             ../hls-exercises/rtl     (the hls points)
  SYN_RTL_FORGE       rtl/forge                (the forge points)
  SYN_LIB_NANGATE45   the nangate45 .db, instead of the tech file's lib_default
  SYN_LIB_NANGATE15   the nangate15 .db, instead of the tech file's lib_default
                      (in general: the tech file's lib_env)
syn.py passes DC: SYN_FILELIST, SYN_LIB_DB, SYN_LIB_NAME, SYN_TIME_UNIT,
SYN_CAP_UNIT, SYN_T_SCALE, SYN_C_SCALE, SYN_DRIVE_CELL, SYN_OUT_LOAD_FF,
SYN_MAX_TRANS_NS, SYN_WIRE_LOAD, SYN_CLOCK_NS, SYN_CORES, and from the
source SYN_FORMAT (verilog; forge sverilog), SYN_CLK_PORT (ap_clk; forge clk_i)
and SYN_RST_PORT (ap_rst_n; forge rst_ni).
Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYN = Path(__file__).resolve().parent
ROOT = SYN.parent
TECH_DIR = SYN / "tech"
# Per source: the points' folder, the HDL format, the clock and reset ports (dc_syn.tcl's defaults
# are the hls values). use_source() sets SOURCE, RTL, RUNS and RESULTS.
SOURCES = {
    "hls": {"rtl": Path(os.environ.get("SYN_RTL", ROOT.parent / "hls-exercises" / "rtl")),
            "format": "verilog", "clk": "ap_clk", "rst": "ap_rst_n"},
    "forge": {"rtl": Path(os.environ.get("SYN_RTL_FORGE", ROOT / "rtl" / "forge")),
              "format": "sverilog", "clk": "clk_i", "rst": "rst_ni"},
}
SOURCE = "hls"
RTL = SOURCES["hls"]["rtl"].resolve()
RUNS = SYN / "runs" / "hls"
RESULTS = ROOT / "results" / "hls"


def use_source(name: str) -> None:
    global SOURCE, RTL, RUNS, RESULTS
    SOURCE, RTL = name, SOURCES[name]["rtl"].resolve()
    RUNS, RESULTS = SYN / "runs" / name, ROOT / "results" / name

SCRIPT = SYN / "scripts" / "dc_syn.tcl"
DEFAULT_CLOCK = "10"
MAX_REPORT_BYTES = 1 << 20  # reports copied to results/ above this size are skipped
# What results/hls/<tech>/reports/ keeps of a run: what the area and energy model reads (area and
# power, per level of hierarchy and per cell type), the QoR, and what the run ran on. The rest
# (timing, constraints, ports, clocks, verbose power) stays in syn/runs/.
KEPT_REPORTS = ("area.rpt", "area_hierarchy.rpt", "reference.rpt", "power.rpt", "power_hierarchy.rpt",
                "qor.rpt", "tech.json", "lib_info.txt")

COLUMNS = ["point", "top", "tech", "clock_ns", "status", "errors", "area_um2", "comb_area_um2", "seq_area_um2",
           "buf_inv_area_um2", "cells", "seq_cells", "crit_path_ns", "slack_ns", "fmax_mhz", "maxcap_nets",
           "maxtrans_nets", "dyn_power_uw", "leak_power_uw", "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj",
           "e_total_pj", "leak_clk_uw", "leak_reg_uw", "leak_seq_uw", "leak_comb_uw", "lib_md5", "dc_version",
           "date", "run"]
FORGE_COLUMNS = ["recipe", "W", "snax_forge_commit",   # after COLUMNS, forge rows only
                 "csr_um2", "ctrl_um2", "datapath_um2", "glue_um2"]
GLUE_MAX = 0.01   # a glue share above this (or below 0) is reported, not failed
# A licence failure, as DC prints it (PITFALLS L1): 'Error: Design-Compiler Internal licensing error
# number -92 ...', 'Unable to obtain feature ...', 'Fatal: Design Compiler is not enabled. (DCSH-1)'.
# A bare 'license' is not enough: every good run's banner says 'license agreement' and its
# DesignWare table 'Licensed DW Building Blocks'.
LICENCE_ERROR = re.compile(r"^.*(licensing error|unable to obtain feature|is not enabled\. \(DCSH-1\)"
                           r"|^(error|fatal):.*licen[cs]e).*$", re.I | re.M)
MODULE_COLUMNS = ["point", "tech", "clock_ns", "path", "design", "area_um2", "comb_um2", "seq_um2", "bbox_um2",
                  "dyn_power_uw", "leak_power_uw"]
# power.rpt group -> CSV suffix
POWER_GROUPS = {"clock_network": "clk", "register": "reg", "sequential": "seq", "combinational": "comb"}
TECH_KEYS = ["name", "lib_env", "lib_default", "lib_name", "units", "drive_cell", "out_load_ff",
             "max_transition_ns", "wire_load", "fixes", "notes"]

SECONDS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}
FARADS = {"f": 1.0, "mf": 1e-3, "uf": 1e-6, "nf": 1e-9, "pf": 1e-12, "ff": 1e-15}
TO_UW = {"W": 1e6, "mW": 1e3, "uW": 1.0, "nW": 1e-3, "pW": 1e-6, "fW": 1e-9}


# ---------------------------------------------------------------- technologies
def tech_names() -> list[str]:
    return sorted(f.stem for f in TECH_DIR.glob("*.json"))


def load_tech(name: str) -> dict:
    tech = json.loads((TECH_DIR / f"{name}.json").read_text())
    missing = [k for k in TECH_KEYS if k not in tech]
    if missing or tech["name"] != name:
        sys.exit(f"syn/tech/{name}.json: missing {missing} or name is not '{name}'")
    if tech["fixes"]:
        sys.exit(f"syn/tech/{name}.json: fixes {tech['fixes']}: dc_syn.tcl applies none")
    return tech


def _unit(text: str, table: dict) -> float:
    """'1ns' -> 1e-9 (table SECONDS), '1ff' -> 1e-15 (table FARADS)."""
    m = re.fullmatch(r"\s*([0-9.]+)\s*([A-Za-z]+)\s*", text)
    if not m or m.group(2).lower() not in table:
        sys.exit(f"unit '{text}' not understood")
    return float(m.group(1)) * table[m.group(2).lower()]


def _num(x: float) -> str:
    return f"{x:.7g}"


def resolve(tech: dict) -> dict:
    """The values a run uses: the .db path, T_SCALE, C_SCALE."""
    env = os.environ.get(tech["lib_env"])
    lib = Path(env) if env else ROOT / tech["lib_default"]
    t_scale = 1e-9 / _unit(tech["units"]["time"], SECONDS)    # library time units per ns
    c_scale = 1e-15 / _unit(tech["units"]["cap"], FARADS)     # library cap units per fF
    return {"lib_db": str(lib.resolve()), "lib_from": tech["lib_env"] if env else "lib_default",
            "t_scale": _num(t_scale), "c_scale": _num(c_scale)}


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def summary_of(tech: str) -> Path:
    return RUNS / tech / "summary.csv"


def techs_with_summary(only: str | None) -> list[str]:
    names = [only] if only else tech_names()
    return [t for t in names if summary_of(t).is_file()]


# ---------------------------------------------------------------- points
def all_points() -> list[str]:
    if SOURCE == "forge":
        return sorted(str(f.parent.relative_to(RTL)) for f in RTL.rglob("bundle.json"))
    return sorted(str(f.parent.relative_to(RTL)) for f in RTL.glob("*/*/*/filelist.f"))


def columns() -> list[str]:
    return COLUMNS + FORGE_COLUMNS if SOURCE == "forge" else COLUMNS


def forge_json(point: str, name: str) -> dict:
    f = RTL / point / name
    return json.loads(f.read_text()) if f.is_file() else {}


def forge_filelist(point: str) -> list[str]:
    """The bundle's rtl/files.f, each path made absolute."""
    rtl = RTL / point / "rtl"
    return [str((rtl / ln.strip()).resolve()) for ln in (rtl / "files.f").read_text().splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def select(patterns: list[str]) -> list[str]:
    pts = all_points()
    if not patterns:
        return pts
    return [p for p in pts if any(fnmatch.fnmatchcase(p, pat) for pat in patterns)]


def top_of(point: str) -> str:
    if SOURCE == "forge":
        return forge_json(point, "bundle.json").get("top", "")
    m = re.search(r"^#\s*top:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)
    return m.group(1) if m else ""


def rams_of(point: str) -> list[str]:
    if SOURCE == "forge":
        return []
    return re.findall(r"^#\s*ram:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)


def parked_row(tech: str, point: str, clock: str, rams: list[str]) -> dict:
    row = {c: "" for c in columns()}
    row.update({"point": point, "top": top_of(point), "tech": tech, "clock_ns": clock,
                "status": f"skipped: needs a RAM macro ({', '.join(rams)}); {tech} has no RAM cells, "
                          "RAM1 builds one (OpenRAM)",
                "date": dt.datetime.now().isoformat(timespec="seconds")})
    return row


def point_tag(point: str, clock: str) -> str:
    return point + ("" if clock == DEFAULT_CLOCK else "_c" + clock.replace(".", "p"))


def run_dir(tech: str, point: str, clock: str) -> Path:
    return RUNS / tech / point_tag(point, clock)


# ---------------------------------------------------------------- reports
def _first(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.M)
    return m.group(1) if m else ""


def _power_uw(text: str, label: str) -> float | None:
    """'Total Dynamic Power    = 108.5871 uW  (100%)' -> 108.5871 (in uW)."""
    m = re.search(rf"{label}\s*=\s*([0-9.eE+-]+)\s*([munpf]?W)\b", text)
    return float(m.group(1)) * TO_UW[m.group(2)] if m else None


def _power_unit(text: str, label: str) -> float | None:
    """'Dynamic Power Units = 1uW    (derived ...)' -> 1.0 (uW per report unit)."""
    m = re.search(rf"{label}\s*=\s*([0-9.]+)\s*([munpf]?W)\b", text)
    return float(m.group(1)) * TO_UW[m.group(2)] if m else None


def lib_info(rdir: Path) -> dict:
    f = rdir / "reports" / "lib_info.txt"
    if not f.is_file():
        return {}
    return dict(ln.split(": ", 1) for ln in f.read_text().splitlines() if ": " in ln)


def power_groups(power: str) -> dict:
    """Per group: (internal, switching, leakage) in uW, from power.rpt's group table."""
    dyn, leak = _power_unit(power, "Dynamic Power Units"), _power_unit(power, "Leakage Power Units")
    out = {}
    if dyn is None or leak is None:
        return out
    for g in POWER_GROUPS:
        m = re.search(rf"^{g}\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", power, re.M)
        if m:
            out[g] = (float(m.group(1)) * dyn, float(m.group(2)) * dyn, float(m.group(3)) * leak)
    return out


def read_run(tech: dict, point: str, clock: str) -> dict:
    rdir = run_dir(tech["name"], point, clock)
    rep = rdir / "reports"
    t_scale = float(resolve(tech)["t_scale"])
    clock_ns = float(clock)

    def text(name: str) -> str:
        f = rep / name
        return f.read_text(errors="replace") if f.is_file() else ""

    area, qor, power = text("area.rpt"), text("qor.rpt"), text("power.rpt")
    log = rdir / "logs" / "dc_shell.log"
    log_text = log.read_text(errors="replace") if log.is_file() else ""
    info = lib_info(rdir)
    tj = rdir / "tech.json"
    row = {c: "" for c in columns()}
    row.update({
        "point": point, "top": top_of(point), "tech": tech["name"], "clock_ns": clock,
        "errors": len(re.findall(r"^Error:", log_text, re.M)) if log.is_file() else "",
        "area_um2": _first(area, r"Total cell area:\s*([0-9.]+)"),
        "comb_area_um2": _first(area, r"Combinational area:\s*([0-9.]+)"),
        "seq_area_um2": _first(area, r"Noncombinational area:\s*([0-9.]+)"),
        "buf_inv_area_um2": _first(area, r"Buf/Inv area:\s*([0-9.]+)"),
        "cells": _first(area, r"Number of cells:\s*([0-9]+)"),
        "seq_cells": _first(area, r"Number of sequential cells:\s*([0-9]+)"),
        "maxcap_nets": _first(qor, r"Max Cap Violations:\s*([0-9]+)"),
        "maxtrans_nets": _first(qor, r"Max Trans Violations:\s*([0-9]+)"),
        "lib_md5": json.loads(tj.read_text())["resolved"]["lib_md5"] if tj.is_file() else "",
        "dc_version": info.get("dc_version", ""),
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "run": str(rdir.relative_to(ROOT)),
    })
    if SOURCE == "forge":
        pj = forge_json(point, "point.json")
        row.update({"recipe": pj.get("recipe", ""), "W": pj.get("W", ""),
                    "snax_forge_commit": forge_json(point, "bundle.json").get("snax_forge_commit", "")})
        row.update(module_shares(tech, point, clock, row["area_um2"]))
    crit = _first(qor, r"Critical Path Length:\s*([0-9.eE+-]+)")
    slack = _first(qor, r"Critical Path Slack:\s*([0-9.eE+-]+)")
    if crit:
        row["crit_path_ns"] = _num(float(crit) / t_scale)
    if slack:
        s = float(slack) / t_scale
        row["slack_ns"] = _num(s)
        row["fmax_mhz"] = _num(1000.0 / (clock_ns - s))
    dyn, leak = _power_uw(power, "Total Dynamic Power"), _power_uw(power, "Cell Leakage Power")
    row["dyn_power_uw"] = "" if dyn is None else _num(dyn)
    row["leak_power_uw"] = "" if leak is None else _num(leak)
    groups = power_groups(power)
    energy_ok = True
    if len(groups) == len(POWER_GROUPS):
        e_total = 0.0
        for g, k in POWER_GROUPS.items():
            internal, switching, leakage = groups[g]
            e = (internal + switching) * clock_ns / 1000.0   # uW x ns = fJ; /1000 -> pJ
            e_total += e
            row[f"e_{k}_pj"] = _num(e)
            row[f"leak_{k}_uw"] = _num(leakage)
        row["e_total_pj"] = _num(e_total)
        if dyn is not None:
            e_dyn = dyn * clock_ns / 1000.0
            energy_ok = abs(e_total - e_dyn) <= 1e-3 * max(abs(e_dyn), 1e-9) + 1e-6
    if not row["area_um2"]:
        # at a line's start: dc_shell.log also echoes the script, whose puts line is indented
        mismatch = re.search(r"^dc_syn\.tcl: library mismatch", log_text, re.M) is not None
        lic = licence_error(rdir)
        row["status"] = ("failed: library mismatch (logs/dc_shell.log)" if mismatch
                         else f"failed: licence ({lic})" if lic else "failed: no area report")
    elif "No wire load specified" not in area:
        row["status"] = "failed: a wire-load model applied"
    elif not energy_ok:
        row["status"] = "failed: power groups do not sum to the total dynamic power"
    elif row["slack_ns"] and float(row["slack_ns"]) < 0:
        row["status"] = "ok, timing violated"
    else:
        row["status"] = "ok"
    return row


def licence_error(rdir: Path) -> str:
    """The first licence-failure line (LICENCE_ERROR) of the run's dc_shell.log or dc_stdout.log,
    the most telling first ('licensing error' over the rest); '' if none."""
    found = []
    for name in ("dc_shell.log", "dc_stdout.log"):
        f = rdir / "logs" / name
        if f.is_file():
            found += [m.group(0).strip() for m in LICENCE_ERROR.finditer(f.read_text(errors="replace"))]
    found.sort(key=lambda x: "licensing error" not in x.lower())
    return found[0] if found else ""


def module_shares(tech: dict, point: str, clock: str, total: str) -> dict:
    """forge: csr_um2, ctrl_um2, datapath_um2 (bundle.json's three modules, by design name, from
    read_modules) and glue_um2 = total - the three; '' where a module has no row."""
    designs = list(forge_json(point, "bundle.json").get("modules", {}))
    keys = ["csr_um2", "ctrl_um2", "datapath_um2"]
    area = {m["design"]: float(m["area_um2"]) for m in read_modules(tech, point, clock)}
    out = {k: "" for k in [*keys, "glue_um2"]}
    if len(designs) != 3 or not total:
        return out
    for k, d in zip(keys, designs):
        if d in area:
            out[k] = f"{area[d]:.4f}"
    if all(out[k] for k in keys):
        out["glue_um2"] = f"{float(total) - sum(float(out[k]) for k in keys):.4f}"
    return out


def _floats(xs: list[str]) -> bool:
    try:
        [float(x) for x in xs]
        return True
    except ValueError:
        return False


def read_modules(tech: dict, point: str, clock: str) -> list[dict]:
    """area_hierarchy.rpt's hierarchical cells joined with power_hierarchy.rpt, by path."""
    rep = run_dir(tech["name"], point, clock) / "reports"
    af, pf = rep / "area_hierarchy.rpt", rep / "power_hierarchy.rpt"
    if not af.is_file() or not pf.is_file():
        return []
    # area: 'path  abs_total  percent  comb  noncomb  bbox  design'
    rows = []
    for ln in af.read_text(errors="replace").split("Hierarchical cell", 1)[-1].splitlines():
        t = ln.split()
        if len(t) == 7 and _floats(t[1:6]):
            rows.append({"path": t[0], "design": t[6], "area_um2": t[1], "comb_um2": t[3], "seq_um2": t[4],
                         "bbox_um2": t[5]})
    # power: instance names indented two spaces per level, '<inst> (<design>)' below the top, then
    # switching, internal, leakage, total, percent; switching and internal in dynamic units, leakage in
    # leakage units (3 digits: the hierarchical report ignores -significant_digits)
    power = pf.read_text(errors="replace")
    dyn, leak = _power_unit(power, "Dynamic Power Units"), _power_unit(power, "Leakage Power Units")
    pw, stack = {}, []
    body = power.split("Hierarchy", 1)[-1] if dyn is not None and leak is not None else ""
    for ln in body.splitlines():
        m = re.match(r"^( *)(\S+)(?: \((\S+)\))?\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+"
                     r"([0-9.eE+-]+)\s+([0-9.]+)\s*$", ln)
        if not m:
            continue
        depth = len(m.group(1)) // 2
        stack[depth:] = [m.group(2)]
        path = stack[0] if depth == 0 else "/".join(stack[1:])
        pw[path] = (float(m.group(4)) * dyn + float(m.group(5)) * dyn, float(m.group(6)) * leak)
    out = []
    for r in rows:
        p = pw.get(r["path"])
        out.append({"point": point, "tech": tech["name"], "clock_ns": clock, **r,
                    "dyn_power_uw": _num(p[0]) if p else "", "leak_power_uw": _num(p[1]) if p else ""})
    return out


def copy_reports(tech: str, point: str, clock: str) -> list[str]:
    """KEPT_REPORTS into results/; returns what was skipped."""
    rdir = run_dir(tech, point, clock)
    dest = RESULTS / tech / "reports" / point_tag(point, clock)
    if dest.exists():
        shutil.rmtree(dest)
    files = [rdir / name if name == "tech.json" else rdir / "reports" / name for name in KEPT_REPORTS]
    skipped = []
    for f in files:
        if not f.is_file():
            continue
        if f.stat().st_size > MAX_REPORT_BYTES:
            skipped.append(f"{f.name} ({f.stat().st_size} B)")
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest / f.name)
    if skipped:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "skipped.txt").write_text(
            f"Over {MAX_REPORT_BYTES} B, kept only in {rdir.relative_to(ROOT)}/:\n" + "\n".join(skipped) + "\n")
    return skipped


def _merge(path: Path, columns: list[str], key, rows: list[dict], drop: set) -> None:
    table = []
    if path.is_file():
        with path.open(newline="") as fh:
            table = [r for r in csv.DictReader(fh) if key(r) not in drop]
    table += rows
    table.sort(key=lambda r: (r["point"], float(r["clock_ns"] or 0), r.get("path", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)


def write_summary(tech: dict, rows: list[dict]) -> None:
    """The run summary, its copy in results/, the modules CSV and the reports, all in step."""
    name = tech["name"]
    key = lambda r: (r["point"], r["clock_ns"])  # noqa: E731
    done = {key(r) for r in rows}
    _merge(summary_of(name), columns(), key, rows, done)
    out = RESULTS / name
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(summary_of(name), out / "synth_dc.csv")
    modules = []
    for r in rows:
        if r["run"]:
            modules += read_modules(tech, r["point"], r["clock_ns"])
            skipped = copy_reports(name, r["point"], r["clock_ns"])
            if skipped:
                print(f"results: {r['point']}: skipped over 1 MB: {', '.join(skipped)}")
        else:
            stale = out / "reports" / point_tag(r["point"], r["clock_ns"])
            if stale.exists():
                shutil.rmtree(stale)
    _merge(out / "synth_dc_modules.csv", MODULE_COLUMNS, key, modules, done)


def print_rows(rows: list[dict]) -> None:
    cols = ["point", "tech", "clock_ns", "status", "area_um2", "cells", "crit_path_ns", "slack_ns", "fmax_mhz",
            "dyn_power_uw", "leak_power_uw", "e_total_pj"]
    t = [[str(r.get(c, "")) for c in cols] for r in rows]
    w = [max(len(c), *(len(x[i]) for x in t)) for i, c in enumerate(cols)] if t else [len(c) for c in cols]
    print("  ".join(c.ljust(n) for c, n in zip(cols, w)))
    for x in t:
        print("  ".join(v.ljust(n) for v, n in zip(x, w)))


def summary_rows(tech: str | None, patterns: list[str]) -> list[dict]:
    rows = []
    for t in techs_with_summary(tech):
        with summary_of(t).open(newline="") as fh:
            rows += [r for r in csv.DictReader(fh)
                     if not patterns or any(fnmatch.fnmatchcase(r["point"], p) for p in patterns)]
    return rows


# ---------------------------------------------------------------- commands
def cmd_list(args) -> int:
    if args.tech:
        for r in summary_rows(args.tech, args.patterns):
            print(f"{r['point']}  {r['tech']}  {r['clock_ns']} ns  {r['status']}")
        return 0
    for p in select(args.patterns):
        rams = rams_of(p)
        print(f"{p}  (top {top_of(p)})" + (f"  parked, RAM: {', '.join(rams)}" if rams else ""))
    return 0


def dc_env(tech: dict, res: dict, point: str, args) -> dict:
    src = SOURCES[SOURCE]
    filelist = (run_dir(tech["name"], point, args.clock) / "filelist.f" if SOURCE == "forge"
                else RTL / point / "filelist.f")
    return {
        "SYN_FILELIST": str(filelist),
        "SYN_LIB_DB": res["lib_db"],
        "SYN_LIB_NAME": tech["lib_name"],
        "SYN_TIME_UNIT": tech["units"]["time"],
        "SYN_CAP_UNIT": tech["units"]["cap"],
        "SYN_T_SCALE": res["t_scale"],
        "SYN_C_SCALE": res["c_scale"],
        "SYN_DRIVE_CELL": tech["drive_cell"],
        "SYN_OUT_LOAD_FF": _num(tech["out_load_ff"]),
        "SYN_MAX_TRANS_NS": _num(tech["max_transition_ns"]),
        "SYN_WIRE_LOAD": tech["wire_load"],
        "SYN_CLOCK_NS": args.clock,
        "SYN_CORES": str(args.cores),
        "SYN_FORMAT": src["format"],
        "SYN_CLK_PORT": src["clk"],
        "SYN_RST_PORT": src["rst"],
    }


RETRIES: list[str] = []          # points rerun on a licence error, this invocation
RETRIES_LOCK = threading.Lock()


def run_one(point: str, args, dc: str, tech: dict, res: dict) -> dict | None:
    name = tech["name"]
    rams = rams_of(point)
    if rams and not args.with_ram:
        print(f"park {point}: it holds a RAM ({', '.join(rams)}); --with-ram runs it anyway", flush=True)
        return None if args.dry_run else parked_row(name, point, args.clock, rams)
    rdir = run_dir(name, point, args.clock)
    syn_env = dc_env(tech, res, point, args)
    cmd = [dc, "-f", str(SCRIPT), "-output_log_file", "logs/dc_shell.log"]
    if args.dry_run:
        print(f"\n# {point} on {name}")
        if SOURCE == "forge":
            print(f"# run writes {syn_env['SYN_FILELIST']}: '# top: {top_of(point)}', "
                  f"then {len(forge_filelist(point))} files from {RTL / point / 'rtl' / 'files.f'}")
        for k, v in syn_env.items():
            print(f"export {k}='{v}'")
        print(f"mkdir -p {rdir}/logs && cd {rdir} && {' '.join(cmd)}")
        return None
    for attempt in (1, 2):
        if rdir.exists():
            shutil.rmtree(rdir)
        (rdir / "logs").mkdir(parents=True)
        if SOURCE == "forge":
            Path(syn_env["SYN_FILELIST"]).write_text(
                f"# top: {top_of(point)}\n" + "".join(f"{f}\n" for f in forge_filelist(point)))
        print(f"run  {point} on {name} at {args.clock} ns in {rdir.relative_to(ROOT)}"
              + (" (licence retry)" if attempt == 2 else ""), flush=True)
        with (rdir / "logs" / "dc_stdout.log").open("w") as fh:
            rc = subprocess.run(cmd, cwd=rdir, env=dict(os.environ, **syn_env), stdout=fh,
                                stderr=subprocess.STDOUT, check=False).returncode
        lic = licence_error(rdir)
        if not lic or attempt == 2:
            break
        with RETRIES_LOCK:
            RETRIES.append(point)
        print(f"retry {point} on {name}: licence error: {lic}", flush=True)
    (rdir / "tech.json").write_text(json.dumps({
        "tech_file": str((TECH_DIR / f"{name}.json").relative_to(ROOT)),
        "tech": tech,
        "resolved": {**res, "clock_ns": args.clock, "cores": args.cores,
                     "dc_env": syn_env, "dc_returncode": rc},
        "dc_lib_info": lib_info(rdir),
    }, indent=2) + "\n")
    row = read_run(tech, point, args.clock)
    print(f"done {point} on {name}: {row['status']}  area {row['area_um2'] or '-'} um2"
          f"  slack {row['slack_ns'] or '-'} ns  errors {row['errors']}", flush=True)
    glue = row.get("glue_um2", "")
    if SOURCE == "forge" and row["area_um2"] and not glue:
        gone = [k for k in ("csr_um2", "ctrl_um2", "datapath_um2") if not row[k]]
        print(f"glue {point} on {name}: no glue, no module row for {', '.join(gone)}", flush=True)
    if glue and (float(glue) < 0 or float(glue) > GLUE_MAX * float(row["area_um2"])):
        print(f"glue {point} on {name}: {glue} um2 of {row['area_um2']} "
              f"({100 * float(glue) / float(row['area_um2']):.3f} %): negative or above "
              f"{100 * GLUE_MAX:g} %", flush=True)
    return row


def cmd_run(args) -> int:
    points = select(args.patterns)
    if not points:
        sys.exit("no rtl point matches (syn.py list shows them)")
    tech = load_tech(args.tech)
    res = resolve(tech)
    lib = Path(res["lib_db"])
    dc = os.environ.get("DC_SHELL", "dc_shell")
    if not args.dry_run:
        if shutil.which(dc) is None:
            sys.exit(f"'{dc}' not found: load Design Compiler or set DC_SHELL")
        if not lib.is_file():
            sys.exit(f"no library at {lib}: put it at {tech['lib_default']} (from the repo root) "
                     f"or set {tech['lib_env']}")
        res["lib_md5"] = md5_of(lib)
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        rows = [r for r in pool.map(lambda p: run_one(p, args, dc, tech, res), points) if r]
    if rows:
        write_summary(tech, rows)
        print(f"\nwrote {summary_of(tech['name']).relative_to(ROOT)} and {(RESULTS / tech['name']).relative_to(ROOT)}/")
        print_rows(rows)
    if not args.dry_run:
        print(f"licence retries: {len(RETRIES)}" + (f" ({', '.join(RETRIES)})" if RETRIES else ""))
    return 0 if rows and all(r["status"].startswith(("ok", "skipped")) for r in rows) or args.dry_run else 1


def cmd_summary(args) -> int:
    if not techs_with_summary(args.tech):
        sys.exit(f"no syn/runs/{SOURCE}/{args.tech or '<tech>'}/summary.csv yet")
    print_rows(summary_rows(args.tech, args.patterns))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    techs = tech_names()
    for name in ("list", "run", "summary"):
        p = sub.add_parser(name)
        p.add_argument("patterns", nargs="*", help="globs over <tier>/<kernel>/<point>, e.g. done/vecadd/unopt_*")
        p.add_argument("--source", choices=sorted(SOURCES), default="hls",
                       help="hls (hls-exercises' rtl/, the default) or forge (rtl/forge/, pixi run forge-rtl)")
        if name == "run":
            p.add_argument("--tech", required=True, choices=techs, help="technology: one of syn/tech/*.json")
            p.add_argument("--clock", default=DEFAULT_CLOCK, help=f"clock period in ns (default {DEFAULT_CLOCK})")
            p.add_argument("--cores", type=int, default=16, help="cores per DC run (default 16)")
            p.add_argument("-j", "--jobs", type=int, default=1, help="DC runs at once (each takes a license)")
            p.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
            p.add_argument("--with-ram", action="store_true",
                           help="also run points with a '# ram:' line (parked by default)")
        else:
            p.add_argument("--tech", choices=techs, help="only this technology's runs")
    args = ap.parse_args()
    use_source(args.source)
    if args.cmd == "run" and not args.patterns:
        ap.error("run needs at least one pattern, e.g. done/vecadd/unopt_n512_w8")
    return {"list": cmd_list, "run": cmd_run, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
