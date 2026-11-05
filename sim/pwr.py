#!/usr/bin/env python3
"""sim/pwr.py - dynamic energy of mapped netlists from simulated activity (docs/power.md).

  pixi run pwr tbjson      POINT [--source hls|forge|char|bambu|xls] [--tech T]
  pixi run pwr run         PATTERN ... --tech T [--source hls|forge|char|bambu|xls] [--stim rand64|forge]
                                       [--size TAG|all] [--seed N] [-j N]
  pixi run pwr setup-check --tech T [--source hls|forge|bambu|xls] [--point P]
  pixi run pwr summary     [PATTERN ...] [--source ...] [--tech T]

--source hls (the default) takes hls-exercises' points, as below; --source forge takes snax-forge's bundles in
rtl/forge/ (forge/bundles.py) and their netlists in syn/runs/forge/<tech>/: tb.json from sim/sources/forge.py
(control forge_csr: the wrapper driven through its CSRs by sim/tb/csr_seq.sv), the size n2048, the window
from the edge accepting START to the run's end, whose cycles must equal the COUNTER read back and the group's
cycles from snax-forge's model; the stimulus rand64; the reference sim/ref.py, checked once per kernel and batch
against snax-forge's kernel body; runs in sim/runs/forge/<tech>/, results in results/forge/<tech>/ with the
columns recipe and snax_forge_commit added (docs/power.md, Forge).

--source char (CHAR1) takes snax-forge's catalogue blocks alone in rtl/char/ (char/blocks.py) and their netlists
in syn/runs/char/<tech>/: tb.json from sim/sources/char.py (control char_<kind>: the block's data and pins driven
by the kind's sequencer sim/tb/char_<kind>_seq.sv through fixed windows, every output compared at every falling
edge against sim/ref.py's char_ref), the stimulus rand64 (one stream per data input port), one vcd2saif and one
PT run per window, the windows' energies per cycle in results/char/<tech>/char_power.csv, one row per point and
window (docs/power.md, Char). --size does not apply.

--source bambu and --source xls (HSYN1, docs X44) take Bambu's points (hls-exercises' rtl/, <case>_w<W> with
case bambu) and Google XLS's (dslx-exercises' rtl/, case xls), as syn/syn.py lists them (its case filters and
MAX_W), and their netlists in syn/runs/<source>/<tech>/: tb.json from sim/sources/bambu.py (control bambu_ctl:
start_port pulsed by sim/tb/bambu_seq.sv, the run-time pins plain inputs held from time 0) or sim/sources/xls.py
(control xls_cfg: one cfg beat on _cfg_TDATA by sim/tb/xls_seq.sv); the streams through axis_src and axis_sink as
for hls; sizes b64, the point's sizes.txt (--size all) and n2048 for tier done; the expected cycles from the
line through results/<source>/<source>_cycles.csv (bambu: cycles_done; xls: cycles, plus 1 for the window); runs
in sim/runs/<source>/<tech>/, results in results/<source>/<tech>/ with X20's columns (docs/power.md, Bambu, XLS).

A point is an hls-exercises rtl/ folder, <tier>/<kernel>/<point>, whose mapped netlist is already in
syn/runs/hls/<tech>/<point>/out/ (syn/syn.py). Per point, one worker runs, start to end:
  tb.json    sim/sources/hls.py (docs/DECISIONS.md X14), written into the run folder
  compile    the fixed TB (sim/tb/) and a generated top (tb.sv), vlog; vopt +initreg+0 +acc=n
  per run (size, stimulus):
    stimulus rand64 (seed 0, 64 beats; rowsum at m8_n64) or forge (data.h at a cosim size, validation)
             with the reference of sim/ref.py; every input stream bit must toggle
    vsim     functional, zero delay: no SDF, +nospecify +notimingchecks; the TB dumps the DUT scopes
             to a VCD between $dumpon and $dumpoff around the busy window and checks every output beat
    cycles   against cosim's line cycles = a x loop_count + b (results/hls/hls_cycles.csv)
    vcd2saif the busy window, in the VCD's time unit; the VCD is deleted at once (X8, X18)
    saif     T0 + T1 + TX = DURATION on every net, DURATION = cycles x clock, clock TC = 2 x cycles (X9)
    pt       sim/scripts/pt_power.tcl: read_saif, >= 99% of nets annotated, report_power
  cleanup    the compiled design library and vsim.wlf are deleted (X18)
Results: results/hls/<tech>/power_pt.csv (one row per point, size and seed), power_pt_modules.csv
(the default run of each point) and power_reports/<point>/ (X20).

Parallel workers J = min(free msimhdlsim, free PrimePower, free PrimeTime, nproc) from lmutil lmstat;
PT threads per run = max(1, nproc // J) (X16). A tool that fails on a licence error is retried once (X17).
setup-check: a diagnostic (X25): PT against DC with the same forced activity, per power group, printed and kept in
check.json; it fails only on the wire-load check (PITFALLS PT1), never on the groups' differences.

Environment, all optional:
  PT_SHELL   pt_shell (else PATH)          LMUTIL    lmutil (else PATH)
  SIM_HLS    ../hls-exercises              vcd2saif  from PATH, else next to pt_shell
  vlib, vlog, vopt, vsim from PATH; dc_shell (setup-check) from DC_SHELL or PATH.
"""
from __future__ import annotations

import argparse
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
from ref import char_ref, ref  # noqa: E402

syn = _syn()      # syn/syn.py, loaded once (sim/sources/__init__.py): its SOURCES is the one port table (X44)

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
SOURCES = ("hls", "forge", "char", "bambu", "xls")
HLS_TOOLS = ("hls", "bambu", "xls")     # an HLS tool's points: rtl/ folders with filelist.f and sizes.txt
PT_SCRIPT = SIM / "scripts" / "pt_power.tcl"
RUN_DO = SIM / "scripts" / "run.do"
DC_READBACK = SIM / "probe" / "dc_readback.tcl"
TB_TOP, DUT = "tb", "dut"
CLOCK_NS = 10.0
SETUP_POINTS = {"hls": "done/vecadd/opt_w8", "forge": "done/vecadd/forge_w4", "bambu": "done/dot/bambu_w8",
                "xls": "done/dot/xls_w16"}     # setup-check's default point per source (X25)
MIN_ANNOTATED = 99.0        # percent of nets annotated from the SAIF
TOGGLE_BEATS = 64           # the input-toggle check fails a run from this many beats up
# Questa cell models, next to each technology's .db, with the vlog options they need
CELL_MODELS = {"nangate45": ("NangateOpenCellLibrary.v", []),
               "nangate15": ("NanGate_15nm_OCL_functional.v", ["-timescale", "1ns/1ps"])}
COLUMNS = ["point", "top", "tech", "clock_ns", "W", "size", "config", "beats", "seed", "cycles",
           "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "p_dyn_uw",
           "e_comb_fire_pj", "e_flop_fire_pj", "e_run_pj", "flop_bits", "e_bit_pj", "status"]
FORGE_COLUMNS = ["recipe", "snax_forge_commit"]
MODULE_COLUMNS = ["point", "tech", "path", "design", "e_dyn_pj"]
KEPT = ("power.rpt", "power_hierarchy.rpt", "switching_activity.rpt")
LICENCE_ERR = re.compile(r"(?i)(licen[sc]\w*\s+(error|fail\w*|not available|denied|checkout)|unable to check\s*out"
                         r"|could not check\s*out|cannot check\s*out|feature removed|license server)")
MASK64 = (1 << 64) - 1


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
    return COLUMNS + (FORGE_COLUMNS if SOURCE == "forge" else [])


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
    """Run a tool with its output in `log`; on a licence error, once more (X17)."""
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
def syn_run(tech: str, point: str) -> Path:
    return SYN_RUNS / tech / point


def netlist_of(tech: str, point: str) -> Path:
    found = sorted((syn_run(tech, point) / "out").glob("*_mapped.v"))
    if not found:
        raise Fail(f"no mapped netlist in {syn_run(tech, point).relative_to(ROOT)}/out")
    return found[0]


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


def stream_block(tb: dict, s: dict, clk: str, rst: str, go: str = "go") -> tuple[list[str], str | None]:
    dw = 64 * s["lanes"]
    L = [f"    wire [{dw - 1}:0] {s['data']};", f"    wire {s['valid']}, {s['ready']};"]
    if s["dir"] == "in":
        L += [f"    axis_src #(.DW({dw}), .NAME(\"{s['arg']}\")) src_{s['arg']} (.clk({clk}), "
              f".go({go}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}));"]
        return L, None
    L += [f"    wire complete_{s['arg']};",
          f"    axis_sink #(.DW({dw}), .NAME(\"{s['arg']}\")) snk_{s['arg']} (.clk({clk}), "
          f".rst_n({rst}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}), "
          f".complete(complete_{s['arg']}));"]
    return L, f"complete_{s['arg']}"


def tb_top_forge(tb: dict, netlist: Path) -> str:
    """The forge top: csr_seq on the wrapper's CSR port, the streams as for HLS (axis_src, axis_sink)."""
    c, clk, rst, L = tb["control"], tb["clock"]["port"], tb["reset"]["port"], []
    L += ["// Generated by sim/pwr.py from tb.json (source forge): do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {clk}, {rst}, go, sinks_complete;",
          f"    wire [31:0] {c['req_addr']}, {c['req_data']}, {c['rsp_data']};",
          f"    wire {c['req_write']}, {c['req_valid']}, {c['req_ready']}, {c['rsp_valid']}, {c['rsp_ready']};",
          f"    wire {c['busy']}, {c['done']};", "",
          f"    csr_seq #(.T_NS({CLOCK_NS})) seq (.clk({clk}), .rst_n({rst}), .go(go), .req_addr({c['req_addr']}), "
          f".req_data({c['req_data']}), .req_write({c['req_write']}), .req_valid({c['req_valid']}), "
          f".req_ready({c['req_ready']}), .rsp_data({c['rsp_data']}), .rsp_valid({c['rsp_valid']}), "
          f".rsp_ready({c['rsp_ready']}), .done({c['done']}), .sinks_complete(sinks_complete));", ""]
    done = []
    for s in tb["streams"]:
        lines, comp = stream_block(tb, s, clk, rst)
        L += lines + [""]
        if comp:
            done.append(comp)
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""]
    ports = [clk, rst, c["busy"], c["done"]]
    ports += [c[k] for k in ("req_addr", "req_data", "req_write", "req_valid", "req_ready", "rsp_data", "rsp_valid",
                             "rsp_ready")]
    ports += [s[k] for s in tb["streams"] for k in ("data", "valid", "ready")]
    L += [f"    {tb['top']} {DUT} ("] + [f"        .{p}({p}){',' if i < len(ports) - 1 else ''}"
                                         for i, p in enumerate(ports)] + ["    );", ""]
    L += dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def tb_top(tb: dict, netlist: Path) -> str:
    """The thin per-point top: tb.json's ports wired to the fixed modules of sim/tb/."""
    if tb["control"]["kind"] == "forge_csr":
        return tb_top_forge(tb, netlist)
    if tb["control"]["kind"].startswith("char_"):
        return tb_top_char(tb, netlist)
    c, L = tb["control"], []
    L += ["// Generated by sim/pwr.py from tb.json: do not edit.", "`timescale 1ns/1ps", "",
          f"module {TB_TOP};",
          f"    wire {tb['clock']['port']}, {tb['reset']['port']}, {c['start']}, pin_vld, go;",
          f"    wire {c['done']}, {c['idle']}, {c['ready']}, sinks_complete;", ""]
    L += [f"    ap_ctrl_hs_seq #(.T_NS({CLOCK_NS})) seq (.clk({tb['clock']['port']}), .rst_n({tb['reset']['port']}), "
          f".go(go), .ap_start({c['start']}), .vld(pin_vld), .ap_done({c['done']}), .ap_ready({c['ready']}), "
          f".sinks_complete(sinks_complete));", ""]
    done = []
    for s in tb["streams"]:
        dw = 64 * s["lanes"]
        L += [f"    wire [{dw - 1}:0] {s['data']};", f"    wire {s['valid']}, {s['ready']};"]
        if s["dir"] == "in":
            L += [f"    axis_src #(.DW({dw}), .NAME(\"{s['arg']}\")) src_{s['arg']} (.clk({tb['clock']['port']}), "
                  f".go(go), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}));"]
        else:
            L += [f"    wire complete_{s['arg']};",
                  f"    axis_sink #(.DW({dw}), .NAME(\"{s['arg']}\")) snk_{s['arg']} (.clk({tb['clock']['port']}), "
                  f".rst_n({tb['reset']['port']}), .tdata({s['data']}), .tvalid({s['valid']}), .tready({s['ready']}), "
                  f".complete(complete_{s['arg']}));"]
            done.append(f"complete_{s['arg']}")
        L.append("")
    L += [f"    assign sinks_complete = {' & '.join(done)};", ""]
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
def beats_hex(x: np.ndarray, lanes: int) -> str:
    out = []
    for b in range(len(x) // lanes):
        v = 0
        for lane in range(lanes):
            v |= (int(x[b * lanes + lane]) & MASK64) << (64 * lane)
        out.append(f"{v:0{lanes * 16}x}\n")
    return "".join(out)


def untoggled_bits(x: np.ndarray, beats: int, lanes: int) -> int:
    seen = np.bitwise_or.reduce(x.view(np.uint64).reshape(beats, lanes), axis=0)
    return sum(64 - bin(int(v)).count("1") for v in seen)


def stimulus_forge(tb: dict, size: str, seed: int) -> dict:
    """rand64 (X19): N full-range int64 per input stream, seed `seed`, stream by stream in tb.json order;
    the reference from sim/ref.py; every input bit must toggle (N / W beats, 64 or more at n2048)."""
    z = tb["sizes"][size]
    n = z["N"]
    ins_s = [s for s in tb["streams"] if s["dir"] == "in"]
    rng = np.random.default_rng(seed)
    info = np.iinfo(np.int64)
    ins = {s["arg"]: rng.integers(info.min, info.max, size=n, dtype=np.int64, endpoint=True) for s in ins_s}
    outs = ref(tb["kernel"], ins, {})
    untoggled = {}
    for s in ins_s:
        k = untoggled_bits(ins[s["arg"]], n // s["lanes"], s["lanes"])
        if k:
            untoggled[s["arg"]] = k
            if n // s["lanes"] >= TOGGLE_BEATS:
                raise Fail(f"stimulus: {k} bits of {s['arg']} never toggle")
    for s in tb["streams"]:
        if s["dir"] == "out" and len(outs[s["arg"]]) % s["lanes"]:
            raise Fail(f"reference {s['arg']}: {len(outs[s['arg']])} values do not fill {s['lanes']} lanes")
    return {"ins": ins, "pins": {}, "outs": outs, "beats": n // ins_s[0]["lanes"], "untoggled": untoggled}


# The forge reference check: sim/ref.py against snax-forge's kernel body (forge/query.py ref), once per kernel,
# size and seed in a batch (the inputs depend on N and the seed only, not on W)
REF_CHECKED: dict = {}
REF_LOCK = threading.Lock()


def forge_ref_check(tb: dict, size: str, seed: int, st: dict, rdir: Path) -> dict:
    key = (tb["kernel"], size, seed)
    with REF_LOCK:
        if key not in REF_CHECKED:
            got = forge_src.kernel_ref(tb["kernel"], st["ins"], rdir / "ref_check")
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
    pins = dict(cfg)
    if stim == "rand64":
        rng = np.random.default_rng(seed)
        info = np.iinfo(np.int64)
        ins = {s["arg"]: rng.integers(info.min, info.max, size=beats * s["lanes"], dtype=np.int64, endpoint=True)
               for s in ins_s}
        for p in data_pins:
            pins[p] = int(rng.integers(info.min, info.max, dtype=np.int64, endpoint=True))
    elif stim == "forge":
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
    outs = ref(tb["kernel"], ins, pins)
    if stim == "forge":
        prm = hls.params_of(tb["point"])
        inv = {v: k for k, v in prm.get("dace", {}).get("split_inout", {}).items()}
        for arg, v in outs.items():
            exp = d.get(f"EXP_{arg}") or d.get(f"EXP_{inv.get(arg, arg)}")
            if exp is None or not np.array_equal(v, np.array(exp, dtype=np.int64)):
                raise Fail(f"sim/ref.py differs from data.h EXP for {arg}")
    # Every input bit toggles at least once (from the 0 the TB holds before go). Enforced from TOGGLE_BEATS
    # beats up: with B random beats a bit stays 0 with probability 2^-B, so a task of a few beats (n64 at
    # W = 32 is 2 beats) cannot pass with any seed; below that the count is recorded (docs X19).
    untoggled = {}
    for s in ins_s:
        x = ins[s["arg"]].view(np.uint64).reshape(beats, s["lanes"])
        seen = np.bitwise_or.reduce(x, axis=0)
        n = sum(64 - bin(int(v)).count("1") for v in seen)
        if n:
            untoggled[s["arg"]] = n
            if beats >= TOGGLE_BEATS:
                raise Fail(f"stimulus: {n} bits of {s['arg']} never toggle")
    for s in tb["streams"]:
        if s["dir"] == "out" and len(outs[s["arg"]]) % s["lanes"]:
            raise Fail(f"reference {s['arg']}: {len(outs[s['arg']])} values do not fill {s['lanes']} lanes")
    return {"ins": ins, "pins": pins, "outs": outs, "beats": beats, "config": cfg, "untoggled": untoggled}


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
    """X9: T0 + T1 + TX = DURATION on every net, DURATION = cycles x clock, the clock toggles 2 x cycles.

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


def pt_groups(rep: Path) -> dict:
    """{group: (internal, switching, leakage) in uW} from PT's power.rpt."""
    to_uw = pt_to_uw(rep / "units.rpt")
    text = (rep / "power.rpt").read_text()
    out = {}
    for g in syn.POWER_GROUPS:
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
            if r["point"] == point and float(r["clock_ns"]) == CLOCK_NS and r["seq_cells"]:
                return int(r["seq_cells"])
    return None


# ---------------------------------------------------------------- one point
def cells_lib(tech: str) -> Path:
    """The cell models compiled once per technology into sim/runs/<tech>/_cells."""
    lib = RUNS / tech / "_cells"
    if (lib / "_info").is_file():
        return lib
    res = syn.resolve(syn.load_tech(tech))
    model, opts = CELL_MODELS[tech]
    src = Path(res["lib_db"]).parent / model
    lib.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([tool("vlib"), str(lib)], check=True, capture_output=True)
    log = RUNS / tech / "_cells.vlog.log"
    if run_tool([tool("vlog"), *opts, "-work", str(lib), str(src)], log, RUNS / tech) or \
            re.search(r"Errors: [1-9]", log.read_text()):
        sys.exit(f"vlog of {src} failed: {log}")
    return lib


def run_tag(size: str, stim: str, seed: int) -> str:
    return f"{size}_forge" if stim == "forge" else f"{size}_s{seed}"


def compile_point(tb: dict, tech: str, pdir: Path, netlist: Path, cells: Path) -> None:
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
    tb_files = tb["tb_files"] if tb.get("source") == "char" else TB_FILES[tb.get("source", "hls")]
    incdir = [f"+incdir+{TB_DIR}"] if tb.get("source") == "char" else []    # char_seq_core.svh
    steps = [("vlog_tb", [tool("vlog"), "-sv", *incdir, "-work", str(work),
                          *(str(TB_DIR / f) for f in tb_files),
                          str(pdir / "tb.sv")]),
             ("vlog_netlist", [tool("vlog"), "-timescale", "1ns/1ps", "-work", str(work), str(netlist)]),
             ("vopt", [tool("vopt"), "-work", str(work), "-L", str(cells), TB_TOP, "+initreg+0", "+acc=n",
                       "-o", "tb_opt"])]
    for name, cmd in steps:
        log = logs / f"{name}.log"
        rc = run_tool(cmd, log, pdir)
        if rc or re.search(r"Errors: [1-9]", log.read_text()):
            raise Fail(f"{name} (logs/{name}.log)")


def run_one(tb: dict, tech: str, pdir: Path, size: str, stim: str, seed: int, threads: int, times: dict,
            row: dict) -> dict:
    """One run; fills `row` as it goes, so a failed run keeps what it got (cycles). Returns its info."""
    rdir = pdir / run_tag(size, stim, seed)
    if rdir.exists():
        shutil.rmtree(rdir)
    (rdir / "stim").mkdir(parents=True)
    cfg = tb["sizes"][size]
    forge = tb["control"]["kind"] == "forge_csr"
    if forge:
        row.update({"config": " ".join(f"{name}={v}" for _, v, name in cfg["writes"][:-1]),
                    "beats": cfg["N"] // next(s["lanes"] for s in tb["streams"] if s["dir"] == "in")})
    else:
        row.update({"config": " ".join(f"{k}={v}" for k, v in cfg.items()), "beats": cfg["loop_count"]})
    info = {"run": str(rdir.relative_to(ROOT)), "times": times}

    t = time.time()
    st = stimulus_forge(tb, size, seed) if forge else stimulus(tb, size, stim, seed)
    plus = []
    if forge:
        info["ref_check"] = forge_ref_check(tb, size, seed, st, rdir)
        f = rdir / "stim" / "csr.hex"
        f.write_text("".join(f"{off:08x}{val & 0xFFFFFFFF:08x}\n" for off, val, _ in cfg["writes"]))
        plus += [f"+CSR_HEX={f}", f"+CSR_N={len(cfg['writes'])}",
                 f"+COUNTER_ADDR={tb['control']['csrs']['COUNTER']:x}"]
    for s in tb["streams"]:
        x = st["ins"][s["arg"]] if s["dir"] == "in" else st["outs"][s["arg"]]
        f = rdir / "stim" / f"{s['arg']}.hex"
        f.write_text(beats_hex(x, s["lanes"]))
        plus += [f"+{s['arg']}_HEX={f}", f"+{s['arg']}_BEATS={len(x) // s['lanes']}"]
    for p in tb["pins"]:
        plus.append(f"+PIN_{p['port']}={st['pins'][p['port']] & ((1 << p['bits']) - 1):x}")
    (rdir / "stim" / "pins.json").write_text(json.dumps(st["pins"], indent=1) + "\n")
    info["untoggled_bits"] = st["untoggled"]
    if forge:
        exp, how = cfg["expected_cycles"], f"snax-forge's group_counter: {cfg['expected_from']}"
    elif SOURCE == "hls":
        exp, how = expected_cycles(tb, size)
    else:       # bambu, xls: the line through the tool's own cycle CSV (X44)
        exp, how = src().expected_cycles(tb, size, RESULTS)
    info["expected_cycles"], info["expected_from"] = exp, how
    times["stim"] = time.time() - t

    vcd = rdir / "dut.vcd"
    try:
        t = time.time()
        timeout = max(10000, 4 * (exp or 0) + 1000)
        cmd = [tool("vsim"), "-c", "-work", str(pdir / "work"), "tb_opt", "+nospecify", "+notimingchecks",
               "-wlf", str(rdir / "vsim.wlf"), f"+VCD={vcd}", f"+TIMEOUT={timeout}", *plus, "-do", str(RUN_DO)]
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
        if forge and "TB: FAIL" in log:
            raise Fail("sim: " + re.search(r"TB: FAIL: (.*)", log).group(1))
        if forge:
            cnt = re.search(r"TB: counter (\d+)", log)
            info["counter"] = int(cnt.group(1)) if cnt else None
            if info["counter"] != cycles:
                raise Fail(f"cycles: window {cycles}, COUNTER {info['counter']}")
        if exp is None:
            raise Fail(f"cycles: no expected value ({how})")
        if cycles != exp:
            raise Fail(f"cycles {cycles}, expected {exp} ({how})")

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
        vcd.unlink(missing_ok=True)      # X18: no VCD is kept, whatever the result

    t = time.time()
    info["saif"] = saif_check(saif, cycles, tb["clock"]["port"])
    times["saif_check"] = time.time() - t

    t = time.time()
    ptd = rdir / "pt"
    ptd.mkdir()
    env = {**os.environ, "PWR_RUN": str(syn_run(tech, tb["point"])), "PWR_MODE": "saif", "PWR_ACT": str(saif),
           "PWR_STRIP": f"{TB_TOP}/{DUT}", "PWR_OUT": str(ptd), "PWR_THREADS": str(threads)}
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
    energy_row(row, groups, flop_bits_of(tech, tb["point"]))
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


def build_tb(point: str, tech: str) -> dict:
    """The point's tb.json from its source's adapter (forge: from the bundle and the netlist's ports)."""
    if SOURCE == "forge":
        tb = forge_src.build(point, netlist_of(tech, point))
    elif SOURCE in ("char", "bambu", "xls"):
        tb = src().build(point, netlist_of(tech, point))
    else:
        tb = hls.build(point)
    src().check(tb)
    return tb


def do_point(point: str, tech: str, runs: list, threads: int) -> list[tuple[dict, dict]]:
    """One worker: tb.json, compile, every requested run, cleanup. Returns [(row, info)]."""
    pdir = tech_runs(tech) / point
    out = []
    try:
        rams = syn.rams_of(point) if SOURCE in HLS_TOOLS else []
        if rams:
            row = {c: "" for c in COLUMNS}
            row.update({"point": point, "top": syn.top_of(point), "tech": tech, "clock_ns": _num(CLOCK_NS), "size": "",
                        "seed": "", "status": f"skipped: needs a RAM macro ({', '.join(rams)}); "
                                              f"{tech} has no RAM cells, RAM1 builds one (OpenRAM)"})
            return [(row, {})]
        tb = build_tb(point, tech)
    except (ValueError, KeyError, FileNotFoundError, Fail) as e:
        row = {c: "" for c in COLUMNS}
        row.update({"point": point, "tech": tech, "size": "", "seed": "", "status": f"failed: tb.json: {e}"})
        return [(row, {})]
    pdir.mkdir(parents=True, exist_ok=True)     # other runs of the point (their SAIFs) stay
    for stale in ("work", "logs"):
        shutil.rmtree(pdir / stale, ignore_errors=True)
    tb_text = json.dumps(tb, indent=1) + "\n"
    (pdir / "tb.json").write_text(tb_text)
    t_point = time.time()
    try:
        compile_times = {}
        t = time.time()
        try:
            netlist = netlist_of(tech, point)
            compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells")     # the cells: one per technology
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
            base.update({"point": point, "top": tb["top"], "tech": tech, "clock_ns": _num(CLOCK_NS), "W": tb["W"],
                         "size": size, "seed": "forge" if stim == "forge" else seed})
            if SOURCE == "forge":
                base.update({"recipe": tb["recipe"], "snax_forge_commit": tb["snax_forge_commit"]})
            info = {"run": str((pdir / run_tag(size, stim, seed)).relative_to(ROOT)), "times": times,
                    "default": (stim, seed, size) == ("rand64", 0, src().default_size(tb))}
            try:
                if size not in tb["sizes"]:
                    raise Fail(f"size {size} not in tb.json ({', '.join(tb['sizes'])})")
                if compile_err:
                    raise Fail(compile_err)
                info.update(run_one(tb, tech, pdir, size, stim, seed, threads, times, base))
            except Fail as e:
                base["status"] = f"failed: {e}"
            except Exception as e:          # noqa: BLE001  a crash fails this run, not the batch
                base["status"] = f"failed: {type(e).__name__}: {e}"
            info["row"] = base
            rdir = ROOT / info["run"]
            if rdir.is_dir():
                (rdir / "result.json").write_text(json.dumps(info, indent=1, default=str) + "\n")
            out.append((base, info))
    finally:
        shutil.rmtree(pdir / "work", ignore_errors=True)        # X18: no compiled design is kept
        for f in pdir.rglob("vsim.wlf"):
            f.unlink()
        for f in pdir.rglob("*.vcd"):
            f.unlink()
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
    table.sort(key=lambda r: (r["point"], r.get("size", ""), str(r.get("seed", "")), r.get("path", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)


def write_results(tech: str, results: list[tuple[dict, dict]]) -> None:
    out = RESULTS / tech
    key = lambda r: (r["point"], r["size"], str(r["seed"]))  # noqa: E731
    rows = [r for r, _ in results]
    _merge(out / "power_pt.csv", columns(), key, rows, {key(r) for r in rows})
    mods, mod_points = [], set()
    for r, info in results:
        if not info.get("default"):
            continue
        mod_points.add(r["point"])
        dest = out / "power_reports" / r["point"]
        if dest.exists():
            for f in dest.iterdir():
                if f.is_file():
                    f.unlink()
        if r["status"] != "ok":
            continue
        dest.mkdir(parents=True, exist_ok=True)
        for m in info.get("modules", []):
            mods.append({"point": r["point"], "tech": tech, "path": m["path"], "design": m["design"],
                         "e_dyn_pj": m["dyn_uw"] * CLOCK_NS / 1000.0})
    _merge(out / "power_pt_modules.csv", MODULE_COLUMNS, lambda r: r["point"], mods, mod_points)
    for r, info in results:
        if r["status"] != "ok":
            continue
        rdir = ROOT / info["run"]
        dest = out / "power_reports" / r["point"]
        if not info.get("default"):
            dest = dest / rdir.name
            shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        for f in KEPT:
            shutil.copy2(rdir / "pt" / f, dest / f)
        shutil.copy2(rdir.parent / "tb.json", out / "power_reports" / r["point"] / "tb.json")


# ---------------------------------------------------------------- char (CHAR1): a block alone, per window
CHAR_COLUMNS = ["point", "datapath", "lanes", "depth", "op", "form", "tech", "clock_ns", "window", "cycles", "fires",
                "seed", "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "e_bit_pj", "status",
                "snax_forge_commit"]
CHAR_KEPT = ("power.rpt", "switching_activity.rpt")


def tb_top_char(tb: dict, netlist: Path) -> str:
    """The char top: the kind's sequencer on the block's data, pins and outputs; a pin of no bits is absent from
    the netlist and left open on the sequencer."""
    kind, ni, no = tb["kind"], len(tb["data_in"]), len(tb["outs"])
    pins = tb["pins"]
    params = {"T_NS": CLOCK_NS, "NI": ni, "NO": no}
    wires = []
    if kind == "fold":
        wires = [("fire", 1), ("first", 1)]
    elif kind == "serial":
        lw = max(1, pins.get("lane", {}).get("bits", 0))
        params.update({"W": tb["W"], "LW": lw})
        wires = [("read", 1), ("lane", lw), ("first", 1)]
    elif kind == "link":
        sw = max(1, pins.get("wslot", {}).get("bits", 0))
        params.update({"D": tb["depth"], "SW": sw})
        wires = [("load", 1), ("wslot", sw), ("rslot", sw)]
    L = ["// Generated by sim/pwr.py from tb.json (source char): do not edit.", "`timescale 1ns/1ps", "",
         f"module {TB_TOP};", f"    wire {tb['clock']['port']}, {tb['reset']['port']};", f"    wire [{64 * ni - 1}:0] data;",
         f"    wire [{64 * no - 1}:0] out;"]
    L += [f"    wire {'' if b == 1 else '[%d:0] ' % (b - 1)}p_{n};" for n, b in wires]
    conn = [f".clk({tb['clock']['port']})", f".rst({tb['reset']['port']})", ".data(data)", ".out(out)"] + [f".{n}(p_{n})" for n, _ in wires]
    L += ["", f"    char_{kind}_seq #({', '.join(f'.{k}({v})' for k, v in params.items())}) seq ({', '.join(conn)});", ""]
    ports = [tb["clock"]["port"], tb["reset"]["port"]]
    ports += [f"{p}(data[{64 * i + 63}:{64 * i}])" for i, p in enumerate(tb["data_in"])]
    ports += [f"{p}(out[{64 * i + 63}:{64 * i}])" for i, p in enumerate(tb["outs"])]
    for n, p in pins.items():
        sel = "" if p["bits"] == 1 else f"[{p['bits'] - 1}:0]"
        ports.append(f"{p['port']}(p_{n}{sel})")
    ports = [p if "(" in p else f"{p}({p})" for p in ports]
    L += [f"    {tb['top']} {DUT} ("] + [f"        .{p}{',' if i < len(ports) - 1 else ''}" for i, p in enumerate(ports)]
    L += ["    );", ""] + dump_block(tb, netlist) + ["endmodule", ""]
    return "\n".join(L)


def char_seq_cells(tech: str, point: str) -> int | None:
    f = RESULTS / tech / "char_synth.csv"
    with f.open(newline="") as fh:
        for r in csv.DictReader(fh):
            if r["point"] == point and float(r["clock_ns"]) == CLOCK_NS:
                return int(r["seq_cells"] or 0)
    return None


def char_stimulus(tb: dict, slots: list[dict], seed: int) -> dict:
    """rand64 (X19): per data input port in tb.json order, one stream of full-range int64, as many values as the
    slots take new beats; the expected outputs from sim/ref.py's char_ref. Every data input bit must take both
    values in the working window's beats (busy, or link's stream: it toggles there). For link's stream the
    reference is checked against the FIFO it is: the output at stream slot t is the beat loaded D slots before."""
    n_new = sum(1 for s in slots if s["new"])
    rng = np.random.default_rng(seed)
    info = np.iinfo(np.int64)
    streams = [rng.integers(info.min, info.max, size=n_new, dtype=np.int64, endpoint=True) for _ in tb["data_in"]]
    beats = [[int(x[b]) & MASK64 for x in streams] for b in range(n_new)]
    busy, b = [], 0
    for s in slots:
        if s["new"]:
            if s["window"] in ("busy", "stream"):
                busy.append(b)
            b += 1
    untoggled = {}
    for i, port in enumerate(tb["data_in"]):
        v = np.array([beats[j][i] for j in busy], dtype=np.uint64)
        ones, zeros = np.bitwise_or.reduce(v), np.bitwise_or.reduce(~v)
        k = 64 - bin(int(ones & zeros)).count("1")
        if k:
            untoggled[port] = k
    if untoggled:
        raise Fail(f"stimulus: data bits that never toggle in the working window: {untoggled}")
    exps = char_ref(tb["datapath"], tb["params"], slots, beats)
    if tb["kind"] == "link":
        loaded = []
        for k, s in enumerate(slots):
            if s["new"]:
                loaded.append(k)
        bad = [k for k, s in enumerate(slots) if s["window"] == "stream"
               and exps[k] != beats[loaded.index(k) - tb["depth"]]]
        if bad:
            raise Fail(f"reference: stream slots {bad[:5]} do not give the beat loaded D = {tb['depth']} before")
    return {"beats": beats, "exps": exps, "n_new": n_new, "busy_beats": len(busy)}


def vcd_windows(vcd: Path, wins: list[tuple[str, int, int]], out: dict) -> None:
    """Cut the run's VCD into one VCD per window, in one pass: the header, then at the window's start t0 a
    $dumpvars block with every variable's value there, then the window's own events up to t1 (VCD time units).
    vcd2saif -time t0 t1 on the shared VCD counts one toggle in the window for a net whose last change before t0 was
    a zero-width pulse (two or more changes in one time step that end where they began, which the zero-delay sim
    makes); the cut file has no event before t0, so a window is counted from its own events only (docs/power.md,
    Char). The values are written at the time of the last time step before t0, as plain value changes, and each cut
    ends with a bare time step at t1 (vcd2saif ends a file's window at its last time step), so the window is whole. The boundaries are quiet: an event at a
    boundary fails the point. `out` maps a window to its file."""
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
    """One worker: tb.json, compile, one simulation over every window, then per window vcd2saif, the SAIF check and
    PT; cleanup. Returns [(row, info)], one per window."""
    t_point = time.time()
    extra = syn.char_extra(point)
    base = {c: "" for c in CHAR_COLUMNS}
    base.update({"point": point, "tech": tech, "clock_ns": _num(CLOCK_NS), "seed": seed,
                 **{k: extra[k] for k in ("datapath", "lanes", "depth", "op", "form", "snax_forge_commit")}})
    try:
        tb = build_tb(point, tech)
    except (ValueError, KeyError, FileNotFoundError, Fail) as e:
        return [({**base, "window": "", "status": f"failed: tb.json: {e}"}, {})]
    rows = {w["name"]: {**base, "window": w["name"]} for w in tb["windows"]}
    infos = {w: {} for w in rows}
    pdir = tech_runs(tech) / point
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
        netlist = netlist_of(tech, point)
        compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells")
        times["compile"] = time.time() - t
        t = time.time()
        slots = char_src.schedule(tb)
        st = char_stimulus(tb, slots, seed)
        (rdir / "stim" / "data.hex").write_text("".join(_pack(b) for b in st["beats"]))
        (rdir / "stim" / "exp.hex").write_text("".join(_pack(e) for e in st["exps"]))
        sim.update({"slots": len(slots), "beats": st["n_new"], "busy_beats": st["busy_beats"],
                    "samples": len(st["exps"])})
        times["stim"] = time.time() - t
        t = time.time()
        cmd = [tool("vsim"), "-c", "-work", str(pdir / "work"), "tb_opt", "+nospecify", "+notimingchecks",
               "-wlf", str(rdir / "vsim.wlf"), f"+VCD={vcd}", f"+DATA_HEX={rdir / 'stim' / 'data.hex'}",
               f"+DATA_N={st['n_new']}", f"+EXP_HEX={rdir / 'stim' / 'exp.hex'}", f"+EXP_N={len(st['exps'])}",
               "-do", str(RUN_DO)]
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
        vcd.unlink()                     # X18: the shared VCD is gone once cut
        t = time.time()
        for w, a, b in spans:
            try:
                rc = run_tool([tool("vcd2saif"), "-input", str(cuts[w]), "-output", str(rdir / w / f"{w}.saif"),
                               "-instance", f"{TB_TOP}/{DUT}", "-time", str(a), str(b)], rdir / w / "vcd2saif.log",
                              rdir / w)
            finally:
                cuts[w].unlink(missing_ok=True)      # X18: and each window's cut at once
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
        vcd.unlink(missing_ok=True)      # X18: no VCD is kept, whatever the result
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
            env = {**os.environ, "PWR_RUN": str(syn_run(tech, point)), "PWR_MODE": "saif",
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
        info = {**infos[w], "sim": sim, "row": r, "run": str((rdir / w).relative_to(ROOT))}
        if (rdir / w).is_dir():
            (rdir / w / "result.json").write_text(json.dumps(info, indent=1, default=str) + "\n")
        out.append((r, info))
    if rdir.is_dir():
        (rdir / "result.json").write_text(json.dumps(sim, indent=1, default=str) + "\n")
    return out


def write_results_char(tech: str, results: list[tuple[dict, dict]]) -> None:
    """char_power.csv (merged on point, window and seed, in each kind's window order), and per ok window its
    reports in power_reports/<point>/<window>/, the point's tb.json once in power_reports/<point>/."""
    out = RESULTS / tech
    key = lambda r: (r["point"], r["window"], str(r["seed"]))  # noqa: E731
    rows = [r for r, _ in results]
    done = {key(r) for r in rows}
    table = []
    f = out / "char_power.csv"
    if f.is_file():
        with f.open(newline="") as fh:
            table = [r for r in csv.DictReader(fh) if key(r) not in done and (r["point"], "", r["seed"]) not in
                     {(x["point"], "", str(x["seed"])) for x in rows if not x["window"]}]
    table += [{c: _num(r.get(c, "")) for c in CHAR_COLUMNS} for r in rows]
    order = {w: i for ws in char_src.WINDOWS.values() for i, w in enumerate(ws)}
    table.sort(key=lambda r: (r["point"], str(r["seed"]), order.get(r["window"], -1)))
    out.mkdir(parents=True, exist_ok=True)
    with f.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CHAR_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)
    for r, info in results:
        if not r["window"]:
            continue
        dest = out / "power_reports" / r["point"] / r["window"]
        shutil.rmtree(dest, ignore_errors=True)
        if r["status"] != "ok":
            continue
        dest.mkdir(parents=True)
        for name in CHAR_KEPT:
            shutil.copy2(ROOT / info["run"] / "pt" / name, dest / name)
        tbj = tech_runs(tech) / r["point"] / "tb.json"
        shutil.copy2(tbj, out / "power_reports" / r["point"] / "tb.json")


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


# ---------------------------------------------------------------- commands
def cmd_tbjson(args) -> int:
    use_source(args.source)
    if args.source == "hls":
        tb = hls.build(args.point)
        hls.check(tb)
    else:       # forge, char: from the netlist's ports
        tb = build_tb(args.point, args.tech)
    print(json.dumps(tb, indent=1))
    return 0


def cmd_run(args) -> int:
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
    nproc = os.cpu_count() or 1
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
                             "seed": args.seed, "licences": lic, "nproc": nproc, "J": j, "threads": threads}) + "\n")
    t = time.time()
    cells_lib(args.tech)
    print(f"pwr: cell models compiled in {time.time() - t:.1f} s", flush=True)
    runs = [(args.size, args.stim, args.seed)]
    results = []

    if args.source == "char":
        return run_char(points, args.tech, args.seed, j, threads)

    def work(p):
        res = do_point(p, args.tech, runs, threads)
        for r, info in res:
            tt = info.get("times", {})
            print(f"{r['point']} {r['size']} {r['seed']}: {r['status']}  cycles {r.get('cycles', '')}  "
                  f"e_dyn {_num(r['e_dyn_pj']) if r.get('e_dyn_pj') != '' else '-'} pJ  "
                  f"({', '.join(f'{k} {v:.1f}' for k, v in tt.items())} s)", flush=True)
        return res
    t = time.time()
    with ThreadPoolExecutor(max_workers=j) as ex:
        for res in ex.map(work, points):
            results += res
    print(f"pwr: batch {time.time() - t:.1f} s", flush=True)
    write_results(args.tech, results)
    bad = [r for r, _ in results if r["status"] != "ok"]
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
    """X25: PT and DC on the same netlist with the same forced activity, per power group: a diagnostic. It prints
    the differences (for the run note) and fails only on the wire-load check (PITFALLS PT1)."""
    use_source(args.source)
    point = args.point or SETUP_POINTS.get(args.source)
    if not point:
        sys.exit(f"setup-check: no default point for --source {args.source}; give --point")
    tech = args.tech
    base = tech_runs(tech) / "setup_check" / point
    shutil.rmtree(base, ignore_errors=True)
    (base / "pt").mkdir(parents=True)
    (base / "dc").mkdir(parents=True)
    run = syn_run(tech, point)
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
          f"a diagnostic (X25), PT is the reference; wire load: {wl['wire_cap_nets']} nets with wire capacitance, "
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
    print(f"setup-check {tech}: done; the differences go into the run note (X25)")
    return 0


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
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("-j", type=int, default=0, help="at most this many workers (default: from the licences)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("setup-check", help="diagnostic: PT against DC with forced activity, per power group (X25)")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--source", choices=list(SOURCES), default="hls")
    p.add_argument("--point", default=None, help=f"default per source: {SETUP_POINTS}")
    p.set_defaults(fn=cmd_setup_check)
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
