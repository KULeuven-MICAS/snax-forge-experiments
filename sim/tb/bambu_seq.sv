// sim/tb/bambu_seq.sv - Bambu start/done sequencer for the gate-level power TB (sim/pwr.py, docs/DECISIONS.md X44).
//
// Clock T_NS (10 ns). Reset synchronous, active low (Bambu's `reset`): rst_n low for 5 cycles, then 2 idle cycles.
// The run-time pins (loop_count, len, alpha) are plain inputs the generated top drives from time 0, before reset
// is released, and holds for the whole run (Bambu reads them on every iteration). One run:
//   go       the sources present beat 0 at the edge after the second idle cycle, one cycle before the start
//   start    start_port high for one cycle (hls-exercises tb/bambu.svh's bambu_ctl pulse)
//   window   DUT outputs are sampled at falling edges, where nothing toggles. The window opens at the falling edge
//            before the first rising edge that samples start_port = 1 and closes at the falling edge before the
//            first rising edge that samples done_port = 1: cycles = the rising edges inside it, Bambu's
//            cycles_done (start pulse to done_port). Dumping runs from the edge that raises start_port ($dumpon)
//            to the done edge ($dumpoff), half a cycle around the window (PITFALLS Q6); vcd2saif -time cuts it.
//            $dumpvars is in the generated top, which knows the DUT's scopes.
//   end      $finish once the window has closed and every sink is complete
// +TIMEOUT=<cycles> (default 10000) fails a run that does not end.
// Prints 'TB: window t0_ns <t0> t1_ns <t1> cycles <n>' for sim/pwr.py.
`timescale 1ns/1ps

module bambu_seq #(
    parameter real T_NS = 10.0
) (
    output logic clk   = 1'b0,
    output logic rst_n = 1'b0,
    output logic go    = 1'b0,
    output logic start = 1'b0,
    input  logic done,
    input  logic sinks_complete
);
    always #(T_NS / 2) clk = ~clk;

    longint negs = 0;           // falling edges so far
    longint n_open = 0, n_close = 0;
    real    t_open = 0.0, t_close = 0.0;
    bit     opened = 1'b0, closed = 1'b0;
    int     timeout = 10000;

    always @(negedge clk) begin
        negs++;
        if (!opened && start === 1'b1) begin
            opened = 1; n_open = negs; t_open = $realtime;
        end else if (opened && !closed && done === 1'b1) begin
            closed = 1; n_close = negs; t_close = $realtime;
        end
    end

    bit dump_off = 1'b0;
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
        repeat (2) @(posedge clk);   // one cycle before the start
        $dumpon;
        start <= 1'b1;
        @(posedge clk);         // the first edge sampling start_port = 1
        start <= 1'b0;
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
