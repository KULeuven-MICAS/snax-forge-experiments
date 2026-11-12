#!/usr/bin/env python3
"""cluster/power.py - the cluster's dynamic energy per program section (PWR1), `pixi run cluster pwr <point>`.

  pixi run cluster pwr <point> [--allow-branch]

Part 1 (R1): the quiet build (sw/forge_quiet.elf of rtl/cluster/<point>.zip, snax-forge D135) on step 3's netlist
with our own vsim command and do-file, which dump a VCD of the cluster's design scopes and log every change of the
wrapper's obs_o (the program section's mark, sw/obs_marks.json); the log is turned into one window per section, every
window is cut from the VCD in one pass, vcd2saif makes a SAIF of each cut, and each SAIF is checked (X8, X9, X32).
Part 2 (PT, R2) reads the SAIFs from the point's zip. snax-forge, snax_cluster and snax-gvsoc are read, never changed.

tb_bin's clock is 1 ns (TCK = 1ns, -t 1ps), the flow's clock 10 ns (X2, X9's CLOCK_NS, PT's constraints.sdc). The
activity of a zero-delay run does not depend on the period, so each cut's header gets `$timescale 10ps $end` in place
of Questa's 1ps: every time reads ten times longer, as if the run were at 10 ns (draft X76), and X9's checks and PT's
clock hold unchanged.

  1. checks before anything runs, as gls: the repos (clean, snax_cluster on origin/main unless --allow-branch); step 1
     (rtl/check.json) and step 3 (gls/check.json) PASS; the netlist in syn/runs/cluster/nangate45/<point>.zip; the
     bundle zip's forge.elf the one the steps used; sw/forge_quiet.elf's sha256 equal to provenance's
     quiet_elf_sha256; no RTL change in snax_cluster between the netlist's commit and HEAD (cluster.rtl_changes)
  2. in tmp/cluster/<point>/, as gls: the bundle and the netlist unpacked; image: make clean-generated clean-vsim,
     rtl-gen; clustergen --memories; cluster/mem.py, whose tc_sram_impl.sv must equal step 1's; the cell models
     (pwr.cell_model); vsim_preparation in the image and snax-forge-sim SIM=vsim on the host with gls's options
     (SRAM_IMPL, SRAM_MODELS, SIM_TYPE=gate_level_sim, GLS_NETLIST, GLS_CELLS), Questa's peak memory sampled
     (cluster.Peak). No snax-forge-run. vopt and vlog are checked as gls's swap check (cluster.swap_check).
  3. the vsim command: bin/snitch_cluster.vsim's vsim line, its one `-do "log -r /*; run -a"` (VSIM_FLAGS) replaced by
     `-do <work>/pwr/pwr.do`, -batch where snax-forge-run puts it ($3), the quiet ELF as the binary ($1, realpath)
     and $2 empty; written to pwr/vsim_cmd.sh and run from target/snitch_cluster, its output in pwr/vsim.txt. It
     passes with `[SUCCESS] Program finished successfully` and no program output (no line outside Questa's `#`
     transcript but fesvr's).
  4. pwr/pwr.do: onbreak {resume}, onfinish stop; `vcd file pwr/dut.vcd` and pwr/vcd_add.do (sourced): one
     non-recursive `vcd add` per design scope (X8: designs, not cells; LIB2), the wrapper's own nets, then every path
     of pwr.scopes(netlist, top) under the wrapper's instance, each in braces with its escaped identifiers kept
     (PITFALLS Q15); a `when` on the wrapper's obs_o (a port, visible under +acc=n, Q16) writes `<ps> <value>` per
     change to pwr/obs_log.txt, flushed, and at the check's mark runs `vcd off` and `vcd flush`; the run goes on to
     the program's exit. The dump runs from time 0 (a `when` can only turn it on at the mark's edge, a quarter cycle
     after the window opens). `run -all`, `quit -f`; no `log`, no `power` (X8, X18). The windows come from obs_o
     only (X73).
  5. the windows (pwr/windows.json): the marks of obs_log.txt in order, each once, from the legend's first up to the
     check's mark; section k from t_k - 250 ps to t_{k+1} - 250 ps (a quarter cycle before the edge where its mark
     appears, a time with no events), (t_{k+1} - t_k) / 1000 cycles, a non-integer count failing. Each window's
     cycles against CORE1 R2's quiet vsim run on the RTL (REF_CYCLES); beyond REF_TOL on any window the run stops.
  6. the cut: one pwr.vcd_windows pass over dut.vcd for every window, the cuts' $timescale 10ps (timescale_10ps;
     the VCD's must be 1ps), the window bounds the ps numbers; dut.vcd deleted right after the pass, whatever the
     result (X18), its size recorded first.
  7. vcd2saif per window as pwr.py's char source (-instance tb_bin/i_dut/i_snax_forge_cluster -time t0 t1), each cut
     deleted after its vcd2saif; at most min(nproc, windows) jobs at once, with no more cuts on disk than jobs; then
     pwr.saif_check(saif, cycles, "clk_i") per window (DURATION = cycles x 10 ns, clk_i TC = 2 x cycles).
  8. under pwr/ of sim/runs/cluster/nangate45/<point>.zip (other members kept): pwr.do, vcd_add.do, vsim_cmd.sh,
     vsim.txt, obs_log.txt, windows.json, <mark>_<kind>/w.saif and vcd2saif.log per window, logs/,
     check.json; also on a failure. Then vsim.wlf (none expected) dropped, tmp/cluster/<point>/ deleted, make
     clean-vsim clean-generated in snax_cluster. The SAIFs live only in this zip (sim/runs/ is git-ignored, X18).
One line at the end; a failure names the check or step and prints at most 30 lines of its log.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import resource
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cluster as cl  # noqa: E402  cluster/cluster.py: the steps' helpers (also puts sim/, arc/ ... on sys.path)

arc, check, mem = cl.arc, cl.check, cl.mem
import pwr  # noqa: E402  sim/pwr.py: scopes, vcd_windows, saif_check, cell_model, tool

ROOT, TB_DIR, TECH, TAIL = cl.ROOT, cl.TB_DIR, cl.TECH, cl.TAIL
TB_TOP = "tb_bin/i_dut/i_snax_forge_cluster"        # the wrapper's instance in the testbench (vcd2saif -instance)
WRAP = "/" + TB_TOP                                  # its vsim path
TOP = "snax_forge_cluster_wrapper"
CLOCK_PS = 1000                                      # tb_bin's TCK = 1ns at -t 1ps
QUIET = CLOCK_PS // 4                                # a window opens a quarter cycle before its mark's rising edge
SAIF_CLOCK = "clk_i"
OLD_DO = '-do "log -r /*; run -a"'                  # VSIM_FLAGS' do (target/snitch_cluster/Makefile)
# CORE1 R2's quiet vsim run on the RTL (snax-forge out/core1-r2/obs_log.txt, results in its run note): cycles per mark
REF_CYCLES = {"dot3_w16": {1: 305, 2: 291, 3: 32, 4: 11, 5: 185, 6: 77}}
REF_TOL = 0.10                                       # D171's rule
RUN_TIMEOUT = 4 * 3600
TIMEOUT = {"pwr_vsim_preparation": 1800, "pwr_snax-forge-sim": 4 * 3600}
FESVR = "[fesvr] "


# ---------------------------------------------------------------- pure helpers (cluster/test_power.py)
def components(scope: str) -> list[str]:
    """A dotted instance path of pwr.scopes as its components; an escaped identifier (from its backslash to the
    space that ends it, dots inside it its own) stays whole, backslash and trailing space kept."""
    out, i = [], 0
    while i < len(scope):
        if scope[i] == "\\":
            j = scope.find(" ", i)
            if j < 0:
                raise ValueError(f"escaped identifier with no ending space in {scope!r}")
            j += 1
        else:
            j = scope.find(".", i)
            j = len(scope) if j < 0 else j
        out.append(scope[i:j])
        if j < len(scope) and scope[j] != ".":
            raise ValueError(f"no '.' after {scope[i:j]!r} in {scope!r}")
        i = j + 1
    return out


def vsim_path(scope: str) -> str:
    """The scope under the wrapper as vsim names it: '/' between components, escaped ones kept as they are."""
    return WRAP + "".join("/" + c for c in components(scope))


def vcd_add_lines(scopes: list[str]) -> list[str]:
    """One non-recursive `vcd add` per design scope: the wrapper's own nets, then each scope; every path in braces
    (Tcl does not substitute in them: an escaped identifier keeps its backslash, brackets and trailing space)."""
    return [f"vcd add {{{WRAP}/*}}"] + [f"vcd add {{{vsim_path(s)}/*}}" for s in scopes]


def vsim_command(script: str, do_file: Path, elf: Path) -> str:
    """bin/snitch_cluster.vsim's text with its one VSIM_FLAGS do replaced by ours, -batch for $3 (where snax-forge-run
    puts it), the ELF for $1 (realpath, as the script's `binary=$(realpath $1)`) and $2 empty (snax-forge-run's "")."""
    for old, n in ((OLD_DO, script.count(OLD_DO)), ("$(realpath $1)", script.count("$(realpath $1)")),
                   (" $3 ", script.count(" $3 ")), ("++$2", script.count("++$2"))):
        if n != 1:
            raise ValueError(f"{old!r} appears {n} times in bin/snitch_cluster.vsim, not once")
    out = script.replace(OLD_DO, f"-do {shlex.quote(str(do_file))}")
    out = out.replace("$(realpath $1)", shlex.quote(str(Path(elf).resolve())))
    out = out.replace(" $3 ", " -batch ")
    return out.replace("++$2", "++")


def obs_marks(marks: list[dict]) -> tuple[list[dict], dict]:
    """The legend's marks up to the check's (the span plus its end) and the check's entry."""
    checks = [m for m in marks if m["kind"] == "check"]
    if len(checks) != 1:
        raise ValueError(f"obs_marks.json has {len(checks)} entries of kind check, not one")
    upto = [m for m in marks if m["mark"] <= checks[0]["mark"]]
    if [m["mark"] for m in upto] != list(range(upto[0]["mark"], checks[0]["mark"] + 1)) or upto[0]["mark"] != 1:
        raise ValueError(f"obs_marks.json's marks up to the check are not 1, 2, ...: {[m['mark'] for m in upto]}")
    return upto, checks[0]


def obs_changes(text: str) -> list[tuple[int, str]]:
    """obs_log.txt's `<ps> <value>` lines, one per time (the last value at a time step: a bus may pass through
    other values within one step)."""
    out: dict[int, str] = {}
    for ln in text.splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        t, v = ln.split()
        out[int(t)] = v
    return sorted(out.items())


def windows(text: str, marks: list[dict]) -> list[dict]:
    """The span's windows from obs_log.txt: the legend's marks in order, each once, from 1 up to the check's mark
    (values before mark 1 are the boot's; after the check's mark the log is not read). Section k's window runs from
    t_k - QUIET to t_{k+1} - QUIET ps, (t_{k+1} - t_k) / CLOCK_PS cycles, which must be whole."""
    upto, chk = obs_marks(marks)
    want = [str(m["mark"]) for m in upto]
    seen: list[tuple[int, int]] = []
    for t, v in obs_changes(text):
        if not seen:
            if v not in want:
                continue                    # the boot (0, or X before reset)
            if v != want[0]:
                raise ValueError(f"mark {v} at {t} ps before mark {want[0]}")
        else:
            k = len(seen)
            if v in want[:k]:
                raise ValueError(f"mark {v} again at {t} ps (after mark {want[k - 1]})")
            if v != want[k]:
                raise ValueError(f"mark {want[k]} missing: {v} at {t} ps after mark {want[k - 1]}")
        seen.append((int(v), t))
        if int(v) == chk["mark"]:
            break
    if not seen or seen[-1][0] != chk["mark"]:
        got = seen[-1][0] if seen else None
        raise ValueError(f"the log ends before the check's mark {chk['mark']} (last mark {got})")
    by = {m["mark"]: m for m in upto}
    out = []
    for (k, tk), (_, tn) in zip(seen, seen[1:]):
        cyc = (tn - tk) / CLOCK_PS
        if cyc != int(cyc):
            raise ValueError(f"mark {k}: {tn - tk} ps from its edge to the next mark's is not whole cycles")
        t0, t1 = tk - QUIET, tn - QUIET
        out.append({"mark": k, "kind": by[k]["kind"], "label": by[k]["label"], "t_mark_ps": tk, "t0_ps": t0,
                    "t1_ps": t1, "cycles": int(cyc), "cut_t0": t0, "cut_t1": t1, "cut_unit": "10ps"})
    return out


def against_ref(wins: list[dict], ref: dict[int, int] | None) -> tuple[bool, list[dict]]:
    """Each window's cycles against CORE1 R2's (REF_CYCLES), the difference and its share; ok within REF_TOL."""
    rows, ok = [], True
    for w in wins:
        r = (ref or {}).get(w["mark"])
        d = None if r is None else w["cycles"] - r
        share = None if r is None else d / r
        ok &= r is None or abs(share) <= REF_TOL
        rows.append({"mark": w["mark"], "kind": w["kind"], "cycles": w["cycles"], "ref": r, "diff": d,
                     "share": None if share is None else round(share, 4)})
    return ok, rows


def program_output(text: str) -> list[str]:
    """The run's lines outside Questa's `#` transcript but fesvr's: the program's own output."""
    return [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#") and not ln.startswith(FESVR)]


def do_file(pdir: Path, check_mark: int) -> str:
    q = lambda p: "{" + str(p) + "}"   # noqa: E731
    L = ["# PWR1 part 1 (cluster/power.py): the VCD of the cluster's design scopes, obs_o's changes",
         "onbreak {resume}", "onfinish stop",
         f"vcd file {q(pdir / 'dut.vcd')}",
         f"source {q(pdir / 'vcd_add.do')}",
         f"set obs_sig {q(WRAP + '/obs_o')}",
         f"set check_mark {check_mark}",
         "set vcd_on 1",
         f"set obs_f [open {q(pdir / 'obs_log.txt')} w]",
         "when -label obs $obs_sig {",
         "  set v [examine -radix unsigned $obs_sig]",
         '  puts $obs_f "$now $v"',
         "  flush $obs_f",
         "  if {$vcd_on && [string equal $v $check_mark]} {",
         "    vcd off",
         "    vcd flush",
         "    set vcd_on 0",
         '    echo "pwr: vcd off at $now (mark $v)"',
         "  }",
         "}",
         'echo "pwr: run from $now"',
         "run -all",
         'echo "pwr: run ended at $now"',
         "close $obs_f",
         "quit -f"]
    return "\n".join(L) + "\n"


def vcd_header_counts(vcd: Path) -> dict:
    """The VCD header's $scope and $var lines and its $timescale."""
    scopes = vars_ = 0
    head = []
    with vcd.open() as f:
        for ln in f:
            s = ln.lstrip()
            if s.startswith("$scope"):
                scopes += 1
            elif s.startswith("$var"):
                vars_ += 1
            if len(head) < 40:
                head.append(ln)
            if s.startswith("$enddefinitions"):
                break
    m = re.search(r"\$timescale\s+(\d+\s*\w+)\s+\$end", "".join(head))
    return {"scopes": scopes, "vars": vars_, "timescale": m.group(1) if m else None}


# ---------------------------------------------------------------- the step
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def preflight(p: dict, images: dict, args) -> dict:
    """Step 1's checks: the repos, steps 1 and 3 PASS, the netlist, the ELFs, no RTL change since the netlist."""
    repos = cl.check_repos(args.allow_branch)
    images = {**images, "snax_cluster_id": cl.image_id(images["snax_cluster"])}
    point = p["point"]
    step1 = cl.RUN_ZIPS / f"{point}.zip"
    for m in ("rtl/check.json", "rtl/tc_sram_impl.sv", "gls/check.json"):
        if not arc.has(step1, m):
            sys.exit(f"no {m} in {step1.relative_to(ROOT)}: run pixi run cluster rtl and gls {point} first")
    rtl_res = json.loads(arc.read(step1, "rtl/check.json"))
    gls_res = json.loads(arc.read(step1, "gls/check.json"))
    for name, r in (("step 1 (rtl)", rtl_res), ("step 3 (gls)", gls_res)):
        if r.get("status") != "PASS":
            sys.exit(f"{name} of {point} is {r.get('status')} ({step1.relative_to(ROOT)}), not PASS")
    cl.synpy.use_source("cluster")
    synz = cl.synpy.run_zip(TECH, point, cl.synpy.DEFAULT_CLOCK)
    if not arc.has(synz, cl.NETLIST):
        sys.exit(f"no {cl.NETLIST} in {synz.relative_to(ROOT)}: run pixi run cluster syn {point} first")
    dc = json.loads(arc.read(synz, "tech.json"))["resolved"]["cluster"]
    z = cl.RTL_ZIPS / f"{point}.zip"
    prov = json.loads(arc.read(z, "provenance.json"))
    shas = {"bundle": prov["elf_sha256"], "step 1": rtl_res["bundle"]["elf_sha256"], "step 2": dc["elf_sha256"],
            "step 3": gls_res["elf_sha256"], "bundle zip's sw/forge.elf": sha(arc.read(z, "sw/forge.elf"))}
    if len(set(shas.values())) != 1:
        sys.exit(f"forge.elf differs between the bundle zip and the steps: {shas}")
    for m in ("sw/forge_quiet.elf", "sw/obs_marks.json"):
        if not arc.has(z, m):
            sys.exit(f"no {m} in {z.relative_to(ROOT)}: the quiet build (snax-forge D135); run cluster rtl again")
    quiet = sha(arc.read(z, "sw/forge_quiet.elf"))
    if quiet != prov.get("quiet_elf_sha256"):
        sys.exit(f"sw/forge_quiet.elf's sha256 {quiet[:16]} is not provenance's quiet_elf_sha256 "
                 f"{str(prov.get('quiet_elf_sha256'))[:16]}")
    netlist_sha = sha(arc.read(synz, cl.NETLIST))
    if gls_res.get("netlist", {}).get("sha256") != netlist_sha:
        sys.exit(f"the netlist in {synz.relative_to(ROOT)} is not the one step 3 ran")
    changed = cl.rtl_changes(dc["snax_cluster_commit"])
    if changed:
        sys.exit(f"snax_cluster changed RTL between the netlist's commit {dc['snax_cluster_commit'][:12]} and HEAD "
                 f"{repos['snax_cluster'][:12]}:\n  " + "\n  ".join(changed))
    cells = pwr.cell_model(TECH)
    if not cells.is_file():
        sys.exit(f"no cell models at {cells}")
    return {"repos": repos, "images": images, "step1": step1, "synz": synz, "dc": dc, "z": z, "prov": prov,
            "netlist_sha": netlist_sha, "quiet_sha": quiet, "cells": cells}


def build(work: Path, steps, pre: dict) -> tuple[Path, Path, str]:
    """Step 2: the netlist build as gls (rtl-gen, clustergen, mem.py, vsim_preparation, snax-forge-sim)."""
    q = shlex.quote
    cl.unpack(pre["z"], work)
    netlist = work / "netlist" / Path(cl.NETLIST).name
    netlist.parent.mkdir()
    netlist.write_bytes(arc.read(pre["synz"], cl.NETLIST))
    cfg = work / "bundle" / "snax_forge.hjson"
    steps.image("rtl-gen", "snax_cluster", TB_DIR,
                f"make clean-generated clean-vsim\nmake rtl-gen CFG_OVERRIDE={q(str(cfg))}", cl.TIMEOUT["rtl-gen"])
    steps.image("clustergen", "snax_cluster", TB_DIR,
                f"python3 {q(str(cl.SC / 'util' / 'clustergen.py'))} -c {q(str(cfg))} -o {q(str(work))} --memories",
                cl.TIMEOUT["clustergen"])
    made = mem.make(work / "memories.json", work / "mem")
    impl = work / "mem" / "tc_sram_impl.sv"
    if impl.read_bytes() != arc.read(pre["step1"], "rtl/tc_sram_impl.sv"):
        raise cl.Stop(f"{impl} differs from step 1's rtl/tc_sram_impl.sv in {pre['step1'].relative_to(ROOT)}")
    print("  tc_sram_impl.sv               equals step 1's; " + "; ".join(
        f"{m['name']} ({'cached' if m.get('cached') else 'made'})" for m in made["macros"]), flush=True)
    cells = pre["cells"]
    opts = (f" SRAM_IMPL={q(str(impl))} SRAM_MODELS={q(str(work / 'mem' / 'sram_models.f'))}"
            f" SIM_TYPE=gate_level_sim GLS_NETLIST={q(str(netlist))} GLS_CELLS={q(str(cells))}")
    watch = [("vlog", str(netlist), "vlog netlist"), ("vlog", str(cells), "vlog cells"),
             ("vsim", "compile.vsim.tcl", "vsim compile"), ("vsim", "tb_bin_opt", "vsim run")]
    steps.image("pwr_vsim_preparation", "snax_cluster", TB_DIR, f"make vsim_preparation CFG_OVERRIDE={q(str(cfg))}{opts}",
                TIMEOUT["pwr_vsim_preparation"])
    steps.host("pwr_snax-forge-sim", TB_DIR, f"make snax-forge-sim SIM=vsim CFG_OVERRIDE={q(str(cfg))}{opts}",
               TIMEOUT["pwr_snax-forge-sim"], watch)
    return netlist, cfg, opts


def saif_jobs(vcd: Path, wins: list[dict], pdir: Path, res: dict) -> None:
    """Steps 6 and 7: one cut pass, vcd2saif per window (at most j jobs, no more cuts on disk than jobs), the checks."""
    j = max(1, min(os.cpu_count() or 1, len(wins)))
    vcd2saif = pwr.tool("vcd2saif")
    names = {f"{w['mark']}_{w['kind']}": w for w in wins}
    cuts = {n: pdir / n / "cut.vcd" for n in names}
    for n in names:
        (pdir / n).mkdir(exist_ok=True)
    slots = threading.Semaphore(j)
    futs = {}
    secs: dict[str, float] = {}

    def job(n: str) -> int:
        w, t = names[n], time.monotonic()
        try:
            return pwr.run_tool([vcd2saif, "-input", str(cuts[n]), "-output", str(pdir / n / "w.saif"),
                                 "-instance", TB_TOP, "-time", str(w["cut_t0"]), str(w["cut_t1"])],
                                pdir / n / "vcd2saif.log", pdir / n, stdin_null=True)
        finally:
            cuts[n].unlink(missing_ok=True)        # X18: each cut at once
            secs[n] = round(time.monotonic() - t, 1)
            slots.release()

    order = [n for n in sorted(names, key=lambda n: names[n]["cut_t0"])]
    left = list(order)

    def done(n: str) -> None:                     # a cut closed: its vcd2saif starts; the next cut waits for a slot
        futs[n] = ex.submit(job, n)
        left.remove(n)
        if left:
            slots.acquire()

    ex = ThreadPoolExecutor(j)
    t = time.monotonic()
    try:
        slots.acquire()
        pwr.vcd_windows(vcd, [(n, names[n]["cut_t0"], names[n]["cut_t1"]) for n in order], cuts,
                        timescale_10ps=True, done=done)
    finally:
        res["seconds"]["cut"] = round(time.monotonic() - t, 1)
        res["cut_maxrss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
        vcd.unlink(missing_ok=True)                # X18: the VCD goes right after the pass, whatever the result
        print(f"  cut pass                      {res['seconds']['cut']:.0f} s, {len(futs)} of {len(order)} cuts; "
              f"dut.vcd deleted", flush=True)
        ex.shutdown(wait=True)
        for c in cuts.values():
            c.unlink(missing_ok=True)
        res["seconds"]["vcd2saif"] = dict(secs)
    res["vcd2saif_jobs"] = j
    bad = [n for n in order if n not in futs or futs[n].result() != 0 or not (pdir / n / "w.saif").is_file()]
    if bad:
        raise cl.StepFailed(f"vcd2saif {bad[0]}", pdir / bad[0] / "vcd2saif.log", "no SAIF or nonzero exit")
    res["saif"] = {}
    for n in order:
        w, t = names[n], time.monotonic()
        try:
            info = pwr.saif_check(pdir / n / "w.saif", w["cycles"], SAIF_CLOCK)
            info["status"] = "PASS"
        except pwr.Fail as e:
            info = {"status": "FAIL", "why": str(e)}
        info["bytes"] = (pdir / n / "w.saif").stat().st_size
        info["check_s"] = round(time.monotonic() - t, 1)
        res["saif"][n] = info
        print(f"  {n:<29s} SAIF {info['bytes'] / 1e6:.1f} MB, vcd2saif {secs.get(n, 0):.0f} s, check {info['status']}"
              + (f" ({info['why']})" if info["status"] != "PASS" else
                 f": {info['nets']} nets, {info['z_nets']} at Z, {info['tx_nets']} with X, clk TC {info['clk_tc']}"),
              flush=True)


def part1(p: dict, images: dict, args) -> dict:
    """Part 1: the quiet netlist run, the windows, the SAIFs, packed under pwr/ of the point's zip. Returns the
    check.json it packed; R2's PT reads the SAIFs from the zip and can skip this when pwr/check.json is PASS."""
    pre = preflight(p, images, args)
    repos, images, point = pre["repos"], pre["images"], p["point"]
    marks = json.loads(arc.read(pre["z"], "sw/obs_marks.json"))
    upto, chk = obs_marks(marks)
    work = cl.TMP / point
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pdir = work / "pwr"
    pdir.mkdir()
    print(f"cluster pwr {point} (part 1): snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), "
          f"netlist of {pre['dc']['snax_cluster_commit'][:12]}, quiet ELF {pre['quiet_sha'][:12]}; marks "
          f"{upto[0]['mark']} to {chk['mark']} (check); work {work}", flush=True)
    steps = cl.Steps(work, images)
    t_all = time.monotonic()
    res = {"point": point, "tech": TECH, "part": 1, "status": "FAIL", "failed": None,
           "snax_cluster_commit": repos["snax_cluster"], "snax_cluster_branch": repos["snax_cluster_branch"],
           "snax_cluster_on_main": repos["snax_cluster_on_main"],
           "netlist_snax_cluster_commit": pre["dc"]["snax_cluster_commit"], "snax_forge_commit": repos["snax_forge"],
           "bundle_snax_forge_commit": pre["prov"]["snax_forge_commit"],
           "snax_forge_experiments_commit": cl.git(ROOT, "rev-parse", "HEAD").stdout.strip(),
           "netlist": {"zip": str(pre["synz"].relative_to(ROOT)), "member": cl.NETLIST, "sha256": pre["netlist_sha"]},
           "elf_sha256": pre["prov"]["elf_sha256"], "quiet_elf_sha256": pre["quiet_sha"], "cells": str(pre["cells"]),
           "images": {k: images[k] for k in ("snax_cluster", "snax_cluster_id")},
           "vcd2saif": None, "clock": {"tb_ps": CLOCK_PS, "flow_ns": pwr.CLOCK_NS, "cut_timescale": "10ps"},
           "seconds": {}, "obs_marks": marks}
    try:
        t = time.monotonic()
        netlist, cfg, opts = build(work, steps, pre)
        res["seconds"]["setup_and_build"] = round(time.monotonic() - t, 1)
        cell_names = set(re.findall(r"^\s*module\s+(\w+)", pre["cells"].read_text(errors="replace"), re.M))
        vopt, vlog = (cl._text(TB_DIR / "work-vsim" / f) for f in ("vopt.log", "vlog.log"))
        # the netlist took the RTL's place (gls's swap check; the run's [tc_sram_impl] prints are checked below)
        sw = cl.swap_check(vopt, vlog, "", netlist, cell_names)
        res["swap"] = {k: v for k, v in sw.items() if k != "vopt_command"}
        if sw["status"] != "PASS":
            raise cl.StepFailed("swap", TB_DIR / "work-vsim" / "vopt.log", f"the netlist build is not gls's: {res['swap']}")

        # step 3 and 4: the do-file, the scopes, the vsim command
        t = time.monotonic()
        scopes = pwr.scopes(netlist, TOP)
        adds = vcd_add_lines(scopes)
        (pdir / "vcd_add.do").write_text("\n".join(adds) + "\n")
        (pdir / "pwr.do").write_text(do_file(pdir, chk["mark"]))
        res["scopes"] = {"vcd_add": len(adds), "design_scopes": len(scopes),
                         "escaped": sum(1 for s in scopes if "\\" in s)}
        script = (TB_DIR / "bin" / "snitch_cluster.vsim").read_text()
        cmd = vsim_command(script, pdir / "pwr.do", work / "sw" / "forge_quiet.elf")
        (pdir / "vsim_cmd.sh").write_text(cmd)
        res["seconds"]["do_file"] = round(time.monotonic() - t, 1)
        print(f"  do-file                       {len(adds)} vcd add ({res['scopes']['escaped']} escaped scopes)", flush=True)
        vtxt = pdir / "vsim.txt"
        try:
            steps.host("pwr_vsim", TB_DIR, f"bash {shlex.quote(str(pdir / 'vsim_cmd.sh'))} > {shlex.quote(str(vtxt))} 2>&1",
                       RUN_TIMEOUT, [("vsim", "tb_bin_opt", "vsim run")])
        finally:
            run = cl._text(vtxt)
            res["questa_elapsed_s"] = cl.elapsed(run)
        out = program_output(run)
        res["run"] = {"success": check.success(run), "program_lines": out[:20], "tc_sram_impl_prints":
                      check.sram_lines(run), "no_objects": len(re.findall(r"vsim-3561|No objects found", run)),
                      "errors": re.findall(r"^# \*\* Error.*$", run, re.M)[:10]}
        if not res["run"]["success"] or out or res["run"]["tc_sram_impl_prints"] or res["run"]["no_objects"] \
                or res["run"]["errors"]:
            raise cl.StepFailed("run", vtxt, f"[SUCCESS] {res['run']['success']}, {len(out)} program lines, "
                                             f"{res['run']['no_objects']} 'no objects', {len(res['run']['errors'])} errors")
        print(f"  run                           [SUCCESS], no program output, Questa {res['questa_elapsed_s']} s",
              flush=True)

        # step 5: the windows
        obs = cl._text(pdir / "obs_log.txt")
        try:
            wins = windows(obs, marks)
        except ValueError as e:
            raise cl.StepFailed("windows", pdir / "obs_log.txt", str(e)) from None
        ok, cmp_rows = against_ref(wins, REF_CYCLES.get(point))
        res["windows"] = wins
        res["windows_ref"] = {"source": "CORE1 R2's quiet vsim run on the RTL (snax-forge out/core1-r2)",
                              "tol": REF_TOL, "rows": cmp_rows,
                              "status": "NONE" if point not in REF_CYCLES else "PASS" if ok else "FAIL"}
        (pdir / "windows.json").write_text(json.dumps(wins, indent=2) + "\n")
        for r in cmp_rows:
            print(f"  window {r['mark']} {r['kind']:<16s} {r['cycles']:5d} cycles, CORE1 R2 {r['ref']}, diff {r['diff']}",
                  flush=True)
        if not ok:
            raise cl.Stop(f"window cycles beyond {REF_TOL:.0%} of CORE1 R2's: {cmp_rows}")

        # steps 6 and 7: the cut, vcd2saif, the checks
        vcd = pdir / "dut.vcd"
        if not vcd.is_file():
            raise cl.StepFailed("run", vtxt, "no dut.vcd")
        res["vcd_bytes"] = vcd.stat().st_size
        h = res["vcd_header"] = vcd_header_counts(vcd)
        want = res["scopes"]["design_scopes"] + 3          # tb_bin, i_dut, the wrapper, then every design scope
        print(f"  dut.vcd                       {res['vcd_bytes'] / 1e9:.2f} GB, {h['vars']} $var, {h['scopes']} $scope "
              f"(want {want}), timescale {h['timescale']}", flush=True)
        if h["scopes"] != want:
            raise cl.StepFailed("vcd scopes", vtxt, f"{h['scopes']} $scope in dut.vcd, not {want}: a vcd add missed")
        res["vcd2saif"] = (subprocess.run([pwr.tool("vcd2saif"), "-help"], capture_output=True, text=True,
                                          check=False).stdout.splitlines() or ["unknown"])[0]
        saif_jobs(vcd, wins, pdir, res)
        bad = [n for n, i in res["saif"].items() if i["status"] != "PASS"]
        res["status"] = "PASS" if not bad else "FAIL"
        res["failed"] = (", ".join(f"saif {n}" for n in bad)) or None
        if bad:
            res["failed_log"], res["failed_tail"] = f"pwr/{bad[0]}/vcd2saif.log", cl.tail(pdir / bad[0] / "vcd2saif.log")
    except cl.StepFailed as e:
        res["failed"] = f"step {e.step} ({e.why})"
        res["failed_log"], res["failed_tail"] = str(e.log), cl.tail(e.log)
        print(f"cluster pwr {point}: FAIL at {e.step} ({e.why})", flush=True)
    except cl.Stop as e:
        res["failed"] = str(e)
        print(f"cluster pwr {point}: FAIL: {e}", flush=True)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded as the run's failure; the zip and clean still done
        res["failed"] = f"driver: {e!r}"
        print(f"cluster pwr {point}: FAIL in the driver: {e!r}", flush=True)
    finally:
        (pdir / "dut.vcd").unlink(missing_ok=True)        # X18, also when the run stopped before the cut
        res["questa"] = cl.questa_version()
        res["seconds"].update({k: v for k, v in steps.times.items()})
        res["seconds"]["total_before_pack"] = round(time.monotonic() - t_all, 1)
        res["memory"] = steps.peaks
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        try:
            cl.drop_wlf(res)
        except OSError as e:
            print(f"  could not delete vsim.wlf: {e!r}", flush=True)
        t = time.monotonic()
        try:
            pack(work, point, res)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack pwr/ of {pre['step1'].relative_to(ROOT)}: {e!r}", flush=True)
        res["pack_s"] = round(time.monotonic() - t, 1)
        shutil.rmtree(work, ignore_errors=True)
        try:
            clean = subprocess.run(["bash", "-c", "make clean-vsim clean-generated"], cwd=TB_DIR, env=cl.host_env(),
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=cl.TIMEOUT["clean"], check=False)
            st = cl.git(cl.SC, "status", "--porcelain").stdout.strip()
            print(f"  cleaned: {work} deleted; snax_cluster make clean-vsim clean-generated exit {clean.returncode}"
                  + (f"; snax_cluster not clean after it:\n{st}" if st else "; snax_cluster clean"), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  snax_cluster's clean failed: {e!r}", flush=True)
        if cl.TMP.is_dir() and not any(cl.TMP.iterdir()):
            cl.TMP.rmdir()
    return res


def pack(work: Path, point: str, res: dict) -> None:
    """Under pwr/ of sim/runs/cluster/nangate45/<point>.zip; the zip's other members (rtl/, gls/) kept."""
    z = cl.RUN_ZIPS / f"{point}.zip"
    pdir = work / "pwr"
    new = {}
    for f in ("pwr.do", "vcd_add.do", "vsim_cmd.sh", "vsim.txt", "obs_log.txt", "windows.json"):
        if (pdir / f).is_file():
            new[f"pwr/{f}"] = (pdir / f).read_bytes()
    for d in sorted(x for x in pdir.iterdir() if x.is_dir()):
        for f in ("w.saif", "vcd2saif.log"):
            if (d / f).is_file():
                new[f"pwr/{d.name}/{f}"] = (d / f).read_bytes()
    if (work / "logs").is_dir():
        new.update({f"pwr/logs/{k}": v.read_bytes() for k, v in arc.files_of(work / "logs").items()})
    new["pwr/check.json"] = (json.dumps(res, indent=2) + "\n").encode()
    old = {k: v for k, v in arc.read_all(z).items() if not k.startswith("pwr/")}
    arc.write(z, {**old, **new})
    res["zip"] = str(z.relative_to(ROOT))
    print(f"  packed {res['zip']} ({len(new)} members under pwr/)", flush=True)


def summary(point: str, res: dict) -> str:
    wins = res.get("windows") or []
    saifs = res.get("saif") or {}
    n_ok = sum(1 for i in saifs.values() if i.get("status") == "PASS")
    span = (f"span marks {wins[0]['mark']}–{wins[-1]['mark']} = {sum(w['cycles'] for w in wins)} cycles in "
            f"{len(wins)} windows" if wins else "no windows")
    vcd = f"VCD {res['vcd_bytes'] / 1e9:.2f} GB" if res.get("vcd_bytes") else "no VCD"
    line = f"cluster pwr {point} (part 1): {res['status']}, {span}, {vcd}, {n_ok} SAIFs checked"
    if res["status"] != "PASS":
        line += f"; failed: {res['failed']}"
    return line


def main(p: dict, images: dict, args) -> int:
    signal.signal(signal.SIGTERM, cl._sigterm)
    res = part1(p, images, args)
    print(summary(p["point"], res) + f" (pack {res.get('pack_s', 0):.0f} s)", flush=True)
    if res["status"] != "PASS" and res.get("failed_tail"):
        print(f"  last {TAIL} lines of {res.get('failed_log')}:\n{res['failed_tail']}", flush=True)
    return 0 if res["status"] == "PASS" else 1
