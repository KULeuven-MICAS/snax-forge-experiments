"""report/xbar_kinds.py on made-up grids with known answers (no CSV, no DC).

    pixi run python report/test_xbar_kinds.py
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


def egrid(g_ro: dict, g_wo: dict) -> list[dict]:
    """Made-up powered points: e_rw = b / 10 pJ, the kinds at 1 - g of it, on every pair with n <= b."""
    rs = []
    for n in (16, 32, 64):
        for b in (16, 32, 64):
            if n > b:
                continue
            e = b / 10
            for ro, wo, f in ((0, 0, 1.0), (n, 0, 1 - g_ro[b]), (0, n, 1 - g_wo[b])):
                rs.append({"point": f"i{n}_b{b}_r{ro}_w{wo}", "n": n, "b": b, "ro": ro, "wo": wo, "e": e * f})
    return rs


def test_energy_factor_by_bank_count():
    g_ro, g_wo = {16: 0.4, 32: 0.3, 64: 0.2}, {16: 0.5, 32: 0.45, 64: 0.25}
    ef = xk.energy_factor(egrid(g_ro, g_wo))
    assert sorted(ef["by_banks"]) == [16, 32, 64] and len(ef["pairs"]) == 6
    for b in (16, 32, 64):
        p = ef["by_banks"][b]
        assert p["inputs"] == b and abs(p["g_ro"] - g_ro[b]) < 1e-12 and abs(p["g_wo"] - g_wo[b]) < 1e-12


def test_energy_factor_between_and_beyond_bank_counts():
    ef = xk.energy_factor(egrid({16: 0.4, 32: 0.3, 64: 0.2}, {16: 0.5, 32: 0.45, 64: 0.25}))
    ro, wo = xk.g_at(ef, 48)
    assert abs(ro - 0.25) < 1e-12 and abs(wo - 0.35) < 1e-12
    assert xk.g_at(ef, 8) == xk.g_at(ef, 16) and xk.g_at(ef, 128) == xk.g_at(ef, 64)


def test_energy_factor_needs_a_full_diagonal_point():
    rs = [r for r in egrid({16: 0.4, 32: 0.3, 64: 0.2}, {16: 0.5, 32: 0.45, 64: 0.25})
          if not (r["n"] == r["b"] and r["wo"])]
    try:
        xk.energy_factor(rs)
    except ValueError:
        return
    raise AssertionError("energy_factor accepted a grid with no all write-only point at inputs = banks")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
