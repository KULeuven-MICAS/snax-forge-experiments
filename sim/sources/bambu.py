"""sim/sources/bambu.py - a Bambu point -> tb.json (docs/DECISIONS.md X44).

hls-exercises is not changed for this: the adapter reads what bench/bambu.py writes and the netlist.
  - rtl/<tier>/<kernel>/bambu_w<W>/filelist.f  the top module ('# top:'), '# ram:'
  - rtl/<tier>/<kernel>/bambu_w<W>/sizes.txt   the sizes (--size all)
  - bench/tier_<tier>/<kernel>/params.json     the stream args in order ("axis"), the config pins and their
                                               expressions, the scalar args, the sizes (shared with Vitis)
  - the netlist's port list                    every port must be covered

tb.json for the generated TB top (sim/pwr.py), as sources/hls.py's with:
  source  "bambu"
  clock   {port}                               clock (syn/syn.py's SOURCES)
  reset   {port, active: low, sync: true}      reset
  control {kind: "bambu_ctl", start: start_port, done: done_port, idle: idle_port}
          start_port pulsed for one cycle by sim/tb/bambu_seq.sv; idle_port an output nobody reads (covered,
          not driven or checked)
  streams [{arg, dir, kind: "axis", lanes, dtype, data, valid, ready}]   <arg>_TDATA/_TVALID/_TREADY (or
          p_<arg>_...), in params.json's axis order; lanes = TDATA bits / 64
  pins    [{port, bits, from: "config" | "data:<arg>"}]   loop_count, len (where the kernel has it), alpha
          (axpy): plain inputs, no ap_vld; driven from time 0, before reset is released, and held for the
          whole run (Bambu reads them on every iteration, hls-exercises tb/bambu.svh); alpha drawn as a rand64
          data pin after the streams (X19)
  sizes   as sources/hls.py's: the cosim sizes, b64 when every config pin equals loop_count, n2048 (X24, X55)
Expected cycles: the line a x loop_count + b through cycles_done at the point's sizes in
results/bambu/bambu_cycles.csv (status ok rows; cycles_done is start_port's cycle to done_port's, as the
window counts), integer and exact at those sizes.
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

    streams = []
    for arg in prm["axis"]:
        base = next((b for b in (arg, f"p_{arg}") if f"{b}_TDATA" in ports), None)
        if base is None:
            raise ValueError(f"{point}: no AXI-stream port for argument {arg}")
        d, bits = ports[f"{base}_TDATA"]
        if bits % 64:
            raise ValueError(f"{point}: {base}_TDATA is {bits} bits, not a multiple of 64")
        streams.append({"arg": arg, "dir": d, "kind": "axis", "lanes": bits // 64, "dtype": prm["dtype"],
                        "data": f"{base}_TDATA", "valid": f"{base}_TVALID", "ready": f"{base}_TREADY"})

    pins = []
    for name in list(prm.get("config", {})) + list(prm.get("scalars", [])):
        if name not in ports or ports[name][0] != "in":
            raise ValueError(f"{point}: no input pin {name}")
        pins.append({"port": name, "bits": ports[name][1],
                     "from": "config" if name in prm.get("config", {}) else f"data:{name}"})

    known = {CLK, RST, *CONTROL.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    known |= {p["port"] for p in pins}
    extra = sorted(set(ports) - known)
    if extra:
        raise ValueError(f"{point}: ports tb.json does not cover: {extra}")

    return {"tb_version": TB_VERSION, "source": "bambu", "point": point, "kernel": prm["kernel"], "top": top,
            "case": case, "W": w,
            "clock": {"port": CLK}, "reset": {"port": RST, "active": "low", "sync": True},
            "control": {"kind": "bambu_ctl", **CONTROL}, "streams": streams, "pins": pins,
            "sizes": hls.sizes_for(point, prm["sizes"], prm["config"], w, prm.get("valid"))}


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    if tb["control"]["kind"] not in CONTROL_KINDS:
        raise ValueError(f"control.kind {tb['control']['kind']}: only bambu_ctl is built here")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    for s in tb["streams"]:
        if s["kind"] != "axis" or s["dtype"] != "int64":
            raise ValueError(f"stream {s['arg']}: {s['kind']} {s['dtype']}, only axis int64 is built")


def default_size(tb: dict) -> str:
    return hls.default_size(tb)


def expected_cycles(tb: dict, size: str, results: Path) -> tuple[int | None, str]:
    """cycles_done's line through the point's ok rows of results/bambu/bambu_cycles.csv, at this size."""
    tier = tb["point"].split("/")[0]
    pts = {}
    with (results / "bambu_cycles.csv").open(newline="") as fh:
        for r in csv.DictReader(fh):
            if (r["tier"], r["kernel"], r["case"], r["W"], r["status"]) == (tier, tb["kernel"], "bambu",
                                                                           str(tb["W"]), "ok"):
                lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
                pts[r["size"]] = (lc, int(r["cycles_done"]))
    try:
        a, b = cycle_line(pts)
    except ValueError as e:
        return None, f"bambu_cycles.csv: {e}"
    return a * tb["sizes"][size]["loop_count"] + b, f"cycles_done line {a} x loop_count + {b} ({', '.join(pts)})"
