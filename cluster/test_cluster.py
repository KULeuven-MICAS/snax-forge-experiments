"""cluster/cluster.py's helpers that need no tool (pure Python): pixi run python cluster/test_cluster.py"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cluster as cl  # noqa: E402

POINTS = json.loads((Path(__file__).resolve().parent / "points.json").read_text())["points"]


def test_bundle_command_takes_sets_alone():
    dot = next(p for p in POINTS if p["point"] == "dot3_w8_cg")
    cmd = cl.bundle_command(dot)
    assert cmd.endswith("dot_v3.json --set W=8 --set N=2048"), cmd      # as before: the bundle is reused
    mvt = next(p for p in POINTS if p["point"] == "mvt_column_cg")
    cmd = cl.bundle_command(mvt)
    assert "W=" not in cmd and cmd.endswith("--set design.data=full --set design.schedule=sequential"), cmd
    fl = cl.flow_command(mvt)
    assert " flow " in fl and fl.endswith("--set design.schedule=sequential --energy"), fl
    assert "--platform platforms/snax_forge.json" in fl, fl


def test_points_adopt_only_known_twins():
    names = {p["point"] for p in POINTS}
    twins = {p["point"]: p["netlist_of"] for p in POINTS if "netlist_of" in p}
    assert twins == {"mvt_padded_w8_cg": "mvt_contiguous_w8_cg", "mvt_column_pipeline_cg": "mvt_column_cg",
                     "bicg_two_pass_pipeline_cg": "bicg_two_pass_cg",
                     "bicg_pipeline_contiguous_w8_cg": "bicg_sequential_contiguous_w8_cg"}, twins
    assert all(t in names for t in twins.values())
    order = [p["point"] for p in POINTS]
    assert all(order.index(t) < order.index(a) for a, t in twins.items())      # the twin runs first
    assert all(p["sets"].count("design.data=full") == 1 for p in POINTS if not p["point"].startswith("dot3"))


def test_flow_out_line():
    text = "flow mvt_v5_ab12 (mvt_v5: M=64; ...) on snax_forge -> out/flow/mvt_v5_ab12/\n  sandbox ..."
    assert cl.FLOW_OUT.search(text).group(1) == "out/flow/mvt_v5_ab12"


def test_adoption():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        old = cl.RTL_ZIPS, cl.RUN_ZIPS
        cl.RTL_ZIPS, cl.RUN_ZIPS = d / "rtl", d / "runs"
        try:
            hw = {"bundle/snax_forge.hjson": b"h", "bundle/rtl/a.sv": b"a"}
            cl.arc.write(cl.RTL_ZIPS / "a.zip", {**hw, "sw/forge.elf": b"1", "bundle/bundle.json": b"A"})
            cl.arc.write(cl.RTL_ZIPS / "b.zip", {**hw, "sw/forge.elf": b"2", "bundle/bundle.json": b"B"})
            cl.arc.write(cl.RTL_ZIPS / "c.zip", {**hw, "bundle/rtl/a.sv": b"other"})
            assert cl.adoption_diff("a", "b") == []
            assert cl.adoption_diff("a", "c") == ["bundle/rtl/a.sv"]
            assert cl.adoption_diff("a", "x")[0].startswith("no ")
            cl.arc.write(cl.RUN_ZIPS / "b.zip", {"rtl/check.json": b"{}"})
            assert cl.netlist_point("b") == "b"
            cl.arc.write(cl.RUN_ZIPS / "b.zip", {"rtl/check.json": b"{}",
                                                 cl.ADOPTED: json.dumps({"netlist_of": "a"}).encode()})
            assert cl.netlist_point("b") == "a" and cl.netlist_point("none") == "none"
        finally:
            cl.RTL_ZIPS, cl.RUN_ZIPS = old


def test_quiet_windows():
    with tempfile.TemporaryDirectory() as d:
        work = Path(d)
        (work / "gvsoc").mkdir()
        ge = {"windows": [{"mark": 0, "kind": "boot", "cycles": 4000}, {"mark": 1, "kind": "dma_in", "cycles": 300},
                          {"mark": 2, "kind": "run", "cycles": 200}, {"mark": 3, "kind": "check", "cycles": 900}]}
        (work / "gvsoc" / "energy.json").write_text(json.dumps(ge))
        qr = {"check_mark": 3, "windows": [{"mark": 1, "kind": "dma_in", "cycles": 310},
                                           {"mark": 2, "kind": "run", "cycles": 230}], "span_cycles": 540}
        out = cl.quiet_windows(qr, {}, work, 545)
        assert out["gate"] is False and out["worst"] == "WARNING" and out["gvsoc_span"] == 500, out
        assert [r["verdict"] for r in out["rows"]] == ["OK", "WARNING"], out["rows"]
        assert out["quiet_span"] == 540 and out["default_cycles"] == 545, out
        none = cl.quiet_windows({"check_mark": 3}, {}, work, 545)
        assert none["status"] == "NONE" and none["gate"] is False, none


def test_ge_run_alone():
    """cluster ge: flow --energy's folder read from its first line, its energy.json into ge/<point>.json, the quiet
    ELF against the bundle's provenance, the windows listed; a flow with no energy.json is a FAIL."""
    mvt = next(p for p in POINTS if p["point"] == "mvt_column_cg")
    ej = {"windows": [{"mark": 0, "kind": "boot", "label": "boot", "cycles": 4000},
                      {"mark": 1, "kind": "run", "label": "program window", "cycles": 1028}]}

    class FakeSteps:
        def __init__(self, work: Path, energy: bool):
            self.work, self.energy, self.calls = work, energy, []

        def image(self, name, which, cwd, cmd, timeout):
            self.calls.append((name, which, cmd))
            run = cl.FORGE / "out" / "flow" / "mvt_v5_ab12"
            (run / "sw").mkdir(parents=True, exist_ok=True)
            (run / "sw" / "forge_quiet.elf").write_bytes(b"quiet")
            if self.energy:
                (run / "energy").mkdir(exist_ok=True)
                (run / "energy" / "energy.json").write_text(json.dumps(ej))
            log = self.work / "flow.log"
            log.write_text("flow mvt_v5_ab12 (mvt_v5: M=64) on snax_forge -> out/flow/mvt_v5_ab12/\n")
            return log

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        old = cl.FORGE, cl.GE_DIR, cl.RTL_ZIPS, cl.ROOT
        cl.FORGE, cl.GE_DIR, cl.RTL_ZIPS, cl.ROOT = d / "forge", d / "ge", d / "rtl", d
        try:
            (cl.FORGE / "recipes" / "polybench").mkdir(parents=True)
            (cl.FORGE / "recipes" / "polybench" / "mvt_v5.json").write_text("{}")
            sha = cl.hashlib.sha256(b"quiet").hexdigest()
            cl.arc.write(cl.RTL_ZIPS / "mvt_column_cg.zip",
                         {"provenance.json": json.dumps({"quiet_elf_sha256": sha}).encode()})
            work = d / "work"
            work.mkdir()
            st = FakeSteps(work, True)
            out = cl.ge_run(work, mvt, st)
            assert out["status"] == "PASS" and out["same_quiet_elf"] is True, out
            assert out["gate"] is False and out["folder"] == "out/flow/mvt_v5_ab12", out
            assert json.loads((cl.GE_DIR / "mvt_column_cg.json").read_text()) == ej
            assert [w["kind"] for w in out["windows"]] == ["boot", "run"] and out["windows"][1]["cycles"] == 1028
            assert st.calls == [("gvsoc", "snax_forge", cl.flow_command(mvt))], st.calls
            (cl.GE_DIR / "mvt_column_cg.json").unlink()
            shutil_rm = cl.shutil.rmtree
            shutil_rm(cl.FORGE / "out")
            cl.arc.write(cl.RTL_ZIPS / "mvt_column_cg.zip",
                         {"provenance.json": json.dumps({"quiet_elf_sha256": "other"}).encode()})
            out = cl.ge_run(work, mvt, FakeSteps(work, True))
            assert out["status"] == "PASS" and out["same_quiet_elf"] is False, out
            shutil_rm(cl.FORGE / "out")
            (cl.GE_DIR / "mvt_column_cg.json").unlink()
            out = cl.ge_run(work, mvt, FakeSteps(work, False))
            assert out["status"] == "FAIL" and "energy.json" in out["why"] and "windows" not in out, out
            assert not (cl.GE_DIR / "mvt_column_cg.json").exists()
        finally:
            cl.FORGE, cl.GE_DIR, cl.RTL_ZIPS, cl.ROOT = old


def test_rtl_gates():
    c = {"d123_macro": {"status": "FAIL", "gate": False}, "quiet_windows": {"status": "INVESTIGATE", "gate": False},
         "gvsoc": {"status": "FAIL", "gate": False}, "data": {"status": "PASS"}, "quiet": {"status": "PASS"}}
    assert cl.gates_failed(c) == []
    assert cl.gates_failed({**c, "quiet": {"status": "FAIL"}}) == ["quiet"]
    assert cl.gates_failed({**c, "data": {"status": "FAIL"}}) == ["data"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
