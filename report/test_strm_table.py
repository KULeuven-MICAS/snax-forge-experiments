#!/usr/bin/env python3
"""report/test_strm_table.py - seeded tests of report/strm_table.py's reference interpolation (X53).

  pixi run strm-table-test

On synthetic tables over the real grids: grid points come back exactly; a function multilinear in the raw values
(a + b d + c l + e ch + f d ch + ...) is reproduced exactly anywhere inside; queries outside the grid and missing
values are refused; the interconnect's energy for inputs > banks is its value at inputs = banks; a query between
grid values stays between the corner values; the interconnect's energy, linear in 1/inputs, reproduces
a + b / inputs exactly while its area stays linear in inputs. CG2 (X83): build() takes only the rows of the clk_gate
asked for, and ratios() pairs gated and ungated rows by point. Standard library only.
"""
from __future__ import annotations

import csv
import itertools
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import strm_table as st  # noqa: E402

DEPTH, LOOPS, CHANNELS = [2, 4, 8, 16], list(range(1, 8)), [1, 2, 4, 6, 8, 16]
INPUTS, BANKS = [4, 8, 16, 24, 32, 40, 48, 56, 64], [16, 32, 64]


def reader_table(f) -> st.Table:
    keys = list(itertools.product(DEPTH, LOOPS, CHANNELS))
    return st.Table({"depth": DEPTH, "loops": LOOPS, "channels": CHANNELS},
                    {"area_um2": {k: f(*k) for k in keys}, "e_beat_pj": {k: 2 * f(*k) for k in keys}})


class TestInterpolation(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(52)

    def test_grid_points_exact(self):
        vals = {k: self.rng.uniform(100, 1e5) for k in itertools.product(DEPTH, LOOPS, CHANNELS)}
        t = st.Table({"depth": DEPTH, "loops": LOOPS, "channels": CHANNELS}, {"area_um2": vals, "e_beat_pj": vals})
        for k in self.rng.sample(sorted(vals), 40):
            self.assertEqual(t.at("area_um2", depth=k[0], loops=k[1], channels=k[2]), vals[k])

    def test_multilinear_reproduced(self):
        a = [self.rng.uniform(-5, 5) for _ in range(8)]
        f = lambda d, lp, c: (a[0] + a[1] * d + a[2] * lp + a[3] * c + a[4] * d * c + a[5] * d * lp  # noqa: E731
                              + a[6] * lp * c + a[7] * d * lp * c)
        t = reader_table(f)
        for _ in range(200):
            d, lp, c = self.rng.uniform(2, 16), self.rng.uniform(1, 7), self.rng.uniform(1, 16)
            area, e = st.reader_cost(t, d, lp, c)
            self.assertAlmostEqual(area, f(d, lp, c), places=6)
            self.assertAlmostEqual(e, 2 * f(d, lp, c), places=6)

    def test_between_corners(self):
        vals = {k: self.rng.uniform(1, 100) for k in itertools.product(INPUTS, BANKS)}
        t = st.Table({"inputs": INPUTS, "banks": BANKS}, {"area_um2": vals, "e_access_pj": vals})
        for _ in range(200):
            i, b = self.rng.uniform(4, 64), self.rng.uniform(16, 64)
            v = t.at("area_um2", inputs=i, banks=b)
            lo_i = max(x for x in INPUTS if x <= i)
            hi_i = min(x for x in INPUTS if x >= i)
            lo_b = max(x for x in BANKS if x <= b)
            hi_b = min(x for x in BANKS if x >= b)
            corners = [vals[(x, y)] for x in (lo_i, hi_i) for y in (lo_b, hi_b)]
            self.assertGreaterEqual(v, min(corners) - 1e-9)
            self.assertLessEqual(v, max(corners) + 1e-9)

    def test_inverse_inputs(self):
        a, b = 2.3, 13.0
        keys = list(itertools.product(INPUTS, BANKS))
        t = st.Table({"inputs": INPUTS, "banks": BANKS},
                     {"area_um2": {(i, bk): 160.0 * i * bk for i, bk in keys},
                      "e_access_pj": {(i, bk): (a + b / i) * bk / 32 for i, bk in keys}},
                     st.XBAR_SCALES)
        for _ in range(200):
            i, bk = self.rng.uniform(4, 64), self.rng.choice(BANKS)
            area, e = st.xbar_cost(t, i, bk)
            self.assertAlmostEqual(e, (a + b / i) * bk / 32, places=9)
            lo = max(x for x in INPUTS if x <= i)
            hi = min(x for x in INPUTS if x >= i)
            w = 0.0 if hi == lo else (i - lo) / (hi - lo)
            self.assertAlmostEqual(area, 160.0 * bk * ((1 - w) * lo + w * hi), places=6)

    def test_outside_refused(self):
        t = reader_table(lambda d, lp, c: d + lp + c)
        for q in ({"depth": 1, "loops": 2, "channels": 4}, {"depth": 17, "loops": 2, "channels": 4},
                  {"depth": 8, "loops": 0, "channels": 4}, {"depth": 8, "loops": 8, "channels": 4},
                  {"depth": 8, "loops": 2, "channels": 0.5}, {"depth": 8, "loops": 2, "channels": 32}):
            with self.assertRaises(ValueError):
                t.at("area_um2", **q)
        with self.assertRaises(ValueError):
            t.at("area_um2", depth=8, loops=2)

    def test_missing_refused(self):
        t = reader_table(lambda d, lp, c: d + lp + c)
        del t.fields["e_beat_pj"][(8, 2, 4)]
        with self.assertRaises(ValueError):
            st.reader_cost(t, 8, 2, 4)
        with self.assertRaises(ValueError):
            st.reader_cost(t, 6, 2, 4)
        st.reader_cost(t, 8, 2, 8)          # a query that does not need the missing value still works

    def test_xbar_energy_above_banks(self):
        e = {(i, b): self.rng.uniform(1, 10) for i, b in itertools.product(INPUTS, BANKS) if i <= b}
        area = {(i, b): self.rng.uniform(1e3, 1e6) for i, b in itertools.product(INPUTS, BANKS)}
        t = st.complete_xbar(st.Table({"inputs": INPUTS, "banks": BANKS}, {"area_um2": area, "e_access_pj": e}))
        for i, b in itertools.product(INPUTS, BANKS):
            want = e[(i, b)] if i <= b else e[(b, b)]
            self.assertEqual(st.xbar_cost(t, i, b)[1], want)
        self.assertAlmostEqual(st.xbar_cost(t, 40, 16)[1], e[(16, 16)])            # between two filled values
        self.assertAlmostEqual(st.xbar_cost(t, 28, 16)[0], (area[(24, 16)] + area[(32, 16)]) / 2)
        mid = st.xbar_cost(t, 48, 24)[1]                                            # banks between 16 and 32
        self.assertAlmostEqual(mid, (e[(16, 16)] + e[(32, 32)]) / 2)


SYNTH = ["point", "clk_gate", "status", "area_um2", "seq_cells", "slack_ns", "fmax_mhz", "depth", "loops", "channels"]
POWER = ["point", "clk_gate", "status", "e_beat_pj"]


def _csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


class TestGated(unittest.TestCase):
    def test_build_takes_one_gate(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / "results" / "streamer" / "nangate45"
            # a row from before X79 (no clk_gate) reads as ungated; the gated rows of the same points sit beside it
            _csv(d / "synth_dc.csv", SYNTH, [
                {"point": "d8_l1_c4", "clk_gate": "", "status": "ok", "area_um2": "100", "seq_cells": "50",
                 "slack_ns": "7", "fmax_mhz": "300", "depth": "8", "loops": "1", "channels": "4"},
                {"point": "d8_l1_c4", "clk_gate": "1", "status": "ok", "area_um2": "80", "seq_cells": "53",
                 "slack_ns": "7.5", "fmax_mhz": "400", "depth": "8", "loops": "1", "channels": "4"},
                {"point": "d2_l1_c1", "clk_gate": "0", "status": "ok, timing violated", "area_um2": "20",
                 "seq_cells": "10", "slack_ns": "-1", "fmax_mhz": "90", "depth": "2", "loops": "1", "channels": "1"}])
            _csv(d / "power_pt.csv", POWER, [
                {"point": "d8_l1_c4", "clk_gate": "1", "status": "ok", "e_beat_pj": "10"},
                {"point": "d8_l1_c4", "clk_gate": "", "status": "ok", "e_beat_pj": "20"},
                {"point": "d2_l1_c1", "clk_gate": "", "status": "ok", "e_beat_pj": "2"}])
            un = st.build("streamer", "nangate45", "0", Path(t))
            cg = st.build("streamer", "nangate45", "1", Path(t))
            self.assertEqual([(r["channels"], r["area_um2"], r["e_beat_pj"], r["flops"]) for r in un],
                             [("1", "20", "2", "10"), ("4", "100", "20", "50")])
            self.assertEqual([(r["channels"], r["area_um2"], r["e_beat_pj"], r["flops"], r["status"]) for r in cg],
                             [("4", "80", "10", "53", "ok")])
            got = st.ratios(cg, un, st.READER_AXES, ("area_um2", "e_beat_pj", "flops"))
            self.assertEqual(len(got), 1)
            self.assertAlmostEqual(got[0]["area_um2"], 0.8)
            self.assertAlmostEqual(got[0]["e_beat_pj"], 0.5)
            self.assertAlmostEqual(got[0]["flops"], 53 / 50)


if __name__ == "__main__":
    unittest.main(verbosity=1)
