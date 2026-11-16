# vecmul (tier done)

forge's figures exclude `<tag>_peripherals` (BUSY_COUNTER, snax-forge D168): it is in neither the csr nor the total without csr.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![vecmul](vecmul.png)

n2048, nangate45, int64, 10 ns, every case clock-gated.

[forge's ctrl + datapath against the HLS totals](vecmul_ctrl_dp.png): forge without its csr, its `<tag>_peripherals` and its glue; the HLS cases as above.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge | 8,079 | 24.99 | 2048 | 1.22 |
| 1 | Vitis opt | 7,795 | 25.91 | 2050 | 1.264 |
| 1 | Vitis dace | 7,925 | 25.89 | 2050 | 1.263 |
| 1 | Bambu | 8,641 | 31.08 | 2050 | 1.516 |
| 1 | XLS | 7,328 | 26.34 | 2049 | 1.286 |
| 2 | forge | 14,991 | 24.04 | 1024 | 2.348 |
| 2 | Vitis opt | 15,010 | 25.6 | 1026 | 2.495 |
| 2 | Vitis dace | 15,398 | 25.6 | 1026 | 2.495 |
| 2 | Bambu | 16,544 | 30.41 | 1026 | 2.964 |
| 2 | XLS | 14,389 | 26.07 | 1025 | 2.543 |
| 4 | forge | 28,817 | 23.6 | 512 | 4.609 |
| 4 | Vitis opt | 29,438 | 25.33 | 514 | 4.929 |
| 4 | Vitis dace | 29,834 | 25.35 | 515 | 4.922 |
| 4 | Bambu | 32,351 | 29.98 | 514 | 5.834 |
| 4 | XLS | 28,515 | 25.93 | 513 | 5.054 |
| 8 | forge | 56,467 | 23.35 | 256 | 9.119 |
| 8 | Vitis opt | 58,296 | 25.17 | 258 | 9.754 |
| 8 | Vitis dace | 58,662 | 25.17 | 259 | 9.72 |
| 8 | Bambu | 63,967 | 29.75 | 258 | 11.53 |
| 8 | XLS | 56,765 | 25.87 | 257 | 10.07 |
| 16 | forge | 111,767 | 23.2 | 128 | 18.13 |
| 16 | Vitis opt | 116,016 | 25.04 | 130 | 19.26 |
| 16 | Vitis dace | 116,351 | 25.05 | 131 | 19.12 |
| 16 | Bambu | 127,250 | 29.67 | 130 | 22.82 |
| 16 | XLS | 113,269 | 25.94 | 129 | 20.11 |
<!-- /gen -->

## Insights

- The 64-bit multiplier is about 7k µm² per lane for every tool, so the areas stay within 13 % (W = 16: XLS 113.3k, Vitis opt 116.0k, Bambu 127.2k).
- Bambu spends 18 to 20 % more energy per task than Vitis opt (29.7 to 31.1 against 25.0 to 25.9 nJ); its flop energy is 20 to 23 % of its energy, against 9 to 11 % for Vitis and 0.1 to 2 % for XLS. The registered beats are the same as in vecadd.
- forge without its csr has the smallest area from W = 2 (0.8 to 2.0 % below XLS's; 0.4 % above it at W = 1) and is 8 % lower in energy per element than the best HLS case at every W (W = 16: 11.29 pJ against Vitis opt's 12.23 and XLS's 12.67). Its totals with the CSR file are the lowest-energy case at every W (23.2 to 25.0 nJ).

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge | csr | 472.9 | 0.6206 | 0.303 |
| 1 | forge | ctrl | 440.2 | 0.6423 | 0.3136 |
| 1 | forge | datapath | 6,913 | 23.16 | 11.31 |
| 1 | forge | total | 8,079 | 24.99 | 12.2 |
| 1 | forge | total without csr | 7,354 | 23.8 | 11.62 |
| 1 | Vitis opt | total | 7,795 | 25.91 | 12.65 |
| 1 | Vitis dace | total | 7,925 | 25.89 | 12.64 |
| 1 | Bambu | ctrl | 72.35 | 0.04325 | 0.02112 |
| 1 | Bambu | datapath | 8,563 | 31.03 | 15.15 |
| 1 | Bambu | total | 8,641 | 31.08 | 15.18 |
| 1 | XLS | total | 7,328 | 26.34 | 12.86 |
| 2 | forge | csr | 472.9 | 0.3104 | 0.1516 |
| 2 | forge | ctrl | 440.2 | 0.3247 | 0.1586 |
| 2 | forge | datapath | 13,825 | 23.12 | 11.29 |
| 2 | forge | total | 14,991 | 24.04 | 11.74 |
| 2 | forge | total without csr | 14,267 | 23.44 | 11.45 |
| 2 | Vitis opt | total | 15,010 | 25.6 | 12.5 |
| 2 | Vitis dace | total | 15,398 | 25.6 | 12.5 |
| 2 | Bambu | ctrl | 72.35 | 0.02193 | 0.01071 |
| 2 | Bambu | datapath | 16,466 | 30.38 | 14.83 |
| 2 | Bambu | total | 16,544 | 30.41 | 14.85 |
| 2 | XLS | total | 14,389 | 26.07 | 12.73 |
| 4 | forge | csr | 472.9 | 0.1553 | 0.07584 |
| 4 | forge | ctrl | 440.2 | 0.1641 | 0.08015 |
| 4 | forge | datapath | 27,650 | 23.13 | 11.29 |
| 4 | forge | total | 28,817 | 23.6 | 11.52 |
| 4 | forge | total without csr | 28,092 | 23.3 | 11.37 |
| 4 | Vitis opt | total | 29,438 | 25.33 | 12.37 |
| 4 | Vitis dace | total | 29,834 | 25.35 | 12.38 |
| 4 | Bambu | ctrl | 72.35 | 0.01127 | 0.005502 |
| 4 | Bambu | datapath | 32,273 | 29.97 | 14.63 |
| 4 | Bambu | total | 32,351 | 29.98 | 14.64 |
| 4 | XLS | total | 28,515 | 25.93 | 12.66 |
| 8 | forge | csr | 472.9 | 0.07776 | 0.03797 |
| 8 | forge | ctrl | 440.2 | 0.08293 | 0.04049 |
| 8 | forge | datapath | 55,300 | 23.11 | 11.28 |
| 8 | forge | total | 56,467 | 23.35 | 11.4 |
| 8 | forge | total without csr | 55,742 | 23.19 | 11.33 |
| 8 | Vitis opt | total | 58,296 | 25.17 | 12.29 |
| 8 | Vitis dace | total | 58,662 | 25.17 | 12.29 |
| 8 | Bambu | ctrl | 75.28 | 0.005961 | 0.002911 |
| 8 | Bambu | datapath | 63,886 | 29.74 | 14.52 |
| 8 | Bambu | total | 63,967 | 29.75 | 14.53 |
| 8 | XLS | total | 56,765 | 25.87 | 12.63 |
| 16 | forge | csr | 472.9 | 0.03898 | 0.01904 |
| 16 | forge | ctrl | 440.2 | 0.04186 | 0.02044 |
| 16 | forge | datapath | 110,601 | 23.09 | 11.27 |
| 16 | forge | total | 111,767 | 23.2 | 11.33 |
| 16 | forge | total without csr | 111,042 | 23.13 | 11.29 |
| 16 | Vitis opt | total | 116,016 | 25.04 | 12.23 |
| 16 | Vitis dace | total | 116,351 | 25.05 | 12.23 |
| 16 | Bambu | ctrl | 75.28 | 0.003297 | 0.00161 |
| 16 | Bambu | datapath | 127,169 | 29.66 | 14.48 |
| 16 | Bambu | total | 127,250 | 29.67 | 14.49 |
| 16 | XLS | total | 113,269 | 25.94 | 12.67 |
<!-- /gen -->
