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
    ok, notes = check.compare(WANT, RUN.format(c=136))
    assert not ok and "beyond its fill 3" in notes[0], notes


def test_no_fill_needs_equal():
    want = "forge counter mult_dot: 132\nforge data: 0 errors (1 words)\n"
    assert check.compare(want, RUN.format(c=132))[0]
    assert not check.compare(want, RUN.format(c=133))[0]


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
    assert check.ram_compare(rtl, gls, srams) == (True, [])


def test_ramcounts_differ():
    rtl = RC.format(p="a", m="sram_d512_w64_m8", r=139, w=139) + RC.format(p="b", m="sram_d512_w64_m8", r=129, w=128)
    srams = {"sram_d512_w64_m8": 2}
    ok, notes = check.ram_compare(rtl, RC.format(p="a", m="sram_d512_w64_m8", r=139, w=139) +
                                  RC.format(p="b", m="sram_d512_w64_m8", r=129, w=129), srams)
    assert not ok and "only in the run [('sram_d512_w64_m8', 129, 129)]" in notes[0], notes
    ok, notes = check.ram_compare(rtl, RC.format(p="a", m="sram_d512_w64_m8", r=139, w=139), srams)
    assert not ok and notes[0].startswith("instances {'sram_d512_w64_m8': 1}"), notes
    ok, notes = check.ram_compare(rtl, "", srams)
    assert not ok and len(notes) == 2, notes


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
