# dot (tier done)

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![dot](dot.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge 2 | 10,792 | 31.51 | 2050 | 1.537 |
| 1 | forge 3 | 9,590 | 29 | 2049 | 1.416 |
| 1 | forge 4 | 10,307 | 29.31 | 2050 | 1.43 |
| 1 | forge 5 | 10,281 | 29.29 | 2050 | 1.429 |
| 1 | forge 6 | 10,778 | 30.24 | 2051 | 1.474 |
| 1 | Vitis opt | 9,301 | 29.91 | 2050 | 1.459 |
| 1 | Vitis dace | 57,696 | 75.46 | 4101 | 1.84 |
| 1 | Bambu | 10,321 | 34.37 | 2050 | 1.677 |
| 1 | XLS | 8,468 | 28.54 | 2049 | 1.393 |
| 2 | forge 2 | 18,431 | 28.02 | 1026 | 2.731 |
| 2 | forge 3 | 16,767 | 26.17 | 1025 | 2.553 |
| 2 | forge 4 | 18,205 | 27.46 | 1026 | 2.676 |
| 2 | forge 5 | 18,400 | 27.38 | 1027 | 2.666 |
| 2 | forge 6 | 19,333 | 28.02 | 1028 | 2.726 |
| 2 | Vitis opt | 16,494 | 26.85 | 1026 | 2.617 |
| 2 | Bambu | 18,325 | 31.31 | 1026 | 3.052 |
| 2 | XLS | 15,732 | 27.48 | 1025 | 2.681 |
| 4 | forge 2 | 33,713 | 26.25 | 514 | 5.107 |
| 4 | forge 3 | 31,127 | 24.65 | 513 | 4.805 |
| 4 | forge 4 | 34,014 | 26.6 | 514 | 5.176 |
| 4 | forge 5 | 33,842 | 26.36 | 517 | 5.098 |
| 4 | forge 6 | 35,647 | 26.99 | 518 | 5.211 |
| 4 | Vitis opt | 30,879 | 25.26 | 514 | 4.914 |
| 4 | Bambu | 34,352 | 32.77 | 1026 | 3.194 |
| 4 | XLS | 30,141 | 26.38 | 513 | 5.142 |
| 8 | forge 2 | 64,277 | 25.34 | 258 | 9.82 |
| 8 | forge 3 | 59,845 | 23.83 | 257 | 9.272 |
| 8 | forge 4 | 65,647 | 26.13 | 258 | 10.13 |
| 8 | forge 5 | 64,584 | 25.59 | 265 | 9.658 |
| 8 | forge 6 | 68,296 | 26.42 | 266 | 9.933 |
| 8 | Vitis opt | 60,079 | 24.57 | 258 | 9.523 |
| 8 | Bambu | 66,374 | 31.33 | 514 | 6.095 |
| 8 | XLS | 59,137 | 25.92 | 257 | 10.08 |
| 16 | forge 2 | 125,400 | 24.89 | 130 | 19.15 |
| 16 | forge 3 | 117,278 | 23.43 | 129 | 18.16 |
| 16 | forge 4 | 128,813 | 25.95 | 130 | 19.96 |
| 16 | forge 5 | 126,139 | 25.43 | 145 | 17.53 |
| 16 | forge 6 | 133,541 | 26.29 | 146 | 18.01 |
| 16 | Vitis opt | 118,444 | 24.2 | 130 | 18.61 |
| 16 | Bambu | 131,737 | 28.82 | 131 | 22 |
| 16 | XLS | 117,399 | 25.83 | 129 | 20.02 |
<!-- /gen -->

## Insights

- Bambu runs at II = 2 at W = 4 and 8: 1026 and 514 cycles, twice the others, with the same lanes. Its energy per task rises at W = 4 (32.8 nJ against 31.3 at W = 2), and its power is lower than the others' there.
- Vitis opt at 10 ns cuts its adder tree with 64-bit partial-sum registers at W = 8 (two) and W = 16 (four), `add_ln21_*_reg` in its Verilog; that is where its flops grow from 264 to 328 and 456.
- XLS's combinational energy is 5 to 9 % above Vitis opt's at every W, while its flops are fewer (160). XLS gates every input bit with its idle state before the multipliers; how much of the gap that explains is not measured.
- The areas stay within 12 % (W = 16: XLS 117.4k µm², Vitis opt 118.4k, Bambu 131.7k).
- forge's dot 3 (the fused tree) is its best variant at every W, and without its csr it has the lowest energy of every case at every W, 4 to 6 % below the best HLS case (W = 16: 11.38 pJ per element against Vitis opt's 11.82 and XLS's 12.61), with the smallest area from W = 2 (116.2k µm² against XLS's 117.4k at W = 16) and 0.6 % above XLS's at W = 1. CTRL2 took 533 to 587 µm² off each variant's ctrl (dot 3 1,295 to 761 µm², dot 2 2,086 to 1,501, 196 to 132 flops): 5.3 % of dot 3's total at W = 1, 1.7 % at W = 4 and 0.5 % at W = 16. At W = 16, dot 2, 4, 5 and 6 cost 7, 10, 8 and 14 % more area than dot 3, and dot 5 and 6 take 145 and 146 cycles against 129 (the MAC's stall and the holding buffer's drain).
- Vitis dace_w1 (X62): 57.7k µm², 49.3k of it the 2048 x 64 macro holding DaCe's products; 4101 cycles, its two loops one after the other; 75.5 nJ per task, 45.3 of it the macro's counted 2048 writes and 2051 reads.

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge 2 | csr | 794.3 | 1.44 | 0.7032 |
| 1 | forge 2 | ctrl | 1,502 | 1.989 | 0.971 |
| 1 | forge 2 | datapath | 8,215 | 27.6 | 13.47 |
| 1 | forge 2 | total | 10,792 | 31.51 | 15.38 |
| 1 | forge 2 | total without csr | 9,719 | 29.58 | 14.45 |
| 1 | forge 3 | csr | 794.3 | 1.439 | 0.7029 |
| 1 | forge 3 | ctrl | 761 | 1.014 | 0.4949 |
| 1 | forge 3 | datapath | 7,753 | 26.07 | 12.73 |
| 1 | forge 3 | total | 9,590 | 29 | 14.16 |
| 1 | forge 3 | total without csr | 8,516 | 27.08 | 13.22 |
| 1 | forge 4 | csr | 794.3 | 1.44 | 0.7032 |
| 1 | forge 4 | ctrl | 1,141 | 1.501 | 0.7327 |
| 1 | forge 4 | datapath | 8,091 | 25.89 | 12.64 |
| 1 | forge 4 | total | 10,307 | 29.31 | 14.31 |
| 1 | forge 4 | total without csr | 9,234 | 27.39 | 13.37 |
| 1 | forge 5 | csr | 794.3 | 1.44 | 0.7032 |
| 1 | forge 5 | ctrl | 1,116 | 1.5 | 0.7326 |
| 1 | forge 5 | datapath | 8,091 | 25.87 | 12.63 |
| 1 | forge 5 | total | 10,281 | 29.29 | 14.3 |
| 1 | forge 5 | total without csr | 9,208 | 27.37 | 13.36 |
| 1 | forge 6 | csr | 794.3 | 1.441 | 0.7036 |
| 1 | forge 6 | ctrl | 1,151 | 1.516 | 0.7403 |
| 1 | forge 6 | datapath | 8,553 | 26.8 | 13.09 |
| 1 | forge 6 | total | 10,778 | 30.24 | 14.77 |
| 1 | forge 6 | total without csr | 9,705 | 28.32 | 13.83 |
| 1 | Vitis opt | total | 9,301 | 29.91 | 14.6 |
| 1 | Vitis dace | RAM (macro) | 49,275 | 45.26 | 22.1 |
| 1 | Vitis dace | logic without the RAM | 8,421 | 30.2 | 14.75 |
| 1 | Vitis dace | total | 57,696 | 75.46 | 36.85 |
| 1 | Bambu | ctrl | 60.12 | 0.04361 | 0.02129 |
| 1 | Bambu | datapath | 10,255 | 34.32 | 16.76 |
| 1 | Bambu | total | 10,321 | 34.37 | 16.78 |
| 1 | XLS | total | 8,468 | 28.54 | 13.94 |
| 2 | forge 2 | csr | 794.3 | 0.7209 | 0.352 |
| 2 | forge 2 | ctrl | 1,501 | 1.004 | 0.4901 |
| 2 | forge 2 | datapath | 15,854 | 26.05 | 12.72 |
| 2 | forge 2 | total | 18,431 | 28.02 | 13.68 |
| 2 | forge 2 | total without csr | 17,357 | 27.06 | 13.21 |
| 2 | forge 3 | csr | 794.3 | 0.7202 | 0.3516 |
| 2 | forge 3 | ctrl | 760.8 | 0.511 | 0.2495 |
| 2 | forge 3 | datapath | 14,931 | 24.69 | 12.06 |
| 2 | forge 3 | total | 16,767 | 26.17 | 12.78 |
| 2 | forge 3 | total without csr | 15,693 | 25.2 | 12.31 |
| 2 | forge 4 | csr | 794.3 | 0.7209 | 0.352 |
| 2 | forge 4 | ctrl | 1,142 | 0.7553 | 0.3688 |
| 2 | forge 4 | datapath | 15,988 | 25.74 | 12.57 |
| 2 | forge 4 | total | 18,205 | 27.46 | 13.41 |
| 2 | forge 4 | total without csr | 17,131 | 26.49 | 12.94 |
| 2 | forge 5 | csr | 794.3 | 0.7216 | 0.3523 |
| 2 | forge 5 | ctrl | 1,150 | 0.7634 | 0.3727 |
| 2 | forge 5 | datapath | 16,175 | 25.65 | 12.52 |
| 2 | forge 5 | total | 18,400 | 27.38 | 13.37 |
| 2 | forge 5 | total without csr | 17,326 | 26.41 | 12.9 |
| 2 | forge 6 | csr | 794.3 | 0.7223 | 0.3527 |
| 2 | forge 6 | ctrl | 1,160 | 0.7715 | 0.3767 |
| 2 | forge 6 | datapath | 17,098 | 26.28 | 12.83 |
| 2 | forge 6 | total | 19,333 | 28.02 | 13.68 |
| 2 | forge 6 | total without csr | 18,259 | 27.05 | 13.21 |
| 2 | Vitis opt | total | 16,494 | 26.85 | 13.11 |
| 2 | Bambu | ctrl | 60.12 | 0.02229 | 0.01088 |
| 2 | Bambu | datapath | 18,260 | 31.28 | 15.27 |
| 2 | Bambu | total | 18,325 | 31.31 | 15.29 |
| 2 | XLS | total | 15,732 | 27.48 | 13.42 |
| 4 | forge 2 | csr | 794.3 | 0.3612 | 0.1764 |
| 4 | forge 2 | ctrl | 1,501 | 0.5074 | 0.2478 |
| 4 | forge 2 | datapath | 31,137 | 25.26 | 12.33 |
| 4 | forge 2 | total | 33,713 | 26.25 | 12.82 |
| 4 | forge 2 | total without csr | 32,640 | 25.76 | 12.58 |
| 4 | forge 3 | csr | 794.3 | 0.3605 | 0.176 |
| 4 | forge 3 | ctrl | 760.8 | 0.2579 | 0.1259 |
| 4 | forge 3 | datapath | 29,291 | 23.91 | 11.67 |
| 4 | forge 3 | total | 31,127 | 24.65 | 12.04 |
| 4 | forge 3 | total without csr | 30,054 | 24.16 | 11.8 |
| 4 | forge 4 | csr | 794.3 | 0.3612 | 0.1764 |
| 4 | forge 4 | ctrl | 1,143 | 0.3809 | 0.186 |
| 4 | forge 4 | datapath | 31,797 | 25.74 | 12.57 |
| 4 | forge 4 | total | 34,014 | 26.6 | 12.99 |
| 4 | forge 4 | total without csr | 32,941 | 26.12 | 12.75 |
| 4 | forge 5 | csr | 794.3 | 0.3633 | 0.1774 |
| 4 | forge 5 | ctrl | 1,178 | 0.3914 | 0.1911 |
| 4 | forge 5 | datapath | 31,590 | 25.48 | 12.44 |
| 4 | forge 5 | total | 33,842 | 26.36 | 12.87 |
| 4 | forge 5 | total without csr | 32,769 | 25.87 | 12.63 |
| 4 | forge 6 | csr | 794.3 | 0.364 | 0.1777 |
| 4 | forge 6 | ctrl | 1,170 | 0.3955 | 0.1931 |
| 4 | forge 6 | datapath | 33,402 | 26.11 | 12.75 |
| 4 | forge 6 | total | 35,647 | 26.99 | 13.18 |
| 4 | forge 6 | total without csr | 34,573 | 26.5 | 12.94 |
| 4 | Vitis opt | total | 30,879 | 25.26 | 12.33 |
| 4 | Bambu | ctrl | 81.4 | 0.3827 | 0.1869 |
| 4 | Bambu | datapath | 34,265 | 32.38 | 15.81 |
| 4 | Bambu | total | 34,352 | 32.77 | 16 |
| 4 | XLS | total | 30,141 | 26.38 | 12.88 |
| 8 | forge 2 | csr | 794.3 | 0.1814 | 0.08857 |
| 8 | forge 2 | ctrl | 1,501 | 0.2574 | 0.1257 |
| 8 | forge 2 | datapath | 61,700 | 24.83 | 12.13 |
| 8 | forge 2 | total | 64,277 | 25.34 | 12.37 |
| 8 | forge 2 | total without csr | 63,203 | 25.09 | 12.25 |
| 8 | forge 3 | csr | 794.3 | 0.1807 | 0.08823 |
| 8 | forge 3 | ctrl | 760.8 | 0.1304 | 0.06367 |
| 8 | forge 3 | datapath | 58,009 | 23.45 | 11.45 |
| 8 | forge 3 | total | 59,845 | 23.83 | 11.64 |
| 8 | forge 3 | total without csr | 58,771 | 23.58 | 11.52 |
| 8 | forge 4 | csr | 795.6 | 0.1814 | 0.08856 |
| 8 | forge 4 | ctrl | 1,142 | 0.1927 | 0.0941 |
| 8 | forge 4 | datapath | 63,394 | 25.69 | 12.55 |
| 8 | forge 4 | total | 65,647 | 26.13 | 12.76 |
| 8 | forge 4 | total without csr | 64,538 | 25.89 | 12.64 |
| 8 | forge 5 | csr | 795.6 | 0.1863 | 0.09096 |
| 8 | forge 5 | ctrl | 1,174 | 0.2037 | 0.09944 |
| 8 | forge 5 | datapath | 62,299 | 25.14 | 12.27 |
| 8 | forge 5 | total | 64,584 | 25.59 | 12.5 |
| 8 | forge 5 | total without csr | 63,475 | 25.34 | 12.37 |
| 8 | forge 6 | csr | 795.6 | 0.187 | 0.0913 |
| 8 | forge 6 | ctrl | 1,195 | 0.2067 | 0.1009 |
| 8 | forge 6 | datapath | 65,990 | 25.96 | 12.68 |
| 8 | forge 6 | total | 68,296 | 26.42 | 12.9 |
| 8 | forge 6 | total without csr | 67,187 | 26.17 | 12.78 |
| 8 | Vitis opt | total | 60,079 | 24.57 | 12 |
| 8 | Bambu | ctrl | 81.4 | 0.1905 | 0.09302 |
| 8 | Bambu | datapath | 66,288 | 31.13 | 15.2 |
| 8 | Bambu | total | 66,374 | 31.33 | 15.3 |
| 8 | XLS | total | 59,137 | 25.92 | 12.65 |
| 16 | forge 2 | csr | 794.3 | 0.09148 | 0.04467 |
| 16 | forge 2 | ctrl | 1,501 | 0.1314 | 0.06418 |
| 16 | forge 2 | datapath | 122,824 | 24.63 | 12.03 |
| 16 | forge 2 | total | 125,400 | 24.89 | 12.15 |
| 16 | forge 2 | total without csr | 124,327 | 24.77 | 12.09 |
| 16 | forge 3 | csr | 794.3 | 0.09078 | 0.04433 |
| 16 | forge 3 | ctrl | 760.8 | 0.06618 | 0.03232 |
| 16 | forge 3 | datapath | 115,442 | 23.24 | 11.35 |
| 16 | forge 3 | total | 117,278 | 23.43 | 11.44 |
| 16 | forge 3 | total without csr | 116,204 | 23.3 | 11.38 |
| 16 | forge 4 | csr | 794.3 | 0.09148 | 0.04467 |
| 16 | forge 4 | ctrl | 1,142 | 0.09832 | 0.04801 |
| 16 | forge 4 | datapath | 126,596 | 25.73 | 12.56 |
| 16 | forge 4 | total | 128,813 | 25.95 | 12.67 |
| 16 | forge 4 | total without csr | 127,739 | 25.83 | 12.61 |
| 16 | forge 5 | csr | 794.3 | 0.102 | 0.04981 |
| 16 | forge 5 | ctrl | 1,170 | 0.1132 | 0.05528 |
| 16 | forge 5 | datapath | 123,894 | 25.17 | 12.29 |
| 16 | forge 5 | total | 126,139 | 25.43 | 12.41 |
| 16 | forge 5 | total without csr | 125,066 | 25.29 | 12.35 |
| 16 | forge 6 | csr | 794.3 | 0.1027 | 0.05016 |
| 16 | forge 6 | ctrl | 1,202 | 0.1152 | 0.05625 |
| 16 | forge 6 | datapath | 131,265 | 26.04 | 12.72 |
| 16 | forge 6 | total | 133,541 | 26.29 | 12.84 |
| 16 | forge 6 | total without csr | 132,467 | 26.16 | 12.77 |
| 16 | Vitis opt | total | 118,444 | 24.2 | 11.82 |
| 16 | Bambu | ctrl | 127.7 | 0.005539 | 0.002704 |
| 16 | Bambu | datapath | 131,604 | 28.82 | 14.07 |
| 16 | Bambu | total | 131,737 | 28.82 | 14.07 |
| 16 | XLS | total | 117,399 | 25.83 | 12.61 |
<!-- /gen -->
