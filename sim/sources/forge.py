"""sim/sources/forge.py - a snax-forge point -> tb.json.

snax-forge is not changed for this: the adapter reads its bundle, rtl/forge/<point>.zip (forge/bundles.py), unpacked by
sim/pwr.py, and asks snax-forge's own code for the rest (forge/query.py, run in snax-forge's pixi environment):
point.json (recipe, W, commit), bundle.json (the top, the design point), accelerator.json (its one group's CSRs by
offset, its outer ports in order with lanes and dtype), the streamer's hjson (each mover's num_channel) and the
netlist's port list, every port covered. build() writes tb.json (its fields in build()'s docstring); docs/power.md,
"Forge", has the testbench and the window. One group only; every read-write CSR is START, JOBS, a unit's
JOB_BEATS or a scalar's.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import numpy as np

from . import hls
from . import ports as _ports

TB_VERSION = 1
CLK, RST = _ports("forge")   # clk_i, rst_ni: syn/syn.py's SOURCES
ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl" / "forge"
QUERY = ROOT / "forge" / "query.py"
SIZE = "n2048"                   # the reference task's tag (X24), the size of a forge point made at its shape
CONTROL_KINDS = {"forge_csr"}
BITS = {"int8": 8, "int16": 16, "int32": 32, "int64": 64}   # a stream's element dtypes: num_slc = 64 / bits a word
SCALAR_DTYPES = ("int32", "int64")    # a scalar CSR slot: one 32-bit word, or two (low word first)
CSR_PORTS = {"req_addr": "csr_req_addr_i", "req_data": "csr_req_data_i", "req_write": "csr_req_write_i",
             "req_valid": "csr_req_valid_i", "req_ready": "csr_req_ready_o", "rsp_data": "csr_rsp_data_o",
             "rsp_valid": "csr_rsp_valid_o", "rsp_ready": "csr_rsp_ready_i"}

_spec = importlib.util.spec_from_file_location("forge_bundles", ROOT / "forge" / "bundles.py")
bundles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bundles)


def query(*args: str) -> dict:
    """forge/query.py in snax-forge's environment (forge/bundles.py's: PIXI_* and CONDA_* removed)."""
    r = subprocess.run(bundles.forge_cmd("python", str(QUERY), *args), cwd=bundles.FORGE, env=bundles.inner_env(),
                       capture_output=True, text=True)
    if r.returncode:
        raise ValueError(f"forge/query.py {args[0]}: exit {r.returncode}: {(r.stdout + r.stderr).strip()[-800:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def bundle_of(point: str, bundle: Path) -> Path:
    """The point's bundle, unpacked from rtl/forge/<point>.zip by sim/pwr.py, with the files it needs."""
    for f in ("bundle.json", "accelerator.json", "point.json"):
        if not (bundle / f).is_file():
            raise FileNotFoundError(f"{point}: no {f} in {RTL / point}.zip (pixi run forge-rtl)")
    return bundle


def streamer_channels(b: Path, tag: str, acc_name: str | None = None) -> dict:
    """Each mover's num_channel: <tag>_streamer_<accelerator>.hjson (one streamer set per accelerator, D157), or
    the first bundles' <tag>_streamer.hjson."""
    f = b / f"{tag}_streamer_{acc_name}.hjson"
    if acc_name is None or not f.is_file():
        f = b / f"{tag}_streamer.hjson"
    text = "\n".join(ln for ln in f.read_text().splitlines()
                     if not ln.lstrip().startswith("//"))
    d = json.loads(text)
    return {"in": d.get("data_reader_params", {}).get("num_channel", []),
            "out": d.get("data_writer_params", {}).get("num_channel", [])}


def build(point: str, netlist: Path, bundle: Path) -> dict:
    """tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
      tb_version, source "forge", point, kernel, recipe, top, case, W, snax_forge_commit
      clock   {port: clk_i}
      reset   {port: rst_ni, active: low, sync: false}
      control {kind: "forge_csr", group, req_addr, req_data, req_write, req_valid, req_ready,
               rsp_data, rsp_valid, rsp_ready, busy, done, csrs: {name: offset}}
      streams [{arg, name, end, dir, kind: "stream", lanes, num_ch, dtype, num_slc, d_out, elems, data, valid, ready,
                beats, identity, order}]
               lanes the TB's 64-bit channels a beat (num_ch); dtype the port's element, num_slc of them in a word,
               little-endian (snax-forge D142); elems the element slots a beat carries (num_ch x num_slc); d_out > 1 a
               packed output (D174): d_out results in one word, the slices past the last result 0 (order -1)
               arg the container the design point binds the port to (the kernel's array, sim/ref.py's name);
               name the TB's name for the stream: arg, or arg_in / arg_out when one container has an input and an
               output stream (axpy's y, read and written in place); order the container's flat (row-major) element
               of each element the stream carries, beat by beat, lane 0 first, as the bundle's streamer loops visit
               them (forge/query.py program), null when it is the identity
      pins    []
      scalars [{container, dtype, unit, slot, csrs: [[offset, name], ...]}]  a slot read from a scalar container (a
               CSR the program writes before START, C§17: K1, or K1_LO and K1_HI low word first at int64); its value
               drawn as rand64 draws a data pin (sim/pwr.py)
      baked   {container: value}  a scalar the recipe bakes (bake_scalar with a value, axpy_baked's alpha = 3): no CSR,
               the value is the reference's
      sizes   {n2048: {shape: {symbol: value}, jobs, beats: {unit: JOB_BEATS}, writes: [[offset, value, name], ...
                       START last], stream_beats: {name: beats}, expected_cycles, expected_from}}
              shape: the point's sets, the size the design point was made at: the n2048 shape for its tier and
              kernel (sim/sources/hls.py's extra_sizes), tagged n2048, or a size of the kernel's hls-exercises
              params.json (X118's n4096, X119), tagged as there; the one size of the point. writes: JOBS and each JOB_BEATS as snax-forge's LOWER writes
              them for that design point (forge/query.py program: lower/derive.py's task list, lower/c.py's
              job_writes), then START; sim/pwr.py adds the scalar writes before START. expected_cycles: the group's
              busy cycles from snax-forge's model (forge/query.py cycles: gen/rtl.py's group_counter) with those
              values; the TB's window is the measurement, the BUSY_COUNTER it reads back and this count are recorded
              beside it, each within 5 % of it.

    One group only (dot 1 is not among the points). Every read-write CSR is START, JOBS, a unit's JOB_BEATS or a scalar's.
    """
    b = bundle_of(point, bundle)
    bundle = json.loads((b / "bundle.json").read_text())
    acc = json.loads((b / "accelerator.json").read_text())
    pj = json.loads((b / "point.json").read_text())
    q = query("point", str(b))
    prog = query("program", str(b))
    ports = hls.ports_of(netlist, bundle["top"])
    # the size: the point's sets that are the kernel's symbols (the design point was made at them,
    # forge/bundles.py); types=i8 is a preset, R=8 a recipe param, design.data=full the design step's
    shape = {k: int(v) for k, v in (x.split("=", 1) for x in pj.get("sets", [])) if k in prog["symbols"]}
    tag = size_tag(point, shape)
    if tag is None:
        raise ValueError(f"{point}: bundle made with sets {pj.get('sets')}, neither the n2048 shape "
                         f"{dict(hls.extra_sizes(point)).get(SIZE)} nor a size of the kernel's params.json: "
                         "rebundle (pixi run forge-rtl)")
    for k, v in shape.items():
        if prog["symbols"].get(k) != v:
            raise ValueError(f"{point}: the design point has {k} = {prog['symbols'].get(k)}, the sets {k} = {v}")
    if "BUSY_COUNTER" not in {c["name"] for a in acc.get("accelerators", [acc]) for g in a["groups"] for c in g["csrs"]}:
        raise ValueError(f"{point}: no BUSY_COUNTER CSR (a bundle made before snax-forge D168 names it COUNTER): "
                         "rebundle (pixi run forge-rtl)")
    if not simple(prog, acc):
        return build_program(point, b, bundle, acc, pj, q, prog, ports, shape, tag)
    acc_name = None
    if "accelerators" in acc:      # D157's nested form: one accelerator's groups, inputs and outputs
        if len(acc["accelerators"]) != 1:
            raise ValueError(f"{point}: {len(acc['accelerators'])} accelerators; one is supported")
        acc = acc["accelerators"][0]
        acc_name = acc["name"]
    top, w = bundle["top"], int(pj["W"])
    case = point.split("/")[2].rsplit("_w", 1)[0]
    if len(acc["groups"]) != 1:
        raise ValueError(f"{point}: {len(acc['groups'])} groups; one is supported")
    (g,) = acc["groups"]

    csrs = {c["name"]: c["offset"] for c in g["csrs"]}
    for need in ("START", "JOBS", "STATUS", "BUSY_COUNTER"):
        if need not in csrs:
            raise ValueError(f"{point}: group {g['name']} has no {need} CSR")
    scal_csr = {(sc["unit"], c) for sc in prog["scalars"] for c in sc["csrs"]}
    for u in g["units"]:
        for c in u.get("csrs", []):
            if c["name"] != "JOB_BEATS" and (u["name"], c["name"]) not in scal_csr:
                raise ValueError(f"{point}: read-write CSR {u['name']}.{c['name']} is neither a JOB_BEATS nor a "
                                 "scalar's the program writes")
            csrs[f"{u['name']}.{c['name']}"] = c["offset"]

    control = {"kind": "forge_csr", "group": g["name"], **CSR_PORTS,
               "busy": f"{g['name']}_busy_o", "done": f"{g['name']}_done_o", "csrs": csrs}
    scalars = [{"container": sc["container"], "dtype": sc["dtype"], "unit": sc["unit"], "slot": sc["slot"],
                "csrs": [[csrs[f"{sc['unit']}.{c}"], f"{sc['unit']}.{c}"] for c in sc["csrs"]]}
               for sc in prog["scalars"]]
    for sc in scalars:
        if sc["dtype"] not in SCALAR_DTYPES:
            raise ValueError(f"{point}: scalar {sc['container']} is {sc['dtype']}; {SCALAR_DTYPES} are driven")

    container = {p["end"]: p["container"] for p in q["ports"]}
    order = {s["end"]: s for s in prog["streams"]}
    units = {u["name"]: u for u in g["units"]}
    nch = streamer_channels(b, bundle["tag"], acc_name)
    streams = []
    for side, ends, pre in (("in", acc["inputs"], "stream2acc"), ("out", acc["outputs"], "acc2stream")):
        for k, end in enumerate(ends):
            uname, port = end.split(".", 1)
            p = units[uname]["ports"][port]
            data = f"{pre}_{k}_data_{'i' if side == 'in' else 'o'}"
            if data not in ports:
                raise ValueError(f"{point}: no port {data} for {end}")
            num_ch = nch[side][k]
            if ports[data][1] != 64 * num_ch:
                raise ValueError(f"{point}: {data} is {ports[data][1]} bits, num_channel {num_ch} gives {64 * num_ch}")
            # a word packs num_slc elements (snax-forge D142): wire-sliced, lanes = num_ch x num_slc; or a packed
            # output (D174, d_out > 1), d_out results of one lane in one word on one channel
            if p["dtype"] not in BITS:
                raise ValueError(f"{point}: {end} is {p['dtype']}; the streams take {sorted(BITS)}")
            num_slc, d_out = 64 // BITS[p["dtype"]], int(p.get("d_out", 1))
            if (num_ch, p["lanes"] * d_out) != ((1, num_slc) if d_out > 1 else (p["lanes"] // num_slc, p["lanes"])) \
                    or (d_out == 1 and p["lanes"] % num_slc):
                raise ValueError(f"{point}: {end} {p['dtype']} x {p['lanes']} (d_out {d_out}) is not {num_ch} "
                                 f"channels of {num_slc} slices")
            o = order.get(end)
            want = (container[end], side, num_ch * num_slc, num_ch, num_slc, d_out, p["dtype"])
            keys = ("container", "dir", "lanes", "num_ch", "num_slc", "d_out", "dtype")
            if o is None or tuple(o.get(x, 1 if x in ("num_slc", "d_out") else None) for x in keys) != want:
                raise ValueError(f"{point}: {end}: the program's streamer task {o and {x: o.get(x) for x in keys}} "
                                 f"is not the port's {dict(zip(keys, want))}")
            # lanes: the TB's 64-bit channels (num_ch words a beat); elems: the element slots a beat carries
            streams.append({"arg": container[end], "name": container[end], "end": end, "dir": side,
                            "kind": "stream", "lanes": num_ch, "num_ch": num_ch, "dtype": p["dtype"],
                            "num_slc": num_slc, "d_out": d_out, "elems": num_ch * num_slc, "data": data,
                            "valid": f"{pre}_{k}_valid_{'i' if side == 'in' else 'o'}",
                            "ready": f"{pre}_{k}_ready_{'o' if side == 'in' else 'i'}",
                            "beats": o["beats"], "shape": o["shape"], "identity": o["identity"],
                            "order": None if o["identity"] else o["order"]})
    args = [s["arg"] for s in streams]
    for s in streams:
        if args.count(s["arg"]) > 1:                # in place (axpy's y): one stream in, one out
            if sorted(x["dir"] for x in streams if x["arg"] == s["arg"]) != ["in", "out"]:
                raise ValueError(f"{point}: container {s['arg']} has streams {args.count(s['arg'])}: only an in/out pair")
            s["name"] = f"{s['arg']}_{s['dir']}"

    known = {CLK, RST, control["busy"], control["done"], *CSR_PORTS.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    missing = sorted(known - set(ports))
    extra = sorted(set(ports) - known)
    if missing or extra:
        raise ValueError(f"{point}: netlist ports not as C§17's wrapper: missing {missing}, not covered {extra}")

    jobs = [v for _, k, v in prog["writes"] if k == "JOBS"]
    if len(jobs) != 1:
        raise ValueError(f"{point}: the program writes JOBS {len(jobs)} times")
    beats = {u: v for u, k, v in prog["writes"] if k == "JOB_BEATS"}
    writes = [[csrs["JOBS"], jobs[0], "JOBS"]] + [[csrs[f"{u}.JOB_BEATS"], v, f"{u}.JOB_BEATS"] for u, v in beats.items()]
    writes.append([csrs["START"], 1, "START"])
    cyc = query("cycles", str(b), str(jobs[0]), json.dumps(beats))
    sizes = {tag: {"shape": shape, "jobs": jobs[0], "beats": beats, "writes": writes,
                    "stream_beats": {s["name"]: s["beats"] for s in streams},
                    "expected_cycles": cyc["cycles"], "expected_from": cyc["working"]}}

    return {"tb_version": TB_VERSION, "source": "forge", "point": point, "kernel": q["kernel"], "recipe": pj["recipe"],
            "top": top, "case": case, "W": w, "snax_forge_commit": pj["snax_forge_commit"],
            "dtypes": {**q.get("dtypes", {}), **pj.get("dtypes", {})}, "symbols": prog["symbols"],
            "clock": {"port": CLK}, "reset": {"port": RST, "active": "low", "sync": False},
            "control": control, "streams": streams, "pins": [], "scalars": scalars, "baked": q.get("baked", {}),
            "sizes": sizes}


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    if tb["control"]["kind"] not in CONTROL_KINDS:
        raise ValueError(f"control.kind {tb['control']['kind']}: the forge source builds forge_csr")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    for s in tb["streams"]:
        if s["kind"] != "stream" or s["dtype"] not in BITS:
            raise ValueError(f"stream {s['arg']}: {s['kind']} {s['dtype']}, only {sorted(BITS)} streams are built")
    for tag, z in tb["sizes"].items():
        if "program" in z:              # several jobs, groups or accelerators (X120)
            if not any(o[0] == "start" for o in z["program"]) or not isinstance(z["expected_cycles"], int):
                raise ValueError(f"size {tag}: a program with no start or no expected cycles")
            continue
        if not z["writes"] or z["writes"][-1][2] != "START":
            raise ValueError(f"size {tag}: the writes do not end with START")
        if not isinstance(z["expected_cycles"], int):
            raise ValueError(f"size {tag}: no expected cycles")


def size_tag(point: str, shape: dict) -> str | None:
    """The size tag of a forge point made at `shape`: n2048 at the reference task's shape (X24), else the tag of
    the hls-exercises params.json size it is (n4096, X119); None when it is neither."""
    low = {k.lower(): v for k, v in shape.items()}
    if low == dict(hls.extra_sizes(point)).get(SIZE):
        return SIZE
    try:
        sizes = hls.params_of(point)["sizes"]
    except (OSError, ValueError, KeyError):
        return None
    return next((hls.size_tag(z) for z in sizes if z == low), None)


def default_size(tb: dict) -> str:
    """The point's one size."""
    return next(iter(tb["sizes"]))


def kernel_ref(kernel: str, ins: dict, workdir: Path, symbols: dict | None = None, dtypes: dict | None = None) -> dict:
    """snax-forge's own reference: the kernel's NumPy body (forge/query.py ref) on `ins` (a scalar as a 0-d
    array), its outputs sized by `symbols` (the design point's), each container at `dtypes` where given (the
    point's: the recipe's dtypes override the kernel's descriptors, as in the bundle)."""
    import numpy as np

    workdir.mkdir(parents=True, exist_ok=True)
    fi, fo = workdir / "ref_in.npz", workdir / "ref_out.npz"
    np.savez(fi, **ins)
    info = query("ref", kernel, str(fi), str(fo), json.dumps(symbols or {}), json.dumps(dtypes or {}))
    out = dict(np.load(fo))
    fi.unlink()
    fo.unlink()
    return {"info": info, "outs": out}


def graph_run(design_point: str, ins: dict, workdir: Path) -> dict:
    """snax-forge's reference executor on the design point (forge/query.py run): {container: array} of
    every container, transients included, from the non-transient ones in `ins` (a scalar a 0-d array)."""
    workdir.mkdir(parents=True, exist_ok=True)
    fi, fo = workdir / "run_in.npz", workdir / "run_out.npz"
    np.savez(fi, **ins)
    query("run", design_point, str(fi), str(fo))
    out = dict(np.load(fo))
    fi.unlink()
    fo.unlink()
    return out


def netlist_modules(netlist: Path) -> set:
    """Every module the netlist defines (DC indents some headers, PITFALLS DC6)."""
    return set(re.findall(r"^\s*module\s+(\S+)\s*\(", netlist.read_text(), re.M))


# ---------------------------------------------------------------- several jobs, groups or accelerators (X120)
def simple(prog: dict, acc: dict) -> bool:
    """A point build_one() drives as before: one accelerator, one group, one accelerator task writing JOBS and
    JOB_BEATS only, no forked input, no copy, at most an in/out pair of streams on a container."""
    accs = acc.get("accelerators", [acc])
    if len(accs) != 1 or len(accs[0]["groups"]) != 1 or len(prog["jobs"]) != 1:
        return False
    if any(isinstance(e, list) for e in accs[0]["inputs"]) or any(d["direction"] == "l1_to_l1" for d in prog["dmas"]):
        return False
    if any(k not in ("JOBS", "JOB_BEATS") for _, k, _ in prog["writes"]):
        return False
    seen: dict = {}
    for s in prog["streams"]:
        seen.setdefault(s["container"], []).append(s["dir"])
    return all(len(v) == 1 or sorted(v) == ["in", "out"] for v in seen.values())


def sources(prog: dict) -> list[dict]:
    """Where each segment's values come from (X120): a read of elements no earlier job or copy wrote takes the
    container's initial contents (drawn, or zeros for a transient), a read of elements an earlier job or copy
    wrote takes the graph's final contents, and a write its final contents. Refused where the final contents
    are not what the stream moves: an element written again after it is read or written (a value between two
    writes), or a segment reading some elements of each kind."""
    pos, k = {}, 0                     # each start's and copy's place in the program
    for o in prog["ops"]:
        if o["op"] == "start":
            pos[("job", o["job"])] = k
            k += 1
        elif o["op"] == "dma":
            pos[("dma", o["task"])] = k
            k += 1
    writes: dict = {}                  # container -> [(place, job or None, set of elements)]
    for s in prog["streams"]:
        if s["dir"] == "out":
            writes.setdefault(s["container"], []).append((pos[("job", s["job"])], s["job"],
                                                          {e for e in s["order"] if e >= 0}))
    for d in prog["dmas"]:
        if d["direction"] == "l1_to_l1":
            writes.setdefault(d["dst"]["container"], []).append((pos[("dma", d["task"])], None, None))   # whole
    out = []
    for s in prog["streams"]:
        at = pos[("job", s["job"])]
        elems = {e for e in s["order"] if e >= 0}
        ws = writes.get(s["container"], [])

        def hits(w):
            return w[2] is None or bool(w[2] & elems)
        if s["dir"] == "out":
            later = [w for w in ws if hits(w) and w[0] > at]
            same = [w for w in ws if w[0] == at and w[2] is not None and w[2] & elems]     # itself, and any other
            if later or len(same) > 1:
                raise ValueError(f"{s['container']}: written by job {s['job']} ({s['end']}) and again after it; "
                                 "its value between the two is not the graph's final one")
            out.append({"value": "final"})
            continue
        before = [w for w in ws if hits(w) and w[0] < at]
        if not before:
            out.append({"value": "initial"})
            continue
        last = max(w[0] for w in before)
        again = [w for w in ws if hits(w) and w[0] > last]
        if again:
            raise ValueError(f"{s['container']}: job {s['job']} ({s['end']}) reads it between two writes; the "
                             "value it reads is not the graph's final one")
        covered = set()
        for w in before:
            covered |= set(range(int(np.prod(s["shape"])))) if w[2] is None else w[2]
        if not elems <= covered:
            raise ValueError(f"{s['container']}: job {s['job']} ({s['end']}) reads elements some written before "
                             "it and some not")
        out.append({"value": "final"})
    return out


def build_program(point: str, b: Path, bundle: dict, acc: dict, pj: dict, q: dict, prog: dict, ports: dict,
                  shape: dict, tag: str) -> dict:
    """tb.json of a form with several jobs, groups or accelerators, a forked input, ROWS or a copy (X120), as
    build()'s with:
      control {kind: "forge_csr", group (the groups joined by +), CSR ports, busy, done (the first group's),
               groups: [{name, busy, done}], csrs: {<group>.<NAME> or <group>.<unit>.<NAME>: offset}}
      streams one per wrapper port (stream2acc_<k>, then acc2stream_<k>): arg (its first segment's container),
               name (its containers joined by _, made unique), ends (a fork's ports), dtype, num_ch, num_slc,
               d_out, lanes, elems, beats (all its segments'), segments: [{job, task, container, shape,
               transient, beats, identity, order, value: initial | final}] in program order
      scalars [{job, container, dtype, unit, slot, csrs: [[offset, name], ...]}] each job's
      design_point the graph sim/pwr.py runs snax-forge's executor on (forge/query.py run)
      left_out the DMA tasks the TB does not run: [{task, direction, src, dst}], a copy's destination read as
               the graph gives it
      sizes   {tag: {shape, program: [op, ...], jobs: [{task, group, cycles, working, writes}], stream_beats,
               expected_cycles, expected_from}}
               program in order: ["write", offset, value, name], ["scalar", i] (scalars[i], its words),
               ["start", offset, group, task], ["wait", group] (until the group's done pulses equal its starts:
               the program's poll on STATUS), ["counter", offset, job, task] (its BUSY_COUNTER read)
    """
    accs = acc["accelerators"]
    groups = [g for a in accs for g in a["groups"]]
    gname = [g["name"] for g in groups]
    csrs = {}
    for g in groups:
        csrs |= {f"{g['name']}.{c['name']}": c["offset"] for c in g["csrs"]}
        for u in g["units"]:
            csrs |= {f"{g['name']}.{u['name']}.{c['name']}": c["offset"] for c in u.get("csrs", [])}
    control = {"kind": "forge_csr", "group": "+".join(gname), **CSR_PORTS,
               "busy": f"{gname[0]}_busy_o", "done": f"{gname[0]}_done_o",
               "groups": [{"name": n, "busy": f"{n}_busy_o", "done": f"{n}_done_o"} for n in gname], "csrs": csrs}
    units = {u["name"]: u for g in groups for u in g["units"]}
    nch = {"in": [], "out": []}
    for a in accs:
        c = streamer_channels(b, bundle["tag"], a["name"])
        nch["in"] += c["in"]
        nch["out"] += c["out"]
    src = sources(prog)
    transient = {c for c in {s["container"] for s in prog["streams"]} if c not in q.get("dtypes", {})}
    streams = []
    for side, ends, pre in (("in", [e for a in accs for e in a["inputs"]], "stream2acc"),
                            ("out", [e for a in accs for e in a["outputs"]], "acc2stream")):
        if len(ends) != len(nch[side]):
            raise ValueError(f"{point}: {len(ends)} {side}put ports, the streamers' num_channel has {len(nch[side])}")
        for k, e in enumerate(ends):
            fork = e if isinstance(e, list) else [e]
            uname, port = fork[0].split(".", 1)
            p = units[uname]["ports"][port]
            io = "i" if side == "in" else "o"
            data = f"{pre}_{k}_data_{io}"
            num_ch = nch[side][k]
            if data not in ports or ports[data][1] != 64 * num_ch:
                raise ValueError(f"{point}: {data} {ports.get(data)}, num_channel {num_ch} gives {64 * num_ch} bits")
            if p["dtype"] not in BITS:
                raise ValueError(f"{point}: {fork[0]} is {p['dtype']}; the streams take {sorted(BITS)}")
            num_slc, d_out = 64 // BITS[p["dtype"]], int(p.get("d_out", 1))
            segs = [(s, v) for s, v in zip(prog["streams"], src) if s["end"] == fork[0]]
            if not segs:
                raise ValueError(f"{point}: no streamer task moves {fork[0]}")
            want = (side, num_ch * num_slc, num_ch, num_slc, d_out, p["dtype"])
            keys = ("dir", "lanes", "num_ch", "num_slc", "d_out", "dtype")
            for s, _ in segs:
                if tuple(s[x] for x in keys) != want:
                    raise ValueError(f"{point}: {s['task']} on {fork[0]} is {[s[x] for x in keys]}, the port {want}")
            streams.append({"arg": segs[0][0]["container"], "name": "_".join(dict.fromkeys(s["container"] for s, _ in segs)),
                            "end": fork[0], "ends": fork, "dir": side, "kind": "stream", "lanes": num_ch,
                            "num_ch": num_ch, "dtype": p["dtype"], "num_slc": num_slc, "d_out": d_out,
                            "elems": num_ch * num_slc, "data": data,
                            "valid": f"{pre}_{k}_valid_{io}", "ready": f"{pre}_{k}_ready_{'o' if side == 'in' else 'i'}",
                            "beats": sum(s["beats"] for s, _ in segs),
                            "segments": [{"job": s["job"], "task": s["task"], "container": s["container"],
                                          "shape": s["shape"], "transient": s["container"] in transient,
                                          "beats": s["beats"], "identity": s["identity"],
                                          "order": None if s["identity"] else s["order"], **v} for s, v in segs]})
    names = [s["name"] for s in streams]
    for s, n in zip(streams, names):   # one name a stream: arg_in / arg_out for an in/out pair, else by unit
        same = [x for x, m in zip(streams, names) if m == n]
        if len(same) > 1:
            pair = sorted(x["dir"] for x in same) == ["in", "out"]
            s["name"] = f"{n}_{s['dir']}" if pair else f"{n}_{s['end'].split('.')[0]}"
    if len({s["name"] for s in streams}) != len(streams):
        raise ValueError(f"{point}: stream names {names} not unique")

    known = {CLK, RST, *CSR_PORTS.values()} | {g[k] for g in control["groups"] for k in ("busy", "done")}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    missing, extra = sorted(known - set(ports)), sorted(set(ports) - known)
    if missing or extra:
        raise ValueError(f"{point}: netlist ports not as C§17's wrapper: missing {missing}, not covered {extra}")

    scalars, sidx, program = [], {}, []
    for j, job in enumerate(prog["jobs"]):
        for i, sc in enumerate(job["scalars"]):
            if sc["dtype"] not in SCALAR_DTYPES:
                raise ValueError(f"{point}: scalar {sc['container']} is {sc['dtype']}; {SCALAR_DTYPES} are driven")
            sidx[(j, i)] = len(scalars)
            scalars.append({"job": j, "container": sc["container"], "dtype": sc["dtype"], "unit": sc["unit"],
                            "slot": sc["slot"], "csrs": [[d["offset"], f"{job['group']}.{sc['unit']}.{c}"]
                                                         for d, c in zip(sc["defines"], sc["csrs"])]})
    for o in prog["ops"]:
        job = prog["jobs"][o["job"]] if "job" in o else None
        if o["op"] == "write":
            own = o["csr"].startswith("JOBS")
            program.append(["write", o["offset"], o["value"],
                            f"{job['group']}.{o['csr']}" if own else f"{job['group']}.{o['unit']}.{o['csr']}"])
        elif o["op"] == "scalar":
            program.append(["scalar", sidx[(o["job"], o["scalar"])]])
        elif o["op"] == "start":
            program.append(["start", o["offset"], o["group"], job["task"]])
        elif o["op"] == "wait":
            program.append(["wait", o["group"]])
        elif o["op"] == "counter":
            program.append(["counter", o["offset"], o["job"], job["task"]])
    exp, how = program_cycles(prog)
    sizes = {tag: {"shape": shape, "program": program,
                   "jobs": [{"task": j["task"], "group": j["group"], "cycles": j["cycles"], "working": j["working"],
                             "writes": j["writes"]} for j in prog["jobs"]],
                   "stream_beats": {s["name"]: s["beats"] for s in streams},
                   "expected_cycles": exp, "expected_from": how}}
    return {"tb_version": TB_VERSION, "source": "forge", "point": point, "kernel": q["kernel"], "recipe": pj["recipe"],
            "top": bundle["top"], "case": point.split("/")[2].rsplit("_w", 1)[0], "W": int(pj["W"]),
            "snax_forge_commit": pj["snax_forge_commit"], "dtypes": {**q.get("dtypes", {}), **pj.get("dtypes", {})},
            "symbols": prog["symbols"], "design_point": prog["design_point"],
            "clock": {"port": CLK}, "reset": {"port": RST, "active": "low", "sync": False},
            "control": control, "streams": streams, "pins": [], "scalars": scalars, "baked": q.get("baked", {}),
            "left_out": [d for d in prog["dmas"]], "sizes": sizes}


def program_cycles(prog: dict) -> tuple[int, str]:
    """The program's window from its jobs' busy cycles (group_counter each): a job runs from its start for its
    cycles, a wait holds the next op until the group's jobs started so far have ended; the CSR traffic between
    is not counted. Its first start to its last end."""
    t, start, end, by_group = 0, {}, {}, {}
    for o in prog["ops"]:
        if o["op"] == "start":
            j = o["job"]
            start[j], end[j] = t, t + prog["jobs"][j]["cycles"]
            by_group.setdefault(o["group"], []).append(j)
        elif o["op"] == "wait":
            t = max([t] + [end[j] for j in by_group.get(o["group"], [])])
    first = min(start.values())
    cyc = [f"{j['task']} {j['cycles']}" for j in prog["jobs"]]
    return max(end.values()) - first, (f"snax-forge's group_counter per job ({', '.join(cyc)}), the jobs in the "
                                       "program's order, a wait ending its group's jobs")
