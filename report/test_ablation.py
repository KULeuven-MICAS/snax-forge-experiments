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


def test_committed_is_the_energy_run():
    en = json.loads((ROOT / "results" / "cluster" / "nangate45" / "energy.json").read_text())
    for pid, r in REP["rows"].items():
        ge = mf._ge("nangate45", f"{pid}_cg")
        marks = {w["mark"] for w in en[f"{pid}_cg"]["windows"]}
        want = sum(sum(w["energy"]["parts"].values()) for w in ge["windows"] if w["mark"] in marks)
        assert abs(r["steps"]["committed"]["nj"] - want) < 1e-6, pid


def test_steps_touch_their_parts():
    touches = {"refusals": {"streamers", "crossbar"}, "floor": {"streamers", "crossbar", "dma"},
               "transfers": {"memory", "dma"}, "copy": {"crossbar", "dma"}, "dma_banks": {"memory"}}
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
