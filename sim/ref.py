"""sim/ref.py - numpy references per kernel, int64 with wrap-around (as the C++ int64 kernels).

ref(kernel, ins, pins) -> {output arg: int64 array}
  ins   {input stream arg: int64 array, flat, lane 0 first}
  pins  {pin: int}: the config pins (loop_count, len) and the data pins (axpy's alpha)
"""
from __future__ import annotations

import numpy as np


def _rows(a, pins):
    m = pins["loop_count"] // pins["len"]          # rows
    return a.reshape(m, a.size // m)


REF = {
    "vecadd": lambda i, p: {"C": i["A"] + i["B"]},
    "matadd": lambda i, p: {"C": i["A"] + i["B"]},
    "vecmul": lambda i, p: {"C": i["A"] * i["B"]},
    "vsum":   lambda i, p: {"out": np.array([i["A"].sum(dtype=np.int64)], dtype=np.int64)},
    "dot":    lambda i, p: {"out": np.array([(i["A"] * i["B"]).sum(dtype=np.int64)], dtype=np.int64)},
    "relu":   lambda i, p: {"B": np.maximum(i["A"], 0)},
    "rowsum": lambda i, p: {"y": _rows(i["A"], p).sum(axis=1, dtype=np.int64)},
    "axpy":   lambda i, p: {"y_out": np.int64(p["alpha"]) * i["x"] + i["y"]},
}


def ref(kernel: str, ins: dict, pins: dict) -> dict:
    if kernel not in REF:
        raise KeyError(f"sim/ref.py has no reference for {kernel}")
    with np.errstate(over="ignore"):
        out = REF[kernel]({k: np.asarray(v, dtype=np.int64) for k, v in ins.items()}, pins)
    return {k: np.asarray(v, dtype=np.int64) for k, v in out.items()}


# ---------------------------------------------------------------- CHAR1: the blocks alone, cycle by cycle
# snax-forge's datapaths (hw/chisel/src/main/scala/snax/forge/datapath/, at the commit of the point) at int64,
# wrapping at 64 bits, stepped one slot at a time as sim/sources/char.py's schedule() drives them. A slot's
# inputs are applied at its rising edge, the TB samples the outputs at its falling edge (the registers still hold
# what the slots before left, the combinational outputs see the slot's inputs), and the next rising edge takes it.
#   ElementwiseLanes  out_l = a_l op b_l (combinational: the slot's own inputs)
#   Mac (accumulate)  on fire: s_l <- first ? a_l b_l : s_l + a_l b_l; out_l = s_l
#   TreeAccumulate    on fire: acc <- first ? sum_l in_l : acc + sum_l in_l; out = acc
#   SerialAccumulate  on read: acc <- (first and lane = 0 ? 0 : acc) + in_lane (in_0 at lanes 1); out = acc
#   LinkBuffer        on load: slot[wslot] <- in; out = slot[rslot] (combinational read; slot 0 at depth 1)
# Every register starts at 0 (RegInit), as after the TB's reset.
M64 = (1 << 64) - 1
CHAR_OPS = {"add": lambda a, b: (a + b) & M64, "mul": lambda a, b: (a * b) & M64}


def char_ref(datapath: str, params: dict, slots: list[dict], beats: list[list[int]]) -> list[list[int]]:
    """The expected outputs (one list of lane values, unsigned 64-bit) at every slot's falling edge. `beats` are
    the new data beats in the order the slots take them, each a list of the data inputs' values in tb.json's
    data_in order; a slot without new data holds the last beat (0 before any)."""
    w = params.get("lanes", 1)
    cur, nb = [0] * (2 * w if datapath in ("ElementwiseLanes", "Mac") else w), 0
    if datapath == "ElementwiseLanes":
        op = CHAR_OPS[params["op"]]
    elif datapath == "Mac":
        s = [0] * w
    elif datapath in ("TreeAccumulate", "SerialAccumulate"):
        acc = 0
    elif datapath == "LinkBuffer":
        depth = params["depth"]
        mem = [[0] * w for _ in range(depth)]
    else:
        raise KeyError(f"sim/ref.py has no char reference for {datapath}")
    out = []
    for sl in slots:
        if sl["new"]:
            cur = [v & M64 for v in beats[nb]]
            nb += 1
        p = sl["pins"]
        # the falling edge: what the registers hold, the combinational outputs of this slot's inputs
        if datapath == "ElementwiseLanes":
            out.append([op(cur[i], cur[w + i]) for i in range(w)])
        elif datapath == "Mac":
            out.append(list(s))
        elif datapath in ("TreeAccumulate", "SerialAccumulate"):
            out.append([acc])
        else:
            out.append(list(mem[p["rslot"] if depth > 1 else 0]))
        # the next rising edge takes the slot
        if datapath == "Mac" and p["fire"]:
            prod = [(cur[i] * cur[w + i]) & M64 for i in range(w)]
            s = prod if p["first"] else [(s[i] + prod[i]) & M64 for i in range(w)]
        elif datapath == "TreeAccumulate" and p["fire"]:
            beat = sum(cur) & M64
            acc = beat if p["first"] else (acc + beat) & M64
        elif datapath == "SerialAccumulate" and p["read"]:
            lane = p["lane"] if w > 1 else 0
            acc = ((0 if p["first"] and lane == 0 else acc) + cur[lane]) & M64
        elif datapath == "LinkBuffer" and p["load"]:
            mem[p["wslot"] if depth > 1 else 0] = list(cur)
    if nb != len(beats):
        raise ValueError(f"char_ref: {len(beats)} beats given, the slots take {nb}")
    return out
