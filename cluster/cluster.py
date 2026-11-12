#!/usr/bin/env python3
"""cluster/cluster.py - a snax-forge design built into snax_cluster's whole cluster (CSYN1 Part B, X66, X67).

  pixi run cluster rtl <point> [--allow-branch]    step 1: the RTL with every memory as a RAM1 macro
  pixi run cluster syn <point> [--cores N] [--allow-branch]   step 2: DC on the whole cluster
  pixi run cluster gls <point> [--allow-branch]    step 3: the netlist in the same testbench (R4)

A point is an entry of cluster/points.json (point, recipe, W, sets, and srams: the macro instances the
cluster holds, per macro); the file also names the two images. snax_cluster is read from SNAX_CLUSTER
(default ../snax_cluster): clean, HEAD on origin/main (`git merge-base --is-ancestor HEAD origin/main`)
unless --allow-branch. snax-forge is read from SNAX_FORGE (default ../snax-forge): clean (PITFALLS E7).
Both commits are recorded. The folder holding the three repos is mounted at its own path in every
`podman run --rm` (no -it, stdin closed), with the home folder's Scala caches at /root (strm/gen.py's
podman_cmd, PITFALLS SC6).

The bundle, rtl/cluster/<point>.zip (X51): `pixi run forge <recipe> --set W=<W> --set <sets...>` in
snax-forge's image from the snax-forge checkout, the recipe found as forge/bundles.py finds it. A dirty
bundle (bundle.json `dirty`, X21) or one whose commit is not the checkout's is refused. The zip holds
bundle/ (the bundle folder, forge_expected.txt with it), sw/forge.elf (the ELF forge prints), the quiet
build beside it (sw/forge_quiet.elf and its legend sw/obs_marks.json, snax-forge D135, for PWR1), forge.log,
forge.txt (forge's terminal output) and provenance.json (snax-forge commit, image and id, the command, both
ELFs' sha256). A zip whose provenance has the same commit, image id and command is reused.

rtl, in tmp/cluster/<point>/ (the bundle zip unpacked there; the cluster file is the bundle's own
snax_forge.hjson), from snax_cluster's target/snitch_cluster:
  1. image: make clean-generated clean-vsim, then make rtl-gen CFG_OVERRIDE=<cluster file>; a separate
     call: util/clustergen.py -c <cluster file> -o <point tmp> --memories (memories.json)
  2. cluster/mem.py memories.json -> mem/ (tc_sram_impl.sv, models/, sram_models.f, mem.json)
  3. the plain run: vsim_preparation in the image, snax-forge-sim SIM=vsim and snax-forge-run SIM=vsim
     ELF=<elf> outside it (Questa on PATH, bender from snax_cluster's .pixi/envs/default/bin)
  4. the macro run: the same three calls with SRAM_IMPL=mem/tc_sram_impl.sv SRAM_MODELS=mem/sram_models.f
     (the vsim stamp rebuilds work-vsim/; no second rtl-gen)
  5. the checks (cluster/check.py): D123 on both runs against forge_expected.txt, equal forge cycles, the
     [tc_sram_impl] prints (their number, and the macro at each one's end) against the point's srams, the macro run's vlog.log (tc_sram_impl.sv and every
     macro compiled, nothing of tech_cells_generic's tc_sram), [SUCCESS] in both runs
  6. sim/runs/cluster/nangate45/<point>.zip, under rtl/ (other members kept): memories.json, mem.json,
     tc_sram_impl.sv, sram_models.f, plain/ and macro/ (each run's snax-forge-vsim.txt; the macro run's
     vlog.log and vopt.log), logs/ (every step's log), check.json. Packed also when a step failed. Then
     tmp/cluster/<point>/ is deleted and `make clean-vsim clean-generated` runs in snax_cluster (X51),
     also on a failure.
Each step's log path is printed when it starts. One line at the end: PASS or FAIL with the cycles and the
instances; a failure names the check or step and prints at most 30 lines of its log.

syn (X67 step 2, X68), from the same bundle zip, in tmp/cluster/<point>/:
  1. image: make clean-generated clean-syn, make rtl-gen CFG_OVERRIDE=<cluster file>; clustergen --memories;
     cluster/mem.py --text-only: its tc_sram_impl.sv must equal step 1's (rtl/tc_sram_impl.sv in
     sim/runs/cluster/nangate45/<point>.zip), or the run stops
  2. image: make gen-syn CFG_OVERRIDE=<cluster file> SRAM_IMPL=<that file> (work-syn/syn_flist.tcl)
  3. DC through syn/syn.py's source `cluster` (dc_env, run_dc with its licence retry, finish_run, write_summary):
     the run folder syn/runs/cluster/nangate45/<point>/ gets syn_flist.tcl, cluster/cluster.sdc and
     tc_sram_impl.sv, and the macros' .db (from ram/runs/lib/<name>.zip) for SYN_RAM_DBS; dc_syn.tcl sources
     the list (SYN_FLIST_TCL), elaborates snax_forge_cluster_wrapper (SYN_TOP), adds cluster.sdc after
     constraints.sdc (SYN_EXTRA_SDC) and runs cluster/cluster_check.tcl after the reports (SYN_POST_TCL);
     no SDF (X69); SYN_IGNORE_LOAD=1, so DC keeps --cores under a loaded host (UIO-231). DC's stdout goes to logs/dc_stdout.log as it runs; its path is printed first.
  4. tree.txt (cluster/tree.py, area_hierarchy.rpt to depth 4) beside the reports; the run zip
     syn/runs/cluster/nangate45/<point>.zip keeps syn.py's KEEP_RUN and the cluster's files; a row in
     results/cluster/nangate45/synth_dc.csv and the report zip results/cluster/nangate45/reports/<point>.zip.
  5. after DC ends, also on a failure: tmp/cluster/<point>/ deleted, make clean-syn clean-generated in snax_cluster.

gls (X67 step 3): step 2's netlist (out/snax_forge_cluster_wrapper_mapped.v of syn/runs/cluster/nangate45/<point>.zip)
in step 1's testbench, with step 1's ELF and check; zero delay, functional. snax_cluster's hook SIM_TYPE=gate_level_sim
(GLS_NETLIST, GLS_CELLS, with SRAM_IMPL and SRAM_MODELS) compiles the cells, the macro models and the netlist into
work-vsim/gls, and vopt takes -Lf work-vsim/gls, +initreg+0, +acc=n; vsim +nospecify +notimingchecks.
  1. checks before anything runs: the repos as rtl and syn; step 1 PASS, step 2's netlist there; the bundle zip's
     ELF the one both steps used (the bundle is reused, never made again: the netlist is of it); no file changed
     under hw/, util/, target/snitch_cluster/cfg/ or Bender.yml between the netlist's snax_cluster commit and HEAD
     but Makefiles, .mk and docs (RTL_CHANGE)
  2. in tmp/cluster/<point>/: the bundle and the netlist unpacked; image: make clean-generated clean-vsim, rtl-gen;
     clustergen --memories; cluster/mem.py, whose tc_sram_impl.sv must equal step 1's; the cell models as sim/pwr.py
     finds them (pwr.cell_model)
  3. vsim_preparation in the image, snax-forge-sim SIM=vsim and snax-forge-run SIM=vsim ELF=<elf> outside it, all
     three with the same SRAM_IMPL, SRAM_MODELS, SIM_TYPE, GLS_NETLIST, GLS_CELLS. The two host steps' Questa
     processes are sampled from /proc every PEAK_EVERY s (peak resident memory, first and last seen); Questa's own
     elapsed times are read from vlog.log (the netlist's vlog), vopt.log and the run's output.
  4. the checks: D123; forge cycles equal step 1's; the swap (vopt loaded snax_forge_cluster_wrapper and Nangate
     cells from work-vsim/gls, its command has +initreg+0 and +acc=n; the run prints no [tc_sram_impl]); RAMCOUNT
     (one line per instance of points.json's srams; against step 1's macro run, without the paths: reads equal on
     every instance, writes equal but for at most one more on an instance, the netlist's write at time 0 under
     +initreg+0, listed as ram_extra_writes; PITFALLS Q14); [SUCCESS] in both runs
  5. under gls/ of sim/runs/cluster/nangate45/<point>.zip (other members kept): snax-forge-vsim.txt, vlog.log,
     vopt.log, logs/, check.json; then vsim.wlf (VSIM_FLAGS' `log -r /*`) deleted with its size in check.json,
     tmp/cluster/<point>/ deleted and make clean-vsim clean-generated in snax_cluster, also on a failure. One line
     at the end.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "cluster"
for d in ("arc", "forge", "strm", "cluster", "syn", "ram", "sim"):
    sys.path.insert(0, str(ROOT / d))
import arc  # noqa: E402  arc/arc.py (X51)
import bundles  # noqa: E402  forge/bundles.py: find_recipe, inner_env
import check  # noqa: E402  cluster/check.py
import gen as strm_gen  # noqa: E402  strm/gen.py: podman_cmd with the Scala caches (SC6)
import mem  # noqa: E402  cluster/mem.py (X66)
import syn as synpy  # noqa: E402  syn/syn.py: the cluster source's DC run (X67 step 2)
import tree  # noqa: E402  cluster/tree.py

POINTS = HERE / "points.json"
SC = Path(os.environ.get("SNAX_CLUSTER", ROOT.parent / "snax_cluster")).resolve()
FORGE = Path(os.environ.get("SNAX_FORGE", ROOT.parent / "snax-forge")).resolve()
TB_DIR = SC / "target" / "snitch_cluster"
BENDER_DIR = SC / ".pixi" / "envs" / "default" / "bin"
TECH = "nangate45"
RTL_ZIPS = ROOT / "rtl" / "cluster"
RUN_ZIPS = ROOT / "sim" / "runs" / "cluster" / TECH
TMP = ROOT / "tmp" / "cluster"
TAIL = 30
TIMEOUT = {"forge": 3600, "rtl-gen": 3600, "clustergen": 600, "vsim_preparation": 1800,
           "snax-forge-sim": 3600, "snax-forge-run": 3600, "clean": 600, "gen-syn": 1800}
SYN_FLIST = TB_DIR / "work-syn" / "syn_flist.tcl"        # snax_cluster's gen-syn output
SDC = HERE / "cluster.sdc"
CHECK_TCL = HERE / "cluster_check.tcl"
TREE_DEPTH = 4
RUN_LOG = "logs/snax-forge-vsim.txt"          # snax_forge.mk's SNAX_FORGE_LOG for SIM=vsim, under TB_DIR
SUCCESS = check.SUCCESS
GENERIC_SRAM = "tech_cells_generic/src/rtl/tc_sram"
NETLIST = "out/snax_forge_cluster_wrapper_mapped.v"     # step 2's netlist in its run zip (X69)
GLS_TIMEOUT = {"gls_vsim_preparation": 1800, "gls_snax-forge-sim": 4 * 3600, "gls_snax-forge-run": 8 * 3600}
RTL_PATHS = ("hw", "util", "target/snitch_cluster/cfg", "Bender.yml")
NOT_RTL = re.compile(r"(^|/)(Makefile[^/]*|[^/]*\.mk|[^/]*\.md|README[^/]*)$")
PEAK_EVERY = 2.0
QUESTA_EXE = re.compile(r"^v(log|opt|sim|ish|lib)\w*$")
# Questa's programs by tool: vsim runs as vish (the Tcl shell, also of `vsim -c -do`) and vsimk (the kernel), vopt as
# vopt and voptk2
QUESTA_TOOL = (("vish", "vsim"), ("vsim", "vsim"), ("vopt", "vopt"), ("vlog", "vlog"), ("vlib", "vlib"))


class StepFailed(Exception):
    def __init__(self, step: str, log: Path, why: str):
        super().__init__(f"{step}: {why}")
        self.step, self.log, self.why = step, log, why


def load(point: str) -> tuple[dict, dict]:
    cfg = json.loads(POINTS.read_text())
    pts = {p["point"]: p for p in cfg["points"]}
    if point not in pts:
        sys.exit(f"no point {point!r} in {POINTS} (points: {', '.join(pts)})")
    return cfg["images"], pts[point]


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def check_repos(allow_branch: bool) -> dict:
    """snax_cluster clean and on origin/main (unless allow_branch), snax-forge clean; their commits."""
    out = {}
    for name, repo in (("snax_cluster", SC), ("snax_forge", FORGE)):
        if not (repo / ".git").exists():
            sys.exit(f"no {name} checkout at {repo}")
        st = git(repo, "status", "--porcelain").stdout
        if st.strip():
            hint = " (a submodule line: PITFALLS E7)" if name == "snax_forge" else ""
            sys.exit(f"{name} at {repo} is not clean{hint}:\n{st.rstrip()}")
        out[name] = git(repo, "rev-parse", "HEAD").stdout.strip()
    out["snax_cluster_branch"] = git(SC, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    on_main = git(SC, "merge-base", "--is-ancestor", "HEAD", "origin/main").returncode == 0
    out["snax_cluster_on_main"] = on_main
    if not on_main and not allow_branch:
        sys.exit(f"snax_cluster HEAD {out['snax_cluster'][:12]} is not on origin/main (--allow-branch to run it)")
    return out


def mount() -> Path:
    """The folder holding this repo, snax_cluster and snax-forge, mounted at its own path."""
    m = Path(os.path.commonpath([ROOT, SC, FORGE]))
    if m == Path("/"):
        sys.exit(f"{ROOT}, {SC} and {FORGE} share no folder but /")
    return m


def image_id(image: str) -> str:
    done = subprocess.run(["podman", "image", "inspect", "--format", "{{.Id}}", image],
                          capture_output=True, text=True, check=False)
    if done.returncode:
        sys.exit(f"no image {image}: {done.stderr.strip()}")
    return done.stdout.strip()


def host_env() -> dict:
    """Outside the image: this repo's pixi variables removed (forge/bundles.py), bender appended to PATH."""
    env = bundles.inner_env()
    env["PATH"] += os.pathsep + str(BENDER_DIR)
    return env


def tail(log: Path, n: int = TAIL) -> str:
    try:
        return "\n".join(log.read_text(errors="replace").rstrip().splitlines()[-n:])
    except OSError:
        return f"(no {log})"


class Steps:
    """Each step's command into logs/<k>_<name>.log, its path printed when it starts."""

    def __init__(self, work: Path, images: dict):
        self.work, self.images, self.mount = work, images, mount()
        self.logs = work / "logs"
        self.scripts = work / "scripts"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.scripts.mkdir(exist_ok=True)
        self.k, self.times, self.peaks = 0, {}, {}

    def _run(self, name: str, kind: str, argv: list[str], cwd: Path | None, env: dict | None,
             timeout: int, watch: list[tuple[str, str]] | None = None) -> Path:
        self.k += 1
        log = self.logs / f"{self.k:02d}_{name}.log"
        print(f"  {name:<28s} ({kind}) log {log}", flush=True)
        t0 = time.monotonic()
        peak = None
        with log.open("w") as f:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=f,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            if watch is not None:
                peak = Peak(proc.pid, watch, t0)
                peak.start()
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                rc = f"timeout after {timeout} s"
            finally:
                if proc.poll() is None:      # a timeout, or a TERM in the driver: stop the whole tree
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                if peak is not None:
                    self.peaks[name] = peak.finish()
        s = time.monotonic() - t0
        self.times[name] = round(s, 1)
        with log.open("a") as f:
            f.write(f"\n[cluster] exit {rc}, {s:.1f} s\n")
        mem_note = ""
        if peak is not None:
            mem_note = "; peak " + ", ".join(f"{k} {v['peak_mb']:.0f} MB" for k, v in self.peaks[name]["tools"].items())
        print(f"  {name:<28s} exit {rc}, {s:.0f} s{mem_note}", flush=True)
        if rc != 0:
            raise StepFailed(name, log, f"exit {rc}")
        return log

    def image(self, name: str, which: str, cwd: Path, cmd: str, timeout: int) -> Path:
        script = self.scripts / f"{name}.sh"
        script.write_text(f"set -e\ncd {shlex.quote(str(cwd))}\nset -x\n{cmd}\n")
        argv = strm_gen.podman_cmd(self.images[which], script, self.mount)
        return self._run(name, f"image {self.images[which]}", argv, None, None, timeout)

    def host(self, name: str, cwd: Path, cmd: str, timeout: int, watch: list[tuple[str, str]] | None = None) -> Path:
        return self._run(name, "host", ["bash", "-c", f"set -x; {cmd}"], cwd, host_env(), timeout, watch)


class Peak(threading.Thread):
    """The Questa processes under a step's command, sampled from /proc every PEAK_EVERY s: per label, the peak of
    the resident memory its processes hold together, and when it was first and last seen. A process's tool is its
    program's (QUESTA_TOOL: vish and vsimk are vsim, voptk2 is vopt); its label the first of `labels` ((tool, text
    in its command line, label)) that matches, else the tool. A label names its tool, since vopt's command line
    holds `-o tb_bin_opt` as the run's does."""

    def __init__(self, root: int, labels: list[tuple[str, str, str]], t0: float):
        super().__init__(daemon=True)
        self.root, self.labels, self.t0 = root, labels, t0
        self.seen: dict[str, dict] = {}
        self.tree_kb = 0
        self.halt = threading.Event()

    def run(self) -> None:
        while True:
            self.sample()
            if self.halt.wait(PEAK_EVERY):
                return

    def sample(self) -> None:
        now = time.monotonic()
        kids: dict[int, list[int]] = {}
        for d in os.listdir("/proc"):
            if d.isdigit():
                try:
                    stat = Path(f"/proc/{d}/stat").read_text()
                except OSError:
                    continue
                kids.setdefault(int(stat.rsplit(")", 1)[1].split()[1]), []).append(int(d))
        todo, total, now_kb = [self.root], 0, {}
        while todo:
            pid = todo.pop()
            todo += kids.get(pid, [])
            try:
                cmd = [c.decode(errors="replace") for c in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if c]
                rss = next(int(ln.split()[1]) for ln in Path(f"/proc/{pid}/status").read_text().splitlines()
                           if ln.startswith("VmRSS:"))
            except (OSError, StopIteration, ValueError, IndexError):
                continue
            total += rss
            exe = os.path.basename(cmd[0]) if cmd else ""
            if exe in ("sh", "bash") and len(cmd) > 1:     # Questa's wrapper scripts
                exe = os.path.basename(cmd[1])
            if not QUESTA_EXE.match(exe):
                continue
            tool = next(t for pre, t in QUESTA_TOOL if exe.startswith(pre))
            text = " ".join(cmd)
            label = next((lab for tl, sub, lab in self.labels if tl == tool and sub in text), tool)
            now_kb[label] = now_kb.get(label, 0) + rss
        for label, kb in now_kb.items():
            r = self.seen.setdefault(label, {"peak_kb": 0, "first": now, "last": now})
            r["peak_kb"], r["last"] = max(r["peak_kb"], kb), now
        self.tree_kb = max(self.tree_kb, total)

    def finish(self) -> dict:
        self.halt.set()
        self.join()
        return {"every_s": PEAK_EVERY, "tree_peak_mb": round(self.tree_kb / 1024, 1),
                "tools": {k: {"peak_mb": round(v["peak_kb"] / 1024, 1), "first_s": round(v["first"] - self.t0, 1),
                              "last_s": round(v["last"] - self.t0, 1)} for k, v in self.seen.items()}}


# ---------------------------------------------------------------- the bundle
FORGE_BUNDLE = re.compile(r"^\s*bundle\s+(\S+?)/?:", re.M)
FORGE_ELF = re.compile(r"^\s*sw\s+(\S+\.elf)\b", re.M)
PROVENANCE_KEY = ("snax_forge_commit", "image_id", "command")


def bundle_command(p: dict) -> str:
    recipe = bundles.find_recipe(p["recipe"], FORGE)
    sets = [f"W={p['W']}", *p.get("sets", [])]
    return " ".join(["pixi", "run", "forge", str(recipe), *(f"--set {shlex.quote(s)}" for s in sets)])


def make_bundle(p: dict, images: dict, repos: dict, steps: Steps) -> tuple[Path, dict]:
    """rtl/cluster/<point>.zip: forge in snax-forge's image, or the zip already made with the same key."""
    z = RTL_ZIPS / f"{p['point']}.zip"
    cmd = bundle_command(p)
    key = {"snax_forge_commit": repos["snax_forge"], "image_id": images["snax_forge_id"], "command": cmd}
    if arc.has(z, "provenance.json"):
        old = json.loads(arc.read(z, "provenance.json"))
        if {k: old.get(k) for k in PROVENANCE_KEY} == key:
            print(f"  bundle                       reused {z.relative_to(ROOT)} (same commit, image, command)",
                  flush=True)
            return z, old
    log = steps.image("forge", "snax_forge", FORGE, cmd, TIMEOUT["forge"])
    text = log.read_text(errors="replace")
    mb, me = FORGE_BUNDLE.search(text), FORGE_ELF.search(text)
    if not mb or not me:
        raise StepFailed("forge", log, "no bundle or sw line in forge's output")
    bdir, elf = FORGE / mb.group(1), FORGE / me.group(1)
    b = json.loads((bdir / "bundle.json").read_text())
    if b.get("dirty"):
        raise StepFailed("forge", log, f"dirty bundle (bundle.json dirty: true, commit {b.get('snax_forge_commit')})")
    if b.get("snax_forge_commit") != repos["snax_forge"]:
        raise StepFailed("forge", log, f"bundle commit {b.get('snax_forge_commit')} is not the checkout's "
                                       f"{repos['snax_forge']}")
    if not (bdir / "forge_expected.txt").is_file() or not elf.is_file():
        raise StepFailed("forge", log, f"no {bdir}/forge_expected.txt or no {elf}")
    quiet, marks = elf.parent / "forge_quiet.elf", elf.parent / "obs_marks.json"
    if not quiet.is_file() or not marks.is_file():
        raise StepFailed("forge", log, f"no {quiet} or no {marks}: the quiet build (snax-forge D135, "
                                       "CORE1 R3 on)")
    forge_log = elf.parent.parent / "forge.log"
    prov = {"point": p["point"], "recipe": p["recipe"], "recipe_file": str(bundles.find_recipe(p["recipe"], FORGE)),
            "W": p["W"], "sets": p.get("sets", []), **key, "image": images["snax_forge"],
            "snax_forge_dirty": b.get("dirty"), "bundle": str(bdir.relative_to(FORGE)),
            "elf": str(elf.relative_to(FORGE)), "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
            "quiet_elf_sha256": hashlib.sha256(quiet.read_bytes()).hexdigest(),
            "date": dt.datetime.now().isoformat(timespec="seconds")}
    members = {f"bundle/{rel}": f.read_bytes() for rel, f in arc.files_of(bdir).items()}
    members["sw/forge.elf"] = elf.read_bytes()
    members["sw/forge_quiet.elf"] = quiet.read_bytes()
    members["sw/obs_marks.json"] = marks.read_bytes()
    members["forge.txt"] = log.read_bytes()
    if forge_log.is_file():
        members["forge.log"] = forge_log.read_bytes()
    members["provenance.json"] = (json.dumps(prov, indent=2) + "\n").encode()
    arc.write(z, members)
    print(f"  bundle                       {z.relative_to(ROOT)} ({len(members)} members)", flush=True)
    return z, prov


# ---------------------------------------------------------------- rtl
def unpack(z: Path, dest: Path) -> None:
    for name, data in arc.read_all(z).items():
        f = dest / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)


def questa_version() -> str:
    done = subprocess.run(["vsim", "-version"], capture_output=True, text=True, env=host_env(), check=False)
    return (done.stdout.strip().splitlines() or ["unknown"])[0]


def vlog_check(text: str, impl: Path, macros: list[str]) -> dict:
    """The macro run's vlog.log: tc_sram_impl.sv read, every macro compiled, no tech_cells_generic tc_sram."""
    compiled = set(re.findall(r"-- Compiling module (\w+)", text))
    return {"tc_sram_impl_sv": str(impl) in text,
            "macros_compiled": {m: m in compiled for m in macros},
            "generic_tc_sram": GENERIC_SRAM in text}


def run_checks(work: Path, p: dict, ms: list[str]) -> dict:
    want = (work / "bundle" / "forge_expected.txt").read_text()
    runs = {r: (work / r / "snax-forge-vsim.txt").read_text(errors="replace")
            for r in ("plain", "macro") if (work / r / "snax-forge-vsim.txt").is_file()}
    c = {}
    for r in ("plain", "macro"):
        if r not in runs:
            c[f"d123_{r}"] = {"status": "FAIL", "notes": [f"no {r} run output"]}
            continue
        ok, notes = check.compare(want, runs[r])
        c[f"d123_{r}"] = {"status": "PASS" if ok else "FAIL", "notes": notes}
    cyc = {r: check.parse(t)["cycles"] for r, t in runs.items()}
    c["cycles"] = {"status": "PASS" if cyc.get("plain") is not None and cyc.get("plain") == cyc.get("macro")
                   else "FAIL", "plain": cyc.get("plain"), "macro": cyc.get("macro")}
    got = check.sram_counts(runs.get("macro", ""))
    lines = check.sram_lines(runs.get("macro", ""))
    want_srams = dict(sorted(p["srams"].items()))
    c["srams"] = {"status": "PASS" if got == want_srams and lines == sum(want_srams.values()) else "FAIL",
                  "want": want_srams, "got": got, "lines": lines,
                  "plain_lines": check.sram_lines(runs.get("plain", ""))}
    vlog = work / "macro" / "vlog.log"
    v = vlog_check(vlog.read_text(errors="replace") if vlog.is_file() else "", work / "mem" / "tc_sram_impl.sv", ms)
    v["status"] = "PASS" if v["tc_sram_impl_sv"] and all(v["macros_compiled"].values()) and \
        not v["generic_tc_sram"] else "FAIL"
    c["vlog"] = v
    succ = {r: check.success(runs.get(r, "")) for r in ("plain", "macro")}
    c["success"] = {"status": "PASS" if all(succ.values()) else "FAIL", **succ}
    return c


def failed_log(work: Path, name: str) -> Path:
    """The log to show for a failed check: the macro run's vlog.log, or the run whose output failed."""
    if name == "vlog":
        return work / "macro" / "vlog.log"
    r = "plain" if name == "d123_plain" or (name == "success" and not check.success(
        (work / "plain" / "snax-forge-vsim.txt").read_text(errors="replace")
        if (work / "plain" / "snax-forge-vsim.txt").is_file() else "")) else "macro"
    return work / r / "snax-forge-vsim.txt"


def rtl(p: dict, images: dict, args) -> int:
    repos = check_repos(args.allow_branch)
    images = {**images, "snax_forge_id": image_id(images["snax_forge"]),
              "snax_cluster_id": image_id(images["snax_cluster"])}
    work = TMP / p["point"]
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"cluster rtl {p['point']}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), "
          f"snax-forge {repos['snax_forge'][:12]}; work {work}", flush=True)
    steps = Steps(work, images)
    t0 = time.monotonic()
    res = {"point": p["point"], "tech": TECH, "status": "FAIL", "failed": None,
           "snax_cluster_commit": repos["snax_cluster"], "snax_cluster_on_main": repos["snax_cluster_on_main"],
           "snax_forge_commit": repos["snax_forge"], "images": {k: images[k] for k in
           ("snax_forge", "snax_forge_id", "snax_cluster", "snax_cluster_id")}}
    ms: list[str] = []
    try:
        z, prov = make_bundle(p, images, repos, steps)
        res["bundle"] = {"zip": str(z.relative_to(ROOT)), "elf_sha256": prov["elf_sha256"], "command": prov["command"]}
        unpack(z, work)
        cfg, elf = work / "bundle" / "snax_forge.hjson", work / "sw" / "forge.elf"
        q = shlex.quote
        steps.image("rtl-gen", "snax_cluster", TB_DIR,
                    f"make clean-generated clean-vsim\nmake rtl-gen CFG_OVERRIDE={q(str(cfg))}", TIMEOUT["rtl-gen"])
        steps.image("clustergen", "snax_cluster", TB_DIR,
                    f"python3 {q(str(SC / 'util' / 'clustergen.py'))} -c {q(str(cfg))} -o {q(str(work))} --memories",
                    TIMEOUT["clustergen"])
        print("  mem.py", flush=True)
        made = mem.make(work / "memories.json", work / "mem")
        ms = [m["name"] for m in made["macros"]]
        print("  " + "; ".join(f"{m['name']} ({'cached' if m.get('cached') else 'made'})" for m in made["macros"]),
              flush=True)
        sram = f"SRAM_IMPL={q(str(work / 'mem' / 'tc_sram_impl.sv'))} SRAM_MODELS={q(str(work / 'mem' / 'sram_models.f'))}"
        for r, opts in (("plain", ""), ("macro", " " + sram)):
            (work / r).mkdir()
            (TB_DIR / RUN_LOG).unlink(missing_ok=True)
            try:
                steps.image(f"{r}_vsim_preparation", "snax_cluster", TB_DIR,
                            f"make vsim_preparation CFG_OVERRIDE={q(str(cfg))}{opts}", TIMEOUT["vsim_preparation"])
                steps.host(f"{r}_snax-forge-sim", TB_DIR,
                           f"make snax-forge-sim SIM=vsim CFG_OVERRIDE={q(str(cfg))}{opts}", TIMEOUT["snax-forge-sim"])
                steps.host(f"{r}_snax-forge-run", TB_DIR,
                           f"make snax-forge-run SIM=vsim CFG_OVERRIDE={q(str(cfg))} ELF={q(str(elf))}{opts}",
                           TIMEOUT["snax-forge-run"])
            finally:
                if (TB_DIR / RUN_LOG).is_file():
                    shutil.copy(TB_DIR / RUN_LOG, work / r / "snax-forge-vsim.txt")
                if r == "macro":
                    for f in ("vlog.log", "vopt.log"):
                        if (TB_DIR / "work-vsim" / f).is_file():
                            shutil.copy(TB_DIR / "work-vsim" / f, work / r / f)
        res["checks"] = run_checks(work, p, ms)
        bad = [k for k, v in res["checks"].items() if v["status"] != "PASS"]
        res["status"] = "PASS" if not bad else "FAIL"
        res["failed"] = ", ".join(bad) or None
        if bad:
            log = failed_log(work, bad[0])
            res["failed_log"], res["failed_tail"] = str(log.relative_to(work)), tail(log)
    except StepFailed as e:
        res["failed"] = f"step {e.step} ({e.why})"
        res["failed_log"] = str(e.log.relative_to(work))
        print(f"cluster rtl {p['point']}: FAIL at {e.step} ({e.why}); last {TAIL} lines of {e.log}:\n{tail(e.log)}",
              flush=True)
        if (work / "plain").is_dir() or (work / "macro").is_dir():
            res["checks"] = run_checks(work, p, ms) if (work / "bundle").is_dir() else {}
    except Exception as e:  # noqa: BLE001 - recorded as the run's failure, the zip and the clean still done
        res["failed"] = f"driver: {e!r}"
        print(f"cluster rtl {p['point']}: FAIL in the driver: {e!r}", flush=True)
    finally:
        res["questa"] = questa_version()
        res["seconds"] = {**steps.times, "total": round(time.monotonic() - t0, 1)}
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        try:
            drop_wlf(res)
        except OSError as e:
            print(f"  could not delete vsim.wlf: {e!r}", flush=True)
        try:
            pack_run(work, p, res)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            clean = subprocess.run(["bash", "-c", "make clean-vsim clean-generated"], cwd=TB_DIR, env=host_env(),
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=TIMEOUT["clean"], check=False)
            st = git(SC, "status", "--porcelain").stdout.strip()
            print(f"  cleaned: {work} deleted; snax_cluster make clean-vsim clean-generated exit {clean.returncode}"
                  + (f"; snax_cluster not clean after it:\n{st}" if st else "; snax_cluster clean"), flush=True)
            if (TMP.is_dir() and not any(TMP.iterdir())):
                TMP.rmdir()
    summary(p, res)
    return 0 if res["status"] == "PASS" else 1


def pack_run(work: Path, p: dict, res: dict) -> None:
    """Under rtl/ of sim/runs/cluster/nangate45/<point>.zip; the zip's other members (syn/, gls/) kept."""
    z = RUN_ZIPS / f"{p['point']}.zip"
    keep = {"memories.json": work / "memories.json"}
    for f in ("mem.json", "tc_sram_impl.sv", "sram_models.f"):
        keep[f] = work / "mem" / f
    for r in ("plain", "macro"):
        for f in ("snax-forge-vsim.txt", "vlog.log", "vopt.log"):
            keep[f"{r}/{f}"] = work / r / f
    new = {f"rtl/{k}": v.read_bytes() for k, v in keep.items() if v.is_file()}
    new.update({f"rtl/logs/{k}": v.read_bytes() for k, v in arc.files_of(work / "logs").items()})
    new["rtl/check.json"] = (json.dumps(res, indent=2) + "\n").encode()
    old = {k: v for k, v in arc.read_all(z).items() if not k.startswith("rtl/")}
    arc.write(z, {**old, **new})
    res["zip"] = str(z.relative_to(ROOT))
    print(f"  packed {res['zip']} ({len(new)} members under rtl/)", flush=True)


def summary(p: dict, res: dict) -> None:
    c = res.get("checks", {})
    cyc, sr = c.get("cycles", {}), c.get("srams", {})
    n_macros = len(sr.get("got", {}))
    line = (f"cluster rtl {p['point']}: {res['status']}, {cyc.get('macro')} cycles (plain {cyc.get('plain')}), "
            f"{sr.get('lines', 0)} tc_sram_impl on {n_macros} macros")
    if res["status"] != "PASS":
        line += f"; failed: {res['failed']}"
    print(line, flush=True)
    if res.get("failed_tail"):
        print(f"  last {TAIL} lines of {res['failed_log']}:\n{res['failed_tail']}", flush=True)
    for k, v in c.items():
        if v.get("status") != "PASS":
            print(f"  {k}: {json.dumps({x: y for x, y in v.items() if x != 'status'})}", flush=True)


class Stop(Exception):
    """The syn step stops before DC (a check failed); the message says why."""


def _sigterm(signum, frame):   # a watchdog's TERM still runs the cleanup (finally blocks)
    raise SystemExit(f"terminated by signal {signum}")


def syn(p: dict, images: dict, args) -> int:
    signal.signal(signal.SIGTERM, _sigterm)
    repos = check_repos(args.allow_branch)
    images = {**images, "snax_forge_id": image_id(images["snax_forge"]),
              "snax_cluster_id": image_id(images["snax_cluster"])}
    step1 = RUN_ZIPS / f"{p['point']}.zip"
    if not arc.has(step1, "rtl/tc_sram_impl.sv"):
        sys.exit(f"no rtl/tc_sram_impl.sv in {step1.relative_to(ROOT)}: run pixi run cluster rtl {p['point']} first")
    synpy.use_source("cluster")
    tech = synpy.load_tech(TECH)
    res = synpy.resolve(tech)
    dc = os.environ.get("DC_SHELL", "dc_shell")
    if shutil.which(dc) is None:
        sys.exit(f"'{dc}' not found: load Design Compiler or set DC_SHELL")
    if not Path(res["lib_db"]).is_file():
        sys.exit(f"no library at {res['lib_db']}")
    res["lib_md5"] = synpy.md5_of(Path(res["lib_db"]))
    sargs = SimpleNamespace(clock=synpy.DEFAULT_CLOCK, cores=args.cores, sdf=False)
    point = p["point"]
    rdir = synpy.run_dir(TECH, point, sargs.clock)
    work = TMP / point
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"cluster syn {point}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), "
          f"snax-forge {repos['snax_forge'][:12]}, --cores {args.cores}; work {work}", flush=True)
    steps = Steps(work, images)
    t0 = time.monotonic()
    row, failed, dc_start = None, None, None
    try:
        z, prov = make_bundle(p, images, repos, steps)
        unpack(z, work)
        cfg = work / "bundle" / "snax_forge.hjson"
        q = shlex.quote
        steps.image("rtl-gen", "snax_cluster", TB_DIR,
                    f"make clean-generated clean-syn\nmake rtl-gen CFG_OVERRIDE={q(str(cfg))}", TIMEOUT["rtl-gen"])
        steps.image("clustergen", "snax_cluster", TB_DIR,
                    f"python3 {q(str(SC / 'util' / 'clustergen.py'))} -c {q(str(cfg))} -o {q(str(work))} --memories",
                    TIMEOUT["clustergen"])
        made = mem.make(work / "memories.json", work / "mem", text_only=True)
        impl = work / "mem" / "tc_sram_impl.sv"
        if impl.read_bytes() != arc.read(step1, "rtl/tc_sram_impl.sv"):
            raise Stop(f"{impl} differs from step 1's rtl/tc_sram_impl.sv in {step1.relative_to(ROOT)}")
        print("  tc_sram_impl.sv               equals step 1's", flush=True)
        macros = [m["name"] for m in made["macros"]]
        if sorted(macros) != sorted(p["srams"]):
            raise Stop(f"the list's macros {macros} are not points.json's srams {sorted(p['srams'])}")
        steps.image("gen-syn", "snax_cluster", TB_DIR,
                    f"make gen-syn CFG_OVERRIDE={q(str(cfg))} SRAM_IMPL={q(str(impl))}", TIMEOUT["gen-syn"])
        if not SYN_FLIST.is_file():
            raise Stop(f"gen-syn wrote no {SYN_FLIST}")
        flist = SYN_FLIST.read_text()
        if str(impl) not in flist:
            raise Stop(f"{SYN_FLIST} does not read {impl}")

        syn_env = synpy.dc_env(tech, res, point, sargs)
        syn_env.pop("SYN_FILELIST")
        dbs = [rdir / "macros" / f"{m}.db" for m in macros]
        syn_env.update({"SYN_FLIST_TCL": str(rdir / "syn_flist.tcl"), "SYN_TOP": synpy.SOURCES["cluster"]["top"],
                        "SYN_EXTRA_SDC": str(rdir / "cluster.sdc"), "SYN_POST_TCL": str(CHECK_TCL),
                        "SYN_RAM_DBS": " ".join(str(d) for d in dbs),
                        "SYN_IGNORE_LOAD": "1"})   # X68: the cores asked for, whatever the host's load (UIO-231)

        def prepare() -> None:
            (rdir / "syn_flist.tcl").write_text(flist)
            shutil.copy(SDC, rdir / "cluster.sdc")
            shutil.copy(impl, rdir / "tc_sram_impl.sv")
            (rdir / "macros").mkdir()
            for m, d in zip(macros, dbs):
                d.write_bytes(arc.read(Path(ram_zip(m)), f"{m}.db"))

        def write_tree() -> None:
            rpt = rdir / "reports" / "area_hierarchy.rpt"
            if rpt.is_file():
                lines = tree.tree(tree.parse(rpt.read_text(errors="replace")), TREE_DEPTH)
                (rdir / "tree.txt").write_text("".join(f"{ln}\n" for ln in lines))

        cmd = [dc, "-f", str(synpy.SCRIPT), "-output_log_file", "logs/dc_shell.log"]
        print(f"  DC: {rdir.relative_to(ROOT)}, follow with: tail -f {rdir / 'logs' / 'dc_stdout.log'}", flush=True)
        t_dc, dc_start = time.monotonic(), time.time()
        rc = synpy.run_dc(point, TECH, rdir, cmd, syn_env, sargs.clock, prepare)
        steps.times["dc"] = round(time.monotonic() - t_dc, 1)
        cluster_info = {"point": point, "recipe": p["recipe"], "W": p["W"], "sets": p.get("sets", []),
                        "snax_forge_commit": repos["snax_forge"], "snax_cluster_commit": repos["snax_cluster"],
                        "snax_cluster_on_main": repos["snax_cluster_on_main"], "images": images,
                        "bundle_zip": str(z.relative_to(ROOT)), "elf_sha256": prov["elf_sha256"],
                        "srams": p["srams"], "macros": macros, "step_seconds": steps.times}
        row = synpy.finish_run(point, rdir, tech, res, sargs, syn_env, rc, {"ram": None, "cluster": cluster_info},
                               before_pack=write_tree)
        synpy.write_summary(tech, [row])
    except StepFailed as e:
        failed = f"step {e.step} ({e.why})"
        print(f"cluster syn {point}: FAIL at {e.step} ({e.why}); last {TAIL} lines of {e.log}:\n{tail(e.log)}",
              flush=True)
    except Stop as e:
        failed = str(e)
        print(f"cluster syn {point}: FAIL: {e}", flush=True)
    except Exception as e:  # noqa: BLE001 - recorded as the run's failure; the cleanup below still runs
        failed = f"driver: {e!r}"
        print(f"cluster syn {point}: FAIL in the driver: {e!r}", flush=True)
    finally:
        # Each step on its own, so one that fails does not skip the rest (CSYN1 R3's stopped run).
        try:
            unfinished(rdir, synpy.run_zip(TECH, point, sargs.clock), dc_start)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack or remove {rdir}: {e!r}", flush=True)
        shutil.rmtree(work, ignore_errors=True)
        try:
            clean = subprocess.run(["bash", "-c", "make clean-syn clean-generated"], cwd=TB_DIR, env=host_env(),
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=TIMEOUT["clean"], check=False)
            st = git(SC, "status", "--porcelain").stdout.strip()
            print(f"  cleaned: {work} deleted; snax_cluster make clean-syn clean-generated exit {clean.returncode}"
                  + (f"; snax_cluster not clean after it:\n{st}" if st else "; snax_cluster clean"), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  snax_cluster's clean failed: {e!r}", flush=True)
        if TMP.is_dir() and not any(TMP.iterdir()):
            TMP.rmdir()
    total = time.monotonic() - t0
    if row is None:
        print(f"cluster syn {point}: FAIL: {failed or 'stopped'} ({total:.0f} s)", flush=True)
        return 1
    print(f"cluster syn {point}: {row['status']}, area {row['area_um2']} um2 (macros {row['macro_um2']} um2: "
          f"{row['macros']}), slack {row['slack_ns']} ns, errors {row['errors']}; DC {steps.times.get('dc', 0):.0f} s, "
          f"total {total:.0f} s", flush=True)
    return 0 if row["status"].startswith("ok") else 1


def unfinished(rdir: Path, z: Path, dc_start: float | None) -> None:
    """A run folder left after the step: pack it (its DC logs kept, X51) when finish_run did not write the zip
    after DC started; otherwise finish_run's zip is the run's and only the folder's remnants go."""
    if not rdir.is_dir():
        return
    if dc_start is not None and z.is_file() and z.stat().st_mtime >= dc_start:
        shutil.rmtree(rdir)
        print(f"  removed what was left of {rdir.relative_to(ROOT)} ({z.relative_to(ROOT)} written by the run)", flush=True)
        return
    synpy.pack_run(rdir)
    print(f"  packed the unfinished run into {z.relative_to(ROOT)}", flush=True)


def ram_zip(name: str) -> Path:
    import ram  # noqa: PLC0415  ram/ram.py: the macros' zips (X49)
    return ram.macro_zip(name)


# ---------------------------------------------------------------- gls (X67 step 3)
def rtl_changes(old: str) -> list[str]:
    """The files changed between the netlist's snax_cluster commit and HEAD that can change the RTL (RTL_PATHS,
    all but Makefiles, .mk and docs)."""
    done = git(SC, "diff", "--name-only", old, "HEAD", "--", *RTL_PATHS)
    if done.returncode:
        sys.exit(f"git diff {old[:12]} HEAD in {SC}: {done.stderr.strip()}")
    return [f for f in done.stdout.split() if not NOT_RTL.search(f)]


ELAPSED = re.compile(r"Elapsed time: (\d+):(\d+):(\d+)")


def elapsed(text: str, needle: str | None = None) -> int | None:
    """Questa's `Elapsed time: h:mm:ss` in seconds: of the tool call whose text holds `needle` (vlog.log holds one
    call per Start time), or the last one."""
    calls = text.split("Start time:")
    if needle is not None:
        calls = [c for c in calls if needle in c]
    for c in reversed(calls):
        if (m := ELAPSED.search(c)):
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    return None


def swap_check(vopt: str, vlog: str, run: str, netlist: Path, cell_names: set[str]) -> dict:
    """The netlist took the RTL's place: vopt loaded snax_forge_cluster_wrapper and cells from the gls library with
    +initreg+0 and +acc=n, vlog compiled the netlist, the run printed no [tc_sram_impl] (the RTL tc_sram_impl gone)."""
    loaded = re.findall(r"^-- Loading module (?:(\S+)\.)?(\w+)\s*$", vopt, re.M)
    wrapper = sorted({lib or "(work)" for lib, m in loaded if m == "snax_forge_cluster_wrapper"})
    from_gls = {m for lib, m in loaded if lib and lib.endswith("gls")}
    cmd = next((ln.strip() for ln in vopt.splitlines() if ln.lstrip().startswith("vopt ")), "")
    c = {"wrapper_from": wrapper, "cells_loaded": len(from_gls & cell_names),
         "netlist_modules_loaded": len(from_gls - cell_names), "vopt_command": cmd,
         "initreg0": "+initreg+0" in cmd, "acc_n": "+acc=n" in cmd,
         "netlist_compiled": str(netlist) in vlog, "tc_sram_impl_prints": check.sram_lines(run)}
    c["status"] = "PASS" if (len(wrapper) == 1 and wrapper[0].endswith("gls") and c["cells_loaded"] > 0
                             and c["initreg0"] and c["acc_n"] and c["netlist_compiled"]
                             and c["tc_sram_impl_prints"] == 0) else "FAIL"
    return c


def gls_checks(work: Path, p: dict, rtl_res: dict, rtl_run: str, netlist: Path, cell_names: set[str]) -> dict:
    g = work / "gls"
    run = (g / "snax-forge-vsim.txt").read_text(errors="replace") if (g / "snax-forge-vsim.txt").is_file() else ""
    vopt = (g / "vopt.log").read_text(errors="replace") if (g / "vopt.log").is_file() else ""
    vlog = (g / "vlog.log").read_text(errors="replace") if (g / "vlog.log").is_file() else ""
    c = {}
    ok, notes = check.compare((work / "bundle" / "forge_expected.txt").read_text(), run) if run else \
        (False, ["no run output"])
    c["d123"] = {"status": "PASS" if ok else "FAIL", "notes": notes}
    want = rtl_res["checks"]["cycles"]["macro"]
    got = check.parse(run)["cycles"]
    c["cycles"] = {"status": "PASS" if got is not None and got == want else "FAIL", "gls": got, "rtl": want}
    c["swap"] = swap_check(vopt, vlog, run, netlist, cell_names)
    ok, notes, extra = check.ram_compare(rtl_run, run, p["srams"])
    c["ramcount"] = {"status": "PASS" if ok else "FAIL", "notes": notes, "lines": len(check.ramcounts(run)),
                     "extra_writes": extra, "gls": check.ramcounts(run), "rtl": check.ramcounts(rtl_run)}
    succ = {"gls": check.success(run), "rtl": check.success(rtl_run)}
    c["success"] = {"status": "PASS" if all(succ.values()) else "FAIL", **succ}
    return c


def gls(p: dict, images: dict, args) -> int:
    signal.signal(signal.SIGTERM, _sigterm)
    repos = check_repos(args.allow_branch)
    images = {**images, "snax_forge_id": image_id(images["snax_forge"]),
              "snax_cluster_id": image_id(images["snax_cluster"])}
    point = p["point"]
    step1 = RUN_ZIPS / f"{point}.zip"
    for m in ("rtl/check.json", "rtl/tc_sram_impl.sv", "rtl/macro/snax-forge-vsim.txt"):
        if not arc.has(step1, m):
            sys.exit(f"no {m} in {step1.relative_to(ROOT)}: run pixi run cluster rtl {point} first")
    rtl_res = json.loads(arc.read(step1, "rtl/check.json"))
    if rtl_res.get("status") != "PASS":
        sys.exit(f"step 1 of {point} is {rtl_res.get('status')} ({step1.relative_to(ROOT)}), not PASS")
    rtl_run = arc.read_text(step1, "rtl/macro/snax-forge-vsim.txt")
    synpy.use_source("cluster")     # run_zip's folder is the source's
    synz = synpy.run_zip(TECH, point, synpy.DEFAULT_CLOCK)
    if not arc.has(synz, NETLIST):
        sys.exit(f"no {NETLIST} in {synz.relative_to(ROOT)}: run pixi run cluster syn {point} first")
    dc = json.loads(arc.read(synz, "tech.json"))["resolved"]["cluster"]
    z = RTL_ZIPS / f"{point}.zip"
    prov = json.loads(arc.read(z, "provenance.json"))
    shas = {"bundle": prov["elf_sha256"], "step 1": rtl_res["bundle"]["elf_sha256"], "step 2": dc["elf_sha256"]}
    if len(set(shas.values())) != 1:
        sys.exit(f"the ELF differs between the bundle zip and the steps: {shas}")
    changed = rtl_changes(dc["snax_cluster_commit"])
    if changed:
        sys.exit(f"snax_cluster changed RTL between the netlist's commit {dc['snax_cluster_commit'][:12]} and HEAD "
                 f"{repos['snax_cluster'][:12]}; the netlist is not of the testbench's RTL:\n  " + "\n  ".join(changed))
    import pwr  # noqa: PLC0415  sim/pwr.py: the cell models' rule (CELL_MODELS beside the .db)
    cells = pwr.cell_model(TECH)
    if not cells.is_file():
        sys.exit(f"no cell models at {cells}")
    cell_names = set(re.findall(r"^\s*module\s+(\w+)", cells.read_text(errors="replace"), re.M))
    work = TMP / point
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"cluster gls {point}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), netlist "
          f"of {dc['snax_cluster_commit'][:12]} (no RTL change between), snax-forge {repos['snax_forge'][:12]} "
          f"(bundle of {prov['snax_forge_commit'][:12]}, reused); work {work}", flush=True)
    steps = Steps(work, images)
    t0 = time.monotonic()
    res = {"point": point, "tech": TECH, "status": "FAIL", "failed": None,
           "snax_cluster_commit": repos["snax_cluster"], "snax_cluster_branch": repos["snax_cluster_branch"],
           "snax_cluster_on_main": repos["snax_cluster_on_main"],
           "netlist_snax_cluster_commit": dc["snax_cluster_commit"],
           "snax_forge_commit": repos["snax_forge"], "bundle_snax_forge_commit": prov["snax_forge_commit"],
           "netlist": {"zip": str(synz.relative_to(ROOT)), "member": NETLIST,
                       "sha256": hashlib.sha256(arc.read(synz, NETLIST)).hexdigest()},
           "cells": str(cells), "elf_sha256": prov["elf_sha256"],
           "rtl_check": f"{step1.relative_to(ROOT)}:rtl/check.json",
           "images": {k: images[k] for k in ("snax_cluster", "snax_cluster_id")}}
    try:
        unpack(z, work)
        netlist = work / "netlist" / Path(NETLIST).name
        netlist.parent.mkdir()
        netlist.write_bytes(arc.read(synz, NETLIST))
        cfg, elf = work / "bundle" / "snax_forge.hjson", work / "sw" / "forge.elf"
        q = shlex.quote
        steps.image("rtl-gen", "snax_cluster", TB_DIR,
                    f"make clean-generated clean-vsim\nmake rtl-gen CFG_OVERRIDE={q(str(cfg))}", TIMEOUT["rtl-gen"])
        steps.image("clustergen", "snax_cluster", TB_DIR,
                    f"python3 {q(str(SC / 'util' / 'clustergen.py'))} -c {q(str(cfg))} -o {q(str(work))} --memories",
                    TIMEOUT["clustergen"])
        made = mem.make(work / "memories.json", work / "mem")
        impl = work / "mem" / "tc_sram_impl.sv"
        if impl.read_bytes() != arc.read(step1, "rtl/tc_sram_impl.sv"):
            raise Stop(f"{impl} differs from step 1's rtl/tc_sram_impl.sv in {step1.relative_to(ROOT)}")
        print("  tc_sram_impl.sv               equals step 1's; " + "; ".join(
            f"{m['name']} ({'cached' if m.get('cached') else 'made'})" for m in made["macros"]), flush=True)
        opts = (f" SRAM_IMPL={q(str(impl))} SRAM_MODELS={q(str(work / 'mem' / 'sram_models.f'))}"
                f" SIM_TYPE=gate_level_sim GLS_NETLIST={q(str(netlist))} GLS_CELLS={q(str(cells))}")
        watch = [("vlog", str(netlist), "vlog netlist"), ("vlog", str(cells), "vlog cells"),  # vopt: its tool
                 ("vsim", "compile.vsim.tcl", "vsim compile"), ("vsim", "tb_bin_opt", "vsim run")]
        (work / "gls").mkdir()
        (TB_DIR / RUN_LOG).unlink(missing_ok=True)
        try:
            steps.image("gls_vsim_preparation", "snax_cluster", TB_DIR,
                        f"make vsim_preparation CFG_OVERRIDE={q(str(cfg))}{opts}", GLS_TIMEOUT["gls_vsim_preparation"])
            steps.host("gls_snax-forge-sim", TB_DIR, f"make snax-forge-sim SIM=vsim CFG_OVERRIDE={q(str(cfg))}{opts}",
                       GLS_TIMEOUT["gls_snax-forge-sim"], watch)
            steps.host("gls_snax-forge-run", TB_DIR,
                       f"make snax-forge-run SIM=vsim CFG_OVERRIDE={q(str(cfg))} ELF={q(str(elf))}{opts}",
                       GLS_TIMEOUT["gls_snax-forge-run"], watch)
        finally:
            if (TB_DIR / RUN_LOG).is_file():
                shutil.copy(TB_DIR / RUN_LOG, work / "gls" / "snax-forge-vsim.txt")
            for f in ("vlog.log", "vopt.log"):
                if (TB_DIR / "work-vsim" / f).is_file():
                    shutil.copy(TB_DIR / "work-vsim" / f, work / "gls" / f)
            res["questa_elapsed_s"] = {
                "vlog_netlist": elapsed(_text(work / "gls" / "vlog.log"), str(netlist)),
                "vopt": elapsed(_text(work / "gls" / "vopt.log")),
                "run": elapsed(_text(work / "gls" / "snax-forge-vsim.txt"))}
        res["checks"] = gls_checks(work, p, rtl_res, rtl_run, netlist, cell_names)
        # the netlist's one write at time 0 per macro, allowed by the check (PITFALLS Q8, Q14)
        res["ram_extra_writes"] = res["checks"]["ramcount"]["extra_writes"]
        bad = [k for k, v in res["checks"].items() if v["status"] != "PASS"]
        res["status"] = "PASS" if not bad else "FAIL"
        res["failed"] = ", ".join(bad) or None
        if bad:
            log = work / "gls" / ("vopt.log" if bad[0] == "swap" and not res["checks"]["swap"]["wrapper_from"]
                                  else "snax-forge-vsim.txt")
            res["failed_log"], res["failed_tail"] = str(log.relative_to(work)), tail(log)
    except StepFailed as e:
        res["failed"] = f"step {e.step} ({e.why})"
        res["failed_log"] = str(e.log.relative_to(work))
        print(f"cluster gls {point}: FAIL at {e.step} ({e.why}); last {TAIL} lines of {e.log}:\n{tail(e.log)}",
              flush=True)
        if (work / "gls" / "snax-forge-vsim.txt").is_file():
            res["checks"] = gls_checks(work, p, rtl_res, rtl_run, work / "netlist" / Path(NETLIST).name, cell_names)
    except Stop as e:
        res["failed"] = str(e)
        print(f"cluster gls {point}: FAIL: {e}", flush=True)
    except Exception as e:  # noqa: BLE001 - recorded as the run's failure, the zip and the clean still done
        res["failed"] = f"driver: {e!r}"
        print(f"cluster gls {point}: FAIL in the driver: {e!r}", flush=True)
    finally:
        res["questa"] = questa_version()
        res["seconds"] = {**steps.times, "total": round(time.monotonic() - t0, 1)}
        res["memory"] = steps.peaks
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        try:
            drop_wlf(res)
        except OSError as e:
            print(f"  could not delete vsim.wlf: {e!r}", flush=True)
        try:
            pack_gls(work, point, res)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack gls/ of {step1.relative_to(ROOT)}: {e!r}", flush=True)
        shutil.rmtree(work, ignore_errors=True)
        try:
            clean = subprocess.run(["bash", "-c", "make clean-vsim clean-generated"], cwd=TB_DIR, env=host_env(),
                                   stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   timeout=TIMEOUT["clean"], check=False)
            st = git(SC, "status", "--porcelain").stdout.strip()
            print(f"  cleaned: {work} deleted; snax_cluster make clean-vsim clean-generated exit {clean.returncode}"
                  + (f"; snax_cluster not clean after it:\n{st}" if st else "; snax_cluster clean"), flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  snax_cluster's clean failed: {e!r}", flush=True)
        if TMP.is_dir() and not any(TMP.iterdir()):
            TMP.rmdir()
    gls_summary(point, res)
    return 0 if res["status"] == "PASS" else 1


def drop_wlf(res: dict) -> None:
    """VSIM_FLAGS' `log -r /*` writes vsim.wlf beside snax_cluster's Makefile: scratch (X51), its size recorded in
    the run's check.json, then deleted (clean-vsim deletes it too; this does not rest on that)."""
    f = TB_DIR / "vsim.wlf"
    if f.is_file():
        res["wlf_bytes"] = f.stat().st_size
        f.unlink()
        print(f"  deleted {f} ({res['wlf_bytes'] / 1e6:.1f} MB)", flush=True)


def _text(f: Path) -> str:
    return f.read_text(errors="replace") if f.is_file() else ""


def pack_gls(work: Path, point: str, res: dict) -> None:
    """Under gls/ of sim/runs/cluster/nangate45/<point>.zip; the zip's other members (rtl/) kept."""
    z = RUN_ZIPS / f"{point}.zip"
    new = {f"gls/{f}": (work / "gls" / f).read_bytes() for f in ("snax-forge-vsim.txt", "vlog.log", "vopt.log")
           if (work / "gls" / f).is_file()}
    if (work / "logs").is_dir():
        new.update({f"gls/logs/{k}": v.read_bytes() for k, v in arc.files_of(work / "logs").items()})
    new["gls/check.json"] = (json.dumps(res, indent=2) + "\n").encode()
    old = {k: v for k, v in arc.read_all(z).items() if not k.startswith("gls/")}
    arc.write(z, {**old, **new})
    res["zip"] = str(z.relative_to(ROOT))
    print(f"  packed {res['zip']} ({len(new)} members under gls/)", flush=True)


def gls_summary(point: str, res: dict) -> None:
    c = res.get("checks", {})
    cyc, sw, rc = c.get("cycles", {}), c.get("swap", {}), c.get("ramcount", {})
    line = (f"cluster gls {point}: {res['status']}, {cyc.get('gls')} cycles (rtl {cyc.get('rtl')}), netlist swap "
            f"{'ok' if sw.get('status') == 'PASS' else 'FAIL'}, "
            + check.ram_summary(rc.get("lines", 0), rc.get("status") == "PASS", rc.get("extra_writes", [])))
    if res["status"] != "PASS":
        line += f"; failed: {res['failed']}"
    print(line, flush=True)
    if res.get("failed_tail"):
        print(f"  last {TAIL} lines of {res['failed_log']}:\n{res['failed_tail']}", flush=True)
    for k, v in c.items():
        if v.get("status") != "PASS":
            skip = {"status"} | ({"gls", "rtl"} if k == "ramcount" else set())
            print(f"  {k}: {json.dumps({x: y for x, y in v.items() if x not in skip})}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rtl", help="step 1: RTL with the memory macros, against the plain RTL (X66, X67)")
    r.add_argument("point")
    r.add_argument("--allow-branch", action="store_true", help="snax_cluster's HEAD need not be on origin/main")
    s = sub.add_parser("syn", help="step 2: DC on the whole cluster (X67, X68)")
    s.add_argument("point")
    s.add_argument("--cores", type=int, default=16, help="DC's cores (default 16, X68)")
    s.add_argument("--allow-branch", action="store_true", help="snax_cluster's HEAD need not be on origin/main")
    g = sub.add_parser("gls", help="step 3: step 2's netlist in step 1's testbench (X67)")
    g.add_argument("point")
    g.add_argument("--allow-branch", action="store_true", help="snax_cluster's HEAD need not be on origin/main")
    a = ap.parse_args()
    images, p = load(a.point)
    return {"rtl": rtl, "syn": syn, "gls": gls}[a.cmd](p, images, a)


if __name__ == "__main__":
    sys.exit(main())
