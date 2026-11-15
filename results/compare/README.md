# forge and the HLS cases side by side: Vitis opt and dace, Bambu, XLS

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs (X45, X64); the text outside the `gen` markers is written by hand. This page has the setup, the summary across kernels and the parts' basis; each kernel has its own page. These rows are ungated synthesis; they are rebuilt clock-gated in CG6 (X79 · X87 · X88).

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

Main view: nangate45, int64, every point synthesized at a 10 ns clock (the HLS tools scheduled at a 10 ns HLS clock), W = 1 to 16 lanes per stream. Size: n2048 everywhere, 2048 elements per input stream (X24, X55): tier done N = 2048, untiered relu and axpy n = 2048, matadd m32_n64, rowsum m16_n128. Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition. forge's cases: dot 2 to 6 (forge2 to forge6), axpy with alpha baked to 3 (forge baked), rowsum 2 (forge2).
<!-- /gen -->

## 2. Across all kernels

### Summary: forge without its csr against the HLS tools

forge without its CSR file, X63's like-for-like basis, against the best HLS case per metric: the lowest of Vitis opt, Vitis dace, Bambu and XLS, taken separately for energy and for area. n2048, nangate45, int64, snax-forge 3c7ea00 (CTRL2, D168). Each cell is forge's energy per element divided by the best HLS energy per element, then forge's area divided by the smallest HLS area; below 1, forge is better. dot is forge's dot 3 and axpy is forge's α from a CSR (forge baked is not like-for-like). vecadd and matadd are the same hardware for every tool, and so are vsum and rowsum (energies within about 2 %), so they share rows; the vsum row is vsum's (rowsum at W = 1: 0.97 / 1.03 against XLS, its Vitis dace being the larger, with a 16-word buffer from flops; rowsum at W = 8: 0.83 / 0.89). Since X65 this total is forge's total minus the whole csr cell, as in Part A: it holds neither the csr nor its child `<tag>_peripherals` (BUSY_COUNTER), so it is forge's ctrl, datapath and glue. The glue is at most 1.1 µm² (0.2 %, relu at W = 1) and changes none of the 472 forge-against-HLS verdicts, so no separate ctrl + datapath table is kept. Each kernel's `<kernel>_ctrl_dp.png` plots forge's ctrl + datapath against the HLS totals (X77).

| Kernel | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 |
|---|---|---|---|---|---|
| dot (forge 3) | 0.95 / 1.01 | 0.94 / 1.00 | 0.96 / 1.00 | 0.96 / 0.99 | 0.96 / 0.99 |
| vecmul | 0.92 / 1.01 | 0.92 / 1.00 | 0.91 / 0.98 | 0.93 / 0.99 | 0.92 / 0.98 |
| axpy (α from a CSR) | 0.88 / 0.96 | 0.90 / 0.97 | 0.90 / 0.98 | 0.91 / 0.98 | 0.90 / 0.99 |
| vecadd, matadd | 0.80 / 1.01 | 0.77 / 0.88 | 0.75 / 0.79 | 0.74 / 0.73 | 0.72 / 0.70 |
| vsum, rowsum | 1.02 / 1.07 | 0.96 / 0.99 | 0.89 / 0.94 | 0.84 / 0.89 | 0.89 / 0.88 |
| relu | 1.04 / 1.39 | 1.03 / 1.33 | 1.01 / 1.25 | 1.00 / 1.16 | 1.00 / 1.09 |

- **Energy:** forge has the lowest energy per element on seven of the eight kernels from W = 2 and on six at W = 1: 4 to 6 % below the best HLS case on dot, 7 to 9 % on vecmul, 9 to 12 % on axpy and 20 to 28 % on vecadd and matadd at every W, 4 to 17 % on vsum and rowsum from W = 2 (at W = 1 rowsum is 3 % below XLS and vsum 2 % above Vitis dace). relu is the exception: 4 % above XLS at W = 1, 1 % at W = 4, level from W = 8 (0.999 at W = 16).
- **Area:** wherever 64-bit multipliers set it, forge is the smallest from W = 2 and within 1 % at W = 1: dot and vecmul 0.6 % above XLS at W = 1 and 0.1 to 1.8 % below it from W = 2, axpy 1 to 4 % below it at every W. vecadd and matadd are 1 % above XLS at W = 1 and 12 to 30 % below it from W = 2; vsum 7 % above Vitis dace at W = 1 (rowsum 3 % above XLS) and 1 to 12 % below the smallest from W = 2. relu is larger at every W, by 9 % (W = 16) to 39 % (W = 1).
- **What CTRL2 changed (snax-forge D168):** the control unit reads JOBS and each JOB_BEATS live from the csr, so it lost its copy of JOBS (an elementwise ctrl 711 to 438 µm², 66 to 34 flops) and a fold also its copy of JOB_BEATS (1,294 to 760 µm², 131 to 67 flops). BUSY_COUNTER left the csr for `<tag>_peripherals` (279 µm², 0.24 to 0.25 pJ per cycle), which X65 keeps out of every figure, as Part A kept it out of this total by keeping it in the csr; so before and after share one basis and the whole control saving shows. The rows move most at W = 1: relu 1.40 / 2.14 to 1.04 / 1.39, vsum 1.22 / 1.43 to 1.02 / 1.07, vecadd and matadd 0.99 / 1.40 to 0.80 / 1.01, dot 3 0.98 / 1.07 to 0.95 / 1.01. The moves shrink as the datapath grows with W (W = 16: relu 1.03 / 1.29 to 1.00 / 1.09, vsum 0.95 / 0.96 to 0.89 / 0.88, vecmul and axpy within 0.01).
- **Why the rows fall with W:** forge's control is fixed, about 438 µm² for an elementwise unit and 760 µm² for a fold with JOB_BEATS, at every W, against XLS's 32 to 160 flops in total. It holds a counter per setting it reads from the csr (JOBS, each JOB_BEATS), the busy flag, the done pulse and the pipeline's valid bits (`ctrl/GroupRule.scala`): 34 flops for an elementwise unit, 67 with JOB_BEATS, as snax-forge's `estimate/bits.py` counts them at all 70 points. The busy-cycle BUSY_COUNTER (snax-forge D123, D168) is in `<tag>_peripherals`, a child of the csr, outside the ctrl and in no figure (X65). Where the datapath is a few hundred µm² (relu's 273 µm² at W = 4, a one-lane adder), the control decides; as W grows the datapath takes over.
- **No flops per lane and no input gating:** forge's datapath is the arithmetic only, so its slope over W is the lowest (vecadd: 270 µm² per lane, against XLS 406, Vitis 679 and Bambu 1622).
- **Latency:** forge is at par, one cycle per beat, the same cycles as before CTRL2 at every point. The exceptions are dot 5 and 6 (145 and 146 cycles at W = 16 against 129), from the stall and the holding buffer.
- **With the CSR file** (the totals on each kernel's page), forge adds 548 µm² for an elementwise unit, 794 µm² for a fold and 1,073 µm² for axpy (K1_LO and K1_HI), and 0.47 to 0.93 pJ per cycle: the csr without its peripherals (X65), which since CTRL2 also holds a write to a busy group's settings until its run ends. The totals also hold BUSY_COUNTER's `<tag>_peripherals` (279 µm², 313 at dot 4 to 6 at W = 8), which no other figure counts (X65). Integrating any HLS block into the cluster would need a register interface of its own (X63).

### The HLS cases

All numbers below are nangate45, int64, at n2048 (X24, X55). Flops are DC's `seq_cells`, traced to each tool's RTL in R6 and R7.

- **Registers per lane decide the gaps wherever the arithmetic is cheap.** Flops added per lane (the slope of the flop count over W): forge 0, XLS 0; Vitis opt 64 per output stream, since it registers the output beat, and 0 for the reductions; Bambu 64 per stream, inputs and outputs alike (vecadd, vecmul and axpy 192; relu 128; dot about 141; vsum about 68).
- **Bambu's registered beats are its most costly trait.** In vecadd they are 53 % of its area and 60 % of its energy, and they are why its area grows 1622 µm² per lane against Vitis's 679 and XLS's 406.
- **XLS's flops are its proc state only, and they do not grow with W:** 32 (the loop count: vecadd, vecmul, matadd, relu), 96 (axpy: loop count and alpha), 160 (vsum, dot, rowsum). That makes XLS the smallest HLS case in every kernel, with flops at most 3 % of its energy from W = 8. forge without its csr is smaller than XLS on every kernel but relu from W = 2, and on axpy at every W (the summary above).
- **XLS gates every input bit with its proc state.** In vecadd that is 2 x 64 AND gates per lane: 497 AND2 cells at W = 4 (529 µm², 28 % of its area) and 1,985 at W = 16 (2,112 µm², 31 %). In relu the same gates are the operation itself (253 at W = 4); in the multiplier kernels fewer are left (vecmul W = 16: 1,097 cells, 1 % of the area). forge feeds its datapath straight from the shell's valid-ready ports, so this is where XLS's extra vecadd area goes, and likely its extra energy; the energy share is not measured.
- **64-bit multipliers set the area wherever they are in the datapath** (vecmul, dot, axpy): about 7.0k to 8.6k µm² per lane for every tool. At W = 16, Vitis opt is within 1 to 10 % of XLS and Bambu 12 to 22 % above it, the difference being registers.
- **Run-time pins:** Vitis registers its pins (`ap_vld`), XLS keeps them in its proc state, and Bambu reads them as plain wires held for the task, so Bambu pays no pin registers. In axpy, Vitis's 65 extra fixed flops against vecadd are alpha's pin register.
- **Energy per task falls with W and then levels off:** the fixed part (control, handshakes, reset logic) is paid per cycle, and wider beats need fewer cycles for the same task.
- **Latency is about one cycle per beat for all four cases.** The differences of 1 or 2 cycles are their windows and pipeline depths (Vitis opt 2 stages at 10 ns, Bambu an iteration latency of 2 or 3, XLS one stage). The one real exception is Bambu's dot at W = 4 and 8, which runs at II = 2. forge is at par (the summary above); DaCe's two loops take twice as long (next bullet).
- **Control is only visible where the RTL keeps it apart.** Bambu's controller is a module of its own and small (81 µm² in dot at W = 8, 0.1 % of the area). Vitis and XLS mix control and datapath in one flat module, so their control cost cannot be split out after synthesis (X41); their totals hold it. forge keeps its control in `<tag>_ctrl` and its CSR file in `<tag>_csr` (X22), the only case with both measured apart; the csr's child `<tag>_peripherals` (BUSY_COUNTER) is in neither part nor in the total without csr (X65). The Bambu figure holds after X63's correction of Bambu's parts.
- **Vitis dace with a RAM** (dot, axpy and rowsum at W = 1, X62): DaCe keeps NPBench's intermediate array, so dot and axpy write 2048 words to a 2048 x 64 macro (49.3k µm²) and read them back in a second loop. That is 4101 cycles, twice the others; 57.7k and 58.2k µm²; 75.5 and 73.5 nJ per task, the macro 85 % of the area and 60 % of the energy. rowsum's 16-word `y_buf` is built from flops (CACTI refuses 16 words, and the buffer has a second read port): 18.8k µm², 2137 cycles, 32.9 nJ. forge's `fuse_map` removes the intermediate array altogether.
- **Timing:** every point meets 10 ns. XLS, with one combinational stage from its ports, has the least slack (dot at W = 16: 2.38 ns on nangate45, against 3.87 ns for Bambu at W = 8 and 4.17 ns for Vitis at W = 8, R4).

## 3. Parts at n2048

The parts' tables are on each kernel's page ("Parts at n2048"); this is the basis they share.

<!-- gen:parts-basis -->
Every point at n2048 on nangate45 (2048 elements per input stream), per kernel and W. A part's energy per task is its energy per cycle (PT's hierarchical report of that run, `power_pt_modules.csv`, X60) times the window's cycles; pJ per element divides it by 2048. forge: csr, ctrl and datapath (the wrapper's three instances), the total (glue included), and the total without csr (ctrl, datapath and glue); the csr is the csr cell without its `<tag>_peripherals` child (BUSY_COUNTER, snax-forge D168, X65), and the total without csr is the total minus the whole csr cell, so the peripherals are in neither (only in the total). Bambu: ctrl and datapath (X41), the total (glue included). Vitis dace with a RAM: the RAM apart (X62: the macro's area and its counted accesses x CACTI's energies, or its flops' area and PT energy) and the logic without it. Vitis opt and XLS: totals only. **Basis (X63):** the HLS tools take their sizes on plain pins (`loop_count`, `len`, axpy's `alpha`) and have no CSR file, while forge holds them in `<tag>_csr`, its interface to the cluster; so forge's total without csr is the like-for-like figure against an HLS total. Integrating any HLS block into the cluster would need a register interface of its own, which none of these totals contains.
<!-- /gen -->

## 4. Notes

- Vitis dace_w1 of dot, axpy and rowsum: rebuilt for n2048 with their RAM as an SRAM macro (dot, axpy) or flops (rowsum), X62.
- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.
