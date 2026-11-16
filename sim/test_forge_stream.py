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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
