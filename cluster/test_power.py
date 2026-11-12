"""cluster/power.py's tests and pwr.vcd_windows' 10 ps timescale (pure Python): pixi run python cluster/test_power.py"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import power  # noqa: E402

pwr = power.pwr

MARKS = [{"mark": 1, "kind": "dma_in", "label": "dma load_A"}, {"mark": 2, "kind": "dma_in", "label": "dma load_B"},
         {"mark": 3, "kind": "run", "label": "run dot"}, {"mark": 4, "kind": "check", "label": "check"}]
LOG = "0 0\n944000 1\n1249000 2\n1540000 3\n1845000 4\n2000000 0\n"


def raises(fn, *a, has: str = "") -> str:
    try:
        fn(*a)
    except (ValueError, pwr.Fail) as e:
        assert has in str(e), (has, str(e))
        return str(e)
    raise AssertionError(f"{fn.__name__} did not fail")


def test_windows_in_order():
    w = power.windows(LOG, MARKS)
    assert [(x["mark"], x["kind"], x["t0_ps"], x["t1_ps"], x["cycles"]) for x in w] == [
        (1, "dma_in", 943750, 1248750, 305), (2, "dma_in", 1248750, 1539750, 291), (3, "run", 1539750, 1844750, 305)]
    assert all(x["cut_t0"] == x["t0_ps"] and x["cut_t1"] == x["t1_ps"] for x in w)


def test_windows_boot_values_and_glitch():
    # X before reset and the boot's 0 are skipped; a value passing through within one time step takes the last
    w = power.windows("0 x\n10000 0\n944000 7\n944000 1\n1249000 2\n1540000 3\n1845000 4\n", MARKS)
    assert [x["mark"] for x in w] == [1, 2, 3]


def test_windows_check_ends_span():
    # after the check's mark the log is not read (a mark again there is no error)
    w = power.windows(LOG + "2100000 1\n2200000 4\n", MARKS)
    assert w[-1]["t1_ps"] == 1844750 and len(w) == 3


def test_windows_missing_repeated_order():
    raises(power.windows, "944000 1\n1249000 3\n1540000 4\n", MARKS, has="mark 2 missing")
    raises(power.windows, "944000 1\n1249000 2\n1300000 1\n1540000 3\n", MARKS, has="mark 1 again")
    raises(power.windows, "944000 2\n1249000 3\n", MARKS, has="before mark 1")
    raises(power.windows, "944000 1\n1249000 2\n1540000 3\n", MARKS, has="ends before the check's mark 4")


def test_windows_non_integer_cycles():
    raises(power.windows, "944000 1\n1249500 2\n1540000 3\n1845000 4\n", MARKS, has="not whole cycles")


def test_against_ref():
    w = power.windows(LOG, MARKS)
    ok, rows = power.against_ref(w, {1: 305, 2: 291, 3: 305})
    assert ok and [r["diff"] for r in rows] == [0, 0, 0]
    ok, rows = power.against_ref(w, {1: 305, 2: 291, 3: 270})
    assert not ok and rows[2]["diff"] == 35


# bin/snitch_cluster.vsim as snax_cluster ac231e42 wrote it for the netlist build (SIM_TYPE=gate_level_sim), PWR1 R1
VSIM_SCRIPT_TEXT = '#!/bin/bash\nbinary=$(realpath $1)\nmkdir -p logs\necho $binary > logs/.rtlbinary\n vsim +permissive -64 -t 1ps +nospecify +notimingchecks -do "log -r /*; run -a" $3 -work /users/micas/rantonio/no_backup/kul_main/snax_cluster/target/snitch_cluster//work-vsim -c -ldflags "-Wl,-rpath,/users/micas/rantonio/no_backup/kul_main/snax_cluster/target/snitch_cluster/work/lib -L/users/micas/rantonio/no_backup/kul_main/snax_cluster/target/snitch_cluster/work/lib -lfesvr -lutil" tb_bin_opt +permissive-off ++$binary ++$2\n'


def test_vsim_command_once():
    do, elf = Path("/w/pwr/pwr.do"), Path("/w/sw/forge_quiet.elf")
    out = power.vsim_command(VSIM_SCRIPT_TEXT, do, elf)
    assert power.OLD_DO not in out and "-do /w/pwr/pwr.do" in out
    assert "binary=/w/sw/forge_quiet.elf" in out and " -batch -work " in out and out.rstrip().endswith("++$binary ++")
    assert "log -r" not in out and "$3" not in out and "$2" not in out
    raises(power.vsim_command, VSIM_SCRIPT_TEXT.replace(power.OLD_DO, ""), do, elf, has="appears 0 times")
    raises(power.vsim_command, VSIM_SCRIPT_TEXT.replace(power.OLD_DO, power.OLD_DO + " " + power.OLD_DO), do, elf,
           has="appears 2 times")


def test_vcd_add_escaped():
    s = "i_cluster.\\gen_core[0].i_snitch_cc .i_snitch"
    assert power.components(s) == ["i_cluster", "\\gen_core[0].i_snitch_cc ", "i_snitch"]
    lines = power.vcd_add_lines([s, "i_cluster.\\gen_core[0].i_snitch_cc ", "i_cluster.i_cut_ext_wide_out"])
    assert lines == ["vcd add {/tb_bin/i_dut/i_snax_forge_cluster/*}",
                     "vcd add {/tb_bin/i_dut/i_snax_forge_cluster/i_cluster/\\gen_core[0].i_snitch_cc /i_snitch/*}",
                     "vcd add {/tb_bin/i_dut/i_snax_forge_cluster/i_cluster/\\gen_core[0].i_snitch_cc /*}",
                     "vcd add {/tb_bin/i_dut/i_snax_forge_cluster/i_cluster/i_cut_ext_wide_out/*}"]
    two = "a.\\gen_x[0].b .c.\\gen_y[1].d "
    assert power.components(two) == ["a", "\\gen_x[0].b ", "c", "\\gen_y[1].d "]


VCD = """$date today $end
$version Questa $end
{ts}
$scope module tb $end
$var wire 1 ! clk $end
$var wire 2 " d [1:0] $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
0!
b00 "
$end
#500
1!
#1000
0!
b01 "
#1500
1!
#2000
0!
#2500
1!
b10 "
#3000
0!
"""


def cut(ts: str, wins, **kw) -> dict[str, str]:
    with tempfile.TemporaryDirectory() as d:
        v = Path(d) / "dut.vcd"
        v.write_text(VCD.replace("{ts}", ts))
        out = {n: Path(d) / f"{n}.vcd" for n, _, _ in wins}
        seen = []
        pwr.vcd_windows(v, wins, out, done=seen.append, **kw)
        assert seen == [n for n, _, _ in sorted(wins, key=lambda w: w[1])], seen
        return {n: f.read_text() for n, f in out.items()}


def test_vcd_10ps_one_and_three_lines():
    wins = [("a", 750, 1750), ("b", 1750, 2750)]
    for ts in ("$timescale 1ps $end", "$timescale\n   1ps\n$end", "$timescale 1 ps $end"):
        got = cut(ts, wins, timescale_10ps=True)
        for n in got:
            assert "$timescale 10ps $end\n" in got[n] and "1ps" not in got[n] and "1 ps" not in got[n], got[n]
        # the cut's times are the VCD's numbers: a's state at #500, its events at #1000 and #1500, its end at #1750
        a = got["a"].split("$enddefinitions $end\n")[1]
        assert a == "#500\n1!\nb00 \"\n#1000\n0!\nb01 \"\n#1500\n1!\n#1750\n", a
        b = got["b"].split("$enddefinitions $end\n")[1]
        assert b.startswith("#1500\n") and "#2000\n" in b and "#2500\n" in b and b.endswith("#2750\n"), b
    plain = cut("$timescale 1ps $end", wins)          # default off: the header as it is
    assert "$timescale 1ps $end" in plain["a"] and "10ps" not in plain["a"]


def test_vcd_10ps_refuses_other_units():
    raises(lambda: cut("$timescale 1ns $end", [("a", 750, 1750)], timescale_10ps=True), has="is not 1ps")
    raises(lambda: cut("$timescale 10ps $end", [("a", 750, 1750)], timescale_10ps=True), has="is not 1ps")
    cut("$timescale 1ns $end", [("a", 750, 1750)])       # without the option any unit is cut as before


def test_vcd_boundary_event_refused():
    raises(lambda: cut("$timescale 1ps $end", [("a", 1000, 2000)], timescale_10ps=True), has="boundary")


def test_program_output():
    run = "# vsim -c\n[fesvr] Wrote 36 bytes\n# ** Info: [SUCCESS] Program finished successfully\n\n"
    assert power.program_output(run) == []
    assert power.program_output(run + "forge cycles: 810\n") == ["forge cycles: 810"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
