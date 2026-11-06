"""sim/sources/char.py - a CHAR1 block point -> tb.json, and the slot schedule its sequencer drives (X14).

A char point is one snax-forge catalogue block alone (char/blocks.py, rtl/char/<point>.zip: point.json, emitted.json, unpacked by sim/pwr.py),
synthesized by syn/syn.py --source char. It has no CSRs, no START and no done: a sequencer of sim/tb/ drives its
data and pins as its group's control unit would, through fixed windows, and every output is compared at every
falling edge (sim/pwr.py --source char, docs/power.md, Char).

tb.json:
  tb_version, source "char", point, datapath, params, kind, top, W (lanes), depth, snax_forge_commit
  clock    {port: clock}
  reset    {port: reset, active: high, sync: false}
  control  {kind: "char_<kind>"}
  data_in  [port, ...]   every 64-bit data input, one per lane, in the catalogue's port order then lane order
                         (ElementwiseLanes and Mac: a_0 .. a_{W-1}, b_0 ..; the others in_0 ..): rand64 draws
                         one stream per port in this order (X19)
  outs     [port, ...]   every 64-bit data output (out, or out_0 .. out_{W-1})
  pins     {name: {port, bits}}  the kind's pins present in the netlist: a pin of no bits is absent (LinkBuffer's
                         wslot and rslot at depth 1, SerialAccumulate's lane at lanes 1)
  windows  [{name, cycles, fires}]  in the order the sequencer runs them (schedule())
  tb_files [sim/tb/ files]  the kind's sequencer and the shared core it includes

The ports must be exactly clock, reset, data_in, outs and the present pins (ElementwiseLanes keeps an unused clock
and reset). The kinds, by datapath: lanes (ElementwiseLanes), fold (Mac in its accumulating form, TreeAccumulate),
serial (SerialAccumulate), link (LinkBuffer).

schedule(tb) is the sequence of slots the kind's sequencer drives after reset, slot by slot: 4 settle slots with
every pin and data input low, then per window a lead-in of the window's own kind (outside every window) and the
window's slots. The windows (CHAR1 R2): lanes, fold and serial have busy (a fire every cycle; serial a read every
cycle, 128 beats of W) and idle (the enable at 0, every other input held), each after one lead-in slot; link has
stream only, a FIFO at full rate: a lead-in of D loads round the ring (the fill), then 128 cycles with a load of
new data every cycle into slot t mod D and rslot the oldest slot, the same slot (read before the edge that
overwrites it), so out at cycle t is the beat loaded at t - D. A slot's inputs are applied at its rising edge (after the flops have taken the slot
before, as SYN1 and SYN2's TBs and a block's neighbours inside an accelerator change them), the outputs are sampled
at its falling edge, and the next rising edge takes it. A window's rising edges are its own slots' input changes
and the captures of its lead-in and its own slots but the last, which falls on the next lead-in's edge: every
window measures its own kind only. sim/tb/char_<kind>_seq.sv implements the same loops; the TB prints each
window's cycles and fires and sim/pwr.py checks them against this.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import hls
from . import ports as _ports

CLK, RST = _ports("char")    # clock, reset: syn/syn.py's SOURCES

TB_VERSION = 1
ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl" / "char"
SETTLE = 4          # slots with every input low after reset
CYCLES = 128        # each window's cycles (beats for serial's firing windows)
KINDS = {"ElementwiseLanes": "lanes", "Mac": "fold", "TreeAccumulate": "fold", "SerialAccumulate": "serial",
         "LinkBuffer": "link"}
INS = {"ElementwiseLanes": ["a", "b"], "Mac": ["a", "b"], "TreeAccumulate": ["in"], "SerialAccumulate": ["in"],
       "LinkBuffer": ["in"]}
PINS = {"lanes": [], "fold": ["fire", "first"], "serial": ["read", "lane", "first"], "link": ["load", "wslot", "rslot"]}
WINDOWS = {"lanes": ["busy", "idle"], "fold": ["busy", "idle"], "serial": ["busy", "idle"], "link": ["stream"]}
SEQ_FILES = {k: [f"char_{k}_seq.sv"] for k in PINS}
CORE = "char_seq_core.svh"


def point_dir(point: str, bundle: Path) -> Path:
    """The block, unpacked from rtl/char/<point>.zip by sim/pwr.py (X51), with the files it needs."""
    for f in ("point.json", "emitted.json"):
        if not (bundle / f).is_file():
            raise FileNotFoundError(f"{point}: no {f} in {RTL / point}.zip (pixi run char-rtl)")
    return bundle


def pin_bits(datapath: str, params: dict) -> dict:
    """The kind's pins and their widths from the Chisel source; 0 bits = absent from the netlist."""
    w = params.get("lanes", 1)
    if datapath == "SerialAccumulate":
        return {"read": 1, "lane": math.ceil(math.log2(w)) if w > 1 else 0, "first": 1}
    if datapath == "LinkBuffer":
        d = params["depth"]
        return {"load": 1, "wslot": math.ceil(math.log2(d)) if d > 1 else 0,
                "rslot": math.ceil(math.log2(d)) if d > 1 else 0}
    return {p: 1 for p in PINS[KINDS[datapath]]}


def _order(ports: list[str], bases: list[str]) -> list[str]:
    def key(p: str):
        m = re.fullmatch(r"io_([a-z]+)(?:_(\d+))?", p)
        return bases.index(m.group(1)), int(m.group(2) or 0)
    return sorted(ports, key=key)


def build(point: str, netlist: Path, bundle: Path) -> dict:
    d = point_dir(point, bundle)
    pj = json.loads((d / "point.json").read_text())
    top = json.loads((d / "emitted.json").read_text())["top"]
    dp, params = pj["datapath"], pj["params"]
    if dp not in KINDS:
        raise ValueError(f"{point}: datapath {dp} has no testbench kind")
    if dp == "Mac" and not params.get("accumulate"):
        raise ValueError(f"{point}: only the accumulating Mac is built (fold kind)")
    kind = KINDS[dp]
    ports = hls.ports_of(netlist, top)
    bits = pin_bits(dp, params)
    pins = {n: {"port": f"io_{n}", "bits": b} for n, b in bits.items() if b}
    data_re = re.compile(rf"io_({'|'.join(INS[dp])})(_\d+)?")
    data_in = [p for p, (dr, _) in ports.items() if dr == "in" and data_re.fullmatch(p)]
    outs = [p for p, (dr, _) in ports.items() if dr == "out" and re.fullmatch(r"io_out(_\d+)?", p)]
    known = {CLK, RST, *data_in, *outs, *(p["port"] for p in pins.values())}
    if set(ports) != known:
        raise ValueError(f"{point}: netlist ports not as expected: missing {sorted(known - set(ports))}, "
                         f"not covered {sorted(set(ports) - known)}")
    for p in data_in + outs:
        if ports[p][1] != 64:
            raise ValueError(f"{point}: {p} is {ports[p][1]} bits, not one int64 lane")
    for n, p in pins.items():
        if ports[p["port"]] != ("in", p["bits"]):
            raise ValueError(f"{point}: pin {p['port']} is {ports[p['port']]}, expected an input of {p['bits']} bits")
    for n, b in bits.items():
        if not b and f"io_{n}" in ports:
            raise ValueError(f"{point}: pin io_{n} should have no bits and be absent")
    tb = {"tb_version": TB_VERSION, "source": "char", "point": point, "datapath": dp, "params": params, "kind": kind,
          "top": top, "W": params.get("lanes", 1), "depth": params.get("depth", ""),
          "snax_forge_commit": pj["snax_forge_commit"],
          "clock": {"port": CLK}, "reset": {"port": RST, "active": "high", "sync": False},
          "control": {"kind": f"char_{kind}"},
          "data_in": _order(data_in, INS[dp]), "outs": _order(outs, ["out"]), "pins": pins,
          "tb_files": SEQ_FILES[kind]}
    slots = schedule(tb)
    tb["windows"] = [{"name": w, "cycles": sum(1 for s in slots if s["window"] == w),
                      "fires": sum(1 for s in slots if s["window"] == w and s["fire"])} for w in WINDOWS[kind]]
    return tb


def check(tb: dict) -> None:
    """What sim/pwr.py relies on."""
    if tb["tb_version"] != TB_VERSION or tb["source"] != "char":
        raise ValueError(f"tb_version {tb['tb_version']} source {tb['source']}: not a char tb.json {TB_VERSION}")
    if tb["control"]["kind"] != f"char_{tb['kind']}" or tb["kind"] not in PINS:
        raise ValueError(f"control.kind {tb['control']['kind']}: not a char kind")
    if [w["name"] for w in tb["windows"]] != WINDOWS[tb["kind"]]:
        raise ValueError(f"windows {tb['windows']}: not the {tb['kind']} kind's")


def default_size(tb: dict) -> str:
    return "windows"


def schedule(tb: dict) -> list[dict]:
    """Every slot after reset: {window (None while settling), new (a new data beat), fire (the block works:
    new data for lanes, fire, read or load), pins {name: value}} (docs/power.md, Char)."""
    kind, w = tb["kind"], tb["W"]
    depth = tb["depth"] or 1
    out = []

    def slot(win, new, fired, /, **pins):       # positional only: the fold kind has a pin named fire
        out.append({"window": win, "new": bool(new), "fire": bool(fired), "pins": pins})

    for _ in range(SETTLE):
        slot(None, 0, 0, **{p: 0 for p in PINS[kind]})
    if kind == "lanes":
        slot(None, 1, 1)                                  # lead-in: new data
        for i in range(CYCLES):
            slot("busy", 1, 1)
        slot(None, 0, 0)
        for i in range(CYCLES):
            slot("idle", 0, 0)
    elif kind == "fold":
        slot(None, 1, 1, fire=1, first=1)                 # the restart
        for i in range(CYCLES):
            slot("busy", 1, 1, fire=1, first=0)
        slot(None, 0, 0, fire=0, first=0)
        for i in range(CYCLES):
            slot("idle", 0, 0, fire=0, first=0)           # every input held, first included (busy's 0)
    elif kind == "serial":
        slot(None, 0, 1, read=1, lane=w - 1, first=0)     # a read of the held beat's last lane
        for b in range(CYCLES):
            for lane in range(w):
                slot("busy", lane == 0, 1, read=1, lane=lane, first=int(b == 0 and lane == 0))
        slot(None, 0, 0, read=0, lane=w - 1, first=0)
        for i in range(CYCLES):
            slot("idle", 0, 0, read=0, lane=w - 1, first=0)        # lane held at the last read's
    elif kind == "link":
        for t in range(depth):                            # the lead-in: the fill, D loads round the ring
            slot(None, 1, 1, load=1, wslot=t, rslot=t)
        for t in range(CYCLES):                           # full rate at full occupancy: read the oldest, which is
            slot("stream", 1, 1, load=1, wslot=t % depth, rslot=t % depth)   # the slot this edge overwrites
    else:
        raise ValueError(f"kind {kind}")
    return out
