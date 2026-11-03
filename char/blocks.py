#!/usr/bin/env python3
"""char/blocks.py - snax-forge's catalogue blocks alone, for the points in char/points.json (CHAR1).

A point is one catalogue datapath of snax-forge (hw/chisel/blocks.json) at
full params, named <block>/<case>_w<W> (e.g. tree/add_w8, link/d4_w1).
Patterns are shell globs over those names.

  pixi run char-rtl [PATTERN ...] [--list] [--dry-run] [--allow-dirty]

Every selected point goes into one call of snax-forge's gen-block (its
snax_forge/gen/block.py, C§17's --block) in the snax-forge checkout
(SNAX_FORGE, default ../snax-forge from the repo root), through
`pixi run --manifest-path $SNAX_FORGE/pixi.toml`, with forge/bundles.py's
environment (this repo's PIXI_* and CONDA_* variables and .pixi/ PATH entries
removed, the inner CONDA_PREFIX checked). gen-block's list is written to
rtl/char/gen-block.json and its output to rtl/char/char-rtl.log. Each block is
the top module with the asynchronous active-high reset it has inside an
accelerator: rtl/char/<point>/sv/, one file per module, and emitted.json
(block, params, top, modules, files). A point's folder is emptied first.

A kept point gets point.json: point, datapath, params, snax_forge_commit,
dirty, date. The commit and dirty are snax-forge's `git rev-parse HEAD` and
`git status --porcelain`, as its bundle.py records them, taken before and
after the call (dirty if either is). A dirty checkout is refused before
anything runs unless --allow-dirty. git ignores rtl/: a block is rebuilt from
its commit. Standard library only.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from forge.bundles import FORGE, check_env, forge_cmd, inner_env  # noqa: E402

POINTS = ROOT / "char" / "points.json"
OUT = ROOT / "rtl" / "char"
LIST = OUT / "gen-block.json"
LOG = OUT / "char-rtl.log"
TAIL = 25  # lines of a failed call's output printed


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


def entries(pts: list[dict]) -> list[dict]:
    """gen-block's list: datapath, params and the point's folder."""
    return [{"datapath": p["datapath"], "params": p["params"], "out": str(OUT / p["point"])} for p in pts]


def git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(FORGE), *args], capture_output=True, text=True, check=True)
    return done.stdout


def provenance() -> tuple[str, bool]:
    """snax-forge's commit and whether its work tree has changes (its bundle.py's rule)."""
    return git("rev-parse", "HEAD").strip(), bool(git("status", "--porcelain").strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("patterns", nargs="*", help="globs over the point names, e.g. 'tree/*'")
    ap.add_argument("--list", action="store_true", help="list the points a pattern picks")
    ap.add_argument("--dry-run", action="store_true", help="print the list and the call, run nothing")
    ap.add_argument("--allow-dirty", action="store_true", help="run on a snax-forge checkout with changes")
    args = ap.parse_args()
    pts = select(load_points(), args.patterns)
    if not pts:
        sys.exit("no point matches (--list shows them)")
    if args.list:
        for p in pts:
            print(f"{p['point']}  {p['datapath']}  {json.dumps(p['params'])}")
        return 0
    cmd = forge_cmd("gen-block", str(LIST))
    if args.dry_run:
        print(f"# snax-forge {FORGE}; env without PIXI_*/CONDA_* and {ROOT / '.pixi'} on PATH")
        print(f"# {LIST.relative_to(ROOT)}:")
        print(json.dumps(entries(pts), indent=1))
        print(" ".join(cmd))
        return 0
    if not (FORGE / "pixi.toml").is_file():
        sys.exit(f"no snax-forge checkout at {FORGE} (set SNAX_FORGE)")
    commit, dirty = provenance()
    if dirty and not args.allow_dirty:
        sys.exit(f"refused: snax-forge's work tree at {FORGE} has changes (commit {commit}); --allow-dirty runs anyway")
    prefix = check_env()
    print(f"snax-forge {FORGE} at {commit}{' (dirty, allowed)' if dirty else ''}, "
          f"inner CONDA_PREFIX {prefix}; {len(pts)} points", flush=True)
    t0 = time.monotonic()
    for p in pts:
        dest = OUT / p["point"]
        if dest.exists():
            shutil.rmtree(dest)
    OUT.mkdir(parents=True, exist_ok=True)
    LIST.write_text(json.dumps(entries(pts), indent=1) + "\n")
    done = subprocess.run(cmd, cwd=FORGE, env=inner_env(), capture_output=True, text=True, check=False)
    LOG.write_text(f"$ {' '.join(cmd)}\n" + done.stdout + done.stderr + f"[exit {done.returncode}]\n")
    after, dirty_after = provenance()
    dirty = dirty or dirty_after
    made, failed = [], []
    for p in pts:
        dest = OUT / p["point"]
        f = dest / "emitted.json"
        emitted = json.loads(f.read_text()) if f.is_file() else {}
        if done.returncode or after != commit or (emitted.get("block"), emitted.get("params")) != (
                p["datapath"], p["params"]):
            failed.append(p["point"])
            continue
        (dest / "point.json").write_text(json.dumps({
            "point": p["point"], "datapath": p["datapath"], "params": p["params"],
            "snax_forge_commit": commit, "dirty": dirty,
            "date": dt.datetime.now().isoformat(timespec="seconds"),
        }, indent=2) + "\n")
        made.append(p["point"])
        print(f"made  {p['point']}  {emitted['top']}  ({len(emitted['files'])} file(s))", flush=True)
    if failed:
        for name in failed:
            if (OUT / name).exists():
                shutil.rmtree(OUT / name)
        tail = (done.stdout + done.stderr).rstrip().splitlines()[-TAIL:]
        why = (f"gen-block exit {done.returncode}" if done.returncode else
               f"snax-forge moved from {commit} to {after}" if after != commit else "emitted.json not as asked")
        print(f"failed ({why}): {', '.join(failed)}\n  " + "\n  ".join(tail), flush=True)
    print(f"\n{len(made)} made, {len(failed)} not, in {time.monotonic() - t0:.0f} s; "
          f"snax_forge_commit {commit}; log {LOG.relative_to(ROOT)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
