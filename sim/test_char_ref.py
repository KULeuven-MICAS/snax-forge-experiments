"""sim/test_char_ref.py - SimdLanes' scalar forms (X99) in sim/ref.py, sim/sources/char.py and sim/pwr.py's char
stimulus, without Questa or snax-forge.

    pixi run python sim/test_char_ref.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "sim")]
import pwr  # noqa: E402
from ref import char_ref  # noqa: E402
from sources import char as cs  # noqa: E402

M31 = 2**31


def bits(x: int, w: int) -> int:
    return x & ((1 << w) - 1)


def lanes(ins: list[str], t: str, op: str, **scal) -> dict:
    p = {"inTypes": ins, "opType": t, "outType": t, "lanes": 1, "op": op, "streams": len(ins),
         "k": None, "k1": None, "k2": None, "kCsr": False, "k1Csr": False, "k2Csr": False}
    return {**p, **scal}


def one(params: dict, beat: list[int], pins: dict) -> int:
    slot = {"window": "busy", "new": True, "fire": True, "pins": pins}
    return char_ref("SimdLanes", params, [slot], [beat])[0][0]


def test_scalar_forms_wrap() -> None:
    """The run note's spot checks: each op at values that wrap."""
    both = lanes(["int32"] * 2, "int32", "axpby", k1Csr=True, k2Csr=True)
    k = {"k1": bits(-3, 32), "k2": M31 - 1}
    assert one(both, [5, 7], k) == M31 - 22                         # -15 + 7 (2^31 - 1) = 7 2^31 - 22
    assert one(both, [bits(-M31, 32), bits(-1, 32)], k) == 1        # 3 2^31 - 2^31 + 1
    scale = lanes(["int8"], "int32", "mul", kCsr=True)
    assert one(scale, [bits(-128, 8)], {"k": bits(-M31, 32)}) == 0              # 2^38 wraps to 0
    assert one(scale, [bits(-1, 8)], {"k": bits(-M31, 32)}) == M31              # -2^31
    assert one(scale, [bits(-128, 8)], {"k": 3}) == bits(-384, 32)              # a sign-extended into op
    i64 = lanes(["int64"], "int64", "mul", kCsr=True)
    assert one(i64, [bits(-2**63, 64)], {"k": bits(-1, 64)}) == 2**63
    k1 = lanes(["int32"] * 2, "int32", "axpby", k1Csr=True)        # k1 a + b
    assert one(k1, [2**30, 1], {"k1": bits(-3, 32)}) == 2**30 + 1
    baked = lanes(["int32"] * 2, "int32", "axpby", k1=3)
    assert one(baked, [M31 - 1, 0], {}) == M31 - 3
    assert one(baked, [bits(-1, 32), bits(-1, 32)], {}) == bits(-4, 32)
    relu = lanes(["int32"], "int32", "max", k=0)                   # signed compare
    assert [one(relu, [bits(x, 32)], {}) for x in (-5, 7, -M31, M31 - 1)] == [0, 7, 0, M31 - 1]


def test_scalar_held_from_the_pins() -> None:
    """A pin scalar is the slot's own pins value: two windows, two values."""
    p = lanes(["int32"], "int32", "mul", kCsr=True)
    slots = [{"window": "busy", "new": True, "fire": True, "pins": {"k": 2}},
             {"window": "idle", "new": False, "fire": False, "pins": {"k": 5}}]
    assert char_ref("SimdLanes", p, slots, [[3]]) == [[6], [15]]


def test_ports_of_one_stream() -> None:
    p = lanes(["int8"], "int32", "mul", kCsr=True)
    assert cs.port_bits("SimdLanes", p) == {"a": 8, "out": 32}
    assert cs.scalar_bits("SimdLanes", p) == {"k": 32}
    two = lanes(["int64"] * 2, "int64", "axpby", k1Csr=True, k2Csr=True)
    assert cs.port_bits("SimdLanes", two) == {"a": 64, "b": 64, "out": 64}
    assert cs.scalar_bits("SimdLanes", two) == {"k1": 64, "k2": 64}
    assert cs.scalar_bits("SimdLanes", lanes(["int32"] * 2, "int32", "axpby", k1=3)) == {}


def _tb(params: dict, data_in: int, scalars: dict) -> dict:
    tb = {"kind": "lanes", "W": 1, "depth": "", "datapath": "SimdLanes", "params": params,
          "data_in": [{"port": f"io_{'ab'[i]}_0", "bits": 32} for i in range(data_in)],
          "outs": [{"port": "io_out_0", "bits": 32}],
          **({"scalars": {n: {"port": f"io_{n}", "bits": b} for n, b in scalars.items()}} if scalars else {})}
    tb["windows"] = [{"name": "busy"}, {"name": "idle"}]
    return tb


def test_stimulus_scalars_per_window() -> None:
    """The data as without scalars; one value a pin a window, held from the window's lead-in; the reference sees it."""
    plain = _tb(lanes(["int32"] * 2, "int32", "add"), 2, {})
    form = _tb(lanes(["int32"] * 2, "int32", "axpby", k1Csr=True, k2Csr=True), 2, {"k1": 32, "k2": 32})
    slots = cs.schedule(plain)
    a, b = pwr.char_stimulus(plain, slots, 0), pwr.char_stimulus(form, slots, 0)
    assert a["beats"] == b["beats"] and a["ks"] == {}
    assert list(b["ks"]) == ["busy", "idle"] and all(set(v) == {"k1", "k2"} for v in b["ks"].values())
    assert b["ks"]["busy"] != b["ks"]["idle"]
    first = {w: next(i for i, s in enumerate(slots) if s["window"] == w) for w in ("busy", "idle")}
    for w, i in first.items():                 # the lead-in slot before each window applies its values
        k = b["ks"][w]
        cur = b["beats"][sum(1 for s in slots[:i] if s["new"]) - 1]
        assert b["exps"][i - 1] == [bits(k["k1"] * cur[0] + k["k2"] * cur[1], 32)]
    assert all(x == [0] for x in b["exps"][:cs.SETTLE])          # settling: data and scalars 0


def e2e1(ins: list[str], t: str, out: str, op: str, **slots) -> dict:
    """An X111 form's params: every slot written out, as char/points.json has them."""
    return {**lanes(ins, t, op), "outType": out, "k3": None, "d": None, "lo": None, "hi": None, "k3Csr": False,
            **slots}


def test_e2e1_forms_by_hand() -> None:
    """The run note's spot checks (X111): requant's floor and clamp, gray's and blur's sums and slices, threshold's
    wrap at int16."""
    rq = e2e1(["int32"], "int32", "int8", "requant", d=1024, lo=0, hi=127)
    got = [one(rq, [bits(a, 32)], {}) for a in (127 * 1024, 128 * 1024, -1, 1023, M31 - 1, -M31, 5120)]
    assert got == [127, 127, 0, 0, 127, 0, 5]
    assert one({**rq, "d": 512}, [65023], {}) == 126                  # 126.99 floors to 126
    assert one({**rq, "lo": -5, "outType": "int32"}, [bits(-6000, 32)], {}) == bits(-5, 32)   # -5.86 floors to -6
    gray = e2e1(["uint8"] * 3, "uint16", "uint8", "axpbypcz", k1=77, k2=150, k3=29, d=256)
    got = [one(gray, abc, {}) for abc in ([255, 255, 255], [255, 0, 0], [0, 255, 0], [0, 0, 255], [0, 0, 0])]
    assert got == [255, 76, 149, 28, 0]                               # 65280, 19635, 38250, 7395 >> 8
    blur = e2e1(["uint8"] * 3, "uint16", "uint8", "axpbypcz", k2=2, d=4)
    assert [one(blur, abc, {}) for abc in ([255, 255, 255], [1, 2, 3], [3, 0, 0])] == [255, 2, 0]
    th = e2e1(["uint8"], "int16", "uint8", "threshold", kCsr=True, hi=255)
    k = lambda v: {"k": bits(v, 16)}                                  # noqa: E731
    assert [one(th, [a], k(128)) for a in (127, 128, 255, 0)] == [0, 255, 255, 0]
    assert [one(th, [a], k(-1)) for a in (0, 255)] == [255, 255]      # a + 2
    assert [one(th, [a], k(-32768)) for a in (0, 255)] == [0, 0]      # a + 32769 wraps negative
    assert one(th, [0], k(-32767)) == 0                               # 32768 wraps to -32768
    assert one(th, [0], k(0)) == 255


def test_three_streams_ports() -> None:
    gray = e2e1(["uint8"] * 3, "uint16", "uint8", "axpbypcz", k1=77, k2=150, k3=29, d=256, lanes=8)
    assert cs.port_bits("SimdLanes", gray) == {"a": 8, "b": 8, "c": 8, "out": 8}
    assert cs.scalar_bits("SimdLanes", gray) == {}
    th = e2e1(["uint8"], "int16", "uint8", "threshold", kCsr=True, hi=255)
    assert cs.port_bits("SimdLanes", th) == {"a": 8, "out": 8} and cs.scalar_bits("SimdLanes", th) == {"k": 16}
    w = 2       # the reference reads c from the third W of a beat
    beat = [1, 2, 10, 20, 100, 200]
    slot = {"window": "busy", "new": True, "fire": True, "pins": {}}
    assert char_ref("SimdLanes", {**gray, "lanes": w, "k1": 1, "k2": 1, "k3": 1, "d": 1}, [slot], [beat]) == [[111, 222]]


def halo(t: int, w: int) -> dict:
    return {"taps": t, "lanes": w, "dtype": "int8"}


def test_halo_taps() -> None:
    """Tap t lane l is e[l + t], e the held beats oldest first, then the input; a load shifts them (D206)."""
    ld = lambda: {"window": "stream", "new": True, "fire": True, "pins": {"load": 1}}  # noqa: E731
    assert char_ref("HaloLink", halo(3, 1), [ld() for _ in range(4)], [[10], [20], [30], [40]]) == \
        [[0, 0, 10], [0, 10, 20], [10, 20, 30], [20, 30, 40]]
    hold = {"window": "stream", "new": True, "fire": False, "pins": {"load": 0}}
    assert char_ref("HaloLink", halo(3, 2), [ld(), hold], [[1, 2], [3, 4]]) == \
        [[0, 0, 0, 1, 1, 2], [1, 2, 2, 3, 3, 4]]                     # H = 1: taps [h0 h1], [h1 i0], [i0 i1]
    assert cs.held(halo(3, 1)) == 2 and cs.held(halo(3, 8)) == 1 and cs.held(halo(9, 8)) == 1 and cs.held(halo(10, 8)) == 2


def test_halo_schedule() -> None:
    """The fill is H loads outside the window, then 128 loads in stream."""
    tb = {"kind": "halo", "W": 1, "depth": "", "held": 2}
    slots = cs.schedule(tb)
    assert [s["window"] for s in slots[cs.SETTLE:cs.SETTLE + 3]] == [None, None, "stream"]
    assert sum(1 for s in slots if s["window"] == "stream" and s["fire"] and s["pins"]["load"]) == cs.CYCLES
    assert len(slots) == cs.SETTLE + 2 + cs.CYCLES


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
