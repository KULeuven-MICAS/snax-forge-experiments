#!/usr/bin/env python3
"""report/test_char_export.py - char_export.py --clk-gate (CG2, X83) on synthetic gated rows.

  pixi run char-export-test

The committed nangate45 CSVs and char.json are copied into a temporary results/char/ (their ungated rows only), and
every row gets a gated twin: integrated clock gates added as sequential cells (one CLKGATE_X1 per 64 bits), the combinational area and
energy a little lower, the idle flop energy far lower. Checked: the ungated rows still load as before (the gated
twins left out); char_cg.json keeps char.json's format and blocks; flop.area_um2 is the mean of seq_area /
seq_cells; e_hold is the gated mean idle e_bit; ctrl's factor is rescaled so that E_ctrl is char.json's (within the
factor's two decimals); the gated/ungated ratios come out as built. Standard library only.
"""
from __future__ import annotations

import csv
import json
import math
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
ICG_UM2 = 3.458
COMB, IDLE = 0.97, 0.1          # the gated twin's comb area and e_comb scale, its idle e_bit scale


def rows(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames), list(r)


def write(path: Path, cols: list[str], data: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(data)


def gated_synth(r: dict) -> dict:
    g = dict(r, clk_gate="1")
    n = int(r["seq_cells"])
    icg = math.ceil(n / 64) if n else 0
    g["seq_cells"] = str(n + icg)
    g["seq_area_um2"] = f"{float(r['seq_area_um2']) + icg * ICG_UM2:.6f}"
    g["comb_area_um2"] = f"{float(r['comb_area_um2']) * COMB:.6f}"
    g["area_um2"] = f"{float(g['seq_area_um2']) + float(g['comb_area_um2']):.6f}"
    return g


def gated_power(r: dict, cells: dict) -> dict:
    g = dict(r, clk_gate="1")
    g["e_comb_pj"] = f"{float(r['e_comb_pj']) * COMB:.7g}"
    n = cells[r["point"]]
    if r["e_bit_pj"]:
        e_bit = float(r["e_bit_pj"]) * (IDLE if r["window"] == "idle" else 1.0)
        g["e_flop_pj"] = f"{e_bit * n:.7g}"
        g["e_bit_pj"] = f"{float(g['e_flop_pj']) / n:.7g}"
    return g


class TestCharExportGated(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(dir=ct.ROOT)       # inside the repo: main_cg names paths from it
        cls.old = ct.CHAR
        char = Path(cls.tmp.name) / "char"
        (char / TECH).mkdir(parents=True)
        shutil.copy(cls.old / TECH / "char.json", char / TECH / "char.json")
        scols, srows = rows(cls.old / TECH / "char_synth.csv")
        pcols, prows = rows(cls.old / TECH / "char_power.csv")
        # the twins are made from the ungated rows; committed gated rows (CG2 R2) are left out
        srows = [r for r in srows if r.get("clk_gate", "") != "1"]
        prows = [r for r in prows if r.get("clk_gate", "") != "1"]
        gs = [gated_synth(r) for r in srows]
        cells = {r["point"]: int(r["seq_cells"]) for r in gs}
        gp = [gated_power(r, cells) for r in prows]
        scols = scols if "clk_gate" in scols else scols[:4] + ["clk_gate"] + scols[4:]
        pcols = pcols if "clk_gate" in pcols else pcols[:8] + ["clk_gate"] + pcols[8:]
        write(char / TECH / "char_synth.csv", scols, srows + gs)
        write(char / TECH / "char_power.csv", pcols, prows + gp)
        cls.srows, cls.gs, cls.gp = srows, gs, gp
        ct.CHAR = char
        cls.points = json.loads(ct.POINTS.read_text())
        cls.base = json.loads((char / TECH / "char.json").read_text())
        with redirect_stdout(StringIO()) as out:
            ce.main_cg(cls.points)
        cls.out = out.getvalue()
        cls.cg = json.loads(ce.path_cg(TECH).read_text())

    @classmethod
    def tearDownClass(cls):
        ct.CHAR = cls.old
        cls.tmp.cleanup()

    def test_ungated_rows_unchanged(self):
        d = ct.load(TECH, self.points)
        drop = lambda r: {k: v for k, v in r.items() if k != "clk_gate"}  # noqa: E731  the column the twins added
        self.assertEqual({p: drop(v["synth"]) for p, v in d.items()}, {r["point"]: drop(r) for r in self.srows})

    def test_format_and_blocks(self):
        self.assertEqual(set(self.cg), set(self.base))
        self.assertEqual(set(self.cg["flop"]), set(self.base["flop"]))
        self.assertEqual(set(self.cg["blocks"]), set(self.base["blocks"]))
        self.assertEqual(self.cg["source"]["clk_gate"], "1")
        for dp, entries in self.cg["blocks"].items():
            for x, y in zip(entries, self.base["blocks"][dp]):
                self.assertEqual(x["params"], y["params"])
                for q, r in zip(x["points"], y["points"]):
                    self.assertAlmostEqual(q["comb_um2"], r["comb_um2"] * COMB, places=3)
                    self.assertAlmostEqual(q["e_comb_pj"], r["e_comb_pj"] * COMB, delta=1e-6 * r["e_comb_pj"] + 1e-9)

    def test_flop_area_is_the_mean(self):
        a = [float(r["seq_area_um2"]) / int(r["seq_cells"]) for r in self.gs if int(r["seq_cells"])]
        self.assertAlmostEqual(self.cg["flop"]["area_um2"], sum(a) / len(a), places=5)
        self.assertLess(self.cg["flop"]["area_um2"], self.base["flop"]["area_um2"])   # a gate is smaller than a DFFR

    def test_e_hold_and_ctrl(self):
        hold = self.cg["flop"]["e_hold_fj"]
        self.assertAlmostEqual(hold, self.base["flop"]["e_hold_fj"] * IDLE, delta=0.01 * hold)
        bits, cycles = 67, 257
        e0, e1 = ce.e_ctrl(self.base, bits, cycles), ce.e_ctrl(self.cg, bits, cycles)
        self.assertAlmostEqual(e1 / e0, 1.0, delta=0.005 / self.cg["ctrl"]["counter_factor"] + 1e-3)

    def test_ratios_printed(self):
        self.assertIn("gated / ungated per point", self.out)
        self.assertIn("lanes/mul_w8: area_um2", self.out)
        line = next(ln for ln in self.out.splitlines() if ln.startswith("  tree/add_w8: area_um2"))
        self.assertIn("seq_cells 1.0156", line)             # 65 / 64: one gate per 64 bits
        self.assertIn("tree/add_w8: 65 sequential cells, its bits are 64", self.out)   # printed, not failed (X82)


if __name__ == "__main__":
    unittest.main(verbosity=1)
