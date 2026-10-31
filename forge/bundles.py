#!/usr/bin/env python3
"""forge/bundles.py - snax-forge's accelerator bundles for the points in forge/points.json.

A point is one snax-forge recipe at one W, named as hls-exercises names its
points (<tier>/<kernel>/<case>_w<W>, e.g. done/dot/forge3_w4), so a forge row
joins the HLS rows of the same kernel and W. Patterns are shell globs over
those names.

  pixi run forge-rtl [PATTERN ...] [--list] [--dry-run] [-j N] [--allow-dirty]
                     [--set K=V ...] [--out DIR]

Per point, in the snax-forge checkout (SNAX_FORGE, default ../snax-forge from
the repo root), each through `pixi run --manifest-path $SNAX_FORGE/pixi.toml`:

  1. sandbox recipes/<r>.json --set W=<w> [--set K=V ...] --out out/sandbox/syn1/<r>_w<w>[_<K><V>...]
  2. design <the last .snaxdfg of that folder> --platform platforms/snax_forge.json
            --out out/design/syn1/<r>_w<w>[_<K><V>...]
  3. bundle out/design/syn1/<...>/design_point.json --out <DIR>/<point>/

DIR is rtl/forge/ in this repo (git ignores rtl/: a bundle is rebuilt from its
commit). A point's folder is emptied first. bundle.json names the commit and
whether snax-forge's work tree was dirty; a dirty bundle is refused (its folder
emptied but for the log) unless --allow-dirty. A bundle that is kept gets
point.json: point, recipe, W, snax_forge_commit, dirty, date. Each point's
task output is in <DIR>/<point>/forge-rtl.log.

The tasks run inside this repo's `pixi run`, whose PIXI_* and CONDA_*
variables and .pixi/ PATH entries would make the inner pixi take this repo's
environment; they are removed, and before any point the driver checks that
the inner CONDA_PREFIX is under $SNAX_FORGE/.pixi/envs/.

The first point runs alone when hw/chisel's Emit classpath
(hw/chisel/target/emit-classpath.txt) is not there yet: the first Emit exports
it through sbt, and parallel first calls would race. --set adds to the sandbox
step (e.g. --set N=2048) and to the sandbox and design folder names.
Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTS = ROOT / "forge" / "points.json"
FORGE = Path(os.environ.get("SNAX_FORGE", ROOT.parent / "snax-forge")).resolve()
PLATFORM = "platforms/snax_forge.json"
CLASSPATH = FORGE / "hw" / "chisel" / "target" / "emit-classpath.txt"
LOG = "forge-rtl.log"
TAIL = 25  # lines of a failed task's output printed


def load_points() -> list[dict]:
    pts = json.loads(POINTS.read_text())
    names = [p["point"] for p in pts]
    if len(set(names)) != len(names):
        sys.exit(f"{POINTS}: duplicate point names")
    return pts


def select(points: list[dict], patterns: list[str]) -> list[dict]:
    if not patterns:
        return points
    return [p for p in points if any(fnmatch.fnmatchcase(p["point"], pat) for pat in patterns)]


def inner_env() -> dict:
    """The environment for snax-forge's pixi: this repo's pixi and conda variables removed, and
    PATH without this repo's .pixi/ entries."""
    own = str(ROOT / ".pixi")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIXI_", "CONDA_"))}
    env["PATH"] = os.pathsep.join(d for d in os.environ.get("PATH", "").split(os.pathsep)
                                  if d and not d.startswith(own))
    return env


def pixi_exe() -> str:
    exe = os.environ.get("PIXI_EXE") or shutil.which("pixi", path=inner_env()["PATH"])
    if not exe:
        sys.exit("pixi not found (PIXI_EXE or PATH)")
    return exe


def forge_cmd(task: str, *args: str) -> list[str]:
    return [pixi_exe(), "run", "--manifest-path", str(FORGE / "pixi.toml"), task, *args]


def check_env() -> str:
    """The inner pixi's CONDA_PREFIX, which must be one of snax-forge's environments."""
    done = subprocess.run(forge_cmd("printenv", "CONDA_PREFIX"), cwd=FORGE, env=inner_env(),
                          capture_output=True, text=True, check=False)
    prefix = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""
    if done.returncode or not Path(prefix).resolve().is_relative_to(FORGE / ".pixi" / "envs"):
        sys.exit(f"the inner pixi did not resolve snax-forge's environment: CONDA_PREFIX '{prefix}', "
                 f"exit {done.returncode}\n{done.stderr.strip()}")
    return prefix


def work_name(p: dict, sets: list[str]) -> str:
    extra = "".join("_" + re.sub(r"[^A-Za-z0-9]", "", s) for s in sets)
    return f"{p['recipe']}_w{p['W']}{extra}"


def last_snaxdfg(folder: Path) -> Path:
    """The sandbox's last step: the .snaxdfg with the highest numeric prefix (<k>_<step>.snaxdfg)."""
    found = [(int(m.group(1)), f) for f in folder.glob("*.snaxdfg")
             if (m := re.match(r"(\d+)_", f.name))]
    if not found:
        raise RuntimeError(f"no <k>_*.snaxdfg in {folder}")
    return max(found)[1]


def steps(p: dict, sets: list[str], out: Path) -> tuple[list[str], list[str], list[str]]:
    name = work_name(p, sets)
    sandbox = f"out/sandbox/syn1/{name}"
    design = f"out/design/syn1/{name}"
    s1 = ["recipes/" + p["recipe"] + ".json", "--set", f"W={p['W']}"]
    for s in sets:
        s1 += ["--set", s]
    s1 += ["--out", sandbox]
    s2 = ["<last .snaxdfg of " + sandbox + ">", "--platform", PLATFORM, "--out", design]
    s3 = [f"{design}/design_point.json", "--out", str(out / p["point"])]
    return s1, s2, s3


def run_point(p: dict, args) -> dict:
    t0 = time.monotonic()
    dest = args.out / p["point"]
    s1, s2, s3 = steps(p, args.set, args.out)
    sandbox, design = Path(FORGE / s1[-1]), Path(FORGE / s2[-1])
    res = {"point": p["point"], "status": "", "seconds": 0.0, "commit": "", "dirty": "", "error": ""}
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for d in (sandbox, design):
        if d.exists():
            shutil.rmtree(d)
    log = (dest / LOG).open("w")
    env = inner_env()

    def task(name: str, argv: list[str]) -> bool:
        cmd = forge_cmd(name, *argv)
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        done = subprocess.run(cmd, cwd=FORGE, env=env, capture_output=True, text=True, check=False)
        log.write(done.stdout + done.stderr + f"[exit {done.returncode}]\n\n")
        log.flush()
        if done.returncode:
            tail = (done.stdout + done.stderr).rstrip().splitlines()[-TAIL:]
            res["status"] = f"failed: {name} (exit {done.returncode})"
            res["error"] = "\n".join(tail)
        return done.returncode == 0

    try:
        if task("sandbox", s1):
            s2[0] = str(last_snaxdfg(sandbox).relative_to(FORGE))
            if task("design", s2) and task("bundle", s3):
                b = json.loads((dest / "bundle.json").read_text())
                res["commit"], res["dirty"] = b["snax_forge_commit"], b["dirty"]
                if b["dirty"] and not args.allow_dirty:
                    res["status"] = "refused: dirty (snax-forge's work tree had changes)"
                    log.write(f"refused: bundle.json has dirty: true (commit {b['snax_forge_commit']})\n")
                else:
                    (dest / "point.json").write_text(json.dumps({
                        "point": p["point"], "recipe": p["recipe"], "W": p["W"],
                        "snax_forge_commit": b["snax_forge_commit"], "dirty": b["dirty"],
                        "sets": args.set, "date": dt.datetime.now().isoformat(timespec="seconds"),
                    }, indent=2) + "\n")
                    res["status"] = "made" + (" (dirty, allowed)" if b["dirty"] else "")
    except Exception as e:  # noqa: BLE001 - reported per point
        res["status"], res["error"] = "failed: driver", repr(e)
    finally:
        log.close()
    if not res["status"].startswith("made"):
        for f in dest.iterdir():
            if f.name != LOG:
                shutil.rmtree(f) if f.is_dir() else f.unlink()
    res["seconds"] = time.monotonic() - t0
    print(f"{res['status']:<10}  {p['point']}  {res['seconds']:.1f} s", flush=True)
    if res["error"]:
        print("  " + res["error"].replace("\n", "\n  "), flush=True)
    return res


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patterns", nargs="*", help="globs over the point names, e.g. 'done/dot/forge3_*'")
    ap.add_argument("--list", action="store_true", help="list the points a pattern picks")
    ap.add_argument("--dry-run", action="store_true", help="print the tasks, run nothing")
    ap.add_argument("-j", "--jobs", type=int, default=1, help="points at once (default 1)")
    ap.add_argument("--allow-dirty", action="store_true", help="keep a bundle whose bundle.json says dirty")
    ap.add_argument("--set", action="append", default=[], metavar="K=V",
                    help="more --set for the sandbox step (e.g. N=2048); also tags the sandbox and design folders")
    ap.add_argument("--out", type=Path, default=ROOT / "rtl" / "forge",
                    help="where the bundles go, one folder per point (default rtl/forge)")
    args = ap.parse_args()
    args.out = args.out.resolve()
    pts = select(load_points(), args.patterns)
    if not pts:
        sys.exit("no point matches (--list shows them)")
    if args.list:
        for p in pts:
            print(f"{p['point']}  recipe {p['recipe']}  W {p['W']}")
        return 0
    if args.dry_run:
        print(f"# snax-forge {FORGE}; env without PIXI_*/CONDA_* and {ROOT / '.pixi'} on PATH")
        for p in pts:
            s1, s2, s3 = steps(p, args.set, args.out)
            print(f"\n# {p['point']}")
            for name, argv in (("sandbox", s1), ("design", s2), ("bundle", s3)):
                print(" ".join(forge_cmd(name, *argv)))
        return 0
    if not (FORGE / "pixi.toml").is_file():
        sys.exit(f"no snax-forge checkout at {FORGE} (set SNAX_FORGE)")
    prefix = check_env()
    print(f"snax-forge {FORGE}, inner CONDA_PREFIX {prefix}; {len(pts)} points, -j {args.jobs}", flush=True)
    t0 = time.monotonic()
    results = []
    rest = pts
    if not CLASSPATH.is_file() and args.jobs > 1:
        print(f"no {CLASSPATH.relative_to(FORGE)} yet: {pts[0]['point']} runs alone first", flush=True)
        results.append(run_point(pts[0], args))
        rest = pts[1:]
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        results += list(pool.map(lambda p: run_point(p, args), rest))
    wall = time.monotonic() - t0
    made = [r for r in results if r["status"].startswith("made")]
    print(f"\n{len(made)} made, {len(results) - len(made)} not, in {wall:.0f} s "
          f"(sum of points {sum(r['seconds'] for r in results):.0f} s)")
    commits = sorted({str(r["commit"]) for r in results if r["commit"]})
    print(f"snax_forge_commit: {', '.join(commits) or '-'}")
    for r in results:
        if not r["status"].startswith("made"):
            print(f"  {r['point']}: {r['status']}")
    return 0 if len(made) == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
