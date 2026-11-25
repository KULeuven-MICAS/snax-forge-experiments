// sim/tb/char_lanes_seq.sv - CHAR1 sequencer of kind lanes (SimdLanes): no pins, data only, and its scalars.
// The windows (sim/sources/char.py schedule(), CYCLES = 128 each) after 4 settle slots, each after one lead-in
// slot of its own kind (outside every window, char_seq_core.svh):
//   busy    new a, b every cycle (lead-in: new data)
//   idle    inputs held (lead-in: held)
// A cycle with new data is a fire. The shared part (clock, reset, sampling, windows, dumping) is
// char_seq_core.svh.
//
// Scalars (NK > 0: a SimdLanes reading k, or k1 and k2, from its CSRs, tb.json's scalars): `scal` holds a 64-bit
// slot per scalar pin, a pin on its slot's low bits (not `k`: the core's sample count, PITFALLS Q17). +K_HEX=<file>
// +K_N=<n> give one line per window in the order the windows run (busy, idle), applied at the window's lead-in slot
// and held through the window, as a program writes a CSR once for a job; 0 while settling. With NK = 0 (every other
// point) `scal` is left open and no plusarg read.
`timescale 1ns/1ps

module char_lanes_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 2,
    parameter int  NO     = 1,
    parameter int  NK     = 0,
    parameter int  CYCLES = 128
) (
    output logic             clk  = 1'b0,
    output logic             rst  = 1'b1,
    output logic [64*NI-1:0] data = '0,
    output logic [64*(NK > 0 ? NK : 1)-1:0] scal = '0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    localparam int NWIN = 2;
    logic [64*(NK > 0 ? NK : 1)-1:0] scal_lines [];
    string kfile;
    int    n_ks;

    initial if (NK > 0) begin
        if (!$value$plusargs("K_HEX=%s", kfile)) $fatal(1, "char seq: +K_HEX=<file> missing (NK = %0d)", NK);
        if (!$value$plusargs("K_N=%d", n_ks) || n_ks != NWIN) $fatal(1, "char seq: +K_N=%0d, %0d windows", n_ks, NWIN);
        scal_lines = new[n_ks];
        $readmemh(kfile, scal_lines);
    end

    // kw >= 0: the slot is window kw's lead-in, its scalars applied (nonblocking, with the slot's data)
    task automatic slot(input string win, input bit nw, input int kw = -1);
        enter(win, nw);
        if (NK > 0 && kw >= 0) scal <= scal_lines[kw];
        if (nw) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b1, 0);
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1);
        slot("", 1'b0, 1);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0);
        finish_run();
    end
endmodule
