"""report/snb_report.py: the measures, the coarse parts on the committed snitch9_cg reports, and a made-up run
joined end to end (no DC, Questa or PT).

    pixi run python report/test_snb_report.py
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import snb_report as sr  # noqa: E402

arc, cb, tree = sr.arc, sr.cb, sr.tree
CFG = json.loads(sr.GROUPS.read_text())
COMMITTED = ROOT / "results" / "snb" / "nangate45"

POWER = """                        Internal             Switching            Leakage              Total
Power Group             Power                Power                Power                Power               (     %)   Attrs
----------------------------------------------------------------------------------------------------------------------------
clock_network           3.770675e-03         4.225871e-04         8.112363e-05         4.274386e-03        ( 3.41%)   i
register                2.393287e-03         3.119723e-04         5.271285e-03         7.976544e-03        ( 6.37%)
combinational           7.032944e-03         1.024089e-02         7.915485e-03         2.518932e-02        (20.12%)
memory                  0.000000e+00         0.000000e+00         0.000000e+00         0.000000e+00        ( 0.00%)
black_box               7.883210e-03         8.165342e-05         7.977507e-02         8.773994e-02        (70.09%)

  Net Switching Power  = 1.105710e-02          ( 8.83%)
  Cell Internal Power  = 2.108012e-02          (16.84%)
  Cell Leakage Power   = 9.304296e-02          (74.33%)
                         -------------------------
Total Power            = 1.251802e-01         (100.00%)
"""
UNITS = "Leakage_power_unit          : 1e-09 Watt\nUser Specified Power Unit   : 1 Watt\n"


def close(a: float, b: float, rel: float = 1e-3) -> bool:
    return abs(a - b) <= rel * abs(b)


def test_eta_a():
    # the plan's worked example (forge's dot_3 at W = 16: 4096 op, 185 cycles, 1.173 mm²) and dot on snitch9_cg
    assert close(sr.eta_a(4096, 185, 1.173e6), 1.8875)
    assert close(sr.eta_a(4096, 11944, 1185665.09), 0.028925)
    assert close(sr.eta_e(4096, 2048.0), 2.0)


def test_rounded():
    # the last digits of a sum differ between Python builds; e11.json keeps six significant digits
    assert sr.rounded({"a": [105358.75439999995, 1.23456789e-5], "b": 3, "c": "x"}) == \
        {"a": [105359.0, 1.23457e-5], "b": 3, "c": "x"}
    assert sr.rounded(105358.75439999993) == sr.rounded(105358.75439999995)


def test_coarse():
    areas = {g["name"]: 1.0 for g in CFG["groups"]}
    p = sr.coarse(areas)
    assert p == {"memory": 2.0, "interconnect": 1.0, "cores": 4.0, "rest": 4.0}
    assert sum(p.values()) + len(sr.NONE_HERE) == len(areas)      # every group once, the accelerator's in none
    try:
        sr.coarse({**areas, "new_group": 1.0})
    except ValueError as e:
        assert "new_group" in str(e)
    else:
        raise AssertionError("an unplaced group passed")


def test_groups_interconnect_rules():
    # the logarithmic interconnect (these clusters) and the sparse one (forge's) both go to tcdm_interconnect
    def group(path: str) -> str:
        rows = [{"path": "", "total": 1.0, "design": "top"}, {"path": "i_cluster", "total": 1.0, "design": "c"},
                {"path": path, "total": 1.0, "design": "x"}]
        return cb.assign(rows, CFG)[path]
    assert group("i_cluster/gen_no_snax_tcdm_interconnect.i_tcdm_interconnect") == "tcdm_interconnect"
    assert group("i_cluster/gen_yes_snax_tcdm_interconnect.i_x/sparse_interconnect_i") == "tcdm_interconnect"


def test_committed_snitch9():
    z = COMMITTED / "reports" / "snitch9_cg.zip"
    a = sr.config_area(tree.parse(arc.read_text(z, "area_hierarchy.rpt", errors="replace")), CFG)
    assert round(a["groups_um2"]["tcdm_interconnect"]) == 54565 and round(a["total_um2"]) == 1185665
    assert a["sum_check"]["ok"] and a["accelerator_groups"]["ok"]
    assert {k: round(v) for k, v in a["parts_um2"].items()} == {
        "memory": 486391, "interconnect": 54565, "cores": 398964, "rest": 245744}
    assert round(a["groups_um2"]["acc_interface"]) == 14358         # the cores' SNAX CSR translators, in rest
    row = next(r for r in sr.read_csv(COMMITTED / "synth_dc.csv") if r["point"] == "snitch9_cg")
    assert abs(a["groups_um2"]["tcdm_banks"] + a["groups_um2"]["icache_macros"] - float(row["macro_um2"])) < 1.0


def test_leakage():
    lk = sr.leakage(POWER, UNITS)
    assert close(lk["p_leak_uw"], 93042.96) and close(lk["p_leak_macro_uw"], 79775.07)
    try:
        sr.leakage("no table", UNITS)
    except ValueError:
        pass
    else:
        raise AssertionError("no leakage line passed")


def test_report_end_to_end():
    # runs.csv, power_pt.csv and a power report zip made up, the committed DC reports copied in
    with tempfile.TemporaryDirectory() as d:
        res = Path(d)
        shutil.copytree(COMMITTED / "reports", res / "reports")
        shutil.copy(COMMITTED / "synth_dc.csv", res / "synth_dc.csv")
        with (res / "runs.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["run", "config", "kernel", "type", "sizes", "workers", "n_op",
                                               "rtl_status", "rtl_dma_in", "rtl_run", "rtl_dma_out", "gls_run"])
            w.writeheader()
            w.writerow({"run": "snitch9_cg_dot_int64", "config": "snitch9_cg", "kernel": "dot", "type": "int64",
                        "sizes": "N=2048", "workers": 8, "n_op": 4096, "rtl_status": "PASS", "rtl_dma_in": 1200,
                        "rtl_run": 11944, "rtl_dma_out": 64, "gls_run": 11944})
            w.writerow({"run": "snitch9_cg_vsum_int64", "config": "snitch9_cg", "kernel": "vsum", "type": "int64",
                        "sizes": "N=2048", "workers": 8, "n_op": 2047, "rtl_status": "FAIL", "rtl_dma_in": "",
                        "rtl_run": "", "rtl_dma_out": "", "gls_run": ""})
        with (res / "power_pt.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["point", "mark", "kind", "cycles", "p_dyn_uw", "e_win_pj", "e_macro_pj",
                                               "ann_pct", "status"])
            w.writeheader()
            w.writerow({"point": "snitch9_cg_dot_int64", "mark": 2, "kind": "run", "cycles": 11950, "p_dyn_uw": 20000.0,
                        "e_win_pj": 2390000.0, "e_macro_pj": 30.0, "ann_pct": 99.9, "status": "ok"})
        arc.write(res / "power_reports" / "snitch9_cg_dot_int64.zip",
                  {"2_run/power.rpt": POWER.encode(), "2_run/units.rpt": UNITS.encode()})
        sr.results = lambda tech: res          # noqa: E731  the made-up folder in place of results/snb/<tech>
        rep = sr.report("nangate45")
        assert list(rep["configs"]) == ["snitch1_cg", "snitch5_cg", "snitch9_cg"]
        assert all(c["synth_dc"]["ok"] for c in rep["configs"].values())
        assert list(rep["runs"]) == ["snitch9_cg_dot_int64"]          # the failed RTL run is left out
        r = rep["runs"]["snitch9_cg_dot_int64"]
        assert (r["n_op"], r["c_run"], r["c_run_gls"], r["window_cycles"]) == (4096, 11944, 11944, 11950)
        assert close(r["eta_a_gops_mm2"], 0.028925)
        assert close(r["e_run_pj"], 2390000.0) and close(r["eta_e_op_pj"], 4096 / 2390000.0)
        assert close(r["e_run_macro_pj"], 30.0 * 11950)
        assert close(r["e_leak_pj"], 93042.96 * 11950 * 10 / 1000)    # µW x cycles x ns, in pJ
        md = sr.markdown(rep)
        assert "| snitch9_cg | 1,185,665 | 486,391 | 54,565 | 398,964 | 245,744 | yes |" in md
        assert "| snitch9_cg_dot_int64 | 4096 | 11944 | 11944 | 0.0289 | 2390.00 | 0.00171 | 11118.63 |" in md, md


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("report/test_snb_report.py: all passed")
