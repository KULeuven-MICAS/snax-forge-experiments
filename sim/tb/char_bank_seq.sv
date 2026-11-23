// sim/tb/char_bank_seq.sv - sequencer of kind bank (an accumulating Mac of R >= 2 rows, snax-forge D191): pins
// fire, first, row and drain, as the control unit drives them (row the beat mod R, drain the row before it).
// The windows (sim/sources/char.py schedule(), CYCLES = 128 each) after 4 settle slots:
//   busy     R lead-in slots, the restart of each row in turn (a fire with first at row i, drain i - 1 mod R);
//            then fire every cycle, new data every cycle, first = 0, row = t mod R, drain = t - 1 mod R
//   idle     one lead-in slot, then fire = 0, data, first, row and drain held at busy's last
// The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_bank_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  R      = 2,
    parameter int  RW     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk   = 1'b0,
    output logic             rst   = 1'b1,
    output logic [64*NI-1:0] data  = '0,
    output logic             fire  = 1'b0,
    output logic             first = 1'b0,
    output logic [RW-1:0]    row   = '0,
    output logic [RW-1:0]    drain = '0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit f, input bit fst, input int r, input int d);
        enter(win, f);
        fire  <= f;
        first <= fst;
        row   <= RW'(r);
        drain <= RW'(d);
        if (f) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        for (int i = 0; i < R; i++) slot("", 1'b1, 1'b1, i, (i + R - 1) % R);
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1, 1'b0, i % R, (i + R - 1) % R);
        slot("", 1'b0, 1'b0, (CYCLES - 1) % R, (CYCLES + R - 2) % R);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, 1'b0, (CYCLES - 1) % R, (CYCLES + R - 2) % R);
        finish_run();
    end
endmodule
