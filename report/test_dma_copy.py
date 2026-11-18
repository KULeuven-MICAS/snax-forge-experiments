#!/usr/bin/env python3
"""report/dma_copy.py: D184's price of mvt's 64 x 64 copy on snitch1_cg's banks, from the committed tables, is
snax-forge's (40.98 nJ in the banks, 13.49 nJ in the crossbar); the config's L1 bank is its 32 macros.

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
    assert abs(p["banks_nj"] - 40.98) < 0.01, p
    assert abs(p["crossbar_nj"] - 13.49) < 0.01, p
    assert abs(p["e_ro_pj"] - 1.839299) < 1e-5 and abs(p["e_wo_pj"] - 1.454513) < 1e-5, p


def test_no_reports_yet_is_empty():
    rep = dc.report("nangate45")
    assert all(r["run"].startswith("snitch1_cg_dma_transpose_") for r in rep["runs"].values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_dma_copy.py: all passed")
