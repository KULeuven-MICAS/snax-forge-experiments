// sim/probe/tb_vecadd_opt_w8.sv
// Gate-level testbench for done/vecadd/opt_w8 (Vitis's vecadd, W = 8, int64), zero delay.
// The power probe of results/hls/runs/2026-10-29_pwr_step0.md: one run of n512 (64 beats),
// with $stop at each SAIF window boundary for sim/probe/run.do.
//
// Plusargs:
//   +STIM=<dir>   folder with A.hex, B.hex, C.hex (sim/probe/make_vectors.py); required
//   +NOSTOP       no $stop at the window boundaries (plain functional or speed runs)
//   +RUNS=<n>     kernel runs back to back (default 1; > 1 only for speed runs, with +NOSTOP)
//
// Power-on state: Vitis's RTL starts its unreset registers (b_fu_76, the beat counter) at 0
// with an `initial` block, which the netlist does not have; in gate-level zero-delay
// simulation they start X and the X stays (DC's start-clear logic also depends on the
// X compare), so ap_done never rises. vopt +initreg+0 sets every reg and UDP to 0 at
// time 0, as the RTL's initial blocks do.
//
// Protocol (Vitis ap_ctrl_hs, AXI4-Stream, ap_vld pin). The TB drives every input with a
// nonblocking assignment at the rising edge and samples the DUT at the rising edge.
//   reset    ap_rst_n is synchronous and active low: low for 5 cycles, then 3 idle cycles.
//   start    ap_start rises and stays high until an edge samples ap_ready = 1.
//   pin      loop_count = 64; loop_count_ap_vld is high for one cycle, the first ap_start
//            cycle (bench/include/lanes.h). loop_count keeps its value afterwards.
//   A, B     always valid; each holds its beat until TVALID && TREADY, then the next. After
//            the last beat it holds the last beat.
//   C        C_TREADY = 1; every beat is captured on the handshake and compared; any X or Z
//            in C_TDATA while C_TVALID = 1 fails.
//   cycles   rising edges from the first edge that samples ap_start = 1 to the first edge
//            that samples ap_done = 1.
//
// SAIF windows. The DUT changes only just after rising edges, so the boundaries sit on
// falling edges: nothing toggles there, and a window from the falling edge before edge s
// to the falling edge before edge d holds exactly the transitions of edges s .. d-1.
//   busy  from the falling edge before the first start edge to the one before the done edge
//         ((done - start) cycles)
//   idle  the 200 cycles after that: no start, inputs held
// $stop #1 opens busy, #2 closes busy and opens idle, #3 closes idle; then $finish.
`timescale 1ns/1ps

module tb_vecadd_opt_w8;
    localparam int    W        = 8;
    localparam int    DW       = 64 * W;
    localparam int    BEATS    = 64;
    localparam real   T_NS     = 10.0;   // the synthesis clock
    localparam int    IDLE     = 200;
    localparam int    TIMEOUT  = 10000;  // cycles per run

    logic          ap_clk   = 1'b0;
    logic          ap_rst_n = 1'b0;
    logic          ap_start = 1'b0;
    wire           ap_done, ap_idle, ap_ready;
    logic [DW-1:0] A_TDATA  = '0;
    logic          A_TVALID = 1'b0;
    wire           A_TREADY;
    logic [DW-1:0] B_TDATA  = '0;
    logic          B_TVALID = 1'b0;
    wire           B_TREADY;
    wire  [DW-1:0] C_TDATA;
    wire           C_TVALID;
    logic          C_TREADY = 1'b1;
    logic [31:0]   loop_count        = '0;
    logic          loop_count_ap_vld = 1'b0;

    vecadd dut (
        .ap_clk, .ap_rst_n, .ap_start, .ap_done, .ap_idle, .ap_ready,
        .A_TDATA, .A_TVALID, .A_TREADY,
        .B_TDATA, .B_TVALID, .B_TREADY,
        .C_TDATA, .C_TVALID, .C_TREADY,
        .loop_count, .loop_count_ap_vld
    );

    always #(T_NS / 2) ap_clk = ~ap_clk;

    logic [DW-1:0] mem_a [BEATS];
    logic [DW-1:0] mem_b [BEATS];
    logic [DW-1:0] mem_c [BEATS];
    string stim;
    bit    nostop;
    int    runs = 1;

    // Rising edges since time 0, and the events of the current run
    longint cyc = 0;
    always @(posedge ap_clk) cyc <= cyc + 1;

    int a_i, b_i, c_i, mism, xerr;
    longint t_start, t_done;
    bit     seen_start, seen_done;

    // A and B: hold the beat until the handshake, then the next one
    always @(posedge ap_clk) begin
        if (A_TVALID && A_TREADY && a_i < BEATS - 1) begin
            a_i     <= a_i + 1;
            A_TDATA <= mem_a[a_i + 1];
        end else if (A_TVALID && A_TREADY) begin
            a_i <= BEATS;
        end
        if (B_TVALID && B_TREADY && b_i < BEATS - 1) begin
            b_i     <= b_i + 1;
            B_TDATA <= mem_b[b_i + 1];
        end else if (B_TVALID && B_TREADY) begin
            b_i <= BEATS;
        end
    end

    // C: capture and compare on the handshake; X/Z while valid fails
    always @(posedge ap_clk) begin
        if (ap_rst_n && $isunknown(C_TVALID)) begin
            xerr++;
            $display("FAIL: C_TVALID is %b at cycle %0d", C_TVALID, cyc);
        end
        if (C_TVALID === 1'b1) begin
            if ($isunknown(C_TDATA)) begin
                xerr++;
                $display("FAIL: X/Z in C_TDATA at cycle %0d, beat %0d: %h", cyc, c_i, C_TDATA);
            end
            if (C_TREADY) begin
                if (c_i >= BEATS) begin
                    mism++;
                    $display("FAIL: extra C beat %0d at cycle %0d: %h", c_i, cyc, C_TDATA);
                end else if (C_TDATA !== mem_c[c_i]) begin
                    mism++;
                    if (mism <= 10) begin
                        $display("FAIL: C beat %0d at cycle %0d", c_i, cyc);
                        for (int l = 0; l < W; l++)
                            if (C_TDATA[64*l +: 64] !== mem_c[c_i][64*l +: 64])
                                $display("        lane %0d: got %h, expected %h", l,
                                         C_TDATA[64*l +: 64], mem_c[c_i][64*l +: 64]);
                    end
                end
                c_i++;
            end
        end
    end

    // Cycle count: first edge sampling ap_start = 1 to first edge sampling ap_done = 1
    always @(posedge ap_clk) begin
        if (ap_start === 1'b1 && !seen_start) begin
            seen_start = 1;
            t_start    = cyc;
        end
        if (seen_start && !seen_done && ap_done === 1'b1) begin
            seen_done = 1;
            t_done    = cyc;
        end
    end

    initial begin : timeout
        automatic int n = 1;
        void'($value$plusargs("RUNS=%d", n));
        repeat (TIMEOUT * n) @(posedge ap_clk);
        $display("FAIL: timeout after %0d cycles (start %0b, done %0b, C beats %0d)",
                 TIMEOUT * n, seen_start, seen_done, c_i);
        $finish;
    end

    task automatic window(string what);
        if (!nostop) begin
            $display("TB: $stop %s at %0t (cycle %0d)", what, $time, cyc);
            $stop;
        end
    endtask

    // Window boundaries, on falling edges (first run only)
    bit idle_over;
    initial begin : windows
        do @(negedge ap_clk); while (ap_start !== 1'b1);
        window("1: busy start");                 // the next edge is the first start edge
        do @(negedge ap_clk); while (ap_done !== 1'b1);
        window("2: busy end, idle start");       // the next edge is the done edge
        repeat (IDLE) @(negedge ap_clk);
        window("3: idle end");
        idle_over = 1;
    end

    initial begin : main
        automatic int total_mism = 0, total_xerr = 0, total_beats = 0;
        if (!$value$plusargs("STIM=%s", stim)) $fatal(1, "TB: +STIM=<dir> is required");
        nostop = $test$plusargs("NOSTOP");
        void'($value$plusargs("RUNS=%d", runs));
        if (runs > 1 && !nostop) $fatal(1, "TB: +RUNS > 1 needs +NOSTOP");
        $readmemh({stim, "/A.hex"}, mem_a);
        $readmemh({stim, "/B.hex"}, mem_b);
        $readmemh({stim, "/C.hex"}, mem_c);
        $display("TB: stimulus %s, %0d beats of %0d lanes, clock %.1f ns, runs %0d",
                 stim, BEATS, W, T_NS, runs);

        // Reset: 5 cycles low, then 3 idle cycles
        repeat (5) @(posedge ap_clk);
        ap_rst_n <= 1'b1;
        repeat (3) @(posedge ap_clk);

        for (int r = 0; r < runs; r++) begin
            a_i = 0; b_i = 0; c_i = 0; mism = 0; xerr = 0;
            seen_start = 0; seen_done = 0;
            A_TDATA  <= mem_a[0];
            B_TDATA  <= mem_b[0];
            A_TVALID <= 1'b1;
            B_TVALID <= 1'b1;
            @(posedge ap_clk);
            // The first start cycle: ap_start and the one-cycle ap_vld pulse
            ap_start          <= 1'b1;
            loop_count        <= BEATS;
            loop_count_ap_vld <= 1'b1;
            @(posedge ap_clk);  // the first edge sampling ap_start = 1
            loop_count_ap_vld <= 1'b0;
            // Hold ap_start until an edge samples ap_ready
            while (ap_ready !== 1'b1) @(posedge ap_clk);
            ap_start <= 1'b0;
            // ap_done and the last C beat may come with ap_ready or later
            while (!seen_done || c_i < BEATS) @(posedge ap_clk);
            total_mism  += mism;
            total_xerr  += xerr;
            total_beats += c_i;
            $display("TB: run %0d: %0d C beats, %0d mismatches, %0d X/Z errors, cycles %0d (start edge %0d, done edge %0d, last C beat edge %0d)",
                     r, c_i, mism, xerr, t_done - t_start, t_start, t_done, cyc - 1);
        end
        disable timeout;
        // The idle window: no start, inputs held
        if (nostop) repeat (IDLE) @(negedge ap_clk);
        else wait (idle_over);
        if (total_mism == 0 && total_xerr == 0 && total_beats == runs * BEATS)
            $display("TB: PASS: %0d beats, 0 mismatches, cycles %0d (cosim 66)", total_beats, t_done - t_start);
        else
            $display("TB: FAIL: %0d beats (expected %0d), %0d mismatches, %0d X/Z errors",
                     total_beats, runs * BEATS, total_mism, total_xerr);
        $finish;
    end
endmodule
