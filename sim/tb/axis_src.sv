// sim/tb/axis_src.sv - AXI4-Stream source for the gate-level power TB (sim/pwr.py).
//
// Always valid from `go`: drives beat 0 with TVALID = 1, holds each beat until a handshake, then
// the next; after the last beat it holds the last beat (TVALID stays 1). Data comes in by
// plusargs, so one compile serves every size:
//   +<NAME>_HEX=<file>    $readmemh file, one beat per line, lane 0 in the low bits (lanes.h)
//   +<NAME>_BEATS=<n>     beats in the file
// Inputs change only by nonblocking assignment at the rising edge; the handshake is the
// TREADY sampled at the falling edge before it, so nothing races with the DUT's flops.
`timescale 1ns/1ps

module axis_src #(
    parameter int    DW   = 64,
    parameter string NAME = "A"
) (
    input  logic          clk,
    input  logic          go,       // from the sequencer: start presenting beats
    output logic [DW-1:0] tdata  = '0,
    output logic          tvalid = 1'b0,
    input  logic          tready
);
    logic [DW-1:0] mem [];
    int   beats, i;
    logic tready_s;
    string file;

    initial begin
        if (!$value$plusargs({NAME, "_HEX=%s"}, file)) $fatal(1, "axis_src %s: +%s_HEX=<file> missing", NAME, NAME);
        if (!$value$plusargs({NAME, "_BEATS=%d"}, beats) || beats < 1)
            $fatal(1, "axis_src %s: +%s_BEATS=<n> missing", NAME, NAME);
        mem = new[beats];
        $readmemh(file, mem);
    end

    always @(negedge clk) tready_s = tready;

    always @(posedge clk) begin
        if (go && !tvalid) begin
            tvalid <= 1'b1;
            tdata  <= mem[0];
            i      <= 0;
        end else if (tvalid && tready_s === 1'b1 && i < beats - 1) begin
            tdata <= mem[i + 1];
            i     <= i + 1;
        end else if (tvalid && tready_s === 1'b1) begin
            i <= beats;
        end
    end

    final $display("TB: source %s: %0d of %0d beats taken", NAME, i, beats);
endmodule
