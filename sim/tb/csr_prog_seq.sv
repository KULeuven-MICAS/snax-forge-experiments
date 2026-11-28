// sim/tb/csr_prog_seq.sv - snax-forge program sequencer for the gate-level power TB (sim/pwr.py, tb.json forge_csr
// with sizes.<tag>.program: several jobs, groups or accelerators, docs/DECISIONS.md X120).
//
// The CSR port as csr_seq.sv drives it (snax-forge docs/CONTRACTS.md section 17): one request at a time, held
// until csr_req_ready_o (a busy group holds its writes until its run ends), csr_rsp_ready_i always 1, a read
// answered in the cycle it is taken. Clock T_NS, reset as csr_seq.sv's (5 cycles low, released at a falling
// edge, then 2 idle cycles). Then the program, +OPS_HEX=<file> (+OPS_N=<n> lines of {kind, a, b}, 32 bits
// each, in hex), op by op as the program issues them, its DMA left out:
//   0 write   a CSR write: offset a, value b
//   1 start   START (value 1) at offset a, of group b; go rises with the first, the sources present beat 0 from
//             the next edge
//   2 wait    until group a's done pulses (<group>_done_o, high in E + 1) equal its starts taken: the program's
//             poll on STATUS; the next request from the next rising edge
//   3 counter read BUSY_COUNTER at offset a, printed as 'TB: counter <b> <value>' (b the job)
// window   opens at the falling edge that samples the first START valid and ready (as csr_seq.sv's) and closes
//          one cycle before the first falling edge where every START has been taken and every group's done
//          pulses equal its starts: the rising edges from the first START's to the last run's end E.
//          Dumping from the edge that offers the first START to the edge after the close.
//   end      every op done, the window closed and every sink complete: $finish
// +TIMEOUT=<cycles> (default 10000) fails a run that does not end.
// Prints 'TB: ports first_in <c> last_out <c>' (X119), 'TB: window t0_ns <t0> t1_ns <t1> cycles <n>' and the
// 'TB: counter' lines for sim/pwr.py.
`timescale 1ns/1ps

module csr_prog_seq #(
    parameter real T_NS = 10.0,
    parameter int  NG   = 1           // groups: done[g] is group g's done pin, in tb.json's control.groups order
) (
    output logic          clk       = 1'b0,
    output logic          rst_n     = 1'b0,
    output logic          go        = 1'b0,
    output logic [31:0]   req_addr  = '0,
    output logic [31:0]   req_data  = '0,
    output logic          req_write = 1'b0,
    output logic          req_valid = 1'b0,
    input  logic          req_ready,
    input  logic [31:0]   rsp_data,
    input  logic          rsp_valid,
    output logic          rsp_ready = 1'b1,
    input  logic [NG-1:0] done,
    input  logic          sinks_complete,
    input  logic          in_hs,
    input  logic          out_hs
);
    always #(T_NS / 2) clk = ~clk;

    // the port window (X119), as csr_seq.sv's
    longint pcyc = 0, first_in = -1, last_out = -1;
    always @(posedge clk) if (rst_n === 1'b1) pcyc++;
    always @(negedge clk) if (rst_n === 1'b1) begin
        if (first_in < 0 && in_hs === 1'b1) first_in = pcyc + 1;
        if (out_hs === 1'b1) last_out = pcyc + 1;
    end

    logic [95:0] ops [];
    int          n_ops, n_starts = 0, timeout = 10000;
    string       file;

    int     starts_taken [NG];          // STARTs taken, by group
    int     dones        [NG];          // done pulses seen, by group
    int     taken = 0;                  // STARTs taken, all groups
    bit     is_start = 0;               // the request on the port is a START, of group start_g
    int     start_g = 0;
    longint negs = 0, n_open, n_close;
    real    t_open, t_close;
    bit     opened, closed;

    initial begin
        if (!$value$plusargs("OPS_HEX=%s", file)) $fatal(1, "csr_prog_seq: +OPS_HEX=<file> missing");
        if (!$value$plusargs("OPS_N=%d", n_ops) || n_ops < 1) $fatal(1, "csr_prog_seq: +OPS_N=<n> missing");
        void'($value$plusargs("TIMEOUT=%d", timeout));
        ops = new[n_ops];
        $readmemh(file, ops);
        for (int i = 0; i < n_ops; i++) if (ops[i][95:64] == 1) n_starts++;
        for (int g = 0; g < NG; g++) begin starts_taken[g] = 0; dones[g] = 0; end
    end

    // At each falling edge (nothing toggles there): a START taken, done pulses, the window
    always @(negedge clk) begin
        bit all_done;
        negs++;
        if (is_start && req_valid === 1'b1 && req_ready === 1'b1) begin
            starts_taken[start_g]++;
            taken++;
            if (!opened) begin opened = 1; n_open = negs; t_open = $realtime; end
        end
        for (int g = 0; g < NG; g++) if (done[g] === 1'b1) dones[g]++;
        all_done = 1;
        for (int g = 0; g < NG; g++) if (dones[g] != starts_taken[g]) all_done = 0;
        if (opened && !closed && taken == n_starts && all_done) begin
            closed = 1; n_close = negs - 1; t_close = $realtime - T_NS;
        end
    end

    bit dump_off;
    always @(posedge clk) if (closed && !dump_off) begin
        dump_off = 1;
        $dumpoff;
        $dumpflush;
    end

    // One request from now until a falling edge samples ready; taken at the edge after (csr_seq.sv's).
    task automatic request(input logic [31:0] addr, input logic [31:0] data, input logic write);
        req_addr  <= addr;
        req_data  <= data;
        req_write <= write;
        req_valid <= 1'b1;
        do @(negedge clk); while (req_ready !== 1'b1);
        @(posedge clk);
        req_valid <= 1'b0;
        req_write <= 1'b0;
    endtask

    task automatic read(input logic [31:0] addr, output logic [31:0] value);
        req_addr  <= addr;
        req_data  <= '0;
        req_write <= 1'b0;
        req_valid <= 1'b1;
        do @(negedge clk); while (req_ready !== 1'b1);
        if (rsp_valid !== 1'b1) $display("TB: FAIL: CSR read %0h taken without a response at %0t", addr, $realtime);
        value = rsp_data;
        @(posedge clk);
        req_valid <= 1'b0;
    endtask

    initial begin : run
        logic [31:0] kind, a, b, value;
        repeat (5) @(posedge clk);
        @(negedge clk) rst_n = 1'b1;
        repeat (2) @(posedge clk);
        for (int i = 0; i < n_ops; i++) begin
            {kind, a, b} = ops[i];
            case (kind)
                0: request(a, b, 1'b1);
                1: begin
                    if (!go) begin
                        $dumpon;            // the edge that offers the first START
                        go <= 1'b1;
                    end
                    start_g = b;
                    is_start = 1;
                    request(a, 32'd1, 1'b1);
                    is_start = 0;
                end
                2: begin
                    wait (dones[a] == starts_taken[a]);
                    @(posedge clk);
                end
                3: begin
                    read(a, value);
                    $display("TB: counter %0d %0d", b, value);
                end
                default: $fatal(1, "csr_prog_seq: op %0d kind %0d", i, kind);
            endcase
        end
        wait (closed && sinks_complete);
        @(negedge clk);
        $display("TB: ports first_in %0d last_out %0d", first_in, last_out);
        $display("TB: window t0_ns %0.3f t1_ns %0.3f cycles %0d", t_open, t_close, n_close - n_open);
        $finish;
    end

    initial begin : watchdog
        @(posedge rst_n);
        #0 repeat (timeout) @(posedge clk);
        $display("TB: FAIL: timeout after %0d cycles (window opened %0b, closed %0b, sinks complete %0b, starts %0d of %0d)",
                 timeout, opened, closed, sinks_complete, taken, n_starts);
        $finish;
    end
endmodule
