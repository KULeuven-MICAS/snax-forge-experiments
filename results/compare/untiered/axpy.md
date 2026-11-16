# axpy (tier untiered)

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![axpy](axpy.png)

n2048, nangate45, int64, 10 ns, every case clock-gated.

[forge's ctrl + datapath against the HLS totals](axpy_ctrl_dp.png): forge without its csr, its `<tag>_peripherals` and its glue; the HLS cases as above.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge | 8,711 | 21.31 | 2048 | 1.041 |
| 1 | forge baked | 1,702 | 4.168 | 2048 | 0.2035 |
| 1 | Vitis opt | 8,559 | 23.42 | 2050 | 1.142 |
| 1 | Vitis dace | 58,037 | 69.93 | 4101 | 1.705 |
| 1 | Bambu | 8,910 | 27.15 | 2050 | 1.325 |
| 1 | XLS | 7,829 | 21.91 | 2049 | 1.07 |
| 2 | forge | 15,625 | 20.45 | 1024 | 1.997 |
| 2 | forge baked | 2,237 | 3.26 | 1024 | 0.3184 |
| 2 | Vitis opt | 16,077 | 23.11 | 1026 | 2.252 |
| 2 | Bambu | 17,118 | 26.49 | 1026 | 2.582 |
| 2 | XLS | 14,817 | 21.63 | 1025 | 2.11 |
| 4 | forge | 29,441 | 19.96 | 512 | 3.897 |
| 4 | forge baked | 3,308 | 2.807 | 512 | 0.5483 |
| 4 | Vitis opt | 31,129 | 22.91 | 514 | 4.457 |
| 4 | Bambu | 33,551 | 26.12 | 514 | 5.081 |
| 4 | XLS | 28,829 | 21.54 | 513 | 4.2 |
| 8 | forge | 57,075 | 19.68 | 256 | 7.688 |
| 8 | forge baked | 5,450 | 2.571 | 256 | 1.004 |
| 8 | Vitis opt | 61,252 | 22.77 | 258 | 8.827 |
| 8 | Bambu | 66,432 | 25.89 | 258 | 10.03 |
| 8 | XLS | 56,791 | 21.37 | 257 | 8.314 |
| 16 | forge | 112,264 | 19.63 | 128 | 15.34 |
| 16 | forge baked | 9,734 | 2.451 | 128 | 1.915 |
| 16 | Vitis opt | 121,451 | 22.73 | 130 | 17.49 |
| 16 | Bambu | 132,178 | 25.8 | 130 | 19.85 |
| 16 | XLS | 112,758 | 21.6 | 129 | 16.75 |
<!-- /gen -->

## Insights

- Multiplier-bound, like vecmul: at W = 16, XLS 112.8k µm², Vitis opt 121.5k, Bambu 132.2k.
- XLS's 96 registers are its loop count and alpha; Vitis registers alpha as a pin and the output beat (135 fixed registers plus 64 per lane, 199 at W = 1); Bambu reads alpha as a held wire but registers x, y and the output beat (192 per lane).
- Energy per task: XLS 21.4 to 21.9 nJ, Vitis 22.7 to 23.4, Bambu 25.8 to 27.2, so Bambu is 19 to 24 % above XLS.
- forge with α in a CSR (K1_LO and K1_HI): without its csr it is 1 to 4 % smaller than XLS at every W and 8 to 9 % lower in energy (W = 16: 9.55 against 10.55 pJ per element). Its CSR file is the largest of the kernels, 912 µm² without its `<tag>_peripherals` (X65), for α's two words.
- forge baked bakes α = 3 into a shift and an add per lane: 9.0k µm² and 1.16 pJ per element at W = 16 without its csr, 12x less area and 9x less energy than the best run-time α case (XLS). It is not like-for-like; it shows what the design-time choice is worth.
- Vitis dace_w1 (X62): 58.0k µm², 49.3k of it the macro holding DaCe's α·x; 4101 cycles; 69.9 nJ per task, 45.2 of it the macro.

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge | csr | 911.6 | 0.6326 | 0.3089 |
| 1 | forge | ctrl | 440.2 | 0.6423 | 0.3136 |
| 1 | forge | datapath | 7,106 | 19.46 | 9.503 |
| 1 | forge | total | 8,711 | 21.31 | 10.41 |
| 1 | forge | total without csr | 7,547 | 20.11 | 9.817 |
| 1 | forge baked | csr | 472.9 | 0.6206 | 0.303 |
| 1 | forge baked | ctrl | 440.2 | 0.6423 | 0.3136 |
| 1 | forge baked | datapath | 535.5 | 2.336 | 1.141 |
| 1 | forge baked | total | 1,702 | 4.168 | 2.035 |
| 1 | forge baked | total without csr | 977.3 | 2.979 | 1.454 |
| 1 | Vitis opt | total | 8,559 | 23.42 | 11.43 |
| 1 | Vitis dace | RAM (macro) | 49,275 | 45.25 | 22.09 |
| 1 | Vitis dace | logic without the RAM | 8,762 | 24.69 | 12.05 |
| 1 | Vitis dace | total | 58,037 | 69.93 | 34.15 |
| 1 | Bambu | ctrl | 72.35 | 0.04325 | 0.02112 |
| 1 | Bambu | datapath | 8,833 | 27.09 | 13.23 |
| 1 | Bambu | total | 8,910 | 27.15 | 13.26 |
| 1 | XLS | total | 7,829 | 21.91 | 10.7 |
| 2 | forge | csr | 911.6 | 0.3167 | 0.1546 |
| 2 | forge | ctrl | 440.2 | 0.3247 | 0.1586 |
| 2 | forge | datapath | 14,020 | 19.52 | 9.532 |
| 2 | forge | total | 15,625 | 20.45 | 9.987 |
| 2 | forge | total without csr | 14,462 | 19.85 | 9.691 |
| 2 | forge baked | csr | 472.9 | 0.3104 | 0.1516 |
| 2 | forge baked | ctrl | 440.2 | 0.3247 | 0.1586 |
| 2 | forge baked | datapath | 1,071 | 2.337 | 1.141 |
| 2 | forge baked | total | 2,237 | 3.26 | 1.592 |
| 2 | forge baked | total without csr | 1,513 | 2.661 | 1.299 |
| 2 | Vitis opt | total | 16,077 | 23.11 | 11.28 |
| 2 | Bambu | ctrl | 72.35 | 0.02193 | 0.01071 |
| 2 | Bambu | datapath | 17,040 | 26.46 | 12.92 |
| 2 | Bambu | total | 17,118 | 26.49 | 12.94 |
| 2 | XLS | total | 14,817 | 21.63 | 10.56 |
| 4 | forge | csr | 911.6 | 0.1587 | 0.07749 |
| 4 | forge | ctrl | 440.2 | 0.1641 | 0.08014 |
| 4 | forge | datapath | 27,836 | 19.49 | 9.514 |
| 4 | forge | total | 29,441 | 19.96 | 9.744 |
| 4 | forge | total without csr | 28,278 | 19.65 | 9.595 |
| 4 | forge baked | csr | 472.9 | 0.1553 | 0.07584 |
| 4 | forge baked | ctrl | 440.2 | 0.1641 | 0.08015 |
| 4 | forge baked | datapath | 2,142 | 2.342 | 1.144 |
| 4 | forge baked | total | 3,308 | 2.807 | 1.371 |
| 4 | forge baked | total without csr | 2,584 | 2.506 | 1.224 |
| 4 | Vitis opt | total | 31,129 | 22.91 | 11.19 |
| 4 | Bambu | ctrl | 72.35 | 0.01127 | 0.005502 |
| 4 | Bambu | datapath | 33,473 | 26.1 | 12.75 |
| 4 | Bambu | total | 33,551 | 26.12 | 12.75 |
| 4 | XLS | total | 28,829 | 21.54 | 10.52 |
| 8 | forge | csr | 911.6 | 0.07979 | 0.03896 |
| 8 | forge | ctrl | 440.2 | 0.08291 | 0.04048 |
| 8 | forge | datapath | 55,470 | 19.45 | 9.495 |
| 8 | forge | total | 57,075 | 19.68 | 9.61 |
| 8 | forge | total without csr | 55,911 | 19.53 | 9.535 |
| 8 | forge baked | csr | 472.9 | 0.07776 | 0.03797 |
| 8 | forge baked | ctrl | 440.2 | 0.08293 | 0.04049 |
| 8 | forge baked | datapath | 4,284 | 2.336 | 1.141 |
| 8 | forge baked | total | 5,450 | 2.571 | 1.255 |
| 8 | forge baked | total without csr | 4,725 | 2.419 | 1.181 |
| 8 | Vitis opt | total | 61,252 | 22.77 | 11.12 |
| 8 | Bambu | ctrl | 75.28 | 0.005961 | 0.002911 |
| 8 | Bambu | datapath | 66,351 | 25.88 | 12.64 |
| 8 | Bambu | total | 66,432 | 25.89 | 12.64 |
| 8 | XLS | total | 56,791 | 21.37 | 10.43 |
| 16 | forge | csr | 911.6 | 0.04033 | 0.01969 |
| 16 | forge | ctrl | 440.2 | 0.04184 | 0.02043 |
| 16 | forge | datapath | 110,659 | 19.51 | 9.528 |
| 16 | forge | total | 112,264 | 19.63 | 9.586 |
| 16 | forge | total without csr | 111,100 | 19.56 | 9.548 |
| 16 | forge baked | csr | 472.9 | 0.03898 | 0.01904 |
| 16 | forge baked | ctrl | 440.2 | 0.04186 | 0.02044 |
| 16 | forge baked | datapath | 8,567 | 2.333 | 1.139 |
| 16 | forge baked | total | 9,734 | 2.451 | 1.197 |
| 16 | forge baked | total without csr | 9,009 | 2.375 | 1.16 |
| 16 | Vitis opt | total | 121,451 | 22.73 | 11.1 |
| 16 | Bambu | ctrl | 75.28 | 0.003297 | 0.00161 |
| 16 | Bambu | datapath | 132,097 | 25.8 | 12.6 |
| 16 | Bambu | total | 132,178 | 25.8 | 12.6 |
| 16 | XLS | total | 112,758 | 21.6 | 10.55 |
<!-- /gen -->
