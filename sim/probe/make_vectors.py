#!/usr/bin/env python3
"""sim/probe/make_vectors.py: stimulus for the power probe on done/vecadd/opt_w8 (n512, W = 8).

Two stimuli, each written to sim/runs/probe/<stim>/ as $readmemh files, one beat per line:
  forge  IN_A, IN_B and EXP_C from hls-exercises' bench/tier_done/vecadd/vectors/n512/data.h
  full   full-range int64 from numpy.random.default_rng(0); C = A + B, wrapping in int64

Packing (bench/include/lanes.h): beat b holds elements b*W .. b*W+W-1, lane l in bits
[64l+63:64l], lane 0 in the low bits. Files: A.hex, B.hex, C.hex (expected), and
meta.txt (beats, loop_count).

Run from the repo root: pixi run python sim/probe/make_vectors.py
"""
import re
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA_H = REPO.parent / "hls-exercises/bench/tier_done/vecadd/vectors/n512/data.h"
OUT = REPO / "sim/runs/probe"
N, W = 512, 8
MASK = (1 << 64) - 1


def parse_data_h(path):
    text = path.read_text()
    arrays = {}
    for m in re.finditer(r"static const data_t (\w+)\[(\d+)\]\s*=\s*\{(.*?)\};", text, re.S):
        vals = [int(v) for v in m.group(3).replace("\n", " ").split(",") if v.strip()]
        assert len(vals) == int(m.group(2)), (m.group(1), len(vals))
        arrays[m.group(1)] = np.array(vals, dtype=np.int64)
    return arrays


def beats(x):
    """int64 elements -> one int per beat, lane 0 in the low bits."""
    out = []
    for b in range(len(x) // W):
        v = 0
        for l in range(W):
            v |= (int(x[b * W + l]) & MASK) << (64 * l)
        out.append(v)
    return out


def write(stim, a, b, c):
    assert len(a) == len(b) == len(c) == N
    with np.errstate(over="ignore"):
        assert np.array_equal(a + b, c), f"{stim}: C != A + B"
    d = OUT / stim
    d.mkdir(parents=True, exist_ok=True)
    for name, x in (("A", a), ("B", b), ("C", c)):
        (d / f"{name}.hex").write_text("".join(f"{v:0{W * 16}x}\n" for v in beats(x)))
    (d / "meta.txt").write_text(f"beats {N // W}\nloop_count {N // W}\nW {W}\nN {N}\n")
    print(f"{stim}: {N // W} beats of {W} lanes -> {d}")


def main():
    arr = parse_data_h(DATA_H)
    write("forge", arr["IN_A"], arr["IN_B"], arr["EXP_C"])
    rng = np.random.default_rng(0)
    info = np.iinfo(np.int64)
    a = rng.integers(info.min, info.max, size=N, dtype=np.int64, endpoint=True)
    b = rng.integers(info.min, info.max, size=N, dtype=np.int64, endpoint=True)
    with np.errstate(over="ignore"):
        c = a + b
    write("full", a, b, c)


if __name__ == "__main__":
    main()
