# rowsum (tier untiered)

csr excludes `<tag>_peripherals` (BUSY_COUNTER), snax-forge D168.

Part of [the comparison](../README.md): setup, summary across kernels and the parts' basis are there.

<!-- gen:main -->
![rowsum](rowsum.png)

n2048, nangate45, int64, 10 ns.

| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |
|---|---|---|---|---|---|
| 1 | forge | 3,243 | 7.798 | 2049 | 0.3806 |
| 1 | forge 2 | 3,243 | 7.798 | 2049 | 0.3806 |
| 1 | Vitis opt | 2,376 | 7.001 | 2050 | 0.3415 |
| 1 | Vitis dace | 18,791 | 32.85 | 2137 | 1.537 |
| 1 | Bambu | 2,951 | 8.416 | 2050 | 0.4105 |
| 1 | XLS | 1,549 | 5.056 | 2049 | 0.2468 |
| 2 | forge | 3,509 | 4.307 | 1025 | 0.4202 |
| 2 | forge 2 | 4,083 | 5.841 | 1025 | 0.5698 |
| 2 | Vitis opt | 2,644 | 3.804 | 1026 | 0.3707 |
| 2 | Bambu | 3,629 | 5.267 | 1026 | 0.5133 |
| 2 | XLS | 1,882 | 2.977 | 1025 | 0.2905 |
| 4 | forge | 4,045 | 2.536 | 513 | 0.4943 |
| 4 | forge 2 | 5,767 | 4.861 | 513 | 0.9475 |
| 4 | Vitis opt | 3,178 | 2.282 | 514 | 0.444 |
| 4 | Bambu | 4,988 | 3.779 | 514 | 0.7352 |
| 4 | XLS | 2,555 | 2.01 | 513 | 0.3918 |
| 8 | forge | 5,114 | 1.63 | 257 | 0.6344 |
| 8 | forge 2 | 9,134 | 4.373 | 257 | 1.702 |
| 8 | Vitis opt | 4,246 | 1.511 | 258 | 0.5856 |
| 8 | Bambu | 7,703 | 2.987 | 258 | 1.158 |
| 8 | XLS | 3,898 | 1.515 | 257 | 0.5897 |
| 16 | forge | 7,251 | 1.187 | 129 | 0.9202 |
| 16 | forge 2 | 15,865 | 4.135 | 129 | 3.206 |
| 16 | Vitis opt | 6,383 | 1.117 | 130 | 0.8595 |
| 16 | Bambu | 13,617 | 2.721 | 131 | 2.077 |
| 16 | XLS | 6,586 | 1.274 | 129 | 0.9876 |
<!-- /gen -->

## Insights

- Every tool builds the same hardware as for vsum (identical area, flops and cycles at n2048): restarting the sum every `len` beats costs nothing synthesis can see, and the energies differ from vsum's by at most about 2 %.
- forge's rowsum (the tree, TreeAccumulate, JOB_BEATS = N / W) follows vsum's ratios. rowsum 2 (LaneAccumulate, W lanes across rows) has the same cycles but W 64-bit sums switching every cycle: its datapath is 2.0x rowsum's at W = 4 (3.4k against 1.6k µm²) and 2.8x at W = 16 (13.5k against 4.8k), and its ctrl + datapath energy per element 2.1x and 3.8x. It is measured with ideal feed, so the bank conflicts of its column walk are not in these numbers. At W = 1 both build one adder and one register and come out identical.
- Vitis dace_w1 (X62): `y_buf` (16 x 64) built from flops, 9.2k of its 18.8k µm²; 2137 cycles; 32.9 nJ per task.

## Parts at n2048

<!-- gen:parts -->
| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |
|---|---|---|---|---|---|
| 1 | forge | csr | 1,107 | 1.938 | 0.9461 |
| 1 | forge | ctrl | 1,295 | 1.995 | 0.9743 |
| 1 | forge | datapath | 841.4 | 3.865 | 1.887 |
| 1 | forge | total | 3,243 | 7.798 | 3.808 |
| 1 | forge | total without csr | 2,137 | 5.861 | 2.862 |
| 1 | forge 2 | csr | 1,107 | 1.938 | 0.9461 |
| 1 | forge 2 | ctrl | 1,295 | 1.995 | 0.9743 |
| 1 | forge 2 | datapath | 841.4 | 3.865 | 1.887 |
| 1 | forge 2 | total | 3,243 | 7.798 | 3.808 |
| 1 | forge 2 | total without csr | 2,137 | 5.861 | 2.862 |
| 1 | Vitis opt | total | 2,376 | 7.001 | 3.418 |
| 1 | Vitis dace | RAM (flops) | 9,232 | 18.27 | 8.92 |
| 1 | Vitis dace | logic without the RAM | 9,559 | 14.58 | 7.121 |
| 1 | Vitis dace | total | 18,791 | 32.85 | 16.04 |
| 1 | Bambu | ctrl | 55.06 | 0.04351 | 0.02125 |
| 1 | Bambu | datapath | 2,891 | 8.357 | 4.081 |
| 1 | Bambu | total | 2,951 | 8.416 | 4.109 |
| 1 | XLS | total | 1,549 | 5.056 | 2.469 |
| 2 | forge | csr | 1,107 | 0.9732 | 0.4752 |
| 2 | forge | ctrl | 1,294 | 1.007 | 0.4916 |
| 2 | forge | datapath | 1,107 | 2.327 | 1.136 |
| 2 | forge | total | 3,509 | 4.307 | 2.103 |
| 2 | forge | total without csr | 2,402 | 3.333 | 1.628 |
| 2 | forge 2 | csr | 1,107 | 0.9732 | 0.4752 |
| 2 | forge 2 | ctrl | 1,294 | 1.002 | 0.4892 |
| 2 | forge 2 | datapath | 1,682 | 3.866 | 1.888 |
| 2 | forge 2 | total | 4,083 | 5.841 | 2.852 |
| 2 | forge 2 | total without csr | 2,976 | 4.868 | 2.377 |
| 2 | Vitis opt | total | 2,644 | 3.804 | 1.857 |
| 2 | Bambu | ctrl | 55.06 | 0.02219 | 0.01084 |
| 2 | Bambu | datapath | 3,568 | 5.237 | 2.557 |
| 2 | Bambu | total | 3,629 | 5.267 | 2.572 |
| 2 | XLS | total | 1,882 | 2.977 | 1.454 |
| 4 | forge | csr | 1,107 | 0.4891 | 0.2388 |
| 4 | forge | ctrl | 1,294 | 0.5104 | 0.2492 |
| 4 | forge | datapath | 1,644 | 1.536 | 0.7502 |
| 4 | forge | total | 4,045 | 2.536 | 1.238 |
| 4 | forge | total without csr | 2,938 | 2.047 | 0.9994 |
| 4 | forge 2 | csr | 1,107 | 0.4891 | 0.2388 |
| 4 | forge 2 | ctrl | 1,294 | 0.5036 | 0.2459 |
| 4 | forge 2 | datapath | 3,366 | 3.868 | 1.889 |
| 4 | forge 2 | total | 5,767 | 4.861 | 2.373 |
| 4 | forge 2 | total without csr | 4,660 | 4.372 | 2.135 |
| 4 | Vitis opt | total | 3,178 | 2.282 | 1.114 |
| 4 | Bambu | ctrl | 55.06 | 0.01153 | 0.005629 |
| 4 | Bambu | datapath | 4,928 | 3.764 | 1.838 |
| 4 | Bambu | total | 4,988 | 3.779 | 1.845 |
| 4 | XLS | total | 2,555 | 2.01 | 0.9814 |
| 8 | forge | csr | 1,107 | 0.2461 | 0.1202 |
| 8 | forge | ctrl | 1,294 | 0.2626 | 0.1282 |
| 8 | forge | datapath | 2,713 | 1.122 | 0.5477 |
| 8 | forge | total | 5,114 | 1.63 | 0.7961 |
| 8 | forge | total without csr | 4,008 | 1.384 | 0.676 |
| 8 | forge 2 | csr | 1,107 | 0.2461 | 0.1202 |
| 8 | forge 2 | ctrl | 1,294 | 0.2537 | 0.1239 |
| 8 | forge 2 | datapath | 6,732 | 3.874 | 1.891 |
| 8 | forge 2 | total | 9,134 | 4.373 | 2.135 |
| 8 | forge 2 | total without csr | 8,027 | 4.127 | 2.015 |
| 8 | Vitis opt | total | 4,246 | 1.511 | 0.7378 |
| 8 | Bambu | ctrl | 55.06 | 0.006196 | 0.003025 |
| 8 | Bambu | datapath | 7,642 | 2.979 | 1.455 |
| 8 | Bambu | total | 7,703 | 2.987 | 1.458 |
| 8 | XLS | total | 3,898 | 1.515 | 0.7399 |
| 16 | forge | csr | 1,107 | 0.1242 | 0.06064 |
| 16 | forge | ctrl | 1,294 | 0.1369 | 0.06685 |
| 16 | forge | datapath | 4,849 | 0.926 | 0.4521 |
| 16 | forge | total | 7,251 | 1.187 | 0.5796 |
| 16 | forge | total without csr | 6,144 | 1.063 | 0.519 |
| 16 | forge 2 | csr | 1,107 | 0.1242 | 0.06064 |
| 16 | forge 2 | ctrl | 1,295 | 0.1282 | 0.0626 |
| 16 | forge 2 | datapath | 13,463 | 3.883 | 1.896 |
| 16 | forge 2 | total | 15,865 | 4.135 | 2.019 |
| 16 | forge 2 | total without csr | 14,758 | 4.011 | 1.959 |
| 16 | Vitis opt | total | 6,383 | 1.117 | 0.5456 |
| 16 | Bambu | ctrl | 118.6 | 0.005344 | 0.00261 |
| 16 | Bambu | datapath | 13,493 | 2.715 | 1.325 |
| 16 | Bambu | total | 13,617 | 2.721 | 1.329 |
| 16 | XLS | total | 6,586 | 1.274 | 0.6221 |
<!-- /gen -->
