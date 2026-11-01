# SYN1 analysis: snax-forge beside HLS tier done

Written by `report/analysis_syn1.py` (`pixi run analysis`) from the committed CSVs (R4's `results/forge_vs_hls_<tech>.csv`, `results/{hls,forge}/<tech>/synth_dc*.csv`, `power_pt*.csv`, `results/hls/hls_cycles.csv`), the committed `reference.rpt` (the flop's area), hls-exercises' Verilog and forge's bundles (the registers by name). Every number is computed; nothing is typed by hand. n2048 only, both technologies, W = 1 to 32: 61 HLS and 48 forge points per technology (HLS dot `dace_w1` parked). This note decides nothing: it is for review, before the comparisons are chosen. PT is the reference for energy (X25). Each section gives observations, explanations (with how sure each is and its evidence) and questions.

## Summary

- **Control overhead.** Forge's csr + ctrl is a fixed block (1,796–5,120 µm² on nangate45; 98 % of its flops are 32-bit counters and CSRs) with a near-constant energy per cycle, so its share of e_run halves with each doubling of W. On nangate45 at W = 1 it is vecadd 65 %, vecmul 11 %, vsum 53 %, dot 2 16 %, dot 3 17 %, dot 4 16 %, dot 5 16 %, dot 6 15 % of e_run; at W = 32 5.8 %, 0.4 %, 14.9 %, 0.7 %, 0.8 %, 0.6 %, 0.9 %, 0.9 % (section 2, rows `done/*/forge*_w1`, `_w32`).
- **Against HLS's own fixed cost.** HLS opt's per-cycle term α is vecadd 0.50, vecmul 0.53, vsum 2.49, dot 2.07 pJ/cycle against forge's vecadd 1.45, vecmul 1.47, vsum 3.68, dot 3 4.16 on nangate45 (fits over W, section 2): forge's overhead is the larger per cycle, and it matters where the datapath is small (one adder: vecadd, vsum) and W is small.
- **Latency.** Forge's window is N / W + 0 to 2 cycles and HLS opt's and dace's N / W + 2 to 4, except dot 5 and 6 (N / W + W + 1, + 2: 97 and 98 cycles at W = 32) and HLS unopt (2.09 to 4.50 cycles per element at W ≥ 2) (section 1).
- **Boundary.** HLS opt registers data per lane inside its block (vecadd 64, vecmul 128, vsum 51, dot 206 bits per lane; dot opt 394 to 6,732 flops), forge's ElementwiseLanes none (dot 3: 421 flops at every W); forge's operand registers sit in the streamers, outside SYN1. Every area and energy comparison inherits this (section 3).
- **dot variants below both HLS dot cases at every W** (unopt, opt): nangate45: area none, e_run dot 2, dot 3, dot 4, dot 5, dot 6, AxC none, ExC dot 2, dot 3, dot 4; nangate15: area none, e_run dot 2, dot 3, dot 4, dot 5, dot 6, AxC none, ExC dot 2, dot 3, dot 4. Lowest area per W: nangate45 HLS unopt; nangate15 HLS unopt; HLS has the lowest A x C at W = nangate45 1, 2; nangate15 1, 2 (section 5).
- **Metrics disagree** on the winning side in 9 of 48 (tech, kernel, W) cells, all at W = 1 and 2; the patterns (pJ/elem, A x C, E x C, throughput per area; f forge, h HLS): f/h/f/h 8x, h/h/f/h 1x (section 8).
- **HWCOST's shape** e_run = α C + β fits 15 of 16 forge design-technology pairs within 2 % over W (worst dot 6 on nangate15, 2.1 %); α is csr + ctrl plus every datapath block that works once per beat (section 2).
- **Not answerable from SYN1:** the streamers' share (forge's registers), narrower counters, J > 1, the cluster-level cycles (open questions).

## 1. Cycles

Cycles beyond the beats, cycles − N / W, at n2048 (N / W beats per input stream). The counts are the same on both technologies (every point). Forge's window is the COUNTER read back (X23), HLS's the `ap_start` to `ap_done` window (X12). Figure `fig1_cycles_overhead.png`: the same numbers against W.

**vecadd** (cycles − N / W)

| W | N / W | HLS unopt | HLS opt | HLS dace | forge |
|---|---|---|---|---|---|
| 1 | 2048 | 1 | 2 | 2 | 0 |
| 2 | 1024 | 7,169 | 2 | 2 | 0 |
| 4 | 512 | 6,657 | 2 | 3 | 0 |
| 8 | 256 | 6,401 | 2 | 3 | 0 |
| 16 | 128 | 6,273 | 2 | 3 | 0 |
| 32 | 64 | 6,209 | 2 | 3 | 0 |

**vecmul** (cycles − N / W)

| W | N / W | HLS unopt | HLS opt | HLS dace | forge |
|---|---|---|---|---|---|
| 1 | 2048 | 2,049 | 2 | 2 | 0 |
| 2 | 1024 | 7,169 | 2 | 2 | 0 |
| 4 | 512 | 6,657 | 2 | 3 | 0 |
| 8 | 256 | 6,401 | 2 | 3 | 0 |
| 16 | 128 | 6,273 | 2 | 3 | 0 |
| 32 | 64 | 6,209 | 2 | 3 | 0 |

**vsum** (cycles − N / W)

| W | N / W | HLS unopt | HLS opt | HLS dace | forge |
|---|---|---|---|---|---|
| 1 | 2048 | 2,049 | 2 | 3 | 1 |
| 2 | 1024 | 6,145 | 2 |  | 1 |
| 4 | 512 | 5,121 | 2 |  | 1 |
| 8 | 256 | 4,609 | 2 |  | 1 |
| 16 | 128 | 4,353 | 3 |  | 1 |
| 32 | 64 | 4,225 | 3 |  | 1 |

**dot** (cycles − N / W)

| W | N / W | HLS unopt | HLS opt | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 |
|---|---|---|---|---|---|---|---|---|
| 1 | 2048 | 4,097 | 3 | 2 | 1 | 2 | 2 | 3 |
| 2 | 1024 | 8,193 | 3 | 2 | 1 | 2 | 3 | 4 |
| 4 | 512 | 7,169 | 3 | 2 | 1 | 2 | 5 | 6 |
| 8 | 256 | 6,657 | 4 | 2 | 1 | 2 | 9 | 10 |
| 16 | 128 | 6,401 | 4 | 2 | 1 | 2 | 17 | 18 |
| 32 | 64 | 6,273 | 4 | 2 | 1 | 2 | 33 | 34 |

### Observations

- Forge's extra cycles are 0 (vecadd, vecmul), 1 (vsum, dot 3), 2 (dot 2, dot 4), W + 1 (dot 5) and W + 2 (dot 6): 48 of 48 forge rows (`done/*/forge*_w*`, nangate45).
- HLS opt's extra cycles are 2, 3, 4 at every W; dace's 2, 3.
- HLS unopt takes a cycles per beat (cosim's line a x loop_count + 1), a at W = 1, 2, 4, 8, 16, 32: vecadd 1/8/14/26/50/98, vecmul 2/8/14/26/50/98, vsum 2/7/11/19/35/67, dot 3/9/15/27/51/99. So at W ≥ 2 its window is 2.09 to 4.50 cycles per element.
- The largest forge overhead is dot 6 at W = 32: 98 cycles for 64 beats; dot 5: 97 (`dot/forge5_w32`).

### Explanations

- **Forge: C§17's closed forms** (snax-forge `docs/CONTRACTS.md` §17, J = 1 job of T = N / W beats): C2 = T + 2, C3 = T + 1, C4 = T + 2, C5 = T + W + 1, C6 = T + W + 2; vecadd and vecmul T, vsum's tree T + 1. Sure: the formula gives every forge row exactly (48 of 48). dot 5 and 6 pay W cycles because their serial sum reads one lane per cycle after the MAC lanes finish; dot 4's tree adds them in one cycle.
- **HLS opt and dace: the pipeline's depth.** The extra cycles equal the loop pipeline's depth in the Verilog (the number of `ap_enable_reg_pp0_iter<k>` stages) on 28 of 37 opt and dace points; where they differ: vecadd/dace_w4 (extra 3, depth 2), vecadd/dace_w8 (extra 3, depth 2), vecadd/dace_w16 (extra 3, depth 2), vecadd/dace_w32 (extra 3, depth 2), vecmul/dace_w4 (extra 3, depth 2), vecmul/dace_w8 (extra 3, depth 2), vecmul/dace_w16 (extra 3, depth 2), vecmul/dace_w32 (extra 3, depth 2), vsum/dace_w1 (extra 3, depth 2). Fairly sure: the depth is read from the RTL, the extra cycles from cosim's line; an extra cycle for the FSM's start state may account for the differences.
- **HLS unopt: the lanes are not pipelined.** unopt keeps NPBench's loop structure with no directives and `pipeline_loops 0` (hls-exercises `docs/HLS_VS_FORGE.md` §1), so each beat's W lanes run one after another: a grows with W. Sure for the mechanism (it is how the case is defined); the exact a per W is cosim's.

### Questions

- Forge's window starts at the accepted START and excludes the CSR writes and the streamers' own latency; HLS's starts at `ap_start` with the pins already set. Does the comparison need the cluster-level count (snax_cluster RTL with the streamers, BASE1) to be fair? A run of the dot variants on snax_cluster's RTL at n2048 would answer it.

## 2. Control overhead

Forge's csr and ctrl, the wrapper's two control instances (X22), against W. Shares are of the accelerator's total area and of e_run. Figure `fig2_control_share.png`: the shares against W, both technologies.

**nangate45** (shares at W = 1 / 2 / 4 / 8 / 16 / 32; the first W below each threshold)

| design | csr + ctrl µm² | area share % | e_run share % | area < 10 % | area < 5 % | e_run < 10 % | e_run < 5 % |
|---|---|---|---|---|---|---|---|
| vecadd | 1,796–1,796 | 86.9 / 76.9 / 62.4 / 45.4 / 29.4 / 17.2 | 65.3 / 48.6 / 32.3 / 19.2 / 10.8 / 5.8 | > 32 | > 32 | W = 32 | > 32 |
| vecmul | 1,796–1,796 | 20.6 / 11.5 / 6.1 / 3.1 / 1.6 / 0.8 | 11.4 / 6.1 / 3.2 / 1.6 / 0.8 / 0.4 | W = 4 | W = 8 | W = 2 | W = 4 |
| vsum | 2,622–2,623 | 75.7 / 70.3 / 61.4 / 49.1 / 35.1 / 22.3 | 53.3 / 48.7 / 42.2 / 33.2 / 23.5 / 14.9 | > 32 | > 32 | > 32 | > 32 |
| dot 2 | 5,085–5,120 | 38.3 / 24.3 / 14.0 / 7.7 / 4.0 / 2.0 | 16.4 / 9.5 / 5.2 / 2.7 / 1.4 / 0.7 | W = 8 | W = 16 | W = 2 | W = 8 |
| dot 3 | 5,043–5,044 | 39.4 / 25.2 / 14.7 / 8.0 / 4.2 / 2.1 | 17.2 / 9.9 / 5.4 / 2.9 / 1.5 / 0.8 | W = 8 | W = 16 | W = 2 | W = 8 |
| dot 4 | 3,028–3,033 | 27.3 / 15.9 / 8.7 / 4.6 / 2.3 / 1.2 | 15.9 / 8.7 / 4.6 / 2.4 / 1.2 / 0.6 | W = 4 | W = 8 | W = 2 | W = 4 |
| dot 5 | 3,037–3,116 | 27.3 / 15.8 / 8.9 / 4.8 / 2.4 / 1.2 | 15.9 / 8.8 / 4.7 / 2.5 / 1.4 / 0.9 | W = 4 | W = 8 | W = 2 | W = 4 |
| dot 6 | 3,072–3,134 | 26.4 / 15.3 / 8.5 / 4.5 / 2.3 / 1.2 | 15.5 / 8.6 / 4.6 / 2.4 / 1.4 / 0.9 | W = 4 | W = 8 | W = 2 | W = 4 |

**nangate15** (shares at W = 1 / 2 / 4 / 8 / 16 / 32; the first W below each threshold)

| design | csr + ctrl µm² | area share % | e_run share % | area < 10 % | area < 5 % | e_run < 10 % | e_run < 5 % |
|---|---|---|---|---|---|---|---|
| vecadd | 454–454 | 85.8 / 75.2 / 60.3 / 43.2 / 27.5 / 16.0 | 67.5 / 50.9 / 34.2 / 20.6 / 11.5 / 6.2 | > 32 | > 32 | W = 32 | > 32 |
| vecmul | 454–454 | 17.0 / 9.3 / 4.9 / 2.5 / 1.3 / 0.6 | 9.8 / 5.1 / 2.6 / 1.3 / 0.7 / 0.3 | W = 2 | W = 4 | W = 1 | W = 4 |
| vsum | 684–684 | 75.4 / 69.6 / 60.5 / 47.9 / 33.9 / 21.4 | 48.1 / 45.7 / 40.9 / 33.6 / 25.1 / 16.7 | > 32 | > 32 | > 32 | > 32 |
| dot 2 | 1,381–1,382 | 35.1 / 21.8 / 12.4 / 6.7 / 3.5 / 1.8 | 13.8 / 7.9 / 4.2 / 2.2 / 1.1 / 0.6 | W = 8 | W = 16 | W = 2 | W = 4 |
| dot 3 | 1,385–1,385 | 36.2 / 22.7 / 13.0 / 7.0 / 3.6 / 1.9 | 14.5 / 8.3 / 4.5 / 2.4 / 1.2 / 0.6 | W = 8 | W = 16 | W = 2 | W = 4 |
| dot 4 | 778–778 | 23.5 / 13.4 / 7.2 / 3.7 / 1.9 / 1.0 | 13.4 / 7.2 / 3.8 / 1.9 / 1.0 / 0.5 | W = 4 | W = 8 | W = 2 | W = 4 |
| dot 5 | 777–794 | 23.4 / 13.3 / 7.3 / 3.8 / 2.0 / 1.0 | 13.4 / 7.3 / 3.8 / 2.0 / 1.1 / 0.7 | W = 4 | W = 8 | W = 2 | W = 4 |
| dot 6 | 779–796 | 22.7 / 12.8 / 7.0 / 3.7 / 1.9 / 1.0 | 13.1 / 7.1 / 3.8 / 2.0 / 1.1 / 0.7 | W = 4 | W = 8 | W = 2 | W = 4 |

What the control holds (registers in the bundle's SV at W = 4; Chisel declares a `reg` only for a flop). On nangate15 every flop has the same area (1.27795 µm², `reference.rpt`), so a module's flops are its sequential area over that: csr + ctrl + datapath = DC's flop count on 48 of 48 forge points.

| design | csr flop bits | ctrl flop bits | 32-bit registers in ctrl | their names |
|---|---|---|---|---|
| vecadd | 97 | 99 | 3 | acc_r, acc_given, counter |
| vecmul | 97 | 99 | 3 | acc_r, acc_given, counter |
| vsum | 129 | 164 | 5 | acc_t, acc_r, acc_d, acc_given, counter |
| dot 2 | 129 | 229 | 7 | sum_t, sum_r, mul_r, mul_given, sum_d, sum_given, counter |
| dot 3 | 129 | 228 | 7 | sum_t, sum_r, mul_r, mul_given, sum_d, sum_given, counter |
| dot 4 | 129 | 197 | 6 | mac_t, sum_r, mac_d, mac_given, sum_given, counter |
| dot 5 | 129 | 199 | 6 | mac_t, sum_r, mac_d, mac_given, sum_given, counter |
| dot 6 | 129 | 200 | 6 | mac_t, sum_r, mac_d, mac_given, sum_given, counter |

**Fits over W** (6 points per design). (a) csr + ctrl energy per cycle (pJ) against W: intercept, slope per lane, R² and the spread (max − min over the mean). (b) the datapath's energy per task (nJ, e_dp x cycles) against W: intercept, slope, R² and the change from W = 1 to 32. R² says little where the slope is near 0; the spread and the change say whether the quantity is flat.

| tech | design | (a) icpt pJ | (a) slope pJ/lane | (a) R² | (a) spread % | (b) icpt nJ | (b) slope nJ/lane | (b) R² | (b) W 1→32 % |
|---|---|---|---|---|---|---|---|---|---|
| nangate45 | vecadd | 1.461 | 0.0016 | 0.91 | 3.6 | 1.586 | -0.0002 | 0.45 | -0.3 |
| nangate45 | vecmul | 1.461 | 0.0016 | 0.91 | 3.6 | 23.119 | -0.0000 | 0.00 | -0.1 |
| nangate45 | vsum | 2.155 | 0.0018 | 0.93 | 2.8 | 2.457 | -0.0660 | 0.45 | -78.7 |
| nangate45 | dot 2 | 2.656 | 0.0025 | 0.89 | 3.1 | 26.195 | -0.0664 | 0.45 | -10.9 |
| nangate45 | dot 3 | 2.656 | 0.0027 | 0.93 | 3.3 | 24.803 | -0.0670 | 0.48 | -11.5 |
| nangate45 | dot 4 | 2.394 | 0.0023 | 0.84 | 3.1 | 25.747 | 0.0008 | 0.04 | -0.0 |
| nangate45 | dot 5 | 2.399 | 0.0029 | 0.87 | 4.2 | 25.544 | -0.0078 | 0.12 | -1.3 |
| nangate45 | dot 6 | 2.408 | 0.0027 | 0.81 | 3.8 | 26.252 | 0.0035 | 0.02 | -0.7 |
| nangate15 | vecadd | 0.410 | 0.0002 | 0.96 | 1.4 | 0.406 | -0.0000 | 0.40 | -0.3 |
| nangate15 | vecmul | 0.410 | 0.0002 | 0.96 | 1.4 | 7.755 | -0.0008 | 0.40 | -0.4 |
| nangate15 | vsum | 0.590 | 0.0004 | 1.00 | 1.9 | 0.781 | -0.0237 | 0.44 | -85.1 |
| nangate15 | dot 2 | 0.731 | 0.0004 | 1.00 | 1.8 | 8.840 | -0.0240 | 0.43 | -12.1 |
| nangate15 | dot 3 | 0.730 | 0.0004 | 1.00 | 1.9 | 8.306 | -0.0244 | 0.44 | -12.9 |
| nangate15 | dot 4 | 0.653 | 0.0004 | 1.00 | 2.0 | 8.610 | 0.0003 | 0.02 | -0.3 |
| nangate15 | dot 5 | 0.655 | 0.0005 | 0.90 | 2.7 | 8.574 | 0.0003 | 0.00 | -0.3 |
| nangate15 | dot 6 | 0.657 | 0.0006 | 0.90 | 2.8 | 8.751 | 0.0062 | 0.42 | +1.1 |

**The two-term model** e_run = α C + β, fitted over W per design (x = the cycles C): α is an energy per cycle (pJ), β an energy per task (nJ). The HWCOST shape $E_{\mathit{task}} = C \thinspace e_{\mathit{ctrl}} + n_{\mathit{fire}} \thinspace E_{\mathit{block}}$ is this with α = e_ctrl and β = n_fire E_block. The last column compares α with the measured csr + ctrl energy per cycle (mean over W).

| tech | design | α pJ/cycle | β nJ | R² | max error % | α − (csr + ctrl) pJ/cycle |
|---|---|---|---|---|---|---|
| nangate45 | vecadd | 1.454 | 1.589 | 1.0000 | 0.4 | -0.024 |
| nangate45 | vecmul | 1.470 | 23.114 | 0.9998 | 0.1 | -0.008 |
| nangate45 | vsum | 3.680 | 0.739 | 1.0000 | 1.4 | 1.505 |
| nangate45 | dot 2 | 4.179 | 24.473 | 0.9998 | 0.2 | 1.497 |
| nangate45 | dot 3 | 4.159 | 23.089 | 0.9997 | 0.3 | 1.475 |
| nangate45 | dot 4 | 2.415 | 25.742 | 0.9995 | 0.3 | -0.002 |
| nangate45 | dot 5 | 2.673 | 25.274 | 0.9949 | 0.8 | 0.244 |
| nangate45 | dot 6 | 2.666 | 26.113 | 0.9854 | 1.7 | 0.229 |
| nangate15 | vecadd | 0.410 | 0.405 | 1.0000 | 0.3 | -0.001 |
| nangate15 | vecmul | 0.426 | 7.736 | 0.9993 | 0.2 | 0.014 |
| nangate15 | vsum | 1.150 | 0.156 | 1.0000 | 1.3 | 0.556 |
| nangate15 | dot 2 | 1.301 | 8.204 | 0.9999 | 0.2 | 0.565 |
| nangate15 | dot 3 | 1.303 | 7.665 | 0.9999 | 0.2 | 0.568 |
| nangate15 | dot 4 | 0.672 | 8.601 | 0.9980 | 0.3 | 0.014 |
| nangate15 | dot 5 | 0.700 | 8.547 | 0.9932 | 0.8 | 0.039 |
| nangate15 | dot 6 | 0.676 | 8.804 | 0.9542 | 2.1 | 0.013 |

**The datapath's blocks**: energy per cycle (pJ) and per task (nJ) at W = 1 and W = 32, and the same two-term fit per block (α per cycle, β per task). vecadd's and vecmul's datapath is one elementwise block (fit (b): flat).

| tech | design | block | pJ/cycle W 1 | pJ/cycle W 32 | nJ/task W 1 | nJ/task W 32 | α pJ/cycle | β nJ |
|---|---|---|---|---|---|---|---|---|
| nangate45 | vsum | acc | 1.884 | 12.638 | 3.860 | 0.821 | 1.533 | 0.732 |
| nangate45 | dot 2 | mul | 10.831 | 335.719 | 22.205 | 22.157 | 0.029 | 22.145 |
| nangate45 | dot 2 | sum | 1.865 | 12.426 | 3.823 | 0.820 | 1.516 | 0.736 |
| nangate45 | dot 2 | tmp0 | 0.759 | 24.073 | 1.555 | 1.589 | -0.007 | 1.582 |
| nangate45 | dot 3 | mul | 10.874 | 343.380 | 22.281 | 22.320 | -0.017 | 22.343 |
| nangate45 | dot 3 | sum | 1.883 | 12.630 | 3.859 | 0.821 | 1.533 | 0.736 |
| nangate45 | dot 4 | mac | 12.131 | 380.098 | 24.869 | 25.086 | -0.072 | 25.028 |
| nangate45 | dot 4 | sum | 0.459 | 10.931 | 0.941 | 0.721 | 0.107 | 0.704 |
| nangate45 | dot 5 | mac | 12.140 | 261.369 | 24.886 | 25.353 | -0.119 | 25.068 |
| nangate45 | dot 5 | sum | 0.459 | 1.450 | 0.941 | 0.141 | 0.415 | 0.191 |
| nangate45 | dot 6 | mac | 12.132 | 258.485 | 24.884 | 25.332 | -0.108 | 25.047 |
| nangate45 | dot 6 | sum | 0.459 | 1.104 | 0.942 | 0.108 | 0.438 | 0.034 |
| nangate45 | dot 6 | out_partial | 0.459 | 11.653 | 0.941 | 1.142 | -0.050 | 1.017 |
| nangate15 | vsum | acc | 0.638 | 3.000 | 1.307 | 0.195 | 0.560 | 0.155 |
| nangate15 | dot 2 | mul | 3.670 | 113.486 | 7.524 | 7.490 | 0.015 | 7.497 |
| nangate15 | dot 2 | sum | 0.632 | 2.938 | 1.296 | 0.194 | 0.554 | 0.156 |
| nangate15 | dot 2 | tmp0 | 0.271 | 8.488 | 0.556 | 0.560 | 0.001 | 0.550 |
| nangate15 | dot 3 | mul | 3.681 | 115.432 | 7.542 | 7.503 | 0.018 | 7.508 |
| nangate15 | dot 3 | sum | 0.632 | 2.985 | 1.296 | 0.194 | 0.554 | 0.156 |
| nangate15 | dot 4 | mac | 4.097 | 128.228 | 8.399 | 8.463 | -0.026 | 8.443 |
| nangate15 | dot 4 | sum | 0.122 | 2.439 | 0.251 | 0.161 | 0.045 | 0.158 |
| nangate15 | dot 5 | mac | 4.096 | 88.327 | 8.397 | 8.568 | -0.052 | 8.476 |
| nangate15 | dot 5 | sum | 0.122 | 0.570 | 0.251 | 0.055 | 0.100 | 0.069 |
| nangate15 | dot 6 | mac | 4.094 | 87.478 | 8.398 | 8.573 | -0.054 | 8.479 |
| nangate15 | dot 6 | sum | 0.121 | 0.379 | 0.248 | 0.037 | 0.113 | 0.014 |
| nangate15 | dot 6 | out_partial | 0.122 | 3.963 | 0.251 | 0.388 | -0.037 | 0.308 |

**The same fit on HLS opt and dace**, for comparison: HLS's per-cycle term α holds its own fixed state (the pins, the loop's counters and accumulator, the FSM), its per-task term β the per-lane registers and the arithmetic. The last column is forge's α for the same kernel (dot: dot 3).

| tech | kernel | case | α pJ/cycle | β nJ | R² | max error % | forge α pJ/cycle |
|---|---|---|---|---|---|---|---|
| nangate45 | vecadd | HLS opt | 0.499 | 2.993 | 0.9998 | 0.3 | 1.454 (vecadd) |
| nangate45 | vecadd | HLS dace | 0.674 | 3.034 | 0.9949 | 2.0 | 1.454 (vecadd) |
| nangate45 | vecmul | HLS opt | 0.531 | 28.367 | 0.9920 | 0.2 | 1.470 (vecmul) |
| nangate45 | vecmul | HLS dace | 0.710 | 28.402 | 0.9930 | 0.3 | 1.470 (vecmul) |
| nangate45 | vsum | HLS opt | 2.490 | 1.886 | 0.9958 | 5.9 | 3.680 (vsum) |
| nangate45 | dot | HLS opt | 2.067 | 29.991 | 0.9892 | 0.8 | 4.159 (dot 3) |
| nangate15 | vecadd | HLS opt | 0.149 | 0.938 | 0.9997 | 0.3 | 0.410 (vecadd) |
| nangate15 | vecadd | HLS dace | 0.195 | 0.948 | 0.9963 | 1.5 | 0.410 (vecadd) |
| nangate15 | vecmul | HLS opt | 0.168 | 9.014 | 0.9953 | 0.1 | 0.426 (vecmul) |
| nangate15 | vecmul | HLS dace | 0.214 | 9.024 | 0.9941 | 0.3 | 0.426 (vecmul) |
| nangate15 | vsum | HLS opt | 0.784 | 0.581 | 0.9958 | 6.3 | 1.150 (vsum) |
| nangate15 | dot | HLS opt | 0.646 | 9.603 | 0.9839 | 0.9 | 1.303 (dot 3) |

### Observations

- ctrl's area hardly moves with W: on nangate45 it spans vecadd 1,009–1,009 µm², vecmul 1,009–1,009 µm², vsum 1,587–1,588 µm², dot 2 4,040–4,062 µm², dot 3 3,999–4,000 µm², dot 4 1,984–1,998 µm², dot 5 1,970–2,054 µm², dot 6 2,005–2,074 µm²; csr 788–1,067 µm² over every design and W.
- nangate45: csr + ctrl falls below 10 % of the area at W = beyond 32 (vecadd), 4 (vecmul), beyond 32 (vsum), 8 (dot 2), 8 (dot 3), 4 (dot 4), 4 (dot 5), 4 (dot 6); below 10 % of e_run at W = 32 (vecadd), 2 (vecmul), beyond 32 (vsum), 2 (dot 2), 2 (dot 3), 2 (dot 4), 2 (dot 5), 2 (dot 6).
- nangate15: csr + ctrl falls below 10 % of the area at W = beyond 32 (vecadd), 2 (vecmul), beyond 32 (vsum), 8 (dot 2), 8 (dot 3), 4 (dot 4), 4 (dot 5), 4 (dot 6); below 10 % of e_run at W = 32 (vecadd), 1 (vecmul), beyond 32 (vsum), 2 (dot 2), 2 (dot 3), 2 (dot 4), 2 (dot 5), 2 (dot 6).
- The two-term model fits 15 of 16 design-technology pairs within 2 % at every W; the worst is dot 6 on nangate15, 2.1 %.

### Explanations

- **ctrl and csr are fixed per accelerator, not per lane.** Their registers are 32-bit counters and CSR copies whose number depends on the group (its units, a JOB_BEATS), not on W (table above; C§17: the control keeps a register only for what changes at run time). Sure: the flop counts are read from the SV and match DC's.
- **Their energy is a cost per cycle.** The counters and CSR registers are clocked every cycle of the window, so csr + ctrl energy per cycle is near constant in W (spread in fit (a)) and their energy per task scales with the cycles, N / W + the overhead. The share therefore halves with each doubling of W. Sure where the spread is small; the measured per-cycle values come from PT's module rows.
- **The datapath splits the same way, by what each block does per beat.** A block that does one 64-bit operation per beat, whatever W, costs per cycle: the accumulator of a tree that folds every beat (vsum, dot 2 and dot 3's `sum`). A block whose work is spread over the lanes costs per task: the multiply lanes, the MAC lanes (W accumulators, each updated once per beat, so N updates per task) and a link buffer of W words. On nangate45 α exceeds csr + ctrl's own per-cycle energy by more than 0.5 pJ on vsum (1.51), dot 2 (1.50), dot 3 (1.48), and by less than 0.1 pJ on vecadd (-0.02), vecmul (-0.01), dot 4 (-0.00). The block table shows it per block: dot 3's `sum` has α 1.53 pJ/cycle, dot 4's `sum` (folding once per job, after the MAC lanes) 0.11, dot 4's `mac` -0.07 with β 25.03 nJ. Fairly sure: the per-block numbers are PT's module rows, the per-beat behaviour is C§17's (the fold reads every beat, a MAC lane fires once per beat); the fit has six points per design.
- **So α is not only csr + ctrl,** and the HWCOST shape holds per block: e_ctrl is csr + ctrl plus every block that works once per beat, E_block the rest per firing. dot 5 and 6's serial `sum` adds about 0.24 pJ per cycle on nangate45: it is busy only in the W-cycle tail.

### Questions

- The counters are 32 bits because the CSRs are; at n2048 a beat count needs 12 bits. How much of ctrl's area and per-cycle energy would narrower counters save? A resynthesis with a counter width parameter in snax-forge's `GroupCtrl` would answer it (no such parameter exists today).
- Is csr + ctrl's cost a fixed cost per accelerator that a cluster pays once for several groups (dot 1 has two groups, not in SYN1)? A two-group design point in SYN1 would show whether csr and ctrl grow per group.

## 3. Area

Total area per kernel and W, forge against each HLS case; for forge also the datapath + ctrl (the accelerator without its CSR block). Figure `fig3_area.png`: totals against W, both technologies.

**vecadd, nangate45** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 861 | 1,301 | 1,420 | 2,068 | 1,279 |
| 2 | 4,828 | 1,980 | 2,273 | 2,338 | 1,548 |
| 4 | 7,445 | 3,340 | 3,779 | 2,877 | 2,088 |
| 8 | 12,834 | 6,057 | 6,459 | 3,956 | 3,167 |
| 16 | 23,544 | 11,489 | 11,864 | 6,114 | 5,324 |
| 32 | 44,691 | 22,358 | 22,700 | 10,429 | 9,640 |

**vecmul, nangate45** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 7,526 | 8,368 | 8,487 | 8,711 | 7,921 |
| 2 | 11,474 | 16,114 | 16,407 | 15,623 | 14,834 |
| 4 | 14,103 | 31,608 | 32,048 | 29,448 | 28,659 |
| 8 | 19,425 | 62,598 | 63,004 | 57,098 | 56,309 |
| 16 | 30,201 | 124,575 | 124,948 | 112,399 | 111,610 |
| 32 | 51,349 | 248,533 | 248,870 | 223,000 | 222,210 |

**vsum, nangate45** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 2,320 | 2,383 | 1,922 | 3,465 | 2,429 |
| 2 | 4,278 | 3,060 | parked | 3,731 | 2,695 |
| 4 | 5,238 | 4,414 | parked | 4,267 | 3,231 |
| 8 | 7,176 | 6,309 | parked | 5,336 | 4,300 |
| 16 | 11,016 | 10,926 | parked | 7,473 | 6,437 |
| 32 | 18,473 | 20,961 | parked | 11,746 | 10,709 |

**dot, nangate45** (µm²)

| W | HLS unopt | HLS opt | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 | dot 2 dp + ctrl | dot 3 dp + ctrl | dot 4 dp + ctrl | dot 5 dp + ctrl | dot 6 dp + ctrl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 9,692 | 10,139 | 13,321 | 12,801 | 11,125 | 11,129 | 11,626 | 12,275 | 11,755 | 10,088 | 10,062 | 10,558 |
| 2 | 12,838 | 18,560 | 20,962 | 19,978 | 19,022 | 19,216 | 20,182 | 19,916 | 18,932 | 17,986 | 18,180 | 19,114 |
| 4 | 14,770 | 35,404 | 36,245 | 34,337 | 34,830 | 34,667 | 36,494 | 35,199 | 33,291 | 33,794 | 33,630 | 35,426 |
| 8 | 18,631 | 69,955 | 66,823 | 63,053 | 66,425 | 65,450 | 69,140 | 65,762 | 62,007 | 65,380 | 64,382 | 68,079 |
| 16 | 26,252 | 138,987 | 127,916 | 120,487 | 129,629 | 126,986 | 134,390 | 126,870 | 119,440 | 128,593 | 125,918 | 133,329 |
| 32 | 41,157 | 273,743 | 250,196 | 235,350 | 256,024 | 250,028 | 264,824 | 249,140 | 234,303 | 254,988 | 248,982 | 263,763 |

**vecadd, nangate15** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 246 | 369 | 406 | 529 | 334 |
| 2 | 1,400 | 558 | 634 | 604 | 409 |
| 4 | 2,146 | 937 | 1,060 | 753 | 558 |
| 8 | 3,694 | 1,693 | 1,807 | 1,052 | 857 |
| 16 | 6,695 | 3,207 | 3,311 | 1,650 | 1,455 |
| 32 | 12,836 | 6,233 | 6,329 | 2,845 | 2,650 |

**vecmul, nangate15** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 2,387 | 2,611 | 2,648 | 2,667 | 2,472 |
| 2 | 3,529 | 5,043 | 5,119 | 4,880 | 4,684 |
| 4 | 4,275 | 9,905 | 10,029 | 9,304 | 9,109 |
| 8 | 5,823 | 19,632 | 19,746 | 18,155 | 17,960 |
| 16 | 8,824 | 39,084 | 39,189 | 35,857 | 35,662 |
| 32 | 14,964 | 77,987 | 78,082 | 71,260 | 71,064 |

**vsum, nangate15** (µm²)

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp + ctrl |
|---|---|---|---|---|---|
| 1 | 673 | 686 | 538 | 908 | 646 |
| 2 | 1,244 | 865 | parked | 983 | 721 |
| 4 | 1,504 | 1,241 | parked | 1,131 | 869 |
| 8 | 2,049 | 1,768 | parked | 1,428 | 1,165 |
| 16 | 3,092 | 3,064 | parked | 2,020 | 1,758 |
| 32 | 5,226 | 5,855 | parked | 3,204 | 2,942 |

**dot, nangate15** (µm²)

| W | HLS unopt | HLS opt | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 | dot 2 dp + ctrl | dot 3 dp + ctrl | dot 4 dp + ctrl | dot 5 dp + ctrl | dot 6 dp + ctrl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3,003 | 3,122 | 3,932 | 3,822 | 3,315 | 3,315 | 3,430 | 3,670 | 3,560 | 3,053 | 3,052 | 3,168 |
| 2 | 3,925 | 5,741 | 6,333 | 6,110 | 5,814 | 5,863 | 6,093 | 6,071 | 5,847 | 5,551 | 5,601 | 5,831 |
| 4 | 4,438 | 10,980 | 11,135 | 10,683 | 10,808 | 10,757 | 11,216 | 10,873 | 10,421 | 10,546 | 10,495 | 10,953 |
| 8 | 5,524 | 21,677 | 20,738 | 19,829 | 20,843 | 20,554 | 21,474 | 20,476 | 19,567 | 20,580 | 20,292 | 21,211 |
| 16 | 7,604 | 43,092 | 39,944 | 38,123 | 40,172 | 39,421 | 41,252 | 39,682 | 37,861 | 39,910 | 39,159 | 40,990 |
| 32 | 11,868 | 85,011 | 78,354 | 74,708 | 79,527 | 77,840 | 81,492 | 78,092 | 74,446 | 79,265 | 77,578 | 81,230 |

**First-order fits of area against W** (µm² = slope W + intercept, 6 points):

| tech | kernel | what | slope µm²/lane | intercept µm² | R² |
|---|---|---|---|---|---|
| nangate45 | vecadd | forge datapath | 269.7 | -0.0 | 1.00000 |
| nangate45 | vecadd | HLS opt total | 679.2 | 622.3 | 1.00000 |
| nangate45 | vecadd | HLS unopt total | 1,365.5 | 1,362.4 | 0.99624 |
| nangate45 | vecmul | forge datapath | 6,912.5 | 0.0 | 1.00000 |
| nangate45 | vecmul | HLS opt total | 7,747.3 | 619.6 | 1.00000 |
| nangate45 | vecmul | HLS unopt total | 1,365.8 | 8,005.3 | 0.99632 |
| nangate45 | vsum | forge datapath | 267.1 | 574.7 | 1.00000 |
| nangate45 | vsum | HLS opt total | 593.7 | 1,775.5 | 0.99886 |
| nangate45 | vsum | HLS unopt total | 493.8 | 2,898.7 | 0.99053 |
| nangate45 | dot | dot 2 datapath | 7,640.3 | 586.4 | 1.00000 |
| nangate45 | dot | dot 3 datapath | 7,179.1 | 575.0 | 1.00000 |
| nangate45 | dot | dot 4 datapath | 7,900.0 | 193.2 | 1.00000 |
| nangate45 | dot | dot 5 datapath | 7,696.9 | 682.7 | 1.00000 |
| nangate45 | dot | dot 6 datapath | 8,158.5 | 673.7 | 1.00000 |
| nangate45 | dot | HLS opt total | 8,515.7 | 1,716.4 | 0.99997 |
| nangate45 | dot | HLS unopt total | 974.4 | 10,325.6 | 0.99450 |
| nangate15 | vecadd | forge datapath | 74.7 | -0.0 | 1.00000 |
| nangate15 | vecadd | HLS opt total | 189.2 | 179.9 | 1.00000 |
| nangate15 | vecadd | HLS unopt total | 391.4 | 393.1 | 0.99619 |
| nangate15 | vecmul | forge datapath | 2,212.7 | -0.4 | 1.00000 |
| nangate15 | vecmul | HLS opt total | 2,431.5 | 179.7 | 1.00000 |
| nangate15 | vecmul | HLS unopt total | 391.2 | 2,525.8 | 0.99630 |
| nangate15 | vsum | forge datapath | 74.1 | 150.3 | 1.00000 |
| nangate15 | vsum | HLS opt total | 165.4 | 509.6 | 0.99891 |
| nangate15 | vsum | HLS unopt total | 138.6 | 842.5 | 0.99010 |
| nangate15 | dot | dot 2 datapath | 2,400.7 | 150.4 | 1.00000 |
| nangate15 | dot | dot 3 datapath | 2,286.6 | 150.4 | 1.00000 |
| nangate15 | dot | dot 4 datapath | 2,455.6 | 184.7 | 0.99998 |
| nangate15 | dot | dot 5 datapath | 2,398.6 | 322.0 | 0.99997 |
| nangate15 | dot | dot 6 datapath | 2,512.7 | 322.1 | 0.99998 |
| nangate15 | dot | HLS opt total | 2,644.9 | 498.7 | 0.99998 |
| nangate15 | dot | HLS unopt total | 273.5 | 3,188.1 | 0.99435 |

**Flops**, nangate45 (DC's `seq_cells`), and where they sit. Forge per module (nangate15's sequential area over the flop's area, the same counts on both technologies); HLS by class, from the names Vitis assigns on the clock edge in its Verilog (their bit sum next to DC's count, which differs by a few bits where DC merged or removed constant flops).

| kernel | W | case | DC flops | where |
|---|---|---|---|---|
| vecadd | 1 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecadd | 1 | HLS unopt | 67 | RTL 67: pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 2 |
| vecadd | 1 | HLS opt | 134 | RTL 134: data pipeline (operands, products) 64, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecadd | 1 | HLS dace | 163 | RTL 164: data pipeline (operands, products) 95, pins (loop_count, len) 33, loop state (accumulator, counters) 31, control (FSM, pipeline enables) 5 |
| vecadd | 4 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecadd | 4 | HLS unopt | 1070 | RTL 1068: data pipeline (operands, products) 998, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecadd | 4 | HLS opt | 326 | RTL 326: data pipeline (operands, products) 256, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecadd | 4 | HLS dace | 384 | RTL 364: data pipeline (operands, products) 287, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 12 |
| vecadd | 32 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecadd | 32 | HLS unopt | 6455 | RTL 6450: data pipeline (operands, products) 6380, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecadd | 32 | HLS opt | 2118 | RTL 2118: data pipeline (operands, products) 2048, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecadd | 32 | HLS dace | 2164 | RTL 2156: data pipeline (operands, products) 2079, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 12 |
| vecmul | 1 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecmul | 1 | HLS unopt | 68 | RTL 68: pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 3 |
| vecmul | 1 | HLS opt | 198 | RTL 198: data pipeline (operands, products) 128, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecmul | 1 | HLS dace | 227 | RTL 228: data pipeline (operands, products) 159, pins (loop_count, len) 33, loop state (accumulator, counters) 31, control (FSM, pipeline enables) 5 |
| vecmul | 4 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecmul | 4 | HLS unopt | 1070 | RTL 1068: data pipeline (operands, products) 998, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecmul | 4 | HLS opt | 582 | RTL 582: data pipeline (operands, products) 512, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecmul | 4 | HLS dace | 640 | RTL 620: data pipeline (operands, products) 543, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 12 |
| vecmul | 32 | forge | 196 | csr 97, ctrl 99, datapath 0 |
| vecmul | 32 | HLS unopt | 6455 | RTL 6450: data pipeline (operands, products) 6380, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecmul | 32 | HLS opt | 4166 | RTL 4166: data pipeline (operands, products) 4096, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 5 |
| vecmul | 32 | HLS dace | 4212 | RTL 4204: data pipeline (operands, products) 4127, pins (loop_count, len) 33, loop state (accumulator, counters) 32, control (FSM, pipeline enables) 12 |
| vsum | 1 | forge | 357 | csr 129, ctrl 164, datapath 64 |
| vsum | 1 | HLS unopt | 262 | RTL 262: loop state (accumulator, counters) 128, pins (loop_count, len) 66, data pipeline (operands, products) 64, control (FSM, pipeline enables) 3, conditions 1 |
| vsum | 1 | HLS opt | 264 | RTL 264: loop state (accumulator, counters) 128, pins (loop_count, len) 66, data pipeline (operands, products) 64, control (FSM, pipeline enables) 5, conditions 1 |
| vsum | 1 | HLS dace | 230 | RTL 233: data pipeline (operands, products) 95, loop state (accumulator, counters) 95, pins (loop_count, len) 33, control (FSM, pipeline enables) 10 |
| vsum | 4 | forge | 357 | csr 129, ctrl 164, datapath 64 |
| vsum | 4 | HLS unopt | 654 | RTL 654: data pipeline (operands, products) 454, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 5, conditions 1 |
| vsum | 4 | HLS opt | 456 | RTL 456: data pipeline (operands, products) 256, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 5, conditions 1 |
| vsum | 32 | forge | 357 | csr 129, ctrl 164, datapath 64 |
| vsum | 32 | HLS unopt | 2452 | RTL 2452: data pipeline (operands, products) 2252, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 5, conditions 1 |
| vsum | 32 | HLS opt | 1866 | RTL 1866: data pipeline (operands, products) 1664, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 6, conditions 2 |
| dot | 1 | dot 2 | 486 | csr 129, ctrl 229, datapath 128 |
| dot | 1 | dot 3 | 421 | csr 129, ctrl 228, datapath 64 |
| dot | 1 | dot 4 | 454 | csr 129, ctrl 197, datapath 128 |
| dot | 1 | dot 5 | 454 | csr 129, ctrl 197, datapath 128 |
| dot | 1 | dot 6 | 519 | csr 129, ctrl 198, datapath 192 |
| dot | 1 | HLS unopt | 328 | RTL 328: loop state (accumulator, counters) 128, data pipeline (operands, products) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 4, conditions 2 |
| dot | 1 | HLS opt | 394 | RTL 394: data pipeline (operands, products) 192, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 6, conditions 2 |
| dot | 4 | dot 2 | 678 | csr 129, ctrl 229, datapath 320 |
| dot | 4 | dot 3 | 421 | csr 129, ctrl 228, datapath 64 |
| dot | 4 | dot 4 | 646 | csr 129, ctrl 197, datapath 320 |
| dot | 4 | dot 5 | 648 | csr 129, ctrl 199, datapath 320 |
| dot | 4 | dot 6 | 905 | csr 129, ctrl 200, datapath 576 |
| dot | 4 | HLS unopt | 1039 | RTL 1039: data pipeline (operands, products) 838, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 6, conditions 1 |
| dot | 4 | HLS opt | 970 | RTL 970: data pipeline (operands, products) 768, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 6, conditions 2 |
| dot | 32 | dot 2 | 2470 | csr 129, ctrl 229, datapath 2112 |
| dot | 32 | dot 3 | 421 | csr 129, ctrl 228, datapath 64 |
| dot | 32 | dot 4 | 2438 | csr 129, ctrl 197, datapath 2112 |
| dot | 32 | dot 5 | 2443 | csr 129, ctrl 202, datapath 2112 |
| dot | 32 | dot 6 | 4492 | csr 129, ctrl 203, datapath 4160 |
| dot | 32 | HLS unopt | 4629 | RTL 4629: data pipeline (operands, products) 4428, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 6, conditions 1 |
| dot | 32 | HLS opt | 6732 | RTL 6732: data pipeline (operands, products) 6528, loop state (accumulator, counters) 128, pins (loop_count, len) 66, control (FSM, pipeline enables) 7, conditions 3 |

**HLS opt minus forge**: the total area gap and the sequential area gap; the e_run gap and the flop energy gap (e_flop = e_clk + e_reg + e_seq, X11, times the cycles). A share above 100 % means the rest of the design is smaller on HLS's side.

| tech | kernel | forge | W | Δ area µm² | Δ seq µm² | seq share of Δ % | Δ e_run nJ | Δ e_flop·C nJ | flop share of Δ % |
|---|---|---|---|---|---|---|---|---|---|
| nangate45 | vecadd | forge | 1 | -767 | -437 | 57 | -0.548 | 0.260 | -47 |
| nangate45 | vecadd | forge | 4 | 463 | 431 | 93 | 0.904 | 1.657 | 183 |
| nangate45 | vecadd | forge | 32 | 11,929 | 8,535 | 72 | 1.355 | 2.087 | 154 |
| nangate45 | vecmul | forge | 1 | -343 | -147 | 43 | 3.300 | 1.935 | 59 |
| nangate45 | vecmul | forge | 4 | 2,160 | 1,589 | 74 | 4.774 | 3.327 | 70 |
| nangate45 | vecmul | forge | 32 | 25,534 | 17,796 | 70 | 5.207 | 3.776 | 73 |
| nangate45 | vsum | forge | 1 | -1,082 | -707 | 65 | -1.340 | -2.150 | 160 |
| nangate45 | vsum | forge | 4 | 147 | 161 | 110 | 0.730 | 0.419 | 57 |
| nangate45 | vsum | forge | 32 | 9,216 | 6,537 | 71 | 1.105 | 0.942 | 85 |
| nangate45 | dot | dot 3 | 1 | -2,662 | -459 | 17 | 2.766 | 0.724 | 26 |
| nangate45 | dot | dot 3 | 4 | 1,067 | 2,145 | 201 | 5.517 | 3.974 | 72 |
| nangate45 | dot | dot 3 | 32 | 38,393 | 28,201 | 73 | 6.836 | 5.272 | 77 |
| nangate45 | dot | dot 5 | 1 | -990 | -635 | 64 | 3.618 | 1.260 | 35 |
| nangate45 | dot | dot 5 | 4 | 738 | 938 | 127 | 4.099 | 3.063 | 75 |
| nangate45 | dot | dot 5 | 32 | 23,715 | 17,444 | 74 | 4.420 | 3.534 | 80 |
| nangate15 | vecadd | forge | 1 | -160 | -79 | 50 | 0.000 | 0.194 |  |
| nangate15 | vecadd | forge | 4 | 183 | 166 | 91 | 0.397 | 0.571 | 144 |
| nangate15 | vecadd | forge | 32 | 3,388 | 2,456 | 72 | 0.520 | 0.687 | 132 |
| nangate15 | vecmul | forge | 1 | -56 | 3 | -5 | 0.749 | 0.908 | 121 |
| nangate15 | vecmul | forge | 4 | 601 | 493 | 82 | 1.150 | 1.291 | 112 |
| nangate15 | vecmul | forge | 32 | 6,727 | 5,073 | 75 | 1.272 | 1.414 | 111 |
| nangate15 | vsum | forge | 1 | -222 | -119 | 54 | -0.346 | -0.442 | 128 |
| nangate15 | vsum | forge | 4 | 110 | 127 | 115 | 0.302 | 0.226 | 75 |
| nangate15 | vsum | forge | 32 | 2,651 | 1,928 | 73 | 0.415 | 0.344 | 83 |
| nangate15 | dot | dot 3 | 1 | -700 | -35 | 5 | 0.633 | 0.726 | 115 |
| nangate15 | dot | dot 3 | 4 | 297 | 702 | 236 | 1.509 | 1.576 | 104 |
| nangate15 | dot | dot 3 | 32 | 10,303 | 8,065 | 78 | 1.907 | 1.955 | 103 |
| nangate15 | dot | dot 5 | 1 | -193 | -77 | 40 | 0.982 | 0.868 | 88 |
| nangate15 | dot | dot 5 | 4 | 223 | 412 | 184 | 0.950 | 1.248 | 131 |
| nangate15 | dot | dot 5 | 32 | 7,170 | 5,481 | 76 | 0.965 | 1.344 | 139 |

### Observations

- Forge dot 3 has 421 flops at every W (`dot/forge3_w1` to `dot/forge3_w32`); HLS dot opt goes from 394 to 6,732 (`dot/opt_w1` to `dot/opt_w32`). Forge vecadd and vecmul keep 196 at every W, all in csr and ctrl.
- Forge's datapath area is close to linear in W: R² ≥ 0.99997 over every design and technology, slope 267 to 8,158 µm² per lane on nangate45; HLS opt's total too (R² ≥ 0.9989).
- At W = 1 forge is larger than HLS opt on vecadd (2,068 against 1,301 µm², nangate45), where csr + ctrl (1,796 µm²) is larger than the adder; at W = 32 it is smaller (10,429 against 22,358 µm²).

### Explanations

- **The boundary differs.** Forge's ElementwiseLanes has no registers (the datapath flops of vecadd and vecmul are 0 at every W: forge's operand registers sit in snax_cluster's streamers, which SYN1 does not synthesize), while HLS opt registers data per lane inside its block: vecadd 64 bits per lane (`c` at W = 1); vecmul 128 bits per lane (`a`, `bb` at W = 1); vsum 51 bits per lane (`a` at W = 1); dot 206 bits per lane (`a`, `bb`, `s` at W = 1). So the per-lane sequential area is in HLS's number and outside forge's. Sure for the inventory (RTL names, DC counts); how large the streamers' registers are is not in SYN1's data.
- **Forge's fixed flops** are csr (129: three 32-bit CSRs, the kept answer and its flag) and ctrl (the 32-bit counters per unit plus a few flags), plus one 64-bit accumulator per sum and 64 W per MAC or link buffer. **HLS's fixed flops** are the pins (`loop_count`, `len`, 32 bits and a valid each), the loop's state (the accumulator and two 32-bit counters for dot and vsum) and the FSM.
- **The sequential area explains most of HLS opt's extra area at large W** (seq share of the gap above); at W = 1 forge's csr + ctrl outweighs it. Fairly sure: the shares are computed from DC's area split; the multiplexers that hold HLS's registers (DFF plus MUX2 for the enable) count as combinational area, so the register cost is somewhat larger than the sequential share alone.

### Questions

- The like-for-like boundary: forge's accelerator plus its share of the streamers against HLS's block. snax_cluster's streamer area per port at each W would put the two on one boundary; a synthesis of the streamers alone (or of the cluster with and without the accelerator) would give it.

## 4. Energy

Energy per element (e_run / 2048, pJ) per kernel and W; the combinational share of e_dyn; forge's datapath share of e_run. Figure `fig4_energy.png`: pJ per element against W.

**vecadd, nangate45**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp % |
|---|---|---|---|---|---|
| 1 | 1.259 (63 %) | 1.962 (22 %) | 2.153 (20 %) | 2.229 (37 %) | 35 |
| 2 | 19.552 (18 %) | 1.710 (25 %) | 1.810 (24 %) | 1.504 (53 %) | 51 |
| 4 | 23.655 (17 %) | 1.583 (27 %) | 1.684 (25 %) | 1.141 (69 %) | 68 |
| 8 | 32.586 (12 %) | 1.525 (27 %) | 1.573 (27 %) | 0.961 (82 %) | 81 |
| 16 | 53.236 (11 %) | 1.493 (28 %) | 1.513 (27 %) | 0.866 (90 %) | 89 |
| 32 | 89.440 (6 %) | 1.480 (28 %) | 1.488 (28 %) | 0.818 (95 %) | 94 |

**vecmul, nangate45**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp % |
|---|---|---|---|---|---|
| 1 | 12.862 (93 %) | 14.372 (84 %) | 14.564 (83 %) | 12.761 (89 %) | 89 |
| 2 | 37.107 (55 %) | 14.143 (85 %) | 14.241 (85 %) | 12.009 (94 %) | 94 |
| 4 | 38.200 (46 %) | 13.984 (86 %) | 14.083 (85 %) | 11.653 (97 %) | 97 |
| 8 | 45.584 (35 %) | 13.895 (86 %) | 13.940 (86 %) | 11.473 (98 %) | 98 |
| 16 | 65.641 (27 %) | 13.878 (86 %) | 13.897 (86 %) | 11.373 (99 %) | 99 |
| 32 | 101.524 (16 %) | 13.882 (86 %) | 13.886 (86 %) | 11.340 (100 %) | 100 |

**vsum, nangate45**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | forge | forge dp % |
|---|---|---|---|---|
| 1 | 5.370 (34 %) | 3.381 (35 %) | 4.035 (20 %) | 47 |
| 2 | 15.276 (29 %) | 2.207 (37 %) | 2.216 (27 %) | 51 |
| 4 | 13.825 (28 %) | 1.643 (38 %) | 1.286 (37 %) | 58 |
| 8 | 14.366 (24 %) | 1.174 (44 %) | 0.824 (50 %) | 67 |
| 16 | 18.449 (23 %) | 1.030 (45 %) | 0.588 (65 %) | 77 |
| 32 | 25.016 (14 %) | 1.011 (44 %) | 0.471 (78 %) | 85 |

**dot, nangate45**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 | dot 2 dp % | dot 3 dp % | dot 4 dp % | dot 5 dp % | dot 6 dp % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 20.283 (69 %) | 16.761 (76 %) | 16.114 (73 %) | 15.411 (76 %) | 14.989 (77 %) | 14.995 (77 %) | 15.464 (75 %) | 84 | 83 | 84 | 84 | 85 |
| 2 | 42.256 (53 %) | 15.632 (79 %) | 14.077 (82 %) | 13.393 (86 %) | 13.784 (85 %) | 13.733 (85 %) | 14.053 (82 %) | 91 | 90 | 91 | 91 | 91 |
| 4 | 39.673 (49 %) | 15.039 (81 %) | 13.016 (88 %) | 12.345 (92 %) | 13.165 (89 %) | 13.038 (89 %) | 13.344 (86 %) | 95 | 95 | 95 | 95 | 95 |
| 8 | 42.277 (42 %) | 14.913 (81 %) | 12.464 (91 %) | 11.796 (96 %) | 12.851 (92 %) | 12.618 (92 %) | 12.995 (89 %) | 97 | 97 | 98 | 98 | 98 |
| 16 | 54.068 (35 %) | 14.885 (81 %) | 12.196 (93 %) | 11.513 (98 %) | 12.714 (93 %) | 12.449 (93 %) | 12.894 (89 %) | 99 | 99 | 99 | 99 | 99 |
| 32 | 74.610 (22 %) | 14.724 (82 %) | 12.083 (94 %) | 11.386 (99 %) | 12.681 (94 %) | 12.566 (92 %) | 13.098 (88 %) | 99 | 99 | 99 | 99 | 99 |

**vecadd, nangate15**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp % |
|---|---|---|---|---|---|
| 1 | 0.344 (61 %) | 0.608 (21 %) | 0.658 (19 %) | 0.608 (37 %) | 33 |
| 2 | 7.875 (21 %) | 0.532 (23 %) | 0.557 (22 %) | 0.403 (52 %) | 49 |
| 4 | 9.695 (17 %) | 0.494 (24 %) | 0.520 (23 %) | 0.300 (68 %) | 66 |
| 8 | 14.428 (15 %) | 0.477 (25 %) | 0.489 (24 %) | 0.250 (81 %) | 79 |
| 16 | 23.326 (10 %) | 0.468 (25 %) | 0.473 (24 %) | 0.223 (89 %) | 89 |
| 32 | 40.744 (6 %) | 0.465 (25 %) | 0.466 (24 %) | 0.210 (94 %) | 94 |

**vecmul, nangate15**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | HLS dace | forge | forge dp % |
|---|---|---|---|---|---|
| 1 | 4.141 (93 %) | 4.567 (82 %) | 4.617 (81 %) | 4.202 (91 %) | 90 |
| 2 | 13.430 (51 %) | 4.492 (83 %) | 4.516 (83 %) | 3.994 (95 %) | 95 |
| 4 | 14.311 (41 %) | 4.445 (84 %) | 4.471 (83 %) | 3.884 (98 %) | 97 |
| 8 | 18.584 (32 %) | 4.417 (84 %) | 4.428 (84 %) | 3.825 (99 %) | 99 |
| 16 | 27.250 (22 %) | 4.412 (84 %) | 4.417 (84 %) | 3.810 (99 %) | 99 |
| 32 | 44.555 (14 %) | 4.409 (84 %) | 4.410 (84 %) | 3.787 (100 %) | 100 |

**vsum, nangate15**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | forge | forge dp % |
|---|---|---|---|---|
| 1 | 1.764 (36 %) | 1.060 (33 %) | 1.229 (25 %) | 52 |
| 2 | 5.583 (28 %) | 0.684 (33 %) | 0.647 (29 %) | 54 |
| 4 | 5.141 (25 %) | 0.510 (33 %) | 0.363 (37 %) | 59 |
| 8 | 5.919 (24 %) | 0.360 (38 %) | 0.222 (48 %) | 66 |
| 16 | 7.704 (19 %) | 0.319 (38 %) | 0.150 (62 %) | 75 |
| 32 | 11.442 (12 %) | 0.317 (38 %) | 0.114 (75 %) | 83 |

**dot, nangate15**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %

| W | HLS unopt | HLS opt | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 | dot 2 dp % | dot 3 dp % | dot 4 dp % | dot 5 dp % | dot 6 dp % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 6.761 (69 %) | 5.356 (74 %) | 5.309 (76 %) | 5.047 (79 %) | 4.878 (80 %) | 4.876 (80 %) | 5.000 (78 %) | 86 | 86 | 87 | 87 | 87 |
| 2 | 15.347 (49 %) | 4.992 (77 %) | 4.656 (84 %) | 4.395 (88 %) | 4.534 (86 %) | 4.530 (87 %) | 4.617 (84 %) | 92 | 92 | 93 | 93 | 93 |
| 4 | 14.729 (43 %) | 4.806 (79 %) | 4.329 (89 %) | 4.069 (94 %) | 4.355 (90 %) | 4.342 (90 %) | 4.420 (88 %) | 96 | 95 | 96 | 96 | 96 |
| 8 | 17.125 (36 %) | 4.775 (79 %) | 4.162 (91 %) | 3.900 (97 %) | 4.273 (92 %) | 4.235 (92 %) | 4.339 (89 %) | 98 | 98 | 98 | 98 | 98 |
| 16 | 22.565 (27 %) | 4.773 (78 %) | 4.096 (93 %) | 3.832 (98 %) | 4.255 (93 %) | 4.217 (93 %) | 4.345 (90 %) | 99 | 99 | 99 | 99 | 99 |
| 32 | 33.902 (18 %) | 4.713 (79 %) | 4.049 (94 %) | 3.782 (99 %) | 4.232 (94 %) | 4.242 (92 %) | 4.426 (88 %) | 99 | 99 | 99 | 99 | 99 |

### Observations

- nangate45, pJ per element at W = 32 over W = 1: vecadd: HLS unopt 71.04, HLS opt 0.75, HLS dace 0.69, forge 0.37; vecmul: HLS unopt 7.89, HLS opt 0.97, HLS dace 0.95, forge 0.89; vsum: HLS unopt 4.66, HLS opt 0.30, forge 0.12; dot: HLS unopt 3.68, HLS opt 0.88, dot 2 0.75, dot 3 0.74, dot 4 0.85, dot 5 0.84, dot 6 0.85.
- nangate15, pJ per element at W = 32 over W = 1: vecadd: HLS unopt 118.44, HLS opt 0.76, HLS dace 0.71, forge 0.35; vecmul: HLS unopt 10.76, HLS opt 0.97, HLS dace 0.96, forge 0.90; vsum: HLS unopt 6.49, HLS opt 0.30, forge 0.09; dot: HLS unopt 5.01, HLS opt 0.88, dot 2 0.76, dot 3 0.75, dot 4 0.87, dot 5 0.87, dot 6 0.89.
- nangate45, from W = 1 to 32: falls: dot 2, dot 3, dot 4, dot 5, dot 6, dot HLS opt, vecadd HLS dace, vecadd forge, vecadd HLS opt, vecmul forge, vsum forge, vsum HLS opt; rises: dot HLS unopt, vecadd HLS unopt, vecmul HLS unopt, vsum HLS unopt; stays within 5 %: vecmul HLS dace, vecmul HLS opt.
- nangate15, from W = 1 to 32: falls: dot 2, dot 3, dot 4, dot 5, dot 6, dot HLS opt, vecadd HLS dace, vecadd forge, vecadd HLS opt, vecmul forge, vsum forge, vsum HLS opt; rises: dot HLS unopt, vecadd HLS unopt, vecmul HLS unopt, vsum HLS unopt; stays within 5 %: vecmul HLS dace, vecmul HLS opt.

### Explanations

- **One shape on both sides.** With e_run = α C + β (section 2) and C ≈ N / W, pJ per element = α / W + β / N: it falls with W as far as the per-cycle part α N is of e_run at W = 1. That part, from the fits, on nangate45: forge vecadd 65 %, vecmul 12 %, vsum 91 %, dot 2 26 %, dot 3 27 %, dot 4 16 %, dot 5 18 %, dot 6 17 %; HLS dot opt 12 %, vecadd dace 31 %, vecadd opt 25 %, vecmul dace 5 %, vecmul opt 4 %, vsum opt 73 %. The larger it is, the more the series falls (compare the W = 32 / W = 1 ratios above). Fairly sure: the fits hold within the errors in section 2 (HLS vsum opt is the loosest).
- **Forge's per-cycle part is larger** because csr + ctrl's 32-bit registers are clocked every cycle; HLS's fixed state is smaller (its pins, two counters, the FSM) and its per-lane registers cost per task (51 to 206 bits per lane, each written once per beat: section 3), like forge's MAC lanes. vecmul's HLS opt barely falls because its multipliers' work dominates e_run; vsum's falls most because a 64-bit adder per lane is small next to the fixed state.
- **HLS unopt rises** because its window stays at a few cycles per element whatever W (it does the lanes one after another, section 1) while its registers grow with W: flops x cycles per task on nangate45 go vecadd 5.6M (W = 2, 4.00 cycles per element) to 40.5M (W = 32, 3.06), vecmul 5.6M (W = 2, 4.00 cycles per element) to 40.5M (W = 32, 3.06), vsum 3.8M (W = 2, 3.50 cycles per element) to 10.5M (W = 32, 2.09), dot 7.2M (W = 2, 4.50 cycles per element) to 29.3M (W = 32, 3.09). Fairly sure: the flops and cycles are measured; that the clocked registers dominate the rise is inferred from the comb share falling with W (the tables above).

### Questions

- The energy here is the accelerator's alone. The streamers' energy per beat (forge) and the AXI-stream interface's (HLS) are outside both; a cluster-level power run would show whether they change the picture at small W, where forge's beats are many.

## 5. dot's variants

dot 2 to 6 (dot 2: multiply lanes, link buffer, adder tree; dot 3: multiply lanes, adder tree; dot 4: MAC lanes, adder tree; dot 5: MAC lanes, serial sum; dot 6: MAC lanes, link buffer, serial sum) against HLS dot unopt and opt (dace is parked: RAM). A x C in mm²·cycles (area x cycles: lower is better), E x C in nJ·cycles. Figure `fig5_dot_variants.png`.

**nangate45** (rank 1 = lowest, among the seven at that W)

| W | case | cycles | area µm² | e_run nJ | A x C mm²·cyc | E x C nJ·cyc | rank area | rank e_run | rank AxC | rank ExC |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | HLS unopt | 6145 | 9,692 | 41.540 | 59.559 | 255,263 | 1 | 7 | 7 | 7 |
| 1 | HLS opt | 2051 | 10,139 | 34.327 | 20.795 | 70,405 | 2 | 6 | 1 | 6 |
| 1 | dot 2 | 2050 | 13,321 | 33.002 | 27.308 | 67,654 | 7 | 5 | 6 | 5 |
| 1 | dot 3 | 2049 | 12,801 | 31.561 | 26.230 | 64,668 | 6 | 3 | 5 | 3 |
| 1 | dot 4 | 2050 | 11,125 | 30.698 | 22.806 | 62,931 | 3 | 1 | 2 | 1 |
| 1 | dot 5 | 2050 | 11,129 | 30.709 | 22.815 | 62,953 | 4 | 2 | 3 | 2 |
| 1 | dot 6 | 2051 | 11,626 | 31.671 | 23.846 | 64,957 | 5 | 4 | 4 | 4 |
| 2 | HLS unopt | 9217 | 12,838 | 86.540 | 118.325 | 797,639 | 1 | 7 | 7 | 7 |
| 2 | HLS opt | 1027 | 18,560 | 32.014 | 19.061 | 32,878 | 2 | 6 | 1 | 6 |
| 2 | dot 2 | 1026 | 20,962 | 28.830 | 21.507 | 29,580 | 7 | 5 | 6 | 4 |
| 2 | dot 3 | 1025 | 19,978 | 27.428 | 20.478 | 28,114 | 5 | 1 | 4 | 1 |
| 2 | dot 4 | 1026 | 19,022 | 28.229 | 19.517 | 28,963 | 3 | 3 | 2 | 3 |
| 2 | dot 5 | 1027 | 19,216 | 28.126 | 19.734 | 28,885 | 4 | 2 | 3 | 2 |
| 2 | dot 6 | 1028 | 20,182 | 28.781 | 20.747 | 29,587 | 6 | 4 | 5 | 5 |
| 4 | HLS unopt | 7681 | 14,770 | 81.250 | 113.451 | 624,081 | 1 | 7 | 7 | 7 |
| 4 | HLS opt | 515 | 35,404 | 30.800 | 18.233 | 15,862 | 5 | 6 | 4 | 6 |
| 4 | dot 2 | 514 | 36,245 | 26.657 | 18.630 | 13,702 | 6 | 2 | 5 | 2 |
| 4 | dot 3 | 513 | 34,337 | 25.283 | 17.615 | 12,970 | 2 | 1 | 1 | 1 |
| 4 | dot 4 | 514 | 34,830 | 26.963 | 17.903 | 13,859 | 4 | 4 | 2 | 4 |
| 4 | dot 5 | 517 | 34,667 | 26.701 | 17.923 | 13,804 | 3 | 3 | 3 | 3 |
| 4 | dot 6 | 518 | 36,494 | 27.329 | 18.904 | 14,156 | 7 | 5 | 6 | 5 |
| 8 | HLS unopt | 6913 | 18,631 | 86.584 | 128.795 | 598,555 | 1 | 7 | 7 | 7 |
| 8 | HLS opt | 260 | 69,955 | 30.541 | 18.188 | 7,941 | 7 | 6 | 5 | 6 |
| 8 | dot 2 | 258 | 66,823 | 25.525 | 17.240 | 6,585 | 5 | 2 | 3 | 2 |
| 8 | dot 3 | 257 | 63,053 | 24.158 | 16.205 | 6,209 | 2 | 1 | 1 | 1 |
| 8 | dot 4 | 258 | 66,425 | 26.320 | 17.138 | 6,791 | 4 | 4 | 2 | 3 |
| 8 | dot 5 | 265 | 65,450 | 25.841 | 17.344 | 6,848 | 3 | 3 | 4 | 4 |
| 8 | dot 6 | 266 | 69,140 | 26.613 | 18.391 | 7,079 | 6 | 5 | 6 | 5 |
| 16 | HLS unopt | 6529 | 26,252 | 110.730 | 171.398 | 722,956 | 1 | 7 | 7 | 7 |
| 16 | HLS opt | 132 | 138,987 | 30.485 | 18.346 | 4,024 | 7 | 6 | 4 | 6 |
| 16 | dot 2 | 130 | 127,916 | 24.977 | 16.629 | 3,247 | 4 | 2 | 2 | 2 |
| 16 | dot 3 | 129 | 120,487 | 23.579 | 15.543 | 3,042 | 2 | 1 | 1 | 1 |
| 16 | dot 4 | 130 | 129,629 | 26.038 | 16.852 | 3,385 | 5 | 4 | 3 | 3 |
| 16 | dot 5 | 145 | 126,986 | 25.496 | 18.413 | 3,697 | 3 | 3 | 5 | 4 |
| 16 | dot 6 | 146 | 134,390 | 26.407 | 19.621 | 3,855 | 6 | 5 | 6 | 5 |
| 32 | HLS unopt | 6337 | 41,157 | 152.802 | 260.813 | 968,306 | 1 | 7 | 7 | 7 |
| 32 | HLS opt | 68 | 273,743 | 30.154 | 18.615 | 2,050 | 7 | 6 | 4 | 4 |
| 32 | dot 2 | 66 | 250,196 | 24.746 | 16.513 | 1,633 | 4 | 2 | 2 | 2 |
| 32 | dot 3 | 65 | 235,350 | 23.318 | 15.298 | 1,516 | 2 | 1 | 1 | 1 |
| 32 | dot 4 | 66 | 256,024 | 25.970 | 16.898 | 1,714 | 5 | 4 | 3 | 3 |
| 32 | dot 5 | 97 | 250,028 | 25.734 | 24.253 | 2,496 | 3 | 3 | 5 | 5 |
| 32 | dot 6 | 98 | 264,824 | 26.825 | 25.953 | 2,629 | 6 | 5 | 6 | 6 |

**nangate15** (rank 1 = lowest, among the seven at that W)

| W | case | cycles | area µm² | e_run nJ | A x C mm²·cyc | E x C nJ·cyc | rank area | rank e_run | rank AxC | rank ExC |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | HLS unopt | 6145 | 3,003 | 13.847 | 18.454 | 85,090 | 1 | 7 | 7 | 7 |
| 1 | HLS opt | 2051 | 3,122 | 10.968 | 6.403 | 22,495 | 2 | 6 | 1 | 6 |
| 1 | dot 2 | 2050 | 3,932 | 10.873 | 8.060 | 22,290 | 7 | 5 | 6 | 5 |
| 1 | dot 3 | 2049 | 3,822 | 10.335 | 7.831 | 21,176 | 6 | 4 | 5 | 4 |
| 1 | dot 4 | 2050 | 3,315 | 9.989 | 6.796 | 20,477 | 4 | 2 | 3 | 2 |
| 1 | dot 5 | 2050 | 3,315 | 9.986 | 6.795 | 20,471 | 3 | 1 | 2 | 1 |
| 1 | dot 6 | 2051 | 3,430 | 10.240 | 7.036 | 21,002 | 5 | 3 | 4 | 3 |
| 2 | HLS unopt | 9217 | 3,925 | 31.431 | 36.174 | 289,700 | 1 | 7 | 7 | 7 |
| 2 | HLS opt | 1027 | 5,741 | 10.223 | 5.896 | 10,499 | 2 | 6 | 1 | 6 |
| 2 | dot 2 | 1026 | 6,333 | 9.536 | 6.498 | 9,784 | 7 | 5 | 6 | 5 |
| 2 | dot 3 | 1025 | 6,110 | 9.001 | 6.262 | 9,226 | 6 | 1 | 4 | 1 |
| 2 | dot 4 | 1026 | 5,814 | 9.285 | 5.965 | 9,526 | 3 | 3 | 2 | 2 |
| 2 | dot 5 | 1027 | 5,863 | 9.278 | 6.021 | 9,529 | 4 | 2 | 3 | 3 |
| 2 | dot 6 | 1028 | 6,093 | 9.456 | 6.264 | 9,721 | 5 | 4 | 5 | 4 |
| 4 | HLS unopt | 7681 | 4,438 | 30.165 | 34.092 | 231,697 | 1 | 7 | 7 | 7 |
| 4 | HLS opt | 515 | 10,980 | 9.843 | 5.655 | 5,069 | 5 | 6 | 4 | 6 |
| 4 | dot 2 | 514 | 11,135 | 8.867 | 5.723 | 4,558 | 6 | 2 | 5 | 2 |
| 4 | dot 3 | 513 | 10,683 | 8.334 | 5.480 | 4,275 | 2 | 1 | 1 | 1 |
| 4 | dot 4 | 514 | 10,808 | 8.918 | 5.556 | 4,584 | 4 | 4 | 2 | 3 |
| 4 | dot 5 | 517 | 10,757 | 8.893 | 5.561 | 4,598 | 3 | 3 | 3 | 4 |
| 4 | dot 6 | 518 | 11,216 | 9.052 | 5.810 | 4,689 | 7 | 5 | 6 | 5 |
| 8 | HLS unopt | 6913 | 5,524 | 35.073 | 38.185 | 242,460 | 1 | 7 | 7 | 7 |
| 8 | HLS opt | 260 | 21,677 | 9.778 | 5.636 | 2,542 | 7 | 6 | 5 | 6 |
| 8 | dot 2 | 258 | 20,738 | 8.524 | 5.350 | 2,199 | 4 | 2 | 2 | 2 |
| 8 | dot 3 | 257 | 19,829 | 7.988 | 5.096 | 2,053 | 2 | 1 | 1 | 1 |
| 8 | dot 4 | 258 | 20,843 | 8.751 | 5.377 | 2,258 | 5 | 4 | 3 | 3 |
| 8 | dot 5 | 265 | 20,554 | 8.673 | 5.447 | 2,298 | 3 | 3 | 4 | 4 |
| 8 | dot 6 | 266 | 21,474 | 8.886 | 5.712 | 2,364 | 6 | 5 | 6 | 5 |
| 16 | HLS unopt | 6529 | 7,604 | 46.213 | 49.644 | 301,725 | 1 | 7 | 7 | 7 |
| 16 | HLS opt | 132 | 43,092 | 9.775 | 5.688 | 1,290 | 7 | 6 | 4 | 5 |
| 16 | dot 2 | 130 | 39,944 | 8.389 | 5.193 | 1,091 | 4 | 2 | 2 | 2 |
| 16 | dot 3 | 129 | 38,123 | 7.848 | 4.918 | 1,012 | 2 | 1 | 1 | 1 |
| 16 | dot 4 | 130 | 40,172 | 8.714 | 5.222 | 1,133 | 5 | 4 | 3 | 3 |
| 16 | dot 5 | 145 | 39,421 | 8.637 | 5.716 | 1,252 | 3 | 3 | 5 | 4 |
| 16 | dot 6 | 146 | 41,252 | 8.899 | 6.023 | 1,299 | 6 | 5 | 6 | 6 |
| 32 | HLS unopt | 6337 | 11,868 | 69.432 | 75.209 | 439,991 | 1 | 7 | 7 | 7 |
| 32 | HLS opt | 68 | 85,011 | 9.653 | 5.781 | 656 | 7 | 6 | 4 | 4 |
| 32 | dot 2 | 66 | 78,354 | 8.293 | 5.171 | 547 | 4 | 2 | 2 | 2 |
| 32 | dot 3 | 65 | 74,708 | 7.746 | 4.856 | 503 | 2 | 1 | 1 | 1 |
| 32 | dot 4 | 66 | 79,527 | 8.668 | 5.249 | 572 | 5 | 3 | 3 | 3 |
| 32 | dot 5 | 97 | 77,840 | 8.688 | 7.551 | 843 | 3 | 4 | 5 | 5 |
| 32 | dot 6 | 98 | 81,492 | 9.064 | 7.986 | 888 | 6 | 5 | 6 | 6 |

### Observations

- nangate45, lowest area: W 1: HLS unopt, W 2: HLS unopt, W 4: HLS unopt, W 8: HLS unopt, W 16: HLS unopt, W 32: HLS unopt.
- nangate45, lowest e_run: W 1: dot 4, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate45, lowest AxC: W 1: HLS opt, W 2: HLS opt, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate45, lowest ExC: W 1: dot 4, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate45, lowest cycles: W 1: dot 3, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate15, lowest area: W 1: HLS unopt, W 2: HLS unopt, W 4: HLS unopt, W 8: HLS unopt, W 16: HLS unopt, W 32: HLS unopt.
- nangate15, lowest e_run: W 1: dot 5, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate15, lowest AxC: W 1: HLS opt, W 2: HLS opt, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate15, lowest ExC: W 1: dot 5, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate15, lowest cycles: W 1: dot 3, W 2: dot 3, W 4: dot 3, W 8: dot 3, W 16: dot 3, W 32: dot 3.
- nangate45: variants below both HLS cases at every W: area: none; e_run: dot 2, dot 3, dot 4, dot 5, dot 6; AxC: none; ExC: dot 2, dot 3, dot 4; cycles: dot 2, dot 3, dot 4.
- nangate15: variants below both HLS cases at every W: area: none; e_run: dot 2, dot 3, dot 4, dot 5, dot 6; AxC: none; ExC: dot 2, dot 3, dot 4; cycles: dot 2, dot 3, dot 4.
- nangate45, W = 1: dot 5 against dot 4 area +0.04 %, e_run +0.04 %, cycles 2050 against 2050; dot 6 against dot 4 area +4.51 %, e_run +3.17 % (`dot/forge4_w1`, `dot/forge5_w1`, `dot/forge6_w1`).
- nangate45, dot 2 minus dot 3 (the link buffer): W 1: 520 µm² (465 in the buffer), +4.6 % e_run; W 2: 984 µm² (943 in the buffer), +5.1 % e_run; W 4: 1,908 µm² (1,866 in the buffer), +5.4 % e_run; W 8: 3,770 µm² (3,692 in the buffer), +5.7 % e_run; W 16: 7,429 µm² (7,382 in the buffer), +5.9 % e_run; W 32: 14,846 µm² (14,772 in the buffer), +6.1 % e_run.
- nangate15, W = 1: dot 5 against dot 4 area -0.02 %, e_run -0.03 %, cycles 2050 against 2050; dot 6 against dot 4 area +3.47 %, e_run +2.51 % (`dot/forge4_w1`, `dot/forge5_w1`, `dot/forge6_w1`).
- nangate15, dot 2 minus dot 3 (the link buffer): W 1: 110 µm² (114 in the buffer), +5.2 % e_run; W 2: 224 µm² (228 in the buffer), +5.9 % e_run; W 4: 452 µm² (456 in the buffer), +6.4 % e_run; W 8: 909 µm² (913 in the buffer), +6.7 % e_run; W 16: 1,821 µm² (1,825 in the buffer), +6.9 % e_run; W 32: 3,647 µm² (3,650 in the buffer), +7.1 % e_run.
- nangate45, dot 5 minus dot 4 per W: area + / + / − / − / − / −; e_run + / − / − / − / − / −; AxC + / + / + / + / + / +; ExC + / − / − / + / + / + (signs at W = 1 … 32).
- nangate15, dot 5 minus dot 4 per W: area − / + / − / − / − / −; e_run − / − / − / − / − / +; AxC − / + / + / + / + / +; ExC − / + / + / + / + / + (signs at W = 1 … 32).

### Explanations

- **dot 5 at W = 1 does dot 4's work**: at one lane a serial sum and a tree both add one value per beat (snax-forge's design note `design.serial_one_lane`), and the two agree within the percentages above on both technologies. dot 6 is larger by its link buffer (462 µm² on nangate45, 114 µm² on nangate15), which at J = 1 saves no cycle. Sure: C§17's forms give the same cycles, the blocks are the same at lanes 1, and the buffer's area is its module row.
- **nangate45: dot 5 (serial sum) is smaller than dot 4 (tree) at W = 4, 8, 16, 32.** At those W its W-cycle tail costs more than the tree's area saves on A x C at W = 4, 8, 16, 32, on E x C at W = 8, 16, 32, on e_run at W = none. Fairly sure for the mechanism (C5's W cycles against a tree of W − 1 adders, the module areas); where the two are within a fraction of a percent (W = 1, 2) the sign is noise of synthesis (PITFALLS DC3).
- **nangate15: dot 5 (serial sum) is smaller than dot 4 (tree) at W = 1, 4, 8, 16, 32.** At those W its W-cycle tail costs more than the tree's area saves on A x C at W = 4, 8, 16, 32, on E x C at W = 4, 8, 16, 32, on e_run at W = 32. Fairly sure for the mechanism (C5's W cycles against a tree of W − 1 adders, the module areas); where the two are within a fraction of a percent (W = 1, 2) the sign is noise of synthesis (PITFALLS DC3).
- **dot 2's buffer** adds W x 64 flops (a LinkBuffer of depth 1) and their per-cycle energy, with no cycle saved at J = 1 (C2 = T + 2 against C3 = T + 1). Sure: the module area and the cycle form.

### Questions

- The variants were measured at one job (J = 1). C§17's forms differ at J > 1 (dot 5: J(T + W − 1) + 2; dot 6 overlaps jobs): a run with several jobs (a matvec, row 16 x 512) would show whether dot 6's buffer pays off where dot 5's tail repeats per job.

## 6. Technologies

nangate45 over nangate15 per point, for area and e_run. Figure `fig6_tech_ratio.png`: the ratios against the sequential share of the nangate45 area.

| side | points | area ratio mean | area ratio range | e_run ratio mean | e_run ratio range |
|---|---|---|---|---|---|
| hls | 61 | 3.40 | 3.15–3.59 | 2.95 | 2.19–3.66 |
| forge | 48 | 3.37 | 3.13–3.91 | 3.19 | 2.95–4.12 |

### Observations

- The area ratio follows the sequential share: ratio = 0.73 x seq share + 3.19 (R² 0.54, 109 points). Lowest: `vecmul/forge_w32` 3.13, `vecmul/forge_w16` 3.13, `vecmul/forge_w8` 3.15; highest: `vecadd/forge_w1` 3.91, `vecadd/forge_w2` 3.87, `vecadd/forge_w4` 3.82.
- dot's lowest-metric variant is the same on both technologies in 22 of 24 (W, metric) cells of section 5.

### Explanations

- **The flops shrink more than the logic, and forge's most.** On nangate45 HLS's flops average 4.522 µm² (the plain DFF, synchronous reset in logic) and forge's 5.322 µm² (with an asynchronous reset); on nangate15 both are 1.27795 µm², since every flop there has an asynchronous reset or set (PITFALLS LIB1). So a flop shrinks 3.54x (HLS) or 4.16x (forge) against about 3.19x for the logic (the fit's intercept at no flops). Forge's flop-heavy points (small W, csr + ctrl) have the highest ratios. Fairly sure: the flop areas are DC's sequential area over its flop count, the logic's ratio is the fit's.
- **Consequence:** relative to HLS, forge pays about 18 % more per flop on nangate45 and the same on nangate15, so forge's control overhead is relatively smaller on nangate15 (section 2's thresholds).

### Questions

- Does a conclusion of section 5 or 8 depend on the library? Where the winners differ between the technologies (count above) it is at W = 1, where forge's flops weigh most; a library with a plain flop on both nodes (or nangate45 with only reset flops) would tell whether it is the flop cell.

## 7. Odd points

Steps in W against the series' own direction (pJ per element, more than 0.5 %):

| tech | series | step | pJ per element |
|---|---|---|---|
| nangate45 | vsum HLS unopt | W 2 → 4 | 15.276 → 13.825 |
| nangate45 | dot HLS unopt | W 2 → 4 | 42.256 → 39.673 |
| nangate45 | dot 5 | W 16 → 32 | 12.449 → 12.566 |
| nangate45 | dot 6 | W 16 → 32 | 12.894 → 13.098 |
| nangate15 | vsum HLS unopt | W 2 → 4 | 5.583 → 5.141 |
| nangate15 | dot HLS unopt | W 2 → 4 | 15.347 → 14.729 |
| nangate15 | dot 5 | W 16 → 32 | 4.217 → 4.242 |
| nangate15 | dot 6 | W 16 → 32 | 4.345 → 4.426 |

- fmax (observation only: DC's lower bound at 10 ns, X2, not analysed in SYN1): nangate45 hls 176–213 MHz; nangate45 forge 141–326 MHz; nangate15 hls 1177–1451 MHz; nangate15 forge 1045–1574 MHz.
- HLS vecadd unopt at W = 1 (`vecadd/unopt_w1`) has 67 flops and 1.259 pJ per element; the lowest pJ per element of the vecadd points at W = 1 on nangate45 is HLS unopt's. unopt at W = 1 registers no data (section 3's inventory: pins and loop state only) and is pipelined at one beat per cycle (a = 1).

### Explanations

- dot 5 and dot 6 from W = 16 to 32: the serial tail of W cycles (section 1, 5). Sure.
- HLS unopt's dip from W = 2 to 4 (vsum, dot): its cycles per element, a / W, fall there (vsum 3.50 to 2.75, dot 4.50 to 3.75) faster than its registers grow; from W = 4 on the registers win (section 4). Its jump from W = 1 to 2 is a / W jumping (vecadd 1.00 to 4.00, vecmul 2.00 to 4.00, vsum 2.00 to 3.50, dot 3.00 to 4.50). Sure: a is cosim's line.

## 8. Metrics

Candidate metrics side by side, per kernel and W: the lowest-energy-per-element, lowest A x C, lowest E x C and highest throughput per area (elements per cycle per mm², N / C / A) case, with forge's value next to the best HLS case's. Nothing is picked here.

**nangate45**: the best case per metric, and (best forge / best HLS) as a ratio of their values

| kernel | W | pJ/elem | A x C | E x C | elem/cyc/mm² |
|---|---|---|---|---|---|
| vecadd | 1 | HLS unopt (forge 1.77x HLS unopt) | HLS unopt (forge 2.40x HLS unopt) | HLS unopt (forge 1.77x HLS unopt) | HLS unopt (forge 0.42x HLS unopt) |
| vecadd | 2 | forge (forge 0.88x HLS opt) | HLS opt (forge 1.18x HLS opt) | forge (forge 0.88x HLS opt) | HLS opt (forge 0.85x HLS opt) |
| vecadd | 4 | forge (forge 0.72x HLS opt) | forge (forge 0.86x HLS opt) | forge (forge 0.72x HLS opt) | forge (forge 1.17x HLS opt) |
| vecadd | 8 | forge (forge 0.63x HLS opt) | forge (forge 0.65x HLS opt) | forge (forge 0.63x HLS opt) | forge (forge 1.54x HLS opt) |
| vecadd | 16 | forge (forge 0.58x HLS opt) | forge (forge 0.52x HLS opt) | forge (forge 0.57x HLS opt) | forge (forge 1.91x HLS opt) |
| vecadd | 32 | forge (forge 0.55x HLS opt) | forge (forge 0.45x HLS opt) | forge (forge 0.54x HLS opt) | forge (forge 2.21x HLS opt) |
| vecmul | 1 | forge (forge 0.99x HLS unopt) | HLS opt (forge 1.04x HLS opt) | forge (forge 0.89x HLS opt) | HLS opt (forge 0.96x HLS opt) |
| vecmul | 2 | forge (forge 0.85x HLS opt) | forge (forge 0.97x HLS opt) | forge (forge 0.85x HLS opt) | forge (forge 1.03x HLS opt) |
| vecmul | 4 | forge (forge 0.83x HLS opt) | forge (forge 0.93x HLS opt) | forge (forge 0.83x HLS opt) | forge (forge 1.08x HLS opt) |
| vecmul | 8 | forge (forge 0.83x HLS opt) | forge (forge 0.91x HLS opt) | forge (forge 0.82x HLS opt) | forge (forge 1.10x HLS opt) |
| vecmul | 16 | forge (forge 0.82x HLS opt) | forge (forge 0.89x HLS opt) | forge (forge 0.81x HLS opt) | forge (forge 1.13x HLS opt) |
| vecmul | 32 | forge (forge 0.82x HLS opt) | forge (forge 0.87x HLS opt) | forge (forge 0.79x HLS opt) | forge (forge 1.15x HLS opt) |
| vsum | 1 | HLS dace (forge 1.31x HLS dace) | HLS dace (forge 1.80x HLS dace) | HLS dace (forge 1.31x HLS dace) | HLS dace (forge 0.56x HLS dace) |
| vsum | 2 | HLS opt (forge 1.00x HLS opt) | HLS opt (forge 1.22x HLS opt) | HLS opt (forge 1.00x HLS opt) | HLS opt (forge 0.82x HLS opt) |
| vsum | 4 | forge (forge 0.78x HLS opt) | forge (forge 0.96x HLS opt) | forge (forge 0.78x HLS opt) | forge (forge 1.04x HLS opt) |
| vsum | 8 | forge (forge 0.70x HLS opt) | forge (forge 0.84x HLS opt) | forge (forge 0.70x HLS opt) | forge (forge 1.19x HLS opt) |
| vsum | 16 | forge (forge 0.57x HLS opt) | forge (forge 0.67x HLS opt) | forge (forge 0.56x HLS opt) | forge (forge 1.48x HLS opt) |
| vsum | 32 | forge (forge 0.47x HLS opt) | forge (forge 0.54x HLS opt) | forge (forge 0.45x HLS opt) | forge (forge 1.84x HLS opt) |
| dot | 1 | dot 4 (dot 4 0.89x HLS opt) | HLS opt (dot 4 1.10x HLS opt) | dot 4 (dot 4 0.89x HLS opt) | HLS opt (dot 4 0.91x HLS opt) |
| dot | 2 | dot 3 (dot 3 0.86x HLS opt) | HLS opt (dot 4 1.02x HLS opt) | dot 3 (dot 3 0.86x HLS opt) | HLS opt (dot 4 0.98x HLS opt) |
| dot | 4 | dot 3 (dot 3 0.82x HLS opt) | dot 3 (dot 3 0.97x HLS opt) | dot 3 (dot 3 0.82x HLS opt) | dot 3 (dot 3 1.04x HLS opt) |
| dot | 8 | dot 3 (dot 3 0.79x HLS opt) | dot 3 (dot 3 0.89x HLS opt) | dot 3 (dot 3 0.78x HLS opt) | dot 3 (dot 3 1.12x HLS opt) |
| dot | 16 | dot 3 (dot 3 0.77x HLS opt) | dot 3 (dot 3 0.85x HLS opt) | dot 3 (dot 3 0.76x HLS opt) | dot 3 (dot 3 1.18x HLS opt) |
| dot | 32 | dot 3 (dot 3 0.77x HLS opt) | dot 3 (dot 3 0.82x HLS opt) | dot 3 (dot 3 0.74x HLS opt) | dot 3 (dot 3 1.22x HLS opt) |

**nangate15**: the best case per metric, and (best forge / best HLS) as a ratio of their values

| kernel | W | pJ/elem | A x C | E x C | elem/cyc/mm² |
|---|---|---|---|---|---|
| vecadd | 1 | HLS unopt (forge 1.77x HLS unopt) | HLS unopt (forge 2.15x HLS unopt) | HLS unopt (forge 1.77x HLS unopt) | HLS unopt (forge 0.47x HLS unopt) |
| vecadd | 2 | forge (forge 0.76x HLS opt) | HLS opt (forge 1.08x HLS opt) | forge (forge 0.76x HLS opt) | HLS opt (forge 0.93x HLS opt) |
| vecadd | 4 | forge (forge 0.61x HLS opt) | forge (forge 0.80x HLS opt) | forge (forge 0.61x HLS opt) | forge (forge 1.25x HLS opt) |
| vecadd | 8 | forge (forge 0.52x HLS opt) | forge (forge 0.62x HLS opt) | forge (forge 0.52x HLS opt) | forge (forge 1.62x HLS opt) |
| vecadd | 16 | forge (forge 0.48x HLS opt) | forge (forge 0.51x HLS opt) | forge (forge 0.47x HLS opt) | forge (forge 1.97x HLS opt) |
| vecadd | 32 | forge (forge 0.45x HLS opt) | forge (forge 0.44x HLS opt) | forge (forge 0.44x HLS opt) | forge (forge 2.26x HLS opt) |
| vecmul | 1 | HLS unopt (forge 1.01x HLS unopt) | HLS opt (forge 1.02x HLS opt) | forge (forge 0.92x HLS opt) | HLS opt (forge 0.98x HLS opt) |
| vecmul | 2 | forge (forge 0.89x HLS opt) | forge (forge 0.97x HLS opt) | forge (forge 0.89x HLS opt) | forge (forge 1.04x HLS opt) |
| vecmul | 4 | forge (forge 0.87x HLS opt) | forge (forge 0.94x HLS opt) | forge (forge 0.87x HLS opt) | forge (forge 1.07x HLS opt) |
| vecmul | 8 | forge (forge 0.87x HLS opt) | forge (forge 0.92x HLS opt) | forge (forge 0.86x HLS opt) | forge (forge 1.09x HLS opt) |
| vecmul | 16 | forge (forge 0.86x HLS opt) | forge (forge 0.90x HLS opt) | forge (forge 0.85x HLS opt) | forge (forge 1.11x HLS opt) |
| vecmul | 32 | forge (forge 0.86x HLS opt) | forge (forge 0.89x HLS opt) | forge (forge 0.83x HLS opt) | forge (forge 1.13x HLS opt) |
| vsum | 1 | HLS dace (forge 1.29x HLS dace) | HLS dace (forge 1.69x HLS dace) | HLS dace (forge 1.28x HLS dace) | HLS dace (forge 0.59x HLS dace) |
| vsum | 2 | forge (forge 0.95x HLS opt) | HLS opt (forge 1.14x HLS opt) | forge (forge 0.95x HLS opt) | HLS opt (forge 0.88x HLS opt) |
| vsum | 4 | forge (forge 0.71x HLS opt) | forge (forge 0.91x HLS opt) | forge (forge 0.71x HLS opt) | forge (forge 1.10x HLS opt) |
| vsum | 8 | forge (forge 0.62x HLS opt) | forge (forge 0.80x HLS opt) | forge (forge 0.61x HLS opt) | forge (forge 1.24x HLS opt) |
| vsum | 16 | forge (forge 0.47x HLS opt) | forge (forge 0.65x HLS opt) | forge (forge 0.46x HLS opt) | forge (forge 1.54x HLS opt) |
| vsum | 32 | forge (forge 0.36x HLS opt) | forge (forge 0.53x HLS opt) | forge (forge 0.35x HLS opt) | forge (forge 1.88x HLS opt) |
| dot | 1 | dot 5 (dot 5 0.91x HLS opt) | HLS opt (dot 5 1.06x HLS opt) | dot 5 (dot 5 0.91x HLS opt) | HLS opt (dot 5 0.94x HLS opt) |
| dot | 2 | dot 3 (dot 3 0.88x HLS opt) | HLS opt (dot 4 1.01x HLS opt) | dot 3 (dot 3 0.88x HLS opt) | HLS opt (dot 4 0.99x HLS opt) |
| dot | 4 | dot 3 (dot 3 0.85x HLS opt) | dot 3 (dot 3 0.97x HLS opt) | dot 3 (dot 3 0.84x HLS opt) | dot 3 (dot 3 1.03x HLS opt) |
| dot | 8 | dot 3 (dot 3 0.82x HLS opt) | dot 3 (dot 3 0.90x HLS opt) | dot 3 (dot 3 0.81x HLS opt) | dot 3 (dot 3 1.11x HLS opt) |
| dot | 16 | dot 3 (dot 3 0.80x HLS opt) | dot 3 (dot 3 0.86x HLS opt) | dot 3 (dot 3 0.78x HLS opt) | dot 3 (dot 3 1.16x HLS opt) |
| dot | 32 | dot 3 (dot 3 0.80x HLS opt) | dot 3 (dot 3 0.84x HLS opt) | dot 3 (dot 3 0.77x HLS opt) | dot 3 (dot 3 1.19x HLS opt) |

### Observations

- The metrics disagree on which side is best in 9 of 48 (tech, kernel, W) cells: nangate45 vecadd W 2 (f/h/f/h); nangate45 vecmul W 1 (f/h/f/h); nangate45 dot W 1 (f/h/f/h); nangate45 dot W 2 (f/h/f/h); nangate15 vecadd W 2 (f/h/f/h); nangate15 vecmul W 1 (h/h/f/h); nangate15 vsum W 2 (f/h/f/h); nangate15 dot W 1 (f/h/f/h); nangate15 dot W 2 (f/h/f/h) (order: pJ/elem, A x C, E x C, throughput per area; h = HLS, f = forge).
- The disagreements by W: W = 1: 4, W = 2: 5. A x C and throughput per area always agree (one is the other's inverse times N).

### What each rewards

- **Energy per element** rewards whatever spends least per result: it ignores area and time, so a slow, small design (HLS unopt at W = 1) can win it.
- **A x C** (area x cycles, the inverse of throughput per area) rewards finishing the task fast for the silicon spent: it favours wide designs whose area grows slower than their cycles fall, and penalizes a fixed overhead (csr + ctrl) at small W and a cycle tail (dot 5, 6) at large W.
- **E x C** (energy-delay) rewards energy and speed together; between two designs of similar energy it follows the cycles, so it separates designs by their overhead cycles (dot 5, 6's tail, HLS unopt).
- **Throughput per area** is A x C's inverse up to N: it ranks the same, and reads as a rate (elements per cycle per mm²).

## Open questions

- Cycles: is the accelerator window (COUNTER) the right count for the comparison, or the cluster-level one with streamers and CSR writes? Needs snax_cluster RTL runs at n2048 (section 1).
- Control: how much would narrower counters (12 bits at n2048, today 32) save in ctrl's area and per-cycle energy? Needs a counter-width parameter and a resynthesis (section 2).
- Control: does csr + ctrl grow per group? Needs a two-group point such as dot 1 (section 2).
- Boundary: forge's datapath registers sit in the streamers, HLS's in the block. What do the streamers cost per port and W? Needs a synthesis of snax_cluster's streamers (section 3).
- Energy: what do the streamers add per beat? A cluster-level power run (snax_cluster) would tell whether forge's lead at large W or its cost at W = 1 changes (section 4).
- dot: at J > 1 dot 5's tail repeats per job and dot 6 overlaps it (C§17). Does dot 6's buffer pay off for matvec-like work? Needs SYN1-style runs of a J > 1 task (section 5).
- fmax: on nangate45 forge's dot variants report 141–176 MHz against HLS dot's 176–179 MHz; it is DC's lower bound at 10 ns (X2), so a synthesis at a tighter clock would be needed to compare speed, and SYN1 does not.

## Candidate metrics or figures for the paper

- Energy per element against W, one panel per kernel, both sides (fig4): the simplest picture; it rewards small slow designs and hides area.
- A x C (or throughput per area) against W for dot's variants and HLS (fig5): the area-time trade-off; it rewards width and punishes fixed overhead at W = 1 and dot 5's tail at W = 32.
- csr + ctrl share of area and e_run against W (fig2): answers the overhead question directly; it depends on what the boundary excludes (the streamers).
- The two-term fit e_run = α C + β per design (fig7): the HWCOST shape; it needs the per-cycle term to include the datapath's clocked registers.

## Figures

- `fig1_cycles_overhead.png`: cycles − N / W against W, per kernel and case (section 1).
- `fig2_control_share.png`: csr + ctrl as a share of area and e_run against W, per forge design, both technologies (section 2).
- `fig3_area.png`: total area against W, per kernel and case, both technologies (section 3).
- `fig4_energy.png`: pJ per element against W, per kernel and case; top row nangate45, bottom row nangate15 (section 4).
- `fig5_dot_variants.png`: A x C and E x C against W for dot 2–6 and HLS dot unopt and opt (section 5).
- `fig6_tech_ratio.png`: nangate45 / nangate15 ratios of area and e_run against the sequential share (section 6).
- `fig7_two_term_fit.png`: forge's e_run against the cycles over W, with the fit e_run = α C + β (section 2).
