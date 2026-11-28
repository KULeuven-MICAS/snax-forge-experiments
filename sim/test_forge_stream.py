"""sim/test_forge_stream.py - forge streams of narrow elements in sim/pwr.py, without Questa or snax-forge.

    pixi run python sim/test_forge_stream.py
"""

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "sim")]
import pwr  # noqa: E402


def _tb(dtype_in: str, slc_in: int, ch_in: int, beats: int) -> dict:
    n = beats * ch_in * slc_in
    return {"kernel": "vsum", "scalars": [], "baked": {},
            "sizes": {"n2048": {"shape": {"N": n}}},
            "streams": [{"arg": "A", "name": "A", "dir": "in", "dtype": dtype_in, "lanes": ch_in, "num_ch": ch_in,
                         "num_slc": slc_in, "d_out": 1, "elems": ch_in * slc_in, "beats": beats, "shape": [n],
                         "order": None},
                        {"arg": "out", "name": "out", "dir": "out", "dtype": "int32", "lanes": 1, "num_ch": 1,
                         "num_slc": 2, "d_out": 2, "elems": 2, "beats": 1, "shape": [1], "order": [0, -1]}]}


def test_words_little_endian() -> None:
    x = np.array([1, -1, 2, -2], dtype=np.int64)
    w = pwr.words(x, 2)                      # int32 slices: element 0 in the low half
    assert [int(v) & pwr.MASK64 for v in w] == [0xFFFFFFFF_00000001, 0xFFFFFFFE_00000002]
    w = pwr.words(np.arange(8, dtype=np.int64) - 4, 8)
    assert int(w[0]) & pwr.MASK64 == 0x03020100_FFFEFDFC
    assert pwr.words(x, 1) is x


def test_narrow_stimulus_packs_and_wraps() -> None:
    tb = _tb("int16", 4, 2, 256)            # vsum at W = 8, int16 in: two channels of four slices
    st = pwr.stimulus_forge(tb, "n2048", 0)
    a = st["ins"]["A"]
    assert a.min() >= -(1 << 15) and a.max() < (1 << 15) and a.min() < -(1 << 14)   # full range, int16
    assert len(st["data"]["A"]) == 256 * 2 and not st["untoggled"]
    assert np.array_equal(pwr.words(a, 4), st["data"]["A"])
    total = int(a.sum())
    assert st["outs"]["out"].tolist() == [np.int64(total).astype(np.int32)]
    word = int(st["data"]["out"][0]) & pwr.MASK64
    assert word == total & 0xFFFFFFFF, hex(word)     # the packed word's upper slice is 0 (snax-forge D174)


def test_int64_stream_unchanged() -> None:
    tb = _tb("int64", 1, 8, 256)
    tb["streams"][1].update({"dtype": "int64", "num_slc": 1, "d_out": 1, "elems": 1, "order": None})
    st = pwr.stimulus_forge(tb, "n2048", 0)
    info = np.iinfo(np.int64)
    want = np.random.default_rng(0).integers(info.min, info.max, size=2048, dtype=np.int64, endpoint=True)
    assert np.array_equal(st["data"]["A"], want)


def _seg(job: int, d: str, c: str, order: list, end: str = "u.a") -> dict:
    return {"job": job, "dir": d, "container": c, "order": order, "shape": [len(order)], "end": end}


def _prog(streams: list, starts: int, dmas: tuple = ()) -> dict:
    ops = [{"op": "start", "job": j} for j in range(starts)]
    for k, d in dmas:                   # a copy between the starts, at op k
        ops.insert(k, {"op": "dma", "task": d["task"]})
    return {"ops": ops, "streams": streams, "dmas": list(d for _, d in dmas)}


def test_sources_initial_final_and_refused() -> None:
    src = pwr.forge_src
    # job 0 reads A and writes t; job 1 reads t (final) and x in place (initial), writes x (final)
    p = _prog([_seg(0, "in", "A", [0, 1]), _seg(0, "out", "t", [0, 1]), _seg(1, "in", "t", [0, 1]),
               _seg(1, "in", "x", [0, 1]), _seg(1, "out", "x", [0, 1])], 2)
    assert [v["value"] for v in src.sources(p)] == ["initial", "final", "final", "initial", "final"]
    # a copy (atax_v1_2's transpose) between the jobs: its destination reads final
    copy = {"task": "transpose_A_T", "direction": "l1_to_l1", "dst": {"container": "A_T"}}
    p = _prog([_seg(0, "in", "A", [0, 1]), _seg(1, "in", "A_T", [0, 1])], 2, ((1, copy),))
    assert [v["value"] for v in src.sources(p)] == ["initial", "final"]
    # t written by job 0, read by job 1, written again by job 2: job 1 reads a value between two writes
    p = _prog([_seg(0, "out", "t", [0]), _seg(1, "in", "t", [0]), _seg(2, "out", "t", [0])], 3)
    try:
        src.sources(p)
    except ValueError as e:
        assert "between two writes" in str(e) or "again after it" in str(e), e
    else:
        raise AssertionError("a read between two writes was not refused")


def test_program_cycles_serial_and_parallel() -> None:
    jobs = [{"task": "a", "cycles": 514}, {"task": "b", "cycles": 514}, {"task": "c", "cycles": 8}]
    serial = {"jobs": jobs, "ops": [{"op": "start", "job": 0, "group": 0}, {"op": "wait", "group": 0},
                                    {"op": "start", "job": 1, "group": 0}, {"op": "wait", "group": 0},
                                    {"op": "start", "job": 2, "group": 1}, {"op": "wait", "group": 1}]}
    assert pwr.forge_src.program_cycles(serial)[0] == 1036          # gesummv_v2_1_1's
    both = {"jobs": jobs[:2], "ops": [{"op": "start", "job": 0, "group": 0}, {"op": "start", "job": 1, "group": 1},
                                      {"op": "wait", "group": 0}, {"op": "wait", "group": 1}]}
    assert pwr.forge_src.program_cycles(both)[0] == 514


def test_ports_of_ansi_header(tmp: Path = ROOT / "tmp") -> None:
    tmp.mkdir(exist_ok=True)
    f = tmp / "test_ports_of_ansi.sv"
    f.write_text("module w(\n  input          clk_i,\n                 rst_ni,\n  output [255:0] d_o,\n"
                 "  input  wire [7:0] _y2_TDATA\n);\nendmodule\n")
    try:
        got = pwr.hls.ports_of(f, "w")
    finally:
        f.unlink()
    assert got == {"clk_i": ("in", 1), "rst_ni": ("in", 1), "d_o": ("out", 256), "_y2_TDATA": ("in", 8)}, got


def test_follow_index_and_distinct_lanes() -> None:
    s = {"lanes": 8, "follows": {"array": "y1", "beats": "m * n // W", "index": "(b % (n // W)) * W + l"}}
    beats, idx = pwr.hls.follow(s, {"m": 4, "n": 16}, 8)        # mvt's y1, again for every row
    assert beats == 8 and idx[:2].ravel().tolist() == list(range(16)) and idx[2].tolist() == list(range(8))
    assert pwr.distinct_per_lane(idx) == 2
    assert pwr.distinct_per_lane(np.arange(64 * 8).reshape(64, 8)) == 64


def test_array_of_in_place_output() -> None:
    dts = {"x": "int8", "y": "int32", "alpha": "int32"}
    assert pwr.hls.array_of("y_out", dts) == "y" and pwr.hls.array_of("y", dts) == "y"
    assert pwr.hls.stream_dtype({"streams": {}}, "in", "y", {"kernel": "axpy", "types": "i8", "dtypes": dts}) == "int32"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
