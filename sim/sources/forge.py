"""sim/sources/forge.py - a snax-forge point -> tb.json (docs/DECISIONS.md X14).

snax-forge is not changed for this: the adapter reads its bundle in rtl/forge/<point>/ (forge/bundles.py)
and asks snax-forge's own code for the rest (forge/query.py, run in snax-forge's pixi environment):
  - point.json          recipe, W, snax_forge_commit
  - bundle.json         top, the design point (for the containers, through forge/query.py point)
  - accelerator.json    its one group's CSRs by offset (START, JOBS, a unit's JOB_BEATS, STATUS, COUNTER),
                        its outer ports in order (inputs, then outputs) with lanes and dtype
  - <tag>_streamer.hjson  each mover's num_channel (the port's 64-bit words per beat)
  - the netlist's port list  every port must be covered (snax-forge docs/CONTRACTS.md section 17, The wrapper)

tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
  tb_version, source "forge", point, kernel, recipe, top, case, W, snax_forge_commit
  clock   {port: clk_i}
  reset   {port: rst_ni, active: low, sync: false}
  control {kind: "forge_csr", group, req_addr, req_data, req_write, req_valid, req_ready,
           rsp_data, rsp_valid, rsp_ready, busy, done, csrs: {name: offset}}
  streams [{arg, end, dir, kind: "stream", lanes, num_ch, dtype, data, valid, ready}]
           arg the container the design point binds the port to (the kernel's array, sim/ref.py's name)
  pins    []
  sizes   {n2048: {N, jobs, beats: {unit: JOB_BEATS}, writes: [[offset, value, name], ... START last],
                   stream_beats: {arg: beats}, expected_cycles, expected_from}}
          expected_cycles: the group's busy cycles from snax-forge's model (forge/query.py cycles:
          gen/rtl.py's group_counter) with JOBS and the units' T as the program writes them; the TB's
          window and the COUNTER it reads back must equal it.

The CSRs (C§17, Programming): an elementwise group runs N / W jobs of one beat (JOBS = N / W); a group with
a fold (a unit with JOB_BEATS) one job of N / W beats (JOBS = 1, JOB_BEATS = N / W). One group only (dot 1
is not in SYN1), at most one JOB_BEATS and no other read-write CSR.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
from pathlib import Path

from . import hls

TB_VERSION = 1
ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl" / "forge"
QUERY = ROOT / "forge" / "query.py"
SIZES = {"n2048": 2048}          # one size for every SYN1 comparison
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


def bundle_of(point: str) -> Path:
    b = RTL / point
    for f in ("bundle.json", "accelerator.json", "point.json"):
        if not (b / f).is_file():
            raise FileNotFoundError(f"{point}: no {f} in {b} (pixi run forge-rtl)")
    return b


def streamer_channels(b: Path, tag: str) -> dict:
    text = "\n".join(ln for ln in (b / f"{tag}_streamer.hjson").read_text().splitlines()
                     if not ln.lstrip().startswith("//"))
    d = json.loads(text)
    return {"in": d.get("data_reader_params", {}).get("num_channel", []),
            "out": d.get("data_writer_params", {}).get("num_channel", [])}


def build(point: str, netlist: Path) -> dict:
    b = bundle_of(point)
    bundle = json.loads((b / "bundle.json").read_text())
    acc = json.loads((b / "accelerator.json").read_text())
    pj = json.loads((b / "point.json").read_text())
    top, w = bundle["top"], int(pj["W"])
    case = point.split("/")[2].rsplit("_w", 1)[0]
    if len(acc["groups"]) != 1:
        raise ValueError(f"{point}: {len(acc['groups'])} groups; one is supported (dot 1 is not in SYN1)")
    (g,) = acc["groups"]
    ports = hls.ports_of(netlist, top)

    csrs = {c["name"]: c["offset"] for c in g["csrs"]}
    unit_csrs = [(u["name"], c) for u in g["units"] for c in u.get("csrs", [])]
    for need in ("START", "JOBS", "STATUS", "COUNTER"):
        if need not in csrs:
            raise ValueError(f"{point}: group {g['name']} has no {need} CSR")
    other = [f"{u}.{c['name']}" for u, c in unit_csrs if c["name"] != "JOB_BEATS"]
    folds = [(u, c) for u, c in unit_csrs if c["name"] == "JOB_BEATS"]
    if other or len(folds) > 1:
        raise ValueError(f"{point}: read-write CSRs beyond JOBS and one JOB_BEATS: {other + [u for u, _ in folds]}")
    for u, c in folds:
        csrs[f"{u}.JOB_BEATS"] = c["offset"]

    control = {"kind": "forge_csr", "group": g["name"], **CSR_PORTS,
               "busy": f"{g['name']}_busy_o", "done": f"{g['name']}_done_o", "csrs": csrs}

    q = query("point", str(b))
    container = {p["end"]: p["container"] for p in q["ports"]}
    units = {u["name"]: u for u in g["units"]}
    nch = streamer_channels(b, bundle["tag"])
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
            streams.append({"arg": container[end], "end": end, "dir": side, "kind": "stream", "lanes": p["lanes"],
                            "num_ch": num_ch, "dtype": p["dtype"], "data": data,
                            "valid": f"{pre}_{k}_valid_{'i' if side == 'in' else 'o'}",
                            "ready": f"{pre}_{k}_ready_{'o' if side == 'in' else 'i'}"})

    known = {"clk_i", "rst_ni", control["busy"], control["done"], *CSR_PORTS.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    missing = sorted(known - set(ports))
    extra = sorted(set(ports) - known)
    if missing or extra:
        raise ValueError(f"{point}: netlist ports not as C§17's wrapper: missing {missing}, not covered {extra}")

    sizes = {}
    for tag, n in SIZES.items():
        if n % w:
            raise ValueError(f"{point}: N {n} is not a multiple of W {w}")
        if folds:
            jobs, beats = 1, {folds[0][0]: n // w}
        else:
            jobs, beats = n // w, {}
        writes = [[csrs["JOBS"], jobs, "JOBS"]] + [[csrs[f"{u}.JOB_BEATS"], v, f"{u}.JOB_BEATS"] for u, v in beats.items()]
        writes.append([csrs["START"], 1, "START"])
        cyc = query("cycles", str(b), str(jobs), json.dumps(beats))
        stream_beats = {s["arg"]: (n // s["lanes"] if s["dir"] == "in" else None) for s in streams}
        sizes[tag] = {"N": n, "jobs": jobs, "beats": beats, "writes": writes, "stream_beats": stream_beats,
                      "expected_cycles": cyc["cycles"], "expected_from": cyc["working"]}

    return {"tb_version": TB_VERSION, "source": "forge", "point": point, "kernel": q["kernel"], "recipe": pj["recipe"],
            "top": top, "case": case, "W": w, "snax_forge_commit": pj["snax_forge_commit"],
            "clock": {"port": "clk_i"}, "reset": {"port": "rst_ni", "active": "low", "sync": False},
            "control": control, "streams": streams, "pins": [], "sizes": sizes}


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
    return "n2048"


def kernel_ref(kernel: str, ins: dict, workdir: Path) -> dict:
    """snax-forge's own reference: the kernel's NumPy body (forge/query.py ref) on `ins`."""
    import numpy as np

    workdir.mkdir(parents=True, exist_ok=True)
    fi, fo = workdir / "ref_in.npz", workdir / "ref_out.npz"
    np.savez(fi, **ins)
    info = query("ref", kernel, str(fi), str(fo))
    out = dict(np.load(fo))
    fi.unlink()
    fo.unlink()
    return {"info": info, "outs": out}


def netlist_modules(netlist: Path) -> set:
    """Every module the netlist defines (DC indents some headers, PITFALLS DC6)."""
    return set(re.findall(r"^\s*module\s+(\S+)\s*\(", netlist.read_text(), re.M))
