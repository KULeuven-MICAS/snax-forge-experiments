# relu (tier untiered)

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![relu](relu.png)

n2048, nangate45, int64, 10 ns. HLS clock-gated, forge ungated: forge's points are not yet synthesized gated, and the insights below were written when both were ungated.

[forge's ctrl + datapath against the HLS totals](relu_ctrl_dp.png): forge without its csr, its `<tag>_peripherals` and its glue; the HLS cases as above.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge | 1,335 | 2.912 | 2048 | 0.1422 |
| 1 | Vitis opt | 933.7 | 2.845 | 2050 | 0.1388 |
| 1 | Vitis dace | 1,071 | 2.824 | 2050 | 0.1378 |
| 1 | Bambu | 1,431 | 4.925 | 2050 | 0.2402 |
| 1 | XLS | 337.3 | 1.481 | 2049 | 0.07229 |
| 2 | forge | 1,403 | 1.909 | 1024 | 0.1864 |
| 2 | Vitis opt | 1,287 | 2.475 | 1026 | 0.2412 |
| 2 | Bambu | 2,192 | 4.257 | 1026 | 0.4149 |
| 2 | XLS | 406.4 | 1.191 | 1025 | 0.1162 |
| 4 | forge | 1,540 | 1.397 | 512 | 0.2729 |
| 4 | Vitis opt | 1,993 | 2.279 | 514 | 0.4433 |
| 4 | Bambu | 3,715 | 3.904 | 514 | 0.7595 |
| 4 | XLS | 544.8 | 1.037 | 513 | 0.2022 |
| 8 | forge | 1,813 | 1.144 | 256 | 0.4469 |
| 8 | Vitis opt | 3,406 | 2.187 | 258 | 0.8478 |
| 8 | Bambu | 6,763 | 3.732 | 258 | 1.446 |
| 8 | XLS | 821.9 | 0.9652 | 257 | 0.3755 |
| 16 | forge | 2,360 | 1.019 | 128 | 0.7959 |
| 16 | Vitis opt | 6,232 | 2.148 | 130 | 1.652 |
| 16 | Bambu | 12,856 | 3.654 | 130 | 2.811 |
| 16 | XLS | 1,376 | 0.9321 | 129 | 0.7226 |
<!-- /gen -->

## Insights

- The cheapest operation, so registers decide everything: XLS needs 69 µm² per lane (a sign select), Vitis opt is 59 to 68 % registers (the output beat, 64 flops per lane), and Bambu registers both the input and the output beat (128 per lane, 1002 µm² per lane).
- Energy per task at W = 8: XLS 0.96 nJ, Vitis 2.24, Bambu 3.88. Flops are 86 to 89 % of Vitis's energy, 61 to 67 % of Bambu's, and 3 to 31 % of XLS's.
- Each lane's sign bit is constant 0 after relu; Vitis's synthesis warns about it (LINT-52, LINT-31). Vitis dace exists only at W = 1.
- forge: the datapath is the same sign select as XLS's (273 µm² at W = 4, against XLS's 253 AND gates, 269 µm²), so the whole gap is control. Since CTRL2 (snax-forge D168) forge's ctrl reads JOBS live from the csr and keeps 34 flops (busy, the 32-bit jobs counter, done): 438 µm², 181 of them flops, against XLS's 32 flops (145 µm²); its `<tag>_peripherals` holds BUSY_COUNTER, 279 µm² and 0.24 pJ per cycle.
- Without its csr (X63; the peripherals in no figure, X65) forge is 9 % (W = 16) to 39 % (W = 1) above XLS's area (508 against 364 µm² at W = 1) and 4 % above its energy at W = 1, 1 % at W = 4, level from W = 8 (W = 16: 0.452 against 0.453 pJ per element). Before CTRL2 it was 29 % to 2.1x and 3 to 40 %: the JOBS copy left the ctrl (711 to 438 µm²). relu is the one kernel where XLS has the smaller area at every W.

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge | csr | 547.7 | 0.9693 | 0.4733 |
| 1 | forge | ctrl | 438.1 | 0.5435 | 0.2654 |
| 1 | forge | datapath | 68.36 | 0.9181 | 0.4483 |
| 1 | forge | total | 1,335 | 2.912 | 1.422 |
| 1 | forge | total without csr | 507.5 | 1.462 | 0.7137 |
| 1 | Vitis opt | total | 933.7 | 2.845 | 1.389 |
| 1 | Vitis dace | total | 1,071 | 2.824 | 1.379 |
| 1 | Bambu | ctrl | 58.79 | 0.04314 | 0.02107 |
| 1 | Bambu | datapath | 1,367 | 4.867 | 2.376 |
| 1 | Bambu | total | 1,431 | 4.925 | 2.405 |
| 1 | XLS | total | 337.3 | 1.481 | 0.7233 |
| 2 | forge | csr | 547.7 | 0.4847 | 0.2367 |
| 2 | forge | ctrl | 438.1 | 0.2755 | 0.1345 |
| 2 | forge | datapath | 136.7 | 0.9045 | 0.4416 |
| 2 | forge | total | 1,403 | 1.909 | 0.9321 |
| 2 | forge | total without csr | 575.9 | 1.18 | 0.5761 |
| 2 | Vitis opt | total | 1,287 | 2.475 | 1.209 |
| 2 | Bambu | ctrl | 59.05 | 0.02183 | 0.01066 |
| 2 | Bambu | datapath | 2,128 | 4.227 | 2.064 |
| 2 | Bambu | total | 2,192 | 4.257 | 2.078 |
| 2 | XLS | total | 406.4 | 1.191 | 0.5814 |
| 4 | forge | csr | 547.7 | 0.2424 | 0.1184 |
| 4 | forge | ctrl | 438.1 | 0.1396 | 0.06815 |
| 4 | forge | datapath | 273.4 | 0.891 | 0.4351 |
| 4 | forge | total | 1,540 | 1.397 | 0.6821 |
| 4 | forge | total without csr | 712.6 | 1.031 | 0.5032 |
| 4 | Vitis opt | total | 1,993 | 2.279 | 1.113 |
| 4 | Bambu | ctrl | 59.05 | 0.01117 | 0.005455 |
| 4 | Bambu | datapath | 3,651 | 3.889 | 1.899 |
| 4 | Bambu | total | 3,715 | 3.904 | 1.906 |
| 4 | XLS | total | 544.8 | 1.037 | 0.5065 |
| 8 | forge | csr | 547.7 | 0.1213 | 0.05922 |
| 8 | forge | ctrl | 438.1 | 0.07074 | 0.03454 |
| 8 | forge | datapath | 546.9 | 0.8891 | 0.4341 |
| 8 | forge | total | 1,813 | 1.144 | 0.5586 |
| 8 | forge | total without csr | 986.1 | 0.9598 | 0.4687 |
| 8 | Vitis opt | total | 3,406 | 2.187 | 1.068 |
| 8 | Bambu | ctrl | 59.58 | 0.005843 | 0.002853 |
| 8 | Bambu | datapath | 6,698 | 3.724 | 1.818 |
| 8 | Bambu | total | 6,763 | 3.732 | 1.822 |
| 8 | XLS | total | 821.9 | 0.9652 | 0.4713 |
| 16 | forge | csr | 547.7 | 0.06071 | 0.02964 |
| 16 | forge | ctrl | 438.1 | 0.03585 | 0.01751 |
| 16 | forge | datapath | 1,094 | 0.8904 | 0.4347 |
| 16 | forge | total | 2,360 | 1.019 | 0.4975 |
| 16 | forge | total without csr | 1,533 | 0.9262 | 0.4523 |
| 16 | Vitis opt | total | 6,232 | 2.148 | 1.049 |
| 16 | Bambu | ctrl | 59.58 | 0.003178 | 0.001552 |
| 16 | Bambu | datapath | 12,791 | 3.65 | 1.782 |
| 16 | Bambu | total | 12,856 | 3.654 | 1.784 |
| 16 | XLS | total | 1,376 | 0.9321 | 0.4551 |
<!-- /gen -->
