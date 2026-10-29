#!/usr/bin/env python3
"""sim/pwr.py - dynamic energy of mapped netlists from simulated activity (docs/power.md).

  pixi run pwr tbjson      POINT
  pixi run pwr run         PATTERN ... --tech T [--stim rand64|forge] [--size TAG|all] [--seed N] [-j N]
  pixi run pwr setup-check --tech T [--point P]
  pixi run pwr summary     [PATTERN ...] [--tech T]

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
setup-check: every power group within 0.1%, nangate15's combinational within 2.5% (X10).

Environment, all optional:
  PT_SHELL   pt_shell (else PATH)          LMUTIL    lmutil (else PATH)
  SIM_HLS    ../hls-exercises              vcd2saif  from PATH, else next to pt_shell
  vlib, vlog, vopt, vsim from PATH; dc_shell (setup-check) from DC_SHELL or PATH.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

SIM = Path(__file__).resolve().parent
ROOT = SIM.parent
sys.path.insert(0, str(SIM))
from sources import hls  # noqa: E402
from ref import ref  # noqa: E402

_spec = importlib.util.spec_from_file_location("syn_driver", ROOT / "syn" / "syn.py")
syn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(syn)

RUNS = SIM / "runs"
SYN_RUNS = ROOT / "syn" / "runs" / "hls"
RESULTS = ROOT / "results" / "hls"
TB_DIR = SIM / "tb"
TB_FILES = ["ap_ctrl_hs_seq.sv", "axis_src.sv", "axis_sink.sv"]
PT_SCRIPT = SIM / "scripts" / "pt_power.tcl"
RUN_DO = SIM / "scripts" / "run.do"
DC_READBACK = SIM / "probe" / "dc_readback.tcl"
TB_TOP, DUT = "tb", "dut"
CLOCK_NS = 10.0
SETUP_POINT = "done/vecadd/opt_w8"
SETUP_TOL = 1e-3            # setup-check: every power group within 0.1% ...
# ... except where PT and DC are known to differ on a library feature, not on the setup (docs X10):
# nangate15's non-switching internal power on inverting multi-input cells (PITFALLS PT5). PT is the reference.
SETUP_TOL_GROUP = {("nangate15", "combinational"): 2.5e-2}
MIN_ANNOTATED = 99.0        # percent of nets annotated from the SAIF
TOGGLE_BEATS = 64           # the input-toggle check fails a run from this many beats up
# Questa cell models, next to each technology's .db, with the vlog options they need
CELL_MODELS = {"nangate45": ("NangateOpenCellLibrary.v", []),
               "nangate15": ("NanGate_15nm_OCL_functional.v", ["-timescale", "1ns/1ps"])}
COLUMNS = ["point", "top", "tech", "clock_ns", "W", "size", "config", "beats", "seed", "cycles",
           "e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "p_dyn_uw",
           "e_comb_fire_pj", "e_flop_fire_pj", "e_run_pj", "flop_bits", "e_bit_pj", "status"]
MODULE_COLUMNS = ["point", "tech", "path", "design", "e_dyn_pj"]
KEPT = ("power.rpt", "power_hierarchy.rpt", "switching_activity.rpt")
LICENCE_ERR = re.compile(r"(?i)(licen[sc]\w*\s+(error|fail\w*|not available|denied|checkout)|unable to check\s*out"
                         r"|could not check\s*out|cannot check\s*out|feature removed|license server)")
MASK64 = (1 << 64) - 1


class Fail(Exception):
    """A check that fails the run: str(e) is the status after 'failed: '."""


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


def scopes(netlist: Path, top: str) -> list[str]:
    """Instance paths below the top that are designs of the netlist (sub-designs, not cells)."""
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
                walk(m, p)
    walk(top, [])
    return [".".join(x if not x.startswith("\\") else x + " " for x in p) for p in out]


def tb_top(tb: dict, netlist: Path) -> str:
    """The thin per-point top: tb.json's ports wired to the fixed modules of sim/tb/."""
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
def saif_check(saif: Path, cycles: int) -> dict:
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
    clk = [n for n in nets if n[0] == "ap_clk"]
    info = {"entries": entries, "nets": len(driven), "z_nets": len(z_nets), "duration": dur, "unit_s": unit,
            "bad_nets": len(bad), "tx_nets": sum(1 for n in driven if n[3]), "clk_tc": clk[0][5] if clk else None}
    if len(nets) != entries:
        raise Fail(f"saif: parsed {len(nets)} of {entries} entries")
    if bad:
        raise Fail(f"saif: T0 + T1 + TX != DURATION on {len(bad)} driven nets")
    if dur != want:
        raise Fail(f"saif: DURATION {dur} is not {cycles} cycles ({want})")
    if not clk or clk[0][5] != 2 * cycles:
        raise Fail(f"saif: ap_clk TC {info['clk_tc']}, expected {2 * cycles}")
    return info


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
    steps = [("vlog_tb", [tool("vlog"), "-sv", "-work", str(work), *(str(TB_DIR / f) for f in TB_FILES),
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
    row.update({"config": " ".join(f"{k}={v}" for k, v in cfg.items()), "beats": cfg["loop_count"]})
    info = {"run": str(rdir.relative_to(ROOT)), "times": times}

    t = time.time()
    st = stimulus(tb, size, stim, seed)
    plus = []
    for s in tb["streams"]:
        x = st["ins"][s["arg"]] if s["dir"] == "in" else st["outs"][s["arg"]]
        f = rdir / "stim" / f"{s['arg']}.hex"
        f.write_text(beats_hex(x, s["lanes"]))
        plus += [f"+{s['arg']}_HEX={f}", f"+{s['arg']}_BEATS={len(x) // s['lanes']}"]
    for p in tb["pins"]:
        plus.append(f"+PIN_{p['port']}={st['pins'][p['port']] & ((1 << p['bits']) - 1):x}")
    (rdir / "stim" / "pins.json").write_text(json.dumps(st["pins"], indent=1) + "\n")
    info["untoggled_bits"] = st["untoggled"]
    exp, how = expected_cycles(tb, size)
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
    info["saif"] = saif_check(saif, cycles)
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
    if ann < MIN_ANNOTATED / 100 * total:
        raise Fail(f"pt: {ann} of {total} nets annotated, under {MIN_ANNOTATED:g}%")
    groups = pt_groups(ptd)
    info["modules"] = pt_hierarchy(ptd)
    energy_row(row, groups, flop_bits_of(tech, tb["point"]))
    row["status"] = "ok"
    return info


def do_point(point: str, tech: str, runs: list, threads: int) -> list[tuple[dict, dict]]:
    """One worker: tb.json, compile, every requested run, cleanup. Returns [(row, info)]."""
    pdir = RUNS / tech / point
    out = []
    try:
        fl = hls.filelist(point)
        if fl["rams"]:
            row = {c: "" for c in COLUMNS}
            row.update({"point": point, "top": fl["top"], "tech": tech, "clock_ns": _num(CLOCK_NS), "size": "",
                        "seed": "", "status": f"skipped: needs a RAM macro ({', '.join(fl['rams'])}); "
                                              f"{tech} has no RAM cells, RAM1 builds one (OpenRAM)"})
            return [(row, {})]
        tb = hls.build(point)
        hls.check(tb)
    except (ValueError, KeyError, FileNotFoundError) as e:
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
            compile_point(tb, tech, pdir, netlist, RUNS / tech / "_cells")
            compile_err = None
        except Fail as e:
            compile_err = str(e)
        compile_times["compile"] = time.time() - t
        expanded = []
        for size, stim, seed in runs:     # --size all: every size in the point's sizes.txt
            sizes = hls.sizes_txt(point) if size == "all" else [size or hls.default_size(tb)]
            expanded += [(z, stim, seed) for z in sizes]
        for size, stim, seed in expanded:
            times = dict(compile_times) if not out else {}
            base = {c: "" for c in COLUMNS}
            base.update({"point": point, "top": tb["top"], "tech": tech, "clock_ns": _num(CLOCK_NS), "W": tb["W"],
                         "size": size, "seed": "forge" if stim == "forge" else seed})
            info = {"run": str((pdir / run_tag(size, stim, seed)).relative_to(ROOT)), "times": times,
                    "default": (stim, seed, size) == ("rand64", 0, hls.default_size(tb))}
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
    _merge(out / "power_pt.csv", COLUMNS, key, rows, {key(r) for r in rows})
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


# ---------------------------------------------------------------- commands
def cmd_tbjson(args) -> int:
    tb = hls.build(args.point)
    hls.check(tb)
    print(json.dumps(tb, indent=1))
    return 0


def cmd_run(args) -> int:
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
    (RUNS / args.tech).mkdir(parents=True, exist_ok=True)
    with (RUNS / args.tech / "batches.jsonl").open("a") as fh:
        fh.write(json.dumps({"date": stamp, "patterns": args.patterns, "stim": args.stim, "size": args.size,
                             "seed": args.seed, "licences": lic, "nproc": nproc, "J": j, "threads": threads}) + "\n")
    t = time.time()
    cells_lib(args.tech)
    print(f"pwr: cell models compiled in {time.time() - t:.1f} s", flush=True)
    runs = [(args.size, args.stim, args.seed)]
    results = []

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
    print(f"pwr: {len(results) - len(bad)} ok, {len(bad)} not ok -> results/hls/{args.tech}/power_pt.csv")
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
    """X10: PT and DC on the same netlist with the same forced activity agree per power group."""
    point, tech = args.point, args.tech
    base = RUNS / tech / "setup_check" / point
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
    pt, dc = pt_groups(base / "pt" / "reports"), dc_groups(base / "dc" / "reports" / "power.rpt")
    ok, table = True, []
    print(f"setup-check {tech} {point}: uniform activity, PT against DC (PT {t_pt:.1f} s, DC {t_dc:.1f} s)")
    print(f"{'group':<14} {'PT dyn uW':>12} {'DC dyn uW':>12} {'diff %':>8} {'PT leak uW':>12} {'DC leak uW':>12} {'diff %':>8} {'tol %':>6}")
    for g in syn.POWER_GROUPS:
        pd, dd = pt[g][0] + pt[g][1], dc[g][0] + dc[g][1]
        pl, dl = pt[g][2], dc[g][2]

        def rel(a, b):
            return 0.0 if max(abs(a), abs(b)) < 1e-9 else (a - b) / b if b else float("inf")
        rd, rl = rel(pd, dd), rel(pl, dl)
        tol = SETUP_TOL_GROUP.get((tech, g), SETUP_TOL)
        good = abs(rd) <= tol and abs(rl) <= tol
        ok &= good
        table.append({"group": g, "pt_dyn_uw": pd, "dc_dyn_uw": dd, "dyn_diff": rd, "pt_leak_uw": pl,
                      "dc_leak_uw": dl, "leak_diff": rl, "tol": tol, "ok": good})
        print(f"{g:<14} {pd:12.6g} {dd:12.6g} {100 * rd:8.4f} {pl:12.6g} {dl:12.6g} {100 * rl:8.4f} {100 * tol:6g}"
              f"{'' if good else '  FAIL'}")
    (base / "check.json").write_text(json.dumps({"tech": tech, "point": point, "ok": ok, "groups": table,
                                                 "pt_s": t_pt, "dc_s": t_dc}, indent=1) + "\n")
    print(f"setup-check {tech}: {'PASS' if ok else 'FAIL'} (every group within its tolerance: {100 * SETUP_TOL:g}%"
          + "".join(f", {g} {100 * v:g}%" for (t_, g), v in SETUP_TOL_GROUP.items() if t_ == tech) + ")")
    return 0 if ok else 1


def cmd_summary(args) -> int:
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
    p.set_defaults(fn=cmd_tbjson)
    p = sub.add_parser("run", help="simulate and run PrimePower on points")
    p.add_argument("patterns", nargs="+")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--stim", default="rand64", choices=["rand64", "forge"])
    p.add_argument("--size", default=None,
                   help="a tb.json size tag (default b64, rowsum m8_n64), or 'all': every size in the point's sizes.txt")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("-j", type=int, default=0, help="at most this many workers (default: from the licences)")
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("setup-check", help="PT and DC with forced activity agree per power group (X10)")
    p.add_argument("--tech", required=True, choices=syn.tech_names())
    p.add_argument("--point", default=SETUP_POINT)
    p.set_defaults(fn=cmd_setup_check)
    p = sub.add_parser("summary", help="print power_pt.csv")
    p.add_argument("patterns", nargs="*")
    p.add_argument("--tech", choices=syn.tech_names())
    p.set_defaults(fn=cmd_summary)
    args = ap.parse_args()
    if args.cmd == "run" and args.stim == "forge" and not args.size:
        sys.exit("--stim forge needs --size <cosim size> (validation only)")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
