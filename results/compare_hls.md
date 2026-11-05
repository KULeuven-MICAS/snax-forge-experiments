# The HLS cases side by side: Vitis opt and dace, Bambu, XLS

Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs (X45, X46); the text outside the `gen` markers is written by hand. Forge is left out until its accelerator parts are in.

## 1. Setup

<!-- gen:setup -->
| Case | Tool version | RTL measured at | Latency window |
|---|---|---|---|
| Vitis opt | v2023.2.2 | 4ef8bc8 | ap_start to ap_done (X12) |
| Vitis dace | v2023.2.2 | 4ef8bc8 | ap_start to ap_done (X12) |
| Bambu | PandA 2026.11 rev cda4db2e | 542fa32 | start_port to done_port (X44) |
| XLS | v0.0.0-10782-g5ddc35c4e | 46fa843, 9ae29ea, faf5a3d | cfg transfer to last output, last edge included (X44) |

Main view: nangate45, int64, every point synthesized at a 10 ns clock and scheduled at a 10 ns HLS clock, W = 1 to 16 lanes per stream. Sizes: tier done at n2048 (2048 elements per input stream, X24); untiered at each kernel's larger task size: matadd m16_n32, relu n512, axpy n512, rowsum m8_n64. Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition.
<!-- /gen -->

## 2. Across all kernels

All numbers below are nangate45, int64, at the sizes of the tables (tier done n2048; untiered the larger task size). Flops are DC's `seq_cells`, traced to each tool's RTL in R6 and R7.

- **Registers per lane decide the gaps wherever the arithmetic is cheap.** Flops added per lane (the slope of the flop count over W): XLS 0; Vitis opt 64 per output stream, since it registers the output beat, and 0 for the reductions; Bambu 64 per stream, inputs and outputs alike (vecadd, vecmul and axpy 192; relu 128; dot about 141; vsum about 68).
- **Bambu's registered beats are its most costly trait.** In vecadd they are 53 % of its area and 60 % of its energy, and they are why its area grows 1622 µm² per lane against Vitis's 679 and XLS's 406.
- **XLS's flops are its proc state only, and they do not grow with W:** 32 (the loop count: vecadd, vecmul, matadd, relu), 96 (axpy: loop count and alpha), 160 (vsum, dot, rowsum). That makes XLS the smallest case in every kernel, with flops at most 3 % of its energy from W = 8.
- **64-bit multipliers set the area wherever they are in the datapath** (vecmul, dot, axpy): about 7.0k to 8.6k µm² per lane for every tool. At W = 16, Vitis opt is within 1 to 10 % of XLS and Bambu 12 to 22 % above it, the difference being registers.
- **Run-time pins:** Vitis registers its pins (`ap_vld`), XLS keeps them in its proc state, and Bambu reads them as plain wires held for the task, so Bambu pays no pin registers. In axpy, Vitis's 65 extra fixed flops against vecadd are alpha's pin register.
- **Energy per task falls with W and then levels off:** the fixed part (control, handshakes, reset logic) is paid per cycle, and wider beats need fewer cycles for the same task.
- **Latency is about one cycle per beat for all four cases.** The differences of 1 or 2 cycles are their windows and pipeline depths (Vitis opt 2 stages at 10 ns, Bambu an iteration latency of 2 or 3, XLS one stage). The one real exception is Bambu's dot at W = 4 and 8, which runs at II = 2.
- **Control is only visible where the RTL keeps it apart.** Bambu's controller is a module of its own and small (81 µm² in dot at W = 8, 0.1 % of the area). Vitis and XLS mix control and datapath in one flat module, so their control cost cannot be split out after synthesis (X41); their totals hold it.
- **Timing:** every point meets 10 ns. XLS, with one combinational stage from its ports, has the least slack (dot at W = 16: 2.38 ns on nangate45, against 3.87 ns for Bambu at W = 8 and 4.17 ns for Vitis at W = 8, R4).

## 3. Tier done

### vecadd

<!-- gen:done/vecadd -->
![vecadd](compare_hls/done_vecadd.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 1,301 | 4.018 | 2050 | 0.196 |
| 1 | Vitis dace | 1,420 | 4.409 | 2050 | 0.2151 |
| 1 | Bambu | 2,425 | 7.421 | 2050 | 0.362 |
| 1 | XLS | 701.7 | 2.666 | 2049 | 0.1301 |
| 2 | Vitis opt | 1,980 | 3.502 | 1026 | 0.3413 |
| 2 | Vitis dace | 2,424 | 3.922 | 1026 | 0.3822 |
| 2 | Bambu | 4,046 | 6.844 | 1026 | 0.6671 |
| 2 | XLS | 1,108 | 2.429 | 1025 | 0.237 |
| 4 | Vitis opt | 3,340 | 3.241 | 514 | 0.6306 |
| 4 | Vitis dace | 3,780 | 3.448 | 515 | 0.6696 |
| 4 | Bambu | 7,288 | 6.547 | 514 | 1.274 |
| 4 | XLS | 1,920 | 2.308 | 513 | 0.4499 |
| 8 | Vitis opt | 6,057 | 3.124 | 258 | 1.211 |
| 8 | Vitis dace | 6,459 | 3.221 | 259 | 1.244 |
| 8 | Bambu | 13,777 | 6.413 | 258 | 2.486 |
| 8 | XLS | 3,545 | 2.256 | 257 | 0.8777 |
| 16 | Vitis opt | 11,489 | 3.058 | 130 | 2.352 |
| 16 | Vitis dace | 11,864 | 3.099 | 131 | 2.366 |
| 16 | Bambu | 26,748 | 6.362 | 130 | 4.894 |
| 16 | XLS | 6,795 | 2.232 | 129 | 1.73 |
<!-- /gen -->

**Insights.**

- At W = 16: XLS 6.8k µm², Vitis opt 11.5k, Vitis dace 11.9k, Bambu 26.7k. Per lane: XLS 406, Vitis 679, Bambu 1622 µm². The gap is registers: Vitis adds 64 flops per lane (the output beat), Bambu 192 (both input beats and the output beat), XLS none.
- Energy per task barely moves from W = 4 on: XLS 2.2 to 2.7 nJ, Vitis opt 3.1 to 4.0, Bambu 6.4 to 7.4. Flops are 72 to 78 % of Vitis's energy, 60 to 64 % of Bambu's and 1 to 16 % of XLS's.
- Vitis dace is opt with 30 to 50 more flops and, from W = 4, one more cycle.

### vecmul

<!-- gen:done/vecmul -->
![vecmul](compare_hls/done_vecmul.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 7,956 | 26.36 | 2050 | 1.286 |
| 1 | Vitis dace | 8,076 | 26.75 | 2050 | 1.305 |
| 1 | Bambu | 9,073 | 31.17 | 2050 | 1.521 |
| 1 | XLS | 7,311 | 25.7 | 2049 | 1.254 |
| 2 | Vitis opt | 15,291 | 25.88 | 1026 | 2.522 |
| 2 | Vitis dace | 15,735 | 26.29 | 1026 | 2.563 |
| 2 | Bambu | 17,340 | 30.65 | 1026 | 2.987 |
| 2 | XLS | 14,276 | 25.37 | 1025 | 2.475 |
| 4 | Vitis opt | 29,961 | 25.53 | 514 | 4.967 |
| 4 | Vitis dace | 30,402 | 25.74 | 515 | 4.998 |
| 4 | Bambu | 33,876 | 30.29 | 514 | 5.893 |
| 4 | XLS | 28,610 | 25.84 | 513 | 5.038 |
| 8 | Vitis opt | 59,302 | 25.33 | 258 | 9.816 |
| 8 | Vitis dace | 59,710 | 25.42 | 259 | 9.814 |
| 8 | Bambu | 66,948 | 30.1 | 258 | 11.67 |
| 8 | XLS | 56,467 | 24.97 | 257 | 9.718 |
| 16 | Vitis opt | 117,985 | 25.18 | 130 | 19.37 |
| 16 | Vitis dace | 118,359 | 25.22 | 131 | 19.25 |
| 16 | Bambu | 133,097 | 30.05 | 130 | 23.11 |
| 16 | XLS | 112,942 | 25.37 | 129 | 19.66 |
<!-- /gen -->

**Insights.**

- The 64-bit multiplier is about 7k µm² per lane for every tool, so the areas stay within 18 % (W = 16: XLS 112.9k, Vitis opt 118.0k, Bambu 133.1k).
- Bambu spends about 20 % more energy per task (30 against 25 nJ); its flops are 18 to 20 % of its energy, against 9 to 12 % for Vitis and 0 to 2 % for XLS. The registered beats are the same as in vecadd.

### vsum

<!-- gen:done/vsum -->
![vsum](compare_hls/done_vsum.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 2,376 | 6.916 | 2050 | 0.3374 |
| 1 | Vitis dace | 1,493 | 4.785 | 2051 | 0.2333 |
| 1 | Bambu | 2,951 | 8.379 | 2050 | 0.4087 |
| 1 | XLS | 1,549 | 5.022 | 2049 | 0.2451 |
| 2 | Vitis opt | 2,644 | 3.789 | 1026 | 0.3693 |
| 2 | Bambu | 3,629 | 5.253 | 1026 | 0.512 |
| 2 | XLS | 1,882 | 2.962 | 1025 | 0.2889 |
| 4 | Vitis opt | 3,178 | 2.236 | 514 | 0.435 |
| 4 | Bambu | 4,988 | 3.761 | 514 | 0.7316 |
| 4 | XLS | 2,555 | 1.991 | 513 | 0.388 |
| 8 | Vitis opt | 4,246 | 1.499 | 258 | 0.5808 |
| 8 | Bambu | 7,703 | 2.992 | 258 | 1.16 |
| 8 | XLS | 3,898 | 1.512 | 257 | 0.5883 |
| 16 | Vitis opt | 6,383 | 1.105 | 130 | 0.8501 |
| 16 | Bambu | 13,617 | 2.717 | 131 | 2.074 |
| 16 | XLS | 6,586 | 1.266 | 129 | 0.9817 |
<!-- /gen -->

**Insights.**

- No per-lane registers in Vitis opt (264 flops at every W) or XLS (160); Bambu registers the input beat, 64 flops per lane, so its area grows 711 µm² per lane against 267 (Vitis) and 336 (XLS).
- The fixed part dominates at small W: about 2.1k µm² for Vitis and 2.2k for Bambu against 1.2k for XLS, which has 104 fewer flops than Vitis.
- Energy per task drops from W = 1 to 16 by 6x for Vitis, 4x for XLS and 3x for Bambu: the fixed per-cycle cost is spread over fewer cycles, but Bambu's input registers grow with W.
- Vitis dace exists only at W = 1 (1.5k µm², 166 flops), smaller than opt there (2.4k µm², 264 flops).

### dot

<!-- gen:done/dot -->
![dot](compare_hls/done_dot.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 9,301 | 29.91 | 2050 | 1.459 |
| 1 | Vitis dace | parked: needs a RAM macro | | | |
| 1 | Bambu | 10,321 | 34.37 | 2050 | 1.677 |
| 1 | XLS | 8,468 | 28.54 | 2049 | 1.393 |
| 2 | Vitis opt | 16,494 | 26.85 | 1026 | 2.617 |
| 2 | Bambu | 18,325 | 31.31 | 1026 | 3.052 |
| 2 | XLS | 15,732 | 27.48 | 1025 | 2.681 |
| 4 | Vitis opt | 30,879 | 25.26 | 514 | 4.914 |
| 4 | Bambu | 34,352 | 32.77 | 1026 | 3.194 |
| 4 | XLS | 30,141 | 26.38 | 513 | 5.142 |
| 8 | Vitis opt | 60,079 | 24.57 | 258 | 9.523 |
| 8 | Bambu | 66,374 | 31.33 | 514 | 6.095 |
| 8 | XLS | 59,137 | 25.92 | 257 | 10.08 |
| 16 | Vitis opt | 118,444 | 24.2 | 130 | 18.61 |
| 16 | Bambu | 131,737 | 28.82 | 131 | 22 |
| 16 | XLS | 117,399 | 25.83 | 129 | 20.02 |
<!-- /gen -->

**Insights.**

- Bambu runs at II = 2 at W = 4 and 8: 1026 and 514 cycles, twice the others, with the same lanes. Its energy per task rises at W = 4 (32.8 nJ against 31.3 at W = 2), and its power is lower than the others' there.
- Vitis opt at 10 ns cuts its adder tree with 64-bit partial-sum registers at W = 8 (two) and W = 16 (four), `add_ln21_*_reg` in its Verilog; that is where its flops grow from 264 to 328 and 456.
- XLS's combinational energy is 5 to 9 % above Vitis opt's at every W, while its flops are fewer (160). XLS gates every input bit with its idle state before the multipliers; how much of the gap that explains is not measured.
- The areas stay within 12 % (W = 16: XLS 117.4k µm², Vitis opt 118.4k, Bambu 131.7k). Vitis dace_w1 is parked (RAM).

## 4. Tier untiered

### matadd

<!-- gen:untiered/matadd -->
![matadd](compare_hls/untiered_matadd.png)

m16_n32, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 1,301 | 1.008 | 514 | 0.1961 |
| 1 | Vitis dace | 1,420 | 1.106 | 514 | 0.2152 |
| 1 | Bambu | 2,425 | 1.861 | 514 | 0.362 |
| 1 | XLS | 701.7 | 0.669 | 513 | 0.1304 |
| 2 | Vitis opt | 1,980 | 0.8783 | 258 | 0.3404 |
| 2 | Vitis dace | 2,424 | 0.9831 | 258 | 0.3811 |
| 2 | Bambu | 4,046 | 1.718 | 258 | 0.6658 |
| 2 | XLS | 1,108 | 0.6103 | 257 | 0.2375 |
| 4 | Vitis opt | 3,340 | 0.8155 | 130 | 0.6273 |
| 4 | Vitis dace | 3,780 | 0.8674 | 131 | 0.6622 |
| 4 | Bambu | 7,288 | 1.649 | 130 | 1.268 |
| 4 | XLS | 1,920 | 0.5827 | 129 | 0.4517 |
| 8 | Vitis opt | 6,057 | 0.7865 | 66 | 1.192 |
| 8 | Vitis dace | 6,459 | 0.8107 | 67 | 1.21 |
| 8 | Bambu | 13,777 | 1.621 | 66 | 2.455 |
| 8 | XLS | 3,545 | 0.5719 | 65 | 0.8798 |
| 16 | Vitis opt | 11,489 | 0.7721 | 34 | 2.271 |
| 16 | Vitis dace | 11,864 | 0.7823 | 35 | 2.235 |
| 16 | Bambu | 26,748 | 1.621 | 34 | 4.768 |
| 16 | XLS | 6,795 | 0.5729 | 33 | 1.736 |
<!-- /gen -->

**Insights.**

- Every tool builds the same hardware as for vecadd (identical area and flops at every W): the 2-D loops become one flat run of M x N / W beats, so only the task size (512 elements) separates this table from vecadd's.

### relu

<!-- gen:untiered/relu -->
![relu](compare_hls/untiered_relu.png)

n512, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 1,028 | 0.8208 | 514 | 0.1597 |
| 1 | Vitis dace | 1,145 | 0.9185 | 514 | 0.1787 |
| 1 | Bambu | 1,764 | 1.25 | 514 | 0.2432 |
| 1 | XLS | 364.4 | 0.3697 | 513 | 0.07207 |
| 2 | Vitis opt | 1,434 | 0.6914 | 258 | 0.268 |
| 2 | Bambu | 2,765 | 1.117 | 258 | 0.4328 |
| 2 | XLS | 433.6 | 0.3096 | 257 | 0.1205 |
| 4 | Vitis opt | 2,246 | 0.6092 | 130 | 0.4686 |
| 4 | Bambu | 4,768 | 1.031 | 130 | 0.7929 |
| 4 | XLS | 571.9 | 0.2691 | 129 | 0.2086 |
| 8 | Vitis opt | 3,871 | 0.5798 | 66 | 0.8785 |
| 8 | Bambu | 8,776 | 0.9977 | 66 | 1.512 |
| 8 | XLS | 849.3 | 0.2537 | 65 | 0.3904 |
| 16 | Vitis opt | 7,121 | 0.582 | 34 | 1.712 |
| 16 | Bambu | 16,789 | 1.009 | 34 | 2.968 |
| 16 | XLS | 1,405 | 0.255 | 33 | 0.7729 |
<!-- /gen -->

**Insights.**

- The cheapest operation, so registers decide everything: XLS needs 69 µm² per lane (a sign select), Vitis opt is 59 to 68 % registers (the output beat, 64 flops per lane), and Bambu registers both the input and the output beat (128 per lane, 1002 µm² per lane).
- Energy per task at W = 8: XLS 0.25 nJ, Vitis 0.58, Bambu 1.00. Flops are 85 to 88 % of Vitis's energy.
- Each lane's sign bit is constant 0 after relu; Vitis's synthesis warns about it (LINT-52, LINT-31). Vitis dace exists only at W = 1.

### axpy

<!-- gen:untiered/axpy -->
![axpy](compare_hls/untiered_axpy.png)

n512, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 8,767 | 6.129 | 514 | 1.192 |
| 1 | Vitis dace | parked: needs a RAM macro | | | |
| 1 | Bambu | 9,340 | 6.737 | 514 | 1.311 |
| 1 | XLS | 7,883 | 5.526 | 513 | 1.077 |
| 2 | Vitis opt | 16,404 | 5.886 | 258 | 2.282 |
| 2 | Bambu | 17,909 | 6.603 | 258 | 2.559 |
| 2 | XLS | 14,883 | 5.404 | 257 | 2.103 |
| 4 | Vitis opt | 31,699 | 5.771 | 130 | 4.439 |
| 4 | Bambu | 35,066 | 6.538 | 130 | 5.029 |
| 4 | XLS | 28,904 | 5.375 | 129 | 4.167 |
| 8 | Vitis opt | 62,301 | 5.716 | 66 | 8.661 |
| 8 | Bambu | 69,396 | 6.503 | 66 | 9.854 |
| 8 | XLS | 56,854 | 5.335 | 65 | 8.208 |
| 16 | Vitis opt | 123,459 | 5.696 | 34 | 16.75 |
| 16 | Bambu | 138,011 | 6.506 | 34 | 19.14 |
| 16 | XLS | 112,732 | 5.437 | 33 | 16.48 |
<!-- /gen -->

**Insights.**

- Multiplier-bound, like vecmul: at W = 16, XLS 112.7k µm², Vitis opt 123.5k, Bambu 138.0k.
- XLS's 96 flops are its loop count and alpha; Vitis registers alpha as a pin and the output beat (199 fixed flops plus 64 per lane); Bambu reads alpha as a held wire but registers x, y and the output beat (192 flops per lane).
- Energy per task: XLS 5.3 to 5.5 nJ, Vitis 5.7 to 6.1, Bambu 6.5 to 6.7, so Bambu is about 20 % above XLS at every W. Vitis dace_w1 is parked (RAM).

### rowsum

<!-- gen:untiered/rowsum -->
![rowsum](compare_hls/untiered_rowsum.png)

m8_n64, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | Vitis opt | 2,376 | 1.756 | 514 | 0.3416 |
| 1 | Vitis dace | parked: needs a RAM macro | | | |
| 1 | Bambu | 2,951 | 2.12 | 514 | 0.4125 |
| 1 | XLS | 1,549 | 1.275 | 513 | 0.2486 |
| 2 | Vitis opt | 2,644 | 0.9706 | 258 | 0.3762 |
| 2 | Bambu | 3,629 | 1.326 | 258 | 0.5139 |
| 2 | XLS | 1,882 | 0.7509 | 257 | 0.2922 |
| 4 | Vitis opt | 3,178 | 0.5775 | 130 | 0.4442 |
| 4 | Bambu | 4,988 | 0.9536 | 130 | 0.7335 |
| 4 | XLS | 2,555 | 0.5086 | 129 | 0.3943 |
| 8 | Vitis opt | 4,246 | 0.3851 | 66 | 0.5835 |
| 8 | Bambu | 7,703 | 0.7555 | 66 | 1.145 |
| 8 | XLS | 3,898 | 0.3864 | 65 | 0.5945 |
| 16 | Vitis opt | 6,383 | 0.2853 | 34 | 0.839 |
| 16 | Bambu | 13,617 | 0.7047 | 35 | 2.013 |
| 16 | XLS | 6,586 | 0.3287 | 33 | 0.9962 |
<!-- /gen -->

**Insights.**

- Every tool builds the same hardware as for vsum (identical area and flops): restarting the sum every `len` beats costs nothing synthesis can see, so only the task size and Bambu's one extra cycle at W = 16 (35 against 34) differ from vsum.
- Vitis dace_w1 is parked (RAM).

## 5. nangate15 check

<!-- gen:tech -->
Values at W = 8 (nangate45 / nangate15); latency is the same on both:

| Kernel | Case | Area (µm²) | Energy (nJ) | Power (mW) |
|---|---|---|---|---|
| vecadd | Vitis opt | 6,057 / 1,693 | 3.124 / 0.9773 | 1.211 / 0.3788 |
| vecadd | Vitis dace | 6,459 / 1,807 | 3.221 / 1.002 | 1.244 / 0.3869 |
| vecadd | Bambu | 13,777 / 3,813 | 6.413 / 2.159 | 2.486 / 0.8368 |
| vecadd | XLS | 3,545 / 985.9 | 2.256 / 0.5825 | 0.8777 / 0.2267 |
| vecmul | Vitis opt | 59,302 / 18,793 | 25.33 / 8.317 | 9.816 / 3.224 |
| vecmul | Vitis dace | 59,710 / 18,907 | 25.42 / 8.342 | 9.814 / 3.221 |
| vecmul | Bambu | 66,948 / 20,840 | 30.1 / 9.7 | 11.67 / 3.76 |
| vecmul | XLS | 56,467 / 17,931 | 24.97 / 7.977 | 9.718 / 3.104 |
| vsum | Vitis opt | 4,246 / 1,194 | 1.499 / 0.4096 | 0.5808 / 0.1587 |
| vsum | Bambu | 7,703 / 2,134 | 2.992 / 0.9561 | 1.16 / 0.3706 |
| vsum | XLS | 3,898 / 1,096 | 1.512 / 0.3941 | 0.5883 / 0.1533 |
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

The order of the cases (smallest to largest) is the same on both technologies in 109 of 120 comparisons (kernel, W and metric with at least two cases).
<!-- /gen -->

## 6. Notes

- Parked points (a RAM macro, X15): Vitis dace_w1 of dot, axpy and rowsum.
- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.
