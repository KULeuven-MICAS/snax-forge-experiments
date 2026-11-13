"""cluster/check.py's tests (pure Python): pixi run python cluster/test_check.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check  # noqa: E402

WANT = "forge counter mult_dot: 132\nforge data: 0 errors (1 words)\nforge fill mult_dot: 3\n"
RUN = ("[tc_sram_impl] tb_bin.i_dut.a.gen_sram_d512_w64_m8: sram_d512_w64_m8\n"
       "[tc_sram_impl] tb_bin.i_dut.b.gen_sram_d512_w64_m8: sram_d512_w64_m8\n"
       "[tc_sram_impl] tb_bin.i_dut.c.gen_sram_d128_w39: sram_d128_w39\n"
       "# forge counter mult_dot: {c}\n# forge data: 0 errors (1 words)\n# forge cycles: 828\n"
       "[SUCCESS] Program finished successfully\n")


def test_pass_equal():
    ok, notes = check.compare(WANT, RUN.format(c=132))
    assert ok and notes == [], notes


def test_within_fill():
    ok, notes = check.compare(WANT, RUN.format(c=135))
    assert ok and notes == ["mult_dot: counter 135 against 132, within its fill 3"], notes
    ok, _ = check.compare(WANT, RUN.format(c=129))
    assert ok


def test_beyond_fill():
    # D123 as amended: e = (|c - 132| - 3) / 132; NEAR up to 10 %, WARNING up to 15 %, FAIL beyond
    ok, notes = check.compare(WANT, RUN.format(c=136))
    assert ok and notes == ["mult_dot: counter 136 against 132, 1 beyond its fill 3 (0.8 %, NEAR)"], notes
    ok, notes = check.compare(WANT, RUN.format(c=112))           # 17 beyond: 12.9 %
    assert ok and notes[0].endswith("(12.9 %, WARNING)"), notes
    ok, notes = check.compare(WANT, RUN.format(c=154))           # 19 beyond: 14.4 %
    assert ok and "WARNING" in notes[0], notes
    ok, notes = check.compare(WANT, RUN.format(c=155))           # 20 beyond: 15.2 %
    assert not ok and notes[0].endswith("(15.2 %, FAIL)"), notes


def test_beyond_fill_dot3_w32():
    # PWR2 R1: at W = 32 the streamers' 8-beat head start hides more than the fill (bank bound, 2 cycles a beat)
    want = "forge counter mult_dot: 131\nforge data: 0 errors (1 words)\nforge fill mult_dot: 3\n"
    ok, notes = check.compare(want, RUN.format(c=118).replace("forge cycles: 828", "forge cycles: 820"))
    assert ok and notes == ["mult_dot: counter 118 against 131, 10 beyond its fill 3 (7.6 %, NEAR)"], notes


def test_no_fill_needs_equal():
    # no fill line: fill 0, so any difference is beyond it (NEAR, WARNING or FAIL by its share, D123)
    want = "forge counter mult_dot: 132\nforge data: 0 errors (1 words)\n"
    assert check.compare(want, RUN.format(c=132)) == (True, [])
    ok, notes = check.compare(want, RUN.format(c=133))
    assert ok and notes == ["mult_dot: counter 133 against 132, 1 beyond its fill 0 (0.8 %, NEAR)"], notes
    assert not check.compare(want, RUN.format(c=152))[0]


def test_data_differs():
    ok, notes = check.compare(WANT, RUN.format(c=132).replace("0 errors", "3 errors"))
    assert not ok and notes[0].startswith("data:"), notes


def test_names_and_order():
    want = "forge counter a: 10\nforge counter b: 20\nforge data: 0 errors (2 words)\nforge fill a: 1\nforge fill b: 1\n"
    got = "forge counter b: 20\nforge counter a: 10\nforge data: 0 errors (2 words)\n"
    assert not check.compare(want, got)[0]
    got = "forge counter a: 10\nforge data: 0 errors (2 words)\n"
    assert not check.compare(want, got)[0]
    got = "forge counter a: 11\nforge counter b: 19\nforge data: 0 errors (2 words)\n"
    assert check.compare(want, got)[0]


def test_no_data_in_run():
    assert not check.compare(WANT, "forge counter mult_dot: 132\n")[0]


def test_cycles_srams_success():
    text = RUN.format(c=132)
    assert check.parse(text)["cycles"] == 828
    assert check.sram_counts(text) == {"sram_d128_w39": 1, "sram_d512_w64_m8": 2}
    assert check.sram_lines(text) == 3
    assert check.success(text) and not check.success("forge cycles: 1\n")


def test_print_split_by_program_output():
    # R2's macro run: the program's lines landed inside one [tc_sram_impl] print (separate buffers)
    text = ("# [tc_sram_impl] tb_bin.x.gen_banks[27].m.gen_sram_d512_w64_m8: sram_d512_w64_m8\n"
            "# [tc_sram_impl] tb_bin.x.i_snitch_data_memforge cycles: 828\n"
            "forge data: 0 errors (1 words)\nforge counter mult_dot: 132\nforge errors: 0\n"
            ".gen_banks[28].m.gen_sram_d512_w64_m8: sram_d512_w64_m8\n"
            "# RAMCOUNT tb_bin.x.gen_sram_d512_w64_m8.i_macro sram_d512_w64_m8 reads 1 writes 1\n")
    assert check.sram_lines(text) == 2
    assert check.sram_counts(text) == {"sram_d512_w64_m8": 2}
    assert check.parse(text)["cycles"] == 828
    assert check.compare(WANT, text)[0]


RC = "# RAMCOUNT tb_bin.{p}.gen_{m}.i_macro {m} reads {r} writes {w}\n"


def test_ramcounts_without_paths():
    rtl = RC.format(p="i_dut.a", m="sram_d512_w64_m8", r=139, w=139) + \
        RC.format(p="i_dut.b", m="sram_d128_w39", r=487, w=237)
    gls = "x" + RC.format(p="i_dut.i_cluster_b", m="sram_d128_w39", r=487, w=237) + \
        RC.format(p="i_dut.i_cluster_a_0", m="sram_d512_w64_m8", r=139, w=139)
    assert check.ramcounts(rtl) == [("sram_d128_w39", 487, 237), ("sram_d512_w64_m8", 139, 139)]
    srams = {"sram_d512_w64_m8": 1, "sram_d128_w39": 1}
    assert check.ram_compare(rtl, gls, srams) == (True, [], [])


# R4's netlist run: the paths hold escaped identifiers, each ending in a space
GLS_LINES = (
    "# RAMCOUNT tb_bin.i_dut.i_snax_forge_cluster.i_cluster.i_snitch_data_mem.\\gen_banks[0].i_data_mem "
    ".\\gen_sram_d512_w64_m8.i_macro  sram_d512_w64_m8 reads 139 writes 139\n"
    "# RAMCOUNT tb_bin.i_dut.i_snax_forge_cluster.i_cluster.\\gen_hive[0].i_snitch_hive .i_snitch_icache.i_lookup."
    "i_snitch_icache_tag.\\g_cache_tag_sets[0].i_tag .\\gen_sram_d128_w39.i_macro  sram_d128_w39 reads 487 writes 238\n")
RTL_LINES = (
    "# RAMCOUNT tb_bin.i_dut.i_snax_forge_cluster.i_cluster.i_snitch_data_mem.gen_banks[0].i_data_mem."
    "gen_sram_d512_w64_m8.i_macro sram_d512_w64_m8 reads 139 writes 139\n"
    "# RAMCOUNT tb_bin.i_dut.i_snax_forge_cluster.i_cluster.gen_hive[0].i_snitch_hive.i_snitch_icache.i_lookup."
    "i_snitch_icache_tag.g_cache_tag_sets[0].i_tag.gen_sram_d128_w39.i_macro sram_d128_w39 reads 487 writes 237\n")
SRAMS1 = {"sram_d512_w64_m8": 1, "sram_d128_w39": 1}


def test_ramcounts_escaped_paths():
    assert check.ramcounts(GLS_LINES) == [("sram_d128_w39", 487, 238), ("sram_d512_w64_m8", 139, 139)]
    assert check.ramcounts(RTL_LINES) == [("sram_d128_w39", 487, 237), ("sram_d512_w64_m8", 139, 139)]


def test_ram_one_extra_write_allowed():
    ok, notes, extra = check.ram_compare(RTL_LINES, GLS_LINES, SRAMS1)
    assert ok and notes == [], notes
    assert extra == [{"macro": "sram_d128_w39", "reads": 487, "rtl_writes": 237, "gls_writes": 238}]
    assert check.ram_summary(2, ok, extra) == "RAMCOUNT 2: reads equal, writes equal but 1 macros +1 at reset (PITFALLS Q8)"
    assert check.ram_summary(2, True, []) == "RAMCOUNT 2: reads equal, writes equal"


def test_ram_two_extra_writes_fail():
    ok, notes, _ = check.ram_compare(RTL_LINES, GLS_LINES.replace("writes 238", "writes 239"), SRAMS1)
    assert not ok and "unmatched in the run [('sram_d128_w39', 487, 239)]" in notes[0], notes


def test_ram_fewer_writes_fail():
    ok, notes, _ = check.ram_compare(RTL_LINES, GLS_LINES.replace("writes 238", "writes 236"), SRAMS1)
    assert not ok, notes


def test_ram_read_difference_fail():
    ok, notes, _ = check.ram_compare(RTL_LINES, GLS_LINES.replace("reads 139", "reads 140"), SRAMS1)
    assert not ok and "('sram_d512_w64_m8', 140, 139)" in notes[0], notes


def test_ram_missing_or_extra_macro_fail():
    one = GLS_LINES.splitlines(keepends=True)
    ok, notes, _ = check.ram_compare(RTL_LINES, one[1], SRAMS1)            # an instance missing
    assert not ok and notes[0].startswith("instances {'sram_d128_w39': 1}"), notes
    ok, notes, _ = check.ram_compare(RTL_LINES, GLS_LINES + one[0], SRAMS1)  # an instance added
    assert not ok and len(notes) == 2, notes
    ok, notes, _ = check.ram_compare(RTL_LINES, "", SRAMS1)
    assert not ok and len(notes) == 2, notes


def test_ram_pairing_without_paths():
    # two instances of one macro, the netlist's +1 on the one with fewer writes: matched by counts, not order
    rtl = "RAMCOUNT a m reads 5 writes 3\nRAMCOUNT b m reads 5 writes 4\n"
    gls = "RAMCOUNT x m reads 5 writes 4\nRAMCOUNT y m reads 5 writes 4\n"
    ok, notes, extra = check.ram_compare(rtl, gls, {"m": 2})
    assert ok and extra == [{"macro": "m", "reads": 5, "rtl_writes": 3, "gls_writes": 4}], (notes, extra)


def test_ram_pairing_both_plus_one():
    # PWR2 R1 dot3_w4: two I-cache sets at 236 and 235 writes, the netlist's each +1 (237, 236); equal-first
    # matching paired 236 with 236 and left 237 against 235
    rtl = "RAMCOUNT a m reads 473 writes 236\nRAMCOUNT b m reads 473 writes 235\n"
    gls = "RAMCOUNT x m reads 473 writes 237\nRAMCOUNT y m reads 473 writes 236\n"
    ok, notes, extra = check.ram_compare(rtl, gls, {"m": 2})
    assert ok and notes == [], notes
    assert extra == [{"macro": "m", "reads": 473, "rtl_writes": 235, "gls_writes": 236},
                     {"macro": "m", "reads": 473, "rtl_writes": 236, "gls_writes": 237}], extra
    ok, notes, _ = check.ram_compare(rtl, gls.replace("writes 237", "writes 238"), {"m": 2})
    assert not ok and notes, notes


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
