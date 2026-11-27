#!/usr/bin/env python3
"""report/bank_counts.py on a small SAIF: the innermost bank instances, reads and writes from T1, the checks.

    pixi run python report/test_bank_counts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import bank_counts as bc  # noqa: E402

# 10 ns cycles at a 1 ps timescale: 10000 a cycle. Bank 0: 30 cycles of req_i, 10 of we_i; bank 1: 4 and 4.
# The wrapper i_data_mem carries the same nets and must not count twice; the core's port is not a bank.
SAIF = r"""(SAIFILE (SAIFVERSION "2.0") (DIRECTION "backward") (DESIGN ) (DIVIDER / ) (TIMESCALE 1 ps)
(DURATION 1000000)
(INSTANCE tb_bin
 (INSTANCE i_dut
  (INSTANCE i_cluster
   (INSTANCE i_snitch_data_mem
    (INSTANCE gen_banks\[0\]\.i_data_mem
     (NET (req_i\[0\] (T0 700000) (T1 300000) (TX 0) (TC 9)) (we_i\[0\] (T0 900000) (T1 100000) (TX 0) (TC 4)))
     (INSTANCE i_tc_sram
      (NET (req_i (T0 700000) (T1 300000) (TX 0) (TC 9)) (we_i (T0 900000) (T1 100000) (TX 0) (TC 4)))))
    (INSTANCE gen_banks\[1\]\.i_data_mem
     (NET (req_i\[0\] (T0 960000) (T1 40000) (TX 0) (TC 2)) (we_i\[0\] (T0 960000) (T1 40000) (TX 0) (TC 2)))
     (INSTANCE i_tc_sram
      (NET (req_i (T0 960000) (T1 40000) (TX 0) (TC 2)) (we_i (T0 960000) (T1 40000) (TX 0) (TC 2))))))
   (INSTANCE i_snitch_core
    (NET (req_i (T0 0) (T1 1000000) (TX 0) (TC 0)) (we_i (T0 0) (T1 1000000) (TX 0) (TC 0)))))))
)"""


def test_counts_innermost_banks():
    c = bc.count(SAIF)
    assert c == {"banks": 2, "reads": 20, "writes": 14}, c


def test_we_without_req_refused():
    bad = SAIF.replace("(we_i (T0 960000) (T1 40000)", "(we_i (T0 950000) (T1 50000)")
    try:
        bc.count(bad)
    except SystemExit as e:
        assert "not gated" in str(e)
    else:
        raise AssertionError("we_i above req_i passed")


def test_fraction_of_a_cycle_refused():
    bad = SAIF.replace("(req_i (T0 700000) (T1 300000)", "(req_i (T0 699000) (T1 301000)")
    try:
        bc.count(bad)
    except SystemExit as e:
        assert "whole number" in str(e)
    else:
        raise AssertionError("a fraction of a cycle passed")


def test_price_row():
    assert bc.bank_price("sram_d512_w64_m8", "nangate45") == (3.38552, 6.45356)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_bank_counts.py: all passed")
