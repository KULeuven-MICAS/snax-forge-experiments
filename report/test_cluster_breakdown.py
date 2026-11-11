"""report/cluster_breakdown.py and cluster/hwcost.py on made-up hierarchies (no DC, no snax-forge).

    pixi run cluster-breakdown-test
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report"), str(ROOT / "cluster")]
import cluster_breakdown as cb  # noqa: E402
import hwcost  # noqa: E402

CFG = {"groups": [
    {"name": "banks", "label": "banks", "rules": [{"path": "c/mem/.*", "design": "tc_sram_impl_.*"}]},
    {"name": "dp", "label": "datapath", "rules": [{"path": "acc/sh/dp"}]},
    {"name": "acc", "label": "accelerator rest", "rules": [{"path": "acc"}]},
    {"name": "cores", "label": "cores", "rules": [{"path": r"c/core\[\d+\]"}]},
    {"name": "others", "label": "others", "rules": []}],
    "hwcost": {"datapath": ["dp"], "control": [], "streamers": ["acc"], "crossbar": ["cores"], "memory": ["banks"]}}


def rows():
    # (path, total, design); a parent before its children, as DC writes them
    t = [("", 1000.0, "top"), ("c", 700.0, "cluster"), ("c/mem", 400.0, "mem"),
         ("c/mem/b0", 190.0, "tc_sram_impl_a"), ("c/mem/b1", 190.0, "tc_sram_impl_a"), ("c/mem/glue", 15.0, "x"),
         ("c/core[0]", 100.0, "snitch"), ("c/core[1]", 120.0, "snitch"), ("c/core[1]/fpu", 50.0, "fpu"),
         ("acc", 290.0, "wrap"), ("acc/sh", 250.0, "shell"), ("acc/sh/dp", 200.0, "dp"), ("acc/sh/csr", 30.0, "csr")]
    return [{"path": p, "total": a, "design": d} for p, a, d in t]


def test_groups_add_up_and_follow_the_rules():
    g = cb.groups(rows(), CFG)
    assert abs(sum(g.values()) - 1000.0) < 1e-9, g
    # banks: the two macros only; the mem node's own 5 and its glue 15 fall to the cluster's group (others)
    assert g == {"banks": 380.0, "dp": 200.0, "acc": 90.0, "cores": 220.0, "others": 110.0}, g


def test_a_child_takes_its_parents_group_unless_a_rule_names_it():
    a = cb.assign(rows(), CFG)
    assert a["c/core[1]/fpu"] == "cores" and a["acc/sh/csr"] == "acc" and a["acc/sh/dp"] == "dp"
    assert a["c/mem/glue"] == "others" and a[""] == "others"


def test_hwcost_rows():
    g = cb.groups(rows(), CFG)
    cost = {"parts": {"datapath": {"area": 210.0}, "control": {"area": 0.0}, "streamers": {"area": 90.0},
                      "crossbar": {"area": 220.0}, "memory": {"area": 380.0}}}
    h = cb.hwcost_rows(cost, g, CFG)
    dp = h["parts"][0]
    assert dp["part"] == "datapath" and abs(dp["diff_pct"] - 5.0) < 1e-9, dp
    assert h["parts"][1]["diff_pct"] is None                    # nothing to compare with
    assert h["cluster_um2"] == 890.0 and h["not_costed_um2"] == 110.0, h
    assert abs(sum(r["hwcost_share_pct"] for r in h["parts"]) - 100.0) < 1e-9


def test_the_real_groups_file_compiles_and_maps_every_part():
    cfg = json.loads((ROOT / "cluster" / "groups.json").read_text())
    cb.compile_groups(cfg)
    names = {g["name"] for g in cfg["groups"]}
    assert set(cfg["hwcost"]) == set(cb.PARTS) and all(set(v) <= names for v in cfg["hwcost"].values())
    assert cfg["groups"][-1]["name"] == "others" and set(cb.MACROS) <= names


def test_hwcost_params():
    assert hwcost.params({"W": 16, "sets": ["N=2048"]}) == {"W": 16, "N": 2048}
    for bad in ("platform.x=1", "N"):
        try:
            hwcost.params({"W": 1, "sets": [bad]})
        except ValueError:
            continue
        raise AssertionError(f"params accepted {bad!r}")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
