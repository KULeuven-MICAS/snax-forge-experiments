// sim/tb/char_slice_seq.sv - sequencer of kind slice (FifoSlicer): pins in_valid, out_ready, enable and clear, as a
// sliced input's group drives them inside an accelerator (ShellWrapper: in_valid the reader's valid, out_ready the
// unit's ready, enable the group's busy, clear the start). The outputs compared are out_bits (through out_valid,
// the generated top's choice: the data register has no reset), out_valid and in_ready.
// After 4 settle slots the start (clear, enable low, no word offered, outside every window), then the windows
// (sim/sources/char.py schedule(), CYCLES = 128 each), each after one lead-in slot of its own kind (outside every
// window, char_seq_core.svh):
//   busy     enable high, the input valid, the output ready: a pop every cycle, a take every R cycles (the last
//            pop's), a new word in the slot after each take; the lead-in offers word 0, taken at its edge
//   idle     enable low, the output not ready, the input valid: no pop, no take; the lead-in offers the next word,
//            held through the window
// A fire is a pop. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_slice_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  R      = 2,
    parameter int  CYCLES = 128
) (
    output logic             clk       = 1'b0,
    output logic             rst       = 1'b1,
    output logic [64*NI-1:0] data      = '0,
    output logic             in_valid  = 1'b0,
    output logic             out_ready = 1'b0,
    output logic             enable    = 1'b0,
    output logic             clear     = 1'b0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit pop, input bit word, input bit iv, input bit ordy, input bit en,
                        input bit clr);
        enter(win, pop);
        in_valid  <= iv;
        out_ready <= ordy;
        enable    <= en;
        clear     <= clr;
        if (word) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b0, 1'b0, 1'b0, 1'b1, 1'b0, 1'b1);                           // the start
        slot("", 1'b0, 1'b1, 1'b1, 1'b1, 1'b1, 1'b0);                           // lead-in: word 0, taken
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1, (i % R) == 0, 1'b1, 1'b1, 1'b1, 1'b0);
        slot("", 1'b0, 1'b1, 1'b1, 1'b0, 1'b0, 1'b0);                           // lead-in: the next word, held
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, 1'b0, 1'b1, 1'b0, 1'b0, 1'b0);
        finish_run();
    end
endmodule
