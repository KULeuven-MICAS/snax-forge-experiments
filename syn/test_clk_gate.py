"""X79's clock-gating switch in syn/syn.py and sim/pwr.py, without DC, Questa or PT.

    pixi run clk-gate-test
"""

import csv
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "syn"), str(ROOT / "sim")]
import syn  # noqa: E402
import pwr  # noqa: E402

TECH = {"name": "nangate45", "lib_name": "L", "units": {"time": "1ns", "cap": "1ff"}, "drive_cell": "INV_X4",
        "out_load_ff": 25.0, "max_transition_ns": 0.25, "wire_load": "off"}
RES = {"lib_db": "/x.db", "t_scale": "1", "c_scale": "1"}


def test_tags_and_env() -> None:
    syn.use_source("forge")
    args = SimpleNamespace(clock=syn.DEFAULT_CLOCK, cores=16, sdf=False)
    try:
        syn.use_clk_gate(False)
        assert syn.point_tag("done/dot/forge3_w8", "10") == "done/dot/forge3_w8"
        assert syn.point_tag("done/dot/forge3_w8", "5") == "done/dot/forge3_w8_c5"
        assert "SYN_CLK_GATE_ENABLE" not in syn.dc_env(TECH, RES, "done/dot/forge3_w8", args)
        syn.use_clk_gate(True)
        assert syn.point_tag("done/dot/forge3_w8", "10") == "done/dot/forge3_w8_cg"
        assert syn.point_tag("done/dot/forge3_w8", "5") == "done/dot/forge3_w8_c5_cg"
        assert syn.run_zip("nangate45", "done/dot/forge3_w8", "10").name == "forge3_w8_cg.zip"
        assert syn.report_zip("nangate45", "done/dot/forge3_w8", "10").name == "forge3_w8_cg.zip"
        assert syn.dc_env(TECH, RES, "done/dot/forge3_w8", args)["SYN_CLK_GATE_ENABLE"] == "1"
    finally:
        syn.use_clk_gate(False)
        syn.use_source("hls")


def test_row_flag_from_tech_json() -> None:
    on = json.dumps({"resolved": {"dc_env": {"SYN_CLK_GATE_ENABLE": "1"}}})
    off = json.dumps({"resolved": {"dc_env": {}}})
    assert syn.run_clk_gate(on) == "1" and syn.run_clk_gate(off) == "0" and syn.run_clk_gate(None) == ""
    assert syn.gate_flag({"clk_gate": ""}) == "0" and syn.gate_flag({}) == "0" and syn.gate_flag({"clk_gate": "1"}) == "1"


def test_merge_keeps_gated_and_ungated_apart() -> None:
    cols = ["point", "clock_ns", "clk_gate", "area_um2"]
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "s.csv"
        f.write_text("point,clock_ns,area_um2\na,10,100\nb,10,7\n")          # rows from before X79: no column
        gated = [{"point": "a", "clock_ns": "10", "clk_gate": "1", "area_um2": "90"}]
        syn._merge(f, cols, syn.summary_key, gated, {syn.summary_key(r) for r in gated})
        got = [(r["point"], r["clk_gate"], r["area_um2"]) for r in csv.DictReader(f.open())]
        assert got == [("a", "", "100"), ("a", "1", "90"), ("b", "", "7")], got
        again = [{"point": "a", "clock_ns": "10", "clk_gate": "0", "area_um2": "101"}]  # the ungated rerun
        syn._merge(f, cols, syn.summary_key, again, {syn.summary_key(r) for r in again})
        got = [(r["point"], r["clk_gate"], r["area_um2"]) for r in csv.DictReader(f.open())]
        assert got == [("a", "0", "101"), ("a", "1", "90"), ("b", "", "7")], got


def test_cg_reports_kept_whatever_their_size() -> None:
    old = syn.RUNS, syn.RESULTS
    try:
        with tempfile.TemporaryDirectory(dir=ROOT) as t:      # inside the repo: copy_reports names paths from it
            syn.use_source("forge")
            syn.RUNS, syn.RESULTS = Path(t) / "runs", Path(t) / "results"
            syn.use_clk_gate(True)
            z = syn.run_zip("nangate45", "p", "10")
            big = b"x" * (syn.MAX_REPORT_BYTES + 1)
            syn.arc.write(z, {"reports/clock_gating_ungated.rpt": big, "reports/qor.rpt": big,
                              "reports/clock_gating.rpt": b"summary\n", "tech.json": b"{}"})
            skipped = syn.copy_reports("nangate45", "p", "10")
            names = set(syn.arc.names(syn.report_zip("nangate45", "p", "10")))
            assert "clock_gating_ungated.rpt" in names and "clock_gating.rpt" in names, names
            assert "qor.rpt" not in names and any(s.startswith("qor.rpt") for s in skipped), (names, skipped)
    finally:
        syn.RUNS, syn.RESULTS = old
        syn.use_clk_gate(False)
        syn.use_source("hls")


def test_pwr_names_and_flag() -> None:
    pwr.use_source("forge")
    try:
        pwr.CLK_GATE = False
        assert pwr.syn_zip("nangate45", "done/dot/forge3_w8").name == "forge3_w8.zip"
        assert pwr.power_zip("nangate45", "done/dot/forge3_w8").name == "forge3_w8.zip" and pwr.gate() == "0"
        pwr.CLK_GATE = True
        assert pwr.syn_zip("nangate45", "done/dot/forge3_w8").name == "forge3_w8_cg.zip"
        assert pwr.power_zip("nangate45", "done/dot/forge3_w8").name == "forge3_w8_cg.zip" and pwr.gate() == "1"
        assert "clk_gate" in pwr.columns() and "clk_gate" in pwr.MODULE_COLUMNS and "clk_gate" in pwr.CHAR_COLUMNS
        assert all("clk_gate" in c for c in pwr.STRM_COLUMNS.values())
    finally:
        pwr.CLK_GATE = False
        pwr.use_source("hls")


def test_pwr_merge_keeps_gated_and_ungated_apart() -> None:
    cols = ["point", "clk_gate", "size", "seed", "e_dyn_pj"]
    key = lambda r: (r["point"], syn.gate_flag(r), r["size"], str(r["seed"]))  # noqa: E731  write_results' key
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "p.csv"
        f.write_text("point,size,seed,e_dyn_pj\na,n2048,0,5\n")
        rows = [{"point": "a", "clk_gate": "1", "size": "n2048", "seed": 0, "e_dyn_pj": 3.0}]
        pwr._merge(f, cols, key, rows, {key(r) for r in rows})
        got = [(r["clk_gate"], r["e_dyn_pj"]) for r in csv.DictReader(f.open())]
        assert got == [("", "5"), ("1", "3")], got


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
