// sim/tb/char_link_seq.sv - CHAR1 sequencer of kind link (LinkBuffer of depth D): pins load, wslot and rslot, as
// its group's control unit drives them. SW is the slots' width, ceil(log2 D); at D = 1 the block has no slot
// ports and the generated top leaves them open.
// One window (sim/sources/char.py schedule(), CYCLES = 128) after 4 settle slots:
//   stream  a FIFO at full rate: a lead-in of D loads round the ring (the fill, outside the window), then a load of
//           new data every cycle into slot t mod D with rslot the oldest slot, the same one (read before the edge
//           that overwrites it), so out at cycle t is the beat loaded at t - D
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
        for (int t = 0; t < D; t++) slot("", 1'b1, t, t);
        for (int t = 0; t < CYCLES; t++) slot("stream", 1'b1, t % D, t % D);
        finish_run();
    end
endmodule
