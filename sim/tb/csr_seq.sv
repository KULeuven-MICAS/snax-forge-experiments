// sim/tb/csr_seq.sv - snax-forge CSR sequencer for the gate-level power TB (sim/pwr.py, tb.json forge_csr).
//
// The wrapper's CSR port (snax-forge docs/CONTRACTS.md section 17, The wrapper and The CSRs): one request at a
// time, held until csr_req_ready_o, as the Snitch core's is; csr_rsp_ready_i always 1. A write has no response;
// a read is answered in the cycle it is taken.
//
// Clock T_NS (10 ns). Reset asynchronous, active low: rst_ni low from time 0 for 5 cycles, released at a
// falling edge, then 2 idle cycles. Then, from +CSR_HEX=<file> (+CSR_N=<n> lines, {offset[31:0], value[31:0]}
// in hex, START last), each write offered from a rising edge until a falling edge samples csr_req_ready_o = 1
// (taken by the next rising edge). One run:
//   go       rises with the START write: the sources present beat 0 from the next edge, the first busy cycle
//   window   DUT outputs are sampled at falling edges, where nothing toggles. START is accepted in cycle a
//            (the edge e_a ending it takes it); the group is busy in a + 1 .. E and <group>_done_o is high in
//            E + 1, so COUNTER = E - a (C§17). The window opens at the falling edge before e_a (it samples
//            START valid and ready) and closes at the falling edge before e_E, one cycle before the first
//            falling edge that samples done = 1: cycles = rising edges inside it = e_a .. e_{E-1} = E - a
//            (as docs/DECISIONS.md X12 counts an HLS run). Dumping runs from the edge that offers START
//            ($dumpon) to the edge after done is seen ($dumpoff), half a cycle or more around the window
//            (docs/PITFALLS.md Q6); vcd2saif -time cuts the window. $dumpvars is in the generated top.
//   counter  once the window has closed and every sink is complete, COUNTER (+COUNTER_ADDR=<hex>) is read over
//            the CSR port and printed beside the window's cycles
//   end      $finish
// +TIMEOUT=<cycles> (default 10000) fails a run that does not end.
// Prints 'TB: window t0_ns <t0> t1_ns <t1> cycles <n>' and 'TB: counter <c>' for sim/pwr.py.
`timescale 1ns/1ps

module csr_seq #(
    parameter real T_NS = 10.0
) (
    output logic        clk       = 1'b0,
    output logic        rst_n     = 1'b0,
    output logic        go        = 1'b0,
    output logic [31:0] req_addr  = '0,
    output logic [31:0] req_data  = '0,
    output logic        req_write = 1'b0,
    output logic        req_valid = 1'b0,
    input  logic        req_ready,
    input  logic [31:0] rsp_data,
    input  logic        rsp_valid,
    output logic        rsp_ready = 1'b1,
    input  logic        done,
    input  logic        sinks_complete
);
    always #(T_NS / 2) clk = ~clk;

    logic [63:0] writes [];
    int          n_writes, timeout = 10000;
    logic [31:0] counter_addr;
    string       file;

    longint negs = 0;               // falling edges so far
    longint n_open, n_close;
    real    t_open, t_close;
    bit     starting, opened, closed;

    initial begin
        if (!$value$plusargs("CSR_HEX=%s", file)) $fatal(1, "csr_seq: +CSR_HEX=<file> missing");
        if (!$value$plusargs("CSR_N=%d", n_writes) || n_writes < 1) $fatal(1, "csr_seq: +CSR_N=<n> missing");
        if (!$value$plusargs("COUNTER_ADDR=%h", counter_addr)) $fatal(1, "csr_seq: +COUNTER_ADDR=<hex> missing");
        void'($value$plusargs("TIMEOUT=%d", timeout));
        writes = new[n_writes];
        $readmemh(file, writes);
    end

    always @(negedge clk) begin
        negs++;
        if (starting && !opened && req_valid === 1'b1 && req_ready === 1'b1) begin
            opened = 1; n_open = negs; t_open = $realtime;
        end else if (opened && !closed && done === 1'b1) begin
            closed = 1; n_close = negs - 1; t_close = $realtime - T_NS;
        end
    end

    bit dump_off;
    always @(posedge clk) if (closed && !dump_off) begin   // the edge after the first falling edge seeing done
        dump_off = 1;
        $dumpoff;
        $dumpflush;
    end

    // One request from the next rising edge until a falling edge samples ready; it is taken at the edge after.
    // The task samples the DUT's outputs itself at the falling edge (stable there), not a copy another block
    // makes at the same edge, which would race with it.
    task automatic request(input logic [31:0] addr, input logic [31:0] data, input logic write);
        req_addr  <= addr;
        req_data  <= data;
        req_write <= write;
        req_valid <= 1'b1;
        do @(negedge clk); while (req_ready !== 1'b1);
        @(posedge clk);
        req_valid <= 1'b0;
        req_write <= 1'b0;
    endtask

    initial begin : run
        logic [31:0] counter;
        repeat (5) @(posedge clk);
        @(negedge clk) rst_n = 1'b1;    // released between edges: no race with the flops' asynchronous reset
        repeat (2) @(posedge clk);
        for (int i = 0; i < n_writes - 1; i++) request(writes[i][63:32], writes[i][31:0], 1'b1);
        $dumpon;                        // the edge that offers START
        starting = 1;
        go <= 1'b1;
        request(writes[n_writes - 1][63:32], writes[n_writes - 1][31:0], 1'b1);
        wait (closed && sinks_complete);
        @(posedge clk);
        req_addr <= counter_addr; req_data <= '0; req_write <= 1'b0; req_valid <= 1'b1;
        do @(negedge clk); while (req_ready !== 1'b1);
        if (rsp_valid !== 1'b1) $display("TB: FAIL: COUNTER read taken without a response at %0t", $realtime);
        counter = rsp_data;
        @(posedge clk);
        req_valid <= 1'b0;
        @(negedge clk);
        $display("TB: window t0_ns %0.3f t1_ns %0.3f cycles %0d", t_open, t_close, n_close - n_open);
        $display("TB: counter %0d", counter);
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
