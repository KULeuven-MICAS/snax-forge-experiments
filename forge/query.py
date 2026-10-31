#!/usr/bin/env python3
"""forge/query.py - what sim/sources/forge.py needs from snax-forge, answered by snax-forge's own code.

Runs inside snax-forge's pixi environment, with snax-forge as the working directory (sim/sources/forge.py
calls it as forge/bundles.py calls snax-forge's tasks: `pixi run --manifest-path $SNAX_FORGE/pixi.toml`,
PIXI_* and CONDA_* removed). It prints one JSON object on stdout.

  python forge/query.py point BUNDLE_DIR
      kernel: the recipe's kernel (recipes/<recipe>.json, point.json's recipe)
      ports:  per outer port of accelerator.json (inputs, then outputs, in its order) the container
              the design point's graph binds it to, as snax-forge's gen/rtl.py `vectors` finds it

  python forge/query.py cycles BUNDLE_DIR JOBS BEATS_JSON
      the group's busy cycles E - s of one run: gen/rtl.py's `group_counter` (snax-gvsoc's group rule,
      estimate/cycles.py's `group_cycles`, every input valid and the output ready), with JOBS and each
      unit's T its JOB_BEATS (BEATS_JSON: {unit: value}) or its fixed T, as the program writes them

  python forge/query.py ref KERNEL IN_NPZ OUT_NPZ
      the kernel's NumPy body (kernels/<...>/<KERNEL>.py, SPEC.func) on the arrays in IN_NPZ; the
      kernel's inout arrays (its outputs, zero-filled at the size the SPEC's descriptors give for N, the
      length of the first input) written to OUT_NPZ

snax-forge is not changed: only its modules are imported.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _bundle(d: str) -> tuple[Path, dict, dict, dict]:
    b = Path(d).resolve()
    return (b, json.loads((b / "bundle.json").read_text()), json.loads((b / "accelerator.json").read_text()),
            json.loads((b / "point.json").read_text()))


def cmd_point(bundle_dir: str) -> dict:
    from snax_forge.design import DesignPoint
    from snax_forge.design.streamers import instance_nodes
    from snax_forge.gen.accelerator import units
    from snax_forge.sandbox import Recipe

    b, bundle, acc, point = _bundle(bundle_dir)
    dp = Path(bundle["design_point"])
    if not dp.is_file():
        raise SystemExit(f"{dp}: the design point bundle.json names is not there (rebundle: pixi run forge-rtl)")
    p = DesignPoint.load(dp)
    found = units(p)[1]
    nodes = instance_nodes(p.graph)
    ports = []
    for side, ends in (("in", acc["inputs"]), ("out", acc["outputs"])):
        for end in ends:
            name, port = end.split(".", 1)
            inst, node = found[name], nodes[name]
            (bp,) = (x for x in inst.brm.interface.ports if x.name == port)
            if bp.direction != side:
                raise SystemExit(f"{end}: BRM port direction {bp.direction}, accelerator.json lists it as {side}")
            m = (node.inputs if side == "in" else node.outputs)[bp.name]
            ports.append({"end": end, "dir": side, "container": m.data})
    recipe = Recipe.load(Path("recipes") / f"{point['recipe']}.json")
    return {"kernel": recipe.kernel, "recipe": point["recipe"], "ports": ports}


def cmd_cycles(bundle_dir: str, jobs: str, beats: str) -> dict:
    from snax_forge.gen.accelerator import Accelerator
    from snax_forge.gen.rtl import group_counter

    _, _, acc, _ = _bundle(bundle_dir)
    a = Accelerator.from_dict(acc)
    if len(a.groups) != 1:
        raise SystemExit(f"{len(a.groups)} groups: one is supported")
    value, working = group_counter(a.groups[0], int(jobs), json.loads(beats))
    return {"cycles": value, "working": working}


def cmd_ref(kernel: str, in_npz: str, out_npz: str) -> dict:
    import numpy as np

    from snax_forge.sdfg.loader import load

    spec = load(kernel)
    ins = dict(np.load(in_npz))
    n = len(next(iter(ins.values())))
    arrays = {}
    for name, desc in spec.descriptors.items():
        if name in ins:
            arrays[name] = ins[name].copy()
        else:
            shape = [int(s.subs({x: n for x in s.free_symbols})) if hasattr(s, "free_symbols") else int(s)
                     for s in desc.shape]
            arrays[name] = np.zeros(shape, dtype=desc.dtype.as_numpy_dtype())
    with np.errstate(over="ignore"):
        spec.func(**arrays)
    outs = {k: arrays[k] for k in spec.inout}
    np.savez(out_npz, **outs)
    return {"kernel": kernel, "func": f"{spec.func.__module__}.{spec.func.__name__}", "outputs": list(outs)}


def main() -> int:
    cmd, *args = sys.argv[1:]
    fn = {"point": cmd_point, "cycles": cmd_cycles, "ref": cmd_ref}[cmd]
    print(json.dumps(fn(*args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
