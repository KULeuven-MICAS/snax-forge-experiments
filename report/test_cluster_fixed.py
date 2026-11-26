#!/usr/bin/env python3
"""report/cluster_fixed.py on the committed reports: the three parts add up their groups, cover what HWCOST leaves out
but the banks and the five parts' groups, the groups' leakage adds up to PrimePower's top, and the icache's macros
leak as the lstp table says.

    pixi run python report/test_cluster_fixed.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cluster_fixed as cf  # noqa: E402

TECH = "nangate45"


def test_parts_add_up():
    j = cf.fixed(TECH)
    for p, x in j["parts"].items():
        gs = [g for g, y in j["groups"].items() if y["part"] == p]
        assert gs == x["groups"], (p, gs)
        for k in ("area_um2", "leak_uw"):
            assert abs(x[k] - sum(j["groups"][g][k] for g in gs)) < 1e-9, (p, k)


def test_covers_what_hwcost_leaves_out():
    j = cf.fixed(TECH)
    b = json.loads((cf.ROOT / "results" / "cluster" / TECH / "breakdown.json").read_text())[cf.POINT]
    area = sum(x["area_um2"] for x in j["parts"].values())
    assert abs(area - b["hwcost"]["not_costed_um2"]) < 1e-3, (area, b["hwcost"]["not_costed_um2"])


def test_leakage_adds_up_to_the_top():
    c = cf.fixed(TECH)["check"]
    assert abs(c["groups_leak_uw"] - c["pt_leak_uw"]) <= 1e-6 * c["pt_leak_uw"], c


def test_icache_macros_at_lstp():
    j = cf.fixed(TECH)
    t = cf.bank_leak_uw(TECH)
    assert abs(j["groups"]["icache_macros"]["leak_uw"] - 2 * (t[(128, 256)] + t[(128, 40)])) < 1e-9


def test_no_floor_for_the_bank_logic():
    j = cf.fixed(TECH)
    assert j["groups"]["tcdm_logic"]["idle_pj_cycle"] is None
    assert all(j["groups"][g]["idle_pj_cycle"] is not None for g in j["groups"] if g not in cf.NO_FLOOR)


def test_equals_the_committed_file():
    got = json.loads(json.dumps(cf.fixed(TECH)))
    assert got == json.loads((cf.ROOT / "results" / "cluster" / TECH / "cluster_fixed.json").read_text())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("report/test_cluster_fixed.py: all passed")
