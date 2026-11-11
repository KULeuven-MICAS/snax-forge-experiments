// cluster/mem.py's tc_sram_impl.sv (RAM1's models, ram.gen_v) against tech_cells_generic v0.2.11's tc_sram_impl, the
// same random traffic per size, rdata compared every cycle from the first read (both start X; tech_cells_generic
// resets its read address, the models do not). Run in chat on 2026-11-11 with Verilator 5.020:
//   sed 's/\btc_sram_impl\b/ref_sram_impl/; s/\btc_sram\b/ref_sram/' <tcg>/src/rtl/tc_sram_impl.sv > ref_impl.sv
//   sed 's/^module tc_sram\b/module ref_sram/' <tcg>/src/rtl/tc_sram.sv > ref_sram.sv
//   verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --top-module tb ref_sram.sv ref_impl.sv \
//     tc_sram_impl.sv sram_d512_w64_m8.v sram_d128_w256_m8.v sram_d128_w39.v cluster/eqv_tb.sv
// Result: compared 19486 / 19867 / 19870 cycles; mismatches tcdm 0, icache data 0, icache tag 0 (EQUIV PASS).
// The tag's reference uses ByteWidth 39 (one enable, tied high as the icache ties it): with ByteWidth 8 its last
// byte slice, bits 32..39 of a 39-bit word, runs past the word and Verilator drops bit 38 of every write.

// The generated tc_sram_impl (RAM1 models) against tech_cells_generic's, same random traffic, per size.
module pair #(parameter int unsigned W = 64, D = 512, RefBw = 8, bit RandBe = 1) (input logic clk, rst_n, output int errs);
  localparam int unsigned A = $clog2(D), B = (W + 7) / 8;
  logic req, we; logic [A-1:0] addr; logic [W-1:0] wdata, r_dut, r_ref; logic [B-1:0] be;
  tc_sram_impl  #(.NumWords(D), .DataWidth(W), .ByteWidth(8), .NumPorts(1), .Latency(1)) i_dut (
    .clk_i(clk), .rst_ni(rst_n), .impl_i('0), .impl_o(), .req_i(req), .we_i(we), .addr_i(addr), .wdata_i(wdata), .be_i(be), .rdata_o(r_dut));
  ref_sram_impl #(.NumWords(D), .DataWidth(W), .ByteWidth(RefBw), .NumPorts(1), .Latency(1)) i_ref (
    .clk_i(clk), .rst_ni(rst_n), .impl_i('0), .impl_o(), .req_i(req), .we_i(we), .addr_i(addr), .wdata_i(wdata), .be_i(RefBw == 8 ? be : '1), .rdata_o(r_ref));
  int cyc = 0; bit seen_read = 0; int reads = 0;
  function automatic logic [W-1:0] rnd(); logic [W-1:0] v; for (int i = 0; i < W; i += 32) v[i +: 32] = $urandom; return v; endfunction
  always_ff @(posedge clk) if (rst_n) begin
    cyc <= cyc + 1;
    if (cyc < D) begin            // preload every word, all bytes
      req <= 1; we <= 1; addr <= A'(cyc); wdata <= rnd(); be <= '1;
    end else begin                // random reads, writes and idles
      req <= ($urandom % 4) != 0; we <= ($urandom % 3) == 0; addr <= A'($urandom % D); wdata <= rnd();
      be <= RandBe ? B'(rnd()) : '1;
    end
    if (req && !we) seen_read <= 1;
    if (seen_read) begin
      reads <= reads + 1;
      if (r_dut !== r_ref) begin
        errs <= errs + 1;
        if (errs < 3) $display("W%0d D%0d cycle %0d: dut %h ref %h", W, D, cyc, r_dut, r_ref);
      end
    end
  end
  initial begin errs = 0; req = 0; we = 0; addr = '0; wdata = '0; be = '0; end
endmodule

module tb;
  logic clk = 0, rst_n = 0;
  int e0, e1, e2;
  always #1 clk = ~clk;
  pair #(.W(64),  .D(512), .RandBe(1)) p_tcdm  (.clk, .rst_n, .errs(e0));
  pair #(.W(256), .D(128), .RandBe(0)) p_data  (.clk, .rst_n, .errs(e1));   // the icache ties be_i to '1
  pair #(.W(39),  .D(128), .RefBw(39), .RandBe(0)) p_tag   (.clk, .rst_n, .errs(e2));
  initial begin
    #5 rst_n = 1;
    #40000;
    $display("compared %0d / %0d / %0d cycles; mismatches tcdm %0d, icache data %0d, icache tag %0d",
             p_tcdm.reads, p_data.reads, p_tag.reads, e0, e1, e2);
    if (e0 + e1 + e2) $display("EQUIV FAIL"); else $display("EQUIV PASS");
    $finish;
  end
endmodule
