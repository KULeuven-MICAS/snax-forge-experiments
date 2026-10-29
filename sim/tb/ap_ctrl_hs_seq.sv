// sim/tb/ap_ctrl_hs_seq.sv - Vitis ap_ctrl_hs sequencer for the gate-level power TB (sim/pwr.py).
//
// Clock T_NS (10 ns). Reset synchronous, active low: 5 cycles low, then 3 idle cycles. One run:
//   go       the sources present beat 0 at the third idle edge, one cycle before the start
//   start    ap_start rises together with `vld` (the config and data pins' ap_vld pulse, one
//            cycle: the first start cycle) and stays high until an edge samples ap_ready = 1
//   window   DUT outputs are sampled at falling edges, where nothing toggles. The busy window
//            opens at the falling edge before the first edge sampling ap_start = 1 and closes at
//            the falling edge before the first edge sampling ap_done = 1: cycles = rising edges
//            inside it (docs/DECISIONS.md X12). Dumping runs from the edge that raises ap_start
//            ($dumpon) to the done edge ($dumpoff), half a cycle around the window, so the clock
//            edges on its boundaries are value changes in the VCD (with $dumpon at the boundary
//            itself, the first falling edge is lost); vcd2saif -time cuts the window.
//            $dumpvars is in the generated top, which knows the DUT's scopes.
//   end      $finish once the window has closed and every sink is complete
// +TIMEOUT=<cycles> (default 10000) fails a run that does not end.
// Prints 'TB: window t0_ns <t0> t1_ns <t1> cycles <n>' for sim/pwr.py.
`timescale 1ns/1ps

module ap_ctrl_hs_seq #(
    parameter real T_NS = 10.0
) (
    output logic clk      = 1'b0,
    output logic rst_n    = 1'b0,
    output logic go       = 1'b0,
    output logic ap_start = 1'b0,
    output logic vld      = 1'b0,
    input  logic ap_done,
    input  logic ap_ready,
    input  logic sinks_complete
);
    always #(T_NS / 2) clk = ~clk;

    longint negs = 0;           // falling edges so far
    longint n_open, n_close;
    real    t_open, t_close;
    bit     opened, closed;
    logic   ready_s;
    int     timeout = 10000;

    always @(negedge clk) begin
        negs++;
        ready_s = ap_ready;
        if (!opened && ap_start === 1'b1) begin
            opened = 1; n_open = negs; t_open = $realtime;
        end else if (opened && !closed && ap_done === 1'b1) begin
            closed = 1; n_close = negs; t_close = $realtime;
        end
    end

    bit dump_off;
    always @(posedge clk) if (closed && !dump_off) begin   // the done edge
        dump_off = 1;
        $dumpoff;
        $dumpflush;
    end

    initial begin : run
        void'($value$plusargs("TIMEOUT=%d", timeout));
        repeat (5) @(posedge clk);
        rst_n <= 1'b1;
        repeat (2) @(posedge clk);
        go <= 1'b1;             // the sources raise TVALID with beat 0 at the next edge,
        repeat (2) @(posedge clk);   // the third idle edge, one cycle before the start
        $dumpon;
        ap_start <= 1'b1;
        vld      <= 1'b1;
        @(posedge clk);         // the first edge sampling ap_start = 1
        vld      <= 1'b0;
        while (ready_s !== 1'b1) @(posedge clk);
        ap_start <= 1'b0;
        wait (closed && sinks_complete);
        @(negedge clk);
        $display("TB: window t0_ns %0.3f t1_ns %0.3f cycles %0d", t_open, t_close, n_close - n_open);
        $finish;
    end

    initial begin : watchdog
        @(posedge rst_n);
        #0 repeat (timeout) @(posedge clk);
        $display("TB: FAIL: timeout after %0d cycles (window opened %0b, closed %0b, sinks complete %0b)",
                 timeout, opened, closed, sinks_complete);
        $finish;
    end
endmodule
