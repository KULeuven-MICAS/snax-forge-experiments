# forge and the HLS cases side by side: Vitis opt and dace, Bambu, XLS

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs (X45, X64); the text outside the `gen` markers is written by hand. This page has the setup, the summary across kernels and the parts' basis; each kernel has its own page. Every case is clock-gated (X79 · X87 · X88).

**The paper's comparison moves to int8 (X118).** E7 is being remeasured at forge's `i8` preset and W = 8 on three levels (the basic blocks, dot and matvec's column form, tier A), with one cycle window for every tool. This page and its CSVs hold the int64 data at W = 1 to 16 until the int8 rows replace them.

<!-- gen:index -->
| Tier | Kernels |
|---|---|
| done | [vecadd](done/vecadd.md), [vecmul](done/vecmul.md), [vsum](done/vsum.md), [dot](done/dot.md) |
| untiered | [matadd](untiered/matadd.md), [relu](untiered/relu.md), [axpy](untiered/axpy.md), [rowsum](untiered/rowsum.md) |
<!-- /gen -->

## 1. Setup

<!-- gen:setup -->
| Case | Tool version | RTL measured at | Latency window |
|---|---|---|---|
| forge |  | 3c7ea00 | START to done (X13) |
| forge 2 |  | 3c7ea00 | START to done (X13) |
| forge 3 |  | 3c7ea00 | START to done (X13) |
| forge 4 |  | 3c7ea00 | START to done (X13) |
| forge 5 |  | 3c7ea00 | START to done (X13) |
| forge 6 |  | 3c7ea00 | START to done (X13) |
| forge baked |  | 3c7ea00 | START to done (X13) |
| Vitis opt | v2023.2.2 | 4ef8bc8 | ap_start to ap_done (X12) |
| Vitis dace | v2023.2.2 | 4ef8bc8, f33338d | ap_start to ap_done (X12) |
| Bambu | PandA 2026.11 rev cda4db2e | 542fa32 | start_port to done_port (X44) |
| XLS | v0.0.0-10782-g5ddc35c4e | 46fa843, 9ae29ea, faf5a3d | cfg transfer to last output, last edge included (X44) |

Main view: nangate45, int64, every point synthesized clock-gated at a 10 ns clock (X79 · X87 · X88; the HLS tools scheduled at a 10 ns HLS clock), W = 1 to 16 lanes per stream. Size: n2048 everywhere, 2048 elements per input stream (X24, X55): tier done N = 2048, untiered relu and axpy n = 2048, matadd m32_n64, rowsum m16_n128. Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition. forge's cases: dot 2 to 6 (forge2 to forge6), axpy with alpha baked to 3 (forge baked), rowsum 2 (forge2).
<!-- /gen -->

## 2. Across all kernels

### Summary: forge without its csr against the HLS tools

forge without its CSR file, X63's like-for-like basis, against the best HLS case per metric: the lowest of Vitis opt, Vitis dace, Bambu and XLS, taken separately for energy and for area. n2048, nangate45, int64, every case clock-gated (X79 · X87 · X88), forge's points at snax-forge 3c7ea00. Each cell is forge's energy per element divided by the best HLS energy per element, then forge's area divided by the smallest HLS area; below 1, forge is better (`report/compare_summary.py`). dot is forge's dot 3 and axpy is forge's α from a CSR (forge baked is not like-for-like). vecadd and matadd are the same hardware for every tool, and so are vsum and rowsum (energies within about 3 %), so they share rows; the vsum row is vsum's (rowsum at W = 1: 0.83 / 0.94 against XLS, its Vitis dace being the larger, with a 16-word buffer from flops). This total is forge's total minus the whole csr cell (X65): it holds neither the csr nor its child `<tag>_peripherals` (BUSY_COUNTER), so it is forge's ctrl, datapath and glue. The glue is at most 1.6 µm² (0.1 %, vecadd at W = 1) and changes none of the 472 forge-against-HLS verdicts, so no separate ctrl + datapath table is kept. Each kernel's `<kernel>_ctrl_dp.png` plots forge's ctrl + datapath against the HLS totals (X77).

| Kernel | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 |
|---|---|---|---|---|---|
| dot (forge 3) | 0.96 / 1.01 | 0.93 / 1.00 | 0.95 / 0.99 | 0.96 / 0.99 | 0.96 / 0.98 |
| vecmul | 0.92 / 1.00 | 0.92 / 0.99 | 0.92 / 0.99 | 0.92 / 0.98 | 0.92 / 0.98 |
| axpy (α from a CSR) | 0.92 / 0.96 | 0.92 / 0.98 | 0.91 / 0.98 | 0.91 / 0.98 | 0.91 / 0.99 |
| vecadd, matadd | 0.81 / 1.06 | 0.77 / 0.91 | 0.75 / 0.80 | 0.74 / 0.74 | 0.73 / 0.70 |
| vsum, rowsum | 1.01 / 1.03 | 0.81 / 0.91 | 0.78 / 0.88 | 0.82 / 0.85 | 0.88 / 0.87 |
| relu | 1.05 / 1.50 | 1.03 / 1.41 | 1.02 / 1.30 | 1.01 / 1.20 | 1.00 / 1.11 |

- **Energy:** forge has the lowest energy per element on seven of the eight kernels from W = 2 and on six at W = 1: 4 to 7 % below the best HLS case on dot, 8 % on vecmul, 8 to 9 % on axpy, 19 to 27 % on vecadd and matadd at every W, 12 to 22 % on vsum and rowsum from W = 2 (at W = 1 rowsum is 17 % below XLS and vsum 1 % above Vitis dace). relu is the exception: 5 % above XLS at W = 1, 2 % at W = 4, 1 % at W = 8 and level at W = 16.
- **Area:** wherever 64-bit multipliers set it, forge is the smallest from W = 2 and within 1 % at W = 1: dot 0.6 % above XLS at W = 1 and 0.1 to 1.6 % below the smallest from W = 2, vecmul 0.4 % above XLS at W = 1 and 0.8 to 2.0 % below it from W = 2, axpy 1 to 4 % below XLS at every W. vecadd and matadd are 6 % above XLS at W = 1 and 9 to 30 % below it from W = 2; vsum 3 % above Vitis dace at W = 1 (rowsum 6 % below XLS) and 9 to 15 % below the smallest from W = 2. relu is larger at every W, by 11 % (W = 16) to 50 % (W = 1).
- **Why the rows fall with W:** forge's control is fixed, about 440 µm² for an elementwise unit and 711 µm² for a fold with JOB_BEATS, at every W, against XLS's 32 to 160 registers in total. It holds a counter per setting it reads from the csr (JOBS, each JOB_BEATS), the busy flag, the done pulse and the pipeline's valid bits (`ctrl/GroupRule.scala`): 34 registers for an elementwise unit, 67 with JOB_BEATS, as snax-forge's `estimate/bits.py` counts them. The busy-cycle BUSY_COUNTER (snax-forge D123, D168) is in `<tag>_peripherals`, a child of the csr, outside the ctrl and in no figure (X65). Where the datapath is a few hundred µm² (relu's 273 µm² at W = 4, a one-lane adder), the control decides; as W grows the datapath takes over.
- **No registers per lane and no input gating:** forge's datapath is the arithmetic only, so its slope over W is the lowest (vecadd: 270 µm² per lane, against XLS 406, Vitis 559 and Bambu 1259).
- **Latency:** forge is at par, one cycle per beat. The exceptions are dot 5 and 6 (145 and 146 cycles at W = 16 against 129), from the stall and the holding buffer.
- **With the CSR file** (the totals on each kernel's page), forge adds 473 µm² for an elementwise unit, 701 µm² for a fold and 912 µm² for axpy (K1_LO and K1_HI), and about 0.30 pJ per cycle: the csr without its peripherals (X65), which also holds a write to a busy group's settings until its run ends. The totals also hold BUSY_COUNTER's `<tag>_peripherals` (252 µm², 0.29 pJ per cycle), which no other figure counts (X65). Integrating any HLS block into the cluster would need a register interface of its own (X63).

### The HLS cases

All numbers below are nangate45, int64, clock-gated, at n2048 (X24, X55). Registers are the RTL's (DC's sequential cells less its clock gates), traced to each tool's RTL in HSYN1 R6 and R7.

- **Registers per lane decide the gaps wherever the arithmetic is cheap.** Registers added per lane (the slope of the register count over W): forge 0, XLS 0; Vitis opt 64 per output stream, since it registers the output beat, and 0 for the reductions; Bambu 64 per stream, inputs and outputs alike (vecadd, vecmul and axpy 192; relu 128; dot about 141; vsum about 68).
- **Bambu's registered beats are its most costly trait.** In vecadd its sequential cells are 63 to 68 % of its area and its flop energy 69 to 74 % of its energy, and they are why its area grows 1259 µm² per lane against Vitis's 559 and XLS's 406.
- **XLS's registers are its proc state only, and they do not grow with W:** 32 (the loop count: vecadd, vecmul, matadd, relu), 96 (axpy: loop count and alpha), 160 (vsum, dot, rowsum). That makes XLS the smallest HLS case in most kernels and at most W, its flop energy 0.3 to 7 % of its energy at W = 8 but in the reductions (vsum and rowsum 21 %). forge without its csr is smaller than XLS on every kernel but relu from W = 2, and on axpy at every W (the summary above).
- **XLS gates every input bit with its proc state.** In vecadd that is 2 x 64 AND gates per lane: 496 AND2 cells at W = 4 (528 µm², 28 % of its area) and 1,984 at W = 16 (2,111 µm², 31 %). In relu the same gates are the operation itself (253 at W = 4); in the multiplier kernels fewer are left (vecmul W = 16: 1,389 cells, 1 % of the area). forge feeds its datapath straight from the shell's valid-ready ports, so this is where XLS's extra vecadd area goes, and likely its extra energy; the energy share is not measured.
- **64-bit multipliers set the area wherever they are in the datapath** (vecmul, dot, axpy): about 6.9k to 8.2k µm² per lane for every tool. At W = 16, Vitis opt is within 8 % of XLS (0.2 % below it to 7.7 % above) and Bambu 8 to 17 % above it, the difference being registers.
- **Run-time pins:** Vitis registers its pins (`ap_vld`), XLS keeps them in its proc state, and Bambu reads them as plain wires held for the task, so Bambu pays no pin registers. In axpy, Vitis's 65 extra fixed registers against vecadd are alpha's pin register.
- **Energy per task falls with W and then levels off:** the fixed part (control, handshakes, reset logic) is paid per cycle, and wider beats need fewer cycles for the same task.
- **Latency is about one cycle per beat for all four cases.** The differences of 1 or 2 cycles are their windows and pipeline depths (Vitis opt 2 stages at 10 ns, Bambu an iteration latency of 2 or 3, XLS one stage). The one real exception is Bambu's dot at W = 4 and 8, which runs at II = 2. forge is at par (the summary above); DaCe's two loops take twice as long (next bullet).
- **Control is only visible where the RTL keeps it apart.** Bambu's controller is a module of its own and small (80 µm² in dot at W = 8, 0.1 % of the area). Vitis and XLS mix control and datapath in one flat module, so their control cost cannot be split out after synthesis (X41); their totals hold it. forge keeps its control in `<tag>_ctrl` and its CSR file in `<tag>_csr` (X22), the only case with both measured apart; the csr's child `<tag>_peripherals` (BUSY_COUNTER) is in neither part nor in the total without csr (X65).
- **Vitis dace with a RAM** (dot, axpy and rowsum at W = 1, X62): DaCe keeps NPBench's intermediate array, so dot and axpy write 2048 words to a 2048 x 64 macro (49.3k µm²) and read them back in a second loop. That is 4101 cycles, twice the others; 57.6k and 58.0k µm²; 72.8 and 69.9 nJ per task, the macro 85 % of the area and 62 to 65 % of the energy. rowsum's 16-word `y_buf` is built from flops (CACTI refuses 16 words, and the buffer has a second read port): 15.8k µm², 7.2k of it the buffer, 2137 cycles, 17.4 nJ. forge's `fuse_map` removes the intermediate array altogether.
- **Timing:** every point meets 10 ns. XLS, with one combinational stage from its ports, has the least slack (2.41 ns at its tightest point; dot at W = 16: 2.66 ns), against 3.87 ns for Bambu (dot at W = 8), 4.00 ns for Vitis (dot at W = 16) and 3.00 ns for forge at their tightest.

## 3. Parts at n2048

The parts' tables are on each kernel's page ("Parts at n2048"); this is the basis they share.

<!-- gen:parts-basis -->
Every point at n2048 on nangate45 (2048 elements per input stream), per kernel and W. A part's energy per task is its energy per cycle (PT's hierarchical report of that run, `power_pt_modules.csv`, X60) times the window's cycles; pJ per element divides it by 2048. forge: csr, ctrl and datapath (the wrapper's three instances), the total (glue included), and the total without csr (ctrl, datapath and glue); the csr is the csr cell without its `<tag>_peripherals` child (BUSY_COUNTER, snax-forge D168, X65), and the total without csr is the total minus the whole csr cell, so the peripherals are in neither (only in the total). Bambu: ctrl and datapath (X41), the total (glue included). Vitis dace with a RAM: the RAM apart (X62: the macro's area and its counted accesses x CACTI's energies, or its flops' area and PT energy) and the logic without it. Vitis opt and XLS: totals only. **Basis (X63):** the HLS tools take their sizes on plain pins (`loop_count`, `len`, axpy's `alpha`) and have no CSR file, while forge holds them in `<tag>_csr`, its interface to the cluster; so forge's total without csr is the like-for-like figure against an HLS total. Integrating any HLS block into the cluster would need a register interface of its own, which none of these totals contains.
<!-- /gen -->

## 4. Notes

- Vitis dace_w1 of dot, axpy and rowsum: rebuilt for n2048 with their RAM as an SRAM macro (dot, axpy) or flops (rowsum), X62.
- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.

## 5. The tier CSVs

`compare_done.csv` and `compare_untiered.csv` (`pixi run compare`, X45 · X55 · X61): one row per tech, tier, kernel, W, tool, case and size, laid out and not compared (no ratios, no ranking); a parked point (a RAM macro) is a row with its status and no numbers. They read only committed CSVs: `results/<source>/<tech>/synth_dc.csv`, `power_pt.csv`, `power_pt_modules.csv` and the cycle CSVs' provenance.

| Columns | What they hold |
|---|---|
| key | tech, tier, kernel, W, tool (forge, vitis, bambu, xls), case (forge, forge2..6, forge_baked, opt, dace, bambu, xls), point, size, status (ok, or the synthesis or power status that is not) |
| task | beats (per input stream), elements (beats * W), cycles (the power window), window (how the window is defined for the tool) |
| area | area_um2, comb_area_um2, seq_area_um2, buf_inv_area_um2, cells, seq_cells, and the split where the RTL declares it as hierarchy: csr_um2 (forge), ctrl_um2, datapath_um2, glue_um2 (forge, bambu); empty for vitis and xls; forge's csr_um2 is the csr cell without its child <tag>_peripherals (BUSY_COUNTER, snax-forge D168), whose area is peripherals_um2 (for the record, in no figure: forge's total without csr is area_um2 - csr_um2 - peripherals_um2; empty where the bundle has none: every point before the leaner control unit); ram_kind and ram_um2 for a Vitis point with a RAM ( an SRAM macro or flops, inside area_um2) |
| timing | crit_path_ns, slack_ns, fmax_mhz, slack_in2reg_ns, slack_reg2reg_ns, slack_reg2out_ns, slack_in2out_ns |
| energy | e_clk_pj, e_reg_pj, e_seq_pj, e_comb_pj, e_flop_pj, e_dyn_pj (per cycle of the window), p_dyn_uw, e_run_pj (the task), pj_per_elem (e_run_pj / elements), flop_bits, e_bit_pj, leak_dc_uw (DC's leakage estimate); ram_reads, ram_writes, e_ram_pj (the RAM's share of e_run_pj: counted accesses x CACTI's energies for a macro, PT's for flops) |
| parts | e_dyn_csr_pj, e_dyn_ctrl_pj, e_dyn_datapath_pj, e_dyn_glue_pj (per cycle, forge and bambu only; forge's csr without its _peripherals child, whose energy is e_dyn_peripherals_pj, for the record), parts_size (the run they come from: the row's own run where power_pt_modules.csv has it (every n2048 run), else the point's default run: tier done b64 (rowsum m8_n64), forge n2048, untiered n2048) provenance rtl_commit (the tool repo commit the RTL was measured at; forge: snax_forge_commit), tool_version, dc_version, syn_date |

Checks (any failure: exit 1, nothing written): every listed point has a synthesis row; every ok point has the same sizes as the other points of its kernel, n2048 among them, each with an ok power row; no duplicate key; the split columns (csr, ctrl, datapath, glue and, for forge's leaner control unit, peripherals) sum to the area where they exist; a point with parts has an ok run at its default size. A glue energy within 1e-5 of the total (PT's rounding) is written as 0.
