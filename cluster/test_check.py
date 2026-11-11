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
    assert check.success(text) and not check.success("forge cycles: 1\n")


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
