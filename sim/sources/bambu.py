"""sim/sources/bambu.py - a Bambu point -> tb.json.

hls-exercises is not changed for this: the adapter reads what bench/bambu.py writes (the point's filelist.f and
sizes.txt), the kernel's bench params.json (shared with Vitis) and the netlist's port list, every port covered.
build() writes tb.json as sources/hls.py's, with Bambu's handshake (its fields and the expected cycles in build()'s
docstring); docs/power.md, "Bambu", has the testbench and the window.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

from . import cycle_line, hls
from . import ports as _ports

TB_VERSION = 1
CLK, RST = _ports("bambu")
CONTROL = {"start": "start_port", "done": "done_port", "idle": "idle_port"}
CONTROL_KINDS = {"bambu_ctl"}


def sizes_txt(point: str) -> list[str]:
    return hls.sizes_txt(point)      # the same rtl/ root as Vitis's


def build(point: str, netlist: Path) -> dict:
    """tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
      source  "bambu"
      clock   {port}                               clock (syn/syn.py's SOURCES)
      reset   {port, active: low, sync: true}      reset
      control {kind: "bambu_ctl", start: start_port, done: done_port, idle: idle_port}
              start_port pulsed for one cycle by sim/tb/bambu_seq.sv; idle_port an output nobody reads (covered,
              not driven or checked)
      streams [{arg, dir, kind: "axis", lanes, dtype, data, valid, ready}]   <arg>_TDATA/_TVALID/_TREADY (or
              p_<arg>_...), in params.json's axis order; dtype and lanes as sources/hls.py's (an input at
              dtype, an output at acc_dtype; lanes = TDATA bits / the element's bits, X119)
      pins    [{port, bits, from: "config" | "data:<arg>"}]   loop_count, len (where the kernel has it), alpha
              (axpy): plain inputs, no ap_vld; driven from time 0, before reset is released, and held for the
              whole run (Bambu reads them on every iteration, hls-exercises tb/bambu.svh); alpha drawn as a rand64
              data pin after the streams
      sizes   as sources/hls.py's: the cosim sizes, b64 when every config pin equals loop_count, n2048 (not at
              a narrow point)
      ref     as sources/hls.py's, a narrow point only
    Expected cycles: cycles_done at a size of results/bambu/bambu_cycles.csv (status ok rows; cycles_done is
    start_port's cycle to done_port's, as the window counts), else the line a x loop_count + b through its sizes,
    integer and exact at them.
    """
    top = hls.filelist(point)["top"]
    prm = hls.params_of(point)
    case, w = hls.case_w(point)
    if case != "bambu":
        raise ValueError(f"{point}: case {case}, not bambu")
    if prm.get("iface") != "axis":
        raise ValueError(f"{point}: iface {prm.get('iface')}, only axis is built")
    ports = hls.ports_of(netlist, top)
    for p in (CLK, RST, *CONTROL.values()):
        if p not in ports:
            raise ValueError(f"{point}: no port {p} on {top}")
    if ports[CONTROL["idle"]][0] != "out" or ports[CONTROL["done"]][0] != "out":
        raise ValueError(f"{point}: done_port or idle_port is not an output")

    types = hls.narrow_types(prm) if hls.narrow(prm) else None
    streams = []
    for arg in prm["axis"]:
        base = next((b for b in (arg, f"p_{arg}") if f"{b}_TDATA" in ports), None)
        if base is None:
            raise ValueError(f"{point}: no AXI-stream port for argument {arg}")
        d, bits = ports[f"{base}_TDATA"]
        dt = hls.stream_dtype(prm, d, arg, types)
        streams.append(hls.axis_stream(point, prm, arg, d, dt, hls.lanes_of(point, f"{base}_TDATA", bits, dt), w,
                                       f"{base}_TDATA", f"{base}_TVALID", f"{base}_TREADY"))

    pins = []
    for name in list(prm.get("config", {})) + list(prm.get("scalars", [])):
        if name not in ports or ports[name][0] != "in":
            raise ValueError(f"{point}: no input pin {name}")
        pins.append({"port": name, "bits": ports[name][1],
                     "from": "config" if name in prm.get("config", {}) else f"data:{name}",
                     **hls.data_dtype(name, prm, types)})

    known = {CLK, RST, *CONTROL.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    known |= {p["port"] for p in pins}
    extra = sorted(set(ports) - known)
    if extra:
        raise ValueError(f"{point}: ports tb.json does not cover: {extra}")

    tb = {"tb_version": TB_VERSION, "source": "bambu", "point": point, "kernel": prm["kernel"], "top": top,
          "case": case, "W": w,
          "clock": {"port": CLK}, "reset": {"port": RST, "active": "low", "sync": True},
          "control": {"kind": "bambu_ctl", **CONTROL}, "streams": streams, "pins": pins,
          "sizes": hls.sizes_for(point, prm["sizes"], prm["config"], w, prm.get("valid"), b64="streams" not in prm,
                                 extra=not hls.narrow(prm))}
    return hls.with_ref(tb, point, prm, w)


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    if tb["control"]["kind"] not in CONTROL_KINDS:
        raise ValueError(f"control.kind {tb['control']['kind']}: only bambu_ctl is built here")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    hls.check_streams(tb)


def default_size(tb: dict) -> str:
    return hls.default_size(tb)


def expected_cycles(tb: dict, size: str, results: Path) -> tuple[int | None, str]:
    """cycles_done of the point's ok row of results/bambu/bambu_cycles.csv at this size, else the line through
    them at this size (a narrow point has one size, X119)."""
    tier = tb["point"].split("/")[0]
    pts = {}
    with (results / "bambu_cycles.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["tier"], r["kernel"], r["case"], r["W"], r["status"]) == (tier, tb["kernel"], "bambu",
                                                                           str(tb["W"]), "ok"):
                lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
                pts[r["size"]] = (lc, int(r["cycles_done"]))
    if size in pts and pts[size][0] == tb["sizes"][size]["loop_count"]:
        return pts[size][1], f"cycles_done at {size}"
    try:
        a, b = cycle_line(pts)
    except ValueError as e:
        return None, f"bambu_cycles.csv: {e}"
    return a * tb["sizes"][size]["loop_count"] + b, f"cycles_done line {a} x loop_count + {b} ({', '.join(pts)})"
