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
