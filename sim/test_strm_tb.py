#!/usr/bin/env python3
"""sim/test_strm_tb.py - the streamer and interconnect TBs of sim/sources/strm.py in their three modes.

  pixi run python sim/test_strm_tb.py

Always: the TB text per mode (grant has no mode code, idle and refused their own checks). With verilator on PATH
(as strm/test_xbar_mix.py's lint), each TB also runs on a small behavioural model of the reader or the interconnect
written here (not snax_cluster's RTL): every check passes on a correct model, and a model that drops a held request's
address, or grants two requests on one bank, fails them. Standard library only.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sources import strm as s  # noqa: E402


def reader(c: int, loops: int, mode: str = "grant") -> dict:
    b = s.bounds(loops)
    tb = {"control": {"kind": "strm_reader"}, "point": f"d4_l{loops}_c{c}", "top": "Reader", "source": "streamer",
          "channels": c, "bounds": b, "strides": s.strides(b, c), "beats": s.BEATS, "spatial_stride_port": c > 1}
    if mode != "grant":
        tb["mode"] = mode
    return tb


def xbar(n: int, banks: int, ro: int = 0, wo: int = 0, mode: str = "grant") -> dict:
    bb = banks.bit_length() - 1
    tb = {"control": {"kind": "strm_xbar"}, "point": f"i{n}_b{banks}", "top": "Xbar", "source": "xbar",
          "inputs": n, "banks": banks, "bank_bits": bb, "row_bits": s.ADDR_W - bb - 3, "cycles": s.CYCLES,
          "window": s.CYCLES + 1, "ro": ro, "wo": wo}
    tb["ports"] = sorted(s.connected(tb))
    if mode != "grant":
        tb["mode"] = mode
    return tb


# ---------------------------------------------------------------- behavioural models (Verilator only)
def reader_model(tb: dict, bad: str = "") -> str:
    """A reader: channel i requests 8 (n C + i) for n < BEATS while (in flight + queued) < 4, a beat when every
    channel has a word. bad="addr": a held request's address moves on (a refused request dropped)."""
    c, loops, aw = tb["channels"], len(tb["bounds"]), s.ADDR_W
    P = ["clock", "reset", "io_aguCfg_ptr", "io_start", "io_busy", "io_data_ready", "io_data_valid", "io_data_bits"]
    P += ["io_aguCfg_spatialStrides_0"] if tb["spatial_stride_port"] else []
    P += [f"io_aguCfg_temporal{k}_{i}" for k in ("Bounds", "Strides") for i in range(loops)]
    for i in range(c):
        P += [f"io_tcdmReq_{i}_{f}" for f in ("ready", "valid", "bits_addr", "bits_priority")]
        P += [f"io_tcdmRsp_{i}_valid", f"io_tcdmRsp_{i}_bits_data"]
    L = [f"module {tb['top']} (" + ", ".join(P) + ");",
         "  input clock, reset, io_start, io_data_ready;", f"  input [{aw - 1}:0] io_aguCfg_ptr;",
         "  output logic io_busy, io_data_valid;", f"  output logic [{64 * c - 1}:0] io_data_bits;"]
    if tb["spatial_stride_port"]:
        L.append(f"  input [{aw - 1}:0] io_aguCfg_spatialStrides_0;")
    L += [f"  input [{aw - 1}:0] io_aguCfg_temporal{k}_{i};" for k in ("Bounds", "Strides") for i in range(loops)]
    for i in range(c):
        L += [f"  input io_tcdmReq_{i}_ready, io_tcdmRsp_{i}_valid; input [63:0] io_tcdmRsp_{i}_bits_data;",
              f"  output logic io_tcdmReq_{i}_valid, io_tcdmReq_{i}_bits_priority;",
              f"  output logic [{aw - 1}:0] io_tcdmReq_{i}_bits_addr;"]
    L += [f"  localparam int C = {c}, BEATS = {tb['beats']};",
          "  int issued [C], inflight [C], beats; logic [63:0] fifo [C][$];",
          "  logic [C-1:0] rdy, rv, vld; logic [63:0] rd [C];"]
    for i in range(c):
        L += [f"  assign rdy[{i}] = io_tcdmReq_{i}_ready; assign rv[{i}] = io_tcdmRsp_{i}_valid;",
              f"  assign rd[{i}] = io_tcdmRsp_{i}_bits_data; assign io_tcdmReq_{i}_valid = vld[{i}];",
              f"  assign io_tcdmReq_{i}_bits_priority = 1'b0;",
              f"  assign io_tcdmReq_{i}_bits_addr = {aw}'(8 * (issued[{i}] * C + {i}))"
              + (" + (bad_step ? 8 : 0);" if bad == "addr" else ";")]
    L += ["  int bad_step = 0;",
          "  always_comb for (int i = 0; i < C; i++)",
          "    vld[i] = io_busy && issued[i] < BEATS && inflight[i] + fifo[i].size() < 4;",
          "  always_comb begin",
          "    io_data_valid = io_busy;",
          "    for (int i = 0; i < C; i++) if (fifo[i].size() == 0) io_data_valid = 0;",
          "    for (int i = 0; i < C; i++) io_data_bits[64*i +: 64] = fifo[i].size() ? fifo[i][0] : 64'd0;",
          "  end",
          "  always @(posedge clock or posedge reset)",
          "    if (reset) begin",
          "      io_busy <= 0; beats <= 0;",
          "      for (int i = 0; i < C; i++) begin issued[i] <= 0; inflight[i] <= 0; fifo[i].delete(); end",
          "    end else begin",
          "      if (io_start && !io_busy) io_busy <= 1;",
          "      for (int i = 0; i < C; i++) begin",
          "        if (vld[i] && !rdy[i]) bad_step <= 1; else bad_step <= 0;",
          "        if (rv[i]) fifo[i].push_back(rd[i]);",
          "        inflight[i] <= inflight[i] + int'(vld[i] && rdy[i]) - int'(rv[i]);",
          "        if (vld[i] && rdy[i]) issued[i] <= issued[i] + 1;",
          "      end",
          "      if (io_data_valid && io_data_ready) begin",
          "        for (int i = 0; i < C; i++) void'(fifo[i].pop_front());",
          "        beats <= beats + 1;",
          "        if (beats + 1 == BEATS) io_busy <= 0;",
          "      end",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def xbar_model(tb: dict, bad: str = "") -> str:
    """An interconnect: per bank a round-robin grant among the valid inputs on it, the winner forwarded, a read
    answered the next cycle from the bank's data. bad="double": a bank with two requests grants both."""
    n, banks, bb, maw = tb["inputs"], tb["banks"], tb["bank_bits"], tb["row_bits"]
    P = ["clock", "reset"]
    for i in range(n):
        P += [f"io_tcdmReqs_{i}_{f}" for f in ("ready", "valid", "bits_addr", "bits_write", "bits_amo", "bits_data",
                                               "bits_strb", "bits_priority", "bits_user")]
        P += [f"io_tcdmRsps_{i}_{f}" for f in ("ready", "valid", "bits_data")]
    for b in range(banks):
        P += [f"io_memReqs_{b}_{f}" for f in ("ready", "valid", "bits_addr", "bits_write", "bits_amo", "bits_data",
                                              "bits_strb", "bits_priority", "bits_user")]
        P += [f"io_memRsps_{b}_{f}" for f in ("ready", "valid", "bits_data")]
    L = [f"module {tb['top']} (" + ", ".join(P) + ");", "  input clock, reset;",
         f"  localparam int N = {n}, B = {banks}, BB = {bb}, MAW = {maw};",
         f"  logic [N-1:0] qv, qw, qr; logic [{s.ADDR_W - 1}:0] qa [N]; logic [63:0] qd [N];",
         "  logic [B-1:0] mv, mw; logic [MAW-1:0] ma [B]; logic [63:0] md [B], mr [B]; logic [7:0] ms [B];",
         "  logic [N-1:0] pv; int sel [N]; int rr [B];"]
    for i in range(n):
        q, p = f"io_tcdmReqs_{i}_", f"io_tcdmRsps_{i}_"
        L += [f"  input {q}valid, {q}bits_write, {q}bits_priority, {p}ready; input [{s.ADDR_W - 1}:0] {q}bits_addr;",
              f"  input [3:0] {q}bits_amo; input [63:0] {q}bits_data; input [7:0] {q}bits_strb;"
              f" input [2:0] {q}bits_user;",
              f"  output logic {q}ready, {p}valid; output logic [63:0] {p}bits_data;",
              f"  assign qv[{i}] = {q}valid; assign qw[{i}] = {q}bits_write; assign qa[{i}] = {q}bits_addr;",
              f"  assign qd[{i}] = {q}bits_data; assign {q}ready = qr[{i}]; assign {p}valid = pv[{i}];",
              f"  assign {p}bits_data = mr[sel[{i}]];"]
    for b in range(banks):
        q, p = f"io_memReqs_{b}_", f"io_memRsps_{b}_"
        L += [f"  input {q}ready, {p}valid; input [63:0] {p}bits_data; output logic {p}ready;",
              f"  assign {p}ready = 1'b1;",
              f"  output logic {q}valid, {q}bits_write, {q}bits_priority; output logic [MAW-1:0] {q}bits_addr;",
              f"  output logic [3:0] {q}bits_amo; output logic [63:0] {q}bits_data; output logic [7:0] {q}bits_strb;"
              f" output logic [2:0] {q}bits_user;",
              f"  assign {q}valid = mv[{b}]; assign {q}bits_write = mw[{b}]; assign {q}bits_addr = ma[{b}];",
              f"  assign {q}bits_data = md[{b}]; assign {q}bits_strb = ms[{b}]; assign {q}bits_priority = 0;",
              f"  assign {q}bits_amo = 0; assign {q}bits_user = 0; assign mr[{b}] = {p}bits_data;"]
    L += ["  always_comb begin",
          "    qr = '0; mv = '0; mw = '0;",
          "    for (int b = 0; b < B; b++) begin",
          "      int w; w = -1; ma[b] = '0; md[b] = '0; ms[b] = '0;",
          "      for (int j = 0; j < N; j++) begin",
          "        int i; i = (rr[b] + j) % N;",
          "        if (qv[i] && int'(qa[i][3 +: BB]) == b) begin",
          "          if (w < 0) begin w = i; qr[i] = 1; end" + (" else qr[i] = 1;" if bad == "double" else ""),
          "        end",
          "      end",
          "      if (w >= 0) begin mv[b] = 1; mw[b] = qw[w]; ma[b] = qa[w][3 + BB +: MAW]; md[b] = qd[w];"
          " ms[b] = 8'hff; end",
          "    end",
          "  end",
          "  always @(posedge clock)",
          "    if (reset) begin pv <= '0; for (int b = 0; b < B; b++) rr[b] <= 0; for (int i = 0; i < N; i++)"
          " sel[i] <= 0; end",
          "    else begin",
          "      for (int i = 0; i < N; i++) begin",
          "        pv[i] <= qv[i] && qr[i] && !qw[i];",
          "        if (qv[i] && qr[i]) begin sel[i] <= int'(qa[i][3 +: BB]); rr[qa[i][3 +: BB]] <= (i + 1) % N; end",
          "      end",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def run(tb: dict, model: str) -> str:
    """The TB on the model in Verilator: its TB lines."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "tb.sv").write_text(s.tb_top(tb, []))
        (d / "dut.sv").write_text(model)
        b = subprocess.run(["verilator", "--binary", "--timing", "-Wno-fatal", "-Wno-lint", "-Wno-style",
                            "--top-module", "tb", "-Mdir", str(d / "obj"), "tb.sv", "dut.sv"],
                           cwd=d, capture_output=True, text=True)
        assert b.returncode == 0, b.stderr[-3000:]
        r = subprocess.run([str(d / "obj" / "Vtb")], cwd=d, capture_output=True, text=True, timeout=600)
        return "\n".join(x for x in r.stdout.splitlines() if x.startswith("TB:"))


def nums(pattern: str, out: str) -> list[int]:
    m = re.search(pattern, out)
    assert m, (pattern, out)
    return [int(x) for x in m.groups()]


# ---------------------------------------------------------------- tests
def test_text() -> None:
    g, i, r = (s.tb_top(reader(4, 3, m), []) for m in s.MODES)
    assert "req_ready" not in g and "refused" not in g and "io_tcdmReq_0_ready(1'b1)" in g
    assert "io_tcdmReq_0_ready(req_ready[0])" in r and "TB: refused" in r and "$urandom); " in r
    assert "io_start" in i and "start <= 1'b1" not in i and "TB: idle requests" in i
    g, i, r = (s.tb_top(xbar(8, 16, mode=m), []) for m in s.MODES)
    assert "refused" not in g and "issue" not in g
    assert "task automatic issue" in r and "(i / 2 + k[i]) % B" in r and "TB: refused" in r
    assert "q_valid" in i and "apply" not in i and "banks valid %b with no input" in i
    try:
        s.tb_top(xbar(8, 16, mode="busy"), [])
    except KeyError:
        pass
    else:
        raise AssertionError("an unknown mode is refused")


def test_sim() -> None:
    if not shutil.which("verilator"):
        print("skip test_sim: no verilator on PATH")
        return
    for tb in (reader(1, 1), reader(4, 3)):
        out = run(tb, reader_model(tb))
        beats, _, fill, stalls, dbad, abad, xz = nums(s_reader(), out)
        assert (beats, dbad, abad, xz) == (1024, 0, 0, 0), out
        out = run(reader(tb["channels"], len(tb["bounds"]), "refused"), reader_model(tb))
        beats, _, fill, stalls, dbad, abad, xz = nums(s_reader(), out)
        (ref,) = nums(r"TB: refused (\d+)", out)
        (cyc,) = nums(r"cycles (\d+)", out)
        assert (beats, dbad, abad, xz) == (1024, 0, 0, 0) and stalls > 0 and ref > 0, out
        assert cyc == fill + beats + stalls, out
        out = run(reader(tb["channels"], len(tb["bounds"]), "refused"), reader_model(tb, "addr"))
        assert nums(s_reader(), out)[5] > 0, out          # a dropped held request is caught
        out = run(reader(tb["channels"], len(tb["bounds"]), "idle"), reader_model(tb))
        assert nums(r"cycles (\d+)", out) == [1024] and nums(r"TB: idle requests (\d+) beats (\d+) busy (\d+) "
                                                             r"xz (\d+)", out) == [0, 0, 0, 0], out
    for tb in (xbar(8, 16), xbar(16, 16, 4, 4)):
        g = run(tb, xbar_model(tb))
        assert nums(s_xbar(), g)[2:] == [0, 0, 0, 0], g
        t = {**tb, "mode": "refused"}
        out = run(t, xbar_model(tb))
        grants, want, gbad, bbad, rbad, xz = nums(s_xbar(), out)
        (ref,) = nums(r"TB: refused (\d+)", out)
        (cyc,) = nums(r"cycles (\d+)", out)
        assert grants == want == tb["inputs"] * s.CYCLES and (gbad, bbad, rbad, xz) == (0, 0, 0, 0), out
        assert ref == tb["inputs"] // 2 * s.CYCLES and cyc == 2 * s.CYCLES + 1, out   # one refusal per pair and request
        out = run(t, xbar_model(tb, "double"))
        assert nums(s_xbar(), out)[2] > 0, out             # two grants on one bank are caught
        out = run({**tb, "mode": "idle"}, xbar_model(tb))
        assert nums(r"cycles (\d+)", out) == [s.CYCLES + 1] and nums(s_xbar(), out) == [0, 0, 0, 0, 0, 0], out
        print(f"{tb['point']} ro {tb['ro']} wo {tb['wo']}: refused {ref} over {cyc} cycles")


def s_reader() -> str:
    return (r"TB: beats (\d+) expected (\d+) fill (-?\d+) stalls (\d+) data_mismatches (\d+) addr_mismatches (\d+) "
            r"xz (\d+)")


def s_xbar() -> str:
    return r"TB: grants (\d+) expected (\d+) grant_cycles_bad (\d+) bank_mismatches (\d+) rsp_mismatches (\d+) xz (\d+)"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
