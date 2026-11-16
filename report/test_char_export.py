#!/usr/bin/env python3
"""report/test_char_export.py - char_export.py on the committed clock-gated rows.

  pixi run python report/test_char_export.py

The committed nangate45 CSVs are copied into a temporary results/char/ and char_export.py's main() writes char.json
there. Checked: it equals the committed char.json; flop.area_um2 is the mean of seq_area / seq_cells (a clock gate
counts as a sequential cell, so it is below a DFFR's area); the control factor is the mean over the tier-done forge
points with a power row (the W = 32 bundles made before snax-forge D168 have none) of ctrl's e_dyn over its cells x
e_hold; E_ctrl is that factor x cells x cycles x e_hold. Standard library only.
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
NO_POWER = {"done/dot/forge2_w32", "done/dot/forge4_w32", "done/dot/forge5_w32", "done/dot/forge6_w32",
            "done/vecadd/forge_w32", "done/vecmul/forge_w32", "done/vsum/forge_w32"}


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
             if int(v["synth"]["seq_cells"])]
        self.assertAlmostEqual(self.j["flop"]["area_um2"], sum(a) / len(a), places=5)
        self.assertLess(self.j["flop"]["area_um2"], DFFR_UM2)   # a gate is smaller than a DFFR

    def test_counter_factor(self):
        area, hold = self.j["flop"]["area_um2"], self.j["flop"]["e_hold_fj"]
        cf = ce.counter_factor(TECH, area, hold)
        self.assertEqual(cf["n"], ce.FORGE_POINTS)
        self.assertTrue(all(p.startswith("done/") for p in cf["points"]))
        self.assertFalse(NO_POWER & set(cf["points"]))
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


if __name__ == "__main__":
    unittest.main(verbosity=1)
