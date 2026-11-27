#!/usr/bin/env python3
"""report/ablation.py: each step adds only its term, re-pricing from the committed energy runs.

    pixi run python report/test_ablation.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import ablation as ab  # noqa: E402
import model_fit as mf  # noqa: E402

REP = ab.report("nangate45")


def test_run_column_only_beside_the_base():
    """run is ge/<point>.json's program window when it is a run priced with the terms beside the base, else empty."""
    import tempfile  # noqa: PLC0415
    run = {"prices": {"r_strm": 0.1}, "windows": [{"mark": 1, "energy": {"parts": {"memory": 2.0, "dma": 1.0}}},
                                                  {"mark": 9, "energy": {"parts": {"memory": 5.0}}}]}
    with tempfile.TemporaryDirectory() as d:
        old = ab.ROOT, mf.ROOT
        ab.ROOT = mf.ROOT = Path(d)
        try:
            ge = Path(d) / "results" / "cluster" / "nangate45" / "ge"
            (ge / "csyn2").mkdir(parents=True)
            (ge / "p.json").write_text(json.dumps(run))
            assert ab.rerun_nj("nangate45", "p", {1}) is None          # ge/p.json is the base itself
            (ge / "csyn2" / "p.json").write_text(json.dumps({**run, "prices": {}}))
            assert ab.rerun_nj("nangate45", "p", {1}) == 3.0           # beside CSYN2's: the program window's parts
            assert ab.base_ge("nangate45", "p")["prices"] == {}
            (ge / "p.json").write_text(json.dumps({**run, "prices": {}}))
            assert ab.rerun_nj("nangate45", "p", {1}) is None          # not priced with the terms
            (ge / "p.json").unlink()
            assert ab.rerun_nj("nangate45", "p", {1}) is None          # no run
        finally:
            ab.ROOT, mf.ROOT = old


def test_committed_is_the_energy_run():
    en = json.loads((ROOT / "results" / "cluster" / "nangate45" / "energy.json").read_text())
    for pid, r in REP["rows"].items():
        ge = mf._ge("nangate45", f"{pid}_cg")
        marks = {w["mark"] for w in en[f"{pid}_cg"]["windows"]}
        want = sum(sum(w["energy"]["parts"].values()) for w in ge["windows"] if w["mark"] in marks)
        assert abs(r["steps"]["committed"]["nj"] - want) < 1e-6, pid


def test_steps_touch_their_parts():
    touches = {"refusals": {"streamers", "crossbar"}, "floor": {"streamers", "crossbar", "dma"},
               "transfers": {"memory", "dma"}, "copy": {"crossbar", "dma"}}
    for pid, r in REP["rows"].items():
        for prev, step in zip(ab.STEPS, ab.STEPS[1:]):
            a, b = r["steps"][prev]["parts"], r["steps"][step]["parts"]
            moved = {p for p in a if abs(a[p] - b[p]) > 1e-9}
            assert moved <= touches[step], (pid, step, moved)


def test_pipelined_twins_transfer_alike():
    rows = REP["rows"]
    for a, b in (("mvt_column", "mvt_column_pipeline"), ("bicg_two_pass", "bicg_two_pass_pipeline")):
        da = rows[a]["steps"]["transfers"]["parts"]["memory"] - rows[a]["steps"]["floor"]["parts"]["memory"]
        db = rows[b]["steps"]["transfers"]["parts"]["memory"] - rows[b]["steps"]["floor"]["parts"]["memory"]
        assert da > 0 and abs(da - db) < 1e-9, (a, da, db)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_ablation.py: all passed")
