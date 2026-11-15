# rowsum (tier untiered)

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![rowsum](rowsum.png)

n2048, nangate45, int64, 10 ns. HLS clock-gated, forge ungated: forge's points are not yet synthesized gated, and the insights below were written when both were ungated.

[forge's ctrl + datapath against the HLS totals](rowsum_ctrl_dp.png): forge without its csr, its `<tag>_peripherals` and its glue; the HLS cases as above.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge | 2,677 | 6.805 | 2049 | 0.3321 |
| 1 | forge 2 | 2,677 | 6.805 | 2049 | 0.3321 |
| 1 | Vitis opt | 2,173 | 6.141 | 2050 | 0.2996 |
| 1 | Vitis dace | 15,774 | 17.4 | 2137 | 0.8141 |
| 1 | Bambu | 2,446 | 8.401 | 2050 | 0.4098 |
| 1 | XLS | 1,490 | 4.909 | 2049 | 0.2396 |
| 2 | forge | 2,942 | 3.808 | 1025 | 0.3715 |
| 2 | forge 2 | 3,517 | 5.343 | 1025 | 0.5213 |
| 2 | Vitis opt | 2,440 | 3.345 | 1026 | 0.326 |
| 2 | Bambu | 3,003 | 5.197 | 1026 | 0.5065 |
| 2 | XLS | 1,824 | 2.906 | 1025 | 0.2835 |
| 4 | forge | 3,478 | 2.284 | 513 | 0.4453 |
| 4 | forge 2 | 5,201 | 4.611 | 513 | 0.8989 |
| 4 | Vitis opt | 2,974 | 2.077 | 514 | 0.4041 |
| 4 | Bambu | 4,121 | 3.68 | 514 | 0.7159 |
| 4 | XLS | 2,496 | 1.974 | 513 | 0.3847 |
| 8 | forge | 4,548 | 1.501 | 257 | 0.5841 |
| 8 | forge 2 | 8,567 | 4.248 | 257 | 1.653 |
| 8 | Vitis opt | 4,043 | 1.407 | 258 | 0.5452 |
| 8 | Bambu | 6,352 | 2.873 | 258 | 1.114 |
| 8 | XLS | 3,840 | 1.498 | 257 | 0.5829 |
| 16 | forge | 6,685 | 1.12 | 129 | 0.8685 |
| 16 | forge 2 | 15,298 | 4.072 | 129 | 3.157 |
| 16 | Vitis opt | 6,179 | 1.064 | 130 | 0.8182 |
| 16 | Bambu | 11,178 | 2.583 | 131 | 1.971 |
| 16 | XLS | 6,528 | 1.266 | 129 | 0.9812 |
<!-- /gen -->

## Insights

- Every tool builds the same hardware as for vsum (identical area, flops and cycles at n2048): restarting the sum every `len` beats costs nothing synthesis can see, and the energies differ from vsum's by at most about 2 %.
- forge's rowsum (the tree, TreeAccumulate, JOB_BEATS = N / W) follows vsum's ratios. rowsum 2 (LaneAccumulate, W lanes across rows) has the same cycles but W 64-bit sums switching every cycle: its datapath is 2.0x rowsum's at W = 4 (3.4k against 1.6k µm²) and 2.8x at W = 16 (13.5k against 4.8k), and its energy per element without csr 2.3x and 4.0x (CTRL2 took the same 534 µm² of control off both, so rowsum 2's ratios grew a little). It is measured with ideal feed, so the bank conflicts of its column walk are not in these numbers. At W = 1 both build one adder and one register and come out identical.
- Vitis dace_w1 (X62): `y_buf` (16 x 64) built from flops, 9.2k of its 18.8k µm²; 2137 cycles; 32.9 nJ per task.

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge | csr | 794.3 | 1.439 | 0.7029 |
| 1 | forge | ctrl | 760.8 | 1.018 | 0.4973 |
| 1 | forge | datapath | 841.4 | 3.865 | 1.887 |
| 1 | forge | total | 2,677 | 6.805 | 3.323 |
| 1 | forge | total without csr | 1,603 | 4.884 | 2.385 |
| 1 | forge 2 | csr | 794.3 | 1.439 | 0.7029 |
| 1 | forge 2 | ctrl | 760.8 | 1.018 | 0.4973 |
| 1 | forge 2 | datapath | 841.4 | 3.865 | 1.887 |
| 1 | forge 2 | total | 2,677 | 6.805 | 3.323 |
| 1 | forge 2 | total without csr | 1,603 | 4.884 | 2.385 |
| 1 | Vitis opt | total | 2,173 | 6.141 | 2.999 |
| 1 | Vitis dace | RAM (flops) | 7,199 | 9.683 | 4.728 |
| 1 | Vitis dace | logic without the RAM | 8,575 | 7.715 | 3.767 |
| 1 | Vitis dace | total | 15,774 | 17.4 | 8.495 |
| 1 | Bambu | ctrl | 67.3 | 0.04319 | 0.02109 |
| 1 | Bambu | datapath | 2,374 | 8.343 | 4.074 |
| 1 | Bambu | total | 2,446 | 8.401 | 4.102 |
| 1 | XLS | total | 1,490 | 4.909 | 2.397 |
| 2 | forge | csr | 794.3 | 0.7202 | 0.3516 |
| 2 | forge | ctrl | 760.5 | 0.5161 | 0.252 |
| 2 | forge | datapath | 1,107 | 2.327 | 1.136 |
| 2 | forge | total | 2,942 | 3.808 | 1.859 |
| 2 | forge | total without csr | 1,869 | 2.843 | 1.388 |
| 2 | forge 2 | csr | 794.3 | 0.7202 | 0.3516 |
| 2 | forge 2 | ctrl | 760.5 | 0.513 | 0.2505 |
| 2 | forge 2 | datapath | 1,682 | 3.865 | 1.887 |
| 2 | forge 2 | total | 3,517 | 5.343 | 2.609 |
| 2 | forge 2 | total without csr | 2,444 | 4.378 | 2.138 |
| 2 | Vitis opt | total | 2,440 | 3.345 | 1.633 |
| 2 | Bambu | ctrl | 67.3 | 0.02188 | 0.01068 |
| 2 | Bambu | datapath | 2,930 | 5.167 | 2.523 |
| 2 | Bambu | total | 3,003 | 5.197 | 2.537 |
| 2 | XLS | total | 1,824 | 2.906 | 1.419 |
| 4 | forge | csr | 794.3 | 0.3605 | 0.176 |
| 4 | forge | ctrl | 760.5 | 0.2633 | 0.1286 |
| 4 | forge | datapath | 1,643 | 1.536 | 0.75 |
| 4 | forge | total | 3,478 | 2.284 | 1.115 |
| 4 | forge | total without csr | 2,405 | 1.799 | 0.8786 |
| 4 | forge 2 | csr | 794.3 | 0.3605 | 0.176 |
| 4 | forge 2 | ctrl | 759.7 | 0.2586 | 0.1263 |
| 4 | forge 2 | datapath | 3,367 | 3.868 | 1.888 |
| 4 | forge 2 | total | 5,201 | 4.611 | 2.252 |
| 4 | forge 2 | total without csr | 4,128 | 4.126 | 2.015 |
| 4 | Vitis opt | total | 2,974 | 2.077 | 1.014 |
| 4 | Bambu | ctrl | 67.3 | 0.01122 | 0.005477 |
| 4 | Bambu | datapath | 4,048 | 3.665 | 1.79 |
| 4 | Bambu | total | 4,121 | 3.68 | 1.797 |
| 4 | XLS | total | 2,496 | 1.974 | 0.9637 |
| 8 | forge | csr | 794.3 | 0.1807 | 0.08823 |
| 8 | forge | ctrl | 760.5 | 0.1354 | 0.06611 |
| 8 | forge | datapath | 2,713 | 1.122 | 0.5477 |
| 8 | forge | total | 4,548 | 1.501 | 0.733 |
| 8 | forge | total without csr | 3,474 | 1.257 | 0.6139 |
| 8 | forge 2 | csr | 794.3 | 0.1807 | 0.08823 |
| 8 | forge 2 | ctrl | 760.5 | 0.1307 | 0.06383 |
| 8 | forge 2 | datapath | 6,732 | 3.874 | 1.891 |
| 8 | forge 2 | total | 8,567 | 4.248 | 2.074 |
| 8 | forge 2 | total without csr | 7,493 | 4.004 | 1.955 |
| 8 | Vitis opt | total | 4,043 | 1.407 | 0.6868 |
| 8 | Bambu | ctrl | 67.3 | 0.005886 | 0.002874 |
| 8 | Bambu | datapath | 6,279 | 2.865 | 1.399 |
| 8 | Bambu | total | 6,352 | 2.873 | 1.403 |
| 8 | XLS | total | 3,840 | 1.498 | 0.7315 |
| 16 | forge | csr | 794.3 | 0.09078 | 0.04432 |
| 16 | forge | ctrl | 760.5 | 0.07144 | 0.03488 |
| 16 | forge | datapath | 4,849 | 0.926 | 0.4521 |
| 16 | forge | total | 6,685 | 1.12 | 0.5471 |
| 16 | forge | total without csr | 5,611 | 0.9974 | 0.487 |
| 16 | forge 2 | csr | 794.3 | 0.09078 | 0.04433 |
| 16 | forge 2 | ctrl | 760.5 | 0.06617 | 0.03231 |
| 16 | forge 2 | datapath | 13,463 | 3.883 | 1.896 |
| 16 | forge 2 | total | 15,298 | 4.072 | 1.988 |
| 16 | forge 2 | total without csr | 14,225 | 3.949 | 1.928 |
| 16 | Vitis opt | total | 6,179 | 1.064 | 0.5193 |
| 16 | Bambu | ctrl | 128.2 | 0.004935 | 0.00241 |
| 16 | Bambu | datapath | 11,045 | 2.577 | 1.258 |
| 16 | Bambu | total | 11,178 | 2.583 | 1.261 |
| 16 | XLS | total | 6,528 | 1.266 | 0.618 |
<!-- /gen -->
