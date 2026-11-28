#!/usr/bin/env python3
"""sim/pwr.py - dynamic energy of mapped netlists from simulated activity (docs/power.md).

  pixi run pwr tbjson      POINT [--source S] [--tech T]
  pixi run pwr run         PATTERN ... --tech T [--source S] [--stim rand64|forge] [--size TAG|all] [--seed N]
                                       [-j N] [--cores C] [--clk-gate] [--initreg-seed N]
  pixi run pwr setup-check --tech T [--source hls|forge|bambu|xls] [--point P]
  pixi run pwr summary     [PATTERN ...] [--source S] [--tech T]
  pixi run pwr modules     --source S --tech T

The sources are hls (the default), forge, char, bambu, xls, streamer, xbar and xbar_mix. Per point one worker unpacks the DC
run, writes tb.json (sim/sources/), compiles the testbench and the netlist, simulates each run at zero delay, cuts
the window into a SAIF, checks it and runs PrimePower, then packs the point into sim/runs/.../<point>.zip and
writes its rows into results/<source>/<tech>/. Workers and PT threads come from the free licences. The stages, each
source's testbench and window, the checks and the columns are in docs/power.md; the commands in docs/TOOL.md.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

SIM = Path(__file__).resolve().parent
ROOT = SIM.parent
sys.path.insert(0, str(SIM))
from sources import hls, syn as _syn  # noqa: E402
from sources import forge as forge_src  # noqa: E402
from sources import char as char_src  # noqa: E402
from sources import strm as strm_src  # noqa: E402
from ref import char_ref, ref  # noqa: E402

syn = _syn()      # syn/syn.py, loaded once (sim/sources/__init__.py): its SOURCES is the one port table
arc = syn.arc     # arc/arc.py, as syn/syn.py imports it

RUNS = SIM / "runs"
SOURCE = "hls"
SYN_RUNS = ROOT / "syn" / "runs" / "hls"
RESULTS = ROOT / "results" / "hls"
TB_DIR = SIM / "tb"
TB_FILES = {"hls": ["ap_ctrl_hs_seq.sv", "axis_src.sv", "axis_sink.sv"],
            "forge": ["csr_seq.sv", "axis_src.sv", "axis_sink.sv"],
            "bambu": ["bambu_seq.sv", "axis_src.sv", "axis_sink.sv"],
            "xls": ["xls_seq.sv", "axis_src.sv", "axis_sink.sv"]}
# The sources: each a tb.json adapter sim/sources/<name>.py, imported when used
SOURCES = ("hls", "forge", "char", "bambu", "xls", "streamer", "xbar", "xbar_mix")
STRM = ("streamer", "xbar", "xbar_mix")     # generated TBs, one busy window, results per point
XBARS = ("xbar", "xbar_mix")                # the interconnect alone and in strm/xbar_mix.py's wrapper
HLS_TOOLS = ("hls", "bambu", "xls")     # an HLS tool's points: rtl/ folders with filelist.f and sizes.txt
PT_SCRIPT = SIM / "scripts" / "pt_power.tcl"
RUN_DO = SIM / "scripts" / "run.do"
DC_READBACK = SIM / "scripts" / "dc_readback.tcl"
TB_TOP, DUT = "tb", "dut"
CLOCK_NS = 10.0
SETUP_POINTS = {"hls": "done/vecadd/opt_w8", "forge": "done/vecadd/forge_w4", "bambu": "done/dot/bambu_w8",
                "xls": "done/dot/xls_w16"}     # setup-check's default point per source
MIN_ANNOTATED = 99.0        # percent of nets annotated from the SAIF
TOGGLE_BEATS = 64           # the input-toggle check fails a run from this many beats up
# Questa cell models, next to each technology's .db, with the vlog options they need
CELL_MODELS = {"nangate45": ("NangateOpenCellLibrary.v", [])}
COLUMNS = ["point", "top", "tech", "clock_ns", "clk_gate", "W", "size", "config", "beats", "seed", "cycles",
           "cycles_ports", "expected_cycles", "expected_diff",
           "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "p_dyn_uw",
           "e_comb_fire_pj", "e_flop_fire_pj", "e_run_pj", "flop_bits", "e_bit_pj", "status"]
FORGE_COLUMNS = ["recipe", "snax_forge_commit", "counter", "counter_diff"]
# an hls point with a RAM (a Vitis dace buffer): the memory's share of the task, inside e_run_pj. macro: e_ram_pj =
# ram_reads x e_rd + ram_writes x e_wr (RAMCOUNT and the macro's CACTI numbers), e_ram_pt_pj PT's own averaged
# figure for the macro cells (PITFALLS PT7, a check, not used); flops: e_ram_pj PT's energy of the RAM instances
HLS_PWR_COLUMNS = ["ram_kind", "ram_reads", "ram_writes", "e_ram_pj", "e_ram_pt_pj"]
# NB (X56): the window is the measurement; the expected count (and forge's BUSY_COUNTER) is recorded beside it,
# with its difference (expected - window), and fails the run only when it is more than this far from the window
CYCLES_TOL = 0.05
MODULE_COLUMNS = ["point", "tech", "clk_gate", "size", "path", "design", "e_dyn_pj"]
# power_pt_modules.csv holds the modules of each point's default run and of every n2048 run (the reference
# task) and n4096 run (X118's E7 task, X119), one set of rows per point and size; the default run stays where it is
# (b64, rowsum m8_n64)
MODULE_SIZES = ("n2048", "n4096")
KEPT = ("power.rpt", "power_hierarchy.rpt", "switching_activity.rpt")
LICENCE_ERR = re.compile(r"(?i)(licen[sc]\w*\s+(error|fail\w*|not available|denied|checkout)|unable to check\s*out"
                         r"|could not check\s*out|cannot check\s*out|feature removed|license server)")
MASK64 = (1 << 64) - 1
# The register start: +initreg+0 (vopt: every register and sequential UDP starts at 0, PITFALLS Q1), the default.
# --initreg-seed N replaces it with Questa 2022.4's random start, for checking only (docs/power.md): vopt
# +initreg=ru marks 4-state variables (r: nangate45's flops are behavioral regs) and sequential UDPs (u) for
# randomization, and vsim +initreg+<N> seeds it. Such runs get the run tag suffix _r<N> and are
# not written to results/ (their SAIFs and PT reports stay in the point's zip in sim/runs/).
INITREG_SEED: int | None = None
# --clk-gate measures the clock-gated netlist of each point (syn.py --clk-gate's run, <point>_cg.zip): the
# point's folder and power_reports zip get the same _cg tag, and its rows have clk_gate 1, merged apart from the
# ungated rows. Off by default.
CLK_GATE = False


def gtag(point: str) -> str:
    """The point as its runs and zips are named: <point>, or <point>_cg with --clk-gate."""
    return point + (syn.CG_TAG if CLK_GATE else "")


def gate() -> str:
    """This invocation's clk_gate column value."""
    return "1" if CLK_GATE else "0"


class Fail(Exception):
    """A check that fails the run: str(e) is the status after 'failed: '."""


def use_source(name: str) -> None:
    """hls, forge, char, bambu or xls: where points, netlists and results are."""
    global SOURCE, SYN_RUNS, RESULTS
    SOURCE = name
    syn.use_source(name)
    SYN_RUNS, RESULTS = ROOT / "syn" / "runs" / name, ROOT / "results" / name


def src():
    """The current source's tb.json adapter (sim/sources/<source>.py)."""
    return importlib.import_module(f"sources.{SOURCE}")


def columns() -> list[str]:
    return COLUMNS + (FORGE_COLUMNS if SOURCE == "forge" else HLS_PWR_COLUMNS if SOURCE == "hls" else [])


def tech_runs(tech: str) -> Path:
    """sim/runs/<tech>/ (hls, as before) or sim/runs/forge/<tech>/; the cell models stay in sim/runs/<tech>/_cells."""
    return RUNS / tech if SOURCE == "hls" else RUNS / SOURCE / tech


# ---------------------------------------------------------------- tools and licences
def tool(name: str, env: str | None = None) -> str:
    path = os.environ.get(env) if env else None
    path = path or shutil.which(name)
    if not path and name == "vcd2saif":
        pt = tool("pt_shell", "PT_SHELL")
        cand = Path(pt).resolve().parent / "vcd2saif"
        path = str(cand) if cand.is_file() else None
    if not path:
        sys.exit(f"{name} not found: put it on PATH" + (f" or set {env}" if env else ""))
    return path


def licences() -> dict:
    """Free licences per feature, from lmutil lmstat on both servers."""
    lm = tool("lmutil", "LMUTIL")
    servers = {"msimhdlsim": os.environ.get("MGLS_LICENSE_FILE", "1717@licserv"),
               "PrimePower": os.environ.get("SNPSLMD_LICENSE_FILE", "1709@licserv"),
               "PrimeTime": os.environ.get("SNPSLMD_LICENSE_FILE", "1709@licserv")}
    out = {}
    for feat, srv in servers.items():
        r = subprocess.run([lm, "lmstat", "-c", srv, "-f", feat], capture_output=True, text=True)
        m = re.search(r"Total of (\d+) licenses? issued;\s+Total of (\d+) licenses? in use", r.stdout)
        if not m:
            sys.exit(f"lmutil lmstat -c {srv} -f {feat}: no count\n{r.stdout}{r.stderr}")
        out[feat] = {"issued": int(m.group(1)), "in_use": int(m.group(2)),
                     "free": int(m.group(1)) - int(m.group(2)), "server": srv}
    return out


def run_tool(cmd: list[str], log: Path, cwd: Path, env: dict | None = None, stdin_null=False) -> int:
    """Run a tool with its output in `log`; on a licence error, once more."""
    for attempt in (1, 2):
        with log.open("w") as fh:
            r = subprocess.run(cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT,
                               stdin=subprocess.DEVNULL if stdin_null else None)
        if attempt == 1 and LICENCE_ERR.search(log.read_text(errors="replace")):
            shutil.copy2(log, log.with_suffix(".licence_retry.log"))
            print(f"{cwd}: licence error in {log.name}, retrying once", flush=True)
            continue
        return r.returncode
    return r.returncode


# ---------------------------------------------------------------- points, tb.json, top
# What a point keeps: sim/runs/.../<point>.zip with tb.json and, per run tag, the SAIF and PT's reports
# (char: per window); setup-check's check.json and reports. The rest of the point's folder (Questa's work/ and
# logs, tb.sv, stim/, transcripts, vsim and vcd2saif logs, PT's logs, result.json) is scratch, deleted.
KEEP_POINT = ("tb.json", "check.json", "*.saif", "*/pt/*.rpt", "*/reports/*.rpt")
# What PT, DC's readback and Questa read of a DC run (pt_power.tcl, dc_readback.tcl): unpacked from its zip
SYN_MEMBERS = ("tech.json", "reports/lib_info.txt")


def syn_run(tech: str, point: str) -> Path:
    """The DC run's folder name (as the CSVs' run column); what is kept of it is syn_zip(). _cg with --clk-gate."""
    return SYN_RUNS / tech / gtag(point)


def syn_zip(tech: str, point: str) -> Path:
    return SYN_RUNS / tech / f"{gtag(point)}.zip"


def point_zip(pdir: Path) -> Path:
    return pdir.with_name(pdir.name + ".zip")


def point_inputs(stack: contextlib.ExitStack, tech: str, point: str) -> tuple[Path, Path, Path | None]:
    """The DC run's netlist, tech.json and lib_info.txt unpacked into tmp/ (PWR_RUN), the netlist, and for forge and
    char the bundle unpacked as well; all deleted when `stack` closes."""
    z = syn_zip(tech, point)
    have = arc.names(z) if z.is_file() else []
    nets = sorted(n for n in have if re.fullmatch(r"out/[^/]*_mapped\.v", n))
    if not nets:
        raise Fail(f"no mapped netlist in {syn_run(tech, point).relative_to(ROOT)}/out")
    d = stack.enter_context(arc.unpacked(z, [nets[0], *(m for m in SYN_MEMBERS if m in have)]))
    bundle = stack.enter_context(arc.unpacked(syn.bundle_zip(point))) if SOURCE in ("forge", "char") else None
    return d, d / nets[0], bundle


def ram_inputs(stack: contextlib.ExitStack, syn_d: Path) -> dict | None:
    """The DC run's RAM plan (tech.json, syn.py): None for a point without one; for macros each macro's .v and
    .db unpacked into tmp/ (deleted with `stack`) and its CACTI energies."""
    tj = syn_d / "tech.json"
    ram = json.loads(tj.read_text()).get("resolved", {}).get("ram") if tj.is_file() else None
    if not ram:
        return None
    out = {"kind": ram["kind"], "modules": ram.get("modules", []), "macros": []}
    for m in ram.get("macros", []):
        d = stack.enter_context(arc.unpacked(Path(m["zip"]), [f"{m['cell']}.v", f"{m['cell']}.db", "result.json"]))
        res = json.loads((d / "result.json").read_text())
        out["macros"].append({"cell": m["cell"], "v": d / f"{m['cell']}.v", "db": d / f"{m['cell']}.db",
                              "e_rd_pj": float(res["e_rd_pj"]), "e_wr_pj": float(res["e_wr_pj"])})
    return out


def pack_point(pdir: Path) -> Path:
    """A point's folder into its zip (KEEP_POINT), merged: the folder's top-level files and run tags replace the
    zip's, the zip's other runs stay; test-read, then the folder goes."""
    z = point_zip(pdir)
    new = {m: p.read_bytes() for m, p in arc.files_of(pdir, KEEP_POINT).items()}
    tags = {d.name for d in pdir.iterdir() if d.is_dir()}
    old = {m: b for m, b in arc.read_all(z).items() if "/" in m and m.split("/", 1)[0] not in tags}
    arc.write(z, {**old, **new})
    shutil.rmtree(pdir)
    return z


def scopes(netlist: Path, top: str, reached: set | None = None) -> list[str]:
    """Instance paths below the top that are designs of the netlist (sub-designs, not cells); `reached`, when
    given, gets every design instantiated on the way."""
    text = netlist.read_text()
    # DC indents some module headers (dot's multiplier: '    module dot_mul_64s_...'), so allow leading space
    bodies = dict(re.findall(r"^\s*module\s+(\S+)\s*\((.*?)^\s*endmodule", text, re.M | re.S))
    if top not in bodies:
        raise Fail(f"{netlist.name}: no module {top}")
    out = []

    def walk(mod: str, path: list[str]) -> None:
        for m, inst in re.findall(r"^\s*(\S+)\s+(\\\S+ |\w+)\s*\(", bodies[mod], re.M):
            if m in bodies:
                p = path + [inst.strip()]
                out.append(p)
                if reached is not None:
                    reached.add(m)
                walk(m, p)
    walk(top, [])
    return [".".join(x if not x.startswith("\\") else x + " " for x in p) for p in out]


def dump_block(tb: dict, netlist: Path) -> list[str]:
    L = ["    // The DUT's own nets and those of its sub-designs, not the cells' (no `celldefine in the models,",
         "    // docs/PITFALLS.md LIB2); the sequencer turns dumping on and off around the busy window.",
         "    initial begin : dump", "        string vcd;", "        if ($value$plusargs(\"VCD=%s\", vcd)) begin",
         "            $dumpfile(vcd);", f"            $dumpvars(1, {TB_TOP}.{DUT});"]
    L += [f"            $dumpvars(1, {TB_TOP}.{DUT}.{s});" for s in scopes(netlist, tb["top"])]
    L += ["            $dumpoff;", "        end", "    end"]
    return L


def sname(s: dict) -> str:
    """A stream's name in the TB (instances, plusargs, hex files): its arg, or forge's arg_in / arg_out when one
    container has an input and an output stream (axpy's y in place, sim/sources/forge.py)."""
    return s.get("name", s["arg"])


def lane_bits(s: dict) -> int:
    """Bits a lane of a stream's beat: an axis stream's element (hls.BITS of its dtype, X119); forge's streams are
    num_ch 64-bit words (their elements are packed into the words, X90)."""
    return hls.BITS[s["dtype"]] if s["kind"] == "axis" else 64


def stream_dw(s: dict) -> int:
    return lane_bits(s) * s["lanes"]


def sink_ew(s: dict) -> str:
    """The sink's lane width parameter, written only when it is not 64 (an int64 point's tb.sv as before)."""
    return "" if lane_bits(s) == 64 else f".EW({lane_bits(s)}), "


def hs_lines(tb: dict) -> list[str]:
    """in_hs and out_hs for the sequencer's port window (X119): valid and ready on any input (output) stream; the
    top declares the two wires with its others, before the sequencer uses them."""
    def any_of(side: str) -> str:
        terms = [f"({s['valid']} & {s['ready']})" for s in tb["streams"] if s["dir"] == side]
        return " | ".join(terms) or "1'b0"
    return [f"    assign in_hs = {any_of('in')};", f"    assign out_hs = {any_of('out')};", ""]


def stream_block(tb: dict, s: dict, clk: str, rst: str, go: str = "go") -> tuple[list[str], str | None]:
    dw, n = stream_dw(s), sname(s)
    L = [f"    wire [{dw - 1}:0] {s['data']};", f"    wire {s['valid']}, {s['ready']};"]
    if s["dir"] == "in":
        L += [f"    axis_src #(.DW({dw}), .NAME(\"{n}\")) src_{n} (.clk({clk}), "
              f".go({go}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}));"]
        return L, None
    L += [f"    wire complete_{n};",
          f"    axis_sink #(.DW({dw}), {sink_ew(s)}.NAME(\"{n}\")) snk_{n} (.clk({clk}), "
          f".rst_n({rst}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}), "
          f".complete(complete_{n}));"]
    return L, f"complete_{n}"


def tb_top_forge(tb: dict, netlist: Path) -> str:
    """The forge top: csr_seq on the wrapper's CSR port, the streams as for HLS (axis_src, axis_sink)."""
    c, clk, rst, L = tb["control"], tb["clock"]["port"], tb["reset"]["port"], []
    L += ["// Generated by sim/pwr.py from tb.json (source forge): do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {clk}, {rst}, go, sinks_complete, in_hs, out_hs;",
          f"    wire [31:0] {c['req_addr']}, {c['req_data']}, {c['rsp_data']};",
          f"    wire {c['req_write']}, {c['req_valid']}, {c['req_ready']}, {c['rsp_valid']}, {c['rsp_ready']};",
          f"    wire {c['busy']}, {c['done']};", "",
          f"    csr_seq #(.T_NS({CLOCK_NS})) seq (.clk({clk}), .rst_n({rst}), .go(go), .req_addr({c['req_addr']}), "
          f".req_data({c['req_data']}), .req_write({c['req_write']}), .req_valid({c['req_valid']}), "
          f".req_ready({c['req_ready']}), .rsp_data({c['rsp_data']}), .rsp_valid({c['rsp_valid']}), "
          f".rsp_ready({c['rsp_ready']}), .done({c['done']}), .sinks_complete(sinks_complete), "
          f".in_hs(in_hs), .out_hs(out_hs));", ""]
    done = []
    for s in tb["streams"]:
        lines, comp = stream_block(tb, s, clk, rst)
        L += lines + [""]
        if comp:
            done.append(comp)
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""] + hs_lines(tb)
    ports = [clk, rst, c["busy"], c["done"]]
    ports += [c[k] for k in ("req_addr", "req_data", "req_write", "req_valid", "req_ready", "rsp_data", "rsp_valid",
                             "rsp_ready")]
    ports += [s[k] for s in tb["streams"] for k in ("data", "valid", "ready")]
    L += [f"    {tb['top']} {DUT} ("] + [f"        .{p}({p}){',' if i < len(ports) - 1 else ''}"
                                         for i, p in enumerate(ports)] + ["    );", ""]
    L += dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def _dut(tb: dict, ports: list[str]) -> list[str]:
    return [f"    {tb['top']} {DUT} ("] + [f"        .{p}({p}){',' if i < len(ports) - 1 else ''}"
                                         for i, p in enumerate(ports)] + ["    );", ""]


def tb_top_bambu(tb: dict, netlist: Path) -> str:
    """The Bambu top: bambu_seq pulses start_port; the run-time pins are plain inputs, driven from time 0
    (before reset is released) and held; the streams as for HLS. idle_port is connected and not read."""
    c, clk, rst, L = tb["control"], tb["clock"]["port"], tb["reset"]["port"], []
    L += ["// Generated by sim/pwr.py from tb.json (source bambu): do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {clk}, {rst}, {c['start']}, go, sinks_complete, in_hs, out_hs;",
          f"    wire {c['done']}, {c['idle']};", "",
          f"    bambu_seq #(.T_NS({CLOCK_NS})) seq (.clk({clk}), .rst_n({rst}), .go(go), .start({c['start']}), "
          f".done({c['done']}), .sinks_complete(sinks_complete), .in_hs(in_hs), .out_hs(out_hs));", ""]
    done = []
    for s in tb["streams"]:
        lines, comp = stream_block(tb, s, clk, rst)       # reset is active low: the sinks' rst_n
        L += lines + [""]
        if comp:
            done.append(comp)
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""] + hs_lines(tb)
    for p in tb["pins"]:
        L += [f"    logic [{p['bits'] - 1}:0] {p['port']};",
              f"    initial if (!$value$plusargs(\"PIN_{p['port']}=%h\", {p['port']})) "
              f"$fatal(1, \"tb: +PIN_{p['port']}=<hex> missing\");", ""]
    ports = [clk, rst, c["start"], c["done"], c["idle"]]
    ports += [s[k] for s in tb["streams"] for k in ("data", "valid", "ready")]
    ports += [p["port"] for p in tb["pins"]]
    L += _dut(tb, ports) + dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def tb_top_xls(tb: dict, netlist: Path) -> str:
    """The XLS top: xls_seq presents the cfg beat; XLS's active-high reset is the TB's ~rst_n; the streams
    as for HLS, the sinks on the TB's rst_n."""
    c, clk, rst, L = tb["control"], tb["clock"]["port"], tb["reset"]["port"], []
    L += ["// Generated by sim/pwr.py from tb.json (source xls): do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {clk}, rst_n, {rst}, go, sinks_complete, in_hs, out_hs;",
          f"    wire [{c['bits'] - 1}:0] {c['data']};", f"    wire {c['valid']}, {c['ready']};",
          f"    assign {rst} = ~rst_n;", "",
          f"    xls_seq #(.T_NS({CLOCK_NS}), .CW({c['bits']})) seq (.clk({clk}), .rst_n(rst_n), .go(go), "
          f".cfg_data({c['data']}), .cfg_valid({c['valid']}), .cfg_ready({c['ready']}), "
          f".sinks_complete(sinks_complete), .in_hs(in_hs), .out_hs(out_hs));", ""]
    done = []
    for s in tb["streams"]:
        lines, comp = stream_block(tb, s, clk, "rst_n")
        L += lines + [""]
        if comp:
            done.append(comp)
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""] + hs_lines(tb)
    ports = [clk, rst, c["data"], c["valid"], c["ready"]]
    ports += [s[k] for s in tb["streams"] for k in ("data", "valid", "ready")]
    L += _dut(tb, ports) + dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def tb_top(tb: dict, netlist: Path) -> str:
    """The thin per-point top: tb.json's ports wired to the fixed modules of sim/tb/."""
    if tb["control"]["kind"] == "forge_csr":
        return tb_top_forge(tb, netlist)
    if tb["control"]["kind"] == "bambu_ctl":
        return tb_top_bambu(tb, netlist)
    if tb["control"]["kind"] == "xls_cfg":
        return tb_top_xls(tb, netlist)
    if tb["control"]["kind"].startswith("char_"):
        return tb_top_char(tb, netlist)
    if tb["control"]["kind"].startswith("strm_"):
        return strm_src.tb_top(tb, scopes(netlist, tb["top"]))
    c, L = tb["control"], []
    L += ["// Generated by sim/pwr.py from tb.json: do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {tb['clock']['port']}, {tb['reset']['port']}, {c['start']}, pin_vld, go;",
          f"    wire {c['done']}, {c['idle']}, {c['ready']}, sinks_complete, in_hs, out_hs;", ""]
    L += [f"    ap_ctrl_hs_seq #(.T_NS({CLOCK_NS})) seq (.clk({tb['clock']['port']}), .rst_n({tb['reset']['port']}), "
          f".go(go), .ap_start({c['start']}), .vld(pin_vld), .ap_done({c['done']}), .ap_ready({c['ready']}), "
          f".sinks_complete(sinks_complete), .in_hs(in_hs), .out_hs(out_hs));", ""]
    done = []
    for s in tb["streams"]:
        dw = stream_dw(s)
        L += [f"    wire [{dw - 1}:0] {s['data']};", f"    wire {s['valid']}, {s['ready']};"]
        if s["dir"] == "in":
            L += [f"    axis_src #(.DW({dw}), .NAME(\"{s['arg']}\")) src_{s['arg']} (.clk({tb['clock']['port']}), "
                  f".go(go), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}));"]
        else:
            L += [f"    wire complete_{s['arg']};",
                  f"    axis_sink #(.DW({dw}), {sink_ew(s)}.NAME(\"{s['arg']}\")) snk_{s['arg']} (.clk({tb['clock']['port']}), "
                  f".rst_n({tb['reset']['port']}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}), "
                  f".complete(complete_{s['arg']}));"]
            done.append(f"complete_{s['arg']}")
        L.append("")
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""] + hs_lines(tb)
    for p in tb["pins"]:
        L += [f"    logic [{p['bits'] - 1}:0] {p['port']} = '0, pv_{p['port']};",
              f"    assign {p['vld']} = pin_vld;",
              f"    initial if (!$value$plusargs(\"PIN_{p['port']}=%h\", pv_{p['port']})) "
              f"$fatal(1, \"tb: +PIN_{p['port']}=<hex> missing\");",
              f"    always @(posedge pin_vld) {p['port']} <= pv_{p['port']};", ""]
    ports = [tb["clock"]["port"], tb["reset"]["port"], c["start"], c["done"], c["idle"], c["ready"]]
    ports += [s[k] for s in tb["streams"] for k in ("data", "valid", "ready")]
    ports += [p[k] for p in tb["pins"] for k in ("port", "vld")]
    L += [f"    {tb['top']} {DUT} ("] + [f"        .{p}({p}){',' if i < len(ports) - 1 else ''}"
                                         for i, p in enumerate(ports)] + ["    );", ""]
    L += ["    // The DUT's own nets and those of its sub-designs, not the cells' (no `celldefine in the models,",
          "    // docs/PITFALLS.md LIB2); the sequencer turns dumping on and off around the busy window.",
          "    initial begin : dump", "        string vcd;", "        if ($value$plusargs(\"VCD=%s\", vcd)) begin",
          "            $dumpfile(vcd);", f"            $dumpvars(1, {TB_TOP}.{DUT});"]
    L += [f"            $dumpvars(1, {TB_TOP}.{DUT}.{s});" for s in scopes(netlist, tb["top"])]
    L += ["            $dumpoff;", "        end", "    end", "endmodule", ""]
    return "\n".join(L)


# ---------------------------------------------------------------- stimulus, reference, cycles
def beats_hex(x: np.ndarray, lanes: int, bits: int = 64) -> str:
    """One beat a line of `lanes` lanes of `bits` bits (an int8 or int32 axis element, X119; 64 otherwise), lane 0 in
    the low bits, each value wrapped to its lane."""
    out, mask = [], (1 << bits) - 1
    for b in range(len(x) // lanes):
        v = 0
        for lane in range(lanes):
            v |= (int(x[b * lanes + lane]) & mask) << (bits * lane)
        out.append(f"{v:0{lanes * bits // 4}x}\n")
    return "".join(out)


def words(x: np.ndarray, num_slc: int) -> np.ndarray:
    """Elements packed num_slc to a 64-bit word, element 0 in the low bits (snax-forge D142), as int64."""
    if num_slc == 1:
        return x
    bits = 64 // num_slc
    u = (x.astype(np.int64).reshape(-1, num_slc).view(np.uint64) & np.uint64((1 << bits) - 1))
    return np.bitwise_or.reduce(u << (np.arange(num_slc, dtype=np.uint64) * np.uint64(bits)), axis=1).view(np.int64)


def untoggled_bits(x: np.ndarray, beats: int, lanes: int) -> int:
    seen = np.bitwise_or.reduce(x.view(np.uint64).reshape(beats, lanes), axis=0)
    return sum(64 - bin(int(v)).count("1") for v in seen)


def stimulus_forge(tb: dict, size: str, seed: int) -> dict:
    """rand64: every input container full-range int64 at its shape (the design point's), seed `seed`, stream
    by stream in tb.json order (a container once), then each scalar a CSR takes (axpy's alpha) as a data pin; a
    scalar the recipe bakes takes the baked value (axpy_baked's alpha = 3). The reference from sim/ref.py, an
    in-place output (axpy's y) its <container>_out. Each stream's data in the order its streamer visits the
    container (tb.json's order, rowsum_2's A down the columns); every input bit must toggle (64 beats or more).
    A narrow stream (int8, int16, int32: tb.json's dtype) draws its container full-range at that dtype, its
    output wrapped to it (the kernel's int32 out and OP_TYPE), and moves num_slc elements a word, little-endian, a
    packed output's slices past its last result 0 (order -1); the data are those 64-bit words."""
    z = tb["sizes"][size]
    ins_s = [s for s in tb["streams"] if s["dir"] == "in"]
    rng = np.random.default_rng(seed)
    info = np.iinfo(np.int64)
    ins = {}
    for s in ins_s:
        if s["arg"] not in ins:
            dinfo = np.iinfo(s.get("dtype", "int64"))
            ins[s["arg"]] = rng.integers(dinfo.min, dinfo.max, size=int(np.prod(s["shape"])), dtype=np.int64,
                                         endpoint=True)
    pins = {sc["container"]: int(rng.integers(info.min, info.max, dtype=np.int64, endpoint=True))
            for sc in tb.get("scalars", [])}
    pins.update({c: int(v) for c, v in tb.get("baked", {}).items()})
    shape = {k.lower(): v for k, v in z["shape"].items()}         # sim/ref.py's rowsum takes m
    got = ref(tb["kernel"], ins, {**shape, **pins})
    outs = {}
    for s in tb["streams"]:
        if s["dir"] == "out":
            a = s["arg"]
            if a not in got and f"{a}_out" not in got:
                raise Fail(f"reference: sim/ref.py's {tb['kernel']} gives {sorted(got)}, no {a}")
            outs[a] = got[a] if a in got else got[f"{a}_out"]
            outs[a] = np.asarray(outs[a]).astype(s.get("dtype", "int64")).astype(np.int64)   # wraps at int32
    data, untoggled = {}, {}
    for s in tb["streams"]:
        x = (ins if s["dir"] == "in" else outs)[s["arg"]].ravel()
        if s.get("order") is not None:
            x = np.append(x, 0)[np.asarray(s["order"], dtype=np.int64)]     # -1: a packed word's empty slice, 0
        elems = s.get("elems", s["lanes"])
        if len(x) != s["beats"] * elems:
            raise Fail(f"stream {sname(s)}: {len(x)} values, the streamer moves {s['beats']} beats of {elems}")
        data[sname(s)] = np.ascontiguousarray(words(x, s.get("num_slc", 1)))
        if s["dir"] == "in":
            k = untoggled_bits(data[sname(s)], s["beats"], s["lanes"])
            if k:
                untoggled[sname(s)] = k
                if s["beats"] >= TOGGLE_BEATS:
                    raise Fail(f"stimulus: {k} bits of {sname(s)} never toggle")
    return {"ins": ins, "pins": pins, "outs": outs, "data": data, "beats": ins_s[0]["beats"], "untoggled": untoggled}


# The forge reference check: sim/ref.py against snax-forge's kernel body (forge/query.py ref), once per kernel,
# size, seed and dtypes in a batch (the inputs depend on N, the seed and the dtypes, not on W: X90)
REF_CHECKED: dict = {}
REF_LOCK = threading.Lock()


def forge_ref_check(tb: dict, size: str, seed: int, st: dict, rdir: Path) -> dict:
    key = (tb["kernel"], size, seed, tuple(sorted(st["pins"].items())),     # axpy and axpy_baked: alpha apart
           tuple(sorted((tb.get("dtypes") or {}).items())))                  # i8 and i16 apart
    with REF_LOCK:
        if key not in REF_CHECKED:
            ins = {**st["ins"], **{c: np.array(v, dtype=np.int64) for c, v in st["pins"].items()}}
            got = forge_src.kernel_ref(tb["kernel"], ins, rdir / "ref_check", tb.get("symbols"), tb.get("dtypes"))
            shutil.rmtree(rdir / "ref_check", ignore_errors=True)
            same = {a: bool(np.array_equal(np.asarray(got["outs"][a]).ravel()[: len(v)], v)
                            and np.asarray(got["outs"][a]).size >= len(v)) for a, v in st["outs"].items()}
            REF_CHECKED[key] = {"func": got["info"]["func"], "point": tb["point"], "equal": same,
                                "outs": {a: np.asarray(v).copy() for a, v in st["outs"].items()}}
        chk = REF_CHECKED[key]
    if not all(chk["equal"].values()):
        raise Fail(f"sim/ref.py differs from snax-forge's {chk['func']}: {chk['equal']}")
    for a, v in st["outs"].items():
        if not np.array_equal(v, chk["outs"][a]):
            raise Fail(f"reference {a} differs from the batch's first {tb['kernel']} run on the same inputs")
    return {"against": chk["func"], "checked_on": chk["point"], "equal": chk["equal"]}


def stimulus(tb: dict, size: str, stim: str, seed: int) -> dict:
    """{'ins': {arg: array}, 'pins': {pin: int}, 'outs': {arg: array}, 'beats': n}"""
    cfg = dict(tb["sizes"][size])
    beats = cfg["loop_count"]
    ins_s = [s for s in tb["streams"] if s["dir"] == "in"]
    data_pins = [p["port"] for p in tb["pins"] if p["from"].startswith("data:")]
    data_pins += [f["name"] for f in tb["control"].get("fields", []) if f["from"].startswith("data:")]   # xls cfg
    pins = dict(cfg)
    if stim == "rand64":
        rng = np.random.default_rng(seed)
        info = np.iinfo(np.int64)
        # each input uniform over its stream's dtype (X119; at int64 X19's full-range draws, in the same order)
        ins = {}
        for s in ins_s:
            d = np.iinfo(s["dtype"])
            ins[s["arg"]] = rng.integers(d.min, d.max, size=beats * s["lanes"], dtype=np.int64, endpoint=True)
        for p in data_pins:
            pins[p] = int(rng.integers(info.min, info.max, dtype=np.int64, endpoint=True))
    elif stim == "forge":
        if "ref" in tb:
            raise Fail("forge stimulus: hls-exercises' data.h is read for int64 points only (a narrow point: rand64)")
        f = hls.data_h(tb["point"], size)
        if not f.is_file():
            raise Fail(f"forge stimulus: no {f}")
        d = hls.read_data_h(f)
        ins = {s["arg"]: np.array(d[f"IN_{s['arg']}"], dtype=np.int64) for s in ins_s}
        for p in data_pins:
            pins[p] = int(d[f"IN_{p}"][0])
        for s in ins_s:
            if len(ins[s["arg"]]) != beats * s["lanes"]:
                raise Fail(f"forge stimulus: IN_{s['arg']} has {len(ins[s['arg']])} values, not {beats} beats")
    else:
        raise Fail(f"stimulus {stim} unknown")
    outs = narrow_outs(tb, ins) if "ref" in tb else ref(tb["kernel"], ins, pins)
    if stim == "forge":
        prm = hls.params_of(tb["point"])
        inv = {v: k for k, v in prm.get("dace", {}).get("split_inout", {}).items()}
        for arg, v in outs.items():
            exp = d.get(f"EXP_{arg}") or d.get(f"EXP_{inv.get(arg, arg)}")
            if exp is None or not np.array_equal(v, np.array(exp, dtype=np.int64)):
                raise Fail(f"sim/ref.py differs from data.h EXP for {arg}")
    # Every input bit toggles at least once (from the 0 the TB holds before go). Enforced from TOGGLE_BEATS
    # beats up: with B random beats a bit stays 0 with probability 2^-B, so a task of a few beats (n64 at
    # W = 32 is 2 beats) cannot pass with any seed; below that the count is recorded.
    untoggled = {}
    for s in ins_s:
        eb = lane_bits(s)          # an int8 lane has 8 bits to toggle
        x = (ins[s["arg"]].view(np.uint64) & np.uint64((1 << eb) - 1)).reshape(beats, s["lanes"])
        seen = np.bitwise_or.reduce(x, axis=0)
        n = sum(eb - bin(int(v)).count("1") for v in seen)
        if n:
            untoggled[s["arg"]] = n
            if beats >= TOGGLE_BEATS:
                raise Fail(f"stimulus: {n} bits of {s['arg']} never toggle")
    for s in tb["streams"]:
        if s["dir"] == "out" and len(outs[s["arg"]]) % s["lanes"]:
            raise Fail(f"reference {s['arg']}: {len(outs[s['arg']])} values do not fill {s['lanes']} lanes")
    return {"ins": ins, "pins": pins, "outs": outs, "beats": beats, "config": cfg, "untoggled": untoggled}


# A narrow HLS point's reference (X119): snax-forge's kernel at the point's types, once per kernel, dtypes and inputs
# in a batch (Vitis, Bambu and XLS of one kernel draw the same inputs)
NARROW_REF: dict = {}


def narrow_outs(tb: dict, ins: dict) -> dict:
    """{output arg: int64 array}: snax-forge's kernel body (forge/query.py ref through sim/sources/forge.py's
    kernel_ref, as the forge source checks) at tb.json's ref dtypes on these inputs, each output at its dtype."""
    import hashlib
    import tempfile

    r = tb["ref"]
    h = hashlib.sha256()
    for a in sorted(ins):
        h.update(a.encode() + np.ascontiguousarray(ins[a], dtype=np.int64).tobytes())
    key = (r["kernel"], json.dumps(r["dtypes"], sort_keys=True), h.hexdigest())
    with REF_LOCK:
        if key not in NARROW_REF:
            (ROOT / "tmp").mkdir(exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="narrow_ref_", dir=ROOT / "tmp"))
            try:
                got = forge_src.kernel_ref(r["kernel"], ins, work / "ref", {}, r["dtypes"])
            except ValueError as e:
                raise Fail(f"reference: {e}") from None
            finally:
                shutil.rmtree(work, ignore_errors=True)
            NARROW_REF[key] = {a: np.asarray(v).ravel().copy() for a, v in got["outs"].items()}
        got = NARROW_REF[key]
    outs = {}
    for s in tb["streams"]:
        if s["dir"] == "out":
            if s["arg"] not in got:
                raise Fail(f"reference: snax-forge's {r['kernel']} gives {sorted(got)}, no {s['arg']}")
            outs[s["arg"]] = got[s["arg"]].astype(s["dtype"]).astype(np.int64)
    return outs


def cosim(tb: dict) -> dict:
    """{size tag: (loop_count, cosim_lat_avg)} for this point's case and W."""
    tier = tb["point"].split("/")[0]
    out = {}
    with (RESULTS / "hls_cycles.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["tier"], r["kernel"], r["case"], r["W"]) == (tier, tb["kernel"], tb["case"], str(tb["W"])):
                lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
                out[r["size"]] = (lc, int(float(r["cosim_lat_avg"])))
    return out


def expected_cycles(tb: dict, size: str) -> tuple[int | None, str]:
    """Cosim's cycles at a cosim size, else its line a x loop_count + b through cosim's two sizes."""
    cs = cosim(tb)
    if size in cs:
        return cs[size][1], f"cosim {size}"
    same = [t for t in cs if t in tb["sizes"] and tb["sizes"][t] == tb["sizes"][size]]
    if same:                    # another tag for the same task (rowsum dace's n2048 is its cosim size m16_n128)
        return cs[same[0]][1], f"cosim {same[0]} (the same pins)"
    if len(cs) < 2:
        return None, "no cosim line"
    (l1, c1), (l2, c2) = sorted(cs.values())[:2]
    a, b = (c2 - c1) / (l2 - l1), c1 - (c2 - c1) / (l2 - l1) * l1
    lc = tb["sizes"][size]["loop_count"]
    note = f"line {a:g} x loop_count + {b:g}"
    if a != int(a) or b != int(b):
        return None, note + " (not integer)"
    return int(a) * lc + int(b), note


# ---------------------------------------------------------------- activity and power
def saif_check(saif: Path, cycles: int, clock: str) -> dict:
    """T0 + T1 + TX = DURATION on every net, DURATION = cycles x clock, the clock toggles 2 x cycles.

    vcd2saif adds (TZ t) for time at Z. DC leaves undriven bits in declared vector wires (b_fu_76[1] when
    only the flop's QN is used); they are Z for the whole window, are not nets in PT, and are counted
    apart (z_nets). A net that is Z for part of the window fails, as does an entry the parser misses."""
    s = saif.read_text()
    ts = re.search(r"\(TIMESCALE\s+(\d+)\s*(\w+)\)", s)
    unit = int(ts.group(1)) * syn.SECONDS[ts.group(2).lower()]
    dur = int(re.search(r"\(DURATION\s+(\d+)\)", s).group(1))
    nets = re.findall(r"\(\s*(\S+)\s*\(T0 (\d+)\)\s*\(T1 (\d+)\)\s*\(TX (\d+)\)\s*(?:\(TZ (\d+)\)\s*)?\(TC (\d+)\)", s)
    entries = s.count("(T0 ")
    nets = [(n, int(t0), int(t1), int(tx), int(tz or 0), int(tc)) for n, t0, t1, tx, tz, tc in nets]
    z_nets = [n for n in nets if n[4] == dur]
    driven = [n for n in nets if n[4] != dur]
    bad = [n for n in driven if n[1] + n[2] + n[3] != dur or n[4]]
    want = round(cycles * CLOCK_NS * 1e-9 / unit)
    clk = [n for n in nets if n[0] == clock]
    info = {"entries": entries, "nets": len(driven), "z_nets": len(z_nets), "duration": dur, "unit_s": unit,
            "bad_nets": len(bad), "tx_nets": sum(1 for n in driven if n[3]), "clk_tc": clk[0][5] if clk else None}
    if len(nets) != entries:
        raise Fail(f"saif: parsed {len(nets)} of {entries} entries")
    if bad:
        raise Fail(f"saif: T0 + T1 + TX != DURATION on {len(bad)} driven nets")
    if dur != want:
        raise Fail(f"saif: DURATION {dur} is not {cycles} cycles ({want})")
    if not clk or clk[0][5] != 2 * cycles:
        raise Fail(f"saif: {clock} TC {info['clk_tc']}, expected {2 * cycles}")
    return info


def saif_floating(saif: Path) -> set:
    """Paths (instance/.../net, below the DUT, escapes dropped) of the SAIF's nets at Z for the whole window."""
    s = saif.read_text()
    dur = re.search(r"\(DURATION\s+(\d+)\)", s).group(1)
    toks = re.findall(r"\(|\)|[^\s()]+", s)
    out, path, stack, i = set(), [], [], 0
    while i < len(toks):
        tk = toks[i]
        if tk == "(":
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if nxt == "INSTANCE":
                path.append(toks[i + 2].replace("\\", ""))
                stack.append("inst")
                i += 3
                continue
            if nxt not in ("T0", "T1", "TX", "TZ", "TC", "IG", "NET", "PORT", "SAIFILE", "SAIFVERSION", "DIRECTION",
                           "DESIGN", "DATE", "VENDOR", "PROGRAM_NAME", "VERSION", "DIVIDER", "TIMESCALE",
                           "DURATION") and i + 2 < len(toks) and toks[i + 2] == "(":
                j, vals = i + 2, {}
                while j + 3 < len(toks) and toks[j] == "(" and toks[j + 1] in ("T0", "T1", "TX", "TZ", "TC", "IG"):
                    vals[toks[j + 1]] = toks[j + 2]
                    j += 4
                if vals.get("TZ") == dur:
                    out.add("/".join(path[2:] + [nxt.replace("\\", "")]))      # below tb/dut
            stack.append(None)
        elif tk == ")":
            if stack and stack.pop() == "inst":
                path.pop()
        i += 1
    return out


def not_annotated(rpt: Path) -> list[str]:
    text = rpt.read_text()
    at = text.find("List of nonannotated nets")
    return [ln.strip() for ln in text[at:].splitlines()[1:] if ln.startswith("\t") and ln.strip()] if at >= 0 else []


def coverage(rpt: Path) -> tuple[int, int]:
    m = re.search(r"^\s*Nets\s+(\d+)\([\d.]+%\).*?\s(\d+)\s*$", rpt.read_text(), re.M)
    if not m:
        raise Fail("pt: no net count in switching_activity.rpt")
    return int(m.group(1)), int(m.group(2))


def pt_to_uw(units: Path) -> float:
    m = re.search(r"User Specified Power Unit\s*:\s*([0-9.eE+-]+)\s*Watt", units.read_text())
    if not m:
        raise Fail("pt: no power unit in units.rpt")
    return float(m.group(1)) * 1e6


def pt_groups(rep: Path, groups=None) -> dict:
    """{group: (internal, switching, leakage) in uW} from PT's power.rpt (syn.POWER_GROUPS by default)."""
    to_uw = pt_to_uw(rep / "units.rpt")
    text = (rep / "power.rpt").read_text()
    out = {}
    for g in (groups or syn.POWER_GROUPS):
        m = re.search(rf"^{g}\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
        if not m:
            raise Fail(f"pt: no group {g} in power.rpt")
        out[g] = tuple(float(x) * to_uw for x in m.groups())
    return out


def pt_hierarchy(rep: Path) -> list[dict]:
    """[{path, design, dyn_uw}] from report_power -hierarchy, paths built from the indentation."""
    to_uw = pt_to_uw(rep / "units.rpt")
    rows, stack = [], []
    num = r"([-0-9.eE+]+|N/A)"
    for line in (rep / "power_hierarchy.rpt").read_text().splitlines():
        m = re.match(rf"^(\s*)(\S+)(?:\s+\((\S+)\))?\s+{num}\s+{num}\s+{num}\s+{num}\s+[\d.]+\s*$", line)
        if not m or m.group(4) == "N/A":
            continue
        depth = len(m.group(1))
        while stack and stack[-1][0] >= depth:
            stack.pop()
        stack.append((depth, m.group(2)))
        rows.append({"path": "/".join(n for _, n in stack), "design": m.group(3) or m.group(2),
                     "dyn_uw": (float(m.group(4)) + float(m.group(5))) * to_uw})
    return rows


def _num(x) -> str:
    return syn._num(x) if isinstance(x, float) else str(x)


def energy_row(r: dict, groups: dict, flop_bits: int | None) -> dict:
    e = {syn.POWER_GROUPS[g]: (i + s) * CLOCK_NS / 1000.0 for g, (i, s, _) in groups.items()}   # uW x ns -> pJ
    e_flop = e["clk"] + e["reg"] + e["seq"]
    e_dyn = e_flop + e["comb"]
    cyc, beats = r["cycles"], r["beats"]
    r.update({"e_clk_pj": e["clk"], "e_reg_pj": e["reg"], "e_seq_pj": e["seq"], "e_comb_pj": e["comb"],
              "e_flop_pj": e_flop, "e_dyn_pj": e_dyn, "p_dyn_uw": e_dyn / CLOCK_NS * 1000.0,
              "e_comb_fire_pj": e["comb"] * cyc / beats, "e_flop_fire_pj": e_flop * cyc / beats,
              "e_run_pj": e_dyn * cyc, "flop_bits": flop_bits if flop_bits is not None else "",
              "e_bit_pj": e_flop / flop_bits if flop_bits else ""})
    return r


def flop_bits_of(tech: str, point: str) -> int | None:
    f = RESULTS / tech / "synth_dc.csv"
    with f.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["point"] == point and float(r["clock_ns"]) == CLOCK_NS and syn.gate_flag(r) == gate()
                    and r["seq_cells"]):
                return int(r["seq_cells"])
    return None


# ---------------------------------------------------------------- one point
def cell_model(tech: str) -> Path:
    """The technology's Questa cell models: CELL_MODELS' file next to the .db syn.py resolves (also cluster gls)."""
    return Path(syn.resolve(syn.load_tech(tech))["lib_db"]).parent / CELL_MODELS[tech][0]


def cells_lib(tech: str) -> Path:
    """The cell models compiled once per technology into sim/runs/<tech>/_cells."""
    lib = RUNS / tech / "_cells"
    if (lib / "_info").is_file():
        return lib
    _model, opts = CELL_MODELS[tech]
    src = cell_model(tech)
    lib.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([tool("vlib"), str(lib)], check=True, capture_output=True)
    log = RUNS / tech / "_cells.vlog.log"
    if run_tool([tool("vlog"), *opts, "-work", str(lib), str(src)], log, RUNS / tech) or \
            re.search(r"Errors: [1-9]", log.read_text()):
        sys.exit(f"vlog of {src} failed: {log}")
    return lib


def run_tag(size: str, stim: str, seed: int) -> str:
    tag = f"{size}_forge" if stim == "forge" else f"{size}_s{seed}"
    return tag if INITREG_SEED is None else f"{tag}_r{INITREG_SEED}"


def compile_point(tb: dict, tech: str, pdir: Path, netlist: Path, cells: Path, ram: dict | None = None) -> None:
    logs = pdir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (pdir / "tb.sv").write_text(tb_top(tb, netlist))
    work = pdir / "work"
    subprocess.run([tool("vlib"), str(work)], check=True, capture_output=True)
    if tb.get("source", "hls") != "hls":   # every module gets a dump scope (DC6)
        reached = set()
        scopes(netlist, tb["top"], reached)
        missing = sorted(forge_src.netlist_modules(netlist) - reached - {tb["top"]})
        if missing:
            raise Fail(f"scopes: modules of the netlist with no dump scope: {missing}")
    tb_files = tb["tb_files"] if tb.get("source") == "char" else [] if tb.get("source") in STRM else \
        TB_FILES[tb.get("source", "hls")]
    incdir = [f"+incdir+{TB_DIR}"] if tb.get("source") == "char" else []    # char_seq_core.svh
    steps = [("vlog_tb", [tool("vlog"), "-sv", *incdir, "-work", str(work),
                          *(str(TB_DIR / f) for f in tb_files),
                          str(pdir / "tb.sv")]),
             ("vlog_netlist", [tool("vlog"), "-timescale", "1ns/1ps", "-work", str(work), str(netlist)]),
             # the SRAM macros' behavioural models (contents, read address and rdata start 0, as Vitis's .dat)
             *([("vlog_macros", [tool("vlog"), "-sv", "+define+SRAM_INIT_ZERO", "-work", str(work),
                                 *(str(m["v"]) for m in ram["macros"])])] if ram and ram["macros"] else []),
             ("vopt", [tool("vopt"), "-work", str(work), "-L", str(cells), TB_TOP,
                       "+initreg+0" if INITREG_SEED is None else "+initreg=ru", "+acc=n", "-o", "tb_opt"])]
    for name, cmd in steps:
        log = logs / f"{name}.log"
        rc = run_tool(cmd, log, pdir)
        if rc or re.search(r"Errors: [1-9]", log.read_text()):
            raise Fail(f"{name} (logs/{name}.log)")


def run_one(tb: dict, tech: str, pdir: Path, size: str, stim: str, seed: int, threads: int, times: dict,
            row: dict, syn_d: Path, ram: dict | None = None) -> dict:
    """One run; fills `row` as it goes, so a failed run keeps what it got (cycles). Returns its info.
    syn_d: the DC run unpacked (point_inputs), PT's PWR_RUN."""
    rdir = pdir / run_tag(size, stim, seed)
    if rdir.exists():
        shutil.rmtree(rdir)
    (rdir / "stim").mkdir(parents=True)
    cfg = tb["sizes"][size]
    forge = tb["control"]["kind"] == "forge_csr"
    if forge:
        row.update({"config": " ".join(f"{name}={v}" for _, v, name in cfg["writes"][:-1]),
                    "beats": next(s["beats"] for s in tb["streams"] if s["dir"] == "in")})
    else:
        row.update({"config": " ".join(f"{k}={v}" for k, v in cfg.items()), "beats": cfg["loop_count"]})
    info = {"run": str(rdir.relative_to(ROOT)), "times": times}

    t = time.time()
    st = stimulus_forge(tb, size, seed) if forge else stimulus(tb, size, stim, seed)
    plus = []
    if forge:
        info["ref_check"] = forge_ref_check(tb, size, seed, st, rdir)
        # JOBS and the JOB_BEATS, then each scalar's CSRs (C§17: low word first at 64 bits), START last
        scal = []
        for sc in tb.get("scalars", []):
            v = st["pins"][sc["container"]] & MASK64
            words = [v & 0xFFFFFFFF, v >> 32] if len(sc["csrs"]) == 2 else [v & 0xFFFFFFFF]
            scal += [[off, wv, name] for (off, name), wv in zip(sc["csrs"], words)]
        writes = cfg["writes"][:-1] + scal + cfg["writes"][-1:]
        info["csr_writes"] = [[name, val] for _, val, name in writes]
        f = rdir / "stim" / "csr.hex"
        f.write_text("".join(f"{off:08x}{val & 0xFFFFFFFF:08x}\n" for off, val, _ in writes))
        plus += [f"+CSR_HEX={f}", f"+CSR_N={len(writes)}",
                 f"+BUSY_COUNTER_ADDR={tb['control']['csrs']['BUSY_COUNTER']:x}"]
    for s in tb["streams"]:
        if forge:
            x = st["data"][sname(s)]
        else:
            x = st["ins"][s["arg"]] if s["dir"] == "in" else st["outs"][s["arg"]]
        f = rdir / "stim" / f"{sname(s)}.hex"
        f.write_text(beats_hex(x, s["lanes"], lane_bits(s)))
        plus += [f"+{sname(s)}_HEX={f}", f"+{sname(s)}_BEATS={len(x) // s['lanes']}"]
    for p in tb["pins"]:
        plus.append(f"+PIN_{p['port']}={st['pins'][p['port']] & ((1 << p['bits']) - 1):x}")
    if tb["control"]["kind"] == "xls_cfg":      # the one cfg beat, fields packed first-high
        plus.append(f"+CFG={src().cfg_word(tb, st['pins']):x}")
    (rdir / "stim" / "pins.json").write_text(json.dumps(st["pins"], indent=1) + "\n")
    info["untoggled_bits"] = st["untoggled"]
    if forge:
        exp, how = cfg["expected_cycles"], f"snax-forge's group_counter: {cfg['expected_from']}"
    elif SOURCE == "hls":
        exp, how = expected_cycles(tb, size)
    else:       # bambu, xls: the line through the tool's own cycle CSV
        exp, how = src().expected_cycles(tb, size, RESULTS)
    info["expected_cycles"], info["expected_from"] = exp, how
    row["expected_cycles"] = exp if exp is not None else ""
    times["stim"] = time.time() - t

    vcd = rdir / "dut.vcd"
    try:
        t = time.time()
        timeout = max(10000, 4 * (exp or 0) + 1000)
        cmd = [tool("vsim"), "-c", "-work", str(pdir / "work"), "tb_opt", "+nospecify", "+notimingchecks",
               "-wlf", str(rdir / "vsim.wlf"), f"+VCD={vcd}", f"+TIMEOUT={timeout}", *plus, "-do", str(RUN_DO)]
        if INITREG_SEED is not None:
            cmd.insert(-2, f"+initreg+{INITREG_SEED}")
            info["initreg"] = f"random, seed {INITREG_SEED} (vopt +initreg=ru, vsim +initreg+{INITREG_SEED})"
        run_tool(cmd, rdir / "vsim.log", rdir)
        times["vsim"] = time.time() - t
        log = (rdir / "vsim.log").read_text(errors="replace")
        sinks = re.findall(r"TB: sink (\S+): beats (\d+) expected (\d+) mismatches (\d+) xz (\d+)", log)
        win = re.search(r"TB: window t0_ns ([\d.]+) t1_ns ([\d.]+) cycles (\d+)", log)
        if "TB: FAIL: timeout" in log:
            raise Fail("sim: timeout")
        if not win or len(sinks) != sum(1 for s in tb["streams"] if s["dir"] == "out"):
            raise Fail("sim: no result (vsim.log)")
        for name, n, want, mism, xz in sinks:
            if n != want or mism != "0" or xz != "0":
                raise Fail(f"sim: sink {name} beats {n}/{want}, {mism} mismatches, {xz} X/Z")
        cycles = int(win.group(3))
        row["cycles"] = cycles
        info["window_ns"] = [float(win.group(1)), float(win.group(2))]
        # the port window (X119): first input beat accepted to the last output beat accepted, both included;
        # recorded beside the energy window, which stays the source's (X12, X23, X44)
        pw = re.search(r"TB: ports first_in (-?\d+) last_out (-?\d+)", log)
        if not pw or int(pw.group(1)) < 1 or int(pw.group(2)) < int(pw.group(1)):
            raise Fail("sim: no port window (the 'TB: ports' line, vsim.log)")
        first_in, last_out = int(pw.group(1)), int(pw.group(2))
        row["cycles_ports"] = last_out - first_in + 1
        info["ports"] = {"first_in": first_in, "last_out": last_out, "cycles_ports": row["cycles_ports"],
                         "le_cycles_plus_1": row["cycles_ports"] <= cycles + 1}
        if ram and ram["macros"]:       # each macro instance's RAMCOUNT line (the whole run: idle outside it)
            counts = re.findall(r"RAMCOUNT\s+(\S+)\s+(\S+)\s+reads\s+(\d+)\s+writes\s+(\d+)", log)
            cells = {m["cell"]: m for m in ram["macros"]}
            if not counts or any(c not in cells for _, c, _, _ in counts):
                raise Fail(f"ram: RAMCOUNT lines {counts}, macros {sorted(cells)}")
            info["ramcount"] = [{"inst": i, "cell": c, "reads": int(r), "writes": int(w)} for i, c, r, w in counts]
        if forge and "TB: FAIL" in log:
            raise Fail("sim: " + re.search(r"TB: FAIL: (.*)", log).group(1))
        # the window is the measurement; the expected count (and forge's BUSY_COUNTER) beside it, failing only
        # past CYCLES_TOL of the window
        if forge:
            cnt = re.search(r"TB: busy_counter (\d+)", log)
            info["counter"] = int(cnt.group(1)) if cnt else None
            if info["counter"] is None:
                raise Fail("cycles: no BUSY_COUNTER read back")
            row["counter"], row["counter_diff"] = info["counter"], info["counter"] - cycles
            if abs(info["counter"] - cycles) > CYCLES_TOL * cycles:
                raise Fail(f"cycles: window {cycles}, BUSY_COUNTER {info['counter']}, over {CYCLES_TOL:.0%} apart")
        if exp is None:
            raise Fail(f"cycles: no expected value ({how})")
        row["expected_diff"] = exp - cycles
        info["expected_diff"] = exp - cycles
        if abs(exp - cycles) > CYCLES_TOL * cycles:
            raise Fail(f"cycles: window {cycles}, expected {exp} ({how}), over {CYCLES_TOL:.0%} apart")

        t = time.time()
        head = vcd.open().read(4096)
        m = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end", head)
        unit = int(m.group(1)) * syn.SECONDS[m.group(2).lower()]
        t0, t1 = (round(x * 1e-9 / unit) for x in info["window_ns"])
        info["vcd_bytes"] = vcd.stat().st_size
        saif = rdir / "busy.saif"
        rc = run_tool([tool("vcd2saif"), "-input", str(vcd), "-output", str(saif), "-instance", f"{TB_TOP}/{DUT}",
                       "-time", str(t0), str(t1)], rdir / "vcd2saif.log", rdir)
        times["vcd2saif"] = time.time() - t
        if rc or not saif.is_file():
            raise Fail("vcd2saif (vcd2saif.log)")
    finally:
        vcd.unlink(missing_ok=True)      # no VCD is kept, whatever the result

    t = time.time()
    info["saif"] = saif_check(saif, cycles, tb["clock"]["port"])
    times["saif_check"] = time.time() - t

    t = time.time()
    ptd = rdir / "pt"
    ptd.mkdir()
    env = {**os.environ, "PWR_RUN": str(syn_d), "PWR_MODE": "saif", "PWR_ACT": str(saif),
           "PWR_STRIP": f"{TB_TOP}/{DUT}", "PWR_OUT": str(ptd), "PWR_THREADS": str(threads)}
    if ram and ram["macros"]:
        env["PWR_RAM_DBS"] = " ".join(str(m["db"]) for m in ram["macros"])
    rc = run_tool([tool("pt_shell", "PT_SHELL"), "-no_init", "-f", str(PT_SCRIPT), "-output_log_file",
                   str(ptd / "pt_shell.log")], ptd / "pt_stdout.log", ptd, env, stdin_null=True)
    times["pt"] = time.time() - t
    if rc or not (ptd / "power.rpt").is_file():
        raise Fail("pt (pt/pt_shell.log)")
    ann, total = coverage(ptd / "switching_activity.rpt")
    info["annotated"] = [ann, total]
    shutil.copy2(ptd / "not_annotated.rpt", rdir / "not_annotated.rpt")
    if forge:
        # A net PT did not annotate that is Z for the whole window in the SAIF has no driver: DC left ports of a
        # constant output floating (STATUS bits 2-31 of <tag>_ctrl, and their <tag>_csr inputs), with no cell on
        # them. They are nets for PT (hierarchical pins), unlike DC5's undriven wire bits, and cost nothing; they
        # leave the denominator, every other net must be annotated as for HLS (docs/power.md, Forge).
        missed = not_annotated(rdir / "not_annotated.rpt")
        floating = saif_floating(saif)
        info["floating"] = sorted(n for n in missed if n in floating)
        rest = [n for n in missed if n not in floating]
        info["not_annotated_driven"] = rest[:50]
        total -= len(info["floating"])
    if ann < MIN_ANNOTATED / 100 * total:
        raise Fail(f"pt: {ann} of {total} nets annotated, under {MIN_ANNOTATED:g}%")
    info["wire_load"] = wire_load_check(ptd / "wire_load.rpt")
    groups = pt_groups(ptd)
    info["modules"] = pt_hierarchy(ptd)
    e_ram = None
    if ram and ram["macros"]:
        # the macros are PT's black_box group; their internal energy is PT7's averaged figure (kept as a check),
        # replaced by the counted accesses; their output nets' switching stays the logic's, with the
        # combinational group (the loads it drives)
        bb_int, bb_sw, _ = pt_groups(ptd, ["black_box"])["black_box"]
        i, s_, l = groups["combinational"]
        groups["combinational"] = (i, s_ + bb_sw, l)
        cells = {m["cell"]: m for m in ram["macros"]}
        reads = sum(c["reads"] for c in info["ramcount"])
        writes = sum(c["writes"] for c in info["ramcount"])
        e_ram = sum(c["reads"] * cells[c["cell"]]["e_rd_pj"] + c["writes"] * cells[c["cell"]]["e_wr_pj"]
                    for c in info["ramcount"])
        row.update({"ram_kind": "macro", "ram_reads": reads, "ram_writes": writes,
                    "e_ram_pt_pj": bb_int * CLOCK_NS / 1000.0 * cycles})
    energy_row(row, groups, flop_bits_of(tech, tb["point"]))
    if e_ram is not None:
        row["e_ram_pj"] = e_ram
        row["e_run_pj"] = float(row["e_run_pj"]) + e_ram         # the task: the logic's window plus the memory
    elif ram:                       # flops: the RAM modules' instances, inside PT's total already
        hits = [m for m in info["modules"] if any(m["design"].startswith(r) for r in ram["modules"])]
        if not hits:
            raise Fail(f"ram: no instance of {ram['modules']} in power_hierarchy.rpt")
        top_depth = min(m["path"].count("/") for m in hits)
        row.update({"ram_kind": "flops", "e_ram_pj": sum(m["dyn_uw"] for m in hits if m["path"].count("/") == top_depth)
                    * CLOCK_NS / 1000.0 * cycles})
    row["status"] = "ok"
    return info


def wire_load_check(rpt: Path) -> dict:
    """PITFALLS PT1: after set_load 0 and set_resistance 0 no net may keep a wire capacitance or resistance."""
    m = re.search(r"nets: (\d+), with wire_capacitance_max > 0: (\d+), with net_resistance_max > 0: (\d+)",
                  rpt.read_text() if rpt.is_file() else "")
    if not m:
        raise Fail(f"pt: no wire-load count in {rpt.name}")
    nets, wc, wr = (int(x) for x in m.groups())
    if wc or wr:
        raise Fail(f"pt: {wc} nets with wire capacitance, {wr} with resistance (PITFALLS PT1)")
    return {"nets": nets, "wire_cap_nets": wc, "wire_res_nets": wr}


def build_tb(point: str, netlist: Path, bundle: Path | None) -> dict:
    """The point's tb.json from its source's adapter (forge, char: from the unpacked bundle and the netlist's
    ports; bambu, xls: from the netlist's ports)."""
    if SOURCE in STRM:
        return strm_src.build(point, netlist)       # it checks its own ports
    if SOURCE in ("forge", "char"):
        tb = src().build(point, netlist, bundle)
    elif SOURCE in ("bambu", "xls"):
        tb = src().build(point, netlist)
    else:
        tb = hls.build(point)
    src().check(tb)
    return tb


def do_point(point: str, tech: str, runs: list, threads: int) -> list[tuple[dict, dict]]:
    """One worker: the DC run (and bundle) unpacked, tb.json, compile, every requested run, cleanup, then the
    point's folder packed into its zip. Returns [(row, info)]."""
    with contextlib.ExitStack() as stack:
        rows = _do_point(stack, point, tech, runs, threads)
    return rows


def _do_point(stack: contextlib.ExitStack, point: str, tech: str, runs: list, threads: int) -> list[tuple[dict, dict]]:
    pdir = tech_runs(tech) / gtag(point)
    out = []
    try:
        rams = syn.rams_of(point) if SOURCE in HLS_TOOLS else []
        ram = None
        if rams and SOURCE == "hls" and syn_zip(tech, point).is_file():     # a macro or flops, from DC's plan
            tj = json.loads(arc.read(syn_zip(tech, point), "tech.json"))
            if tj.get("resolved", {}).get("ram"):
                rams = []
        if rams:
            row = {c: "" for c in COLUMNS}
            row.update({"point": point, "top": syn.top_of(point), "tech": tech, "clock_ns": _num(CLOCK_NS),
                        "clk_gate": gate(), "size": "",
                        "seed": "", "status": f"skipped: needs a RAM macro ({', '.join(rams)}); "
                                              f"{tech} has no RAM cells, ram/ram.py builds one"})
            return [(row, {})]
        try:
            syn_d, netlist, bundle = point_inputs(stack, tech, point)
            ram = ram_inputs(stack, syn_d)
            input_err = None
        except Fail as e:       # hls builds tb.json without the netlist: each run fails at compile, as before
            if SOURCE != "hls":
                raise
            syn_d = netlist = bundle = None
            input_err = str(e)
        tb = build_tb(point, netlist, bundle)
    except (ValueError, KeyError, FileNotFoundError, Fail) as e:
        # keyed as the runs would be (write_results: point, clk_gate, size, seed): the invocation's size and
        # seed where every run names the same one ('' otherwise, and for the default or 'all' size)
        sizes = {z for z, _, _ in runs}
        seeds = {"forge" if stim == "forge" else seed for _, stim, seed in runs}
        size = next(iter(sizes)) if len(sizes) == 1 else ""
        row = {c: "" for c in COLUMNS}
        row.update({"point": point, "tech": tech, "clock_ns": _num(CLOCK_NS), "clk_gate": gate(),
                    "size": "" if size in (None, "all") else size,
                    "seed": next(iter(seeds)) if len(seeds) == 1 else "", "status": f"failed: tb.json: {e}"})
        return [(row, {})]
    pdir.mkdir(parents=True, exist_ok=True)     # the point's other runs stay in its zip (pack_point merges)
    for stale in ("work", "logs"):
        shutil.rmtree(pdir / stale, ignore_errors=True)
    tb_text = json.dumps(tb, indent=1) + "\n"
    (pdir / "tb.json").write_text(tb_text)
    t_point = time.time()
    try:
        compile_times = {}
        t = time.time()
        try:
            if input_err:
                raise Fail(input_err)
            compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells", ram)     # the cells: one per technology
            compile_err = None
        except Fail as e:
            compile_err = str(e)
        compile_times["compile"] = time.time() - t
        expanded = []
        for size, stim, seed in runs:     # --size all: every size in the point's sizes.txt
            if size == "all" and SOURCE not in HLS_TOOLS:
                sizes = list(tb["sizes"])
            else:
                sizes = src().sizes_txt(point) if size == "all" else [size or src().default_size(tb)]
            expanded += [(z, stim, seed) for z in sizes]
        for size, stim, seed in expanded:
            times = dict(compile_times) if not out else {}
            base = {c: "" for c in columns()}
            base.update({"point": point, "top": tb["top"], "tech": tech, "clock_ns": _num(CLOCK_NS), "clk_gate": gate(),
                         "W": tb["W"],
                         "size": size, "seed": "forge" if stim == "forge" else seed})
            if SOURCE == "forge":
                base.update({"recipe": tb["recipe"], "snax_forge_commit": tb["snax_forge_commit"]})
            info = {"run": str((pdir / run_tag(size, stim, seed)).relative_to(ROOT)), "times": times,
                    "default": (stim, seed, size) == ("rand64", 0, src().default_size(tb)) and INITREG_SEED is None,
                    "zip": point_zip(pdir), "prefix": f"{run_tag(size, stim, seed)}/"}
            try:
                if size not in tb["sizes"]:
                    raise Fail(f"size {size} not in tb.json ({', '.join(tb['sizes'])})")
                if compile_err:
                    raise Fail(compile_err)
                info.update(run_one(tb, tech, pdir, size, stim, seed, threads, times, base, syn_d, ram))
            except Fail as e:
                base["status"] = f"failed: {e}"
            except Exception as e:          # noqa: BLE001  a crash fails this run, not the batch
                base["status"] = f"failed: {type(e).__name__}: {e}"
            info["row"] = base
            out.append((base, info))
    finally:
        shutil.rmtree(pdir / "work", ignore_errors=True)        # no compiled design is kept
        for f in pdir.rglob("vsim.wlf"):
            f.unlink()
        for f in pdir.rglob("*.vcd"):
            f.unlink()
        pack_point(pdir)                                         # tb.json, SAIFs, PT reports; the rest goes
    for _, info in out:
        info.setdefault("times", {})["point_total"] = time.time() - t_point
    return out


# ---------------------------------------------------------------- results
def _merge(path: Path, columns: list[str], key, rows: list[dict], drop: set) -> None:
    table = []
    if path.is_file():
        with path.open(newline="") as fh:
            table = [r for r in csv.DictReader(fh) if key(r) not in drop]
    table += [{c: _num(r.get(c, "")) for c in columns} for r in rows]
    table.sort(key=lambda r: (r["point"], syn.gate_flag(r), r.get("size", ""), str(r.get("seed", "")),
                              r.get("path", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)


def write_results(tech: str, results: list[tuple[dict, dict]]) -> None:
    out = RESULTS / tech
    key = lambda r: (r["point"], syn.gate_flag(r), r["size"], str(r["seed"]))  # gated rows apart  # noqa: E731
    rows = [r for r, _ in results]
    # a point that ran replaces its parked row (size and seed empty: 'skipped: needs a RAM macro')
    ran = {(r["point"], syn.gate_flag(r)) for r in rows if r.get("size")}
    _merge(out / "power_pt.csv", columns(), key, rows, {key(r) for r in rows} | {(p, g, "", "") for p, g in ran})
    mods, mod_keys = [], set()
    reports: dict[str, dict] = {}       # point -> the members of results/<source>/<tech>/power_reports/<point>.zip

    def members(point: str) -> dict:
        if point not in reports:
            reports[point] = arc.read_all(power_zip(tech, point))
        return reports[point]
    for r, info in results:
        if info.get("default"):
            have = members(r["point"])
            for k in [k for k in have if "/" not in k]:     # the default run's reports and tb.json, at the top
                del have[k]
        elif r["size"] not in MODULE_SIZES or str(r["seed"]) != "0" or INITREG_SEED is not None:
            continue
        mod_keys.add((r["point"], gate(), r["size"]))   # the modules of this point and size are replaced
        if r["status"] != "ok":
            continue
        for mod in info.get("modules", []):
            mods.append({"point": r["point"], "tech": tech, "clk_gate": gate(), "size": r["size"], "path": mod["path"],
                         "design": mod["design"], "e_dyn_pj": mod["dyn_uw"] * CLOCK_NS / 1000.0})
    _merge(out / "power_pt_modules.csv", MODULE_COLUMNS, lambda r: (r["point"], syn.gate_flag(r), r["size"]), mods,
           mod_keys)
    for r, info in results:
        if r["status"] != "ok":
            continue
        m = members(r["point"])
        sub = ""
        if not info.get("default"):       # another run: in <run tag>/ inside the point's zip
            sub = info["prefix"]
            for k in [k for k in m if k.startswith(sub)]:
                del m[k]
        for f in KEPT:
            m[sub + f] = arc.read(info["zip"], f"{info['prefix']}pt/{f}")
        m["tb.json"] = arc.read(info["zip"], "tb.json")
    for point, m in reports.items():
        z = power_zip(tech, point)
        if m:
            arc.write(z, m)
        elif z.exists():
            z.unlink()


def power_zip(tech: str, point: str) -> Path:
    """The committed PT reports of a point: results/<source>/<tech>/power_reports/<point>[_cg].zip."""
    return RESULTS / tech / "power_reports" / f"{gtag(point)}.zip"


# ---------------------------------------------------------------- char: a block alone, per window
CHAR_COLUMNS = ["point", "datapath", "lanes", "depth", "op", "form", "in_type", "out_type", "tech", "clock_ns", "clk_gate", "window", "cycles", "fires",
                "seed", "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "e_bit_pj", "status",
                "snax_forge_commit"]
CHAR_KEPT = ("power.rpt", "switching_activity.rpt")


def tb_top_char(tb: dict, netlist: Path) -> str:
    """The char top: the kind's sequencer on the block's data, pins and outputs; a pin of no bits is absent from
    the netlist and left open on the sequencer. Each data port has a 64-bit slot of the sequencer's data and out: a
    port of fewer bits takes its slot's low bits, and an output's slot is zero above them. A FifoSlicer's out_bits
    reach their slots through out_valid (0 when it holds no word: its data register has no reset, X until the
    first take). A SimdLanes' scalar pins (tb.json's scalars) take the low bits of their 64-bit slots of the
    sequencer's scal (NK slots; NK and scal only where there are scalars)."""
    kind, ni, no = tb["kind"], len(tb["data_in"]), len(tb["outs"])
    pins, scalars = tb["pins"], tb.get("scalars", {})
    params = {"T_NS": CLOCK_NS, "NI": ni, "NO": no, **({"NK": len(scalars)} if scalars else {})}
    wires = []
    if kind == "fold":
        wires = [("fire", 1), ("first", 1)]
    elif kind == "bank":
        rw = pins["row"]["bits"]
        params.update({"R": tb["rows"], "RW": rw})
        wires = [("fire", 1), ("first", 1), ("row", rw), ("drain", rw)]
    elif kind == "serial":
        lw = max(1, pins.get("lane", {}).get("bits", 0))
        params.update({"W": tb["W"], "LW": lw})
        wires = [("read", 1), ("lane", lw), ("first", 1)]
    elif kind == "link":
        sw = max(1, pins.get("wslot", {}).get("bits", 0))
        params.update({"D": tb["depth"], "SW": sw})
        wires = [("load", 1), ("wslot", sw), ("rslot", sw)]
    elif kind == "halo":
        params["H"] = tb["held"]
        wires = [("load", 1)]
    elif kind == "pack":
        wires = [("in_valid", 1), ("out_ready", 1), ("clear", 1), ("last", 1)]
    elif kind == "slice":
        params["R"] = tb["r"]
        wires = [("in_valid", 1), ("out_ready", 1), ("enable", 1), ("clear", 1)]
    gated = {}                  # a slicer's out_bits slot: through out_valid
    if kind == "slice":
        kv = next(i for i, d in enumerate(tb["outs"]) if d["port"] == "io_out_valid")
        gated = {i: kv for i, d in enumerate(tb["outs"]) if d["port"].startswith("io_out_bits")}
    L = ["// Generated by sim/pwr.py from tb.json (source char): do not edit.", "`timescale 1ns/1ps", "",
         f"module {TB_TOP};", f"    wire {tb['clock']['port']}, {tb['reset']['port']};", f"    wire [{64 * ni - 1}:0] data;",
         f"    wire [{64 * no - 1}:0] out;"]
    L += [f"    wire {'' if b == 1 else '[%d:0] ' % (b - 1)}p_{n};" for n, b in wires]
    L += [f"    wire [{64 * len(scalars) - 1}:0] kv;"] if scalars else []
    conn = [f".clk({tb['clock']['port']})", f".rst({tb['reset']['port']})", ".data(data)", ".out(out)"] + [f".{n}(p_{n})" for n, _ in wires]
    conn += [".scal(kv)"] if scalars else []
    L += ["", f"    char_{kind}_seq #({', '.join(f'.{k}({v})' for k, v in params.items())}) seq ({', '.join(conn)});", ""]
    ports = [tb["clock"]["port"], tb["reset"]["port"]]
    sel = lambda i, b: f"[{64 * i + b - 1}:{64 * i}]" if b > 1 else f"[{64 * i}]"  # noqa: E731
    ports += [f"{d['port']}(data{sel(i, d['bits'])})" for i, d in enumerate(tb["data_in"])]
    ports += [f"{d['port']}(" + (f"ob_{i}" if i in gated else f"out{sel(i, d['bits'])}") + ")"
              for i, d in enumerate(tb["outs"])]
    L += [f"    wire [{tb['outs'][i]['bits'] - 1}:0] ob_{i};" for i in gated]
    L += [f"    assign out{sel(i, tb['outs'][i]['bits'])} = out[{64 * kv}] ? ob_{i} : '0;" for i, kv in gated.items()]
    L += [f"    assign out[{64 * i + 63}:{64 * i + d['bits']}] = '0;" for i, d in enumerate(tb["outs"]) if d["bits"] < 64]
    for n, p in pins.items():
        sel = "" if p["bits"] == 1 else f"[{p['bits'] - 1}:0]"
        ports.append(f"{p['port']}(p_{n}{sel})")
    for i, p in enumerate(scalars.values()):
        ports.append(f"{p['port']}(kv{'[%d]' % (64 * i) if p['bits'] == 1 else '[%d:%d]' % (64 * i + p['bits'] - 1, 64 * i)})")
    ports = [p if "(" in p else f"{p}({p})" for p in ports]
    L += [f"    {tb['top']} {DUT} ("] + [f"        .{p}{',' if i < len(ports) - 1 else ''}" for i, p in enumerate(ports)]
    L += ["    );", ""] + dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def char_seq_cells(tech: str, point: str) -> int | None:
    f = RESULTS / tech / "char_synth.csv"
    with f.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["point"] == point and float(r["clock_ns"]) == CLOCK_NS and syn.gate_flag(r) == gate():
                return int(r["seq_cells"] or 0)
    return None


THRESHOLD_K_STREAM = 1     # threshold_k's generator: default_rng([seed, THRESHOLD_K_STREAM])


def threshold_k(tb: dict, seed: int) -> dict:
    """A SimdLanes threshold's held k (X117), {window: {"k": bits at opType}}: per window in tb.json's order one value
    uniform over a's range above its least value (1 to 255 for uint8), so a lane's output is hi for some a and 0 for
    others, as a workload's threshold is; from its own generator (seeded [seed, THRESHOLD_K_STREAM], not after the
    data), so the point's W = 1 and W = 8 hold the same k."""
    ta, bits = tb["params"]["inTypes"][0], tb["scalars"]["k"]["bits"]
    w = int(ta.removeprefix("u").removeprefix("int"))
    lo, hi = (0, (1 << w) - 1) if ta.startswith("u") else (-(1 << (w - 1)), (1 << (w - 1)) - 1)
    rng = np.random.default_rng([seed, THRESHOLD_K_STREAM])
    return {win["name"]: {"k": int(rng.integers(lo + 1, hi, endpoint=True)) & ((1 << bits) - 1)}
            for win in tb["windows"]}


def char_stimulus(tb: dict, slots: list[dict], seed: int) -> dict:
    """rand64: per data input port in tb.json order, one stream of full-range int64, as many values as the
    slots take new beats, each value the port's low bits; the expected outputs from sim/ref.py's char_ref. Every
    bit of every data input must take both values in the working window's beats (busy, or link's stream: it
    toggles there). For link's stream the
    reference is checked against the FIFO it is: the output at stream slot t is the beat loaded D slots before.

    A SimdLanes' scalar pins (tb.json's scalars), a CSR the program writes once and holds: drawn after the data
    streams from the same generator (the data as without them), per window in tb.json's order one full-range int64
    per pin, its low bits, applied at the window's lead-in slot and held through the window (0 while settling). They
    hold, so they are not in the toggle check; `ks` gives {window: {pin: value}}. A threshold's k from its CSR is
    threshold_k's instead (X117): inside a's range, from a generator of its own, so every lanes count holds the same."""
    n_new = sum(1 for s in slots if s["new"])
    rng = np.random.default_rng(seed)
    info = np.iinfo(np.int64)
    streams = [rng.integers(info.min, info.max, size=n_new, dtype=np.int64, endpoint=True) for _ in tb["data_in"]]
    masks = [(1 << d["bits"]) - 1 for d in tb["data_in"]]
    beats = [[int(x[b]) & m for x, m in zip(streams, masks)] for b in range(n_new)]
    scalars = tb.get("scalars", {})
    ks = {w["name"]: {n: int(rng.integers(info.min, info.max, dtype=np.int64, endpoint=True)) & ((1 << p["bits"]) - 1)
                      for n, p in scalars.items()} for w in tb["windows"]} if scalars else {}
    if scalars and tb["params"].get("op") == "threshold":
        ks = threshold_k(tb, seed)
    if scalars:     # each slot's pins with the scalars it sees: a window's from its lead-in slot on
        held, ref_slots = {n: 0 for n in scalars}, []
        for i, s in enumerate(slots):
            nxt = slots[i + 1]["window"] if i + 1 < len(slots) else None
            if s["window"] is None and nxt is not None:
                held = ks[nxt]
            ref_slots.append({**s, "pins": {**s["pins"], **held}})
    else:
        ref_slots = slots
    busy, b = [], 0
    for s in slots:
        if s["new"]:
            if s["window"] in ("busy", "stream"):
                busy.append(b)
            b += 1
    untoggled = {}
    for i, d in enumerate(tb["data_in"]):
        v = np.array([beats[j][i] for j in busy], dtype=np.uint64)
        ones, zeros = np.bitwise_or.reduce(v), np.bitwise_or.reduce(~v)
        k = d["bits"] - bin(int(ones & zeros & np.uint64(masks[i]))).count("1")
        if k:
            untoggled[d["port"]] = k
    if untoggled:
        raise Fail(f"stimulus: data bits that never toggle in the working window: {untoggled}")
    exps = char_ref(tb["datapath"], tb["params"], ref_slots, beats)
    if tb["kind"] == "link":
        loaded = []
        for k, s in enumerate(slots):
            if s["new"]:
                loaded.append(k)
        bad = [k for k, s in enumerate(slots) if s["window"] == "stream"
               and exps[k] != beats[loaded.index(k) - tb["depth"]]]
        if bad:
            raise Fail(f"reference: stream slots {bad[:5]} do not give the beat loaded D = {tb['depth']} before")
    return {"beats": beats, "exps": exps, "n_new": n_new, "busy_beats": len(busy), "ks": ks}


def vcd_windows(vcd: Path, wins: list[tuple[str, int, int]], out: dict, timescale_10ps: bool = False,
                done=None) -> None:
    """Cut the run's VCD into one VCD per window, in one pass: the header, then at the window's start t0 a
    $dumpvars block with every variable's value there, then the window's own events up to t1 (VCD time units).
    vcd2saif -time t0 t1 on the shared VCD counts one toggle in the window for a net whose last change before t0 was
    a zero-width pulse (two or more changes in one time step that end where they began, which the zero-delay sim
    makes); the cut file has no event before t0, so a window is counted from its own events only (docs/power.md,
    Char). The values are written at the time of the last time step before t0, as plain value changes, and each cut
    ends with a bare time step at t1 (vcd2saif ends a file's window at its last time step), so the window is whole. The boundaries are quiet: an event at a
    boundary fails the point. `out` maps a window to its file.

    timescale_10ps (cluster pwr): the VCD's $timescale must be 1ps (on one line or three) and each cut's
    is written as 10ps, the time numbers unchanged, so a run at tb_bin's 1 ns clock reads as one at 10 ns. `done`,
    when given, is called with a window's name as soon as its cut is closed (it may block, holding the pass)."""
    wins = sorted(wins, key=lambda w: w[1])
    bounds = {a for _, a, _ in wins} | {b for _, _, b in wins}
    state: dict = {}
    header: list[str] = []
    idx, fh, prev = 0, None, 0
    with vcd.open() as src:
        for line in src:
            header.append(line)
            if line.startswith("$enddefinitions"):
                break
        if timescale_10ps:      # NB (X76): tb_bin runs at 1 ns; read as 10 ns, a zero-delay run's activity unchanged
            text = "".join(header)
            m = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end[^\n]*\n?", text)
            if not m or (m.group(1), m.group(2)) != ("1", "ps"):
                raise Fail(f"vcd: timescale {m.group(1) + m.group(2) if m else None} is not 1ps")
            header = (text[:m.start()] + "$timescale 10ps $end\n" + text[m.end():]).splitlines(keepends=True)

        def open_win():
            nonlocal fh
            name, a, _ = wins[idx]
            fh = Path(out[name]).open("w")
            fh.writelines(header)
            fh.write(f"#{prev}\n")         # plain value changes: vcd2saif starts a $dumpvars block's window late
            fh.writelines(state.values())

        def advance(t: int):
            nonlocal idx, fh
            while idx < len(wins):
                if fh is None and t > wins[idx][1]:
                    open_win()
                elif fh is not None and t > wins[idx][2]:
                    fh.write(f"#{wins[idx][2]}\n")      # the window's end: vcd2saif ends a file at its last time step
                    fh.close()
                    fh = None
                    idx += 1
                    if done is not None:
                        done(wins[idx - 1][0])
                else:
                    return

        t = None
        for line in src:
            c = line[:1]
            if c == "#":
                t = int(line[1:])
                if t in bounds:
                    raise Fail(f"vcd: an event at the window boundary {t}")
                advance(t)
                prev = t
                if fh is not None:
                    fh.write(line)
            elif c == "$" or not line.strip():
                continue            # $dumpvars, $dumpon, $dumpoff, $end, $comment: their values are value lines
            else:
                code = line.split()[1] if c in "bBrR" else line[1:].strip()
                state[code] = line if line.endswith("\n") else line + "\n"
                if fh is not None:
                    fh.write(state[code])
        advance(1 << 62)
    if fh is not None:
        fh.close()
    if idx != len(wins):
        raise Fail(f"vcd: the VCD ends inside window {wins[idx][0]}")


def _pack(values: list[int]) -> str:
    v = 0
    for i, x in enumerate(values):
        v |= (x & MASK64) << (64 * i)
    return f"{v:0{16 * len(values)}x}\n"


def do_point_char(point: str, tech: str, seed: int, threads: int) -> list[tuple[dict, dict]]:
    """One worker: the DC run and the block unpacked, tb.json, compile, one simulation over every window, then per
    window vcd2saif, the SAIF check and PT; cleanup, and the point's folder packed into its zip. Returns
    [(row, info)], one per window."""
    with contextlib.ExitStack() as stack:
        rows = _do_point_char(stack, point, tech, seed, threads)
    return rows


def _do_point_char(stack: contextlib.ExitStack, point: str, tech: str, seed: int, threads: int) -> list[tuple[dict, dict]]:
    t_point = time.time()
    extra = syn.char_extra(point)
    base = {c: "" for c in CHAR_COLUMNS}
    base.update({"point": point, "tech": tech, "clock_ns": _num(CLOCK_NS), "clk_gate": gate(), "seed": seed,
                 **{k: extra[k] for k in ("datapath", "lanes", "depth", "op", "form", "in_type", "out_type",
                                          "snax_forge_commit")}})
    try:
        syn_d, netlist, bundle = point_inputs(stack, tech, point)
        tb = build_tb(point, netlist, bundle)
    except (ValueError, KeyError, FileNotFoundError, Fail) as e:
        return [({**base, "window": "", "status": f"failed: tb.json: {e}"}, {})]
    rows = {w["name"]: {**base, "window": w["name"]} for w in tb["windows"]}
    infos = {w: {} for w in rows}
    pdir = tech_runs(tech) / gtag(point)
    rdir = pdir / f"s{seed}"
    for stale in ("work", "logs", rdir.name):
        shutil.rmtree(pdir / stale, ignore_errors=True)
    (rdir / "stim").mkdir(parents=True)
    (pdir / "tb.json").write_text(json.dumps(tb, indent=1) + "\n")
    times: dict = {}
    vcd = rdir / "dut.vcd"
    sim: dict = {"run": str(rdir.relative_to(ROOT)), "times": times}
    try:
        t = time.time()
        compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells")
        times["compile"] = time.time() - t
        t = time.time()
        slots = char_src.schedule(tb)
        st = char_stimulus(tb, slots, seed)
        (rdir / "stim" / "data.hex").write_text("".join(_pack(b) for b in st["beats"]))
        (rdir / "stim" / "exp.hex").write_text("".join(_pack(e) for e in st["exps"]))
        sim.update({"slots": len(slots), "beats": st["n_new"], "busy_beats": st["busy_beats"],
                    "samples": len(st["exps"])})
        k_args = []
        if st["ks"]:            # one line a window, in the windows' order (sim/tb/char_lanes_seq.sv)
            (rdir / "stim" / "k.hex").write_text("".join(_pack(list(v.values())) for v in st["ks"].values()))
            k_args = [f"+K_HEX={rdir / 'stim' / 'k.hex'}", f"+K_N={len(st['ks'])}"]
            sim["scalars"] = st["ks"]
            tb["scalar_values"] = {"seed": seed, "windows": st["ks"]}      # kept: tb.json goes to power_reports
            (pdir / "tb.json").write_text(json.dumps(tb, indent=1) + "\n")
            print(f"{point}: scalars per window " + "; ".join(
                f"{w} " + ", ".join(f"{n} 0x{x:x}" for n, x in v.items()) for w, v in st["ks"].items()), flush=True)
        times["stim"] = time.time() - t
        t = time.time()
        cmd = [tool("vsim"), "-c", "-work", str(pdir / "work"), "tb_opt", "+nospecify", "+notimingchecks",
               "-wlf", str(rdir / "vsim.wlf"), f"+VCD={vcd}", f"+DATA_HEX={rdir / 'stim' / 'data.hex'}",
               f"+DATA_N={st['n_new']}", f"+EXP_HEX={rdir / 'stim' / 'exp.hex'}", f"+EXP_N={len(st['exps'])}",
               *k_args, "-do", str(RUN_DO)]
        run_tool(cmd, rdir / "vsim.log", rdir)
        times["vsim"] = time.time() - t
        log = (rdir / "vsim.log").read_text(errors="replace")
        summ = re.search(r"TB: samples (\d+) of (\d+) mismatches (\d+) xz (\d+) beats (\d+) of (\d+)", log)
        wins = re.findall(r"TB: window (\S+) t0_ns ([\d.]+) t1_ns ([\d.]+) cycles (\d+) fires (\d+)", log)
        changes = dict(re.findall(r"TB: changes (\S+) (\d+)", log))
        if not summ:
            raise Fail("sim: no result (vsim.log)")
        k, n, mism, xz, bi, nb = (int(x) for x in summ.groups())
        sim.update({"compared": k, "mismatches": mism, "xz": xz, "changes": {w: int(c) for w, c in changes.items()}})
        if mism or xz or k != n or bi != nb:
            raise Fail(f"sim: {k} of {n} samples, {mism} mismatches, {xz} X/Z, {bi} of {nb} beats taken")
        got = [{"name": w, "cycles": int(c), "fires": int(f)} for w, _, _, c, f in wins]
        if got != tb["windows"]:
            raise Fail(f"sim: windows {got}, tb.json has {tb['windows']}")
        if "idle" in changes and int(changes["idle"]) != 0:
            raise Fail(f"sim: the outputs change {changes['idle']} times in idle")
        if any(w["name"] == "idle" for w in tb["windows"]) and "idle" not in changes:
            raise Fail("sim: no idle line in vsim.log")
        head = vcd.open().read(4096)
        m = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end", head)
        unit = int(m.group(1)) * syn.SECONDS[m.group(2).lower()]
        sim["vcd_bytes"] = vcd.stat().st_size
        t = time.time()
        cuts, spans = {}, []
        for w, t0, t1, c, f in wins:
            rows[w].update({"cycles": int(c), "fires": int(f)})
            infos[w]["window_ns"] = [float(t0), float(t1)]
            (rdir / w).mkdir()
            cuts[w] = rdir / w / f"{w}.vcd"
            spans.append((w, *(round(float(x) * 1e-9 / unit) for x in (t0, t1))))
        vcd_windows(vcd, spans, cuts)
        times["vcd_cut"] = time.time() - t
        vcd.unlink()                     # the shared VCD is gone once cut
        t = time.time()
        for w, a, b in spans:
            try:
                rc = run_tool([tool("vcd2saif"), "-input", str(cuts[w]), "-output", str(rdir / w / f"{w}.saif"),
                               "-instance", f"{TB_TOP}/{DUT}", "-time", str(a), str(b)], rdir / w / "vcd2saif.log",
                              rdir / w)
            finally:
                cuts[w].unlink(missing_ok=True)      # and each window's cut at once
            if rc or not (rdir / w / f"{w}.saif").is_file():
                raise Fail(f"vcd2saif {w} ({w}/vcd2saif.log)")
        times["vcd2saif"] = time.time() - t
    except Fail as e:
        for r in rows.values():
            r["status"] = f"failed: {e}"
    except Exception as e:  # noqa: BLE001  a crash fails this point, not the batch
        for r in rows.values():
            r["status"] = f"failed: {type(e).__name__}: {e}"
    finally:
        vcd.unlink(missing_ok=True)      # no VCD is kept, whatever the result
        for f in rdir.rglob("*.vcd"):
            f.unlink()
        shutil.rmtree(pdir / "work", ignore_errors=True)
        for f in pdir.rglob("vsim.wlf"):
            f.unlink()
    flops = char_seq_cells(tech, point)
    for w, r in rows.items():
        if r["status"]:
            continue
        wdir, info = rdir / w, infos[w]
        try:
            t = time.time()
            info["saif"] = saif_check(wdir / f"{w}.saif", r["cycles"], tb["clock"]["port"])
            ptd = wdir / "pt"
            ptd.mkdir()
            env = {**os.environ, "PWR_RUN": str(syn_d), "PWR_MODE": "saif",
                   "PWR_ACT": str(wdir / f"{w}.saif"), "PWR_STRIP": f"{TB_TOP}/{DUT}", "PWR_OUT": str(ptd),
                   "PWR_THREADS": str(threads)}
            rc = run_tool([tool("pt_shell", "PT_SHELL"), "-no_init", "-f", str(PT_SCRIPT), "-output_log_file",
                           str(ptd / "pt_shell.log")], ptd / "pt_stdout.log", ptd, env, stdin_null=True)
            info["pt_s"] = time.time() - t
            if rc or not (ptd / "power.rpt").is_file():
                raise Fail(f"pt {w} ({w}/pt/pt_shell.log)")
            ann, total = coverage(ptd / "switching_activity.rpt")
            info["annotated"] = [ann, total]
            if ann < MIN_ANNOTATED / 100 * total:
                raise Fail(f"pt {w}: {ann} of {total} nets annotated, under {MIN_ANNOTATED:g}%")
            info["wire_load"] = wire_load_check(ptd / "wire_load.rpt")
            groups = pt_groups(ptd)
            e = {syn.POWER_GROUPS[g]: (i + s) * CLOCK_NS / 1000.0 for g, (i, s, _) in groups.items()}
            e_flop = e["clk"] + e["reg"] + e["seq"]
            r.update({"e_clk_pj": e["clk"], "e_reg_pj": e["reg"], "e_seq_pj": e["seq"], "e_comb_pj": e["comb"],
                      "e_flop_pj": e_flop, "e_dyn_pj": e_flop + e["comb"],
                      "e_bit_pj": e_flop / flops if flops else "", "status": "ok"})
        except Fail as ex:
            r["status"] = f"failed: {ex}"
        except Exception as ex:  # noqa: BLE001
            r["status"] = f"failed: {type(ex).__name__}: {ex}"
    sim["times"]["point_total"] = time.time() - t_point
    out = []
    for w, r in rows.items():
        out.append((r, {**infos[w], "sim": sim, "row": r, "run": str((rdir / w).relative_to(ROOT)),
                        "zip": point_zip(pdir), "prefix": f"{rdir.name}/{w}/"}))
    pack_point(pdir)                     # tb.json, each window's SAIF and PT reports; the rest goes
    return out


def write_results_char(tech: str, results: list[tuple[dict, dict]]) -> None:
    """char_power.csv (merged on point, window and seed, in each kind's window order), and per ok window its
    reports in power_reports/<point>.zip as <window>/..., the point's tb.json once at its top."""
    out = RESULTS / tech
    key = lambda r: (r["point"], syn.gate_flag(r), r["window"], str(r["seed"]))  # gated rows apart  # noqa: E731
    rows = [r for r, _ in results]
    done = {key(r) for r in rows}
    table = []
    f = out / "char_power.csv"
    if f.is_file():
        with f.open(newline="") as fh:
            table = [r for r in csv.DictReader(fh) if key(r) not in done and
                     (r["point"], syn.gate_flag(r), "", r["seed"]) not in
                     {(x["point"], syn.gate_flag(x), "", str(x["seed"])) for x in rows if not x["window"]}]
    table += [{c: _num(r.get(c, "")) for c in CHAR_COLUMNS} for r in rows]
    order = {w: i for ws in char_src.WINDOWS.values() for i, w in enumerate(ws)}
    table.sort(key=lambda r: (r["point"], syn.gate_flag(r), str(r["seed"]), order.get(r["window"], -1)))
    out.mkdir(parents=True, exist_ok=True)
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CHAR_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)
    reports: dict[str, dict] = {}       # point -> the members of power_reports/<point>.zip, a folder per window
    for r, info in results:
        if not r["window"]:
            continue
        if r["point"] not in reports:
            reports[r["point"]] = arc.read_all(power_zip(tech, r["point"]))
        m = reports[r["point"]]
        for k in [k for k in m if k.startswith(f"{r['window']}/")]:
            del m[k]
        if r["status"] != "ok":
            continue
        for name in CHAR_KEPT:
            m[f"{r['window']}/{name}"] = arc.read(info["zip"], f"{info['prefix']}pt/{name}")
        m["tb.json"] = arc.read(info["zip"], "tb.json")
    for point, m in reports.items():
        z = power_zip(tech, point)
        if m:
            arc.write(z, m)
        elif z.exists():
            z.unlink()


def run_char(points: list[str], tech: str, seed: int, j: int, threads: int) -> int:
    results = []

    def work(p):
        res = do_point_char(p, tech, seed, threads)
        for r, info in res:
            tt = info.get("sim", {}).get("times", {})
            print(f"{r['point']} {r['window']}: {r['status']}  cycles {r.get('cycles', '')}  "
                  f"e_dyn {_num(r['e_dyn_pj']) if r.get('e_dyn_pj') != '' else '-'} pJ  "
                  f"({', '.join(f'{k} {v:.1f}' for k, v in tt.items())} s)", flush=True)
        return res
    t = time.time()
    with ThreadPoolExecutor(max_workers=j) as ex:
        for res in ex.map(work, points):
            results += res
    print(f"pwr: batch {time.time() - t:.1f} s", flush=True)
    write_results_char(tech, results)
    bad = [r for r, _ in results if r["status"] != "ok"]
    print(f"pwr: {len(results) - len(bad)} ok, {len(bad)} not ok -> "
          f"{(RESULTS / tech / 'char_power.csv').relative_to(ROOT)}")
    return 1 if bad else 0



# ---------------------------------------------------------------- streamer and xbar: one busy window
STRM_COLUMNS = {
    "streamer": ["point", "depth", "loops", "channels", "tech", "clock_ns", "clk_gate", "seed", "bounds", "cycles", "fill",
                 "stalls", "beats", "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj",
                 "e_window_pj", "e_beat_pj", "p_dyn_uw", "annotated", "status", "snax_cluster_commit"],
    "xbar": ["point", "inputs", "banks", "tech", "clock_ns", "clk_gate", "seed", "cycles", "grants", "e_clk_pj", "e_reg_pj",
             "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "e_window_pj", "e_access_pj", "p_dyn_uw",
             "annotated", "status", "snax_cluster_commit"]}
STRM_COLUMNS["xbar_mix"] = STRM_COLUMNS["xbar"][:3] + ["ro", "wo"] + STRM_COLUMNS["xbar"][3:]
STRM_KEPT = ("power.rpt", "power_hierarchy.rpt", "switching_activity.rpt")
READER_RE = re.compile(r"TB: beats (\d+) expected (\d+) fill (-?\d+) stalls (\d+) data_mismatches (\d+) "
                       r"addr_mismatches (\d+) xz (\d+)")
XBAR_RE = re.compile(r"TB: grants (\d+) expected (\d+) grant_cycles_bad (\d+) bank_mismatches (\d+) "
                     r"rsp_mismatches (\d+) xz (\d+)")


def strm_points(points: list[str]) -> tuple[list[str], list[str]]:
    """(points to run, xbar points left out because inputs > banks: no conflict-free stimulus)."""
    if SOURCE not in XBARS:
        return points, []
    keep, out = [], []
    for p in points:
        prm = syn.forge_json(p, "config.json").get("params", {})
        (keep if prm.get("inputs", 0) <= prm.get("banks", 0) else out).append(p)
    return keep, out


def do_point_strm(point: str, tech: str, seed: int, threads: int) -> tuple[dict, dict]:
    """One worker: the DC run unpacked, tb.json and the generated TB, compile, vsim, the window cut out of the VCD
    (vcd_windows) and vcd2saif on it, both VCDs deleted at once, the SAIF check, PT; the point's
    folder packed into its zip. Returns (row, info)."""
    with contextlib.ExitStack() as stack:
        return _do_point_strm(stack, point, tech, seed, threads)


def _do_point_strm(stack: contextlib.ExitStack, point: str, tech: str, seed: int, threads: int) -> tuple[dict, dict]:
    t_point = time.time()
    cfg = syn.forge_json(point, "config.json")
    row = {c: "" for c in STRM_COLUMNS[SOURCE]}
    row.update({"point": point, "tech": tech, "clock_ns": _num(CLOCK_NS), "clk_gate": gate(), "seed": seed,
                "snax_cluster_commit": cfg.get("snax_cluster_commit", ""),
                **{k: cfg.get("params", {}).get(v, "") for k, v in syn.STRM_PARAMS[SOURCE].items()}})
    times: dict = {}
    info: dict = {"times": times}
    pdir = tech_runs(tech) / gtag(point)
    rdir = pdir / f"s{seed}"
    shutil.rmtree(pdir, ignore_errors=True)
    try:
        syn_d, netlist, _ = point_inputs(stack, tech, point)
        tb = strm_src.build(point, netlist, seed)
    except (ValueError, KeyError, FileNotFoundError, Fail) as e:
        row["status"] = f"failed: tb.json: {e}"
        return row, info
    if SOURCE == "streamer":
        row["bounds"] = "x".join(map(str, tb["bounds"]))
    rdir.mkdir(parents=True)
    (pdir / "tb.json").write_text(json.dumps(tb, indent=1) + "\n")
    vcd, cut, saif = rdir / "dut.vcd", rdir / "busy.vcd", rdir / "busy.saif"
    soft = ""
    try:
        t = time.time()
        compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells")
        times["compile"] = time.time() - t
        t = time.time()
        run_tool([tool("vsim"), "-c", "-work", str(pdir / "work"), "tb_opt", "+nospecify", "+notimingchecks",
                  "-sv_seed", str(seed), "-wlf", str(rdir / "vsim.wlf"), f"+VCD={vcd}", "-do", str(RUN_DO)],
                 rdir / "vsim.log", rdir)
        times["vsim"] = time.time() - t
        log = (rdir / "vsim.log").read_text(errors="replace")
        info["tb"] = re.findall(r"TB: .*", log)
        win = re.search(r"TB: window busy t0_ns ([\d.]+) t1_ns ([\d.]+) cycles (\d+)", log)
        if "TB: FAIL: timeout" in log:
            raise Fail("sim: timeout")
        if not win:
            raise Fail("sim: no window (vsim.log)")
        cycles = int(win.group(3))
        row["cycles"] = cycles
        if SOURCE == "streamer":
            m = READER_RE.search(log)
            if not m:
                raise Fail("sim: no beats line (vsim.log)")
            beats, want, fill, stalls, dbad, abad, xz = map(int, m.groups())
            row.update({"beats": beats, "fill": fill, "stalls": stalls})
            if beats != want or dbad or abad or xz or cycles != fill + beats + stalls:
                raise Fail(f"sim: beats {beats} of {want}, {dbad} data and {abad} address mismatches, {xz} X/Z, "
                           f"cycles {cycles} = fill {fill} + beats + stalls {stalls}?")
            if stalls:
                soft = f"failed: {stalls} stalls after the fill (energy kept)"
            work = beats
        else:
            m = XBAR_RE.search(log)
            if not m:
                raise Fail("sim: no grants line (vsim.log)")
            grants, want, gbad, bbad, rbad, xz = map(int, m.groups())
            row["grants"] = grants
            if grants != want or gbad or bbad or rbad or xz or cycles != tb["window"]:
                raise Fail(f"sim: grants {grants} of {want}, {gbad} cycles short, {bbad} bank and {rbad} response "
                           f"mismatches, {xz} X/Z, cycles {cycles}")
            work = grants
        head = vcd.open().read(4096)
        tu = re.search(r"\$timescale\s+(\d+)\s*(\w+)\s+\$end", head)
        unit = int(tu.group(1)) * syn.SECONDS[tu.group(2).lower()]
        a, b = (round(float(x) * 1e-9 / unit) for x in win.groups()[:2])
        info.update({"window_ns": [float(win.group(1)), float(win.group(2))], "vcd_bytes": vcd.stat().st_size})
        t = time.time()
        vcd_windows(vcd, [("busy", a, b)], {"busy": cut})
        vcd.unlink()                      # the shared VCD is gone once cut
        rc = run_tool([tool("vcd2saif"), "-input", str(cut), "-output", str(saif), "-instance", f"{TB_TOP}/{DUT}",
                       "-time", str(a), str(b)], rdir / "vcd2saif.log", rdir)
        cut.unlink(missing_ok=True)
        times["vcd2saif"] = time.time() - t
        if rc or not saif.is_file():
            raise Fail("vcd2saif (vcd2saif.log)")
        info["saif"] = saif_check(saif, cycles, tb["clock"]["port"])
        t = time.time()
        ptd = rdir / "pt"
        ptd.mkdir()
        env = {**os.environ, "PWR_RUN": str(syn_d), "PWR_MODE": "saif", "PWR_ACT": str(saif),
               "PWR_STRIP": f"{TB_TOP}/{DUT}", "PWR_OUT": str(ptd), "PWR_THREADS": str(threads)}
        rc = run_tool([tool("pt_shell", "PT_SHELL"), "-no_init", "-f", str(PT_SCRIPT), "-output_log_file",
                       str(ptd / "pt_shell.log")], ptd / "pt_stdout.log", ptd, env, stdin_null=True)
        times["pt"] = time.time() - t
        if rc or not (ptd / "power.rpt").is_file():
            raise Fail("pt (pt/pt_shell.log)")
        ann, total = coverage(ptd / "switching_activity.rpt")
        row["annotated"] = f"{ann}/{total}"
        if ann < MIN_ANNOTATED / 100 * total:
            raise Fail(f"pt: {ann} of {total} nets annotated, under {MIN_ANNOTATED:g}%")
        info["wire_load"] = wire_load_check(ptd / "wire_load.rpt")
        e = {syn.POWER_GROUPS[g]: (i + s) * CLOCK_NS / 1000.0 for g, (i, s, _) in pt_groups(ptd).items()}
        e_flop = e["clk"] + e["reg"] + e["seq"]
        e_dyn = e_flop + e["comb"]
        row.update({"e_clk_pj": e["clk"], "e_reg_pj": e["reg"], "e_seq_pj": e["seq"], "e_comb_pj": e["comb"],
                    "e_flop_pj": e_flop, "e_dyn_pj": e_dyn, "e_window_pj": e_dyn * cycles,
                    "e_beat_pj" if SOURCE == "streamer" else "e_access_pj": e_dyn * cycles / work,
                    "p_dyn_uw": e_dyn / CLOCK_NS * 1000.0, "status": soft or "ok"})
    except Fail as e:
        row["status"] = f"failed: {e}"
    except Exception as e:  # noqa: BLE001  a crash fails this point, not the batch
        row["status"] = f"failed: {type(e).__name__}: {e}"
    finally:
        for f in (vcd, cut):
            f.unlink(missing_ok=True)     # no VCD is kept, whatever the result
        shutil.rmtree(pdir / "work", ignore_errors=True)
        for f in pdir.rglob("vsim.wlf"):
            f.unlink()
    times["point_total"] = time.time() - t_point
    info.update({"zip": point_zip(pdir), "prefix": f"{rdir.name}/"})
    pack_point(pdir)                      # tb.json, the SAIF and PT's reports; the rest goes
    return row, info


def write_results_strm(tech: str, results: list[tuple[dict, dict]]) -> None:
    """power_pt.csv (merged on point and seed) and per ok point its PT reports and tb.json in
    power_reports/<point>.zip."""
    out = RESULTS / tech
    key = lambda r: (r["point"], syn.gate_flag(r), str(r["seed"]))  # gated rows apart  # noqa: E731
    rows = [r for r, _ in results]
    _merge(out / "power_pt.csv", STRM_COLUMNS[SOURCE], key, rows, {key(r) for r in rows})
    for r, info in results:
        z = power_zip(tech, r["point"])
        if r["status"] != "ok" and not r.get("e_dyn_pj"):
            if z.exists():
                z.unlink()
            continue
        m = {f: arc.read(info["zip"], f"{info['prefix']}pt/{f}") for f in STRM_KEPT}
        m["tb.json"] = arc.read(info["zip"], "tb.json")
        arc.write(z, m)


def run_strm(points: list[str], tech: str, seed: int, j: int, threads: int) -> int:
    points, out = strm_points(points)
    if out:
        print(f"pwr: {len(out)} xbar points left out, inputs > banks: {', '.join(out)}", flush=True)
    points.sort(key=syn.strm_size, reverse=True)       # the largest first, as syn.py runs them
    results = []

    def work(p):
        r, info = do_point_strm(p, tech, seed, threads)
        tt = info.get("times", {})
        e = r.get("e_beat_pj", r.get("e_access_pj", ""))
        print(f"{p}: {r['status']}  cycles {r.get('cycles', '')}  e {_num(e) if e != '' else '-'} pJ  "
              f"({', '.join(f'{k} {v:.1f}' for k, v in tt.items())} s)", flush=True)
        return r, info
    t = time.time()
    with ThreadPoolExecutor(max_workers=j) as ex:
        results = list(ex.map(work, points))
    print(f"pwr: batch {time.time() - t:.1f} s", flush=True)
    write_results_strm(tech, results)
    bad = [r for r, _ in results if r["status"] != "ok"]
    print(f"pwr: {len(results) - len(bad)} ok, {len(bad)} not ok -> "
          f"{(RESULTS / tech / 'power_pt.csv').relative_to(ROOT)}")
    return 1 if bad else 0

# ---------------------------------------------------------------- commands
def cmd_tbjson(args) -> int:
    use_source(args.source)
    if args.source == "hls":
        tb = hls.build(args.point)
        hls.check(tb)
    else:       # forge, char, bambu, xls: from the netlist's ports (and the bundle), unpacked into tmp/
        with contextlib.ExitStack() as stack:
            _, netlist, bundle = point_inputs(stack, args.tech, args.point)
            tb = build_tb(args.point, netlist, bundle)
    print(json.dumps(tb, indent=1))
    return 0


def cmd_run(args) -> int:
    global INITREG_SEED, CLK_GATE
    INITREG_SEED = args.initreg_seed
    CLK_GATE = args.clk_gate          # the _cg netlists (syn.py --clk-gate), rows with clk_gate 1
    syn.use_clk_gate(CLK_GATE)
    if INITREG_SEED is not None and args.source in ("char", *STRM):
        sys.exit("--initreg-seed: not built for --source char (its windows run one simulation per point)")
    use_source(args.source)
    if args.source != "hls" and args.stim != "rand64":
        sys.exit(f"--source {args.source} runs rand64 only (--stim forge is hls-exercises' data.h)")
    points = syn.select(args.patterns)
    if not points:
        sys.exit(f"no point matches {args.patterns}")
    for t in ("vlib", "vlog", "vopt", "vsim", "vcd2saif"):
        tool(t)
    tool("pt_shell", "PT_SHELL")
    lic = licences()
    nproc = min(os.cpu_count() or 1, args.cores or os.cpu_count() or 1)      # --cores: the run's core budget
    j = min(lic["msimhdlsim"]["free"], lic["PrimePower"]["free"], lic["PrimeTime"]["free"], nproc)
    if args.j:
        j = min(j, args.j)
    if j < 1:
        sys.exit(f"no free licences: {lic}")
    threads = max(1, nproc // j)
    stamp = dt.datetime.now().isoformat(timespec="seconds")
    print(f"pwr: {len(points)} points on {args.tech}; free msimhdlsim {lic['msimhdlsim']['free']}, "
          f"PrimePower {lic['PrimePower']['free']}, PrimeTime {lic['PrimeTime']['free']}, nproc {nproc} "
          f"-> J = {j}, PT threads {threads}", flush=True)
    tech_runs(args.tech).mkdir(parents=True, exist_ok=True)
    with (tech_runs(args.tech) / "batches.jsonl").open("a") as fh:
        fh.write(json.dumps({"date": stamp, "source": args.source, "patterns": args.patterns, "stim": args.stim, "size": args.size,
                             "seed": args.seed, "initreg_seed": INITREG_SEED, "licences": lic, "nproc": nproc, "J": j, "threads": threads}) + "\n")
    t = time.time()
    cells_lib(args.tech)
    print(f"pwr: cell models compiled in {time.time() - t:.1f} s", flush=True)
    runs = [(args.size, args.stim, args.seed)]
    results = []

    if args.source == "char":
        return run_char(points, args.tech, args.seed, j, threads)
    if args.source in STRM:
        return run_strm(points, args.tech, args.seed, j, threads)

    def work(p):
        res = do_point(p, args.tech, runs, threads)
        for r, info in res:
            tt = info.get("times", {})
            print(f"{r['point']} {r['size']} {r['seed']}: {r['status']}  cycles {r.get('cycles', '')}  "
                  f"cycles_ports {r.get('cycles_ports', '')}  "
                  f"e_dyn {_num(r['e_dyn_pj']) if r.get('e_dyn_pj') != '' else '-'} pJ  "
                  f"({', '.join(f'{k} {v:.1f}' for k, v in tt.items())} s)", flush=True)
        return res
    t = time.time()
    with ThreadPoolExecutor(max_workers=j) as ex:
        for res in ex.map(work, points):
            results += res
    print(f"pwr: batch {time.time() - t:.1f} s", flush=True)
    bad = [r for r, _ in results if r["status"] != "ok"]
    if INITREG_SEED is not None:      # a check: nothing goes to results/
        print(f"pwr: {len(results) - len(bad)} ok, {len(bad)} not ok; random register start (seed {INITREG_SEED}), "
              f"a check: results/ not written; PT reports in the point zips' _r{INITREG_SEED} folders")
        return 1 if bad else 0
    write_results(args.tech, results)
    print(f"pwr: {len(results) - len(bad)} ok, {len(bad)} not ok -> {(RESULTS / args.tech / 'power_pt.csv').relative_to(ROOT)}")
    return 1 if any(r["status"].startswith("failed") for r in bad) else 0


def dc_groups(rpt: Path) -> dict:
    text = rpt.read_text()

    def unit(label):
        m = re.search(rf"{label}\s*=\s*([0-9.]+)\s*([munpf]?W)\b", text)
        return float(m.group(1)) * syn.TO_UW[m.group(2)]
    dyn, leak = unit("Dynamic Power Units"), unit("Leakage Power Units")
    out = {}
    for g in syn.POWER_GROUPS:
        m = re.search(rf"^{g}\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
        out[g] = (float(m.group(1)) * dyn, float(m.group(2)) * dyn, float(m.group(3)) * leak)
    return out


def cmd_setup_check(args) -> int:
    """PT and DC on the same netlist with the same forced activity, per power group: a diagnostic. It prints
    the differences (for the run note) and fails only on the wire-load check (PITFALLS PT1)."""
    use_source(args.source)
    point = args.point or SETUP_POINTS.get(args.source)
    if not point:
        sys.exit(f"setup-check: no default point for --source {args.source}; give --point")
    tech = args.tech
    base = tech_runs(tech) / "setup_check" / point
    shutil.rmtree(base, ignore_errors=True)
    with contextlib.ExitStack() as stack:     # the DC run unpacked for PT and DC; the folder packed after
        try:
            run, _, _ = point_inputs(stack, tech, point)
        except Fail as e:
            sys.exit(f"setup-check: {e}")
        (base / "pt").mkdir(parents=True)
        (base / "dc").mkdir(parents=True)
        try:
            return _setup_check(tech, point, base, run)
        finally:
            pack_point(base)


def _setup_check(tech: str, point: str, base: Path, run: Path) -> int:
    env = {**os.environ, "PWR_RUN": str(run), "PWR_MODE": "uniform", "PWR_OUT": str(base / "pt" / "reports")}
    t = time.time()
    rc = run_tool([tool("pt_shell", "PT_SHELL"), "-no_init", "-f", str(PT_SCRIPT), "-output_log_file",
                   str(base / "pt" / "pt_shell.log")], base / "pt" / "pt_stdout.log", base / "pt", env, True)
    t_pt = time.time() - t
    if rc or not (base / "pt" / "reports" / "power.rpt").is_file():
        sys.exit(f"setup-check: PT failed ({base / 'pt'})")
    t = time.time()
    rc = run_tool([os.environ.get("DC_SHELL") or tool("dc_shell"), "-f", str(DC_READBACK), "-output_log_file",
                   str(base / "dc" / "dc_shell.log")], base / "dc" / "dc_stdout.log", base / "dc",
                  {**env, "PWR_MODE": "uniform"}, True)
    t_dc = time.time() - t
    if rc or not (base / "dc" / "reports" / "power.rpt").is_file():
        sys.exit(f"setup-check: DC failed ({base / 'dc'})")
    try:
        wl = wire_load_check(base / "pt" / "reports" / "wire_load.rpt")
    except Fail as e:
        sys.exit(f"setup-check: {e} ({base / 'pt'})")
    pt, dc = pt_groups(base / "pt" / "reports"), dc_groups(base / "dc" / "reports" / "power.rpt")
    table = []
    print(f"setup-check {tech} {point}: uniform activity, PT against DC (PT {t_pt:.1f} s, DC {t_dc:.1f} s); "
          f"a diagnostic, PT is the reference; wire load: {wl['wire_cap_nets']} nets with wire capacitance, "
          f"{wl['wire_res_nets']} with resistance, of {wl['nets']}")
    print(f"{'group':<14} {'PT dyn uW':>12} {'DC dyn uW':>12} {'diff %':>8} {'PT leak uW':>12} {'DC leak uW':>12} {'diff %':>8}")
    for g in syn.POWER_GROUPS:
        pd, dd = pt[g][0] + pt[g][1], dc[g][0] + dc[g][1]
        pl, dl = pt[g][2], dc[g][2]

        def rel(a, b):
            return 0.0 if max(abs(a), abs(b)) < 1e-9 else (a - b) / b if b else float("inf")
        rd, rl = rel(pd, dd), rel(pl, dl)
        table.append({"group": g, "pt_dyn_uw": pd, "dc_dyn_uw": dd, "dyn_diff": rd, "pt_leak_uw": pl,
                      "dc_leak_uw": dl, "leak_diff": rl})
        print(f"{g:<14} {pd:12.6g} {dd:12.6g} {100 * rd:8.4f} {pl:12.6g} {dl:12.6g} {100 * rl:8.4f}")
    (base / "check.json").write_text(json.dumps({"tech": tech, "point": point, "wire_load": wl, "groups": table,
                                                 "pt_s": t_pt, "dc_s": t_dc}, indent=1) + "\n")
    print(f"setup-check {tech}: done; the differences go into the run note")
    return 0


def cmd_modules(args) -> int:
    """Once per source and technology: power_pt_modules.csv's size column filled on the rows written before it
    (the point's default size, from its committed tb.json and the source's default_size), and the rows of every
    n2048 run with seed 0 that has none yet, from the run's kept power_hierarchy.rpt and units.rpt in sim/runs/
    (pt_hierarchy, as a run writes them). Each added point's top row must equal power_pt.csv's e_dyn_pj."""
    use_source(args.source)
    f = RESULTS / args.tech / "power_pt_modules.csv"
    with f.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    with (RESULTS / args.tech / "power_pt.csv").open(newline="") as fh:
        power = {(r["point"], r["size"]): r for r in csv.DictReader(fh)
                 if r["seed"] == "0" and syn.gate_flag(r) == "0"}   # ungated rows only
    filled = 0
    defaults: dict[str, str] = {}
    for r in rows:
        if r.get("size"):
            continue
        p = r["point"]
        if p not in defaults:
            tb = json.loads(arc.read(power_zip(args.tech, p), "tb.json"))
            defaults[p] = src().default_size(tb)
        r["size"] = defaults[p]
        filled += 1
    have = {(r["point"], r["size"]) for r in rows}
    added, missing = [], []
    for (p, size), pr in sorted(power.items()):
        if size not in MODULE_SIZES or pr["status"] != "ok" or (p, size) in have:
            continue
        z = tech_runs(args.tech) / f"{p}.zip"
        tag = run_tag(size, "rand64", 0)
        if not z.is_file() or not arc.has(z, f"{tag}/pt/power_hierarchy.rpt") or not arc.has(z, f"{tag}/pt/units.rpt"):
            missing.append(p)
            continue
        with arc.unpacked(z, [f"{tag}/pt/power_hierarchy.rpt", f"{tag}/pt/units.rpt"]) as d:
            mods = pt_hierarchy(d / tag / "pt")
        new = [{"point": p, "tech": args.tech, "size": size, "path": m["path"], "design": m["design"],
                "e_dyn_pj": _num(m["dyn_uw"] * CLOCK_NS / 1000.0)} for m in mods]
        top = min(new, key=lambda m: m["path"].count("/"))
        if abs(float(top["e_dyn_pj"]) - float(pr["e_dyn_pj"])) > 1e-6 * max(1.0, abs(float(pr["e_dyn_pj"]))):
            sys.exit(f"{p} {size}: top module {top['e_dyn_pj']} pJ, power_pt.csv e_dyn_pj {pr['e_dyn_pj']}")
        added += new
        print(f"  {args.tech} {p} {size}: {len(new)} rows, top {top['design']} {top['e_dyn_pj']} pJ")
    out = rows + added
    out.sort(key=lambda r: (r["point"], r["size"], r["path"]))
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=MODULE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(out)
    print(f"pwr modules: {args.source} {args.tech}: size filled on {filled} rows, {len(added)} rows added "
          f"({len({(r['point'], r['size']) for r in added})} runs); no kept hierarchy report: {missing or 'none'}")
    return 1 if missing else 0


def cmd_summary(args) -> int:
    use_source(args.source)
    cols = ["point", "size", "seed", "cycles", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "e_comb_fire_pj",
            "e_flop_fire_pj", "flop_bits", "e_bit_pj", "status"]
    for tech in ([args.tech] if args.tech else syn.tech_names()):
        f = RESULTS / tech / "power_pt.csv"
        if not f.is_file():
            continue
        with f.open(newline="") as fh:
            rows = [r for r in csv.DictReader(fh)
                    if not args.patterns or any(__import__("fnmatch").fnmatchcase(r["point"], p) for p in args.patterns)]
        print(f"# {tech}")
        t = [[r.get(c, "") for c in cols] for r in rows]
        w = [max(len(c), *(len(x[i]) for x in t)) if t else len(c) for i, c in enumerate(cols)]
        print("  ".join(c.ljust(n) for c, n in zip(cols, w)))
        for x in t:
            print("  ".join(v.ljust(n) for v, n in zip(x, w)))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("tbjson", help="print a point's tb.json")
    p.add_argument("point")
    p.add_argument("--source", choices=list(SOURCES), default="hls")
    p.add_argument("--tech", choices=syn.tech_names(), default="nangate45",
                   help="forge: the netlist whose ports tb.json covers (the same on both technologies)")
    p.set_defaults(fn=cmd_tbjson)
    p = sub.add_parser("run", help="simulate and run PrimePower on points")
    p.add_argument("patterns", nargs="+")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--source", choices=list(SOURCES), default="hls")
    p.add_argument("--stim", default="rand64", choices=["rand64", "forge"])
    p.add_argument("--size", default=None,
                   help="a tb.json size tag (default b64, rowsum m8_n64; forge n2048), or 'all': every size in "
                        "the point's sizes.txt (forge: every size in tb.json)")
    p.add_argument("--seed", type=int, default=0, help="the stimulus seed (streamer, xbar: vsim -sv_seed)")
    p.add_argument("-j", type=int, default=0, help="at most this many workers (default: from the licences)")
    p.add_argument("--cores", type=int, default=0,
                   help="cores the whole run may use (default: nproc): J <= cores, PT threads = cores // J")
    p.add_argument("--initreg-seed", type=int, default=None,
                   help="a check, never the default: random register start (vopt +initreg=ru, vsim +initreg+N) "
                        "in place of +initreg+0; results/ is not written")
    p.add_argument("--clk-gate", action="store_true",
                   help="the clock-gated netlists (syn.py --clk-gate, <point>_cg.zip): runs and power_reports tagged "
                        "_cg, rows with clk_gate 1, apart from the ungated ones; off by default")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("setup-check", help="diagnostic: PT against DC with forced activity, per power group")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--source", choices=list(SOURCES), default="hls")
    p.add_argument("--point", default=None, help=f"default per source: {SETUP_POINTS}")
    p.set_defaults(fn=cmd_setup_check)
    p = sub.add_parser("modules", help="fill power_pt_modules.csv's size column, add the n2048 runs' modules")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--source", choices=["hls", "forge", "bambu", "xls"], default="hls")
    p.set_defaults(fn=cmd_modules)
    p = sub.add_parser("summary", help="print power_pt.csv")
    p.add_argument("patterns", nargs="*")
    p.add_argument("--tech", choices=syn.tech_names())
    p.add_argument("--source", choices=list(SOURCES), default="hls")
    p.set_defaults(fn=cmd_summary)
    args = ap.parse_args()
    if args.cmd == "run" and args.stim == "forge" and not args.size:
        sys.exit("--stim forge needs --size <cosim size> (validation only)")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
