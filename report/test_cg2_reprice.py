#!/usr/bin/env python3
"""report/test_cg2_reprice.py - report/cg2_reprice.py (CG2).

  pixi run cg2-reprice-test

The ungated table set gives back every part (area and energy) of the committed HWCOST json at W = 2, 4, 8, 16 and
32, W = 32 extrapolated on the readers' channels and the crossbar's inputs as snax-forge's estimate does.
A gated set made by scaling the ungated tables (reader energy x 0.5, e_hold x 0.1 with ctrl's factor rescaled)
moves the streamers' energy by exactly 0.5, keeps ctrl's energy, and a gated reader table without dot_3's points
leaves those fields empty and names them. The comparison with the cluster comes for every W with a gated point
(dot3_w8_cg today) and for no other. Standard library only.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cg2_reprice as rp  # noqa: E402
import strm_table as st  # noqa: E402

TECH = "nangate45"


def scaled(base: rp.Tables, e_beat: float, hold: float) -> rp.Tables:
    t = copy.copy(base)
    t.name = "gated"
    f = {k: dict(v) for k, v in base.reader.fields.items()}
    f["e_beat_pj"] = {k: v * e_beat for k, v in f["e_beat_pj"].items()}
    t.reader = st.Table(base.reader.axes, f, base.reader.scales)
    t.char = copy.deepcopy(base.char)
    t.char["flop"]["e_hold_fj"] = base.char["flop"]["e_hold_fj"] * hold
    t.char["ctrl"]["counter_factor"] = base.char["ctrl"]["counter_factor"] / hold
    return t


class TestReprice(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.u = rp.Tables(TECH, "ungated")

    def test_ungated_gives_back_hwcost(self):
        for w in rp.WS:
            cost = rp.hwcost(TECH, w)
            parts, gaps = rp.price(self.u, w, cost)
            self.assertEqual(gaps, [])
            for p in rp.PARTS:
                self.assertAlmostEqual(parts[p][0], cost["parts"][p]["area"], delta=1e-9 * cost["parts"][p]["area"])
                self.assertAlmostEqual(parts[p][1], cost["parts"][p]["energy"], delta=1e-9 * cost["parts"][p]["energy"])

    def test_w32_extrapolated(self):
        out: list[str] = []
        rp.price(self.u, 32, rp.hwcost(TECH, 32), out)
        self.assertEqual(out, ["reader d8_l1_c32 area_um2 on channels", "reader d8_l1_c32 e_beat_pj on channels",
                               "xbar i67_b32 area_um2 on inputs"])
        out = []
        rp.price(self.u, 16, rp.hwcost(TECH, 16), out)
        self.assertEqual(out, [])

    def test_strict_table_refuses_outside(self):
        with self.assertRaises(ValueError):
            self.u.reader.at("e_beat_pj", depth=8, loops=1, channels=32)

    def test_vs_cluster_only_where_gated(self):
        g, _ = rp.price(self.u, 8, rp.hwcost(TECH, 8))
        lines = rp.vs_cluster(TECH, 8, g)
        self.assertTrue(any(x.startswith("dot3_w8_cg:") for x in lines), lines)
        self.assertEqual(sum(x.startswith("| five parts |") for x in lines), 2)
        g, _ = rp.price(self.u, 2, rp.hwcost(TECH, 2))
        if "dot3_w2_cg" not in (rp.ROOT / "results" / "cluster" / TECH / "energy.json").read_text():
            self.assertEqual(rp.vs_cluster(TECH, 2, g), [])

    def test_scaled_set(self):
        g = scaled(self.u, 0.5, 0.1)
        for w in rp.WS:
            cost = rp.hwcost(TECH, w)
            pu, _ = rp.price(self.u, w, cost)
            pg, _ = rp.price(g, w, cost)
            self.assertAlmostEqual(pg["streamers"][1] / pu["streamers"][1], 0.5, places=12)
            self.assertAlmostEqual(pg["control"][1], pu["control"][1], places=12)
            self.assertAlmostEqual(pg["streamers"][0], pu["streamers"][0], places=9)
            self.assertLess(pg["datapath"][1], pu["datapath"][1])        # the tree's held register costs less

    def test_partial_gated_grid(self):
        g = copy.copy(self.u)
        keep = {k: v for k, v in self.u.reader.fields["e_beat_pj"].items() if k[2] != 8}
        g.reader = st.Table(self.u.reader.axes, {**self.u.reader.fields, "e_beat_pj": keep})
        parts, gaps = rp.price(g, 8, rp.hwcost(TECH, 8))
        self.assertIsNone(parts["streamers"][1])
        self.assertIsNotNone(parts["streamers"][0])
        self.assertTrue(any("reader d8_l1_c8" in x for x in gaps), gaps)
        parts, gaps = rp.price(g, 4, rp.hwcost(TECH, 4))
        self.assertIsNotNone(parts["streamers"][1])


if __name__ == "__main__":
    unittest.main(verbosity=1)
