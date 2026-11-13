"""report/cluster_sweep.py on made-up energy.json and breakdown.json entries (no PT, no DC, no snax-forge).

    pixi run cluster-sweep-test
"""

import csv
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import cluster_sweep as cs  # noqa: E402

PARTS = cs.PARTS


def entries(w: int) -> tuple[dict, dict, dict]:
    """A point at width w: run-window parts 1..5 nJ times w, a run window of 100 nJ; area parts 10..50 um2."""
    run_nj = {k: (i + 1) * w for i, k in enumerate(PARTS)}
    hw_nj = {k: (i + 1) * 2.0 for i, k in enumerate(PARTS)}
    area = {k: (i + 1) * 10.0 for i, k in enumerate(PARTS)}
    p = {"point": f"x_w{w}", "recipe": "r", "W": w, "alone": f"done/x_w{w}"}
    e = {"windows": [{"name": "4_acc_config", "cycles": 5, "nj": 1.0, "groups": {"g": 200.0}},
                     {"name": "5_run", "cycles": 50, "nj": 100.0, "groups": {"g": 1500.0, "h": 500.0}}],
         "span": {"cycles": 60, "nj": 120.0},
         "run": [{"window": "5_run"}],
         "hwcost": {"snax_forge_commit": "abc", "parts": [{"part": k, "hwcost_nj": hw_nj[k], "run_nj": run_nj[k]} for k in PARTS]},
         "alone": {"point": p["alone"], "cluster": {"cycles": 50, "pj_cycle": 20.0, "nj": 1.0},
                   "alone": {"cycles": 40, "pj_cycle": 50.0, "nj": 2.0}},
         "snax_forge_commit": "abc"}
    b = {"total_um2": 200.0, "groups": [{"name": "g", "area_um2": 150.0}, {"name": "h", "area_um2": 50.0}],
         "hwcost": {"parts": [{"part": k, "hwcost_um2": area[k] * 2, "cluster_um2": area[k]} for k in PARTS]},
         "alone": {"rows": [{"name": "total", "cluster_um2": 7.0, "alone_um2": 8.0}]}}
    return p, e, b


def test_point_data() -> None:
    p, e, b = entries(2)
    d = cs.point_data(p, {p["point"]: e}, {p["point"]: b})
    assert d["gls_e"]["memory"] == 10 and abs(d["gls_e"][cs.REST] - (100 - 30)) < 1e-9, d["gls_e"]
    assert d["gls_a"][cs.REST] == 200 - 150 and d["hw_a"]["datapath"] == 20, d["gls_a"]
    assert d["run_cycles"] == 50 and d["groups_pj"] == {"g": 1500.0, "h": 500.0}


def test_rows_and_shares() -> None:
    pts = []
    for w in (4, 2):
        p, e, b = entries(w)
        pts.append(cs.point_data(p, {p["point"]: e}, {p["point"]: b}))
    pts.sort(key=lambda d: d["W"])
    rows = cs.rows(pts)
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "s.csv"
        cs.write_csv(path, rows)
        got = list(csv.DictReader(path.open()))
    assert list(got[0]) == cs.FIELDS
    five = [r for r in got if r["point"] == "x_w2" and r["source"] == "gls" and r["window"] == "5_run"
            and r["metric"] == "share_five_pct"]
    assert abs(sum(float(r["value"]) for r in five) - 100) < 1e-3, five
    hw = [r for r in got if r["point"] == "x_w4" and r["source"] == "hwcost" and r["metric"] == "share_five_pct"
          and r["window"] == "task"]
    assert abs(sum(float(r["value"]) for r in hw) - 100) < 1e-3
    grp = {r["group"]: float(r["value"]) for r in got if r["point"] == "x_w2" and r["window"] == "5_run_group"
           and r["metric"] == "nj"}
    assert grp == {"g": 75.0, "h": 25.0}, grp          # pJ/cycle x 50 cycles
    md = cs.markdown(pts)
    assert md.index("W = 2") < md.index("W = 4") and "| run window | 100.00 |" in md


def test_figure_writes() -> None:
    p, e, b = entries(2)
    pts = [cs.point_data(p, {p["point"]: e}, {p["point"]: b})]
    with tempfile.TemporaryDirectory() as t:
        for kind in ("energy", "area"):
            path = Path(t) / f"{kind}.png"
            cs.figure(pts, kind, path)
            assert path.stat().st_size > 1000
            cs.figure(pts, kind, path.with_name(f"{kind}_five.png"), panels=(False,))
            assert path.with_name(f"{kind}_five.png").stat().st_size > 1000


def test_select_variants() -> None:
    cfg = [{"point": "a_w8", "recipe": "r", "W": 8}, {"point": "a_w2", "recipe": "r", "W": 2},
           {"point": "a_w8_cg", "recipe": "r", "W": 8, "syn": {"clk_gate": True}}, {"point": "b_w4", "recipe": "s", "W": 4}]
    assert [p["point"] for p in cs.select(cfg, "r")] == ["a_w2", "a_w8"]          # the variant left out (X79)
    assert [p["point"] for p in cs.select(cfg, "r", ["a_w8", "a_w8_cg"])] == ["a_w8", "a_w8_cg"]   # X80
    try:
        cs.select(cfg, "r", ["nope"])
    except SystemExit:
        pass
    else:
        raise AssertionError("an unknown point must stop")


def test_figure_by_point() -> None:
    pts = []
    for name in ("x_w2", "x_w2_cg"):
        p, e, b = entries(2)
        p["point"] = name
        pts.append(cs.point_data(p, {name: e}, {name: b}))
    with tempfile.TemporaryDirectory() as t:
        path = Path(t) / "e.png"
        cs.figure(pts, "energy", path, panels=(False,), by_point=True)
        assert path.stat().st_size > 1000


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
