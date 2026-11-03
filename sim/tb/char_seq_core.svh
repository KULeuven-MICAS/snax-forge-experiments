// sim/tb/char_seq_core.svh - the part every CHAR1 sequencer shares (sim/tb/char_<kind>_seq.sv), `include'd in
// the module body. The module declares the parameters T_NS, NI (64-bit data inputs) and NO (64-bit outputs) and
// the ports clk, rst, data [64*NI-1:0] and out [64*NO-1:0].
//
// Clock T_NS (10 ns). Reset asynchronous, active high: rst high from time 0 for 5 rising edges, released at a
// falling edge (no race with the flops' asynchronous reset). Then slots, one per cycle (sim/sources/char.py,
// schedule()): at a slot's rising edge its inputs are applied (nonblocking, after the flops have taken the slot
// before), as SYN1 and SYN2's TBs and a block's neighbours inside an accelerator change them; at its falling edge
// the outputs are sampled and compared with the next expected line; the next rising edge takes the slot. 4 settle
// slots with every input low, then per window one lead-in slot of the window's own kind, outside every window,
// then the window's slots. A window runs from a quarter cycle before its first slot's rising edge to a quarter
// cycle before the rising edge after its last slot: its rising edges are its own slots' input changes and the
// captures of the lead-in and its own slots but the last (which falls on the next lead-in's edge), so it holds
// only its own kind's work, and no event sits at either end. A change of the outputs between two of its samples
// is counted. Dumping runs from the rising edge before the first window (the first lead-in's) to the rising edge
// after the last (docs/PITFALLS.md Q6); sim/pwr.py cuts each window out of the VCD. $dumpvars is in the
// generated top.
//
// Plusargs: +DATA_HEX=<file> +DATA_N=<n> (the new data beats in the order the slots take them, data_in[0] in the
// low bits), +EXP_HEX=<file> +EXP_N=<n> (the expected outputs at every slot's falling edge, outs[0] in the low
// bits). Prints, for sim/pwr.py:
//   TB: window <name> t0_ns <t0> t1_ns <t1> cycles <c> fires <f>
//   TB: changes <name> <n>
//   TB: samples <k> of <n> mismatches <m> xz <x> beats <b> of <n>

    always #(T_NS / 2) clk = ~clk;

    logic [64*NI-1:0] beats [];
    logic [64*NO-1:0] exps  [];
    int    n_beats, n_exps, bi = 0, k = 0, mism = 0, xz = 0;
    string bfile, efile;
    bit    dump_armed = 1'b0;

    initial begin
        if (!$value$plusargs("DATA_HEX=%s", bfile)) $fatal(1, "char seq: +DATA_HEX=<file> missing");
        if (!$value$plusargs("DATA_N=%d", n_beats) || n_beats < 1) $fatal(1, "char seq: +DATA_N=<n> missing");
        if (!$value$plusargs("EXP_HEX=%s", efile)) $fatal(1, "char seq: +EXP_HEX=<file> missing");
        if (!$value$plusargs("EXP_N=%d", n_exps) || n_exps < 1) $fatal(1, "char seq: +EXP_N=<n> missing");
        beats = new[n_beats];
        exps  = new[n_exps];
        $readmemh(bfile, beats);
        $readmemh(efile, exps);
    end

    // The open window ("" outside the windows: settle and lead-in slots)
    string            w_name = "";
    real              w_t0;
    int               w_cycles, w_fires, w_changes;
    logic [64*NO-1:0] w_prev;

    // At a slot's falling edge: compare with the next expected line; count a change inside the open window
    task automatic sample();
        logic [64*NO-1:0] o;
        @(negedge clk);
        o = out;
        if ($isunknown(o)) begin
            xz++;
            if (xz <= 5) $display("TB: FAIL: X/Z on the outputs at sample %0d, %0t: %h", k, $realtime, o);
        end else if (k >= n_exps) begin
            mism++;
            if (mism <= 5) $display("TB: FAIL: sample %0d past the %0d expected", k, n_exps);
        end else if (o !== exps[k]) begin
            mism++;
            if (mism <= 5) begin
                $display("TB: FAIL: sample %0d at %0t", k, $realtime);
                for (int l = 0; l < NO; l++)
                    if (o[64*l +: 64] !== exps[k][64*l +: 64])
                        $display("TB:         out %0d: got %h, expected %h", l, o[64*l +: 64], exps[k][64*l +: 64]);
            end
        end
        if (w_name != "" && o !== w_prev) w_changes++;
        w_prev = o;
        k++;
    endtask

    task automatic close_window();
        if (w_name != "") begin
            $display("TB: window %s t0_ns %0.3f t1_ns %0.3f cycles %0d fires %0d", w_name, w_t0,
                     $realtime - T_NS / 4, w_cycles, w_fires);
            $display("TB: changes %s %0d", w_name, w_changes);
        end
        w_name = "";
    endtask

    // A slot's rising edge: dumping starts at the first lead-in's; the slot belongs to window `name` ("": none)
    task automatic enter(input string name, input bit fired);
        @(posedge clk);
        if (dump_armed) begin
            $dumpon;
            dump_armed = 1'b0;
        end
        if (name != w_name) begin
            close_window();
            if (name != "") begin
                w_name = name;
                w_t0 = $realtime - T_NS / 4;
                w_cycles = 0;
                w_fires = 0;
                w_changes = 0;
            end
        end
        if (name != "") begin
            w_cycles++;
            if (fired) w_fires++;
        end
    endtask

    // The next data beat onto `data` (nonblocking: after the flops have taken the slot before)
    task automatic next_beat();
        if (bi >= n_beats) $fatal(1, "char seq: slot %0d wants beat %0d of %0d", k, bi, n_beats);
        data <= beats[bi];
        bi++;
    endtask

    // Reset, then `n` settle slots with every input low (each sampled); dumping is armed for the next slot
    task automatic reset_and_settle(input int n);
        repeat (5) @(posedge clk);
        @(negedge clk) rst = 1'b0;
        for (int i = 0; i < n; i++) begin
            enter("", 1'b0);
            sample();
        end
        dump_armed = 1'b1;
    endtask

    // After the last slot: the last window closes at the next rising edge, dumping off there, the summary
    task automatic finish_run();
        @(posedge clk);
        close_window();
        $dumpoff;
        $dumpflush;
        $display("TB: samples %0d of %0d mismatches %0d xz %0d beats %0d of %0d", k, n_exps, mism, xz, bi, n_beats);
        $finish;
    endtask
