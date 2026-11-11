#!/usr/bin/env python3
"""cluster/hwcost.py - snax-forge's HWCOST for a cluster point, to compare with its synthesized cluster (X72).

    pixi run cluster-hwcost <point> [--tech nangate45] [--platform platforms/snax_forge.json]

The point's recipe, W and sets come from cluster/points.json; the estimate is snax-forge's own (D167, its C§20
`cost`), on the recipe's last graph and the platform file, the way `pixi run flow` prices a design. It runs in
snax-forge's environment: this script calls itself there (`pixi run --manifest-path <snax-forge>/pixi.toml python
cluster/hwcost.py --inner ...`, in snax-forge's folder), which prints the estimate as JSON; snax-forge is read from
SNAX_FORGE (default ../snax-forge), and SNAX_FORGE_PYTHON, if set, is the Python run instead of pixi (a venv with
snax-forge installed, where pixi is not there). Writes results/cluster/<tech>/hwcost/<point>.json: the point, recipe, W, sets,
platform, tech, snax-forge's commit and whether its tree was clean, and the estimate's `cost` as snax-forge gives it.
The cluster's own design came from the snax-forge commit in synth_dc.csv; HWCOST is priced at the commit recorded
here, so a later cost-model change shows up as a new file, not as a change to the netlist. Standard library only
outside snax-forge.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTS = ROOT / "cluster" / "points.json"
FORGE = Path(os.environ.get("SNAX_FORGE", ROOT.parent / "snax-forge")).resolve()
PLATFORM = "platforms/snax_forge.json"


def params(point: dict) -> dict[str, int]:
    """The recipe's parameters: W and the point's `sets` (NAME=VALUE, recipe parameters only)."""
    out = {"W": int(point["W"])}
    for s in point.get("sets", []):
        name, _, value = s.partition("=")
        if not value or "." in name:
            raise ValueError(f"set {s!r}: only recipe parameters (NAME=INT) are priced here")
        out[name] = int(value)
    return out


def find(point: str, points: Path = POINTS) -> dict:
    for p in json.loads(points.read_text())["points"]:
        if p["point"] == point:
            return p
    raise SystemExit(f"no point {point!r} in {points}")


def inner(recipe: str, prm: dict[str, int], platform: str, tech: str) -> dict:
    """In snax-forge's environment, from its folder: the estimate's `cost` for the recipe at `prm`."""
    sys.path.insert(0, str(Path.cwd()))
    from snax_forge.design import Platform
    from snax_forge.dfg.import_sdfg import import_kernel
    from snax_forge.estimate import estimate
    from snax_forge.sandbox import Recipe, apply_recipe
    from snax_forge.sandbox.recipe import find_recipe

    r = Recipe.load(find_recipe(recipe)).with_params(prm)
    graph = apply_recipe(r, import_kernel(r.kernel, dict(r.dtypes or {}) or None))[-1].graph
    return estimate(graph, Platform.load(Path(platform)), tech).to_dict()["cost"]


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(FORGE), *args], check=True, capture_output=True, text=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("point", nargs="?")
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--platform", default=PLATFORM)
    ap.add_argument("--inner", help=argparse.SUPPRESS)          # recipe name, in snax-forge's environment
    ap.add_argument("--params", help=argparse.SUPPRESS)         # JSON, with --inner
    a = ap.parse_args()
    if a.inner:
        print(json.dumps(inner(a.inner, json.loads(a.params), a.platform, a.tech)))
        return 0
    if not a.point:
        ap.error("a point is needed")
    p = find(a.point)
    prm = params(p)
    py = os.environ.get("SNAX_FORGE_PYTHON")
    head = [py] if py else ["pixi", "run", "--manifest-path", str(FORGE / "pixi.toml"), "python"]
    cmd = [*head, str(Path(__file__).resolve()), "--inner", p["recipe"], "--params", json.dumps(prm), "--platform", a.platform, "--tech", a.tech]
    run = subprocess.run(cmd, cwd=FORGE, capture_output=True, text=True)
    if run.returncode:
        sys.stderr.write(run.stderr[-3000:])
        return run.returncode
    cost = json.loads(run.stdout.strip().splitlines()[-1])
    out = {"point": a.point, "recipe": p["recipe"], "W": p["W"], "sets": p.get("sets", []), "platform": a.platform,
           "tech": a.tech, "snax_forge_commit": git("rev-parse", "HEAD"),
           "snax_forge_clean": not git("status", "--porcelain", "--untracked-files=no"), "cost": cost}
    path = ROOT / "results" / "cluster" / a.tech / "hwcost" / f"{a.point}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n")
    parts = {k: round(v["area"]) for k, v in cost["parts"].items()}
    print(f"{path.relative_to(ROOT)}: {parts}, total {round(cost['area'])} um2, snax-forge {out['snax_forge_commit'][:8]}"
          f"{'' if out['snax_forge_clean'] else ' (dirty)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
