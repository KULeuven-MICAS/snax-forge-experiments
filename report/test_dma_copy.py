#!/usr/bin/env python3
"""report/dma_copy.py: D184's price of mvt's 64 x 64 copy on snitch1_cg's banks, from the committed tables, is
322.41 nJ in the banks at itrs-lstp (8 per burst) and 13.49 nJ in the crossbar; the config's L1 bank is its 32 macros.

    pixi run python report/test_dma_copy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import dma_copy as dc  # noqa: E402


def test_l1_bank():
    pts = json.loads(dc.POINTS.read_text())
    one = next(c for c in pts["configs"] if c["config"] == "snitch1_cg")
    assert dc.l1_bank(one) == (32, 512, 64)


def test_d184_price():
    p = dc.d184_price(64 * 64, 32, 512, 64, "nangate45")
    assert p["superbank_banks"] == 8, p
    assert abs(p["banks_nj"] - 322.41) < 0.01, p
    assert abs(p["crossbar_nj"] - 13.49) < 0.01, p
    assert abs(p["e_ro_pj"] - 1.839299) < 1e-5 and abs(p["e_wo_pj"] - 1.454513) < 1e-5, p


def test_e_burst():
    rep = dc.report("nangate45")
    if not rep["runs"]:
        return
    floor = rep["engine"]["idle"]["pj_cycle"]
    for r in rep["runs"].values():
        e = r["e_burst"]
        assert abs(e["pj"] - e["dma_pj"] - e["axi_pj"]) < 1e-9, e
        want = (r["groups"]["dma"] * 1e3 - r["cycles"] * floor["dma"]) / r["d184"]["bursts"]
        assert abs(e["dma_pj"] - want) < 1e-9, e
    mean = sum(r["e_burst"]["pj"] for r in rep["runs"].values()) / len(rep["runs"])
    assert abs(rep["engine"]["e_burst_pj"] - mean) < 1e-9
    assert 90 < mean < 120, mean


def test_no_reports_yet_is_empty():
    rep = dc.report("nangate45")
    assert all(r["run"].startswith("snitch1_cg_dma_transpose_") for r in rep["runs"].values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_dma_copy.py: all passed")
