// sim/tb/char_serial_seq.sv - CHAR1 sequencer of kind serial (SerialAccumulate): pins read, lane and first, as
// its control unit drives them (span = W lanes: lane k read in cycle k of a beat, the beat held for its W cycles).
// LW is lane's width, ceil(log2 W); at W = 1 the block has no lane port and the generated top leaves it open.
// The windows (sim/sources/char.py schedule(), CYCLES = 128 beats or cycles) after 4 settle slots, each after
// one lead-in slot of its own kind (outside every window, char_seq_core.svh):
//   busy     read every cycle, lane 0 .. W - 1, a new beat at lane 0, first at lane 0 of the first beat only;
//            lead-in a read of the held beat's lane W - 1
//   busy_t1  the same with first at lane 0 of every beat; lead-in the same
//   idle     read = 0, first = 0, lane and data held, 128 cycles; lead-in the same
//   duty50   read every other cycle (even slots), 128 beats of W reads, a new beat at each lane-0 read, first at
//            the first; the odd slots hold lane and data; lead-in read = 0, held (an odd slot)
// A read is a fire. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_serial_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  W      = 1,
    parameter int  LW     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk   = 1'b0,
    output logic             rst   = 1'b1,
    output logic [64*NI-1:0] data  = '0,
    output logic             read  = 1'b0,
    output logic [LW-1:0]    lane  = '0,
    output logic             first = 1'b0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit nw, input bit rd, input int ln, input bit fst);
        enter(win, rd);
        read  <= rd;
        lane  <= ln[LW-1:0];
        first <= fst;
        if (nw) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b0, 1'b1, W - 1, 1'b0);
        for (int b = 0; b < CYCLES; b++)
            for (int l = 0; l < W; l++) slot("busy", l == 0, 1'b1, l, b == 0 && l == 0);
        slot("", 1'b0, 1'b1, W - 1, 1'b0);
        for (int b = 0; b < CYCLES; b++)
            for (int l = 0; l < W; l++) slot("busy_t1", l == 0, 1'b1, l, l == 0);
        slot("", 1'b0, 1'b0, W - 1, 1'b0);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, 1'b0, W - 1, 1'b0);
        slot("", 1'b0, 1'b0, W - 1, 1'b0);
        for (int b = 0; b < CYCLES; b++)
            for (int l = 0; l < W; l++) begin
                slot("duty50", l == 0, 1'b1, l, b == 0 && l == 0);
                slot("duty50", 1'b0, 1'b0, l, 1'b0);
            end
        finish_run();
    end
endmodule
