// sim/tb/char_pack_seq.sv - CHAR2 sequencer of kind pack (FifoPacker): pins in_valid, out_ready, clear and last,
// as a packed output's group drives them inside an accelerator (ShellWrapper: in_valid the group's output valid,
// out_ready the writer's ready, clear the start, last the run's last result). The outputs compared are out_bits,
// out_valid and in_ready (the generated top's choice).
// After 4 settle slots the start (clear, no push, outside every window), then the windows (sim/sources/char.py
// schedule(), CYCLES = 128 each), each after one lead-in slot of its own kind (outside every window,
// char_seq_core.svh):
//   busy     a push every cycle (in_valid, new data), out_ready high, clear and last low; the lead-in a push
//   idle     no push (in_valid low), data and out_ready held; the lead-in the same
// A fire is a push. The shared part is char_seq_core.svh.
`timescale 1ns/1ps

module char_pack_seq #(
    parameter real T_NS   = 10.0,
    parameter int  NI     = 1,
    parameter int  NO     = 1,
    parameter int  CYCLES = 128
) (
    output logic             clk       = 1'b0,
    output logic             rst       = 1'b1,
    output logic [64*NI-1:0] data      = '0,
    output logic             in_valid  = 1'b0,
    output logic             out_ready = 1'b0,
    output logic             clear     = 1'b0,
    output logic             last      = 1'b0,
    input  logic [64*NO-1:0] out
);
`include "char_seq_core.svh"

    task automatic slot(input string win, input bit push, input bit clr);
        enter(win, push);
        in_valid  <= push;
        out_ready <= 1'b1;
        clear     <= clr;
        last      <= 1'b0;
        if (push) next_beat();
        sample();
    endtask

    initial begin : run
        reset_and_settle(4);
        slot("", 1'b0, 1'b1);                                           // the start
        slot("", 1'b1, 1'b0);                                           // lead-in: a push
        for (int i = 0; i < CYCLES; i++) slot("busy", 1'b1, 1'b0);
        slot("", 1'b0, 1'b0);
        for (int i = 0; i < CYCLES; i++) slot("idle", 1'b0, 1'b0);
        finish_run();
    end
endmodule
