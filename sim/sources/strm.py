"""sim/sources/strm.py - a streamer, xbar or xbar_mix point -> tb.json and its generated TB.

A streamer point is snax_cluster's reader alone, as the Streamer uses it (strm/gen.py, rtl/streamer/<point>.zip); an
xbar point is the TCDM sparse interconnect (rtl/xbar/<point>.zip); an xbar_mix point is that interconnect in
strm/xbar_mix.py's wrapper, with read-only and write-only inputs (rtl/xbar_mix/<point>.zip). None has a done: the TB here is generated
whole per point (the port names carry the channel and bank index), drives the work, checks every output and prints
the window. A point runs in one of MODES: grant (every request granted, the tables' runs), idle (configured, no
request) or refused (requests held while refused), the last two for the refusal price (report/refusal_fit.py).
build() writes tb.json (its fields and the stimuli in its docstring); docs/power.md, "Streamer and interconnect", has
the testbench and the window.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from . import ROOT, syn as _syn

TB_VERSION = 1
BEATS = 1024        # reader: beats per run, split over the loops
CYCLES = 1024       # xbar: request cycles per run (refused: requests per input); idle: the window's cycles
MODES = ("grant", "idle", "refused")
T_NS = 10
ADDR_W = 17         # log2(128 KiB): the reader's address and the xbar's TCDM address width (grid.json)
WORD_B = 8          # bytes per 64-bit TCDM word


STEP_MAX = (1 << (ADDR_W - 1)) - 1   # the largest stride a loop takes: ProgrammableCounter's step is width - 1 bits


def _xbar_mix():
    """strm/xbar_mix.py: its tie() says which of the interconnect's ports the wrapper ties (not ports of xbar_mix)."""
    spec = importlib.util.spec_from_file_location("strm_xbar_mix", ROOT / "strm" / "xbar_mix.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bounds(loops: int, beats: int = BEATS) -> list[int]:
    """beats (a power of two) split over the loops as evenly as powers of two allow, loop 0 (innermost) first and
    the larger bounds outermost: 1024 over 3 loops is [8, 8, 16], over 7 [2, 2, 2, 2, 4, 4, 4]. Outermost, so the
    outermost stride (8 C x the inner bounds' product) stays under 64 KiB at 16 channels (PITFALLS SC9)."""
    e = beats.bit_length() - 1
    if beats != 1 << e or loops < 1 or loops > e:
        raise ValueError(f"{beats} beats do not split over {loops} loops")
    return [1 << (e // loops + (1 if i >= loops - e % loops else 0)) for i in range(loops)]


def strides(bnds: list[int], channels: int) -> list[int]:
    """Unit strides: loop 0 steps over one beat of `channels` words, loop k over loop k-1's whole range."""
    out = [WORD_B * channels]
    for b in bnds[:-1]:
        out.append(out[-1] * b)
    return out


def build(point: str, netlist: Path, seed: int = 0, mode: str = "grant") -> dict:
    """tb.json:
      tb_version, source, point, params, top, snax_cluster_commit
      clock    {port: clock}
      reset    {port: reset, active: high, sync: false (reader) | true (xbar)}
      control  {kind: "strm_reader" | "strm_xbar" (xbar and xbar_mix)}
      reader:  bounds [b0 .. b{L-1}] (powers of two, product BEATS = 1024, the larger ones outermost: every stride
               stays under the counter's 16-bit step, PITFALLS SC9),
               strides [8 C, 8 C b0, ...] (unit strides: beat n reads words n C .. n C + C - 1), ptr 0, spatial
               stride 8, beats 1024
      xbar:    cycles 1024, inputs, banks, row_bits (log2 of the bank depth), bank_bits
      xbar_mix: as xbar, and ro, wo: inputs 0 .. ro-1 read-only, ro .. ro+wo-1 write-only, the rest read-write
      window   the window's expected cycles: reader None (fill + beats, measured), xbar cycles + 1; idle: reader
               cycles, xbar cycles + 1; refused: None (measured)
      seed     the root seed of the TB's $urandom calls: sim/pwr.py runs vsim -sv_seed <seed> (pwr run --seed, default 0)
      mode     idle or refused; absent in a grant run's tb.json (as before the modes)

    The stimuli:
      reader  io_start for one cycle; every TCDM request granted at once (ready 1), its response valid the next cycle
              with a new random 64-bit word; the output always ready. Window: from a quarter cycle before the edge that
              takes io_start to a quarter cycle before the edge that takes the last beat. Checks: beats = 1024, every
              beat = the responses in order per channel (channel i in bits 64 i), every request address
              8 (n C + i), no X/Z, no cycle without a beat between the first and the last (stalls after the fill).
      xbar    (inputs <= banks only) cycle t: input i requests bank (i + t) mod banks at a random row, write = t odd
              for every input (reads and writes alternate), random write data, strb ff, amo, priority and user 0; the
              memory side always ready, memRsps valid 1 (as sparse_interconnect_wrapper ties it), a read bank's data a
              new random word at the next edge; tcdmRsps ready 1. Window: from a quarter cycle before the edge applying
              cycle 0 to a quarter cycle before the edge after cycle `cycles` (its read responses): cycles + 1 edges.
              Checks: every input granted every cycle (grants = inputs x cycles), each bank's request (row, write,
              data, strb) its input's, no bank valid without an input, each read response valid with the bank's data.
      xbar_mix the xbar stimulus on the wrapper's ports (the ports its ties remove are not driven): the read-write
              inputs exactly as xbar's (the same $urandom calls at ro = wo = 0); a read-only input the same banks and
              rows, every request a read; a write-only input the same banks and rows, every request a write with new
              random data. The checks are xbar's by kind: the bank's write bit its input's kind, write data checked on
              writes, read responses checked only on inputs that read (a write-only input has no response data).
    The idle and refused stimuli (the refusal price, report/refusal_fit.py):
      idle    the same ports and configuration, nothing started or requested. reader: io_start never, the window
              `cycles` (1024) cycles from a quarter cycle before an edge 4 cycles after reset; checks: no request,
              no beat, busy low, no X/Z. xbar: every input's valid low, address and data 0, the window cycles + 1
              edges as xbar's; checks: no bank valid, no X/Z.
      refused reader: as grant, but each channel's TCDM ready is a new random bit every cycle ($urandom), so a
              request is refused on about half its cycles and held (valid, address) until granted; a granted request
              is answered the next cycle. Checks: grant's, the address of a held request its pending one, stalls
              allowed; the TB prints the refused request-cycles (valid and not ready) in the window. xbar: inputs
              2j and 2j + 1 are a pair that moves in step, as two movers feeding one datapath: each issues `cycles`
              requests, request k of both to bank (j + k) mod banks, rows and data random, write by kind as
              xbar_mix's with k in place of the cycle; a refused request is held, a granted one's input waits (valid
              low) until its partner is granted, then the pair issues request k + 1. So each pair has one refusal
              per request, about 2 x cycles cycles. The window: from the first requests to the cycle after the last
              grant (its read responses). Checks: every bank with requests
              grants exactly one of them and forwards its request (row, write, data, strb), no bank valid without
              one, each granted read answered with the bank's data, grants = inputs x cycles; the TB prints the
              refused request-cycles.
    The window's rising edges are its own cycles and no event sits on a boundary (the char source's rule); the TB dumps
    from time 0 and sim/pwr.py cuts the window.
    """
    if mode not in MODES:
        raise ValueError(f"mode {mode}: one of {', '.join(MODES)}")
    syn = _syn()
    source = syn.SOURCE
    cfg = syn.forge_json(point, "config.json")
    p = cfg["params"]
    tb = {"tb_version": TB_VERSION, "source": source, "point": point, "params": p, "top": syn.top_of(point),
          "snax_cluster_commit": cfg.get("snax_cluster_commit", ""), "clock": {"port": "clock"}, "seed": seed}
    if mode != "grant":
        tb["mode"] = mode
    if source == "streamer":
        b = bounds(p["temporal_dim"])
        st = strides(b, p["num_channel"])
        if max(st) > STEP_MAX:
            raise ValueError(f"stride {max(st)} B over the counter's step ({STEP_MAX}, PITFALLS SC9)")
        tb.update({"reset": {"port": "reset", "active": "high", "sync": False}, "control": {"kind": "strm_reader"},
                   "channels": p["num_channel"], "bounds": b, "strides": st,
                   "beats": BEATS, "window": CYCLES if mode == "idle" else None})
    else:
        n, banks = p["inputs"], p["banks"]
        if n > banks:
            raise ValueError(f"{n} inputs on {banks} banks: no conflict-free stimulus (power only where inputs <= banks)")
        if mode == "refused" and n % 2:
            raise ValueError(f"{n} inputs: the refused stimulus pairs the inputs")
        bank_bits = banks.bit_length() - 1
        tb.update({"reset": {"port": "reset", "active": "high", "sync": True}, "control": {"kind": "strm_xbar"},
                   "inputs": n, "banks": banks, "bank_bits": bank_bits,
                   **({"ro": p["ro"], "wo": p["wo"]} if source == "xbar_mix" else {}),
                   "row_bits": ADDR_W - bank_bits - (WORD_B.bit_length() - 1), "cycles": CYCLES,
                   "window": None if mode == "refused" else CYCLES + 1})
    tb["netlist_inputs"] = netlist_inputs(netlist, tb["top"])
    # at 1 channel the spatial stride multiplies only channel 0's index: firtool drops the port (PITFALLS SC2)
    tb["spatial_stride_port"] = source == "streamer" and "io_aguCfg_spatialStrides_0" in tb["netlist_inputs"]
    tb["ports"] = sorted(connected(tb))
    check(tb)
    return tb


def connected(tb: dict) -> set[str]:
    """Every DUT port the generated TB connects."""
    out = {"clock", "reset"}
    if tb["control"]["kind"] == "strm_reader":
        out |= {"io_aguCfg_ptr", "io_start", "io_busy", "io_data_ready", "io_data_valid", "io_data_bits"}
        if tb["spatial_stride_port"]:
            out.add("io_aguCfg_spatialStrides_0")
        out |= {f"io_aguCfg_temporal{k}_{i}" for k in ("Bounds", "Strides") for i in range(len(tb["bounds"]))}
        for i in range(tb["channels"]):
            out |= {f"io_tcdmReq_{i}_{f}" for f in ("ready", "valid", "bits_addr", "bits_priority")}
            out |= {f"io_tcdmRsp_{i}_{f}" for f in ("valid", "bits_data")}
    else:
        for i in range(tb["inputs"]):
            out |= {f"io_tcdmReqs_{i}_{f}" for f in ("ready", "valid", "bits_addr", "bits_write", "bits_amo",
                                                     "bits_data", "bits_strb", "bits_priority", "bits_user")}
            out |= {f"io_tcdmRsps_{i}_{f}" for f in ("ready", "valid", "bits_data")}
        for b in range(tb["banks"]):
            out |= {f"io_memReqs_{b}_{f}" for f in ("ready", "valid", "bits_addr", "bits_write", "bits_amo",
                                                    "bits_data", "bits_strb", "bits_priority", "bits_user")}
            out |= {f"io_memRsps_{b}_{f}" for f in ("ready", "valid", "bits_data")}
        if tb["source"] == "xbar_mix":      # the wrapper's ties: those ports are not on xbar_mix
            tie = _xbar_mix().tie
            out = {p for p in out if p in ("clock", "reset") or tie(p, tb["ro"], tb["wo"]) is None}
    return out


def netlist_inputs(netlist: Path, top: str) -> list[str]:
    """The top's ports in the mapped netlist (DC keeps the RTL's names, buses as vectors)."""
    ports = _syn().module_ports([netlist.read_text()], top)
    if ports is None:
        raise ValueError(f"{netlist.name}: no module {top}")
    return ports


def check(tb: dict) -> None:
    """Every port the TB connects is on the netlist's top and every netlist port is connected."""
    have, want = set(tb["netlist_inputs"]), set(tb["ports"])
    if want - have:
        raise ValueError(f"ports the TB connects that {tb['top']} lacks: {sorted(want - have)[:8]}")
    if have - want:
        raise ValueError(f"ports of {tb['top']} the TB leaves open: {sorted(have - want)[:8]}")


def _dump(scopes: list[str]) -> list[str]:
    """The DUT's nets and its sub-designs' (sim/pwr.py's dump_block), from time 0; sim/pwr.py cuts the window."""
    L = ["    initial begin : dump", "        string vcd;", "        if ($value$plusargs(\"VCD=%s\", vcd)) begin",
         "            $dumpfile(vcd);", "            $dumpvars(1, tb.dut);"]
    L += [f"            $dumpvars(1, tb.dut.{s});" for s in scopes]
    return L + ["        end", "    end"]


def tb_top(tb: dict, scopes: list[str]) -> str:
    mode = tb.get("mode", "grant")
    if tb["control"]["kind"] == "strm_reader":
        return (tb_reader_idle if mode == "idle" else tb_reader)(tb, scopes)
    return {"grant": tb_xbar, "idle": tb_xbar_idle, "refused": tb_xbar_held}[mode](tb, scopes)


def _reader_head(tb: dict, what: str, ready: str) -> list[str]:
    """The reader TB's declarations and the DUT, each channel's TCDM ready `ready` (indexed by {i})."""
    c, b, s, aw = tb["channels"], tb["bounds"], tb["strides"], ADDR_W
    L = [f"// Generated by sim/sources/strm.py from tb.json ({what} {tb['point']}): do not edit.",
         "`timescale 1ns/1ps", "module tb;",
         f"    localparam int C = {c}, BEATS = {tb['beats']};", f"    localparam real T_NS = {T_NS};",
         "    logic clock = 1'b0, reset = 1'b1;", "    always #(T_NS / 2) clock = ~clock;", "    logic start = 1'b0;",
         "    logic [C-1:0] req_valid, rsp_valid = '0, req_seen = '0;", f"    logic [{aw - 1}:0] req_addr [C];",
         "    logic [63:0] rsp_data [C];", "    logic data_valid, busy;", "    logic [64*C-1:0] data_bits;",
         "    initial for (int i = 0; i < C; i++) rsp_data[i] = '0;"]
    if ready != "1'b1":
        L.append("    logic [C-1:0] req_ready = '1;")
    L += [f"    {tb['top']} dut (", "        .clock(clock), .reset(reset),",
          f"        .io_aguCfg_ptr({aw}'d0),"
          + (f" .io_aguCfg_spatialStrides_0({aw}'d{WORD_B})," if tb["spatial_stride_port"] else "")]
    for k, (bk, sk) in enumerate(zip(b, s)):
        L.append(f"        .io_aguCfg_temporalBounds_{k}({aw}'d{bk}), .io_aguCfg_temporalStrides_{k}({aw}'d{sk}),")
    L.append("        .io_start(start), .io_busy(busy),")
    for i in range(c):
        L += [f"        .io_tcdmReq_{i}_ready({ready.format(i=i)}), .io_tcdmReq_{i}_valid(req_valid[{i}]), "
              f".io_tcdmReq_{i}_bits_addr(req_addr[{i}]), .io_tcdmReq_{i}_bits_priority(),",
              f"        .io_tcdmRsp_{i}_valid(rsp_valid[{i}]), .io_tcdmRsp_{i}_bits_data(rsp_data[{i}]),"]
    return L + ["        .io_data_ready(1'b1), .io_data_valid(data_valid), .io_data_bits(data_bits));", ""]


def tb_reader(tb: dict, scopes: list[str]) -> str:
    """grant, or refused: each channel's ready a new random bit every cycle, a refused request held."""
    aw = ADDR_W
    held = tb.get("mode") == "refused"
    L = _reader_head(tb, "reader, refused" if held else "reader", "req_ready[{i}]" if held else "1'b1")
    L += _dump(scopes)
    L += ["",
          "    // TCDM: requests sampled at the falling edge, granted at the next rising edge, answered the cycle after",
          "    logic [63:0] q [C][$];", "    int n_req [C];",
          "    int addr_bad = 0, data_bad = 0, xz = 0, beats = 0, stalls = 0, cycles = 0, fill = -1;",
          "    bit in_run = 0, done = 0;", "    real t0, t1;"]
    if held:
        L += ["    int refused = 0;"]
    L += ["    always @(negedge clock) if (!reset) begin",
          "        req_seen = req_valid & req_ready;" if held else "        req_seen = req_valid;",
          "        if ($isunknown(req_valid)) xz++;",
          "        for (int i = 0; i < C; i++) if (req_valid[i]) begin",
          f"            if (req_addr[i] !== {aw}'({WORD_B} * (n_req[i] * C + i))) begin",
          "                addr_bad++;",
          "                if (addr_bad <= 5) $display(\"TB: FAIL: channel %0d request %0d addr %h\", i, n_req[i], req_addr[i]);",
          "            end",
          "            if (req_ready[i]) n_req[i]++;    // a refused request is held: the same address next cycle"
          if held else "            n_req[i]++;",
          "        end",
          "        if (in_run && !done) begin",
          "            cycles++;"]
    if held:
        L += ["            refused += $countones(req_valid & ~req_ready);"]
    L += [
          "            if ($isunknown(data_valid) || (data_valid && $isunknown(data_bits))) xz++;",
          "            if (data_valid) begin",
          "                if (fill < 0) fill = cycles - 1;",
          "                for (int i = 0; i < C; i++) begin",
          "                    if (q[i].size() == 0 || data_bits[64*i +: 64] !== q[i][0]) begin",
          "                        data_bad++;",
          "                        if (data_bad <= 5) $display(\"TB: FAIL: beat %0d channel %0d got %h\", beats, i, data_bits[64*i +: 64]);",
          "                    end",
          "                    if (q[i].size()) void'(q[i].pop_front());",
          "                end",
          "                beats++;",
          "                if (beats == BEATS) begin done = 1; t1 = $realtime + T_NS / 4; end",
          "            end else if (fill >= 0) stalls++;",
          "        end",
          "    end",
          "    always @(posedge clock)",
          "        for (int i = 0; i < C; i++) begin",
          "            if (rsp_valid[i]) q[i].push_back(rsp_data[i]);      // the DUT takes it at this edge",
          "            rsp_valid[i] <= req_seen[i];",
          "            if (req_seen[i]) rsp_data[i] <= {$urandom, $urandom};"]
    if held:
        L += ["            req_ready[i] <= 1'($urandom);    // the next cycle's grant or refusal"]
    L += ["        end",
          "    initial begin",
          "        repeat (5) @(posedge clock);",
          "        @(negedge clock) reset = 1'b0;",
          "        repeat (4) @(posedge clock);",
          "        start <= 1'b1;",
          "        @(posedge clock);                  // this edge takes io_start: the window's first",
          "        start <= 1'b0;",
          "        t0 = $realtime - T_NS / 4;",
          "        in_run = 1;",
          "        fork",
          "            wait (done);",
          "            begin repeat (BEATS * 4 + 1000) @(posedge clock); $display(\"TB: FAIL: timeout\"); end",
          "        join_any",
          "        repeat (2) @(posedge clock);",
          "        $display(\"TB: window busy t0_ns %0.3f t1_ns %0.3f cycles %0d\", t0, t1, cycles);",
          "        $display(\"TB: beats %0d expected %0d fill %0d stalls %0d data_mismatches %0d addr_mismatches %0d xz %0d\",",
          "                 beats, BEATS, fill, stalls, data_bad, addr_bad, xz);"]
    if held:
        L += ["        $display(\"TB: refused %0d\", refused);"]
    L += ["        $finish;",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def tb_reader_idle(tb: dict, scopes: list[str]) -> str:
    """idle: configured, never started; `cycles` edges counted from 4 cycles after reset."""
    L = _reader_head(tb, "reader, idle", "1'b1") + _dump(scopes)
    L += ["",
          f"    localparam int IDLE = {CYCLES};",
          "    int requests = 0, beats = 0, busy_cycles = 0, xz = 0, cycles = 0;",
          "    bit in_run = 0;", "    real t0, t1;",
          "    always @(negedge clock) if (!reset && in_run) begin",
          "        cycles++;",
          "        if ($isunknown(req_valid) || $isunknown(data_valid) || $isunknown(busy)) xz++;",
          "        requests += $countones(req_valid);",
          "        if (data_valid) beats++;",
          "        if (busy) busy_cycles++;",
          "    end",
          "    always @(posedge clock) rsp_valid <= '0;",
          "    initial begin",
          "        repeat (5) @(posedge clock);",
          "        @(negedge clock) reset = 1'b0;",
          "        repeat (4) @(posedge clock);",
          "        @(posedge clock);                  // the window's first edge: nothing started",
          "        t0 = $realtime - T_NS / 4;",
          "        in_run = 1;",
          "        repeat (IDLE) @(posedge clock);",
          "        t1 = $realtime - T_NS / 4;",
          "        in_run = 0;",
          "        repeat (2) @(posedge clock);",
          "        $display(\"TB: window busy t0_ns %0.3f t1_ns %0.3f cycles %0d\", t0, t1, cycles);",
          "        $display(\"TB: idle requests %0d beats %0d busy %0d xz %0d\", requests, beats, busy_cycles, xz);",
          "        $finish;",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def _xbar_head(tb: dict, what: str) -> list[str]:
    """The interconnect TB's declarations and the DUT (xbar_mix's tied ports left out)."""
    n, banks, cyc = tb["inputs"], tb["banks"], tb["cycles"]
    bb, maw = tb["bank_bits"], tb["row_bits"]
    ro, wo = tb.get("ro", 0), tb.get("wo", 0)
    have = set(tb["ports"])

    def conns(items: list[tuple[str, str]], end: str) -> str:
        return "        " + ", ".join(f".{p}({x})" for p, x in items if p in have) + end

    kinds = f", {ro} read-only, {wo} write-only" if tb["source"] == "xbar_mix" else ""
    L = [f"// Generated by sim/sources/strm.py from tb.json ({tb['source']} {tb['point']}{kinds}, {what}): do not edit.",
         "`timescale 1ns/1ps", "module tb;",
         f"    localparam int N = {n}, B = {banks}, CYC = {cyc}, BB = {bb}, MAW = {maw}, RO = {ro}, WO = {wo};",
         f"    localparam real T_NS = {T_NS};",
         "    logic clock = 1'b0, reset = 1'b1;", "    always #(T_NS / 2) clock = ~clock;",
         "    logic [N-1:0] q_valid = '0, q_ready, q_write = '0, p_valid;",
         f"    logic [{ADDR_W - 1}:0] q_addr [N];", "    logic [63:0] q_data [N], p_data [N];",
         "    logic [B-1:0] m_valid, m_write;", "    logic [MAW-1:0] m_addr [B];",
         "    logic [63:0] m_wdata [B], m_rdata [B];", "    logic [7:0] m_strb [B];",
         "    initial for (int i = 0; i < N; i++) begin q_addr[i] = '0; q_data[i] = '0; end",
         "    initial for (int b = 0; b < B; b++) m_rdata[b] = '0;",
         f"    {tb['top']} dut (", "        .clock(clock), .reset(reset),"]
    for i in range(n):
        q, p = f"io_tcdmReqs_{i}_", f"io_tcdmRsps_{i}_"
        L += [conns([(q + "ready", f"q_ready[{i}]"), (q + "valid", f"q_valid[{i}]"), (q + "bits_addr", f"q_addr[{i}]"),
                     (q + "bits_write", f"q_write[{i}]"), (q + "bits_amo", "4'd0"), (q + "bits_data", f"q_data[{i}]"),
                     (q + "bits_strb", "8'hff"), (q + "bits_priority", "1'b0"), (q + "bits_user", "3'd0")], ","),
              conns([(p + "ready", "1'b1"), (p + "valid", f"p_valid[{i}]"), (p + "bits_data", f"p_data[{i}]")], ",")]
    for b in range(banks):
        q, p = f"io_memReqs_{b}_", f"io_memRsps_{b}_"
        L += [conns([(q + "ready", "1'b1"), (q + "valid", f"m_valid[{b}]"), (q + "bits_addr", f"m_addr[{b}]"),
                     (q + "bits_write", f"m_write[{b}]"), (q + "bits_amo", ""), (q + "bits_data", f"m_wdata[{b}]"),
                     (q + "bits_strb", f"m_strb[{b}]"), (q + "bits_priority", ""), (q + "bits_user", "")], ","),
              conns([(p + "ready", ""), (p + "valid", "1'b1"), (p + "bits_data", f"m_rdata[{b}]")],
                    "," if b < banks - 1 else ");")]
    return L


def tb_xbar_idle(tb: dict, scopes: list[str]) -> str:
    """idle: no input valid, address and data 0; the window xbar's cycles + 1 edges."""
    L = _xbar_head(tb, "idle") + [""] + _dump(scopes)
    L += ["",
          "    int t = -1, bank_bad = 0, xz = 0;", "    real t0, t1;",
          "    always @(negedge clock) if (!reset && t >= 0 && t <= CYC) begin",
          "        if ($isunknown(q_ready) || $isunknown(m_valid) || $isunknown(p_valid)) xz++;",
          "        if (m_valid !== '0) begin",
          "            bank_bad++;",
          "            if (bank_bad <= 5) $display(\"TB: FAIL: cycle %0d banks valid %b with no input\", t, m_valid);",
          "        end",
          "    end",
          "    initial begin",
          "        repeat (5) @(posedge clock);",
          "        @(negedge clock) reset = 1'b0;",
          "        repeat (3) @(posedge clock);",
          "        @(posedge clock);                  // the window's first edge: no request",
          "        t0 = $realtime - T_NS / 4;",
          "        t = 0;",
          "        while (t < CYC) begin @(posedge clock); t++; end",
          "        @(posedge clock);",
          "        t1 = $realtime - T_NS / 4;",
          "        t = CYC + 1;",
          "        repeat (2) @(posedge clock);",
          "        $display(\"TB: window busy t0_ns %0.3f t1_ns %0.3f cycles %0d\", t0, t1, CYC + 1);",
          "        $display(\"TB: grants %0d expected %0d grant_cycles_bad %0d bank_mismatches %0d rsp_mismatches %0d xz %0d\",",
          "                 0, 0, 0, bank_bad, 0, xz);",
          "        $finish;",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def tb_xbar_held(tb: dict, scopes: list[str]) -> str:
    """refused: each input `cycles` requests in order, two inputs per bank at the start, a refused request held."""
    L = _xbar_head(tb, "refused") + [""] + _dump(scopes)
    L += ["",
          "    localparam int REQS = CYC;",
          "    int t = -1, grants = 0, refused = 0, grant_bad = 0, bank_bad = 0, rsp_bad = 0, xz = 0;",
          "    int k [N], tgt [N], was_bank [N];", "    bit adv [N], got [N], was_read [N], stop = 0, last = 0;",
          "    logic [MAW-1:0] row [N];", "    logic [63:0] bank_rd_next [B];", "    real t0, t1;",
          "    // input i's request k[i]: bank (i / 2 + k) mod B (a pair's two inputs on one bank), a random row;",
          "    // none once k[i] = REQS",
          "    task automatic issue(input int i);",
          "        row[i] = MAW'($urandom);",
          "        tgt[i] = (i / 2 + k[i]) % B;",
          "        q_valid[i] <= k[i] < REQS;",
          "        q_write[i] <= (i < RO) ? 1'b0 : (i < RO + WO) ? 1'b1 : 1'(k[i] % 2);",
          "        q_addr[i] <= {row[i], BB'(tgt[i]), 3'b000};",
          "        if (i >= RO && (i < RO + WO || k[i] % 2)) q_data[i] <= {$urandom, $urandom};",
          "    endtask",
          "    // the falling edge of cycle t: grants and refusals, the banks' requests, cycle t-1's read responses",
          "    always @(negedge clock) if (!reset && t >= 0 && !stop) begin",
          "        if ($isunknown(q_ready & q_valid) || $isunknown(m_valid) || $isunknown(p_valid)) xz++;",
          "        for (int i = 0; i < N; i++) if (was_read[i]) begin",
          "            if (!p_valid[i] || p_data[i] !== m_rdata[was_bank[i]]) begin",
          "                rsp_bad++;",
          "                if (rsp_bad <= 5) $display(\"TB: FAIL: cycle %0d input %0d response %b %h\", t, i, p_valid[i], p_data[i]);",
          "            end",
          "        end",
          "        grants += $countones(q_valid & q_ready);",
          "        refused += $countones(q_valid & ~q_ready);",
          "        for (int b = 0; b < B; b++) begin",
          "            int want, won, w;",
          "            want = 0; won = 0; w = -1;",
          "            for (int i = 0; i < N; i++) if (q_valid[i] && tgt[i] == b) begin",
          "                want++;",
          "                if (q_ready[i]) begin won++; w = i; end",
          "            end",
          "            if (want > 0 && won != 1) begin",
          "                grant_bad++;",
          "                if (grant_bad <= 5) $display(\"TB: FAIL: cycle %0d bank %0d: %0d of %0d requests granted\", t, b, won, want);",
          "            end",
          "            if (want == 0 && m_valid[b]) begin",
          "                bank_bad++;",
          "                if (bank_bad <= 5) $display(\"TB: FAIL: cycle %0d bank %0d valid with no input\", t, b);",
          "            end else if (w >= 0 && (!m_valid[b] || m_addr[b] !== row[w] || m_write[b] !== q_write[w] ||",
          "                     (q_write[w] && (m_wdata[b] !== q_data[w] || m_strb[b] !== 8'hff)))) begin",
          "                bank_bad++;",
          "                if (bank_bad <= 5) $display(\"TB: FAIL: cycle %0d bank %0d from input %0d\", t, b, w);",
          "            end",
          "            bank_rd_next[b] = (w >= 0 && !q_write[w]) ? {$urandom, $urandom} : m_rdata[b];",
          "        end",
          "        for (int i = 0; i < N; i++) begin",
          "            adv[i] = q_valid[i] && q_ready[i];",
          "            was_read[i] = adv[i] && !q_write[i];",
          "            was_bank[i] = tgt[i];",
          "        end",
          "    end",
          "    initial begin",
          "        repeat (5) @(posedge clock);",
          "        @(negedge clock) reset = 1'b0;",
          "        repeat (3) @(posedge clock);",
          "        @(posedge clock);                  // the first requests: the window's first edge",
          "        t0 = $realtime - T_NS / 4;",
          "        t = 0;",
          "        for (int i = 0; i < N; i++) begin k[i] = 0; adv[i] = 0; got[i] = 0; was_read[i] = 0; issue(i); end",
          "        while (!last) begin",
          "            int active;",
          "            @(posedge clock);",
          "            for (int b = 0; b < B; b++) m_rdata[b] <= bank_rd_next[b];",
          "            t++;",
          "            active = 0;",
          "            for (int i = 0; i < N; i++) if (adv[i]) begin got[i] = 1; q_valid[i] <= 1'b0; end",
          "            for (int j = 0; j < N / 2; j++) if (got[2*j] && got[2*j+1])  // the pair's next requests",
          "                for (int i = 2*j; i < 2*j + 2; i++) begin k[i]++; got[i] = 0; issue(i); end",
          "            for (int i = 0; i < N; i++) if (k[i] < REQS) active++;",
          "            if (active == 0) last = 1;      // this cycle only answers the last grants' reads",
          "            if (t > REQS * 8 + 1000) begin $display(\"TB: FAIL: timeout\"); last = 1; end",
          "        end",
          "        @(posedge clock);                  // after the last cycle's falling edge (its responses checked)",
          "        t1 = $realtime - T_NS / 4;",
          "        stop = 1;",
          "        repeat (2) @(posedge clock);",
          "        $display(\"TB: window busy t0_ns %0.3f t1_ns %0.3f cycles %0d\", t0, t1, t + 1);",
          "        $display(\"TB: grants %0d expected %0d grant_cycles_bad %0d bank_mismatches %0d rsp_mismatches %0d xz %0d\",",
          "                 grants, N * REQS, grant_bad, bank_bad, rsp_bad, xz);",
          "        $display(\"TB: refused %0d\", refused);",
          "        $finish;",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"


def tb_xbar(tb: dict, scopes: list[str]) -> str:
    n, banks, cyc = tb["inputs"], tb["banks"], tb["cycles"]
    bb, maw = tb["bank_bits"], tb["row_bits"]
    ro, wo = tb.get("ro", 0), tb.get("wo", 0)
    have = set(tb["ports"])

    def conns(items: list[tuple[str, str]], end: str) -> str:
        """The connections of the ports the TB connects (tb["ports"]); xbar_mix's tied ones dropped."""
        return "        " + ", ".join(f".{p}({x})" for p, x in items if p in have) + end

    kinds = f", {ro} read-only, {wo} write-only" if tb["source"] == "xbar_mix" else ""
    L = [f"// Generated by sim/sources/strm.py from tb.json ({tb['source']} {tb['point']}{kinds}): do not edit.",
         "`timescale 1ns/1ps", "module tb;",
         f"    localparam int N = {n}, B = {banks}, CYC = {cyc}, BB = {bb}, MAW = {maw}, RO = {ro}, WO = {wo};",
         f"    localparam real T_NS = {T_NS};",
         "    logic clock = 1'b0, reset = 1'b1;", "    always #(T_NS / 2) clock = ~clock;",
         "    logic [N-1:0] q_valid = '0, q_ready, q_write = '0, p_valid;",
         f"    logic [{ADDR_W - 1}:0] q_addr [N];", "    logic [63:0] q_data [N], p_data [N];",
         "    logic [B-1:0] m_valid, m_write;", "    logic [MAW-1:0] m_addr [B];",
         "    logic [63:0] m_wdata [B], m_rdata [B];", "    logic [7:0] m_strb [B];",
         "    initial for (int i = 0; i < N; i++) begin q_addr[i] = '0; q_data[i] = '0; end",
         "    initial for (int b = 0; b < B; b++) m_rdata[b] = '0;",
         f"    {tb['top']} dut (", "        .clock(clock), .reset(reset),"]
    for i in range(n):
        q, p = f"io_tcdmReqs_{i}_", f"io_tcdmRsps_{i}_"
        L += [conns([(q + "ready", f"q_ready[{i}]"), (q + "valid", f"q_valid[{i}]"), (q + "bits_addr", f"q_addr[{i}]"),
                     (q + "bits_write", f"q_write[{i}]"), (q + "bits_amo", "4'd0"), (q + "bits_data", f"q_data[{i}]"),
                     (q + "bits_strb", "8'hff"), (q + "bits_priority", "1'b0"), (q + "bits_user", "3'd0")], ","),
              conns([(p + "ready", "1'b1"), (p + "valid", f"p_valid[{i}]"), (p + "bits_data", f"p_data[{i}]")], ",")]
    for b in range(banks):
        q, p = f"io_memReqs_{b}_", f"io_memRsps_{b}_"
        L += [conns([(q + "ready", "1'b1"), (q + "valid", f"m_valid[{b}]"), (q + "bits_addr", f"m_addr[{b}]"),
                     (q + "bits_write", f"m_write[{b}]"), (q + "bits_amo", ""), (q + "bits_data", f"m_wdata[{b}]"),
                     (q + "bits_strb", f"m_strb[{b}]"), (q + "bits_priority", ""), (q + "bits_user", "")], ","),
              conns([(p + "ready", ""), (p + "valid", "1'b1"), (p + "bits_data", f"m_rdata[{b}]")],
                    "," if b < banks - 1 else ");")]
    L += [""] + _dump(scopes)
    L += ["",
          "    int t = -1, grants = 0, grant_bad = 0, bank_bad = 0, rsp_bad = 0, xz = 0;",
          "    bit was_read [N];", "    int was_bank [N];", "    logic [63:0] bank_rd_next [B];",
          "    logic [MAW-1:0] row [N];", "    real t0, t1;",
          "    // the falling edge of cycle t: grants, the banks' requests, cycle t-1's read responses",
          "    always @(negedge clock) if (!reset && t >= 0 && t <= CYC) begin",
          "        if ($isunknown(q_ready) || $isunknown(m_valid) || $isunknown(p_valid)) xz++;",
          "        for (int i = 0; i < N; i++) if (t >= 1 && was_read[i]) begin",
          "            if (!p_valid[i] || p_data[i] !== m_rdata[was_bank[i]]) begin",
          "                rsp_bad++;",
          "                if (rsp_bad <= 5) $display(\"TB: FAIL: cycle %0d input %0d response %b %h\", t, i, p_valid[i], p_data[i]);",
          "            end",
          "        end",
          "        if (t < CYC) begin",
          "            if ((q_valid & q_ready) !== {N{1'b1}}) begin",
          "                grant_bad++;",
          "                if (grant_bad <= 5) $display(\"TB: FAIL: cycle %0d grants %b\", t, q_valid & q_ready);",
          "            end",
          "            grants += $countones(q_valid & q_ready);",
          "            for (int b = 0; b < B; b++) begin",
          "                int i;",
          "                i = (b - t) % B;",
          "                if (i < 0) i += B;",
          "                if (i < N) begin",
          "                    if (!m_valid[b] || m_addr[b] !== row[i] || m_write[b] !== q_write[i] ||",
          "                        (q_write[i] && (m_wdata[b] !== q_data[i] || m_strb[b] !== 8'hff))) begin",
          "                        bank_bad++;",
          "                        if (bank_bad <= 5) $display(\"TB: FAIL: cycle %0d bank %0d from input %0d\", t, b, i);",
          "                    end",
          "                end else if (m_valid[b]) begin",
          "                    bank_bad++;",
          "                    if (bank_bad <= 5) $display(\"TB: FAIL: cycle %0d bank %0d valid with no input\", t, b);",
          "                end",
          "                bank_rd_next[b] = (i < N && !q_write[i]) ? {$urandom, $urandom} : m_rdata[b];",
          "            end",
          "            for (int i = 0; i < N; i++) begin was_read[i] = !q_write[i]; was_bank[i] = (i + t) % B; end",
          "        end else for (int i = 0; i < N; i++) was_read[i] = 0;",
          "    end",
          "    // at the rising edge that starts cycle c: cycle c's requests (cycle CYC: none); inputs 0 .. RO-1 read,",
          "    // RO .. RO+WO-1 write, the rest write on odd cycles (q_write and q_data model the tied ports as well)",
          "    task automatic apply(input int c);",
          "        for (int i = 0; i < N; i++) begin",
          "            row[i] = MAW'($urandom);",
          "            q_valid[i] <= c < CYC;",
          "            q_write[i] <= (i < RO) ? 1'b0 : (i < RO + WO) ? 1'b1 : 1'(c % 2);",
          "            q_addr[i] <= {row[i], BB'((i + c) % B), 3'b000};",
          "            q_data[i] <= (i >= RO && (i < RO + WO || c % 2)) ? {$urandom, $urandom} : q_data[i];",
          "        end",
          "    endtask",
          "    initial begin",
          "        repeat (5) @(posedge clock);",
          "        @(negedge clock) reset = 1'b0;",
          "        repeat (3) @(posedge clock);",
          "        @(posedge clock);                  // cycle 0's requests: the window's first edge",
          "        t0 = $realtime - T_NS / 4;",
          "        t = 0;",
          "        apply(0);",
          "        while (t < CYC) begin",
          "            @(posedge clock);",
          "            for (int b = 0; b < B; b++) m_rdata[b] <= bank_rd_next[b];",
          "            t++;",
          "            apply(t);",
          "        end",
          "        @(posedge clock);                  // after cycle CYC's falling edge (its responses checked)",
          "        t1 = $realtime - T_NS / 4;",
          "        t = CYC + 1;",
          "        repeat (2) @(posedge clock);",
          "        $display(\"TB: window busy t0_ns %0.3f t1_ns %0.3f cycles %0d\", t0, t1, CYC + 1);",
          "        $display(\"TB: grants %0d expected %0d grant_cycles_bad %0d bank_mismatches %0d rsp_mismatches %0d xz %0d\",",
          "                 grants, N * CYC, grant_bad, bank_bad, rsp_bad, xz);",
          "        $finish;",
          "    end",
          "endmodule"]
    return "\n".join(L) + "\n"
