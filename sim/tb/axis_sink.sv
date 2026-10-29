// sim/tb/axis_sink.sv - AXI4-Stream sink for the gate-level power TB (sim/pwr.py).
//
// Always ready. At the falling edge before each rising edge it samples TVALID and TDATA: a
// valid beat is the handshake of the next edge; it is compared with the expected beat. Any X or Z
// on TVALID after reset, or in TDATA while valid, is an error. Expected data by plusargs:
//   +<NAME>_HEX=<file>    $readmemh file of the expected beats (sim/ref.py)
//   +<NAME>_BEATS=<n>     beats expected
// `complete` rises once every expected beat has arrived.
`timescale 1ns/1ps

module axis_sink #(
    parameter int    DW   = 64,
    parameter string NAME = "C"
) (
    input  logic          clk,
    input  logic          rst_n,
    input  logic [DW-1:0] tdata,
    input  logic          tvalid,
    output logic          tready = 1'b1,
    output logic          complete = 1'b0
);
    logic [DW-1:0] mem [];
    int   beats, n, mism, xerr;
    string file;

    initial begin
        if (!$value$plusargs({NAME, "_HEX=%s"}, file)) $fatal(1, "axis_sink %s: +%s_HEX=<file> missing", NAME, NAME);
        if (!$value$plusargs({NAME, "_BEATS=%d"}, beats) || beats < 1)
            $fatal(1, "axis_sink %s: +%s_BEATS=<n> missing", NAME, NAME);
        mem = new[beats];
        $readmemh(file, mem);
    end

    always @(negedge clk) begin
        if (rst_n === 1'b1 && $isunknown(tvalid)) begin
            xerr++;
            if (xerr <= 5) $display("TB: FAIL: %s_TVALID is %b at %0t", NAME, tvalid, $realtime);
        end
        if (tvalid === 1'b1) begin
            if ($isunknown(tdata)) begin
                xerr++;
                if (xerr <= 5) $display("TB: FAIL: X/Z in %s_TDATA, beat %0d at %0t: %h", NAME, n, $realtime, tdata);
            end
            if (n >= beats) begin
                mism++;
                if (mism <= 5) $display("TB: FAIL: extra %s beat %0d at %0t: %h", NAME, n, $realtime, tdata);
            end else if (tdata !== mem[n]) begin
                mism++;
                if (mism <= 5) begin
                    $display("TB: FAIL: %s beat %0d at %0t", NAME, n, $realtime);
                    for (int l = 0; l < DW / 64; l++)
                        if (tdata[64*l +: 64] !== mem[n][64*l +: 64])
                            $display("TB:         lane %0d: got %h, expected %h", l, tdata[64*l +: 64], mem[n][64*l +: 64]);
                end
            end
            n++;
            if (n == beats) complete <= 1'b1;
        end
    end

    final $display("TB: sink %s: beats %0d expected %0d mismatches %0d xz %0d", NAME, n, beats, mism, xerr);
endmodule
