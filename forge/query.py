#!/usr/bin/env python3
"""forge/query.py - what sim/sources/forge.py needs from snax-forge, answered by snax-forge's own code.

  python forge/query.py point BUNDLE_DIR            kernel, ports' containers, baked scalars
  python forge/query.py program BUNDLE_DIR          the program LOWER makes for the design point: jobs, ops, streams
  python forge/query.py run POINT IN_NPZ OUT_NPZ    the design point's graph (a bundle or its design_point.json) by snax-forge's executor
  python forge/query.py cycles BUNDLE_DIR JOBS BEATS_JSON    the group's busy cycles
  python forge/query.py ctrl_bits ACCELERATOR_JSON  the control units' registers and bits
  python forge/query.py ref KERNEL IN_NPZ OUT_NPZ [SYMBOLS_JSON [DTYPES_JSON]]   the kernel's NumPy body, a type parameter (OP_TYPE) rebound
  python forge/query.py types KERNEL PRESET          the containers' and type parameters' dtypes at a type preset (i8)

Runs inside snax-forge's pixi environment, with snax-forge as the working directory (sim/sources/forge.py calls it
as forge/bundles.py calls snax-forge's tasks), and prints one JSON object on stdout. What each answer holds is in
forge/README.md. snax-forge is not changed: only its modules are imported.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bundles import find_recipe  # noqa: E402  one resolver for both (recipes/**/<name>.json, custom/ left out)


def flat(acc: dict) -> dict:
    """accelerator.json's groups, inputs and outputs over its accelerators (D157's nested form), or as written
    in the flat form of the first bundles (f9764d5)."""
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
        for end in (x for e in ends for x in (e if isinstance(e, list) else [e])):     # a fork's every port
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
    # the dtypes the bundle was made at: each kernel container's and the type parameters (OP_TYPE), after the
    # recipe's dtypes and its --set types= preset
    dtypes = {c: d.dtype for c, d in p.graph.containers.items() if not d.transient}
    dtypes.update(p.graph.type_params)
    return {"kernel": recipe.kernel, "recipe": point["recipe"], "ports": ports, "baked": baked, "dtypes": dtypes}


def _segment(p, nodes, c, st, np, addresses, word_bounds) -> dict:
    """One streamer task's stream: the container's flat (row-major) element of each element slot it moves, beat
    by beat, channel 0 first and in a word its num_slc slices little-endian, -1 a packed output's slice past
    its last result (D174)."""
    node = nodes[st.instance]
    m = (node.outputs if st.write else node.inputs)[st.port]
    visit = addresses(c.values, list(word_bounds(st)))
    # the container the task moves: the node's, or the one its addresses are in when one unit runs on several
    # (gesummv_v2_1_1's matvec on A, then B)
    data = m.data if visit.size == 0 else _l1_container(p, int(visit.ravel()[0]))
    lay = p.memory.layouts[data]["l1"]
    size = np.dtype(st.dtype).itemsize
    idx = np.indices(lay.shape).reshape(len(lay.shape), -1).T         # every element, row-major
    where = {int(x): i for i, x in enumerate(lay.address(idx))}
    slots = (visit[..., None] + size * np.arange(st.num_slc)).reshape(visit.shape[0], -1)
    if not all(int(x) in where for x in visit.ravel()):
        bad = next(int(x) for x in visit.ravel() if int(x) not in where)
        raise SystemExit(f"{c.component}: address {bad} is no element of {data}'s L1 layout")
    order = [where.get(int(x), -1) for x in slots.ravel()]           # -1: a packed word's slice past the end
    if -1 in order and not (st.write and st.d_out > 1):
        raise SystemExit(f"{c.component}: a word of {st.num_slc} {st.dtype} slices runs past {data}")
    return {"end": f"{st.instance}.{st.port}", "component": c.component, "task": c.task_name,
            "dir": "out" if st.write else "in", "container": data, "shape": list(lay.shape),
            "beats": int(visit.shape[0]), "lanes": int(slots.shape[1]), "num_ch": int(visit.shape[1]),
            "num_slc": int(st.num_slc), "d_out": int(st.d_out), "dtype": st.dtype, "order": order,
            "identity": order == list(range(len(order)))}


def _l1_container(p, base: int) -> str:
    """The container whose L1 layout holds byte address `base` (a DMA copy's side)."""
    import numpy as np

    for name, lays in p.memory.layouts.items():
        lay = lays.get("l1") if isinstance(lays, dict) else None
        if lay is None:
            continue
        a = lay.address(np.indices(lay.shape).reshape(len(lay.shape), -1).T)
        if int(a.min()) <= base <= int(a.max()):
            return name
    raise SystemExit(f"L1 address {base}: no container's layout holds it")


def main_c_sequence(text: str, defines: dict) -> list[list]:
    """The accelerator CSR accesses of main.c as its default build runs them (lower/c.py strip_quiet): ["w",
    define, value] per csrw_ss, ["r", define] per csrr_ss, the streamers' CSRs left out."""
    import re

    from snax_forge.lower.c import strip_quiet

    out = []
    for m in re.finditer(r"csrw_ss\((\w+), (.+?)\);|csrr_ss\((\w+)\)", strip_quiet(text)):
        if m.group(1) in defines:
            out.append(["w", m.group(1), m.group(2)])
        elif m.group(3) in defines:
            out.append(["r", m.group(3)])
    return out


def cmd_program(bundle_dir: str) -> dict:
    """The design point's program as the C backend lowers it (lower/c.py's _Program.run, the default build), its
    DMA left out: every accelerator task (a job) with its CSR writes (job_writes, chains and all), scalar slots
    and the group's busy cycles (gen/rtl.py's group_counter, as vectors() calls it), the ops in program order
    (write, scalar, start, wait, counter: a wait where placed_waits puts one on a SNAX component, a counter read
    after each wait for every accelerator task it ends), every streamer task's stream (a segment) with its job,
    and the DMA tasks. Checked against the bundle's main.c: the same accelerator CSR accesses in the same order.
    The one-task keys of before (task, n, writes, scalars, streams) stay."""
    import numpy as np

    from snax_forge.design import DesignPoint
    from snax_forge.design.streamers import groups as graph_groups
    from snax_forge.design.streamers import instance_nodes, word_bounds
    from snax_forge.gen.accelerator import Description, scalar_csrs
    from snax_forge.gen.rtl import group_counter
    from snax_forge.lower.c import accelerators, job_writes
    from snax_forge.lower.derive import addresses, task_list
    from snax_forge.lower.tasks import Configure, Start, check_values
    from snax_forge.lower.waits import idle, placed_waits

    b, bundle, acc, _ = _bundle(bundle_dir)
    dp = Path(bundle["design_point"])
    if not dp.is_file():
        raise SystemExit(f"{dp}: the design point bundle.json names is not there (rebundle: pixi run forge-rtl)")
    p = DesignPoint.load(dp)
    tl = task_list(p)
    check_values(tl, p)
    desc = Description.from_dict(acc)
    for a in desc.accelerators:
        if desc.port_mux_sel(a.name) is not None:
            raise SystemExit(f"accelerator {a.name} shares its movers (D169, PORT_MUX_SEL): not driven")
    defines = desc.defines()
    units = {u: inst for us in accelerators(p).values() for u, inst in us.items()}
    jdesc = {u["name"]: u for ac in acc["accelerators"] for g in ac["groups"] for u in g["units"]}
    fixed = {u for u, d in jdesc.items() if "T" in d.get("params", {})}
    linked = {k: v for k, v in graph_groups(p.graph).items() if len(v) > 1 and v[0] in units}
    gnames = [g.name for g in desc.groups]
    conf = tl.configured()
    nodes = instance_nodes(p.graph)

    def unit_of(comp: str) -> str:
        if comp in linked:
            return linked[comp][0]
        return comp if comp in units else p.streamers[comp].instance

    def csr(unit: str, name: str) -> dict:
        d = desc.find(unit, name)
        return {"define": d, "offset": defines[d]}

    jobs, ops, segs, dmas = [], [], [], []
    job_of: dict[str, int] = {}
    started: dict[str, list[str]] = {}
    order: list[str] = []
    waited: set[str] = set()
    placed: dict[int, list] = {}
    for wt in placed_waits(tl, p):
        placed.setdefault(wt.step, []).append(wt)

    def wait(wt) -> None:
        if wt.component == "dma":           # the DMA is left out (the copies are section C's)
            return
        u = unit_of(wt.component)
        ops.append({"op": "wait", "group": gnames.index(desc.group(u).name), **csr(u, "STATUS")})
        ended = [t for c, last in wt.covers.items() for t in started[c][: started[c].index(last) + 1]
                 if t not in waited]
        for t in sorted(ended, key=order.index):
            waited.add(t)
            if conf[t].type == "accel":
                ops.append({"op": "counter", "job": job_of[t], **csr(unit_of(conf[t].component), "BUSY_COUNTER")})

    for i, s in enumerate(tl.steps):
        if isinstance(s, Configure):
            if s.type != "accel":
                continue
            mine = linked.get(s.component, [s.component])
            g = desc.group(mine[0])
            chains = g.chains() if len(mine) > 1 else None
            wr = [(u, k, int(v)) for u, k, v in job_writes({u: units[u] for u in mine}, s.values, fixed, chains)]
            k = len(jobs)
            job_of[s.task_name] = k
            by_unit = s.values if s.component in linked else {s.component: s.values}
            scalars = []
            for u in mine:
                for slot in units[u].read:
                    dtype = jdesc[u].get("scalars", {})[slot]
                    names = scalar_csrs(slot, dtype)
                    scalars.append({"unit": u, "slot": slot, "container": by_unit[u][slot]["from"], "dtype": dtype,
                                    "csrs": names, "defines": [csr(u, c) for c in names]})
            beats = {u: v for u, n, v in wr if n == "JOB_BEATS"}
            jl = [v for _, n, v in wr if n.startswith("JOBS")]
            cyc, working = group_counter(g, jl[0] if len(jl) == 1 else jl, beats, desc.forks)
            jobs.append({"task": s.task_name, "component": s.component, "group": g.name,
                         "group_index": gnames.index(g.name), "units": mine,
                         "n": int(s.values["n"]) if "n" in s.values else None,
                         "writes": [[u, n, v] for u, n, v in wr], "scalars": scalars, "jobs": jl, "beats": beats,
                         "cycles": int(cyc), "working": working})
            for u, n, v in wr:
                ops.append({"op": "write", "job": k, "unit": u, "csr": n, "value": v, **csr(u, n)})
            for j in range(len(scalars)):
                ops.append({"op": "scalar", "job": k, "scalar": j})
        elif isinstance(s, Start):
            here = [wt for wt in placed.get(i, []) if wt.component != "dma"]
            for wt in sorted(here, key=lambda wt: order.index(wt.covers[wt.component])):
                wait(wt)
            for t in s.tasks:
                started.setdefault(conf[t].component, []).append(t)
                order.append(t)
            accs = {desc.group(unit_of(conf[t].component)).name: t for t in s.tasks if conf[t].type == "accel"}
            for t in s.tasks:
                c = conf[t]
                if c.type == "dma":
                    ops.append({"op": "dma", "task": t, "direction": c.values["direction"]})
                    v = c.values
                    side = {x: ({"symbol": v[x]["symbol"]} if "symbol" in v[x] else
                                {"base": int(v[x]["base"]), "container": _l1_container(p, int(v[x]["base"]))})
                            for x in ("src", "dst")}
                    dmas.append({"task": t, "direction": v["direction"], **side})
                elif c.type == "streamer":
                    if idle(c):             # another group's mover in an encapsulated set: moves nothing
                        continue
                    st = p.streamers[c.component]
                    gname = desc.group(st.instance).name
                    if gname not in accs:
                        raise SystemExit(f"{t}: a streamer started with no accelerator task of its group {gname}")
                    seg = _segment(p, nodes, c, st, np, addresses, word_bounds)
                    seg["job"] = job_of[accs[gname]]
                    segs.append(seg)
                else:
                    u = unit_of(c.component)
                    ops.append({"op": "start", "job": job_of[t], "group": gnames.index(desc.group(u).name),
                                **csr(u, "START")})
        else:
            for wt in placed.get(i, []):
                wait(wt)
    unread = [t for t in job_of if t not in waited]
    if unread:
        raise SystemExit(f"no wait covers {unread}")

    # the bundle's own program: the same accelerator CSR accesses, in the same order
    mine = []
    for o in ops:
        if o["op"] == "write":
            mine.append(["w", o["define"], str(o["value"])])
        elif o["op"] == "scalar":
            for d in jobs[o["job"]]["scalars"][o["scalar"]]["defines"]:
                mine.append(["w", d["define"], None])
        elif o["op"] == "start":
            mine.append(["w", o["define"], "1"])
        elif o["op"] in ("wait", "counter"):
            mine.append(["r", o["define"]])
    theirs = main_c_sequence((b / "main.c").read_text(), defines) if (b / "main.c").is_file() else None
    if theirs is not None:
        same = len(mine) == len(theirs) and all(
            x[:2] == y[:2] and (x[0] == "r" or x[2] is None or x[2] == y[2]) for x, y in zip(mine, theirs))
        if not same:
            k = next((j for j, (x, y) in enumerate(zip(mine, theirs)) if x[:2] != y[:2]), min(len(mine), len(theirs)))
            raise SystemExit(f"program: the task list's CSR accesses differ from main.c's at {k}: "
                             f"{mine[k:k + 3]} against {theirs[k:k + 3]} ({len(mine)} and {len(theirs)})")

    one = jobs[0] if len(jobs) == 1 else None
    return {"symbols": {k: int(v) for k, v in p.graph.bound_symbols.items()},
            "design_point": str(dp), "groups": gnames, "jobs": jobs, "ops": ops, "dmas": dmas,
            "main_c_checked": theirs is not None,
            "task": one and one["task"], "n": one and one["n"],
            "writes": one["writes"] if one else None,
            "scalars": [{k: v for k, v in sc.items() if k != "defines"} for sc in one["scalars"]] if one else None,
            "streams": segs}


def cmd_run(point: str, in_npz: str, out_npz: str) -> dict:
    """snax-forge's reference executor (dfg/execute.py) on the design point's graph (POINT a bundle folder, or its
    design_point.json as tb.json names it): IN_NPZ's arrays as its
    non-transient containers (cast to the graph's dtypes, shaped as the graph shapes them; one not given is
    zeros), every container's final contents, transients (tmp2, a transpose's A_T) included, to OUT_NPZ."""
    import numpy as np

    from snax_forge.design import DesignPoint
    from snax_forge.dfg.execute import _int, execute

    dp = Path(point)
    if dp.is_dir():
        dp = Path(_bundle(point)[1]["design_point"])
    if not dp.is_file():
        raise SystemExit(f"{dp}: no design point there (rebundle: pixi run forge-rtl)")
    p = DesignPoint.load(dp)
    g = p.graph
    sym = {k: int(v) for k, v in g.bound_symbols.items()}
    ins = dict(np.load(in_npz))
    inputs = {}
    for name, c in g.containers.items():
        if c.transient:
            continue
        shape = tuple(_int(x, sym, name) for x in c.shape)
        v = np.asarray(ins[name]) if name in ins else np.zeros(shape, dtype=np.int64)
        if v.ndim == 0 and shape == (1,) or shape == ():
            v = v.reshape(shape)
        inputs[name] = v.astype(np.dtype(c.dtype)).reshape(shape)
    with np.errstate(over="ignore"):
        out = execute(g, inputs)
    np.savez(out_npz, **out)
    return {"containers": {k: {"dtype": str(v.dtype), "shape": list(v.shape),
                               "transient": bool(g.containers[k].transient)} for k, v in out.items()}}


def cmd_cycles(bundle_dir: str, jobs: str, beats: str) -> dict:
    from snax_forge.gen.accelerator import Accelerator, Description
    from snax_forge.gen.rtl import group_counter

    _, _, acc, _ = _bundle(bundle_dir)
    a = Description.from_dict(acc) if "accelerators" in acc else Accelerator.from_dict(acc)
    if len(a.groups) != 1:
        raise SystemExit(f"{len(a.groups)} groups: one is supported")
    value, working = group_counter(a.groups[0], int(jobs), json.loads(beats))
    return {"cycles": value, "working": working}


def cmd_ctrl_bits(path: str) -> dict:
    from snax_forge.estimate.bits import accelerator_registers

    f = Path(path)
    acc = json.loads((f / "accelerator.json" if f.is_dir() else f).read_text())
    return {m: {"registers": [list(r) for r in regs], "bits": sum(b for _, b in regs)}
            for m, regs in accelerator_registers(acc).items()}


def cmd_ref(kernel: str, in_npz: str, out_npz: str, symbols: str = "", dtypes: str = "") -> dict:
    import numpy as np

    from snax_forge.sdfg.loader import load

    spec = load(kernel)
    ins = dict(np.load(in_npz))
    n = len(next(v for v in ins.values() if v.ndim))
    sym = json.loads(symbols) if symbols else None
    dts = json.loads(dtypes) if dtypes else {}
    unknown = sorted(set(dts) - set(spec.descriptors) - set(getattr(spec, "types", {})))
    if unknown:      # e.g. ACC in a bundle made before snax-forge named it OP_TYPE: rebundle it
        raise SystemExit(f"ref {kernel}: dtypes name {unknown}, neither a container nor a type parameter "
                         f"of the kernel; rebundle the point (pixi run forge-rtl)")
    params = {k: v for k, v in dts.items() if k in getattr(spec, "types", {})}
    if params:      # a type parameter (OP_TYPE in A.astype(OP_TYPE)): the body's global rebound, as the bundle's
        spec = spec.with_types(params, "dtypes")
    dts = {k: v for k, v in dts.items() if k not in params}
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


def cmd_types(kernel: str, preset: str) -> dict:
    """The dtypes a recipe at --set types=PRESET gives the kernel (KernelSpec.kernel_dtypes): an HLS point at
    X118's spec checks against snax-forge's kernel at these (sim/sources/hls.py narrow_ref, X119)."""
    from snax_forge.sdfg.loader import load

    spec = load(kernel)
    try:
        dtypes = spec.kernel_dtypes(preset, {})
    except ValueError as e:
        raise SystemExit(f"types {kernel}: {e}") from None
    return {"kernel": kernel, "preset": preset, "dtypes": dict(dtypes)}


def main() -> int:
    cmd, *args = sys.argv[1:]
    fn = {"point": cmd_point, "program": cmd_program, "cycles": cmd_cycles, "ctrl_bits": cmd_ctrl_bits,
          "ref": cmd_ref, "types": cmd_types, "run": cmd_run}[cmd]
    print(json.dumps(fn(*args)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
