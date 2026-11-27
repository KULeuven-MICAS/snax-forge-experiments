// sim/tb/char_halo_seq.sv - char sequencer of kind halo (HaloLink of T taps and W lanes, snax-forge D206): the pin
// load, as its group's control unit drives it. H is the beats it holds, ceil((T - 1) / W).
// One window (sim/sources/char.py schedule(), CYCLES = 128) after 4 settle slots:
//   stream  the link at full rate: a lead-in of H loads (the fill, outside the window), then a load of new data
//           every cycle; every tap reads the held beats and the incoming one
// A load is a fire. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_halo_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 3,
    parameter int  H      = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk  = 1'b0,
    output logic             rst  = 1'b1,
    output logic [64*NI-1:0] data = '0,
    output logic             load = 1'b0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit ld);
        enter(win, ld);
        load <= ld;
        if (ld) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        for (int t = 0; t < H; t++) slot("", 1'b1);
        for (int t = 0; t < CYCLES; t++) slot("stream", 1'b1);
        finish_run();
    end
endmodule
