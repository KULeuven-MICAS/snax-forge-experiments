#!/usr/bin/env python3
"""forge/bundles.py - snax-forge's accelerator bundles for the points in forge/points.json.

  pixi run forge-rtl [PATTERN ...] [--list] [--dry-run] [-j N] [--allow-dirty] [--set K=V ...] [--out DIR]

A point is one snax-forge recipe at one W, named as hls-exercises names its points (done/dot/forge3_w4); patterns
are shell globs over those names. Per point, in the snax-forge checkout (SNAX_FORGE, default ../snax-forge):
sandbox, design and bundle (a set starting with design., platform. or memory. goes to the design step, every other
to the sandbox: split_sets), packed into <DIR>/<point>.zip (DIR rtl/forge/) with point.json (recipe, W, sets,
dtypes, commit, dirty, date). A dirty bundle is refused unless --allow-dirty. find_recipe finds a recipe by name
under recipes/ (also used by forge/query.py). The steps, the environment and the dtypes are in forge/README.md.
Standard library and arc/arc.py only.
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
sys.path.insert(0, str(ROOT / "arc"))
import arc  # noqa: E402  arc/arc.py: a bundle is one zip

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


def find_recipe(name: str, forge: Path = FORGE) -> Path:
    """The recipe file of `name`, relative to the snax-forge checkout: recipes/**/<name>.json, recipes/custom/
    left out. Refuses a missing or an ambiguous name."""
    root = forge / "recipes"
    found = sorted(f for f in root.rglob(f"{name}.json")
                   if f.is_file() and not f.relative_to(root).parts[0] == "custom" and len(f.relative_to(root).parts) > 1)
    if not found:
        raise ValueError(f"no recipe {name!r} under {root} (recipes/custom/ left out)")
    if len(found) > 1:
        raise ValueError(f"recipe {name!r} is ambiguous under {root}: {[str(f.relative_to(root)) for f in found]}")
    return found[0].relative_to(forge)


def point_sets(p: dict, sets: list[str]) -> list[str]:
    """The point's own sets (points.json), then the global --set values."""
    own = p.get("sets", [])
    if not isinstance(own, list) or not all(isinstance(x, str) and "=" in x for x in own):
        raise ValueError(f"{p['point']}: sets must be a list of 'K=V' strings, got {own!r}")
    return [*own, *sets]


DESIGN_HEADS = ("design", "platform", "memory")      # snax-forge's design step takes these --set paths (TOOL.md)


def split_sets(sets: list[str]) -> tuple[list[str], list[str]]:
    """(the sandbox's sets, the design step's): a set whose name starts with design., platform. or memory.
    (design.narrow_mul=true, design.data=full) is the design step's, the rest (N=2048, types=i8, dtypes.C=int16)
    the recipe's. snax-forge's sandbox refuses a design set, and its design step reads only these."""
    design = [x for x in sets if x.split("=", 1)[0].split(".", 1)[0] in DESIGN_HEADS and "." in x.split("=", 1)[0]]
    return [x for x in sets if x not in design], design


def work_name(p: dict, sets: list[str]) -> str:
    extra = "".join("_" + re.sub(r"[^A-Za-z0-9]", "", s) for s in sets)
    extra += "".join(f"_{d}" for d in sorted(set(p.get("dtypes", {}).values())))
    return f"{p['recipe']}_w{p['W']}{extra}"


RECIPES_TMP = ROOT / "tmp" / "forge_recipes"


def recipe_arg(p: dict, name: str) -> str:
    """The sandbox's recipe: snax-forge's file (relative to the checkout), or with the point's `dtypes` a copy
    of it with that field set, tmp/forge_recipes/<name>.json (absolute; run_point deletes it)."""
    rel = find_recipe(p["recipe"])
    dts = p.get("dtypes")
    if not dts:
        return str(rel)
    if not isinstance(dts, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in dts.items()):
        raise ValueError(f"{p['point']}: dtypes must map container names to dtype names, got {dts!r}")
    r = json.loads((FORGE / rel).read_text())
    r["dtypes"] = {**r.get("dtypes", {}), **dts}
    RECIPES_TMP.mkdir(parents=True, exist_ok=True)
    f = RECIPES_TMP / f"{name}.json"
    f.write_text(json.dumps(r, indent=1) + "\n")
    return str(f)


def last_snaxdfg(folder: Path) -> Path:
    """The sandbox's last step: the .snaxdfg with the highest numeric prefix (<k>_<step>.snaxdfg)."""
    found = [(int(m.group(1)), f) for f in folder.glob("*.snaxdfg")
             if (m := re.match(r"(\d+)_", f.name))]
    if not found:
        raise RuntimeError(f"no <k>_*.snaxdfg in {folder}")
    return max(found)[1]


def steps(p: dict, sets: list[str], out: Path) -> tuple[list[str], list[str], list[str]]:
    sets = point_sets(p, sets)
    name = work_name(p, sets)
    sandbox = f"out/sandbox/syn1/{name}"
    design = f"out/design/syn1/{name}"
    own, design_sets = split_sets(sets)
    s1 = [recipe_arg(p, name), "--set", f"{p.get('w_param', 'W')}={p['W']}"]      # mvt_v5's width is W_x1
    for s in own:
        s1 += ["--set", s]
    s1 += ["--out", sandbox]
    s2 = ["<last .snaxdfg of " + sandbox + ">", "--platform", PLATFORM]
    for s in design_sets:
        s2 += ["--set", s]
    s2 += ["--out", design]
    s3 = [f"{design}/design_point.json", "--out", str(out / p["point"])]
    return s1, s2, s3


def run_point(p: dict, args) -> dict:
    t0 = time.monotonic()
    dest = args.out / p["point"]
    try:
        s1, s2, s3 = steps(p, args.set, args.out)
    except ValueError as e:
        print(f"failed: recipe  {p['point']}: {e}", flush=True)
        return {"point": p["point"], "status": f"failed: recipe ({e})", "seconds": 0.0, "commit": "", "dirty": "",
                "error": str(e)}
    sandbox, design = Path(FORGE / s1[-1]), Path(FORGE / s2[-1])      # each step's --out is its last argument
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
                        "sets": point_sets(p, args.set), "dtypes": p.get("dtypes", {}),
                        "recipe_file": str(find_recipe(p["recipe"])), "date": dt.datetime.now().isoformat(timespec="seconds"),
                    }, indent=2) + "\n")
                    res["status"] = "made" + (" (dirty, allowed)" if b["dirty"] else "")
    except Exception as e:  # noqa: BLE001 - reported per point
        res["status"], res["error"] = "failed: driver", repr(e)
    finally:
        log.close()
        if s1[0].startswith(str(RECIPES_TMP)):
            Path(s1[0]).unlink(missing_ok=True)
    if not res["status"].startswith("made"):
        for f in dest.iterdir():
            if f.name != LOG:
                shutil.rmtree(f) if f.is_dir() else f.unlink()
    arc.pack_bundle(dest)                   # <DIR>/<point>.zip, test-read; the folder goes
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
                    help="more --set (e.g. N=2048 for the sandbox, design.narrow_mul=true for the design step); "
                         "also tags the sandbox and design folders")
    ap.add_argument("--out", type=Path, default=ROOT / "rtl" / "forge",
                    help="where the bundles go, one zip per point (default rtl/forge)")
    args = ap.parse_args()
    args.out = args.out.resolve()
    pts = select(load_points(), args.patterns)
    if not pts:
        sys.exit("no point matches (--list shows them)")
    if args.list:
        for p in pts:
            print(f"{p['point']}  recipe {p['recipe']}  W {p['W']}  sets {point_sets(p, args.set)}")
        return 0
    if args.dry_run:
        print(f"# snax-forge {FORGE}; env without PIXI_*/CONDA_* and {ROOT / '.pixi'} on PATH")
        for p in pts:
            s1, s2, s3 = steps(p, args.set, args.out)
            print(f"\n# {p['point']}")
            for name, argv in (("sandbox", s1), ("design", s2), ("bundle", s3)):
                print(" ".join(forge_cmd(name, *argv)))
        shutil.rmtree(RECIPES_TMP, ignore_errors=True)     # the dtypes copies written for the listing
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
    if RECIPES_TMP.is_dir() and not any(RECIPES_TMP.iterdir()):
        RECIPES_TMP.rmdir()                                  # the dtypes copies are gone with their points
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
