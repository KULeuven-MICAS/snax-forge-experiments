#!/usr/bin/env python3
"""forge/query.py - what sim/sources/forge.py needs from snax-forge, answered by snax-forge's own code.

Runs inside snax-forge's pixi environment, with snax-forge as the working directory (sim/sources/forge.py
calls it as forge/bundles.py calls snax-forge's tasks: `pixi run --manifest-path $SNAX_FORGE/pixi.toml`,
PIXI_* and CONDA_* removed). It prints one JSON object on stdout.

  python forge/query.py point BUNDLE_DIR
      kernel: the recipe's kernel (point.json's recipe, found under recipes/**/ by forge/bundles.py's find_recipe)
      ports:  per outer port of accelerator.json (inputs, then outputs, in its order) the container
              the design point's graph binds it to, as snax-forge's gen/rtl.py `vectors` finds it
      baked:  {container: value} of the recipe's bake_scalar steps with a number (axpy_baked's alpha = 3)

  python forge/query.py program BUNDLE_DIR
      what snax-forge's LOWER writes for the design point's own size (lower/derive.py's task_list, the C
      backend's job_writes and scalar slots, lower/c.py), for its one accelerator task:
      symbols   the graph's bound symbols (the size the design point was made at: the point's sets)
      n         the task's firings; writes [[unit, CSR, value], ...] JOBS then each JOB_BEATS, as job_writes
      scalars   [{unit, slot, container, dtype, csrs}] each slot read from a scalar container (axpy's k1 from
                alpha): its R/W CSRs (K1, or K1_LO and K1_HI at 64 bits, low word first, gen/accelerator.py's
                scalar_csrs), written with the container's value before START
      streams   per streamer task {end, component, dir, container, shape, beats, lanes, order, identity}:
                order the container's flat (row-major) element index of each element the streamer visits,
                beat by beat and lane 0 first (lower/derive.py's addresses over the task's bounds and strides,
                mapped back through the container's L1 layout); identity when it is 0, 1, 2, ...

  python forge/query.py cycles BUNDLE_DIR JOBS BEATS_JSON
      the group's busy cycles E - s of one run: gen/rtl.py's `group_counter` (snax-gvsoc's group rule,
      estimate/cycles.py's `group_cycles`, every input valid and the output ready), with JOBS and each
      unit's T its JOB_BEATS (BEATS_JSON: {unit: value}) or its fixed T, as the program writes them

  python forge/query.py ref KERNEL IN_NPZ OUT_NPZ [SYMBOLS_JSON [DTYPES_JSON]]
      the kernel's NumPy body (kernels/<...>/<KERNEL>.py, SPEC.func) on the arrays in IN_NPZ (a scalar
      container, axpy's alpha, as a 0-d array cast to its descriptor's dtype); the kernel's inout arrays
      not given (its outputs, zero-filled at the size the SPEC's descriptors give for SYMBOLS_JSON, else
      every symbol = N, the length of the first input) written to OUT_NPZ; an inout array given (axpy's y)
      is updated in place and written too. DTYPES_JSON ({container: dtype}, the point's, X57) replaces the
      descriptors' dtypes, as the recipe's dtypes do in the bundle (relu, matadd and axpy are int32 kernels).

snax-forge is not changed: only its modules are imported.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundles import find_recipe  # noqa: E402  one resolver for both (recipes/**/<name>.json, custom/ left out)


def flat(acc: dict) -> dict:
    """accelerator.json's groups, inputs and outputs over its accelerators (D157's nested form), or as written
    in the flat form of the SYN1 bundles (f9764d5)."""
    if "accelerators" not in acc:
        return acc
    a = acc["accelerators"]
    return {"groups": [g for x in a for g in x["groups"]], "inputs": [p for x in a for p in x["inputs"]],
            "outputs": [p for x in a for p in x["outputs"]]}


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
    found = {u: inst for mine in units(p).values() for u, inst in mine.items()}
    nodes = instance_nodes(p.graph)
    ports = []
    fa = flat(acc)
    for side, ends in (("in", fa["inputs"]), ("out", fa["outputs"])):
        for end in ends:
            name, port = end.split(".", 1)
            inst, node = found[name], nodes[name]
            (bp,) = (x for x in inst.brm.interface.ports if x.name == port)
            if bp.direction != side:
                raise SystemExit(f"{end}: BRM port direction {bp.direction}, accelerator.json lists it as {side}")
            m = (node.inputs if side == "in" else node.outputs)[bp.name]
            ports.append({"end": end, "dir": side, "container": m.data})
    recipe = Recipe.load(find_recipe(point["recipe"], Path.cwd()))
    baked = {st.params["container"]: st.params["value"] for st in recipe.steps
             if st.transform == "bake_scalar" and isinstance(st.params.get("value"), int)}
    return {"kernel": recipe.kernel, "recipe": point["recipe"], "ports": ports, "baked": baked}


def cmd_program(bundle_dir: str) -> dict:
    import numpy as np

    from snax_forge.design import DesignPoint
    from snax_forge.design.streamers import instance_nodes
    from snax_forge.gen.accelerator import scalar_csrs
    from snax_forge.lower.c import accelerators, job_writes
    from snax_forge.lower.derive import addresses, task_list
    from snax_forge.lower.tasks import check_values

    b, bundle, acc, _ = _bundle(bundle_dir)
    dp = Path(bundle["design_point"])
    if not dp.is_file():
        raise SystemExit(f"{dp}: the design point bundle.json names is not there (rebundle: pixi run forge-rtl)")
    p = DesignPoint.load(dp)
    tl = task_list(p)
    check_values(tl, p)
    accel = tl.of_type("accel")
    if len(accel) != 1:
        raise SystemExit(f"{len(accel)} accelerator tasks: one is supported")
    (a,) = accel
    units = {u: inst for us in accelerators(p).values() for u, inst in us.items()}
    jdesc = {u["name"]: u for ac in acc["accelerators"] for g in ac["groups"] for u in g["units"]}
    fixed = {u for u, d in jdesc.items() if "T" in d.get("params", {})}
    linked = "n" not in a.values           # a linked group's values are by unit
    mine = list(a.values) if linked else [a.component]
    writes = [[u, k, int(v)] for u, k, v in job_writes({u: units[u] for u in mine}, a.values, fixed)]
    by_unit = a.values if linked else {a.component: a.values}
    scalars = []
    for u in mine:
        for slot in units[u].read:
            dtype = jdesc[u].get("scalars", {})[slot]
            scalars.append({"unit": u, "slot": slot, "container": by_unit[u][slot]["from"], "dtype": dtype,
                            "csrs": scalar_csrs(slot, dtype)})
    nodes = instance_nodes(p.graph)
    streams = []
    for c in tl.of_type("streamer"):
        st = p.streamers[c.component]
        if st.num_slc != 1:
            raise SystemExit(f"{c.component}: num_slc {st.num_slc}; only one element per channel word is mapped")
        node = nodes[st.instance]
        m = (node.outputs if st.write else node.inputs)[st.port]
        lay = p.memory.layouts[m.data]["l1"]
        visit = addresses(c.values, list(st.spatial_bounds))              # (beats, lanes) byte addresses
        idx = np.indices(lay.shape).reshape(len(lay.shape), -1).T         # every element, row-major
        where = {int(x): i for i, x in enumerate(lay.address(idx))}
        try:
            order = [where[int(x)] for x in visit.ravel()]
        except KeyError as e:
            raise SystemExit(f"{c.component}: address {e} is no element of {m.data}'s L1 layout") from None
        streams.append({"end": f"{st.instance}.{st.port}", "component": c.component,
                        "dir": "out" if st.write else "in", "container": m.data, "shape": list(lay.shape),
                        "beats": int(visit.shape[0]), "lanes": int(visit.shape[1]), "order": order,
                        "identity": order == list(range(len(order)))})
    return {"symbols": {k: int(v) for k, v in p.graph.bound_symbols.items()}, "task": a.task_name,
            "n": int(a.values["n"]) if not linked else None, "writes": writes, "scalars": scalars,
            "streams": streams}


def cmd_cycles(bundle_dir: str, jobs: str, beats: str) -> dict:
    from snax_forge.gen.accelerator import Accelerator, Description
    from snax_forge.gen.rtl import group_counter

    _, _, acc, _ = _bundle(bundle_dir)
    a = Description.from_dict(acc) if "accelerators" in acc else Accelerator.from_dict(acc)
    if len(a.groups) != 1:
        raise SystemExit(f"{len(a.groups)} groups: one is supported")
    value, working = group_counter(a.groups[0], int(jobs), json.loads(beats))
    return {"cycles": value, "working": working}


def cmd_ref(kernel: str, in_npz: str, out_npz: str, symbols: str = "", dtypes: str = "") -> dict:
    import numpy as np

    from snax_forge.sdfg.loader import load

    spec = load(kernel)
    ins = dict(np.load(in_npz))
    n = len(next(v for v in ins.values() if v.ndim))
    sym = json.loads(symbols) if symbols else None
    dts = json.loads(dtypes) if dtypes else {}
    arrays = {}
    for name, desc in spec.descriptors.items():
        dt = np.dtype(dts[name]) if name in dts else desc.dtype.as_numpy_dtype()
        if name in ins:
            v = ins[name]
            if v.ndim == 0:      # a scalar argument: the kernel body takes it as a number
                arrays[name] = v.astype(dt)[()]
            else:
                shape = [int(s.subs({x: sym[str(x)] for x in s.free_symbols})) if hasattr(s, "free_symbols")
                         else int(s) for s in desc.shape] if sym else [v.size]
                arrays[name] = v.astype(dt).reshape(shape)
        else:
            shape = [int(s.subs({x: (sym[str(x)] if sym else n) for x in s.free_symbols}))
                     if hasattr(s, "free_symbols") else int(s) for s in desc.shape]
            arrays[name] = np.zeros(shape, dtype=dt)
    with np.errstate(over="ignore"):
        spec.func(**arrays)
    outs = {k: arrays[k] for k in spec.inout}
    np.savez(out_npz, **outs)
    return {"kernel": kernel, "func": f"{spec.func.__module__}.{spec.func.__name__}", "outputs": list(outs)}


def main() -> int:
    cmd, *args = sys.argv[1:]
    fn = {"point": cmd_point, "program": cmd_program, "cycles": cmd_cycles, "ref": cmd_ref}[cmd]
    print(json.dumps(fn(*args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
