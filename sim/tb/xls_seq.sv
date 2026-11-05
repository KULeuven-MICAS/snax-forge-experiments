// sim/tb/xls_seq.sv - XLS cfg-channel sequencer for the gate-level power TB (sim/pwr.py, docs/DECISIONS.md X44).
//
// Clock T_NS (10 ns). Reset synchronous: rst_n low for 5 cycles, then 2 idle cycles; the generated top drives
// XLS's active-high `rst` with ~rst_n. One run:
//   go       the sources present beat 0 at the edge after the second idle cycle, one cycle before the cfg beat
//   cfg      the cfg beat (+CFG=<hex>, the fields packed by sim/pwr.py) with cfg_valid, held until a rising edge
//            samples cfg_ready = 1: the cfg transfer edge, the start of the task
//   window   DUT outputs are sampled at falling edges, where nothing toggles. The window opens at the falling edge
//            before the cfg transfer edge and closes at the falling edge after the rising edge that transfers the
//            last output beat (every sink complete): cycles = the rising edges inside it, both transfer edges
//            included, XLS's cycles + 1 (its datapath is combinational: the last beat is computed in the cycle
//            that ends at its transfer edge). Dumping runs from the edge that raises cfg_valid ($dumpon) to the
//            edge after the window ($dumpoff), half a cycle or more around it (PITFALLS Q6); vcd2saif -time cuts it.
//   end      $finish once the window has closed
// +TIMEOUT=<cycles> (default 10000) fails a run that does not end.
// Prints 'TB: window t0_ns <t0> t1_ns <t1> cycles <n>' for sim/pwr.py.
`timescale 1ns/1ps

module xls_seq #(
    parameter real T_NS = 10.0,
    parameter int  CW   = 64
) (
    output logic          clk       = 1'b0,
    output logic          rst_n     = 1'b0,
    output logic          go        = 1'b0,
    output logic [CW-1:0] cfg_data  = '0,
    output logic          cfg_valid = 1'b0,
    input  logic          cfg_ready,
    input  logic          sinks_complete
);
    always #(T_NS / 2) clk = ~clk;

    logic [CW-1:0] cfg = '0;
    longint negs = 0;           // falling edges so far
    longint n_open = 0, n_close = 0;
    real    t_open = 0.0, t_close = 0.0;
    bit     opened = 1'b0, closed = 1'b0;
    logic   ready_s = 1'b0;
    int     timeout = 10000;

    initial if (!$value$plusargs("CFG=%h", cfg)) $fatal(1, "xls_seq: +CFG=<hex> missing");

    always @(negedge clk) begin
        negs++;
        ready_s = cfg_ready;
        if (!opened && cfg_valid === 1'b1 && cfg_ready === 1'b1) begin     // the next edge transfers cfg
            opened = 1; n_open = negs; t_open = $realtime;
        end else if (opened && !closed && sinks_complete === 1'b1) begin   // the edge before took the last beat
            closed = 1; n_close = negs; t_close = $realtime;
        end
    end

    bit dump_off = 1'b0;
    always @(posedge clk) if (closed && !dump_off) begin   // the edge after the window
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
        repeat (2) @(posedge clk);   // one cycle before the cfg beat
        $dumpon;
        cfg_data  <= cfg;
        cfg_valid <= 1'b1;
        @(posedge clk);
        while (ready_s !== 1'b1) @(posedge clk);   // this edge sampled cfg_ready = 1: the transfer
        cfg_valid <= 1'b0;
        wait (closed);
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
