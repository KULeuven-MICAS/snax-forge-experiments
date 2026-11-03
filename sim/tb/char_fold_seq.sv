// sim/tb/char_fold_seq.sv - CHAR1 sequencer of kind fold (Mac in its accumulating form, TreeAccumulate): pins
// fire and first, as a fold's control unit drives them (the out side, NO lanes, is the generated top's choice).
// The windows (sim/sources/char.py schedule(), CYCLES = 128 each) after 4 settle slots, each after one lead-in
// slot of its own kind (outside every window, char_seq_core.svh):
//   busy     fire every cycle, new data every cycle, first = 0; the lead-in is the restart (a fire with first)
//   busy_t1  the same with first on every fire (T = 1); lead-in a fire with first
//   idle     fire = 0, data and first held (first stays at busy_t1's 1: no pin but fire moves); lead-in the same
//   duty50   fire every other cycle (even slots), new data only on fired cycles, first on the first; lead-in
//            fire = 0, held (an odd slot)
// Every firing window starts from a restart. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_fold_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk   = 1'b0,
    output logic             rst   = 1'b1,
    output logic [64*NI-1:0] data  = '0,
    output logic             fire  = 1'b0,
    output logic             first = 1'b0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit f, input bit fst);
        enter(win, f);
        fire  <= f;
        first <= fst;
        if (f) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b1, 1'b1);
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1, 1'b0);
        slot("", 1'b1, 1'b1);
        for (int i = 0; i < CYCLES; i++) slot("busy_t1", 1'b1, 1'b1);
        slot("", 1'b0, 1'b1);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, 1'b1);     // first held at busy_t1's
        slot("", 1'b0, 1'b1);
        for (int i = 0; i < CYCLES; i++) slot("duty50", i % 2 == 0, i == 0);
        finish_run();
    end
endmodule
