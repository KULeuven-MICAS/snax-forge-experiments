// sim/tb/char_lanes_seq.sv - CHAR1 sequencer of kind lanes (ElementwiseLanes): no pins, data only.
// The windows (sim/sources/char.py schedule(), CYCLES = 128 each) after 4 settle slots, each after one lead-in
// slot of its own kind (outside every window, char_seq_core.svh):
//   busy    new a, b every cycle (lead-in: new data)
//   idle    inputs held (lead-in: held)
// A cycle with new data is a fire. The shared part (clock, reset, sampling, windows, dumping) is
// char_seq_core.svh.
`timescale 1ns/1ps

module char_lanes_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 2,
    parameter int  NO     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk  = 1'b0,
    output logic             rst  = 1'b1,
    output logic [64*NI-1:0] data = '0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit nw);
        enter(win, nw);
        if (nw) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b1);
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1);
        slot("", 1'b0);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0);
        finish_run();
    end
endmodule
