# forge and the HLS cases side by side: Vitis opt and dace, Bambu, XLS

csr excludes `<tag>_peripherals` (BUSY_COUNTER), snax-forge D168.

Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs (X45, X46, X61, X64); the text outside the `gen` markers is written by hand. One page per kernel; this page has the setup, the summary across kernels, the parts' basis and the nangate15 check. The insights were written in HSYN1 R9 for the HLS cases and reread against the n2048 numbers in CSYN1 R4, with forge's cases added; the pages moved here from `results/compare_hls.md` in CSYN1 (X64). forge's rows and insights were remeasured and reread in CTRL2 R5 on snax-forge's leaner control unit (D168, X65); the numbers before it are kept only in [ctrl2_before_after.md](ctrl2_before_after.md).

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
| forge |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge 2 |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge 3 |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge 4 |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge 5 |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge 6 |  | 3c7ea00, f9764d5 | START to done (X13) |
| forge baked |  | 3c7ea00 | START to done (X13) |
| Vitis opt | v2023.2.2 | 4ef8bc8 | ap_start to ap_done (X12) |
| Vitis dace | v2023.2.2 | 4ef8bc8, f33338d | ap_start to ap_done (X12) |
| Bambu | PandA 2026.11 rev cda4db2e | 542fa32 | start_port to done_port (X44) |
| XLS | v0.0.0-10782-g5ddc35c4e | 46fa843, 9ae29ea, faf5a3d | cfg transfer to last output, last edge included (X44) |

Main view: nangate45, int64, every point synthesized at a 10 ns clock (the HLS tools scheduled at a 10 ns HLS clock), W = 1 to 16 lanes per stream. Size: n2048 everywhere, 2048 elements per input stream (X24, X55): tier done N = 2048, untiered relu and axpy n = 2048, matadd m32_n64, rowsum m16_n128. Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition. forge's cases: dot 2 to 6 (forge2 to forge6), axpy with alpha baked to 3 (forge baked), rowsum 2 (forge2).
<!-- /gen -->

## 2. Across all kernels

### Summary: forge without its csr against the HLS tools

forge without its CSR file, X63's like-for-like basis, against the best HLS case per metric: the lowest of Vitis opt, Vitis dace, Bambu and XLS, taken separately for energy and for area. n2048, nangate45, int64, snax-forge 3c7ea00 (CTRL2, D168). Each cell is forge's energy per element divided by the best HLS energy per element, then forge's area divided by the smallest HLS area; below 1, forge is better. dot is forge's dot 3 and axpy is forge's α from a CSR (forge baked is not like-for-like). vecadd and matadd are the same hardware for every tool, and so are vsum and rowsum (energies within about 2 %), so they share rows; the vsum row is vsum's (rowsum at W = 1: 1.06 / 1.21, its Vitis dace being the larger, with a 16-word buffer from flops). Since X65 the csr leaves out `<tag>_peripherals` (BUSY_COUNTER), so this total holds it.

| Kernel | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 |
|---|---|---|---|---|---|
| dot (forge 3) | 0.97 / 1.04 | 0.95 / 1.02 | 0.96 / 1.01 | 0.96 / 1.00 | 0.96 / 0.99 |
| vecmul | 0.94 / 1.04 | 0.93 / 1.02 | 0.92 / 0.99 | 0.93 / 0.99 | 0.92 / 0.99 |
| axpy (α from a CSR) | 0.90 / 0.99 | 0.91 / 0.99 | 0.91 / 0.99 | 0.91 / 0.99 | 0.90 / 0.99 |
| vecadd, matadd | 0.98 / 1.41 | 0.87 / 1.14 | 0.80 / 0.94 | 0.76 / 0.81 | 0.74 / 0.74 |
| vsum, rowsum | 1.12 / 1.26 | 1.04 / 1.14 | 0.96 / 1.05 | 0.88 / 0.96 | 0.92 / 0.92 |
| relu | 1.39 / 2.16 | 1.24 / 1.97 | 1.13 / 1.73 | 1.07 / 1.49 | 1.03 / 1.29 |

The same ratios for forge's ctrl + datapath alone, the busy counter and the glue left out:

| Kernel | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 |
|---|---|---|---|---|---|
| dot (forge 3) | 0.95 / 1.01 | 0.94 / 1.00 | 0.96 / 1.00 | 0.96 / 0.99 | 0.96 / 0.99 |
| vecmul | 0.92 / 1.01 | 0.92 / 1.00 | 0.91 / 0.98 | 0.93 / 0.99 | 0.92 / 0.98 |
| axpy (α from a CSR) | 0.88 / 0.96 | 0.90 / 0.97 | 0.90 / 0.98 | 0.91 / 0.98 | 0.90 / 0.99 |
| vecadd, matadd | 0.80 / 1.01 | 0.77 / 0.88 | 0.75 / 0.79 | 0.74 / 0.73 | 0.72 / 0.70 |
| vsum, rowsum | 1.02 / 1.07 | 0.96 / 0.99 | 0.89 / 0.94 | 0.84 / 0.89 | 0.89 / 0.88 |
| relu | 1.04 / 1.39 | 1.03 / 1.33 | 1.01 / 1.24 | 1.00 / 1.16 | 1.00 / 1.09 |

- **Energy:** from W = 8, forge has the lowest energy per element on six of the eight kernels: 4 % below the best HLS case on dot, 7 to 8 % on vecmul, 9 to 10 % on axpy, 24 to 26 % on vecadd and matadd, 8 to 13 % on vsum and rowsum, which are below it from W = 4 already. relu stays above XLS at every W (3 % at W = 16).
- **Area:** within 1 % of the smallest wherever 64-bit multipliers set it (dot, vecmul and axpy, from W = 4); 19 to 26 % smaller on vecadd and matadd at W = 8 and 16; 4 to 8 % smaller on vsum and rowsum from W = 8 and larger below it (5 to 26 % at W ≤ 4); larger on relu at every W (29 % to 2.2x).
- **What CTRL2 changed (snax-forge D168, [before and after](ctrl2_before_after.md)):** the control unit reads JOBS and each JOB_BEATS live from the csr, so it lost its copy of JOBS (an elementwise ctrl 711 to 438 µm², 66 to 34 flops) and a fold also its copy of JOB_BEATS (1,294 to 760 µm², 131 to 67 flops); and BUSY_COUNTER left the csr for `<tag>_peripherals` (279 µm², 0.24 to 0.25 pJ per cycle), which X65 keeps in the total without csr. For an elementwise unit the two cancel on this basis: vecadd, vecmul, axpy and relu are within 0.02 of Part A, relu's area 1 % higher. A fold keeps the JOB_BEATS copy's saving: vsum 1.22 / 1.43 to 1.12 / 1.26 at W = 1 and 1.02 / 1.15 to 0.96 / 1.05 at W = 4, dot 3 0.98 / 1.07 to 0.97 / 1.04 at W = 1. The ctrl + datapath table shows the control alone: relu comes within 4 % of XLS's energy at every W (level from W = 8), vecadd and matadd within 1 % of XLS's area at W = 1, and vsum and rowsum within 2 % of the best energy at W = 1.
- **Why the rows fall with W:** forge's control is fixed, about 438 µm² for an elementwise unit and 760 µm² for a fold with JOB_BEATS, at every W, against XLS's 32 to 160 flops in total. It holds a counter per setting it reads from the csr (JOBS, each JOB_BEATS), the busy flag, the done pulse and the pipeline's valid bits (`ctrl/GroupRule.scala`): 34 flops for an elementwise unit, 67 with JOB_BEATS, as snax-forge's `estimate/bits.py` counts them at all 70 points. The busy-cycle BUSY_COUNTER (snax-forge D123, D168) is in `<tag>_peripherals`, a child of the csr, outside the ctrl and inside the total without csr (X65). Where the datapath is a few hundred µm² (relu's 273 µm² at W = 4, a one-lane adder), the control and the counter decide; as W grows the datapath takes over.
- **No flops per lane and no input gating:** forge's datapath is the arithmetic only, so its slope over W is the lowest (vecadd: 270 µm² per lane, against XLS 406, Vitis 679 and Bambu 1622).
- **Latency:** forge is at par, one cycle per beat, the same cycles as before CTRL2 at every point. The exceptions are dot 5 and 6 (145 and 146 cycles at W = 16 against 129), from the stall and the holding buffer.
- **With the CSR file** (the totals on each kernel's page), forge adds 548 µm² for an elementwise unit, 794 µm² for a fold and 1,073 µm² for axpy (K1_LO and K1_HI), and 0.47 to 0.93 pJ per cycle: the csr without its peripherals (X65), which since CTRL2 also holds a write to a busy group's settings until its run ends. Integrating any HLS block into the cluster would need a register interface of its own (X63).

### The HLS cases

All numbers below are nangate45, int64, at n2048 (X24, X55). Flops are DC's `seq_cells`, traced to each tool's RTL in R6 and R7.

- **Registers per lane decide the gaps wherever the arithmetic is cheap.** Flops added per lane (the slope of the flop count over W): forge 0, XLS 0; Vitis opt 64 per output stream, since it registers the output beat, and 0 for the reductions; Bambu 64 per stream, inputs and outputs alike (vecadd, vecmul and axpy 192; relu 128; dot about 141; vsum about 68).
- **Bambu's registered beats are its most costly trait.** In vecadd they are 53 % of its area and 60 % of its energy, and they are why its area grows 1622 µm² per lane against Vitis's 679 and XLS's 406.
- **XLS's flops are its proc state only, and they do not grow with W:** 32 (the loop count: vecadd, vecmul, matadd, relu), 96 (axpy: loop count and alpha), 160 (vsum, dot, rowsum). That makes XLS the smallest HLS case in every kernel, with flops at most 3 % of its energy from W = 8. forge without its csr is smaller than XLS on vecadd and matadd from W = 4 and on vsum and rowsum from W = 8 (the summary above).
- **XLS gates every input bit with its proc state.** In vecadd that is 2 x 64 AND gates per lane: 497 AND2 cells at W = 4 (529 µm², 28 % of its area) and 1,985 at W = 16 (2,112 µm², 31 %). In relu the same gates are the operation itself (253 at W = 4); in the multiplier kernels fewer are left (vecmul W = 16: 1,097 cells, 1 % of the area). forge feeds its datapath straight from the shell's valid-ready ports, so this is where XLS's extra vecadd area goes, and likely its extra energy; the energy share is not measured.
- **64-bit multipliers set the area wherever they are in the datapath** (vecmul, dot, axpy): about 7.0k to 8.6k µm² per lane for every tool. At W = 16, Vitis opt is within 1 to 10 % of XLS and Bambu 12 to 22 % above it, the difference being registers.
- **Run-time pins:** Vitis registers its pins (`ap_vld`), XLS keeps them in its proc state, and Bambu reads them as plain wires held for the task, so Bambu pays no pin registers. In axpy, Vitis's 65 extra fixed flops against vecadd are alpha's pin register.
- **Energy per task falls with W and then levels off:** the fixed part (control, handshakes, reset logic) is paid per cycle, and wider beats need fewer cycles for the same task.
- **Latency is about one cycle per beat for all four cases.** The differences of 1 or 2 cycles are their windows and pipeline depths (Vitis opt 2 stages at 10 ns, Bambu an iteration latency of 2 or 3, XLS one stage). The one real exception is Bambu's dot at W = 4 and 8, which runs at II = 2. forge is at par (the summary above); DaCe's two loops take twice as long (next bullet).
- **Control is only visible where the RTL keeps it apart.** Bambu's controller is a module of its own and small (81 µm² in dot at W = 8, 0.1 % of the area). Vitis and XLS mix control and datapath in one flat module, so their control cost cannot be split out after synthesis (X41); their totals hold it. forge keeps its control in `<tag>_ctrl` and its CSR file in `<tag>_csr` (X22), the only case with both measured apart; the csr's child `<tag>_peripherals` (BUSY_COUNTER) is counted apart from both (X65). The Bambu figure holds after X63's correction of Bambu's parts.
- **Vitis dace with a RAM** (dot, axpy and rowsum at W = 1, X62): DaCe keeps NPBench's intermediate array, so dot and axpy write 2048 words to a 2048 x 64 macro (49.3k µm²) and read them back in a second loop. That is 4101 cycles, twice the others; 57.7k and 58.2k µm²; 75.5 and 73.5 nJ per task, the macro 85 % of the area and 60 % of the energy. rowsum's 16-word `y_buf` is built from flops (CACTI refuses 16 words, and the buffer has a second read port): 18.8k µm², 2137 cycles, 32.9 nJ. forge's `fuse_map` removes the intermediate array altogether.
- **Timing:** every point meets 10 ns. XLS, with one combinational stage from its ports, has the least slack (dot at W = 16: 2.38 ns on nangate45, against 3.87 ns for Bambu at W = 8 and 4.17 ns for Vitis at W = 8, R4).

## 3. Parts at n2048

The parts' tables are on each kernel's page ("Parts at n2048"); this is the basis they share.

<!-- gen:parts-basis -->
Every point at n2048 on nangate45 (2048 elements per input stream), per kernel and W. A part's energy per task is its energy per cycle (PT's hierarchical report of that run, `power_pt_modules.csv`, X60) times the window's cycles; pJ per element divides it by 2048. forge: csr, ctrl and datapath (the wrapper's three instances), the total (glue included), and the total without csr; the csr is the csr cell without its `<tag>_peripherals` child (BUSY_COUNTER, snax-forge D168, X65), which the totals hold. Bambu: ctrl and datapath (X41), the total (glue included). Vitis dace with a RAM: the RAM apart (X62: the macro's area and its counted accesses x CACTI's energies, or its flops' area and PT energy) and the logic without it. Vitis opt and XLS: totals only. **Basis (X63):** the HLS tools take their sizes on plain pins (`loop_count`, `len`, axpy's `alpha`) and have no CSR file, while forge holds them in `<tag>_csr`, its interface to the cluster; so forge's total without csr is the like-for-like figure against an HLS total. Integrating any HLS block into the cluster would need a register interface of its own, which none of these totals contains.
<!-- /gen -->

## 4. nangate15 check

<!-- gen:tech -->
Values at W = 8 (nangate45 / nangate15); latency is the same on both. Tier done at n2048, untiered at each kernel's larger cosim size (matadd m16_n32, relu n512, axpy n512, rowsum m8_n64): untiered has no n2048 on nangate15, and forge's untiered points are nangate45 only.

| Kernel | Case | Area (µm²) | Energy (nJ) | Power (mW) |
|---|---|---|---|---|
| vecadd | forge | 3,424 / 986.4 | 1.844 / 0.4962 | 0.7202 / 0.1938 |
| vecadd | Vitis opt | 6,057 / 1,693 | 3.124 / 0.9773 | 1.211 / 0.3788 |
| vecadd | Vitis dace | 6,459 / 1,807 | 3.221 / 1.002 | 1.244 / 0.3869 |
| vecadd | Bambu | 13,777 / 3,813 | 6.413 / 2.159 | 2.486 / 0.8368 |
| vecadd | XLS | 3,545 / 985.9 | 2.256 / 0.5825 | 0.8777 / 0.2267 |
| vecmul | forge | 56,567 / 18,090 | 23.37 / 7.819 | 9.129 / 3.054 |
| vecmul | Vitis opt | 59,302 / 18,793 | 25.33 / 8.317 | 9.816 / 3.224 |
| vecmul | Vitis dace | 59,710 / 18,907 | 25.42 / 8.342 | 9.814 / 3.221 |
| vecmul | Bambu | 66,948 / 20,840 | 30.1 / 9.7 | 11.67 / 3.76 |
| vecmul | XLS | 56,467 / 17,931 | 24.97 / 7.977 | 9.718 / 3.104 |
| vsum | forge | 4,548 / 1,361 | 1.502 / 0.4378 | 0.5844 / 0.1703 |
| vsum | Vitis opt | 4,246 / 1,194 | 1.499 / 0.4096 | 0.5808 / 0.1587 |
| vsum | Bambu | 7,703 / 2,134 | 2.992 / 0.9561 | 1.16 / 0.3706 |
| vsum | XLS | 3,898 / 1,096 | 1.512 / 0.3941 | 0.5883 / 0.1533 |
| dot | forge 2 | 64,277 / 20,167 | 25.34 / 8.508 | 9.82 / 3.298 |
| dot | forge 3 | 59,845 / 19,062 | 23.83 / 7.936 | 9.272 / 3.088 |
| dot | forge 4 | 65,647 / 20,776 | 26.13 / 8.736 | 10.13 / 3.386 |
| dot | forge 5 | 64,584 / 20,487 | 25.59 / 8.657 | 9.658 / 3.267 |
| dot | forge 6 | 68,296 / 21,406 | 26.42 / 8.869 | 9.933 / 3.334 |
| dot | Vitis opt | 60,079 / 19,004 | 24.57 / 7.974 | 9.523 / 3.091 |
| dot | Bambu | 66,374 / 20,686 | 31.33 / 10.43 | 6.095 / 2.029 |
| dot | XLS | 59,137 / 18,587 | 25.92 / 8.06 | 10.08 / 3.136 |
| matadd | Vitis opt | 6,057 / 1,693 | 0.7865 / 0.2465 | 1.192 / 0.3735 |
| matadd | Vitis dace | 6,459 / 1,807 | 0.8107 / 0.2526 | 1.21 / 0.3771 |
| matadd | Bambu | 13,777 / 3,813 | 1.621 / 0.5464 | 2.455 / 0.8278 |
| matadd | XLS | 3,545 / 985.9 | 0.5719 / 0.1482 | 0.8798 / 0.228 |
| relu | Vitis opt | 3,871 / 1,079 | 0.5798 / 0.1856 | 0.8785 / 0.2812 |
| relu | Bambu | 8,776 / 2,425 | 0.9977 / 0.3508 | 1.512 / 0.5315 |
| relu | XLS | 849.3 / 235.1 | 0.2537 / 0.0791 | 0.3904 / 0.1217 |
| axpy | Vitis opt | 62,301 / 19,551 | 5.716 / 1.733 | 8.661 / 2.625 |
| axpy | Bambu | 69,396 / 21,536 | 6.503 / 2.044 | 9.854 / 3.097 |
| axpy | XLS | 56,854 / 18,274 | 5.335 / 1.662 | 8.208 / 2.557 |
| rowsum | Vitis opt | 4,246 / 1,194 | 0.3851 / 0.1044 | 0.5835 / 0.1582 |
| rowsum | Bambu | 7,703 / 2,134 | 0.7555 / 0.242 | 1.145 / 0.3667 |
| rowsum | XLS | 3,898 / 1,096 | 0.3864 / 0.1008 | 0.5945 / 0.1551 |

The order of the cases (smallest to largest) is the same on both technologies in 87 of 120 comparisons (kernel, W and metric with at least two cases).
<!-- /gen -->

## 5. Notes

- Vitis dace_w1 of dot, axpy and rowsum: rebuilt for n2048 with their RAM as an SRAM macro (dot, axpy) or flops (rowsum), X62 (CSYN1 R3); parked on nangate15, which has no macros.
- forge's tier done rows on nangate15 are CTRL1's RTL (`f9764d5`, the setup table's second commit), not rerun in CTRL2 R5, which is nangate45 only (snax-forge D159): in section 4 each forge cell sets CTRL2's nangate45 value beside CTRL1's nangate15 one, so forge's nangate45 areas there are 297 to 617 µm² below what CTRL1's RTL gave in Part A (its leaner ctrl and csr). The order agrees in 87 of 120 comparisons, one fewer than before CTRL2.
- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.
