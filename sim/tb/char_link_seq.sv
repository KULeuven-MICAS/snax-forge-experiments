// sim/tb/char_link_seq.sv - CHAR1 sequencer of kind link (LinkBuffer of depth D): pins load, wslot and rslot, as
// its group's control unit drives them. SW is the slots' width, ceil(log2 D); at D = 1 the block has no slot
// ports and the generated top leaves them open.
// The windows (sim/sources/char.py schedule(), CYCLES = 128 each) after 4 settle slots, each after one lead-in
// slot of its own kind (outside every window, char_seq_core.svh):
//   busy    load every cycle, new data every cycle, wslot stepping round the ring from 0, rslot the slot written
//           the cycle before; lead-in a load of new data into slot D - 1 (the ring's step before 0)
//   idle    load = 0, data and slots held; lead-in the same
//   duty50  load every other cycle (even slots), new data on loaded cycles, wslot stepping on each load, rslot the
//           slot the previous load wrote; the odd slots hold everything; lead-in load = 0, held (an odd slot)
// A load is a fire. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_link_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  D      = 1,
    parameter int  SW     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk   = 1'b0,
    output logic             rst   = 1'b1,
    output logic [64*NI-1:0] data  = '0,
    output logic             load  = 1'b0,
    output logic [SW-1:0]    wslot = '0,
    output logic [SW-1:0]    rslot = '0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit ld, input int ws, input int rs);
        enter(win, ld);
        load  <= ld;
        wslot <= ws[SW-1:0];
        rslot <= rs[SW-1:0];
        if (ld) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b1, D - 1, (2 * D - 2) % D);
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1, i % D, (i + D - 1) % D);
        slot("", 1'b0, (CYCLES - 1) % D, (CYCLES - 2) % D);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, (CYCLES - 1) % D, (CYCLES - 2) % D);
        slot("", 1'b0, (CYCLES - 1) % D, (CYCLES - 2) % D);
        for (int j = 0; j < CYCLES / 2; j++) begin
            slot("duty50", 1'b1, j % D, (j + D - 1) % D);
            slot("duty50", 1'b0, j % D, (j + D - 1) % D);
        end
        finish_run();
    end
endmodule
