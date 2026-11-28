"""forge/test_bundles.py - forge/bundles.py's steps: which --set goes to snax-forge's sandbox and which to its design step.

  pixi run python forge/test_bundles.py

Standard library only; find_recipe is stubbed, so no snax-forge checkout is read.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bundles  # noqa: E402


def sets_of(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]


class SplitSets(unittest.TestCase):
    def setUp(self):
        self._find = bundles.find_recipe
        bundles.find_recipe = lambda name, forge=bundles.FORGE: Path(f"recipes/x/{name}.json")

    def tearDown(self):
        bundles.find_recipe = self._find

    def test_split(self):
        own, design = bundles.split_sets(["N=4096", "types=i8", "dtypes.C=int16", "design.data=full",
                                          "design.narrow_mul=true", "memory.passes.layout=padded_rows",
                                          "platform.x=1"])
        self.assertEqual(own, ["N=4096", "types=i8", "dtypes.C=int16"])
        self.assertEqual(design, ["design.data=full", "design.narrow_mul=true", "memory.passes.layout=padded_rows",
                                  "platform.x=1"])

    def test_steps_route_design_sets(self):
        p = {"point": "done/dot/forge3nm_w8_i8_n4096", "recipe": "dot_v3", "W": 8,
             "sets": ["N=4096", "types=i8", "design.data=full", "design.narrow_mul=true"]}
        s1, s2, s3 = bundles.steps(p, ["N=9"], Path("/out"))
        self.assertEqual(sets_of(s1), ["W=8", "N=4096", "types=i8", "N=9"])
        self.assertEqual(sets_of(s2), ["design.data=full", "design.narrow_mul=true"])
        self.assertEqual(s2[1:3], ["--platform", bundles.PLATFORM])
        # each step's --out is its last argument (run_point reads it there); the folder names keep every set
        self.assertEqual(s1[-2], "--out")
        self.assertEqual(s2[-2], "--out")
        self.assertTrue(s2[-1].endswith("dot_v3_w8_N4096_typesi8_designdatafull_designnarrowmultrue_N9"), s2[-1])
        self.assertEqual(s3[-1], "/out/done/dot/forge3nm_w8_i8_n4096")

    def test_no_design_sets(self):
        p = {"point": "done/vecadd/forge_w8", "recipe": "vecadd_v1", "W": 8, "sets": ["N=2048"]}
        s1, s2, _ = bundles.steps(p, [], Path("/out"))
        self.assertEqual(sets_of(s1), ["W=8", "N=2048"])
        self.assertEqual(sets_of(s2), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
