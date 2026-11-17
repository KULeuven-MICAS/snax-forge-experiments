#!/usr/bin/env python3
"""cluster/snb.py - snax_cluster's Snitch-only clusters through the cluster flow, `pixi run snb <step> <name>`.

  pixi run snb rtl <run> [--allow-branch]        the run's plain and quiet ELF, then the plain one on the RTL with macros
  pixi run snb syn <config> [--cores N] [--again] [--allow-branch]   DC on the whole cluster (a kept netlist adopted)
  pixi run snb gls <run> [--allow-branch]        the config's netlist in the same testbench, the plain ELF on it
  pixi run snb pwr <run> [--cores N] [--again] [--allow-branch]   the quiet ELF on the netlist, a SAIF per section, PT

Configs and runs are cluster/snb_points.json's (a run is <config>_<kernel>_<type>). snax_cluster is read from
SNAX_CLUSTER (default ../snax_cluster), clean and on origin/main unless --allow-branch; every make call names the
config by its relative cfg path, as snax_cluster's apps Makefile builds snitch-forge only then. A step works in
tmp/snb/<name>/ and keeps what it made under its folder of sim/runs/snb/nangate45/<run>.zip (rtl/, gls/, pwr/, pt/),
also on a failure; syn writes syn/runs/snb/nangate45/<config>.zip and results/snb/nangate45/synth_dc.csv, rtl and
gls a row of results/snb/nangate45/runs.csv, pwr results/snb/nangate45/power_pt.csv. The steps and their checks are
in cluster/README.md, "snb"; the helpers are cluster.py's and power.py's.
"""

from __future__ import annotations

import argparse
import ast
import csv
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
import time
from pathlib import Path
from types import SimpleNamespace

import cluster as cl  # noqa: E402  cluster/cluster.py: steps, podman, vsim and DC helpers (puts sim/, syn/ ... on sys.path)
import power as pw  # noqa: E402  cluster/power.py: the do-file, the windows, the cut, part 2

arc, mem, synpy = cl.arc, cl.mem, cl.synpy
import pwr  # noqa: E402  sim/pwr.py: scopes, cell_model, tool

ROOT, TECH, TAIL, SC, TB_DIR = cl.ROOT, cl.TECH, cl.TAIL, cl.SC, cl.TB_DIR
POINTS = cl.HERE / "snb_points.json"
RTL_ZIPS = ROOT / "rtl" / "snb"
RUN_ZIPS = ROOT / "sim" / "runs" / "snb" / TECH
TMP = ROOT / "tmp" / "snb"
RESULTS = ROOT / "results" / "snb" / TECH
RUNS_CSV = RESULTS / "runs.csv"
TOP = synpy.SOURCES["snb"]["top"]                       # snax_snitch_cluster_wrapper
NETLIST = f"out/{TOP}_mapped.v"
TB_TOP = "tb_bin/i_dut/i_snax_snitch_cluster"           # the wrapper's instance in the testbench
WRAP = "/" + TB_TOP
APPS = "sw/apps/snitch-forge"                           # under snax_cluster's target/snitch_cluster
SITE = pw.Site("snb pwr", RUN_ZIPS, TMP, NETLIST, TB_TOP, RESULTS / "power_pt.csv", RESULTS / "power_reports")
TIMEOUT = {"rtl-gen": 3600, "clustergen": 600, "sw": 1800, "vsim_preparation": 1800, "vsim_build": 4 * 3600,
           "run": 8 * 3600, "gen-syn": 1800, "clean": 600}
SUCCESS, FAILURE = "[SUCCESS] Program finished successfully", "[FAILURE]"
RUN_DO = "onbreak {resume}\nonfinish stop\nrun -all\nquit -f\n"     # the run with no waveform log
RUN_COLUMNS = ["run", "config", "kernel", "type", "sizes", "workers", "n_op",
               "rtl_status", "rtl_dma_in", "rtl_run", "rtl_dma_out", "rtl_compute", "rtl_errors",
               "gls_status", "gls_dma_in", "gls_run", "gls_dma_out", "gls_compute", "gls_errors", "gls_run_diff",
               "elf_sha256", "quiet_elf_sha256", "netlist_sha256", "snax_cluster_commit", "rtl_date", "gls_date"]
GLS_COLUMNS = [c for c in RUN_COLUMNS if c.startswith("gls_")] + ["netlist_sha256"]


# ---------------------------------------------------------------- points (cluster/test_snb.py)
def n_op(expr: str, sizes: dict[str, int]) -> int:
    """A kernel's operations from its sizes: ints, size names, + - * // and brackets."""
    def ev(n: ast.AST) -> int:
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.Name) and n.id in sizes:
            return int(sizes[n.id])
        if isinstance(n, ast.BinOp) and isinstance(n.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)):
            a, b = ev(n.left), ev(n.right)
            return {ast.Add: a + b, ast.Sub: a - b, ast.Mult: a * b}.get(type(n.op), a // b if b else 0)
        raise ValueError(f"n_op {expr!r}: {ast.dump(n)} is not an int, a size ({', '.join(sizes)}) or + - * //")
    return ev(ast.parse(expr, mode="eval"))


def load(path: Path = POINTS) -> dict:
    return json.loads(path.read_text())


def config_of(pts: dict, name: str) -> dict:
    cs = {c["config"]: c for c in pts["configs"]}
    if name not in cs:
        sys.exit(f"no config {name!r} in {POINTS.name} (configs: {', '.join(cs)})")
    return cs[name]


def run_of(pts: dict, name: str) -> dict:
    """<config>_<kernel>_<type> as a run: the config, the kernel's sizes and n_op, the seed."""
    for c in pts["configs"]:
        rest = name.removeprefix(c["config"] + "_")
        if rest == name or "_" not in rest:
            continue
        kernel, typ = rest.rsplit("_", 1)
        if kernel not in pts["kernels"] or typ not in pts["types"]:
            break
        k = pts["kernels"][kernel]
        return {"run": name, "config": c, "kernel": kernel, "type": typ, "sizes": dict(k["sizes"]),
                "n_op": n_op(k["n_op"], k["sizes"]), "seed": pts["seed"]}
    sys.exit(f"{name!r} is not <config>_<kernel>_<type> of {POINTS.name} (configs "
             f"{', '.join(c['config'] for c in pts['configs'])}; kernels {', '.join(pts['kernels'])}; types "
             f"{', '.join(pts['types'])})")


def size_text(sizes: dict[str, int]) -> str:
    """As snitch-forge prints them (SF_SIZE): `N=2048`, `M=16 N=128`."""
    return " ".join(f"{k}={v}" for k, v in sizes.items())


def make_args(r: dict) -> str:
    """The make variables of the run's program build."""
    return " ".join([f"CFG_OVERRIDE={r['config']['cfg']}", f"TYPE={r['type']}", f"SEED={r['seed']}",
                     *(f"{k}={v}" for k, v in r["sizes"].items())])


def data_line(r: dict) -> str:
    """data.h's first line for the run (snitch_forge_data.py's write)."""
    return f"// {r['kernel']}'s data, generated by datagen.py: {size_text(r['sizes'])}, TYPE={r['type']}, seed {r['seed']}"


# ---------------------------------------------------------------- the program's output (cluster/test_snb.py)
HEADER = re.compile(r"snitch-forge (\w+) (\w+) (.*?) workers (\d+)\s*$")
CYCLES = re.compile(r"snitch-forge cycles (dma_in|run|dma_out): (\d+)")
CORE = re.compile(r"snitch-forge core (\d+) compute: (\d+)")
ERRORS = re.compile(r"snitch-forge errors: (-?\d+)")
FIRST = re.compile(r"snitch-forge first error at (\d+)")


def parse_output(text: str) -> dict:
    """The plain build's lines: the header, the three sections' cycles (core 0's mcycle at each barrier), each
    worker's compute cycles, the errors and the first one, and the testbench's verdict."""
    out: dict = {"header": None, "cycles": {}, "compute": {}, "errors": None, "first_error": None,
                 "success": SUCCESS in text, "failure": FAILURE in text}
    for ln in text.splitlines():
        if (m := HEADER.search(ln)) and out["header"] is None:
            sizes = dict(kv.split("=", 1) for kv in m.group(3).split())
            out["header"] = {"kernel": m.group(1), "type": m.group(2), "sizes": {k: int(v) for k, v in sizes.items()},
                             "workers": int(m.group(4))}
        elif m := CYCLES.search(ln):
            out["cycles"][m.group(1)] = int(m.group(2))
        elif m := CORE.search(ln):
            out["compute"][int(m.group(1))] = int(m.group(2))
        elif m := ERRORS.search(ln):
            out["errors"] = int(m.group(1))
        elif m := FIRST.search(ln):
            out["first_error"] = int(m.group(1))
    return out


def program_checks(out: dict, r: dict) -> dict:
    """The run's gates: [SUCCESS] and no [FAILURE], errors 0, the header the run's (kernel, type, sizes, workers),
    the three sections' cycles, one compute line per worker."""
    want = {"kernel": r["kernel"], "type": r["type"], "sizes": r["sizes"], "workers": r["config"]["workers"]}
    ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    return {"success": {"status": ok(out["success"] and not out["failure"]), "success": out["success"],
                        "failure": out["failure"]},
            "errors": {"status": ok(out["errors"] == 0), "errors": out["errors"], "first": out["first_error"]},
            "header": {"status": ok(out["header"] == want), "want": want, "got": out["header"]},
            "cycles": {"status": ok(set(out["cycles"]) == {"dma_in", "run", "dma_out"}), **out["cycles"]},
            "compute": {"status": ok(len(out["compute"]) == want["workers"]),
                        "cores": {str(k): v for k, v in sorted(out["compute"].items())}}}


def failed(checks: dict) -> list[str]:
    return [k for k, v in checks.items() if v.get("status") != "PASS"]


def merge_runs(path: Path, row: dict, clear: list[str] | None = None) -> None:
    """runs.csv merged on run: the row's columns written into the run's row (other columns kept; `clear` emptied),
    sorted by config, kernel and type."""
    table: list[dict] = []
    if path.is_file():
        with path.open(newline="") as fh:
            table = list(csv.DictReader(fh))
    old = next((t for t in table if t["run"] == row["run"]), None)
    if old is None:
        old = {c: "" for c in RUN_COLUMNS}
        table.append(old)
    for c in clear or []:
        old[c] = ""
    old.update({k: v for k, v in row.items() if k in RUN_COLUMNS})
    table.sort(key=lambda t: (t["config"], t["kernel"], t["type"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=RUN_COLUMNS, extrasaction="ignore")
        w.writeheader()
        w.writerows(table)


def csv_cells(out: dict, prefix: str) -> dict:
    c = out["cycles"]
    return {f"{prefix}_dma_in": c.get("dma_in", ""), f"{prefix}_run": c.get("run", ""),
            f"{prefix}_dma_out": c.get("dma_out", ""), f"{prefix}_errors": "" if out["errors"] is None else out["errors"],
            f"{prefix}_compute": ";".join(str(v) for _, v in sorted(out["compute"].items()))}


# ---------------------------------------------------------------- shared step pieces
def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def check_sc(allow_branch: bool) -> dict:
    """snax_cluster clean and on origin/main (unless allow_branch); its commit and branch."""
    if not (SC / ".git").exists():
        sys.exit(f"no snax_cluster checkout at {SC}")
    st = cl.git(SC, "status", "--porcelain").stdout
    if st.strip():
        sys.exit(f"snax_cluster at {SC} is not clean:\n{st.rstrip()}")
    head = cl.git(SC, "rev-parse", "HEAD").stdout.strip()
    on_main = cl.git(SC, "merge-base", "--is-ancestor", "HEAD", "origin/main").returncode == 0
    if not on_main and not allow_branch:
        sys.exit(f"snax_cluster HEAD {head[:12]} is not on origin/main (--allow-branch to run it)")
    return {"snax_cluster": head, "snax_cluster_branch": cl.git(SC, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            "snax_cluster_on_main": on_main}


def with_ids(images: dict) -> dict:
    return {**images, "snax_cluster_id": cl.image_id(images["snax_cluster"])}


def memories(steps, work: Path, c: dict, text_only: bool = False) -> tuple[Path, list[str]]:
    """rtl-gen and clustergen for the config, mem.py's tc_sram_impl.sv; its macros must be the config's srams."""
    q = shlex.quote
    steps.image("rtl-gen", "snax_cluster", TB_DIR, f"make clean-generated clean-vsim clean-syn\n"
                f"make rtl-gen CFG_OVERRIDE={c['cfg']}", TIMEOUT["rtl-gen"])
    steps.image("clustergen", "snax_cluster", TB_DIR,
                f"python3 {q(str(SC / 'util' / 'clustergen.py'))} -c {q(str(TB_DIR / c['cfg']))} -o {q(str(work))} "
                "--memories", TIMEOUT["clustergen"])
    made = mem.make(work / "memories.json", work / "mem", text_only=text_only)
    macros = [m["name"] for m in made["macros"]]
    if sorted(macros) != sorted(c["srams"]):
        raise cl.Stop(f"the memory list's macros {macros} are not {POINTS.name}'s srams {sorted(c['srams'])}")
    print("  " + "; ".join(f"{m['name']} ({'cached' if m.get('cached') else 'made'})" for m in made["macros"]),
          flush=True)
    return work / "mem" / "tc_sram_impl.sv", macros


def run_elf(steps, name: str, d: Path, elf: Path) -> str:
    """The ELF on bin/snitch_cluster.vsim with RUN_DO in place of VSIM_FLAGS' do (no waveform log); its output in
    d/run.txt, returned."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.do").write_text(RUN_DO)
    script = (TB_DIR / "bin" / "snitch_cluster.vsim").read_text()
    (d / "vsim_cmd.sh").write_text(pw.vsim_command(script, d / "run.do", elf))
    q = shlex.quote
    try:
        steps.host(name, TB_DIR, f"bash {q(str(d / 'vsim_cmd.sh'))} > {q(str(d / 'run.txt'))} 2>&1", TIMEOUT["run"],
                   [("vsim", "tb_bin_opt", "vsim run")])
    finally:
        text = cl._text(d / "run.txt")
    return text


def keep_vsim_logs(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for f in ("vlog.log", "vopt.log"):
        if (TB_DIR / "work-vsim" / f).is_file():
            shutil.copy(TB_DIR / "work-vsim" / f, d / f)


def pack_under(z: Path, prefix: str, work: Path, files: dict[str, Path], res: dict) -> None:
    """files and work/logs under prefix/ of z, check.json beside them; the zip's other members kept."""
    new = {f"{prefix}/{k}": v.read_bytes() for k, v in files.items() if v.is_file()}
    if (work / "logs").is_dir():
        new.update({f"{prefix}/logs/{k}": v.read_bytes() for k, v in arc.files_of(work / "logs").items()})
    new[f"{prefix}/check.json"] = (json.dumps(res, indent=2, default=str) + "\n").encode()
    old = {k: v for k, v in arc.read_all(z).items() if not k.startswith(f"{prefix}/")}
    arc.write(z, {**old, **new})
    res["zip"] = str(z.relative_to(ROOT))
    print(f"  packed {res['zip']} ({len(new)} members under {prefix}/)", flush=True)


def wrap_up(work: Path, res: dict, cleans: str) -> None:
    """vsim.wlf's size recorded and deleted, the work folder deleted, snax_cluster's `make <cleans>`; each on its own."""
    try:
        cl.drop_wlf(res)
    except OSError as e:
        print(f"  could not delete vsim.wlf: {e!r}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    try:
        done = subprocess.run(["bash", "-c", f"make {cleans}"], cwd=TB_DIR, env=cl.host_env(), stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=TIMEOUT["clean"], check=False)
        st = cl.git(SC, "status", "--porcelain").stdout.strip()
        print(f"  cleaned: {work} deleted; snax_cluster make {cleans} exit {done.returncode}"
              + (f"; snax_cluster not clean after it:\n{st}" if st else "; snax_cluster clean"), flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"  snax_cluster's clean failed: {e!r}", flush=True)
    if TMP.is_dir() and not any(TMP.iterdir()):
        TMP.rmdir()


def fail_note(res: dict, e: Exception, step: str, name: str, work: Path) -> None:
    """A step's exception into res (failed, the log and its tail) and one line."""
    if isinstance(e, cl.StepFailed):
        res["failed"] = f"step {e.step} ({e.why})"
        res["failed_log"], res["failed_tail"] = str(e.log), cl.tail(e.log)
        print(f"snb {step} {name}: FAIL at {e.step} ({e.why}); last {TAIL} lines of {e.log}:\n{res['failed_tail']}",
              flush=True)
    elif isinstance(e, cl.Stop):
        res["failed"] = str(e)
        print(f"snb {step} {name}: FAIL: {e}", flush=True)
    else:
        res["failed"] = f"driver: {e!r}"
        print(f"snb {step} {name}: FAIL in the driver: {e!r}", flush=True)


# ---------------------------------------------------------------- rtl
def build_sw(steps, r: dict, work: Path, repos: dict, images: dict) -> dict:
    """The run's plain and quiet ELF in snax_cluster's image, right after the config's own runtime (make clean-sw,
    make sw), into rtl/snb/<run>.zip with data.h, the marks' legend and provenance.json; copied to work/sw/."""
    k, cfg, args = r["kernel"], r["config"]["cfg"], make_args(r)
    cmd = "\n".join([f"make clean-sw CFG_OVERRIDE={cfg}", f"make sw CFG_OVERRIDE={cfg}",
                     f"make -C {APPS}/{k} {args}", f"make -C {APPS}/{k} {args} QUIET=1"])
    log = steps.image("sw", "snax_cluster", TB_DIR, cmd, TIMEOUT["sw"])
    app = TB_DIR / APPS / k
    files = {"plain.elf": app / "build" / f"{k}.elf", "quiet.elf": app / "build" / f"{k}_quiet.elf",
             "data.h": app / "data" / "data.h", "obs_marks.json": TB_DIR / APPS / "obs_marks.json"}
    missing = [str(f) for f in files.values() if not f.is_file()]
    if missing:
        raise cl.StepFailed("sw", log, f"not built: {', '.join(missing)}")
    first = files["data.h"].read_text().splitlines()[0]
    if first != data_line(r):
        raise cl.StepFailed("sw", log, f"data.h is {first!r}, not {data_line(r)!r}")
    (work / "sw").mkdir()
    for n, f in files.items():
        shutil.copy(f, work / "sw" / n)
    prov = {"run": r["run"], "config": r["config"]["config"], "cfg": cfg, "kernel": k, "type": r["type"],
            "sizes": r["sizes"], "seed": r["seed"], "command": cmd, "snax_cluster_commit": repos["snax_cluster"],
            "image": images["snax_cluster"], "image_id": images["snax_cluster_id"],
            "elf_sha256": sha(files["plain.elf"].read_bytes()), "quiet_elf_sha256": sha(files["quiet.elf"].read_bytes()),
            "date": dt.datetime.now().isoformat(timespec="seconds")}
    z = RTL_ZIPS / f"{r['run']}.zip"
    arc.write(z, {**{n: f.read_bytes() for n, f in files.items()}, "sw.log": log.read_bytes(),
                  "provenance.json": (json.dumps(prov, indent=2) + "\n").encode()})
    print(f"  ELFs                         {z.relative_to(ROOT)}: plain {prov['elf_sha256'][:12]}, quiet "
          f"{prov['quiet_elf_sha256'][:12]}", flush=True)
    return prov


def rtl(r: dict, pts: dict, args) -> int:
    signal.signal(signal.SIGTERM, cl._sigterm)
    repos, images = check_sc(args.allow_branch), with_ids(pts["images"])
    name, c = r["run"], r["config"]
    work = TMP / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"snb rtl {name}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), {c['cfg']}, "
          f"{make_args(r)}; work {work}", flush=True)
    steps = cl.Steps(work, images)
    t0 = time.monotonic()
    res = {"run": name, "config": c["config"], "tech": TECH, "status": "FAIL", "failed": None, **repos,
           "snax_cluster_commit": repos["snax_cluster"], "make": make_args(r),
           "images": {k: images[k] for k in ("snax_cluster", "snax_cluster_id")}}
    out = None
    try:
        res["sw"] = build_sw(steps, r, work, repos, images)
        impl, macros = memories(steps, work, c)
        q = shlex.quote
        opts = f" SRAM_IMPL={q(str(impl))} SRAM_MODELS={q(str(work / 'mem' / 'sram_models.f'))}"
        steps.image("vsim_preparation", "snax_cluster", TB_DIR, f"make vsim_preparation CFG_OVERRIDE={c['cfg']}{opts}",
                    TIMEOUT["vsim_preparation"])
        try:
            steps.host("vsim_build", TB_DIR, f"make bin/snitch_cluster.vsim CFG_OVERRIDE={c['cfg']}{opts}",
                       TIMEOUT["vsim_build"])
        finally:
            keep_vsim_logs(work / "rtl")
        text = run_elf(steps, "run", work / "rtl", work / "sw" / "plain.elf")
        out = parse_output(text)
        checks = program_checks(out, r)
        v = cl.vlog_check(cl._text(work / "rtl" / "vlog.log"), impl, macros)
        v["status"] = "PASS" if v["tc_sram_impl_sv"] and all(v["macros_compiled"].values()) and \
            not v["generic_tc_sram"] else "FAIL"
        checks["vlog"] = v
        res["checks"], res["output"] = checks, out
        bad = failed(checks)
        res["status"], res["failed"] = ("PASS" if not bad else "FAIL"), ", ".join(bad) or None
        if bad:
            log = work / "rtl" / ("vlog.log" if bad[0] == "vlog" else "run.txt")
            res["failed_log"], res["failed_tail"] = str(log.relative_to(work)), cl.tail(log)
    except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded; the zip and the clean still done
        fail_note(res, e, "rtl", name, work)
    finally:
        res["questa"] = cl.questa_version()
        res["seconds"] = {**steps.times, "total": round(time.monotonic() - t0, 1)}
        res["memory"] = steps.peaks
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        try:
            files = {"memories.json": work / "memories.json"}
            files.update({f: work / "mem" / f for f in ("mem.json", "tc_sram_impl.sv", "sram_models.f")})
            files.update({f: work / "rtl" / f for f in ("run.txt", "run.do", "vsim_cmd.sh", "vlog.log", "vopt.log")})
            pack_under(RUN_ZIPS / f"{name}.zip", "rtl", work, files, res)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack rtl/ of {name}: {e!r}", flush=True)
        if out is not None and "sw" in res:
            old = {}
            if RUNS_CSV.is_file():
                with RUNS_CSV.open(newline="") as fh:
                    old = next((t for t in csv.DictReader(fh) if t["run"] == name), {})
            stale = old.get("elf_sha256") not in ("", None, res["sw"]["elf_sha256"])
            merge_runs(RUNS_CSV, {"run": name, "config": c["config"], "kernel": r["kernel"], "type": r["type"],
                                  "sizes": size_text(r["sizes"]), "workers": c["workers"], "n_op": r["n_op"],
                                  "rtl_status": res["status"], **csv_cells(out, "rtl"),
                                  "elf_sha256": res["sw"]["elf_sha256"], "quiet_elf_sha256": res["sw"]["quiet_elf_sha256"],
                                  "snax_cluster_commit": repos["snax_cluster"], "rtl_date": res["date"]},
                       clear=GLS_COLUMNS + ["gls_date"] if stale else None)
        wrap_up(work, res, "clean-vsim clean-generated")
    cyc = (out or {}).get("cycles", {})
    print(f"snb rtl {name}: {res['status']}, run {cyc.get('run')} cycles (dma in {cyc.get('dma_in')}, dma out "
          f"{cyc.get('dma_out')}), errors {(out or {}).get('errors')}"
          + (f"; failed: {res['failed']}" if res["status"] != "PASS" else ""), flush=True)
    for k, v in (res.get("checks") or {}).items():
        if v.get("status") != "PASS":
            print(f"  {k}: {json.dumps({x: y for x, y in v.items() if x != 'status'})}", flush=True)
    return 0 if res["status"] == "PASS" else 1


# ---------------------------------------------------------------- syn
def syn_row(config: str) -> dict | None:
    """The config's row of results/snb/nangate45/synth_dc.csv."""
    f = RESULTS / "synth_dc.csv"
    if not f.is_file():
        return None
    with f.open(newline="") as fh:
        return next((t for t in csv.DictReader(fh) if t["point"] == config), None)


def adoptable(z: Path, c: dict) -> tuple[bool, str]:
    """A kept DC run is used as it is when its netlist is the config's netlist_sha256, its row is ok and snax_cluster
    changed no RTL since its commit."""
    if not arc.has(z, NETLIST) or not arc.has(z, "tech.json"):
        return False, f"no {NETLIST} in {z.relative_to(ROOT)}"
    got = sha(arc.read(z, NETLIST))
    if got != c["netlist_sha256"]:
        return False, f"its netlist {got[:12]} is not {POINTS.name}'s {c['netlist_sha256'][:12]}"
    row = syn_row(c["config"])
    if row is None or row.get("status") != "ok":
        return False, f"synth_dc.csv's row is {None if row is None else row.get('status')}, not ok"
    commit = json.loads(arc.read(z, "tech.json"))["resolved"]["cluster"]["snax_cluster_commit"]
    changed = cl.rtl_changes(commit)
    if changed:
        return False, f"snax_cluster changed RTL since {commit[:12]}: {', '.join(changed[:5])}"
    return True, f"netlist {got[:12]} of snax_cluster {commit[:12]}, no RTL change since, row ok"


def syn(c: dict, pts: dict, args) -> int:
    signal.signal(signal.SIGTERM, cl._sigterm)
    repos, images = check_sc(args.allow_branch), with_ids(pts["images"])
    point = c["config"]
    synpy.use_source("snb")
    z = synpy.run_zip(TECH, point, synpy.DEFAULT_CLOCK)
    if not args.again:
        ok, why = adoptable(z, c)
        if ok:
            print(f"snb syn {point}: kept {z.relative_to(ROOT)} ({why}); --again runs DC", flush=True)
            return 0
        print(f"snb syn {point}: DC runs ({why})", flush=True)
    tech = synpy.load_tech(TECH)
    res = synpy.resolve(tech)
    dc = os.environ.get("DC_SHELL", "dc_shell")
    if shutil.which(dc) is None:
        sys.exit(f"'{dc}' not found: load Design Compiler or set DC_SHELL")
    if not Path(res["lib_db"]).is_file():
        sys.exit(f"no library at {res['lib_db']}")
    res["lib_md5"] = synpy.md5_of(Path(res["lib_db"]))
    sargs = SimpleNamespace(clock=synpy.DEFAULT_CLOCK, cores=args.cores, sdf=False)
    rdir = synpy.run_dir(TECH, point, sargs.clock)
    work = TMP / point
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"snb syn {point}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), {c['cfg']}, "
          f"--cores {args.cores}; work {work}", flush=True)
    steps = cl.Steps(work, images)
    t0 = time.monotonic()
    row, why, dc_start = None, None, None
    try:
        impl, macros = memories(steps, work, c, text_only=True)
        q = shlex.quote
        steps.image("gen-syn", "snax_cluster", TB_DIR, f"make gen-syn CFG_OVERRIDE={c['cfg']} SRAM_IMPL={q(str(impl))}",
                    TIMEOUT["gen-syn"])
        if not cl.SYN_FLIST.is_file() or str(impl) not in cl.SYN_FLIST.read_text():
            raise cl.Stop(f"gen-syn wrote no {cl.SYN_FLIST}, or it does not read {impl}")
        flist = cl.SYN_FLIST.read_text()
        syn_env = synpy.dc_env(tech, res, point, sargs)
        syn_env.pop("SYN_FILELIST")
        dbs = [rdir / "macros" / f"{m}.db" for m in macros]
        syn_env.update({"SYN_FLIST_TCL": str(rdir / "syn_flist.tcl"), "SYN_TOP": TOP,
                        "SYN_EXTRA_SDC": str(rdir / "cluster.sdc"), "SYN_POST_TCL": str(cl.CHECK_TCL),
                        "SYN_RAM_DBS": " ".join(str(d) for d in dbs), "SYN_IGNORE_LOAD": "1"})
        if c.get("syn", {}).get("clk_gate"):
            syn_env["SYN_CLK_GATE_ENABLE"] = "1"

        def prepare() -> None:
            (rdir / "syn_flist.tcl").write_text(flist)
            shutil.copy(cl.SDC, rdir / "cluster.sdc")
            shutil.copy(impl, rdir / "tc_sram_impl.sv")
            (rdir / "macros").mkdir()
            for m, d in zip(macros, dbs):
                d.write_bytes(arc.read(cl.ram_zip(m), f"{m}.db"))

        def write_tree() -> None:
            rpt = rdir / "reports" / "area_hierarchy.rpt"
            if rpt.is_file():
                lines = cl.tree.tree(cl.tree.parse(rpt.read_text(errors="replace")), cl.TREE_DEPTH)
                (rdir / "tree.txt").write_text("".join(f"{ln}\n" for ln in lines))

        cmd = [dc, "-f", str(synpy.SCRIPT), "-output_log_file", "logs/dc_shell.log"]
        print(f"  DC: {rdir.relative_to(ROOT)}, follow with: tail -f {rdir / 'logs' / 'dc_stdout.log'}", flush=True)
        t_dc, dc_start = time.monotonic(), time.time()
        rc = synpy.run_dc(point, TECH, rdir, cmd, syn_env, sargs.clock, prepare)
        steps.times["dc"] = round(time.monotonic() - t_dc, 1)
        info = {"config": point, "cfg": c["cfg"], "snax_cluster_commit": repos["snax_cluster"],
                "snax_cluster_on_main": repos["snax_cluster_on_main"], "images": images, "srams": c["srams"],
                "macros": macros, "syn": c.get("syn", {}), "step_seconds": steps.times}
        row = synpy.finish_run(point, rdir, tech, res, sargs, syn_env, rc, {"ram": None, "cluster": info},
                               before_pack=write_tree)
        synpy.write_summary(tech, [row])
    except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded; the cleanup below still runs
        note: dict = {}
        fail_note(note, e, "syn", point, work)
        why = note["failed"]
    finally:
        try:
            cl.unfinished(rdir, z, dc_start)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack or remove {rdir}: {e!r}", flush=True)
        wrap_up(work, {}, "clean-syn clean-generated")
    total = time.monotonic() - t0
    if row is None:
        print(f"snb syn {point}: FAIL: {why or 'stopped'} ({total:.0f} s)", flush=True)
        return 1
    got = sha(arc.read(z, NETLIST)) if arc.has(z, NETLIST) else None
    print(f"snb syn {point}: {row['status']}, area {row['area_um2']} um2 (macros {row['macro_um2']} um2: "
          f"{row['macros']}), slack {row['slack_ns']} ns, errors {row['errors']}; DC {steps.times.get('dc', 0):.0f} s, "
          f"total {total:.0f} s; netlist {got}", flush=True)
    if got != c["netlist_sha256"]:
        print(f"  a new netlist: set {point}'s netlist_sha256 in {POINTS.name} to {got} for gls and pwr to use it",
              flush=True)
    return 0 if row["status"].startswith("ok") else 1


# ---------------------------------------------------------------- gls and pwr: the netlist build
def preflight(r: dict, pts: dict, args, need_gls: bool = False) -> dict:
    """The repos, rtl/ PASS (and gls/ when need_gls), the ELFs as rtl/ built them, the config's netlist as
    snb_points.json names it, no RTL change in snax_cluster since the netlist."""
    repos, images = check_sc(args.allow_branch), with_ids(pts["images"])
    name, c = r["run"], r["config"]
    runz, elfz = RUN_ZIPS / f"{name}.zip", RTL_ZIPS / f"{name}.zip"
    want = ["rtl/check.json", "rtl/tc_sram_impl.sv"] + (["gls/check.json"] if need_gls else [])
    for m in want:
        if not arc.has(runz, m):
            sys.exit(f"no {m} in {runz.relative_to(ROOT)}: run pixi run snb rtl{' and gls' if need_gls else ''} {name}")
    rtl_res = json.loads(arc.read(runz, "rtl/check.json"))
    gls_res = json.loads(arc.read(runz, "gls/check.json")) if need_gls else None
    for step, x in (("rtl", rtl_res), ("gls", gls_res)):
        if x is not None and x.get("status") != "PASS":
            sys.exit(f"snb {step} of {name} is {x.get('status')} ({runz.relative_to(ROOT)}), not PASS")
    prov = json.loads(arc.read(elfz, "provenance.json"))
    for m, key in (("plain.elf", "elf_sha256"), ("quiet.elf", "quiet_elf_sha256")):
        if sha(arc.read(elfz, m)) != prov[key] or rtl_res["sw"][key] != prov[key]:
            sys.exit(f"{m} of {elfz.relative_to(ROOT)} is not the one rtl/ built and ran: run pixi run snb rtl {name}")
    synpy.use_source("snb")
    synz = synpy.run_zip(TECH, c["config"], synpy.DEFAULT_CLOCK)
    if not arc.has(synz, NETLIST):
        sys.exit(f"no {NETLIST} in {synz.relative_to(ROOT)}: run pixi run snb syn {c['config']}")
    netlist_sha = sha(arc.read(synz, NETLIST))
    if netlist_sha != c["netlist_sha256"]:
        sys.exit(f"the netlist in {synz.relative_to(ROOT)} is {netlist_sha}, not {POINTS.name}'s {c['config']} "
                 f"netlist_sha256: set it there if this netlist is the one to use")
    if need_gls and gls_res.get("netlist", {}).get("sha256") != netlist_sha:
        sys.exit(f"gls/ of {name} ran another netlist: run pixi run snb gls {name}")
    dc = json.loads(arc.read(synz, "tech.json"))["resolved"]["cluster"]
    changed = cl.rtl_changes(dc["snax_cluster_commit"])
    if changed:
        sys.exit(f"snax_cluster changed RTL between the netlist's commit {dc['snax_cluster_commit'][:12]} and HEAD "
                 f"{repos['snax_cluster'][:12]}:\n  " + "\n  ".join(changed))
    cells = pwr.cell_model(TECH)
    if not cells.is_file():
        sys.exit(f"no cell models at {cells}")
    return {"repos": repos, "images": images, "runz": runz, "elfz": elfz, "rtl": rtl_res, "gls": gls_res,
            "prov": prov, "synz": synz, "netlist_sha": netlist_sha, "quiet_sha": prov["quiet_elf_sha256"],
            "netlist_commit": dc["snax_cluster_commit"], "cells": cells}


def build_netlist(steps, work: Path, r: dict, pre: dict) -> tuple[Path, dict]:
    """The ELFs and the netlist unpacked, the config's memories (tc_sram_impl.sv equal to rtl/'s), the gate-level
    build (vsim_preparation in the image, bin/snitch_cluster.vsim outside) and its swap check (the run's
    [tc_sram_impl] prints are checked after the run)."""
    q = shlex.quote
    (work / "sw").mkdir()
    for m in ("plain.elf", "quiet.elf", "obs_marks.json"):
        (work / "sw" / m).write_bytes(arc.read(pre["elfz"], m))
    netlist = work / "netlist" / Path(NETLIST).name
    netlist.parent.mkdir()
    netlist.write_bytes(arc.read(pre["synz"], NETLIST))
    impl, _ = memories(steps, work, r["config"])
    if impl.read_bytes() != arc.read(pre["runz"], "rtl/tc_sram_impl.sv"):
        raise cl.Stop(f"{impl} differs from rtl/tc_sram_impl.sv in {pre['runz'].relative_to(ROOT)}")
    cells, cfg = pre["cells"], r["config"]["cfg"]
    opts = (f" SRAM_IMPL={q(str(impl))} SRAM_MODELS={q(str(work / 'mem' / 'sram_models.f'))}"
            f" SIM_TYPE=gate_level_sim GLS_NETLIST={q(str(netlist))} GLS_CELLS={q(str(cells))}")
    watch = [("vlog", str(netlist), "vlog netlist"), ("vlog", str(cells), "vlog cells"),
             ("vsim", "compile.vsim.tcl", "vsim compile")]
    steps.image("gls_vsim_preparation", "snax_cluster", TB_DIR, f"make vsim_preparation CFG_OVERRIDE={cfg}{opts}",
                TIMEOUT["vsim_preparation"])
    try:
        steps.host("gls_vsim_build", TB_DIR, f"make bin/snitch_cluster.vsim CFG_OVERRIDE={cfg}{opts}",
                   TIMEOUT["vsim_build"], watch)
    finally:
        keep_vsim_logs(work / "build")
    cell_names = set(re.findall(r"^\s*module\s+(\w+)", cells.read_text(errors="replace"), re.M))
    vopt, vlog = cl._text(work / "build" / "vopt.log"), cl._text(work / "build" / "vlog.log")
    sw = cl.swap_check(vopt, vlog, "", netlist, cell_names, top=TOP)
    if sw["status"] != "PASS":
        raise cl.StepFailed("swap", work / "build" / "vopt.log", f"the netlist did not take the RTL's place: "
                            f"{ {k: v for k, v in sw.items() if k != 'vopt_command'} }")
    print(f"  swap                         PASS: {TOP} from {sw['wrapper_from']}, {sw['cells_loaded']} cells, "
          f"{sw['netlist_modules_loaded']} netlist modules", flush=True)
    return netlist, sw


def gls(r: dict, pts: dict, args) -> int:
    signal.signal(signal.SIGTERM, cl._sigterm)
    pre = preflight(r, pts, args)
    name, repos = r["run"], pre["repos"]
    work = TMP / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    print(f"snb gls {name}: snax_cluster {repos['snax_cluster'][:12]} ({repos['snax_cluster_branch']}), netlist "
          f"{pre['netlist_sha'][:12]} of {pre['netlist_commit'][:12]}, ELF {pre['prov']['elf_sha256'][:12]}; work {work}",
          flush=True)
    steps = cl.Steps(work, pre["images"])
    t0 = time.monotonic()
    res = {"run": name, "config": r["config"]["config"], "tech": TECH, "status": "FAIL", "failed": None, **repos,
           "snax_cluster_commit": repos["snax_cluster"],
           "netlist": {"zip": str(pre["synz"].relative_to(ROOT)), "member": NETLIST, "sha256": pre["netlist_sha"],
                       "snax_cluster_commit": pre["netlist_commit"]},
           "elf_sha256": pre["prov"]["elf_sha256"], "cells": str(pre["cells"]),
           "images": {k: pre["images"][k] for k in ("snax_cluster", "snax_cluster_id")}}
    out = None
    try:
        netlist, sw = build_netlist(steps, work, r, pre)
        text = run_elf(steps, "gls_run", work / "gls", work / "sw" / "plain.elf")
        res["questa_elapsed_s"] = cl.elapsed(text)
        out = parse_output(text)
        checks = program_checks(out, r)
        sw["tc_sram_impl_prints"] = cl.check.sram_lines(text)
        sw["status"] = "PASS" if sw["tc_sram_impl_prints"] == 0 else "FAIL"
        checks["swap"] = {k: v for k, v in sw.items() if k != "vopt_command"}
        rtl_out = pre["rtl"]["output"]
        # recorded beside the RTL's, not a gate (X91)
        res["against_rtl"] = {s: {"gls": out["cycles"].get(s), "rtl": rtl_out["cycles"].get(s),
                                  "diff": None if out["cycles"].get(s) is None or rtl_out["cycles"].get(s) is None
                                  else out["cycles"][s] - rtl_out["cycles"][s]} for s in ("dma_in", "run", "dma_out")}
        res["checks"], res["output"] = checks, out
        bad = failed(checks)
        res["status"], res["failed"] = ("PASS" if not bad else "FAIL"), ", ".join(bad) or None
        if bad:
            res["failed_log"], res["failed_tail"] = "gls/run.txt", cl.tail(work / "gls" / "run.txt")
    except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded; the zip and the clean still done
        fail_note(res, e, "gls", name, work)
    finally:
        res["questa"] = cl.questa_version()
        res["seconds"] = {**steps.times, "total": round(time.monotonic() - t0, 1)}
        res["memory"] = steps.peaks
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        try:
            files = {f"build/{f}": work / "build" / f for f in ("vlog.log", "vopt.log")}
            files.update({f: work / "gls" / f for f in ("run.txt", "run.do", "vsim_cmd.sh")})
            pack_under(pre["runz"], "gls", work, files, res)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack gls/ of {name}: {e!r}", flush=True)
        if out is not None:
            diff = (res.get("against_rtl") or {}).get("run", {}).get("diff")
            merge_runs(RUNS_CSV, {"run": name, "gls_status": res["status"], **csv_cells(out, "gls"),
                                  "gls_run_diff": "" if diff is None else diff, "netlist_sha256": pre["netlist_sha"],
                                  "gls_date": res["date"]})
        wrap_up(work, res, "clean-vsim clean-generated")
    a = (res.get("against_rtl") or {}).get("run", {})
    print(f"snb gls {name}: {res['status']}, run {a.get('gls')} cycles (RTL {a.get('rtl')}, diff {a.get('diff')}), "
          f"errors {(out or {}).get('errors')}" + (f"; failed: {res['failed']}" if res["status"] != "PASS" else ""),
          flush=True)
    for k, v in (res.get("checks") or {}).items():
        if v.get("status") != "PASS":
            print(f"  {k}: {json.dumps({x: y for x, y in v.items() if x != 'status'})}", flush=True)
    return 0 if res["status"] == "PASS" else 1


# ---------------------------------------------------------------- pwr
def against_rtl(wins: list[dict], rtl_out: dict) -> list[dict]:
    """Each window's cycles beside the plain RTL run's section (core 0's mcycle between barriers); recorded only."""
    rows = []
    for w in wins:
        ref = rtl_out["cycles"].get(w["kind"])
        rows.append({"mark": w["mark"], "kind": w["kind"], "cycles": w["cycles"], "rtl": ref,
                     "diff": None if ref is None else w["cycles"] - ref})
    return rows


def part1_head(name: str, pre: dict, marks: list[dict]) -> dict:
    """part 1's check.json before the run: what it ran on, with the keys power.part1_current reads."""
    repos = pre["repos"]
    return {"point": name, "tech": TECH, "part": 1, "status": "FAIL", "failed": None, **repos,
            "snax_cluster_commit": repos["snax_cluster"],
            "netlist": {"zip": str(pre["synz"].relative_to(ROOT)), "member": NETLIST, "sha256": pre["netlist_sha"]},
            "netlist_snax_cluster_commit": pre["netlist_commit"],
            "snax_forge_experiments_commit": cl.git(ROOT, "rev-parse", "HEAD").stdout.strip(),
            "elf_sha256": pre["prov"]["elf_sha256"], "quiet_elf_sha256": pre["quiet_sha"], "cells": str(pre["cells"]),
            "images": {k: pre["images"][k] for k in ("snax_cluster", "snax_cluster_id")},
            "clock": {"tb_ps": pw.CLOCK_PS, "flow_ns": pwr.CLOCK_NS, "cut_timescale": "10ps"}, "seconds": {},
            "obs_marks": marks}


def part1(r: dict, pre: dict) -> dict:
    """The quiet ELF on the netlist with power.py's do-file (the VCD of the design scopes, obs_o's changes), the
    windows from the marks, the cut and one checked SAIF per window, packed under pwr/ of the run zip."""
    name = r["run"]
    marks = json.loads(arc.read(pre["elfz"], "obs_marks.json"))
    upto, chk = pw.obs_marks(marks)
    work = TMP / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    pdir = work / "pwr"
    pdir.mkdir()
    print(f"snb pwr {name} (part 1): netlist {pre['netlist_sha'][:12]}, quiet ELF {pre['quiet_sha'][:12]}; marks "
          f"{upto[0]['mark']} to {chk['mark']} (check); work {work}", flush=True)
    steps = cl.Steps(work, pre["images"])
    t_all = time.monotonic()
    res = part1_head(name, pre, marks)
    try:
        t = time.monotonic()
        netlist, sw = build_netlist(steps, work, r, pre)
        res["swap"] = {k: v for k, v in sw.items() if k != "vopt_command"}
        res["seconds"]["setup_and_build"] = round(time.monotonic() - t, 1)
        scopes = pwr.scopes(netlist, TOP)
        adds = pw.vcd_add_lines(scopes, WRAP)
        (pdir / "vcd_add.do").write_text("\n".join(adds) + "\n")
        (pdir / "pwr.do").write_text(pw.do_file(pdir, chk["mark"], WRAP))
        res["scopes"] = {"vcd_add": len(adds), "design_scopes": len(scopes), "escaped": sum("\\" in s for s in scopes)}
        script = (TB_DIR / "bin" / "snitch_cluster.vsim").read_text()
        (pdir / "vsim_cmd.sh").write_text(pw.vsim_command(script, pdir / "pwr.do", work / "sw" / "quiet.elf"))
        print(f"  do-file                      {len(adds)} vcd add ({res['scopes']['escaped']} escaped scopes)", flush=True)
        vtxt = pdir / "vsim.txt"
        try:
            steps.host("pwr_vsim", TB_DIR, f"bash {shlex.quote(str(pdir / 'vsim_cmd.sh'))} > "
                       f"{shlex.quote(str(vtxt))} 2>&1", pw.RUN_TIMEOUT, [("vsim", "tb_bin_opt", "vsim run")])
        finally:
            run = cl._text(vtxt)
            res["questa_elapsed_s"] = cl.elapsed(run)
        prog = pw.program_output(run)
        res["run"] = {"success": SUCCESS in run, "failure": FAILURE in run, "program_lines": prog[:20],
                      "tc_sram_impl_prints": cl.check.sram_lines(run),
                      "no_objects": len(re.findall(r"vsim-3561|No objects found", run)),
                      "errors": re.findall(r"^# \*\* Error.*$", run, re.M)[:10]}
        x = res["run"]
        if not x["success"] or x["failure"] or prog or x["tc_sram_impl_prints"] or x["no_objects"] or x["errors"]:
            raise cl.StepFailed("run", vtxt, f"[SUCCESS] {x['success']}, {len(prog)} program lines, "
                                             f"{x['no_objects']} 'no objects', {len(x['errors'])} errors")
        try:
            wins = pw.windows(cl._text(pdir / "obs_log.txt"), marks)
        except ValueError as e:
            raise cl.StepFailed("windows", pdir / "obs_log.txt", str(e)) from None
        res["windows"] = wins
        res["windows_rtl"] = against_rtl(wins, pre["rtl"]["output"])        # recorded, not a gate (X91)
        (pdir / "windows.json").write_text(json.dumps(wins, indent=2) + "\n")
        for w in res["windows_rtl"]:
            print(f"  window {w['mark']} {w['kind']:<16s} {w['cycles']:7d} cycles, plain RTL run {w['rtl']}, "
                  f"diff {w['diff']}", flush=True)
        vcd = pdir / "dut.vcd"
        if not vcd.is_file():
            raise cl.StepFailed("run", vtxt, "no dut.vcd")
        res["vcd_bytes"] = vcd.stat().st_size
        h = res["vcd_header"] = pw.vcd_header_counts(vcd)
        want = res["scopes"]["design_scopes"] + 3           # tb_bin, i_dut, the wrapper, then every design scope
        print(f"  dut.vcd                      {res['vcd_bytes'] / 1e9:.2f} GB, {h['vars']} $var, {h['scopes']} $scope "
              f"(want {want}), timescale {h['timescale']}", flush=True)
        if h["scopes"] != want:
            raise cl.StepFailed("vcd scopes", vtxt, f"{h['scopes']} $scope in dut.vcd, not {want}: a vcd add missed")
        res["vcd2saif"] = (subprocess.run([pwr.tool("vcd2saif"), "-help"], capture_output=True, text=True,
                                          check=False).stdout.splitlines() or ["unknown"])[0]
        pw.saif_jobs(vcd, wins, pdir, res, instance=TB_TOP)
        bad = [n for n, i in res["saif"].items() if i["status"] != "PASS"]
        res["status"], res["failed"] = ("PASS" if not bad else "FAIL"), ", ".join(f"saif {n}" for n in bad) or None
        if bad:
            res["failed_log"], res["failed_tail"] = f"pwr/{bad[0]}/vcd2saif.log", cl.tail(pdir / bad[0] / "vcd2saif.log")
    except (Exception, SystemExit) as e:  # noqa: BLE001 - recorded; the zip and the clean still done
        fail_note(res, e, "pwr", name, work)
    finally:
        (pdir / "dut.vcd").unlink(missing_ok=True)
        res["questa"] = cl.questa_version()
        res["seconds"].update(steps.times)
        res["seconds"]["total_before_pack"] = round(time.monotonic() - t_all, 1)
        res["memory"] = steps.peaks
        res["date"] = dt.datetime.now().isoformat(timespec="seconds")
        t = time.monotonic()
        try:
            files = {f"build/{f}": work / "build" / f for f in ("vlog.log", "vopt.log")}
            files.update({f: pdir / f for f in ("pwr.do", "vcd_add.do", "vsim_cmd.sh", "vsim.txt", "obs_log.txt",
                                                "windows.json")})
            for d in sorted(x for x in pdir.iterdir() if x.is_dir()):
                files.update({f"{d.name}/{f}": d / f for f in ("w.saif", "vcd2saif.log")})
            pack_under(pre["runz"], "pwr", work, files, res)
        except Exception as e:  # noqa: BLE001
            print(f"  could not pack pwr/ of {name}: {e!r}", flush=True)
        res["pack_s"] = round(time.monotonic() - t, 1)
        wrap_up(work, res, "clean-vsim clean-generated")
    return res


def pwr_step(r: dict, pts: dict, args) -> int:
    signal.signal(signal.SIGTERM, cl._sigterm)
    pre = preflight(r, pts, args, need_gls=True)
    name = r["run"]
    old = json.loads(arc.read(pre["runz"], "pwr/check.json")) if arc.has(pre["runz"], "pwr/check.json") else None
    current, why = pw.part1_current(old, pre["netlist_sha"], pre["quiet_sha"], pre["repos"]["snax_cluster"])
    if args.again or not current:
        print(f"snb pwr {name}: part 1 runs ({'--again' if args.again else why})", flush=True)
        res1 = part1(r, pre)
        print(pw.summary(name, res1).replace("cluster pwr", "snb pwr", 1) + f" (pack {res1.get('pack_s', 0):.0f} s)",
              flush=True)
        if res1["status"] != "PASS":
            return 1
    else:
        print(f"snb pwr {name}: part 1 skipped ({why})", flush=True)
        res1 = old
    print(f"snb pwr {name} (part 2): PT on {len(res1['windows'])} windows; work {TMP / name}", flush=True)
    pre2 = {"images": pre["images"], "repos": pre["repos"], "prov": {"snax_forge_commit": ""}, "synz": pre["synz"],
            "netlist_sha": pre["netlist_sha"], "quiet_sha": pre["quiet_sha"]}
    res2 = pw.part2({"point": name, "srams": r["config"]["srams"]}, pre2, args, res1, SITE)
    print(pw.summary2(name, res2).replace("cluster pwr", "snb pwr", 1) + f" (pack {res2.get('pack_s', 0):.0f} s)",
          flush=True)
    if res2["status"] != "PASS" and res2.get("failed_tail"):
        print(f"  last {TAIL} lines of {res2.get('failed_log')}:\n{res2['failed_tail']}", flush=True)
    return 0 if res2["status"] == "PASS" else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd, what, cores, again in (("rtl", "a run: its ELFs, then the plain one on the RTL with the macros", None, False),
                                    ("syn", "a config: DC on the whole cluster", 16, True),
                                    ("gls", "a run: the config's netlist in the same testbench", None, False),
                                    ("pwr", "a run: the quiet ELF on the netlist, a SAIF per window, PT", 16, True)):
        s = sub.add_parser(cmd, help=what)
        s.add_argument("name", help="a config (syn) or a run, <config>_<kernel>_<type>")
        if cores:
            s.add_argument("--cores", type=int, default=cores, help=f"DC's cores or PT's threads (default {cores})")
        if again:
            s.add_argument("--again", action="store_true",
                           help="syn: run DC though a kept netlist would do; pwr: run part 1 though it is current")
        s.add_argument("--allow-branch", action="store_true", help="snax_cluster's HEAD need not be on origin/main")
    a = ap.parse_args()
    pts = load()
    if a.cmd == "syn":
        return syn(config_of(pts, a.name), pts, a)
    return {"rtl": rtl, "gls": gls, "pwr": pwr_step}[a.cmd](run_of(pts, a.name), pts, a)


if __name__ == "__main__":
    sys.exit(main())
