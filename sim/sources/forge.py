"""sim/sources/forge.py - a snax-forge point -> tb.json (docs/DECISIONS.md X14).

snax-forge is not changed for this: the adapter reads its bundle, rtl/forge/<point>.zip (forge/bundles.py), unpacked by sim/pwr.py
and asks snax-forge's own code for the rest (forge/query.py, run in snax-forge's pixi environment):
  - point.json          recipe, W, snax_forge_commit
  - bundle.json         top, the design point (for the containers, through forge/query.py point)
  - accelerator.json    its one group's CSRs by offset (START, JOBS, a unit's JOB_BEATS, STATUS, BUSY_COUNTER),
                        its outer ports in order (inputs, then outputs) with lanes and dtype
  - <tag>_streamer_<accelerator>.hjson (<tag>_streamer.hjson in SYN1's bundles)  each mover's num_channel
  - the netlist's port list  every port must be covered (snax-forge docs/CONTRACTS.md section 17, The wrapper)

tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
  tb_version, source "forge", point, kernel, recipe, top, case, W, snax_forge_commit
  clock   {port: clk_i}
  reset   {port: rst_ni, active: low, sync: false}
  control {kind: "forge_csr", group, req_addr, req_data, req_write, req_valid, req_ready,
           rsp_data, rsp_valid, rsp_ready, busy, done, csrs: {name: offset}}
  streams [{arg, name, end, dir, kind: "stream", lanes, num_ch, dtype, data, valid, ready, beats, identity,
            order}]
           arg the container the design point binds the port to (the kernel's array, sim/ref.py's name);
           name the TB's name for the stream: arg, or arg_in / arg_out when one container has an input and an
           output stream (axpy's y, read and written in place); order the container's flat (row-major) element
           of each element the stream carries, beat by beat, lane 0 first, as the bundle's streamer loops visit
           them (forge/query.py program), null when it is the identity
  pins    []
  scalars [{container, dtype, unit, slot, csrs: [[offset, name], ...]}]  a slot read from a scalar container (a
           CSR the program writes before START, C§17: K1, or K1_LO and K1_HI low word first at int64); its value
           drawn as X19 draws a data pin (sim/pwr.py)
  baked   {container: value}  a scalar the recipe bakes (bake_scalar with a value, axpy_baked's alpha = 3): no CSR,
           the value is the reference's
  sizes   {n2048: {shape: {symbol: value}, jobs, beats: {unit: JOB_BEATS}, writes: [[offset, value, name], ...
                   START last], stream_beats: {name: beats}, expected_cycles, expected_from}}
          shape: the point's sets, X55's n2048 shape for its tier and kernel (sim/sources/hls.py's extra_sizes),
          the size the design point was made at. writes: JOBS and each JOB_BEATS as snax-forge's LOWER writes
          them for that design point (forge/query.py program: lower/derive.py's task list, lower/c.py's
          job_writes), then START; sim/pwr.py adds the scalar writes before START. expected_cycles: the group's
          busy cycles from snax-forge's model (forge/query.py cycles: gen/rtl.py's group_counter) with those
          values; the TB's window is the measurement, the BUSY_COUNTER it reads back and this count are recorded
          beside it, each within 5 % of it (X56).

One group only (dot 1 is not in SYN1). Every read-write CSR is START, JOBS, a unit's JOB_BEATS or a scalar's.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

from . import hls
from . import ports as _ports

TB_VERSION = 1
CLK, RST = _ports("forge")   # clk_i, rst_ni: syn/syn.py's SOURCES
ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl" / "forge"
QUERY = ROOT / "forge" / "query.py"
SIZE = "n2048"                   # the one size of a forge point (X24, X55): its shape is the point's sets
CONTROL_KINDS = {"forge_csr"}
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
    """The point's bundle, unpacked from rtl/forge/<point>.zip by sim/pwr.py (X51), with the files it needs."""
    for f in ("bundle.json", "accelerator.json", "point.json"):
        if not (bundle / f).is_file():
            raise FileNotFoundError(f"{point}: no {f} in {RTL / point}.zip (pixi run forge-rtl)")
    return bundle


def streamer_channels(b: Path, tag: str, acc_name: str | None = None) -> dict:
    """Each mover's num_channel: <tag>_streamer_<accelerator>.hjson (one streamer set per accelerator, D157), or
    the SYN1 bundles' <tag>_streamer.hjson."""
    f = b / f"{tag}_streamer_{acc_name}.hjson"
    if acc_name is None or not f.is_file():
        f = b / f"{tag}_streamer.hjson"
    text = "\n".join(ln for ln in f.read_text().splitlines()
                     if not ln.lstrip().startswith("//"))
    d = json.loads(text)
    return {"in": d.get("data_reader_params", {}).get("num_channel", []),
            "out": d.get("data_writer_params", {}).get("num_channel", [])}


def build(point: str, netlist: Path, bundle: Path) -> dict:
    b = bundle_of(point, bundle)
    bundle = json.loads((b / "bundle.json").read_text())
    acc = json.loads((b / "accelerator.json").read_text())
    acc_name = None
    if "accelerators" in acc:      # D157's nested form: one accelerator's groups, inputs and outputs
        if len(acc["accelerators"]) != 1:
            raise ValueError(f"{point}: {len(acc['accelerators'])} accelerators; one is supported")
        acc = acc["accelerators"][0]
        acc_name = acc["name"]
    pj = json.loads((b / "point.json").read_text())
    top, w = bundle["top"], int(pj["W"])
    case = point.split("/")[2].rsplit("_w", 1)[0]
    if len(acc["groups"]) != 1:
        raise ValueError(f"{point}: {len(acc['groups'])} groups; one is supported (dot 1 is not in SYN1)")
    (g,) = acc["groups"]
    # snax-forge D168 (CTRL2) renamed the busy-cycle CSR; its forge/query.py refuses a bundle made before it
    if "BUSY_COUNTER" not in {c["name"] for c in g["csrs"]}:
        raise ValueError(f"{point}: no BUSY_COUNTER CSR (a bundle made before snax-forge D168 names it COUNTER): "
                         "rebundle (pixi run forge-rtl)")
    ports = hls.ports_of(netlist, top)

    # the size: the point's sets are X55's n2048 shape (the design point was made at it, forge/bundles.py)
    shape = {k: int(v) for k, v in (x.split("=", 1) for x in pj.get("sets", []))}
    want = dict(hls.extra_sizes(point)).get(SIZE)
    if want is None or {k.lower(): v for k, v in shape.items()} != want:
        raise ValueError(f"{point}: bundle made with sets {pj.get('sets')}, the n2048 shape (X55) is {want}: "
                         "rebundle (pixi run forge-rtl)")

    q = query("point", str(b))
    prog = query("program", str(b))
    for k, v in shape.items():
        if prog["symbols"].get(k) != v:
            raise ValueError(f"{point}: the design point has {k} = {prog['symbols'].get(k)}, the sets {k} = {v}")

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
        if sc["dtype"] != "int64":
            raise ValueError(f"{point}: scalar {sc['container']} is {sc['dtype']}; only int64 is driven")

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
            if p["dtype"] != "int64" or p["lanes"] != num_ch:
                raise ValueError(f"{point}: {end} {p['dtype']} x {p['lanes']}: only int64, one lane per channel")
            o = order.get(end)
            if o is None or o["container"] != container[end] or o["dir"] != side or o["lanes"] != p["lanes"]:
                raise ValueError(f"{point}: {end}: the program's streamer task {o and {k: o[k] for k in ('container', 'dir', 'lanes')}} "
                                 f"is not the port's ({container[end]}, {side}, {p['lanes']} lanes)")
            streams.append({"arg": container[end], "name": container[end], "end": end, "dir": side,
                            "kind": "stream", "lanes": p["lanes"], "num_ch": num_ch, "dtype": p["dtype"], "data": data,
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
    sizes = {SIZE: {"shape": shape, "jobs": jobs[0], "beats": beats, "writes": writes,
                    "stream_beats": {s["name"]: s["beats"] for s in streams},
                    "expected_cycles": cyc["cycles"], "expected_from": cyc["working"]}}

    return {"tb_version": TB_VERSION, "source": "forge", "point": point, "kernel": q["kernel"], "recipe": pj["recipe"],
            "top": top, "case": case, "W": w, "snax_forge_commit": pj["snax_forge_commit"],
            "dtypes": pj.get("dtypes", {}), "symbols": prog["symbols"],
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
        if s["kind"] != "stream" or s["dtype"] != "int64":
            raise ValueError(f"stream {s['arg']}: {s['kind']} {s['dtype']}, only int64 streams are built")
    for tag, z in tb["sizes"].items():
        if not z["writes"] or z["writes"][-1][2] != "START":
            raise ValueError(f"size {tag}: the writes do not end with START")
        if not isinstance(z["expected_cycles"], int):
            raise ValueError(f"size {tag}: no expected cycles")


def default_size(tb: dict) -> str:
    return SIZE


def kernel_ref(kernel: str, ins: dict, workdir: Path, symbols: dict | None = None, dtypes: dict | None = None) -> dict:
    """snax-forge's own reference: the kernel's NumPy body (forge/query.py ref) on `ins` (a scalar as a 0-d
    array), its outputs sized by `symbols` (the design point's), each container at `dtypes` where given (the
    point's, X57: the recipe's dtypes override the kernel's descriptors, as in the bundle)."""
    import numpy as np

    workdir.mkdir(parents=True, exist_ok=True)
    fi, fo = workdir / "ref_in.npz", workdir / "ref_out.npz"
    np.savez(fi, **ins)
    info = query("ref", kernel, str(fi), str(fo), json.dumps(symbols or {}), json.dumps(dtypes or {}))
    out = dict(np.load(fo))
    fi.unlink()
    fo.unlink()
    return {"info": info, "outs": out}


def netlist_modules(netlist: Path) -> set:
    """Every module the netlist defines (DC indents some headers, PITFALLS DC6)."""
    return set(re.findall(r"^\s*module\s+(\S+)\s*\(", netlist.read_text(), re.M))
