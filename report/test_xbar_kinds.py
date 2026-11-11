"""report/xbar_kinds.py on made-up grids with known answers (no CSV, no DC).

    pixi run xbar-kinds-test
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xbar_kinds as xk  # noqa: E402

TRUE = {"c_rw": 160.0, "c_ro": 96.0, "c_wo": 94.0, "d": 25.0, "e": -20.0, "g": -200.0}


def grid(fn) -> list[dict]:
    rs = []
    for n in (16, 32, 64):
        for b in (16, 32, 64):
            for ro, wo in ((0, 0), (n, 0), (0, n)):
                rs.append({"point": f"i{n}_b{b}_r{ro}_w{wo}", "n": n, "b": b, "ro": ro, "wo": wo,
                           "area": fn(n, b, ro, wo)})
    rs.append({"point": "i36_b32_r32_w1", "n": 36, "b": 32, "ro": 32, "wo": 1, "area": fn(36, 32, 32, 1)})
    return rs


def exact(n, b, ro, wo):
    return xk.predict_crosspoint(TRUE, n, b, ro, wo)


def test_crosspoint_recovers_the_coefficients():
    cp = xk.crosspoint(grid(exact), {"i36_b32_r32_w1"})
    assert all(abs(cp[k] - TRUE[k]) < 1e-6 for k in xk.COEF), cp
    assert cp["points"] == 27 and cp["max_residual_pct"] < 1e-9


def test_factor_on_a_pure_crosspoint_grid():
    pure = {**TRUE, "d": 0.0, "e": 0.0, "g": 0.0}
    f = xk.factor(grid(lambda n, b, ro, wo: xk.predict_crosspoint(pure, n, b, ro, wo)))
    assert abs(f["f_ro"] - (1 - 96 / 160)) < 1e-12 and abs(f["f_wo"] - (1 - 94 / 160)) < 1e-12
    assert f["f_ro_range"][0] == f["f_ro_range"][1] and len(f["pairs"]) == 9


def test_factor_formula():
    f = {"f_ro": 0.4, "f_wo": 0.5}
    assert xk.predict_factor(f, 1000.0, 10, 5, 2) == 1000.0 * (1 - 0.4 * 0.5 - 0.5 * 0.2)
    assert xk.predict_factor(f, 1000.0, 10, 0, 0) == 1000.0


def test_factor_needs_a_full_pair():
    rs = [r for r in grid(exact) if not (r["ro"] and not r["wo"])]    # no all read-only point
    try:
        xk.factor(rs)
    except ValueError:
        return
    raise AssertionError("factor accepted a grid with no all read-only point")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
