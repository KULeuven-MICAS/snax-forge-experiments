"""report/tier_check.py's ordering maths, and the committed CSYN2 points if snax-forge is beside this repo.

    pixi run python report/test_tier_check.py
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import tier_check as tc  # noqa: E402


def test_kendall_with_ties():
    assert tc.kendall([1, 2, 3], [10, 20, 30]) == (1.0, [])
    t, disc = tc.kendall([1, 2, 3], [30, 20, 10])
    assert t == -1.0 and len(disc) == 3
    t, disc = tc.kendall([100, 100.5, 200], [1, 2, 3])        # the first pair is within 1 %: neither
    assert abs(t - 2 / 3) < 1e-12 and disc == []
    assert tc.kendall([1], [1]) == (None, [])


def test_best_keeps_ties():
    assert tc.best([10, 10.05, 12]) == [0, 1]
    assert tc.best([12, 10]) == [1]


def test_committed_points():
    if not (tc.FORGE / "paper" / "data" / "forms.csv").is_file():
        print("  (no snax-forge beside this repo: skipped)")
        return
    j = tc.check("nangate45")
    assert not j["missing"] and len(j["points"]) >= 14
    for r in j["points"]:                                       # the netlist's windows are the RTL's
        assert r["netlist"]["cycles"] == sum(r["netlist"]["windows"].values())
        assert set(r["gvsoc"]["windows"]) == set(r["netlist"]["windows"]), r["id"]
    json.dumps(j, default=list)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
