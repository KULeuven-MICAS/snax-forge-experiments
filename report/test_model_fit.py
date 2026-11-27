#!/usr/bin/env python3
"""report/model_fit.py: the floor, e_l2 and the refusal fractions from the committed dot3 and mvt_v4 runs.

    pixi run python report/test_model_fit.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import model_fit as mf  # noqa: E402

REP = mf.report("nangate45")


def test_floor_fits_calibration():
    fl = REP["floor"]
    for pt, p in fl["points"].items():
        f = mf.floor_pj(fl, p["shape"])
        for q in ("streamers", "crossbar", "dma"):
            assert abs(f[q] / p["pj_cycle"][q] - 1) < 0.15, (pt, q, f[q], p["pj_cycle"][q])
    assert 3.2 < fl["dma"]["pj"] < 3.5, fl["dma"]


def test_floor_held_out():
    for pt, v in REP["check"]["floor"].items():
        for q in ("streamers", "crossbar", "dma"):
            assert abs(v[q]["fitted"] / v[q]["measured"] - 1) < 0.25, (pt, q, v[q])


def test_l2():
    l2 = REP["l2"]
    assert 50 < l2["e_l2_pj"] < 60, l2["e_l2_pj"]
    assert all(abs(p["pj"] / l2["e_l2_pj"] - 1) < 0.01 for p in l2["points"].values())
    assert all(abs(v["pj"] / l2["e_l2_pj"] - 1) < 0.12 for v in REP["check"]["l2"].values())


def test_refusal():
    r = REP["refusal"]
    assert r["fit"]["grants"][0] == r["fit"]["grants"][1]
    assert r["fit"]["d_refusals"] > 20000, r["fit"]["d_refusals"]
    assert 0 < r["r_strm"] < 0.2, r["r_strm"]
    assert r["r_xbar"] == 0.0 and r["fit"]["parts"]["crossbar"]["raw"] < 0
    chk = r["check"]["parts"]
    total_nl = sum(v["d_netlist_nj"] for v in chk.values())
    total_model = sum(v["model_nj"] for v in chk.values())
    assert abs(total_nl - total_model) < 1.0, (total_nl, total_model)


def test_copy_has_no_crossbar_access():
    for pt, v in REP["check"]["copy_crossbar"].items():
        assert abs(v["above_floor_pj_burst"]) < v["d184_pj_burst"] / 2, (pt, v)


def test_ge_order():
    """The runs as priced before the terms: CSYN2's tier A, GE1's dot3, else ge/ itself; a missing point fails."""
    import json  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    assert mf.GE_ORDER == ("csyn2", "ge1", "")
    assert mf.ge_path("nangate45", "mvt_column_cg").parent.name == "csyn2"
    assert mf.ge_path("nangate45", "dot3_w8_cg").parent.name == "ge1"
    with tempfile.TemporaryDirectory() as d:
        old, mf.ROOT = mf.ROOT, Path(d)
        try:
            ge = Path(d) / "results" / "cluster" / "nangate45" / "ge"
            for sub in ("", "ge1", "csyn2"):
                (ge / sub).mkdir(parents=True, exist_ok=True)
                (ge / sub / "p.json").write_text(json.dumps({"from": sub}))
                assert mf._ge("nangate45", "p") == {"from": sub}   # each folder added wins over the ones before
            try:
                mf.ge_path("nangate45", "q")
                raise AssertionError("no error for a missing point")
            except FileNotFoundError as e:
                assert "csyn2/" in str(e) and "ge1/" in str(e), e
        finally:
            mf.ROOT = old


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_model_fit.py: all passed")
