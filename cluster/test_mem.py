"""cluster/mem.py's list-to-macros step and its tc_sram_impl.sv text (no lc_shell, no simulator).

    pixi run python cluster/test_mem.py

The generated module against tech_cells_generic's tc_sram_impl, cycle by cycle, is cluster/eqv_tb.sv.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

# snax_forge_cluster's list as clustergen --memories writes it (the fields mem.py reads)
LIST = [
    {"byte_enable": True, "byte_width": 8, "description": ["tcdm"], "dual_port": False, "latency": 1, "ports": 1,
     "width": 64, "words": 512},
    {"byte_enable": True, "byte_width": 8, "description": ["icache data (hive 0)"], "dual_port": False, "latency": 1,
     "ports": 1, "width": 256, "words": 128},
    {"byte_enable": False, "byte_width": 8, "description": ["icache tag (hive 0)"], "dual_port": False, "latency": 1,
     "ports": 1, "width": 39, "words": 128},
]


def raises(f, *a):
    try:
        f(*a)
    except ValueError as e:
        return str(e)
    raise AssertionError(f"{f.__name__}{a} did not raise")


def test_macros():
    ms = mem.macros(LIST)
    assert [m["name"] for m in ms] == ["sram_d128_w39", "sram_d128_w256_m8", "sram_d512_w64_m8"]
    assert [m["mask"] for m in ms] == [None, 8, 8]
    assert ms[2]["memories"] == ["tcdm"]


def test_refused():
    assert "2 ports" in raises(mem.macros, [{**LIST[0], "ports": 2}])
    assert "latency 2" in raises(mem.macros, [{**LIST[0], "latency": 2}])
    assert "byte width 9" in raises(mem.macros, [{**LIST[0], "byte_width": 9}])
    assert "not a multiple" in raises(mem.macros, [{**LIST[0], "width": 60}])
    assert "same macro" in raises(mem.macros, [LIST[0], LIST[0]])


def test_text():
    t = mem.impl_text(mem.macros(LIST))
    assert t.count("module tc_sram_impl #(") == 1 and t.rstrip().endswith("endmodule")
    assert "if (NumPorts != 1 || Latency != 1) begin : gen_unsupported" in t
    assert "end else if (NumWords == 512 && DataWidth == 64 && ByteWidth == 8) begin : gen_sram_d512_w64_m8" in t
    assert "end else if (NumWords == 128 && DataWidth == 39) begin : gen_sram_d128_w39" in t
    assert t.count(".be_i    ( be_i[0]    )") == 2          # the two macros with byte enable
    assert t.count(" i_macro (") == 3 and "gen_no_macro" in t
    assert "assign impl_o = '0;" in t


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f()
            print(f"ok {name}")
