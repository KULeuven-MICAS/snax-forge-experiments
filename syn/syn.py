#!/usr/bin/env python3
"""syn/syn.py - ASIC synthesis of bench points with Design Compiler, on one technology per run.

A point is a folder named <tier>/<kernel>/<case>_w<W> (e.g. done/vecadd/opt_w8, one
hardware point: case and W, every size runs on it) holding an HLS tool's Verilog and a
filelist.f ('# top: <module>', then the files). Patterns are shell globs over those names.

  pixi run syn list         [PATTERN ...] [--tech T] [--source S]
  pixi run syn run          PATTERN ... --tech T [--clock NS] [--cores N] [-j N] [--dry-run] [--sdf] [--clk-gate]
                            [--source S]
  pixi run syn summary      [PATTERN ...] [--tech T] [--source S]
  pixi run syn check-ports  [PATTERN ...] [--source S]

--source picks where the points come from (docs X39):

  hls    Vitis (the default): hls-exercises' rtl/ (a checkout next to this repo,
         ../hls-exercises), the filelist.f that bench/bench.py writes; cases opt and
         dace; clock ap_clk, reset ap_rst_n
  bambu  Bambu: the same rtl/ root, the filelist.f that bench/bambu.py writes; case
         bambu; clock clock, reset reset. A bambu row has more columns: ctrl_um2 (the
         controller_* instance with its children), datapath_um2 (the datapath_*
         instance with its children) and glue_um2 = area_um2 minus the two (docs X41),
         from synth_dc_modules.csv's rows; a point without exactly one controller_* and
         one datapath_* fails
  xls    Google XLS: dslx-exercises' rtl/ (../dslx-exercises); case xls; clock clk,
         reset rst

For these three, list shows only the folders named <case>_w<W> with <case> in the
source's cases and W <= MAX_W (16, docs X38): Vitis's unopt_w*, any *_w32, a per-size
folder (opt_n512_w8) or a clock variant (opt_w8_c10) is not listed.

Or forge, snax-forge's accelerator bundles that forge/bundles.py (pixi run
forge-rtl) writes into rtl/forge/ in this repo. A forge point is a zip
there holding a bundle.json, rtl/forge/<point>.zip, named as an HLS point
(e.g. done/dot/forge3_w4); its top is bundle.json's "top", and run unpacks
the zip into tmp/ for DC (deleted after) and writes the point's filelist.f
into the run folder: '# top: <top>', then rtl/files.f's paths in the
unpacked bundle. Forge
RTL is SystemVerilog with clock clk_i and an asynchronous active-low reset
rst_ni (SYN_FORMAT, SYN_CLK_PORT, SYN_RST_PORT below). Runs go to
syn/runs/forge/<tech>/, results to results/forge/<tech>/, and a forge row has
more columns: recipe, W, snax_forge_commit (from point.json and
bundle.json), and csr_um2, ctrl_um2, datapath_um2 (the area of the wrapper's
three modules, bundle.json's "modules", from synth_dc_modules.csv's rows) and
glue_um2 = area_um2 minus the three (the cells DC leaves at the top's own
level); run reports a glue that is negative or above 1 % of the total.

Or char (CHAR1): snax-forge's catalogue blocks alone, which char/blocks.py
(pixi run char-rtl) writes into rtl/char/ in this repo. A char point is a
zip there holding an emitted.json, rtl/char/<point>.zip, named
<block>/<case>_w<W> (e.g. tree/add_w8); its top is emitted.json's "top",
and run unpacks it as a forge bundle and writes the point's filelist.f into
the run folder: '# top: <top>', then emitted.json's "files". Char RTL is SystemVerilog with clock clock and an asynchronous
active-high reset reset, kept ideal as the others. Runs go to
syn/runs/char/<tech>/, results to results/char/<tech>/ under other names,
char_synth.csv and char_synth_modules.csv (columns as synth_dc.csv and
synth_dc_modules.csv), and a char row has more columns, from point.json:
datapath, lanes, depth, op, form (a Mac's acc, plain or reg) and
snax_forge_commit.

Or streamer and xbar (STRM1, docs X52): snax_cluster's streamer reader and TCDM
sparse interconnect, which strm/gen.py (pixi run strm-rtl) writes into
rtl/streamer/ and rtl/xbar/ in this repo, one zip per point named after the
grid (streamer d<depth>_l<loops>_c<channels>, xbar i<inputs>_b<banks>) holding
config.json, point.json, filelist.f ('# top: <top>', then <top>.sv) and the SV.
run unpacks the zip into tmp/ and writes the run folder's filelist.f with the
unpacked file's path. The RTL is SystemVerilog with clock clock and reset reset
(the reader's asynchronous, the interconnect's synchronous; both active high,
kept ideal). Runs go to syn/runs/<source>/<tech>/, results to
results/<source>/<tech>/synth_dc.csv and synth_dc_modules.csv; a row adds the
grid's params (streamer depth, loops, channels; xbar inputs, banks),
rtl_flop_bits (the register and memory bits the bundle's RTL declares,
strm/gen.py's flop_bits), opt1207 (DC's unloaded registers removed, the unique
OPT-1207 lines) and snax_cluster_commit. The flop check: a row whose seq_cells
differs from rtl_flop_bits is "failed: flop check (...)". run starts the
largest points first (xbar by inputs x banks, streamer by channels x depth,
then loops).

Or xbar_mix (CSYN1 R3c, docs X70): an xbar point's SparseInterconnect inside
strm/xbar_mix.py's wrapper, top xbar_mix, with read-only and write-only inputs
(rtl/xbar_mix/i<inputs>_b<banks>_r<ro>_w<wo>.zip, strm/gen.py --set xbar_mix),
run as xbar is. Its rows add inputs, banks, ro, wo, rtl_flop_bits (the
SparseInterconnect's: the wrapper adds none), flops_removed (rtl_flop_bits minus
DC's flops), opt1207 and snax_cluster_commit. Flops DC removes are reported per
point, not failed; a row with more flops than the RTL declares fails.

Or cluster (CSYN1 Part B, docs X67): a snax-forge design in snax_cluster's whole
cluster, top snax_forge_cluster_wrapper (clock clk_i, reset rst_ni, asynchronous).
Its DC run is driven by cluster/cluster.py (pixi run cluster syn <point>), which
builds the cluster's file list with snax_cluster's gen-syn and calls this
module's dc_env, run_dc, finish_run and write_summary; `syn run --source cluster`
refuses and points there, list and summary work as for the others. Runs go to
syn/runs/cluster/<tech>/<point>, results to results/cluster/<tech>/synth_dc.csv
(no modules CSV), and a row adds recipe, W, snax_forge_commit,
snax_cluster_commit, macro_um2 (the black boxes' area) and macros (instances per
macro). Its gates fail the row: an unresolved reference (cluster_check.rpt or a
LINK-5 line in the log), a black box that is not one of the point's macros, a
macro count other than points.json's srams, a cell from a library other than the
technology's and the macros'. Its zip and report zip keep cluster_check.rpt,
cluster_ports.rpt and tree.txt as well, and the report zip keeps
area_hierarchy.rpt and power_hierarchy.rpt whatever their size.

Before DC starts, the port guard reads the top's port list from the point's Verilog
files and checks that the source's clock and reset ports are on it; if not, the row is
"failed: no clock port <name> on <top>" (or reset) and DC is not run. check-ports runs
the guard alone on every listed point, one line per point.

After compile, dc_syn.tcl measures the worst setup slack of four path classes (docs X40)
with get_timing_paths -from/-to only, into reports/path_classes.rpt: in2reg, reg2reg,
reg2out and in2out, inputs being every input but the clock and the reset, registers
their clock pins as start points and their data pins as endpoints. Every row has them
as slack_in2reg_ns, slack_reg2reg_ns, slack_reg2out_ns and slack_in2out_ns; a class
with no path is empty.

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

Each run works in syn/runs/<source>/<tech>/<tier>/<kernel>/<point>[_c<clock>][_cg]/ (the
clock tag only for a clock other than the default, _cg only with --clk-gate): WORK/, logs/, reports/,
out/ (the mapped netlist; the sdf only with --sdf, docs X69) and tech.json (the tech file, the resolved
values, the .db's md5 and what DC read from the library). When DC ends, the
folder is packed into <point>[_c<clock>].zip next to it (KEEP_RUN: the mapped
netlist, KEPT_REPORTS, dc_shell.log and dc_stdout.log; docs X51), the zip is
test-read and the folder deleted, scratch with it; everything that reads a run
afterwards reads the zip. Every run also writes one row into
syn/runs/<source>/<tech>/summary.csv, whose run column names the folder (its
zip is <run>.zip). git ignores syn/runs/ entirely; results/<source>/<tech>/
keeps what is committed: synth_dc.csv (a copy of the summary),
synth_dc_modules.csv (one row per hierarchical cell) and per run one zip
reports/<tier>/<kernel>/<point>[_c<clock>][_cg].zip (KEPT_REPORTS: area, power,
reference, qor, path classes, tech.json, lib_info.txt; with clock gating the three
clock_gating*.rpt, whatever their size).

--clk-gate (X79) turns on dc_syn.tcl's CLK_GATE_ENABLE (SYN_CLK_GATE_ENABLE=1):
clock_gating.tcl's style, compile_ultra -no_autoungroup -gate_clock and the
clock-gating reports. Such a run is tagged _cg, its rows (synth_dc.csv and the
modules CSV) have clk_gate 1, and it never replaces the ungated run of the same
point: the CSVs merge on point, clock_ns and clk_gate (empty reads as 0). A
cluster point turns it on with points.json's "syn": {"clk_gate": true}
(cluster/cluster.py); its own name tells it apart, so it gets no _cg tag, and its
row's clk_gate comes from the environment DC ran with (tech.json).

A point whose filelist.f has '# ram:' lines holds a memory Vitis built (e.g.
DaCe's dot buffer). Neither library has RAM cells. On nangate45 (hls source) each
such RAM is swapped for an SRAM macro (X62, ram/vitis_ram.py): the macro of the
instance's AddressRange x DataWidth (pixi run ram lib, made when missing), a
wrapper with Vitis's module name and ports in the run folder, the run's own
filelist.f, and the macro's .db linked beside the library (SYN_RAM_DBS); the row's
ram_um2 is the macros' area and ram_kind "macro". Where no macro can be made
(another technology, a size CACTI refuses such as 16 words) `run` parks the
point: no DC run, and a row "skipped: needs a RAM macro (...)". --with-ram runs it
instead with Vitis's RAM as written, built from flops: ram_kind "flops", ram_um2
the RAM modules' area.

Environment, all optional:
  DC_SHELL            dc_shell                 (Design Compiler)
  SYN_RTL             ../hls-exercises/rtl     (the hls and bambu points)
  SYN_RTL_XLS         ../dslx-exercises/rtl    (the xls points)
  SYN_RTL_FORGE       rtl/forge                (the forge points' zips)
  SYN_RTL_CHAR        rtl/char                 (the char points' zips)
  SYN_RTL_STREAMER    rtl/streamer             (the streamer points' zips)
  SYN_RTL_XBAR        rtl/xbar                 (the xbar points' zips)
  SYN_RTL_XBAR_MIX    rtl/xbar_mix             (the xbar_mix points' zips)
  SYN_RTL_CLUSTER     rtl/cluster              (the cluster points' bundle zips, cluster/cluster.py)
  SYN_LIB_NANGATE45   the nangate45 .db, instead of the tech file's lib_default
  SYN_LIB_NANGATE15   the nangate15 .db, instead of the tech file's lib_default
                      (in general: the tech file's lib_env)
syn.py passes DC: SYN_FILELIST, SYN_LIB_DB, SYN_LIB_NAME, SYN_TIME_UNIT,
SYN_CAP_UNIT, SYN_T_SCALE, SYN_C_SCALE, SYN_DRIVE_CELL, SYN_OUT_LOAD_FF,
SYN_MAX_TRANS_NS, SYN_WIRE_LOAD, SYN_CLOCK_NS, SYN_CORES, and from the
source SYN_FORMAT (verilog; forge, char, streamer, xbar and xbar_mix sverilog),
SYN_CLK_PORT (ap_clk; bambu clock; xls clk; forge clk_i; char, streamer, xbar
and xbar_mix clock) and SYN_RST_PORT (ap_rst_n; bambu reset; xls rst; forge
rst_ni; char, streamer, xbar and xbar_mix reset); with --sdf, SYN_WRITE_SDF=1 (dc_syn.tcl
writes the SDF only then, X69); with --clk-gate, SYN_CLK_GATE_ENABLE=1 (X79). The cluster source also sets SYN_FLIST_TCL,
SYN_TOP, SYN_EXTRA_SDC, SYN_POST_TCL and SYN_RAM_DBS in place of SYN_FILELIST,
and SYN_IGNORE_LOAD=1 (dc_syn.tcl's optional hooks).
Standard library and arc/arc.py only.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fnmatch
import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SYN = Path(__file__).resolve().parent
ROOT = SYN.parent
sys.path.insert(0, str(ROOT / "arc"))
import arc  # noqa: E402  arc/arc.py: every output is one zip per point (X51)
sys.path.insert(0, str(ROOT / "ram"))
import vitis_ram  # noqa: E402  ram/vitis_ram.py: a Vitis RAM swapped for an SRAM macro (X62)

TECH_DIR = SYN / "tech"
# Per source: the points' folder, the HDL format, the clock and reset ports (dc_syn.tcl's defaults
# are the hls values) and, for the HLS tools, the cases listed (folders <case>_w<W>).
# use_source() sets SOURCE, RTL, RUNS and RESULTS.
HLS_RTL = Path(os.environ.get("SYN_RTL", ROOT.parent / "hls-exercises" / "rtl"))
SOURCES = {
    "hls": {"rtl": HLS_RTL, "format": "verilog", "clk": "ap_clk", "rst": "ap_rst_n", "cases": ("opt", "dace")},
    "bambu": {"rtl": HLS_RTL, "format": "verilog", "clk": "clock", "rst": "reset", "cases": ("bambu",)},
    "xls": {"rtl": Path(os.environ.get("SYN_RTL_XLS", ROOT.parent / "dslx-exercises" / "rtl")),
            "format": "verilog", "clk": "clk", "rst": "rst", "cases": ("xls",)},
    "forge": {"rtl": Path(os.environ.get("SYN_RTL_FORGE", ROOT / "rtl" / "forge")),
              "format": "sverilog", "clk": "clk_i", "rst": "rst_ni"},
    "char": {"rtl": Path(os.environ.get("SYN_RTL_CHAR", ROOT / "rtl" / "char")),
             "format": "sverilog", "clk": "clock", "rst": "reset"},
    "streamer": {"rtl": Path(os.environ.get("SYN_RTL_STREAMER", ROOT / "rtl" / "streamer")),
                 "format": "sverilog", "clk": "clock", "rst": "reset"},
    "xbar": {"rtl": Path(os.environ.get("SYN_RTL_XBAR", ROOT / "rtl" / "xbar")),
             "format": "sverilog", "clk": "clock", "rst": "reset"},
    # CSYN1 R3c (X70): an xbar point's SparseInterconnect in strm/xbar_mix.py's wrapper, top xbar_mix
    "xbar_mix": {"rtl": Path(os.environ.get("SYN_RTL_XBAR_MIX", ROOT / "rtl" / "xbar_mix")),
                 "format": "sverilog", "clk": "clock", "rst": "reset"},
    # CSYN1 Part B (X67): driven by cluster/cluster.py, not by `syn run`; the point's bundle zip names it
    "cluster": {"rtl": Path(os.environ.get("SYN_RTL_CLUSTER", ROOT / "rtl" / "cluster")),
                "format": "sverilog", "clk": "clk_i", "rst": "rst_ni", "top": "snax_forge_cluster_wrapper"},
}
# The sources whose points are bundle zips in rtl/<source>/ (unpacked into tmp/ for DC); STRM: strm/gen.py's
BUNDLED = ("forge", "char", "streamer", "xbar", "xbar_mix")
STRM = ("streamer", "xbar", "xbar_mix")
# The results/<source>/<tech>/ CSVs: synth_dc.csv and synth_dc_modules.csv, but for char
RESULT_CSVS = {"char": ("char_synth.csv", "char_synth_modules.csv")}
# X38: at most 16 64-bit channels per stream, so W <= 16 for every HLS case; W = 32 is retired
MAX_W = 16
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
# X79: clock gating for this invocation (--clk-gate): runs tagged _cg, rows with clk_gate 1. use_clk_gate() sets it.
CLK_GATE = False
CG_TAG = "_cg"
# dc_syn.tcl's clock-gating reports (X79): kept with the others, whatever their size, where the run wrote them
CG_REPORTS = ("clock_gating.rpt", "clock_gating_elements.rpt", "clock_gating_ungated.rpt")


def use_clk_gate(on: bool) -> None:
    global CLK_GATE
    CLK_GATE = on


def gate_flag(row: dict) -> str:
    """A row's clk_gate as a key: '1' or '0' (empty, a row from before X79, reads as 0)."""
    return "1" if str(row.get("clk_gate", "")) == "1" else "0"
MAX_REPORT_BYTES = 1 << 20  # reports copied to results/ above this size are skipped
# What results/<source>/<tech>/reports/ keeps of a run: what the area and energy model reads (area and
# power, per level of hierarchy and per cell type), the QoR, the path classes, and what the run ran on. The rest
# (timing, constraints, ports, clocks, verbose power) stays in syn/runs/.
KEPT_REPORTS = ("area.rpt", "area_hierarchy.rpt", "reference.rpt", "power.rpt", "power_hierarchy.rpt",
                "qor.rpt", "path_classes.rpt", "tech.json", "lib_info.txt", *CG_REPORTS)
# What a run's zip, syn/runs/<source>/<tech>/<point>[_c<clock>].zip, keeps of its folder (X51): the mapped netlist
# (sim/pwr.py and pt_power.tcl read it), KEPT_REPORTS (tech.json at the top, the rest in reports/) and the two DC
# logs (errors and licence lines). The rest (WORK/, alib-*/, the .sdf if --sdf wrote one, default.svf, the other reports, command logs,
# a forge or char point's filelist.f into the unpacked bundle) is scratch, deleted with the folder.
KEEP_RUN = ("out/*_mapped.v", "tech.json", "logs/dc_shell.log", "logs/dc_stdout.log", "ram/*.v",
            *(f"reports/{r}" for r in KEPT_REPORTS if r != "tech.json"))
# The cluster source keeps more (X67): its gate and port reports, the area tree, and in the run zip what it ran
# from; its report zip keeps the hierarchical area and power reports whatever their size (CSYN1 R3b reads them)
CLUSTER_REPORTS = ("cluster_check.rpt", "cluster_ports.rpt")
CLUSTER_RUN_FILES = ("syn_flist.tcl", "cluster.sdc", "tc_sram_impl.sv", "tree.txt")
UNLIMITED_REPORTS = {"cluster": ("area_hierarchy.rpt", "power_hierarchy.rpt")}
TOP_MEMBERS = ("tech.json", "tree.txt")   # report zip members at the run zip's top, not in reports/


def kept_reports() -> tuple:
    """KEPT_REPORTS, and for the cluster source its reports and tree.txt too."""
    return KEPT_REPORTS + ((*CLUSTER_REPORTS, "tree.txt") if SOURCE == "cluster" else ())


def keep_run() -> tuple:
    """KEEP_RUN, and for the cluster source its reports and the files it ran from too."""
    if SOURCE != "cluster":
        return KEEP_RUN
    return KEEP_RUN + CLUSTER_RUN_FILES + tuple(f"reports/{r}" for r in CLUSTER_REPORTS)


# dc_syn.tcl's path classes (X40), in reports/path_classes.rpt and the slack_<class>_ns columns
PATH_CLASSES = ("in2reg", "reg2reg", "reg2out", "in2out")

COLUMNS = ["point", "top", "tech", "clock_ns", "clk_gate", "status", "errors", "area_um2", "comb_area_um2", "seq_area_um2",
           "buf_inv_area_um2", "cells", "seq_cells", "crit_path_ns", "slack_ns", "fmax_mhz",
           *(f"slack_{c}_ns" for c in PATH_CLASSES), "maxcap_nets",
           "maxtrans_nets", "dyn_power_uw", "leak_power_uw", "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj",
           "e_total_pj", "leak_clk_uw", "leak_reg_uw", "leak_seq_uw", "leak_comb_uw", "lib_md5", "dc_version",
           "date", "run"]
FORGE_COLUMNS = ["recipe", "W", "snax_forge_commit",   # after COLUMNS, forge rows only
                 "csr_um2", "ctrl_um2", "datapath_um2", "glue_um2"]
CHAR_COLUMNS = ["datapath", "lanes", "depth", "op", "form", "snax_forge_commit"]  # after COLUMNS, char rows only
BAMBU_COLUMNS = ["ctrl_um2", "datapath_um2", "glue_um2"]  # after COLUMNS, bambu rows only (X41)
CLUSTER_COLUMNS = ["recipe", "W", "snax_forge_commit", "snax_cluster_commit", "macro_um2", "macros"]  # cluster rows
HLS_COLUMNS = ["ram_um2", "ram_kind"]   # after COLUMNS, hls rows only (X62): a RAM's area, inside area_um2
RAM_TECH = "nangate45"                  # the macros are CACTI's 45 nm (X47)
# after COLUMNS, streamer and xbar rows (X52): the grid's params, then the flop check's numbers
STRM_COLUMNS = {"streamer": ["depth", "loops", "channels", "rtl_flop_bits", "opt1207", "snax_cluster_commit"],
                "xbar": ["inputs", "banks", "rtl_flop_bits", "opt1207", "snax_cluster_commit"],
                "xbar_mix": ["inputs", "banks", "ro", "wo", "rtl_flop_bits", "flops_removed", "opt1207",
                             "snax_cluster_commit"]}
STRM_PARAMS = {"streamer": {"depth": "fifo_depth", "loops": "temporal_dim", "channels": "num_channel"},
               "xbar": {"inputs": "inputs", "banks": "banks"},
               "xbar_mix": {"inputs": "inputs", "banks": "banks", "ro": "ro", "wo": "wo"}}
GLUE_MAX = 0.01   # a glue share above this (or below 0) is reported, not failed
# A licence failure, as DC prints it (PITFALLS L1): 'Error: Design-Compiler Internal licensing error
# number -92 ...', 'Unable to obtain feature ...', 'Fatal: Design Compiler is not enabled. (DCSH-1)'.
# A bare 'license' is not enough: every good run's banner says 'license agreement' and its
# DesignWare table 'Licensed DW Building Blocks'.
LICENCE_ERROR = re.compile(r"^.*(licensing error|unable to obtain feature|is not enabled\. \(DCSH-1\)"
                           r"|^(error|fatal):.*licen[cs]e).*$", re.I | re.M)
MODULE_COLUMNS = ["point", "tech", "clock_ns", "clk_gate", "path", "design", "area_um2", "comb_um2", "seq_um2", "bbox_um2",
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
    """The points of the source: a forge or char point is a bundle zip, rtl/<set>/<point>.zip, holding a
    bundle.json (forge) or an emitted.json (char); an HLS tool's is an rtl/ folder with a filelist.f."""
    if SOURCE == "cluster":
        return sorted(f.stem for f in RTL.glob("*.zip") if "provenance.json" in arc.names(f))
    if SOURCE in BUNDLED:
        marker = {"forge": "bundle.json", "char": "emitted.json"}.get(SOURCE, "config.json")
        return sorted(f.relative_to(RTL).with_suffix("").as_posix() for f in RTL.rglob("*.zip")
                      if marker in arc.names(f))
    name = re.compile(rf"({'|'.join(SOURCES[SOURCE]['cases'])})_w([0-9]+)")
    return sorted(str(f.parent.relative_to(RTL)) for f in RTL.glob("*/*/*/filelist.f")
                  if (m := name.fullmatch(f.parent.name)) and int(m.group(2)) <= MAX_W)


def columns() -> list[str]:
    return COLUMNS + {"forge": FORGE_COLUMNS, "char": CHAR_COLUMNS, "bambu": BAMBU_COLUMNS, "hls": HLS_COLUMNS,
                      "cluster": CLUSTER_COLUMNS, **STRM_COLUMNS}.get(SOURCE, [])


def bundle_zip(point: str) -> Path:
    """A forge or char point's bundle: rtl/forge/<point>.zip or rtl/char/<point>.zip (forge/bundles.py,
    char/blocks.py)."""
    return RTL / f"{point}.zip"


def forge_json(point: str, name: str) -> dict:
    z = bundle_zip(point)
    return json.loads(arc.read_text(z, name)) if arc.has(z, name) else {}


def forge_members(point: str) -> list[str]:
    """The bundle's rtl/files.f, as members of its zip."""
    text = arc.read_text(bundle_zip(point), "rtl/files.f")
    return [posixpath.normpath(f"rtl/{ln.strip()}") for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def char_members(point: str) -> list[str]:
    """emitted.json's files, as members of the block's zip."""
    return [posixpath.normpath(f) for f in forge_json(point, "emitted.json")["files"]]


def strm_members(point: str) -> list[str]:
    """filelist.f's files (after its '# top:' line), as members of a streamer or xbar point's zip."""
    return [posixpath.normpath(ln.strip()) for ln in arc.read_text(bundle_zip(point), "filelist.f").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def strm_extra(point: str, top: str, log: str) -> dict:
    """A streamer, xbar or xbar_mix row's STRM_COLUMNS: the grid's params (config.json), the bits the RTL declares
    under the top (strm/gen.py's flop_bits; for xbar_mix over both files, so the SparseInterconnect's), DC's unique
    OPT-1207 lines and the snax_cluster commit."""
    sys.path.insert(0, str(ROOT / "strm"))
    import gen as strm_gen  # noqa: PLC0415  strm/gen.py, only for these two sources
    z = bundle_zip(point)
    cfg = forge_json(point, "config.json")
    params = cfg.get("params", {})
    out = {k: params.get(v, "") for k, v in STRM_PARAMS[SOURCE].items()}
    try:
        text = ("".join(arc.read_text(z, m) for m in strm_members(point)) if SOURCE == "xbar_mix"
                else arc.read_text(z, f"{top}.sv"))
        out["rtl_flop_bits"] = strm_gen.flop_bits(text, top)
    except (KeyError, ValueError) as e:
        out["rtl_flop_bits"] = ""
        print(f"flop check {point}: no RTL count ({e})", flush=True)
    out["opt1207"] = len(set(re.findall(r"^Information: The register '([^']+)' will be removed\. \(OPT-1207\)",
                                        log, re.M)))
    out["snax_cluster_commit"] = cfg.get("snax_cluster_commit", "")
    return out


def strm_size(point: str) -> tuple:
    """The order run starts streamer and xbar points in, largest first: inputs x banks; channels x depth, loops."""
    p = forge_json(point, "config.json").get("params", {})
    if SOURCE in ("xbar", "xbar_mix"):
        return (p.get("inputs", 0) * p.get("banks", 0), p.get("banks", 0))
    return (p.get("num_channel", 0) * p.get("fifo_depth", 0), p.get("num_channel", 0), p.get("temporal_dim", 0))


def point_members(point: str) -> list[str]:
    """A forge or char point's HDL files, as members of its bundle zip."""
    if SOURCE in STRM:
        return strm_members(point)
    return forge_members(point) if SOURCE == "forge" else char_members(point)


def point_filelist(point: str, bundle: Path) -> list[str]:
    """A forge or char point's files in its unpacked bundle, for the filelist.f that run writes."""
    return [str((bundle / m).resolve()) for m in point_members(point)]


def hdl_texts(point: str) -> list[str]:
    """The point's HDL sources: filelist.f's files for the HLS tools, the bundle zip's for forge and char;
    a file that is not there is left out."""
    if SOURCE in BUNDLED:
        z, have = bundle_zip(point), set(arc.names(bundle_zip(point)))
        return [arc.read_text(z, m, errors="replace") for m in point_members(point) if m in have]
    files = [RTL / point / ln.strip() for ln in (RTL / point / "filelist.f").read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    return [f.read_text(errors="replace") for f in files if f.is_file()]


def _balanced(text: str, i: int) -> int:
    """The index just after the parenthesis that closes the one at text[i]."""
    depth = 0
    for j in range(i, len(text)):
        depth += {"(": 1, ")": -1}.get(text[j], 0)
        if depth == 0:
            return j + 1
    return -1


def module_ports(texts: list[str], top: str) -> list[str] | None:
    """The port names of module `top` in these sources (ANSI or not), None if none declares it.
    Each item of the header's port list, split at top-level commas, names its port last."""
    for src in texts:
        text = re.sub(r"//[^\n]*|/\*.*?\*/", " ", src, flags=re.S)
        m = re.search(rf"\bmodule\s+{re.escape(top)}\b", text)
        if not m:
            continue
        i = m.end()
        imp = re.match(r"(\s*import\s[^;]*;)*\s*", text[i:])   # SystemVerilog package imports
        i += imp.end()
        if text.startswith("#", i):                                # the parameter list
            i = _balanced(text, text.index("(", i))
            i += len(text[i:]) - len(text[i:].lstrip())
        if not text.startswith("(", i):
            return []                                              # a module without ports
        body = text[i + 1:_balanced(text, i) - 1]
        items, depth, cur = [], 0, ""
        for ch in body:
            depth += {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}.get(ch, 0)
            if ch == "," and depth == 0:
                items.append(cur)
                cur = ""
            else:
                cur += ch
        items.append(cur)
        names = []
        for it in items:
            it = re.sub(r"\[[^\]]*\]|=.*$", " ", it, flags=re.S)  # ranges and default values
            ids = re.findall(r"[A-Za-z_][A-Za-z0-9_$]*", it)
            if ids:
                names.append(ids[-1])
        return names
    return None


def port_guard(point: str) -> str:
    """'' if the top has the source's clock and reset ports, else the row's failed status."""
    top, src = top_of(point), SOURCES[SOURCE]
    try:
        ports = module_ports(hdl_texts(point), top)
    except (OSError, KeyError) as e:
        return f"failed: port guard could not read the point's files ({e})"
    if ports is None:
        return f"failed: no module {top or '(no # top:)'} in the point's files"
    for kind, name in (("clock", src["clk"]), ("reset", src["rst"])):
        if name not in ports:
            return f"failed: no {kind} port {name} on {top}"
    return ""


def char_extra(point: str) -> dict:
    """A char row's CHAR_COLUMNS from point.json: the datapath, the params that apply, a Mac's form."""
    pj = forge_json(point, "point.json")
    params = pj.get("params", {})
    form = ""
    if pj.get("datapath") == "Mac":
        form = "acc" if params.get("accumulate") else "reg" if params.get("regOut") else "plain"
    return {"datapath": pj.get("datapath", ""), "lanes": params.get("lanes", ""), "depth": params.get("depth", ""),
            "op": params.get("op", ""), "form": form, "snax_forge_commit": pj.get("snax_forge_commit", "")}


def select(patterns: list[str]) -> list[str]:
    pts = all_points()
    if not patterns:
        return pts
    return [p for p in pts if any(fnmatch.fnmatchcase(p, pat) for pat in patterns)]


def top_of(point: str) -> str:
    if SOURCE == "cluster":
        return SOURCES["cluster"]["top"]
    if SOURCE == "forge":
        return forge_json(point, "bundle.json").get("top", "")
    if SOURCE == "char":
        return forge_json(point, "emitted.json").get("top", "")
    if SOURCE in STRM:
        m = re.search(r"^#\s*top:\s*(\S+)", arc.read_text(bundle_zip(point), "filelist.f"), re.M)
        return m.group(1) if m else ""
    m = re.search(r"^#\s*top:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)
    return m.group(1) if m else ""


def point_files(point: str) -> list[str]:
    """The Verilog files of an HLS point's filelist.f, as written (relative to its folder)."""
    return [ln.strip() for ln in (RTL / point / "filelist.f").read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def rams_of(point: str) -> list[str]:
    if SOURCE in BUNDLED or SOURCE == "cluster":
        return []
    return re.findall(r"^#\s*ram:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)


def parked_row(tech: str, point: str, clock: str, rams: list[str]) -> dict:
    return no_run_row(tech, point, clock, f"skipped: needs a RAM macro ({', '.join(rams)}); {tech} has no RAM "
                                          "cells, RAM1 builds one (OpenRAM)")


def no_run_row(tech: str, point: str, clock: str, status: str) -> dict:
    """A summary row for a point DC does not run (parked, or failed by the port guard)."""
    row = {c: "" for c in columns()}
    row.update({"point": point, "top": top_of(point), "tech": tech, "clock_ns": clock,
                "clk_gate": "1" if CLK_GATE else "0", "status": status,
                "date": dt.datetime.now().isoformat(timespec="seconds")})
    return row


def point_tag(point: str, clock: str) -> str:
    """<point>[_c<clock>][_cg]: the clock tag for a clock other than the default, _cg with --clk-gate (X79)."""
    return point + ("" if clock == DEFAULT_CLOCK else "_c" + clock.replace(".", "p")) + (CG_TAG if CLK_GATE else "")


def run_dir(tech: str, point: str, clock: str) -> Path:
    """The folder DC works in; it lives only during the run (X51), the CSVs' run column names it."""
    return RUNS / tech / point_tag(point, clock)


def run_zip(tech: str, point: str, clock: str) -> Path:
    """What is kept of a run: syn/runs/<source>/<tech>/<point>[_c<clock>][_cg].zip (KEEP_RUN)."""
    d = run_dir(tech, point, clock)
    return d.with_name(d.name + ".zip")


def pack_run(rdir: Path) -> Path:
    """A finished run folder to its zip (keep_run(), test-read), then the folder goes, scratch with it."""
    z = arc.write(rdir.with_name(rdir.name + ".zip"),
                  {m: p.read_bytes() for m, p in arc.files_of(rdir, keep_run()).items()})
    shutil.rmtree(rdir)
    return z


def folder_reader(rdir: Path):
    """get(member) -> the text of a file in a run folder, None if it is not there."""
    def get(member: str) -> str | None:
        f = rdir / member
        return f.read_text(errors="replace") if f.is_file() else None
    return get


def zip_reader(z: Path):
    """get(member) -> the text of a member of a run zip, None if it is not there."""
    have = set(arc.names(z)) if z.is_file() else set()

    def get(member: str) -> str | None:
        return arc.read_text(z, member, errors="replace") if member in have else None
    return get


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


def lib_info(get) -> dict:
    text = get("reports/lib_info.txt")
    if text is None:
        return {}
    return dict(ln.split(": ", 1) for ln in text.splitlines() if ": " in ln)


def power_groups(power: str, groups=None) -> dict:
    """Per group: (internal, switching, leakage) in uW, from power.rpt's group table (POWER_GROUPS by default)."""
    dyn, leak = _power_unit(power, "Dynamic Power Units"), _power_unit(power, "Leakage Power Units")
    out = {}
    if dyn is None or leak is None:
        return out
    for g in (groups or POWER_GROUPS):
        m = re.search(rf"^{g}\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", power, re.M)
        if m:
            out[g] = (float(m.group(1)) * dyn, float(m.group(2)) * dyn, float(m.group(3)) * leak)
    return out


def run_clk_gate(tech_json: str | None) -> str:
    """X79: '1' when the run's DC environment (tech.json) had SYN_CLK_GATE_ENABLE=1, else '0' ('' with no tech.json)."""
    if tech_json is None:
        return ""
    env = json.loads(tech_json).get("resolved", {}).get("dc_env", {})
    return "1" if env.get("SYN_CLK_GATE_ENABLE") == "1" else "0"


def read_run(tech: dict, point: str, clock: str) -> dict:
    """The summary row of a run, from its zip."""
    rdir = run_dir(tech["name"], point, clock)
    get = zip_reader(run_zip(tech["name"], point, clock))
    t_scale = float(resolve(tech)["t_scale"])
    clock_ns = float(clock)

    def text(name: str) -> str:
        return get(f"reports/{name}") or ""

    area, qor, power, classes = text("area.rpt"), text("qor.rpt"), text("power.rpt"), text("path_classes.rpt")
    log = get("logs/dc_shell.log")
    log_text = log or ""
    info = lib_info(get)
    tj = get("tech.json")
    row = {c: "" for c in columns()}
    row.update({
        "point": point, "top": top_of(point), "tech": tech["name"], "clock_ns": clock,
        "clk_gate": run_clk_gate(tj),
        "errors": len(re.findall(r"^Error:", log_text, re.M)) if log is not None else "",
        "area_um2": _first(area, r"Total cell area:\s*([0-9.]+)"),
        "comb_area_um2": _first(area, r"Combinational area:\s*([0-9.]+)"),
        "seq_area_um2": _first(area, r"Noncombinational area:\s*([0-9.]+)"),
        "buf_inv_area_um2": _first(area, r"Buf/Inv area:\s*([0-9.]+)"),
        "cells": _first(area, r"Number of cells:\s*([0-9]+)"),
        "seq_cells": _first(area, r"Number of sequential cells:\s*([0-9]+)"),
        "maxcap_nets": _first(qor, r"Max Cap Violations:\s*([0-9]+)"),
        "maxtrans_nets": _first(qor, r"Max Trans Violations:\s*([0-9]+)"),
        "lib_md5": json.loads(tj)["resolved"]["lib_md5"] if tj is not None else "",
        "dc_version": info.get("dc_version", ""),
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "run": str(rdir.relative_to(ROOT)),
    })
    if SOURCE == "forge":
        pj = forge_json(point, "point.json")
        row.update({"recipe": pj.get("recipe", ""), "W": pj.get("W", ""),
                    "snax_forge_commit": forge_json(point, "bundle.json").get("snax_forge_commit", "")})
        row.update(module_shares(tech, point, clock, row["area_um2"]))
    if SOURCE == "char":
        row.update(char_extra(point))
    if SOURCE in STRM:
        row.update(strm_extra(point, row["top"], log_text))
    if SOURCE == "xbar_mix":
        row["flops_removed"] = flops_removed(row)
    if SOURCE == "hls" and tj is not None:
        row.update(ram_area(json.loads(tj), get, tech, point, clock))
    cluster_gate = ""
    if SOURCE == "cluster":
        extra, cluster_gate = cluster_extra(json.loads(tj) if tj is not None else {}, get, log_text, tech)
        row.update(extra)
    split_error = ""
    if SOURCE == "bambu":
        split, split_error = bambu_split(tech, point, clock, row["area_um2"])
        row.update(split)
    crit = _first(qor, r"Critical Path Length:\s*([0-9.eE+-]+)")
    slack = _first(qor, r"Critical Path Slack:\s*([0-9.eE+-]+)")
    if crit:
        row["crit_path_ns"] = _num(float(crit) / t_scale)
    if slack:
        s = float(slack) / t_scale
        row["slack_ns"] = _num(s)
        row["fmax_mhz"] = _num(1000.0 / (clock_ns - s))
    for c in PATH_CLASSES:   # 'none' (no path in the class) stays empty
        v = _first(classes, rf"^{c}\s+(\S+)")
        if re.fullmatch(r"[0-9.eE+-]+", v):
            row[f"slack_{c}_ns"] = _num(float(v) / t_scale)
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
            # X62: an SRAM macro is a black box to DC (its default-activity power is in that group, not in the four);
            # the cluster's memories are macros (X66, PITFALLS DC12)
            if row.get("ram_kind") == "macro" or SOURCE == "cluster":
                bb = power_groups(power, ["black_box"]).get("black_box", (0.0, 0.0, 0.0))
                e_dyn -= (bb[0] + bb[1]) * clock_ns / 1000.0
            energy_ok = abs(e_total - e_dyn) <= 1e-3 * max(abs(e_dyn), 1e-9) + 1e-6
    lic = licence_error(get)
    if not row["area_um2"] or float(row["area_um2"]) == 0 or lic:
        # A licence failure in compile_ultra (DC-Expert, SEC-50) still writes the reports, of an empty
        # design: area 0. It fails the row whatever the reports say (HSYN1 R6).
        # at a line's start: dc_shell.log also echoes the script, whose puts line is indented
        mismatch = re.search(r"^dc_syn\.tcl: library mismatch", log_text, re.M) is not None
        row["status"] = ("failed: library mismatch (logs/dc_shell.log)" if mismatch
                         else f"failed: licence ({lic})" if lic else "failed: no area report")
    elif "No wire load specified" not in area:
        row["status"] = "failed: a wire-load model applied"
    elif cluster_gate:
        row["status"] = f"failed: cluster gate ({cluster_gate})"
    elif not energy_ok:
        row["status"] = "failed: power groups do not sum to the total dynamic power"
    elif split_error:
        row["status"] = f"failed: Bambu split ({split_error})"
    elif SOURCE == "xbar_mix" and (row["flops_removed"] == "" or row["flops_removed"] < 0):
        row["status"] = (f"failed: flop check (DC {row['seq_cells'] or '?'} flops, more than the RTL's "
                         f"{row['rtl_flop_bits'] or '?'} bits, or no count)")
    elif SOURCE in STRM and SOURCE != "xbar_mix" and str(row["rtl_flop_bits"]) != row["seq_cells"]:
        # STRM1 R0: every register the RTL declares is a flop after compile (no OPT-1207, no OPT-1206)
        row["status"] = (f"failed: flop check (DC {row['seq_cells'] or '?'} flops, RTL {row['rtl_flop_bits'] or '?'} "
                         f"bits, {row['opt1207']} OPT-1207)")
    elif row["slack_ns"] and float(row["slack_ns"]) < 0:
        row["status"] = "ok, timing violated"
    else:
        row["status"] = "ok"
    return row


def flops_removed(row: dict) -> int | str:
    """An xbar_mix row's rtl_flop_bits minus DC's flops ('' without both): the flops DC removed, which the ties may
    make dead (reported per point, X70)."""
    try:
        return int(row["rtl_flop_bits"]) - int(row["seq_cells"])
    except (TypeError, ValueError):
        return ""


LINK5 = re.compile(r"\(LINK-5\)|Unable to resolve reference", re.I)
# X79: the library's integrated clock gates DC found (clock_gating.tcl's line, gated runs only). Nangate describes
# them with a statetable, so DC marks them is_black_box; they are not the cluster's black boxes (CG1 R2).
ICG_LINE = re.compile(r"^clock_gating\.tcl: integrated clock gates (.+)$", re.M)


def icg_cells(log: str) -> set[str]:
    """The integrated clock gates clock_gating.tcl listed in the log (lib/cell -> cell); empty when ungated."""
    return {c.split("/")[-1] for m in ICG_LINE.finditer(log) for c in m.group(1).split()}


def cluster_check(text: str) -> dict:
    """cluster_check.rpt (cluster/cluster_check.tcl): leaf_cells, refs {ref: (lib, cells, bb)}, unresolved,
    black_box, library and constant {name: cells}, macro_area."""
    out = {"leaf_cells": None, "refs": {}, "unresolved": {}, "black_box": {}, "library": {}, "constant": {},
           "macro_area": ""}
    for ln in text.splitlines():
        t = ln.split()
        if not t or t[0].startswith("#"):
            continue
        if t[0] == "leaf_cells" and len(t) == 2:
            out["leaf_cells"] = int(t[1])
        elif t[0] == "ref" and len(t) == 5:
            out["refs"][t[1]] = (t[2], int(t[3]), t[4] == "1")
        elif t[0] in ("unresolved", "black_box", "library", "constant") and len(t) == 3:
            out[t[0]][t[1]] = int(t[2])
        elif t[0] == "macro_area":
            out["macro_area"] = t[1] if len(t) == 2 else ""
    return out


def cluster_extra(tj: dict, get, log: str, tech: dict) -> tuple[dict, str]:
    """A cluster row's CLUSTER_COLUMNS (tech.json's resolved cluster block, cluster_check.rpt) and its gates
    (X67): no unresolved reference (cluster_check.rpt, LINK-5 in the log), the macros the only black boxes in
    the point's numbers (srams), every leaf cell from the technology's library or a macro's. '' when they pass."""
    cl = tj.get("resolved", {}).get("cluster", {})
    srams = dict(sorted(cl.get("srams", {}).items()))
    row = {"recipe": cl.get("recipe", ""), "W": cl.get("W", ""), "snax_forge_commit": cl.get("snax_forge_commit", ""),
           "snax_cluster_commit": cl.get("snax_cluster_commit", ""), "macro_um2": "", "macros": ""}
    text = get("reports/cluster_check.rpt")
    if text is None:
        return row, "no reports/cluster_check.rpt"
    cc = cluster_check(text)
    # X79: the technology's integrated clock gates, which DC marks black boxes, are not macros (CG1 R2)
    icg = icg_cells(log)
    cc["black_box"] = {k: v for k, v in cc["black_box"].items()
                       if not (k in icg and cc["refs"].get(k, ("",))[0] == tech["lib_name"])}
    row["macro_um2"] = cc["macro_area"]
    row["macros"] = ";".join(f"{k}={v}" for k, v in sorted(cc["black_box"].items()))
    bad = []
    link5 = sum(1 for ln in log.splitlines() if LINK5.search(ln))      # lines, not matches
    if cc["unresolved"] or link5:
        bad.append(f"{len(cc['unresolved'])} unresolved references, {link5} LINK-5 lines")
    if cc["black_box"] != srams:
        bad.append(f"black boxes {cc['black_box']} against srams {srams}")
    libs = set(cc["library"]) - {tech["lib_name"], *srams}
    if libs:
        bad.append(f"cells from {sorted(libs)}")
    if cc["leaf_cells"] is None:
        bad.append("no leaf_cells line in cluster_check.rpt")
    return row, "; ".join(bad)


def ram_area(tj: dict, get, tech: dict, point: str, clock: str) -> dict:
    """X62: ram_um2 and ram_kind of an hls row: the area of the RAM modules' top-level instances (area_hierarchy.rpt,
    by design name: Vitis's RAM, or its wrapper around the macro); for a macro it must equal the macros' area (a
    black box, the CACTI area of X49). '' for a point without a RAM."""
    ram = tj.get("resolved", {}).get("ram")
    if not ram:
        return {"ram_um2": "", "ram_kind": ""}
    mods = [r for r in read_modules(tech, point, clock)
            if any(r["design"].startswith(m) for m in ram["modules"]) and r["path"].count("/") == 0]
    if not mods:
        return {"ram_um2": "", "ram_kind": f"{ram['kind']}: no RAM instance in area_hierarchy.rpt"}
    area = sum(float(r["area_um2"]) for r in mods)
    if ram["kind"] == "macro":
        want = sum(float(m["area_um2"]) * len(m["instances"]) for m in ram["macros"])
        if abs(area - want) > 0.01:
            return {"ram_um2": _num(area), "ram_kind": f"macro: instances {area} um2, macros {want} um2"}
    return {"ram_um2": _num(area), "ram_kind": ram["kind"]}


def licence_error(get) -> str:
    """The first licence-failure line (LICENCE_ERROR) of the run's dc_shell.log or dc_stdout.log,
    the most telling first ('licensing error' over the rest); '' if none. get: folder_reader or zip_reader."""
    found = []
    for name in ("dc_shell.log", "dc_stdout.log"):
        text = get(f"logs/{name}")
        if text is not None:
            found += [m.group(0).strip() for m in LICENCE_ERROR.finditer(text)]
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


def bambu_split(tech: dict, point: str, clock: str, total: str) -> tuple[dict, str]:
    """bambu: ctrl_um2 and datapath_um2 (the area, children included, of the one controller_* and the one
    datapath_* instance in synth_dc_modules.csv's rows) and glue_um2 = total - the two; and '' or why not."""
    out = {k: "" for k in BAMBU_COLUMNS}
    if not total:
        return out, ""
    mods = read_modules(tech, point, clock)
    for key, prefix in (("ctrl_um2", "controller_"), ("datapath_um2", "datapath_")):
        hits = [m for m in mods if m["design"].startswith(prefix)]
        if len(hits) != 1:
            return {k: "" for k in BAMBU_COLUMNS}, f"{len(hits)} {prefix}* instances, not 1"
        out[key] = f"{float(hits[0]['area_um2']):.4f}"
    out["glue_um2"] = f"{float(total) - float(out['ctrl_um2']) - float(out['datapath_um2']):.4f}"
    return out, ""


def _floats(xs: list[str]) -> bool:
    try:
        [float(x) for x in xs]
        return True
    except ValueError:
        return False


def read_modules(tech: dict, point: str, clock: str) -> list[dict]:
    """area_hierarchy.rpt's hierarchical cells joined with power_hierarchy.rpt, by path (from the run's zip)."""
    get = zip_reader(run_zip(tech["name"], point, clock))
    area_text, power = get("reports/area_hierarchy.rpt"), get("reports/power_hierarchy.rpt")
    if area_text is None or power is None:
        return []
    # area: 'path  abs_total  percent  comb  noncomb  bbox  design'
    rows = []
    for ln in area_text.split("Hierarchical cell", 1)[-1].splitlines():
        t = ln.split()
        if len(t) == 7 and _floats(t[1:6]):
            rows.append({"path": t[0], "design": t[6], "area_um2": t[1], "comb_um2": t[3], "seq_um2": t[4],
                         "bbox_um2": t[5]})
    # power: instance names indented two spaces per level, '<inst> (<design>)' below the top, then
    # switching, internal, leakage, total, percent; switching and internal in dynamic units, leakage in
    # leakage units (3 digits: the hierarchical report ignores -significant_digits)
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
        out.append({"point": point, "tech": tech["name"], "clock_ns": clock, "clk_gate": "1" if CLK_GATE else "0", **r,
                    "dyn_power_uw": _num(p[0]) if p else "", "leak_power_uw": _num(p[1]) if p else ""})
    return out


def report_zip(tech: str, point: str, clock: str) -> Path:
    """The committed reports of a run: results/<source>/<tech>/reports/<tier>/<kernel>/<point>[_c<clock>][_cg].zip."""
    return RESULTS / tech / "reports" / f"{point_tag(point, clock)}.zip"


def copy_reports(tech: str, point: str, clock: str) -> list[str]:
    """kept_reports(), from the run's zip, into the committed report zip (flat); returns what was skipped."""
    z = run_zip(tech, point, clock)
    dest = report_zip(tech, point, clock)
    have = set(arc.names(z)) if z.is_file() else set()
    members, skipped = {}, []
    for name in kept_reports():
        m = name if name in TOP_MEMBERS else f"reports/{name}"
        if m not in have:
            continue
        data = arc.read(z, m)
        if len(data) > MAX_REPORT_BYTES and name not in (*UNLIMITED_REPORTS.get(SOURCE, ()), *CG_REPORTS):
            skipped.append(f"{name} ({len(data)} B)")
            continue
        members[name] = data
    if skipped:
        members["skipped.txt"] = (f"Over {MAX_REPORT_BYTES} B, kept only in {z.relative_to(ROOT)}:\n"
                                  + "\n".join(skipped) + "\n").encode()
    if members:
        arc.write(dest, members)
    elif dest.exists():
        dest.unlink()
    return skipped


def _merge(path: Path, columns: list[str], key, rows: list[dict], drop: set) -> None:
    table = []
    if path.is_file():
        with path.open(newline="") as fh:
            table = [r for r in csv.DictReader(fh) if key(r) not in drop]
    table += rows
    table.sort(key=lambda r: (r["point"], float(r["clock_ns"] or 0), gate_flag(r), r.get("path", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)


def summary_key(r: dict) -> tuple:
    """The CSVs' merge key: point, clock and clk_gate (X79), so a gated run never replaces the ungated one."""
    return (r["point"], r["clock_ns"], gate_flag(r))


def write_summary(tech: dict, rows: list[dict]) -> None:
    """The run summary, its copy in results/, the modules CSV and the reports, all in step."""
    name = tech["name"]
    key = summary_key
    done = {key(r) for r in rows}
    _merge(summary_of(name), columns(), key, rows, done)
    out = RESULTS / name
    out.mkdir(parents=True, exist_ok=True)
    synth_csv, modules_csv = RESULT_CSVS.get(SOURCE, ("synth_dc.csv", "synth_dc_modules.csv"))
    shutil.copy2(summary_of(name), out / synth_csv)
    modules = []
    for r in rows:
        if r["run"]:
            if SOURCE != "cluster":          # no modules CSV for the cluster (X67; R3b reads the reports)
                modules += read_modules(tech, r["point"], r["clock_ns"])
            skipped = copy_reports(name, r["point"], r["clock_ns"])
            if skipped:
                print(f"results: {r['point']}: skipped over 1 MB: {', '.join(skipped)}")
        else:
            stale = report_zip(name, r["point"], r["clock_ns"])
            if stale.exists():
                stale.unlink()
    if SOURCE != "cluster":
        _merge(out / modules_csv, MODULE_COLUMNS, key, modules, done)


def print_rows(rows: list[dict]) -> None:
    cols = ["point", "tech", "clock_ns", "clk_gate", "status", "area_um2", "cells", "crit_path_ns", "slack_ns", "fmax_mhz",
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
    filelist = (run_dir(tech["name"], point, args.clock) / "filelist.f" if SOURCE in BUNDLED
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
        **({"SYN_WRITE_SDF": "1"} if getattr(args, "sdf", False) else {}),   # X69: no SDF unless asked
        **({"SYN_CLK_GATE_ENABLE": "1"} if CLK_GATE else {}),               # X79: clock gating only when asked
    }


RETRIES: list[str] = []          # points rerun on a licence error, this invocation
RETRIES_LOCK = threading.Lock()


def run_dc(point: str, name: str, rdir: Path, cmd: list[str], syn_env: dict, clock: str, prepare) -> int:
    """DC in a fresh rdir (logs/ made, then prepare() writes what the run reads), its stdout into
    logs/dc_stdout.log as it runs; rerun once on a licence error (X17, counted in RETRIES). The return code."""
    for attempt in (1, 2):
        if rdir.exists():
            shutil.rmtree(rdir)
        (rdir / "logs").mkdir(parents=True)
        prepare()
        print(f"run  {point} on {name} at {clock} ns in {rdir.relative_to(ROOT)}"
              + (" (licence retry)" if attempt == 2 else ""), flush=True)
        with (rdir / "logs" / "dc_stdout.log").open("w") as fh:
            rc = subprocess.run(cmd, cwd=rdir, env=dict(os.environ, **syn_env), stdout=fh,
                                stderr=subprocess.STDOUT, check=False).returncode
        lic = licence_error(folder_reader(rdir))
        if not lic or attempt == 2:
            break
        with RETRIES_LOCK:
            RETRIES.append(point)
        print(f"retry {point} on {name}: licence error: {lic}", flush=True)
    return rc


def finish_run(point: str, rdir: Path, tech: dict, res: dict, args, syn_env: dict, rc: int, extra: dict,
               before_pack=None) -> dict:
    """tech.json (the tech file, the resolved values, the run's environment and return code, extra), then
    before_pack() if given, the zip (keep_run()), and the summary row read back from it."""
    name = tech["name"]
    (rdir / "tech.json").write_text(json.dumps({
        "tech_file": str((TECH_DIR / f"{name}.json").relative_to(ROOT)),
        "tech": tech,
        "resolved": {**res, "clock_ns": args.clock, "cores": args.cores,
                     "dc_env": syn_env, "dc_returncode": rc, **extra},
        "dc_lib_info": lib_info(folder_reader(rdir)),
    }, indent=2) + "\n")
    if before_pack is not None:
        before_pack()
    pack_run(rdir)
    row = read_run(tech, point, args.clock)
    print(f"done {point} on {name}: {row['status']}  area {row['area_um2'] or '-'} um2"
          f"  slack {row['slack_ns'] or '-'} ns  errors {row['errors']}", flush=True)
    return row


def run_one(point: str, args, dc: str, tech: dict, res: dict) -> dict | None:
    name = tech["name"]
    guard = port_guard(point)
    if guard:
        print(f"fail {point}: {guard.removeprefix('failed: ')}; DC not run", flush=True)
        return None if args.dry_run else no_run_row(name, point, args.clock, guard)
    rams = rams_of(point)
    rdir = run_dir(name, point, args.clock)
    syn_env = dc_env(tech, res, point, args)
    ram_plan, ram_info = None, None
    if rams and args.with_ram:          # Vitis's RAM as written: DC builds it from flops
        ram_info = {"kind": "flops", "modules": [Path(f).stem for f in rams]}
    elif rams:                          # X62: the macro swap, where a macro can be made
        why = f"{name} has no macros (CACTI at 45 nm, X47)" if name != RAM_TECH or SOURCE != "hls" else ""
        if not why:
            ram_plan = vitis_ram.plan(RTL / point, point_files(point), rams, make=not args.dry_run)
            why = "" if ram_plan["ok"] else ram_plan["why"]
        if why:
            print(f"park {point}: it holds a RAM ({', '.join(rams)}) and no macro: {why}; --with-ram builds it "
                  "from flops", flush=True)
            return None if args.dry_run else no_run_row(
                name, point, args.clock, f"skipped: needs a RAM macro ({', '.join(rams)}): {why}")
        ram_info = {"kind": "macro", "macros": ram_plan["macros"], "modules": [Path(f).stem for f in rams]}
        syn_env["SYN_FILELIST"] = str(rdir / "filelist.f")
    cmd = [dc, "-f", str(SCRIPT), "-output_log_file", "logs/dc_shell.log"]
    if args.dry_run:
        print(f"\n# {point} on {name}")
        print(f"# port guard: ok, clock {syn_env['SYN_CLK_PORT']} and reset {syn_env['SYN_RST_PORT']} on {top_of(point)}")
        if SOURCE in BUNDLED:
            print(f"# run unpacks {bundle_zip(point).relative_to(ROOT)} into tmp/ and writes "
                  f"{syn_env['SYN_FILELIST']}: '# top: {top_of(point)}', then its {len(point_members(point))} "
                  f"files ({'rtl/files.f' if SOURCE == 'forge' else 'filelist.f' if SOURCE in STRM else 'emitted.json'})")
        for k, v in syn_env.items():
            print(f"export {k}='{v}'")
        print(f"mkdir -p {rdir}/logs && cd {rdir} && {' '.join(cmd)}")
        print(f"# then {run_zip(name, point, args.clock).relative_to(ROOT)} keeps {', '.join(KEEP_RUN)}; "
              f"the folder is deleted")
        return None
    with contextlib.ExitStack() as stack:     # a forge or char bundle, unpacked for DC, deleted after (X51)
        bundle = (stack.enter_context(arc.unpacked(bundle_zip(point))) if SOURCE in BUNDLED
                  else None)
        if ram_plan:                          # the macros' .db for DC's link_library, unpacked, deleted after
            dbs = []
            for m in ram_plan["macros"]:
                d = stack.enter_context(arc.unpacked(Path(m["zip"]), [f"{m['cell']}.db"]))
                dbs.append(str(d / f"{m['cell']}.db"))
            syn_env["SYN_RAM_DBS"] = " ".join(dbs)
        def prepare() -> None:
            if bundle is not None:
                Path(syn_env["SYN_FILELIST"]).write_text(
                    f"# top: {top_of(point)}\n" + "".join(f"{f}\n" for f in point_filelist(point, bundle)))
            if ram_plan:                      # the wrappers in ram/, the point's other files by absolute path
                (rdir / "ram").mkdir()
                for fname, text in ram_plan["wrappers"].items():
                    (rdir / "ram" / fname).write_text(text)
                lines = [str(rdir / "ram" / f) if f in ram_plan["wrappers"] else str((RTL / point / f).resolve())
                         for f in ram_plan["files"]]
                Path(syn_env["SYN_FILELIST"]).write_text(f"# top: {top_of(point)}\n" + "".join(f"{f}\n" for f in lines))

        rc = run_dc(point, name, rdir, cmd, syn_env, args.clock, prepare)
    row = finish_run(point, rdir, tech, res, args, syn_env, rc, {"ram": ram_info})
    if SOURCE == "xbar_mix" and isinstance(row["flops_removed"], int) and row["flops_removed"] > 0:
        print(f"flops {point} on {name}: DC removed {row['flops_removed']} of the RTL's {row['rtl_flop_bits']} bits "
              f"({row['opt1207']} OPT-1207 lines)", flush=True)
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
    if SOURCE == "cluster":
        sys.exit("the cluster source runs through cluster/cluster.py: pixi run cluster syn <point> (X67)")
    points = select(args.patterns)
    if not points:
        sys.exit("no rtl point matches (syn.py list shows them)")
    if SOURCE in STRM:          # the largest first, so the longest runs do not end the batch alone
        points.sort(key=strm_size, reverse=True)
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


def cmd_check_ports(args) -> int:
    points = select(args.patterns)
    if not points:
        sys.exit("no rtl point matches (syn.py list shows them)")
    src, bad = SOURCES[SOURCE], 0
    for p in points:
        guard = port_guard(p)
        bad += bool(guard)
        print(f"{p}  (top {top_of(p)})  " + (guard or f"ok: clock {src['clk']}, reset {src['rst']}"))
    print(f"{len(points) - bad} of {len(points)} points pass, {bad} fail")
    return 1 if bad else 0


def cmd_summary(args) -> int:
    if not techs_with_summary(args.tech):
        sys.exit(f"no syn/runs/{SOURCE}/{args.tech or '<tech>'}/summary.csv yet")
    print_rows(summary_rows(args.tech, args.patterns))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    techs = tech_names()
    for name in ("list", "run", "summary", "check-ports"):
        p = sub.add_parser(name)
        p.add_argument("patterns", nargs="*", help="globs over <tier>/<kernel>/<point>, e.g. done/vecadd/opt_*")
        p.add_argument("--source", choices=sorted(SOURCES), default="hls",
                       help="hls (Vitis, hls-exercises' rtl/, the default), bambu (the same rtl/), xls "
                            "(dslx-exercises' rtl/), forge (rtl/forge/, pixi run forge-rtl) "
                            "char (rtl/char/, pixi run char-rtl), streamer or xbar (rtl/streamer/, rtl/xbar/, "
                            "pixi run strm-rtl), xbar_mix (rtl/xbar_mix/, strm-rtl --set xbar_mix), cluster (results and summary; runs through pixi run cluster syn)")
        if name == "check-ports":
            continue
        if name == "run":
            p.add_argument("--tech", required=True, choices=techs, help="technology: one of syn/tech/*.json")
            p.add_argument("--clock", default=DEFAULT_CLOCK, help=f"clock period in ns (default {DEFAULT_CLOCK})")
            p.add_argument("--cores", type=int, default=16, help="cores per DC run (default 16)")
            p.add_argument("-j", "--jobs", type=int, default=1, help="DC runs at once (each takes a license)")
            p.add_argument("--dry-run", action="store_true", help="print the commands, run nothing")
            p.add_argument("--sdf", action="store_true", help="also write the SDF (SYN_WRITE_SDF=1); off by default (X69)")
            p.add_argument("--clk-gate", action="store_true",
                           help="clock gating (SYN_CLK_GATE_ENABLE=1, dc_syn.tcl's CLK_GATE_ENABLE): runs tagged _cg, "
                                "rows with clk_gate 1; off by default (X79)")
            p.add_argument("--with-ram", action="store_true",
                           help="also run points with a '# ram:' line (parked by default)")
        else:
            p.add_argument("--tech", choices=techs, help="only this technology's runs")
    args = ap.parse_args()
    use_source(args.source)
    use_clk_gate(getattr(args, "clk_gate", False))
    if args.cmd == "run" and not args.patterns:
        ap.error("run needs at least one pattern, e.g. done/vecadd/opt_w8")
    return {"list": cmd_list, "run": cmd_run, "summary": cmd_summary, "check-ports": cmd_check_ports}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
