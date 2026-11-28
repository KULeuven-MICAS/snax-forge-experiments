"""sim/sources/xls.py - a Google XLS point -> tb.json.

dslx-exercises is not changed for this: the adapter reads what it writes (the point's filelist.f and sizes.txt, the
kernel's params.json with its channels and cfg fields), hls-exercises' params.json for the streams' names in
sim/ref.py (matched by position) and the netlist's port list, every port covered. build() writes tb.json as
sources/hls.py's, with one cfg beat (its fields and the expected cycles in build()'s docstring); docs/power.md,
"XLS", has the testbench and the window.
"""
from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path

from . import ROOT, cycle_line, hls
from . import ports as _ports

TB_VERSION = 1
CLK, RST = _ports("xls")
DSLX = Path(os.environ.get("SIM_XLS", ROOT.parent / "dslx-exercises")).resolve()
RTL = DSLX / "rtl"
KERNELS = DSLX / "kernels"
CFG = {"data": "_cfg_TDATA", "valid": "_cfg_TVALID", "ready": "_cfg_TREADY"}
CFG_BITS = {"loop_count": 32, "len": 32, "alpha": 64}      # the cfg fields' widths (the kernels' .x structs)
CONTROL_KINDS = {"xls_cfg"}


def filelist(point: str) -> str:
    m = re.search(r"^#\s*top:\s*(\S+)", (RTL / point / "filelist.f").read_text(), re.M)
    if not m:
        raise ValueError(f"{point}: filelist.f has no '# top:' line")
    return m.group(1)


def sizes_txt(point: str) -> list[str]:
    lines = (RTL / point / "sizes.txt").read_text().splitlines()
    return [ln.split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def params_of(point: str) -> dict:
    tier, kernel, _ = point.split("/")
    return json.loads((KERNELS / tier / kernel / "params.json").read_text())


def build(point: str, netlist: Path) -> dict:
    """tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
      source  "xls"
      clock   {port}                               clk (syn/syn.py's SOURCES)
      reset   {port, active: high, sync: true}     rst; the generated top drives it with the TB's ~rst_n
      control {kind: "xls_cfg", data, valid, ready, bits, fields: [{name, bits, from: "config" | "data:<name>"}]}
              one cfg beat on _cfg_TDATA, presented by sim/tb/xls_seq.sv; the fields packed in params.json's cfg
              order, the first in the high bits (XLS flattens a tuple MSB first; dslx-exercises tb/: cfg carries
              {loop_count, len}, loop_count in bits [63:32]); widths from CFG_BITS, their sum must be _cfg_TDATA's
              width; config fields from the cfg expressions at the size, alpha drawn as a rand64 data pin after the
              streams
      streams [{arg, xls_arg, dir, kind: "axis", lanes, dtype, data, valid, ready}]   _<xls_arg>_TDATA/_TVALID/
              _TREADY, inputs then outputs; arg is the hls-exercises name (sim/ref.py, the plusargs); dtype and
              lanes as sources/hls.py's, from dslx-exercises' params.json (X119)
      pins    []
      sizes   as sources/hls.py's, from the config fields (no n2048 at a narrow point)
      ref     as sources/hls.py's, a narrow point only (forge_kernel and forge_types from hls-exercises' params.json)
    Expected cycles: cycles (the cfg transfer to the last output beat) at a size of results/xls/xls_cycles.csv
    (status ok), else the line a x loop_count + b through its sizes, plus 1: the window counts the rising edges from the cfg
    transfer edge to the last output's transfer edge, both included (XLS's datapath is combinational, so the last
    beat is computed in the cycle that ends at its transfer edge).
    """
    top = filelist(point)
    prm = params_of(point)
    case, w = hls.case_w(point)
    if case != "xls":
        raise ValueError(f"{point}: case {case}, not xls")
    ports = hls.ports_of(netlist, top)
    for p in (CLK, RST, *CFG.values()):
        if p not in ports:
            raise ValueError(f"{point}: no port {p} on {top}")
    if ports[CFG["data"]][0] != "in" or ports[CFG["ready"]][0] != "out":
        raise ValueError(f"{point}: _cfg is not an input channel")

    fields = []
    for name, expr in prm["cfg"].items():
        if name not in CFG_BITS:
            raise ValueError(f"{point}: cfg field {name} has no width in sim/sources/xls.py CFG_BITS")
        fields.append({"name": name, "bits": CFG_BITS[name],
                       "from": f"data:{name}" if str(expr).startswith("IN_") else "config"})
    cw = ports[CFG["data"]][1]
    if sum(f["bits"] for f in fields) != cw:
        raise ValueError(f"{point}: cfg fields {[(f['name'], f['bits']) for f in fields]} sum to "
                         f"{sum(f['bits'] for f in fields)} bits, _cfg_TDATA is {cw}")

    hprm = json.loads((hls.HLS / prm["hls_exercises"] / "params.json").read_text())
    xargs = [(a, "in") for a in prm["inputs"]] + [(a, "out") for a in prm["outputs"]]
    if len(xargs) != len(hprm["axis"]):
        raise ValueError(f"{point}: {len(xargs)} channels, hls-exercises' axis has {hprm['axis']}")
    streams = []
    for (xarg, side), harg in zip(xargs, hprm["axis"]):
        base = f"_{xarg}"
        if f"{base}_TDATA" not in ports:
            raise ValueError(f"{point}: no channel {base}_TDATA")
        d, bits = ports[f"{base}_TDATA"]
        if d != side:
            raise ValueError(f"{point}: {base}_TDATA is {d}, expected {side}")
        dt = hls.stream_dtype(prm, d)
        streams.append({"arg": harg, "xls_arg": xarg, "dir": d, "kind": "axis",
                        "lanes": hls.lanes_of(point, f"{base}_TDATA", bits, dt),
                        "dtype": dt, "data": f"{base}_TDATA", "valid": f"{base}_TVALID",
                        "ready": f"{base}_TREADY"})

    known = {CLK, RST, *CFG.values()} | {s[k] for s in streams for k in ("data", "valid", "ready")}
    extra = sorted(set(ports) - known)
    if extra:
        raise ValueError(f"{point}: ports tb.json does not cover: {extra}")

    config = {f["name"]: prm["cfg"][f["name"]] for f in fields if f["from"] == "config"}
    tb = {"tb_version": TB_VERSION, "source": "xls", "point": point, "kernel": prm["kernel"], "top": top,
          "case": case, "W": w,
          "clock": {"port": CLK}, "reset": {"port": RST, "active": "high", "sync": True},
          "control": {"kind": "xls_cfg", **CFG, "bits": cw, "fields": fields},
          "streams": streams, "pins": [], "sizes": hls.sizes_for(point, prm["sizes"], config, w,
                                                                 extra=not hls.narrow(prm))}
    if hls.narrow(prm):
        tb["ref"] = hls.narrow_ref({**hprm, **prm}, streams)     # forge_kernel and forge_types from either
    return tb


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    if tb["control"]["kind"] not in CONTROL_KINDS:
        raise ValueError(f"control.kind {tb['control']['kind']}: only xls_cfg is built here")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    hls.check_streams(tb)


def default_size(tb: dict) -> str:
    return hls.default_size(tb)


def cfg_word(tb: dict, values: dict) -> int:
    """The cfg beat: the fields in order, the first in the high bits."""
    v = 0
    for f in tb["control"]["fields"]:
        v = (v << f["bits"]) | (int(values[f["name"]]) & ((1 << f["bits"]) - 1))
    return v


def expected_cycles(tb: dict, size: str, results: Path) -> tuple[int | None, str]:
    """cycles of the point's ok row of results/xls/xls_cycles.csv at this size, else the line through them at this
    size; plus 1 (the window)."""
    tier = tb["point"].split("/")[0]
    pts = {}
    with (results / "xls_cycles.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["tier"], r["kernel"], r["case"], r["W"], r["status"]) == (tier, tb["kernel"], "xls",
                                                                           str(tb["W"]), "ok"):
                lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
                pts[r["size"]] = (lc, int(r["cycles"]))
    if size in pts and pts[size][0] == tb["sizes"][size]["loop_count"]:
        return pts[size][1] + 1, f"cycles at {size}, + 1"
    try:
        a, b = cycle_line(pts)
    except ValueError as e:
        return None, f"xls_cycles.csv: {e}"
    return a * tb["sizes"][size]["loop_count"] + b + 1, f"cycles line {a} x loop_count + {b}, + 1 ({', '.join(pts)})"
