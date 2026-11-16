#!/usr/bin/env python3
"""report/test_char_export.py - char_export.py on the committed clock-gated rows.

  pixi run python report/test_char_export.py

The committed nangate45 CSVs are copied into a temporary results/char/ and char_export.py's main() writes char.json
there. Checked: it equals the committed char.json; flop.area_um2 is the mean of seq_area / seq_cells over the int64
points (a clock gate counts as a sequential cell, so it is below a DFFR's area); the control factor is the mean over
the 48 int64 tier-done forge points (the narrow ones, a types= set, are T7's check) of ctrl's e_dyn
over its cells x e_hold; E_ctrl is that factor x cells x cycles x e_hold; the type axis's rules (X89): copy from a
pair's point at W0, a narrow fold's slope, a narrow LinkBuffer's width, the packer's bits, the check points left out.
Standard library only.
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import char_export as ce  # noqa: E402
import char_table as ct  # noqa: E402

TECH = "nangate45"
DFFR_UM2 = 5.32                 # NangateOpenCellLibrary's DFFR_X1
NARROW = {"done/vecmul/forge_w8_i8", "done/dot/forge3_w32_i8"}


class TestCharExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ct.ROOT)
        cls.old = ct.CHAR
        char = Path(cls.tmp.name) / "char"
        (char / TECH).mkdir(parents=True)
        for f in ("char_synth.csv", "char_power.csv"):
            shutil.copy(cls.old / TECH / f, char / TECH / f)
        ct.CHAR = char
        with redirect_stdout(StringIO()) as out:
            ce.main()
        cls.out = out.getvalue()
        cls.j = json.loads(ce.path(TECH).read_text())
        cls.committed = (cls.old / TECH / "char.json").read_text()
        cls.points = json.loads(ct.POINTS.read_text())
        cls.d = ct.load(TECH, cls.points)

    @classmethod
    def tearDownClass(cls):
        ct.CHAR = cls.old
        cls.tmp.cleanup()

    def test_equals_the_committed_table(self):
        self.assertEqual(ce.path(TECH).read_text(), self.committed)
        self.assertEqual(self.j["source"]["clk_gate"], "1")

    def test_flop_area_is_the_mean(self):
        a = [float(v["synth"]["seq_area_um2"]) / int(v["synth"]["seq_cells"]) for v in self.d.values()
             if int(v["synth"]["seq_cells"]) and ct.is64(v["params"])]
        self.assertAlmostEqual(self.j["flop"]["area_um2"], sum(a) / len(a), places=5)
        self.assertLess(self.j["flop"]["area_um2"], DFFR_UM2)   # a gate is smaller than a DFFR

    def test_counter_factor(self):
        area, hold = self.j["flop"]["area_um2"], self.j["flop"]["e_hold_fj"]
        cf = ce.counter_factor(TECH, area, hold)
        self.assertEqual(cf["n"], ce.FORGE_POINTS)
        self.assertTrue(all(p.startswith("done/") for p in cf["points"]))
        self.assertFalse(NARROW & set(cf["points"]))
        self.assertIn("done/dot/forge4_w32", cf["points"])
        for p, v in cf["points"].items():
            self.assertAlmostEqual(v, cf["e_ctrl"][p] / (cf["bits"][p] * hold / 1000), places=9)
        self.assertEqual(self.j["ctrl"]["counter_factor"], round(sum(cf["points"].values()) / cf["n"], 2))

    def test_ctrl_cells_from_seq_area(self):
        area = self.j["flop"]["area_um2"]
        with (ct.RES / "forge" / TECH / "synth_dc_modules.csv").open(newline="") as fh:
            seq = {r["point"]: float(r["seq_um2"]) for r in csv.DictReader(fh)
                   if r["path"] == "ctrl/ctrl" and r.get("clk_gate") == "1"}
        for p, n in ce.ctrl_bits(TECH, area).items():
            self.assertEqual(n, round(seq[p] / area), p)
            self.assertGreater(n, 0, p)

    def test_e_ctrl(self):
        bits, cycles = 67, 257
        want = self.j["ctrl"]["counter_factor"] * bits * cycles * self.j["flop"]["e_hold_fj"] / 1000
        self.assertAlmostEqual(ce.e_ctrl(self.j, bits, cycles), want, places=12)

    def test_gates_printed_not_failed(self):
        self.assertIn("tree/add_w8: 65 sequential cells, its bits are 64", self.out)

    def test_constants_from_the_int64_points(self):
        self.assertEqual((ce.flop_area(self.d)["n"], ce.e_load(self.d)["n"], ce.e_hold(self.d)["n"]), (21, 17, 14))

    def test_check_points_left_out(self):
        written = {(dp, json.dumps(x["params"], sort_keys=True), q.get("lanes"), q.get("depth"))
                   for dp, es in self.j["blocks"].items() for x in es for q in x["points"]}
        for p in self.points:
            key = {k: v for k, v in p["params"].items() if k not in ce.SHAPE}
            there = (p["datapath"], json.dumps(key, sort_keys=True), p["params"].get("lanes"), p["params"].get("depth"))
            self.assertEqual(there in written, not ct.check_only(p["datapath"], p["params"]), p["point"])

    def test_copy_from_the_pair_at_w0(self):
        params = next(p["params"] for p in self.points if p["point"] == "mac/acc_w8_i8_i32")
        at8 = ce.comb_at(self.j, "Mac", params, "comb_um2")
        self.assertAlmostEqual(ce.comb_at(self.j, "Mac", {**params, "lanes": 1}, "comb_um2"), at8 / 8, places=9)
        self.assertAlmostEqual(ce.comb_at(self.j, "Mac", {**params, "lanes": 32}, "comb_um2"), 4 * at8, places=9)

    def test_narrow_fold_slope(self):
        params = next(p["params"] for p in self.points if p["point"] == "tree/add_w8_i8_i32")
        p64 = next(p["params"] for p in self.points if p["point"] == "tree/add_w8")
        for col in ce.COMB:
            s64 = (ce.comb_at(self.j, "TreeAccumulate", {**p64, "lanes": 32}, col)
                   - ce.comb_at(self.j, "TreeAccumulate", p64, col)) / 24
            at8 = ce.comb_at(self.j, "TreeAccumulate", params, col)
            self.assertAlmostEqual(ce.comb_at(self.j, "TreeAccumulate", {**params, "lanes": 32}, col),
                                   at8 + 24 * s64 * 8 / 64, places=4)
            self.assertAlmostEqual(ce.comb_at(self.j, "TreeAccumulate", {**params, "lanes": 2}, col),
                                   at8 - 6 * s64 * 8 / 64, places=4)

    def test_narrow_link_by_width(self):
        p64 = next(p["params"] for p in self.points if p["point"] == "link/d4_w1")
        for col in ce.COMB:
            self.assertAlmostEqual(ce.comb_at(self.j, "LinkBuffer", {**p64, "dtype": "int8"}, col),
                                   ce.comb_at(self.j, "LinkBuffer", p64, col) * 8 / 64, places=9)

    def test_packer_bits(self):
        for r, t, flops in ((2, "int32", 33), (4, "int16", 50), (8, "int8", 59)):
            params = {"inLanes": 1, "laneType": t, "words": 1}
            self.assertEqual(ce.n_bits("FifoPacker", params), flops)
            w = ce.width(t)
            self.assertAlmostEqual(ce.load_bits("FifoPacker", params), (r - 1) / r * w + (r - 1).bit_length(), places=9)


if __name__ == "__main__":
    unittest.main(verbosity=1)
