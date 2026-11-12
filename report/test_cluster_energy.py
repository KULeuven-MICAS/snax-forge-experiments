"""report/cluster_energy.py on made-up PT hierarchies (no PT, no snax-forge).

    pixi run cluster-energy-test
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import cluster_energy as ce  # noqa: E402

CFG = {"groups": [
    {"name": "banks", "label": "banks", "rules": [{"path": "c/mem/.*", "design": "tc_sram_impl_.*"}]},
    {"name": "dp", "label": "datapath", "rules": [{"path": r"i_snax_core_0_acc_0_x/i_x_shell_wrapper/dp"}]},
    {"name": "str", "label": "streamers", "rules": [{"path": "i_str"}]},
    {"name": "xbar", "label": "interconnect", "rules": [{"path": "c/xbar"}]},
    {"name": "others", "label": "others", "rules": []}],
    "hwcost": {"datapath": ["dp"], "control": [], "streamers": ["str"], "crossbar": ["xbar"], "memory": ["banks"]}}

HEAD = """Report : Averaged Power
	-hierarchy
                                      Int                       Switch                    Leak                      Total
Hierarchy                             Power                     Power                     Power                     Power                     %
------------------------------------------------------------------------------------------------------------------------
"""


def report(p: dict[str, tuple[float, float]]) -> str:
    """A PT hierarchy report: (internal, switching) in W per node; leakage 1 W everywhere, which must be left out."""
    t = [("", 0, "top"), ("c", 1, "cluster"), ("c/mem", 2, "mem"), ("c/mem/b0", 3, "tc_sram_impl_a"),
         ("c/mem/gen_banks[1].b1", 3, "tc_sram_impl_a"), ("c/xbar", 2, "xbar"),
         ("i_snax_core_0_acc_0_x", 1, "wrap"), ("i_snax_core_0_acc_0_x/i_x_shell_wrapper", 2, "shell"),
         ("i_snax_core_0_acc_0_x/i_x_shell_wrapper/dp", 3, "dp_7"), ("i_str", 1, "streamer")]
    kids: dict[str, list[str]] = {}
    for path, _, _ in t[1:]:
        kids.setdefault(path.rsplit("/", 1)[0] if "/" in path else "", []).append(path)

    def tot(path: str) -> tuple[float, float]:
        i, s = p.get(path, (0.0, 0.0))
        for k in kids.get(path, []):
            ki, ks = tot(k)
            i, s = i + ki, s + ks
        return i, s

    out = []
    for path, d, design in t:
        i, s = tot(path)
        name = design if d == 0 else path.rsplit("/", 1)[-1]
        label = name if d == 0 else f"{name} ({design})"
        pct = "N/A" if i + s == 0 else "12.3"
        out.append(f"{'  ' * d}{label}   {i:.6e}   {s:.6e}   {1.0:.6e}   {i + s + 1.0:.6e}   {pct}")
    return HEAD + "\n".join(out) + "\n"


IDLE = {"": (0.0, 0.0), "c": (0.002, 0.0), "i_str": (0.015, 0.0), "c/xbar": (0.0003, 0.0)}
RUN = {"": (0.0, 0.0), "c": (0.002, 0.0), "i_str": (0.014, 0.001), "c/xbar": (0.003, 0.002),
       "c/mem/b0": (0.004, 0.0), "c/mem/gen_banks[1].b1": (0.004, 0.0),
       "i_snax_core_0_acc_0_x/i_x_shell_wrapper/dp": (0.005, 0.003), "i_snax_core_0_acc_0_x/i_x_shell_wrapper": (0.0001, 0.0)}


def test_parse_keeps_paths_and_leaves_leakage_out():
    rows = ce.parse_hierarchy(report(RUN))
    assert rows[0]["path"] == "" and rows[0]["design"] == "top"
    paths = [r["path"] for r in rows]
    assert "c/mem/gen_banks[1].b1" in paths and "i_snax_core_0_acc_0_x/i_x_shell_wrapper/dp" in paths, paths
    dyn = sum(i + s for i, s in RUN.values())
    assert abs(rows[0]["total"] - dyn) < 1e-12, (rows[0]["total"], dyn)       # no leakage


def test_groups_add_up_to_the_top_in_pj_per_cycle():
    rows = ce.parse_hierarchy(report(RUN))
    g = ce.window_groups(rows, CFG, 10.0)
    assert abs(sum(g.values()) - ce.pj_per_cycle(rows[0]["total"], 10.0)) < 1e-9
    assert abs(g["banks"] - 80.0) < 1e-9 and abs(g["dp"] - 80.0) < 1e-9, g    # 8 mW * 10 ns = 80 pJ
    assert abs(g["xbar"] - 50.0) < 1e-9 and abs(g["str"] - 150.0) < 1e-9, g


def wins():
    w = []
    for name, mark, kind, cyc, p in (("4_acc_config", 4, "acc_config", 11, IDLE), ("5_run", 5, "run", 185, RUN)):
        w.append({"name": name, "mark": mark, "kind": kind, "cycles": cyc,
                  "groups": ce.window_groups(ce.parse_hierarchy(report(p)), CFG, 10.0)})
    return w


def test_run_phase_against_the_idle_window_before_it():
    r = ce.run_phase(wins())
    assert len(r) == 1 and r[0]["idle_window"] == "4_acc_config", r
    by = {x["group"]: x for x in r[0]["groups"]}
    assert abs(by["str"]["idle_pj_cycle"] - 150.0) < 1e-9 and abs(by["str"]["above_idle_nj"]) < 1e-9, by["str"]
    assert abs(by["xbar"]["above_idle_nj"] - (50.0 - 3.0) * 185 / 1e3) < 1e-9, by["xbar"]
    assert abs(by["banks"]["run_nj"] - 80.0 * 185 / 1e3) < 1e-9


def test_no_idle_window_gives_no_above_idle():
    r = ce.run_phase(wins()[1:])
    assert r[0]["idle_window"] is None and all(x["above_idle_nj"] is None for x in r[0]["groups"])
    cost = {"parts": {k: {"energy": 1.0} for k in ce.PARTS}}
    h = ce.hwcost_rows(cost, r, CFG)
    assert h["above_idle_nj"] is None and all(x["above_idle_share_pct"] is None for x in h["parts"])


def test_hwcost_shares_are_each_sides_own():
    cost = {"parts": {"datapath": {"energy": 20.0}, "control": {"energy": 0.0}, "streamers": {"energy": 30.0},
                      "crossbar": {"energy": 10.0}, "memory": {"energy": 40.0}}}
    h = ce.hwcost_rows(cost, ce.run_phase(wins()), CFG)
    assert abs(h["hwcost_nj"] - 100.0) < 1e-9 and h["parts"][4]["hwcost_share_pct"] == 40.0
    assert abs(sum(r["run_share_pct"] for r in h["parts"]) - 100.0) < 1e-9
    run = {r["part"]: r["run_nj"] for r in h["parts"]}
    assert abs(run["memory"] - 14.8) < 1e-9 and run["control"] == 0.0, run


def test_alone_row():
    rows = ce.parse_hierarchy(report(RUN))
    a = ce.alone_row(rows, 185, 10.0, {"point": "done/x", "snax_forge_commit": "abc", "seed": "0", "cycles": "129",
                                       "e_dyn_pj": "181.6", "e_run_pj": "23427.1"})
    assert abs(a["cluster"]["pj_cycle"] - 81.0) < 1e-9 and abs(a["alone"]["nj"] - 23.4271) < 1e-9, a


def test_the_real_groups_file_maps_every_part():
    cfg = json.loads((ROOT / "cluster" / "groups.json").read_text())
    names = {g["name"] for g in cfg["groups"]}
    assert set(cfg["hwcost"]) == set(ce.PARTS) and all(set(v) <= names for v in cfg["hwcost"].values())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
