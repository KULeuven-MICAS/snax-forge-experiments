"""sim/sources/char.py - a block point -> tb.json, and the slot schedule its sequencer drives.

A char point is one snax-forge catalogue block alone (char/blocks.py, rtl/char/<point>.zip, unpacked by sim/pwr.py),
synthesized by syn/syn.py --source char. It has no CSRs, no START and no done: a sequencer of sim/tb/ drives its data
and pins as its group's control unit would, through fixed windows, and every output is compared at every falling
edge. build() writes tb.json and schedule() gives the slots (both in their docstrings); docs/power.md, "Char",
has the testbench and the windows.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from . import hls
from . import ports as _ports

CLK, RST = _ports("char")    # clock, reset: syn/syn.py's SOURCES

TB_VERSION = 2
ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl" / "char"
SETTLE = 4          # slots with every input low after reset
CYCLES = 128        # each window's cycles (beats for serial's firing windows)
KINDS = {"SimdLanes": "lanes", "Mac": "fold", "TreeAccumulate": "fold", "SerialAccumulate": "serial",
         "LinkBuffer": "link", "FifoPacker": "pack", "FifoSlicer": "slice", "HaloLink": "halo"}
INS = {"SimdLanes": ["a", "b", "c"], "Mac": ["a", "b"], "TreeAccumulate": ["in"], "SerialAccumulate": ["in"],
       "LinkBuffer": ["in"], "FifoPacker": ["in_bits"], "FifoSlicer": ["in_bits"], "HaloLink": ["in"]}
OUTS = {"FifoPacker": ["out_bits", "out_valid", "in_ready"],
        "FifoSlicer": ["out_bits", "out_valid", "in_ready"], "HaloLink": ["taps"]}    # the others: out
PINS = {"lanes": [], "fold": ["fire", "first"], "bank": ["fire", "first", "row", "drain"], "serial": ["read", "lane", "first"], "link": ["load", "wslot", "rslot"],
        "halo": ["load"], "pack": ["in_valid", "out_ready", "clear", "last"], "slice": ["in_valid", "out_ready", "enable", "clear"]}
WINDOWS = {"lanes": ["busy", "idle"], "fold": ["busy", "idle"], "bank": ["busy", "idle"], "serial": ["busy", "idle"], "link": ["stream"],
           "halo": ["stream"], "pack": ["busy", "idle"], "slice": ["busy", "idle"]}
SEQ_FILES = {k: [f"char_{k}_seq.sv"] for k in PINS}
SCALARS = ("k", "k1", "k2", "k3")     # SimdLanes' scalar slots; one read from its CSR is an input pin io_<k> of opType's width
CORE = "char_seq_core.svh"


def point_dir(point: str, bundle: Path) -> Path:
    """The block, unpacked from rtl/char/<point>.zip by sim/pwr.py, with the files it needs."""
    for f in ("point.json", "emitted.json"):
        if not (bundle / f).is_file():
            raise FileNotFoundError(f"{point}: no {f} in {RTL / point}.zip (pixi run char-rtl)")
    return bundle


def held(params: dict) -> int:
    """A HaloLink's held beats, H = ceil((T - 1) / W) (snax-forge D206)."""
    return (params["taps"] + params["lanes"] - 2) // params["lanes"]


def rows(params: dict) -> int:
    """A Mac's rows of sums (its bank, snax-forge D191); 1 for every other block and a Mac without the param."""
    return params.get("rows", 1)


def kind_of(datapath: str, params: dict) -> str:
    """The testbench kind: KINDS', and bank for a Mac of 2 rows or more (pins row and drain)."""
    return "bank" if datapath == "Mac" and rows(params) > 1 else KINDS[datapath]


def pin_bits(datapath: str, params: dict) -> dict:
    """The kind's pins and their widths from the Chisel source; 0 bits = absent from the netlist."""
    w = params.get("lanes", 1)
    if kind_of(datapath, params) == "bank":
        rw = math.ceil(math.log2(rows(params)))
        return {"fire": 1, "first": 1, "row": rw, "drain": rw}
    if datapath == "SerialAccumulate":
        return {"read": 1, "lane": math.ceil(math.log2(w)) if w > 1 else 0, "first": 1}
    if datapath == "LinkBuffer":
        d = params["depth"]
        return {"load": 1, "wslot": math.ceil(math.log2(d)) if d > 1 else 0,
                "rslot": math.ceil(math.log2(d)) if d > 1 else 0}
    return {p: 1 for p in PINS[KINDS[datapath]]}


def scalar_bits(datapath: str, params: dict) -> dict:
    """{scalar: bits} of a SimdLanes' scalars read from their CSRs (params <k>Csr), each an input pin io_<k> of
    opType's width (snax-forge's SimdLanes.scala); {} for a baked or absent scalar and every other block."""
    if datapath != "SimdLanes":
        return {}
    return {n: width(params["opType"]) for n in SCALARS if params.get(f"{n}Csr")}


def width(dtype: str) -> int:
    """An int dtype's bits (int8, uint32)."""
    return int(dtype.removeprefix("u").removeprefix("int"))


def port_bits(datapath: str, params: dict) -> dict:
    """{port base: bits} of the data ports from the params, what the netlist must show (D175's types); a SimdLanes of
    one stream has a alone, of three (axpbypcz) a, b and c."""
    if datapath in ("SimdLanes", "Mac"):
        return {**dict(zip(INS[datapath], (width(t) for t in params["inTypes"]))), "out": width(params["outType"])}
    if datapath == "HaloLink":
        return {"in": width(params["dtype"]), "taps": width(params["dtype"])}
    if datapath in ("TreeAccumulate", "SerialAccumulate"):
        return {"in": width(params["inType"]), "out": width(params["outType"])}
    if datapath == "LinkBuffer":
        return {"in": width(params["dtype"]), "out": width(params["dtype"])}
    if datapath == "FifoSlicer":
        return {"in_bits": 64, "out_bits": width(params["laneType"]), "out_valid": 1, "in_ready": 1}
    return {"in_bits": width(params["laneType"]), "out_bits": 64, "out_valid": 1, "in_ready": 1}


def slicer_r(params: dict) -> int:
    """A FifoSlicer's pops per in-beat (d_in at one word in)."""
    return params["words"] * 64 // (width(params["laneType"]) * params["outLanes"])


def _base(p: str, bases: list[str]) -> tuple[int, tuple[int, ...]] | None:
    """(the base's index, its indices) of port io_<base>, io_<base>_<lane> or io_<base>_<tap>_<lane> (a HaloLink's
    taps, tap-major), None for another port."""
    for i, b in enumerate(bases):
        m = re.fullmatch(rf"io_{b}(?:_(\d+))?(?:_(\d+))?", p)
        if m:
            return i, tuple(int(g) for g in m.groups() if g is not None) or (0,)
    return None


def _order(ports: list[str], bases: list[str]) -> list[str]:
    return sorted(ports, key=lambda p: _base(p, bases))


def build(point: str, netlist: Path, bundle: Path) -> dict:
    """tb.json:
      tb_version, source "char", point, datapath, params, kind, top, W (lanes), depth, snax_forge_commit
      clock    {port: clock}
      reset    {port: reset, active: high, sync: false}
      control  {kind: "char_<kind>"}
      data_in  [{port, bits}]  every data input, one per lane, its width from the netlist (its type's), in the
                             catalogue's port order then lane order (SimdLanes and Mac: a_0 .. a_{W-1}, b_0 .., c_0 ..;
                             FifoPacker and FifoSlicer in_bits_0 ..; the others in_0 ..): rand64 draws one stream per
                             port in this order and keeps the port's low bits
      outs     [{port, bits}]  every output compared (out, or out_0 .. out_{W-1}; a HaloLink's taps_0_0 ..
                             taps_{T-1}_{W-1}, tap-major; FifoPacker and FifoSlicer
                             out_bits_0 .., out_valid, in_ready), its width from the netlist; a FifoSlicer's out_bits
                             compared through out_valid (0 when it holds no word: its data register has no reset)
      pins     {name: {port, bits}}  the kind's pins present in the netlist: a pin of no bits is absent (LinkBuffer's
                             wslot and rslot at depth 1, SerialAccumulate's lane at lanes 1)
      scalars  {name: {port, bits}}  only where a SimdLanes reads a scalar from its CSR (scalar_bits): io_k, io_k1,
                             io_k2, io_k3 at opType's width; sim/pwr.py holds one random value on each a window
      taps, held             a HaloLink's T and H (its fill is H loads)
      windows  [{name, cycles, fires}]  in the order the sequencer runs them (schedule())
      tb_files [sim/tb/ files]  the kind's sequencer and the shared core it includes

    The ports must be exactly clock, reset, data_in, outs, the present pins and the scalars (SimdLanes keeps an unused
    clock and reset), each data port as wide as its type (port_bits), W lanes of each input (a SimdLanes of one stream:
    a alone; of three: a, b and c), T x W taps of a HaloLink, each scalar pin as wide as opType. The kinds, by
    datapath: lanes (SimdLanes), fold (Mac in its accumulating form, TreeAccumulate), bank (an accumulating Mac of 2
    rows or more, tb.json's rows), serial (SerialAccumulate), link (LinkBuffer), halo (HaloLink), pack (FifoPacker),
    slice (FifoSlicer).

    """
    d = point_dir(point, bundle)
    pj = json.loads((d / "point.json").read_text())
    top = json.loads((d / "emitted.json").read_text())["top"]
    dp, params = pj["datapath"], pj["params"]
    if dp not in KINDS:
        raise ValueError(f"{point}: datapath {dp} has no testbench kind")
    if dp == "Mac" and not params.get("accumulate"):
        raise ValueError(f"{point}: only the accumulating Mac is built (fold kind)")
    kind = kind_of(dp, params)
    ports = hls.ports_of(netlist, top)
    bits = pin_bits(dp, params)
    pins = {n: {"port": f"io_{n}", "bits": b} for n, b in bits.items() if b}
    scalars = {n: {"port": f"io_{n}", "bits": b} for n, b in scalar_bits(dp, params).items()}
    out_bases = OUTS.get(dp, ["out"])
    data_in = [p for p, (dr, _) in ports.items() if dr == "in" and _base(p, INS[dp])]
    outs = [p for p, (dr, _) in ports.items() if dr == "out" and _base(p, out_bases)]
    known = {CLK, RST, *data_in, *outs, *(p["port"] for p in [*pins.values(), *scalars.values()])}
    if set(ports) != known:
        raise ValueError(f"{point}: netlist ports not as expected: missing {sorted(known - set(ports))}, "
                         f"not covered {sorted(set(ports) - known)}")
    want = port_bits(dp, params)
    bases = INS[dp] + out_bases
    for p in data_in + outs:
        b = want[bases[_base(p, bases)[0]]]
        if ports[p][1] != b:
            raise ValueError(f"{point}: {p} is {ports[p][1]} bits, its type's {b}")
    if dp in ("SimdLanes", "Mac"):
        lanes = {b: sum(1 for p in data_in if _base(p, INS[dp])[0] == i) for i, b in enumerate(INS[dp])}
        if lanes != {b: params["lanes"] if b in want else 0 for b in INS[dp]}:
            raise ValueError(f"{point}: data inputs {lanes} per port, {params['lanes']} lanes of {sorted(set(want) - {'out'})}")
    if dp == "HaloLink" and (len(data_in), len(outs)) != (params["lanes"], params["taps"] * params["lanes"]):
        raise ValueError(f"{point}: {len(data_in)} inputs and {len(outs)} taps, {params['lanes']} lanes and "
                         f"{params['taps']} x {params['lanes']} taps expected")
    for n, p in [*pins.items(), *scalars.items()]:
        if ports[p["port"]] != ("in", p["bits"]):
            raise ValueError(f"{point}: pin {p['port']} is {ports[p['port']]}, expected an input of {p['bits']} bits")
    for n, b in bits.items():
        if not b and f"io_{n}" in ports:
            raise ValueError(f"{point}: pin io_{n} should have no bits and be absent")
    tb = {"tb_version": TB_VERSION, "source": "char", "point": point, "datapath": dp, "params": params, "kind": kind,
          "top": top, "W": params.get("lanes", 1), "depth": params.get("depth", ""),
          **({"r": slicer_r(params)} if kind == "slice" else {}),
          **({"rows": rows(params)} if kind == "bank" else {}),
          **({"taps": params["taps"], "held": held(params)} if kind == "halo" else {}),
          "snax_forge_commit": pj["snax_forge_commit"],
          "clock": {"port": CLK}, "reset": {"port": RST, "active": "high", "sync": False},
          "control": {"kind": f"char_{kind}"},
          "data_in": [{"port": p, "bits": ports[p][1]} for p in _order(data_in, INS[dp])],
          "outs": [{"port": p, "bits": ports[p][1]} for p in _order(outs, out_bases)], "pins": pins,
          **({"scalars": scalars} if scalars else {}),
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
    """schedule(tb) is the sequence of slots the kind's sequencer drives after reset, slot by slot: 4 settle slots with
    every pin and data input low, then per window a lead-in of the window's own kind (outside every window) and the
    window's slots. The windows: lanes, fold, bank and serial have busy (a fire every cycle; serial a read every
    cycle, 128 beats of W) and idle (the enable at 0, every other input held), each after one lead-in slot (bank's
    busy: R lead-in slots, the restart of each row in turn, then row t mod R and drain the row before it, (t - 1) mod
    R, as the control unit drives them, first 0; idle: row and drain held at busy's last); pack has
    the start (clear, no push, outside every window), then busy (a push every cycle, out_ready high, clear and last
    low) and idle (no push, every other input held), each after one lead-in slot of its own kind; slice has the
    start (clear, enable low, no word offered, outside every window), then busy (enable high, the input valid, the
    output ready: a pop every cycle, a take every r = d_in cycles, a new word offered in the slot after each take,
    the lead-in's the first) and idle (enable low, the output not ready, the input valid, the word the lead-in
    offers held: no pop, no take), each after one lead-in slot of its own kind; a fire is a pop; link has
    stream only, a FIFO at full rate: a lead-in of D loads round the ring (the fill), then 128 cycles with a load of
    new data every cycle into slot t mod D and rslot the oldest slot, the same slot (read before the edge that
    overwrites it), so out at cycle t is the beat loaded at t - D; halo has stream only, the link at full rate: a
    lead-in of H loads (the fill: the held beats real data), then 128 cycles with a load of new data every cycle (each
    tap reads the held beats and the incoming one). A slot's inputs are applied at its rising edge (after the flops have taken the slot
    before, as the forge points' TBs and a block's neighbours inside an accelerator change them), the outputs are sampled
    at its falling edge, and the next rising edge takes it. A window's rising edges are its own slots' input changes
    and the captures of its lead-in and its own slots but the last, which falls on the next lead-in's edge: every
    window measures its own kind only. sim/tb/char_<kind>_seq.sv implements the same loops; the TB prints each
    window's cycles and fires and sim/pwr.py checks them against this.

    Every slot after reset: {window (None while settling), new (a new data beat), fire (the block works:
    new data for lanes, fire, read, load or push), pins {name: value}} (docs/power.md, Char).
    """
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
    elif kind == "bank":
        r = tb["rows"]
        for i in range(r):                                # the restart, each row in turn
            slot(None, 1, 1, fire=1, first=1, row=i, drain=(i - 1) % r)
        for i in range(CYCLES):
            slot("busy", 1, 1, fire=1, first=0, row=i % r, drain=(i - 1) % r)
        last = {"row": (CYCLES - 1) % r, "drain": (CYCLES - 2) % r}
        slot(None, 0, 0, fire=0, first=0, **last)
        for i in range(CYCLES):
            slot("idle", 0, 0, fire=0, first=0, **last)     # every input held
    elif kind == "serial":
        slot(None, 0, 1, read=1, lane=w - 1, first=0)     # a read of the held beat's last lane
        for b in range(CYCLES):
            for lane in range(w):
                slot("busy", lane == 0, 1, read=1, lane=lane, first=int(b == 0 and lane == 0))
        slot(None, 0, 0, read=0, lane=w - 1, first=0)
        for i in range(CYCLES):
            slot("idle", 0, 0, read=0, lane=w - 1, first=0)        # lane held at the last read's
    elif kind == "pack":
        slot(None, 0, 0, in_valid=0, out_ready=1, clear=1, last=0)     # the start: the slice pointer cleared
        slot(None, 1, 1, in_valid=1, out_ready=1, clear=0, last=0)     # lead-in: a push
        for i in range(CYCLES):
            slot("busy", 1, 1, in_valid=1, out_ready=1, clear=0, last=0)
        slot(None, 0, 0, in_valid=0, out_ready=1, clear=0, last=0)
        for i in range(CYCLES):
            slot("idle", 0, 0, in_valid=0, out_ready=1, clear=0, last=0)
    elif kind == "slice":
        r = tb["r"]
        slot(None, 0, 0, in_valid=0, out_ready=1, enable=0, clear=1)    # the start: the held word dropped
        slot(None, 1, 0, in_valid=1, out_ready=1, enable=1, clear=0)    # lead-in: word 0 offered and taken
        for i in range(CYCLES):                                         # pop i % r of a word, the take at r - 1
            slot("busy", i % r == 0, 1, in_valid=1, out_ready=1, enable=1, clear=0)
        slot(None, 1, 0, in_valid=1, out_ready=0, enable=0, clear=0)    # lead-in: the next word offered, held
        for i in range(CYCLES):
            slot("idle", 0, 0, in_valid=1, out_ready=0, enable=0, clear=0)
    elif kind == "link":
        for t in range(depth):                            # the lead-in: the fill, D loads round the ring
            slot(None, 1, 1, load=1, wslot=t, rslot=t)
        for t in range(CYCLES):                           # full rate at full occupancy: read the oldest, which is
            slot("stream", 1, 1, load=1, wslot=t % depth, rslot=t % depth)   # the slot this edge overwrites
    elif kind == "halo":
        for _ in range(tb["held"]):                       # the lead-in: the fill, H loads
            slot(None, 1, 1, load=1)
        for _ in range(CYCLES):
            slot("stream", 1, 1, load=1)
    else:
        raise ValueError(f"kind {kind}")
    return out
