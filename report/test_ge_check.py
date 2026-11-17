"""report/ge_check.py on made-up data with known answers (no result files).

    pixi run python report/test_ge_check.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ge_check as gc  # noqa: E402

PARTS = gc.PARTS


def test_tau_counts_pairs():
    assert gc.tau([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert gc.tau([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0
    assert gc.tau([1, 2, 3], [1, 3, 2]) == (2 - 1) / 3
    assert gc.tau([1, 1, 2], [1, 2, 3]) == 2 / 3      # the tied pair is neither
    assert gc.tau([5], [7]) == 0.0


def made(w: int, net: float, static: float, ge: float) -> dict:
    def five(x: float) -> dict:
        return dict.fromkeys(PARTS, x / 5)
    return {"point": f"p{w}", "W": w, "netlist": five(net), "static": five(static), "ge": five(ge),
            "cycles": {"netlist": 10, "ge": 9}, "requests": {"static": 4, "ge": 5}, "busy": {"static": 2, "ge": 3},
            "xbar_rw": {"static": 1.0, "ge": 1.25}}


def test_taus_per_part_and_five():
    pts = [made(2, 50, 60, 60), made(4, 49, 59, 59), made(8, 70, 58, 72)]
    t = gc.taus(pts)
    assert t["five"]["ge"] == 1.0 and t["five"]["static"] == -1 / 3
    assert t["datapath"] == t["five"]


def test_one_run_window():
    ge = {"windows": [{"kind": "boot"}, {"kind": "run", "x": 1}, {"kind": "check"}]}
    assert gc.run_window(ge)["x"] == 1
    try:
        gc.run_window({"windows": [{"kind": "run"}, {"kind": "run"}]})
    except ValueError:
        return
    raise AssertionError("run_window accepted two run windows")


def test_point_data_maps_the_groups():
    energy = {"run": [{"cycles": 322, "groups": [{"group": g, "run_nj": float(i + 1)} for i, g in
                                                 enumerate(["a", "b", "c", "d", "e", "f"])]}]}
    groups = {"datapath": ["a", "f"], "control": ["b"], "streamers": ["c"], "crossbar": ["d"], "memory": ["e"]}
    hw = {"cost": {"parts": {k: {"energy": 1.0} for k in PARTS}, "xbar": {"e_access": 2.0}}}
    run = {"kind": "run", "cycles": 300,
           "energy": {"parts": dict.fromkeys(PARTS, 2.0), "counts": {"requests": 7, "cycles": 5}}}
    ge = {"windows": [run], "static": {"counts": {"requests": 6, "cycles": 4}}}
    d = gc.point_data({"point": "p", "W": 8}, energy, groups, hw, ge)
    assert d["netlist"]["datapath"] == 7.0 and d["netlist"]["memory"] == 5.0
    assert d["cycles"] == {"netlist": 322, "ge": 300} and d["requests"] == {"static": 6, "ge": 7}
    assert d["xbar_rw"] == {"static": 6 * 2.0 / 1000, "ge": 7 * 2.0 / 1000}


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
