# Control roles: every register of SYN1's points, forge and HLS

Written by `report/control_roles.py` (`pixi run control`) from `roles.json` (the roles, read from the RTL) and SYN1's `results/analysis/syn1/split_regs_<tech>.csv` (each register's flops and its internal and switching energy per cycle from PrimePower, X23). Every number is computed. Forge's RTL is snax-forge 32dbcc6; its control RTL at W = 8 is in `src/` (X26). HLS's Verilog is in hls-exercises, `hls-exercises/rtl/done/<kernel>/<case>_w<W>/`.

Each register has one role; the role's layer: **interface** (what HLS's block leaves to its driver: CSR settings, the START word, the read-back buffer, the cycle counter), **kernel** (settings latched or derived at start, progress counters, FSM state, pipeline control), **datapath** (data stages and data state). Energy is pJ per cycle (internal plus switching power of the register's flops, over the busy window); a cell reads `flops · pJ per cycle`. Flops only: the logic around the registers is in SYN1's section 9 by cone, not by role.

**Checks** (all passed): each of the 4802 register rows (both technologies) matches exactly one entry of `roles.json`, and every entry is used; 384 forge registers checked against their own bundle (a CSR's index against `accelerator.json`, a ctrl `_r`'s role against how ctrl loads it); the flops per point and cone equal `split_<tech>.csv`'s, and the energy within 0.000009 pJ per cycle.

## a. Per kernel at W = 8, nangate45

**vecadd**: flops · pJ per cycle

| layer | role | forge | HLS unopt | HLS opt | HLS dace |
|---|---|---|---|---|---|
| interface | csr_setting | 32 · 0.23 |  |  |  |
| interface | csr_start | 32 · 0.23 |  |  |  |
| interface | csr_readback | 33 · 0.24 |  |  |  |
| interface | perf_counter | 32 · 0.24 |  |  |  |
| **interface** | **all** | **129 · 0.93** |  |  |  |
| kernel | setting_latch | 32 · 0.23 | 33 · 0.23 | 33 · 0.23 | 29 · 0.20 |
| kernel | derived_setting |  |  |  | 56 · 0.39 |
| kernel | progress_counter | 32 · 0.24 | 75 · 0.46 | 32 · 0.23 | 29 · 0.20 |
| kernel | fsm_state | 3 · 0.02 | 5 · 0.11 | 3 · 0.02 | 8 · 0.06 |
| kernel | pipe_control |  |  | 2 · 0.01 | 2 · 0.01 |
| **kernel** | **all** | **67 · 0.49** | **113 · 0.80** | **70 · 0.49** | **124 · 0.86** |
| datapath | data_pipeline |  | 1728 · 8.04 | 512 · 8.29 | 512 · 8.27 |
| **datapath** | **all** |  | **1728 · 8.04** | **512 · 8.29** | **512 · 8.27** |
| **all** |  | **196 · 1.42** | **1841 · 8.84** | **582 · 8.79** | **636 · 9.12** |

**vecmul**: flops · pJ per cycle

| layer | role | forge | HLS unopt | HLS opt | HLS dace |
|---|---|---|---|---|---|
| interface | csr_setting | 32 · 0.23 |  |  |  |
| interface | csr_start | 32 · 0.23 |  |  |  |
| interface | csr_readback | 33 · 0.24 |  |  |  |
| interface | perf_counter | 32 · 0.24 |  |  |  |
| **interface** | **all** | **129 · 0.93** |  |  |  |
| kernel | setting_latch | 32 · 0.23 | 33 · 0.23 | 33 · 0.23 | 29 · 0.20 |
| kernel | derived_setting |  |  |  | 56 · 0.39 |
| kernel | progress_counter | 32 · 0.24 | 75 · 0.46 | 32 · 0.23 | 29 · 0.20 |
| kernel | fsm_state | 3 · 0.02 | 5 · 0.10 | 3 · 0.02 | 8 · 0.06 |
| kernel | pipe_control |  |  | 2 · 0.01 | 2 · 0.01 |
| **kernel** | **all** | **67 · 0.49** | **113 · 0.79** | **70 · 0.49** | **124 · 0.86** |
| datapath | data_pipeline |  | 1728 · 8.25 | 1024 · 14.69 | 1024 · 14.65 |
| **datapath** | **all** |  | **1728 · 8.25** | **1024 · 14.69** | **1024 · 14.65** |
| **all** |  | **196 · 1.42** | **1841 · 9.05** | **1094 · 15.19** | **1148 · 15.51** |

**vsum**: flops · pJ per cycle

| layer | role | forge | HLS unopt | HLS opt |
|---|---|---|---|---|
| interface | csr_setting | 64 · 0.46 |  |  |
| interface | csr_start | 32 · 0.23 |  |  |
| interface | csr_readback | 33 · 0.24 |  |  |
| interface | perf_counter | 32 · 0.24 |  |  |
| **interface** | **all** | **161 · 1.16** |  |  |
| kernel | setting_latch | 64 · 0.46 | 66 · 0.46 | 66 · 0.46 |
| kernel | progress_counter | 64 · 0.47 | 136 · 0.85 | 64 · 0.46 |
| kernel | fsm_state | 3 · 0.02 | 5 · 0.13 | 3 · 0.02 |
| kernel | pipe_control | 1 · 0.01 | 1 · 0.01 | 3 · 0.02 |
| **kernel** | **all** | **132 · 0.96** | **208 · 1.44** | **136 · 0.96** |
| datapath | data_pipeline |  | 576 · 2.43 | 384 · 3.67 |
| datapath | data_state | 64 · 1.13 | 128 · 0.71 | 64 · 0.62 |
| **datapath** | **all** | **64 · 1.13** | **704 · 3.14** | **448 · 4.29** |
| **all** |  | **357 · 3.25** | **912 · 4.58** | **584 · 5.25** |

**dot**: flops · pJ per cycle

| layer | role | dot 2 | dot 3 | dot 4 | dot 5 | dot 6 | HLS unopt | HLS opt |
|---|---|---|---|---|---|---|---|---|
| interface | csr_setting | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 |  |  |
| interface | csr_start | 32 · 0.23 | 32 · 0.23 | 32 · 0.23 | 32 · 0.23 | 32 · 0.23 |  |  |
| interface | csr_readback | 33 · 0.24 | 33 · 0.24 | 33 · 0.24 | 33 · 0.24 | 33 · 0.24 |  |  |
| interface | perf_counter | 32 · 0.24 | 32 · 0.24 | 32 · 0.24 | 32 · 0.23 | 32 · 0.23 |  |  |
| **interface** | **all** | **161 · 1.17** | **161 · 1.18** | **161 · 1.18** | **161 · 1.16** | **161 · 1.17** |  |  |
| kernel | setting_latch | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 | 64 · 0.46 | 66 · 0.46 | 66 · 0.46 |
| kernel | derived_setting | 32 · 0.23 | 32 · 0.23 |  |  |  |  |  |
| kernel | progress_counter | 96 · 0.70 | 96 · 0.71 | 96 · 0.69 | 99 · 0.72 | 99 · 0.71 | 136 · 0.84 | 64 · 0.45 |
| kernel | fsm_state | 3 · 0.02 | 3 · 0.02 | 3 · 0.02 | 3 · 0.02 | 3 · 0.02 | 6 · 0.13 | 3 · 0.02 |
| kernel | pipe_control | 2 · 0.01 | 1 · 0.01 | 2 · 0.01 | 2 · 0.01 | 3 · 0.02 | 1 · 0.01 | 7 · 0.05 |
| **kernel** | **all** | **197 · 1.42** | **196 · 1.43** | **165 · 1.19** | **168 · 1.21** | **169 · 1.22** | **209 · 1.44** | **140 · 0.98** |
| datapath | data_pipeline | 512 · 5.16 |  |  |  | 512 · 3.56 | 1216 · 5.21 | 1664 · 20.72 |
| datapath | data_state | 64 · 1.12 | 64 · 1.12 | 576 · 5.98 | 576 · 5.63 | 576 · 5.52 | 128 · 0.64 | 64 · 0.61 |
| **datapath** | **all** | **576 · 6.27** | **64 · 1.12** | **576 · 5.98** | **576 · 5.63** | **1088 · 9.08** | **1344 · 5.85** | **1728 · 21.33** |
| **all** |  | **934 · 8.86** | **421 · 3.72** | **902 · 8.35** | **905 · 8.00** | **1418 · 11.47** | **1553 · 7.29** | **1868 · 22.31** |

## b. Per layer across W, both technologies

**vecadd, nangate45**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 129 · 0.92 | 129 · 0.92 | 129 · 0.93 | 129 · 0.93 | 129 · 0.93 | 129 · 0.94 |
| forge | kernel | 67 · 0.48 | 67 · 0.48 | 67 · 0.48 | 67 · 0.49 | 67 · 0.49 | 67 · 0.49 |
| HLS unopt | kernel | 67 · 0.46 | 107 · 0.76 | 110 · 0.78 | 113 · 0.80 | 116 · 0.82 | 119 · 0.83 |
| HLS unopt | datapath |  | 576 · 3.22 | 960 · 4.86 | 1728 · 8.04 | 3264 · 14.34 | 6336 · 26.70 |
| HLS opt | kernel | 70 · 0.48 | 70 · 0.49 | 70 · 0.49 | 70 · 0.49 | 70 · 0.50 | 70 · 0.50 |
| HLS opt | datapath | 64 · 1.04 | 128 · 2.07 | 256 · 4.14 | 512 · 8.29 | 1024 · 16.45 | 2048 · 32.51 |
| HLS dace | kernel | 99 · 0.68 | 99 · 0.68 | 128 · 0.88 | 124 · 0.86 | 120 · 0.83 | 116 · 0.80 |
| HLS dace | datapath | 64 · 1.04 | 128 · 2.07 | 256 · 4.13 | 512 · 8.27 | 1024 · 16.35 | 2048 · 32.15 |

**vecmul, nangate45**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 129 · 0.92 | 129 · 0.92 | 129 · 0.93 | 129 · 0.93 | 129 · 0.93 | 129 · 0.94 |
| forge | kernel | 67 · 0.48 | 67 · 0.48 | 67 · 0.48 | 67 · 0.49 | 67 · 0.49 | 67 · 0.49 |
| HLS unopt | kernel | 68 · 0.47 | 107 · 0.76 | 110 · 0.77 | 113 · 0.79 | 116 · 0.82 | 119 · 0.84 |
| HLS unopt | datapath |  | 576 · 3.45 | 960 · 5.08 | 1728 · 8.25 | 3264 · 14.57 | 6336 · 26.94 |
| HLS opt | kernel | 70 · 0.48 | 70 · 0.49 | 70 · 0.49 | 70 · 0.49 | 70 · 0.50 | 70 · 0.50 |
| HLS opt | datapath | 128 · 1.85 | 256 · 3.71 | 512 · 7.39 | 1024 · 14.69 | 2048 · 29.37 | 4096 · 58.09 |
| HLS dace | kernel | 99 · 0.68 | 99 · 0.68 | 128 · 0.88 | 124 · 0.86 | 120 · 0.83 | 116 · 0.80 |
| HLS dace | datapath | 128 · 1.85 | 256 · 3.71 | 512 · 7.38 | 1024 · 14.65 | 2048 · 29.20 | 4096 · 57.46 |

**vsum, nangate45**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 161 · 1.15 | 161 · 1.15 | 161 · 1.16 | 161 · 1.16 | 161 · 1.16 | 161 · 1.17 |
| forge | kernel | 132 · 0.95 | 132 · 0.95 | 132 · 0.96 | 132 · 0.96 | 132 · 0.96 | 132 · 0.97 |
| forge | datapath | 64 · 1.14 | 64 · 1.11 | 64 · 1.11 | 64 · 1.13 | 64 · 1.11 | 64 · 1.11 |
| HLS unopt | kernel | 198 · 1.35 | 204 · 1.40 | 206 · 1.41 | 208 · 1.44 | 210 · 1.48 | 212 · 1.50 |
| HLS unopt | datapath | 64 · 0.43 | 320 · 1.71 | 448 · 2.19 | 704 · 3.14 | 1216 · 5.03 | 2240 · 8.83 |
| HLS opt | kernel | 136 · 0.93 | 136 · 0.94 | 136 · 0.95 | 136 · 0.96 | 138 · 0.98 | 138 · 0.99 |
| HLS opt | datapath | 128 · 1.25 | 192 · 1.85 | 320 · 3.08 | 448 · 4.29 | 832 · 7.90 | 1728 · 16.22 |
| HLS dace | kernel | 102 · 0.70 |  |  |  |  |  |
| HLS dace | datapath | 128 · 1.73 |  |  |  |  |  |

**dot, nangate45**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| dot 2 | interface | 161 · 1.16 | 161 · 1.17 | 161 · 1.17 | 161 · 1.17 | 161 · 1.18 | 161 · 1.17 |
| dot 2 | kernel | 197 · 1.40 | 197 · 1.41 | 197 · 1.42 | 197 · 1.42 | 197 · 1.43 | 197 · 1.43 |
| dot 2 | datapath | 128 · 1.76 | 192 · 2.41 | 320 · 3.69 | 576 · 6.27 | 1088 · 11.35 | 2112 · 21.45 |
| dot 3 | interface | 161 · 1.16 | 161 · 1.17 | 161 · 1.17 | 161 · 1.18 | 161 · 1.18 | 161 · 1.18 |
| dot 3 | kernel | 196 · 1.41 | 196 · 1.41 | 196 · 1.42 | 196 · 1.43 | 196 · 1.43 | 196 · 1.44 |
| dot 3 | datapath | 64 · 1.13 | 64 · 1.12 | 64 · 1.12 | 64 · 1.12 | 64 · 1.11 | 64 · 1.10 |
| dot 4 | interface | 161 · 1.15 | 161 · 1.15 | 161 · 1.16 | 161 · 1.18 | 161 · 1.16 | 161 · 1.17 |
| dot 4 | kernel | 165 · 1.18 | 165 · 1.18 | 165 · 1.19 | 165 · 1.19 | 165 · 1.19 | 165 · 1.20 |
| dot 4 | datapath | 128 · 1.11 | 192 · 1.85 | 320 · 3.23 | 576 · 5.98 | 1088 · 11.50 | 2112 · 22.32 |
| dot 5 | interface | 161 · 1.15 | 161 · 1.15 | 161 · 1.16 | 161 · 1.16 | 161 · 1.16 | 161 · 1.18 |
| dot 5 | kernel | 165 · 1.18 | 166 · 1.19 | 167 · 1.20 | 168 · 1.21 | 169 · 1.22 | 170 · 1.22 |
| dot 5 | datapath | 128 · 1.11 | 192 · 1.75 | 320 · 3.09 | 576 · 5.63 | 1088 · 10.36 | 2112 · 18.01 |
| dot 6 | interface | 161 · 1.15 | 161 · 1.15 | 161 · 1.16 | 161 · 1.17 | 161 · 1.17 | 161 · 1.17 |
| dot 6 | kernel | 166 · 1.19 | 167 · 1.20 | 168 · 1.21 | 169 · 1.22 | 170 · 1.22 | 171 · 1.23 |
| dot 6 | datapath | 192 · 1.56 | 320 · 2.66 | 576 · 4.85 | 1088 · 9.08 | 2112 · 16.78 | 4160 · 29.21 |
| HLS unopt | kernel | 200 · 1.34 | 205 · 1.39 | 207 · 1.41 | 209 · 1.44 | 211 · 1.47 | 213 · 1.49 |
| HLS unopt | datapath | 128 · 0.73 | 576 · 3.03 | 832 · 3.97 | 1344 · 5.85 | 2368 · 9.62 | 4416 · 17.21 |
| HLS opt | kernel | 138 · 0.95 | 138 · 0.95 | 138 · 0.96 | 140 · 0.98 | 140 · 0.99 | 140 · 1.00 |
| HLS opt | datapath | 256 · 3.10 | 448 · 5.56 | 832 · 10.45 | 1728 · 21.33 | 3520 · 42.95 | 6592 · 80.09 |

**vecadd, nangate15**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 |
| forge | kernel | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 |
| HLS unopt | kernel | 67 · 0.13 | 107 · 0.22 | 110 · 0.23 | 113 · 0.23 | 116 · 0.24 | 119 · 0.24 |
| HLS unopt | datapath |  | 576 · 1.34 | 960 · 2.08 | 1728 · 3.54 | 3264 · 6.44 | 6336 · 12.25 |
| HLS opt | kernel | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 |
| HLS opt | datapath | 64 · 0.34 | 128 · 0.68 | 256 · 1.36 | 512 · 2.71 | 1024 · 5.39 | 2048 · 10.65 |
| HLS dace | kernel | 99 · 0.19 | 99 · 0.19 | 128 · 0.25 | 124 · 0.24 | 120 · 0.23 | 116 · 0.22 |
| HLS dace | datapath | 64 · 0.34 | 128 · 0.68 | 256 · 1.35 | 512 · 2.71 | 1024 · 5.36 | 2048 · 10.54 |

**vecmul, nangate15**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 | 129 · 0.25 |
| forge | kernel | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 | 67 · 0.13 |
| HLS unopt | kernel | 68 · 0.14 | 107 · 0.22 | 110 · 0.23 | 113 · 0.23 | 116 · 0.24 | 119 · 0.24 |
| HLS unopt | datapath |  | 576 · 1.43 | 960 · 2.17 | 1728 · 3.63 | 3264 · 6.53 | 6336 · 12.33 |
| HLS opt | kernel | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 | 70 · 0.14 |
| HLS opt | datapath | 128 · 0.69 | 256 · 1.38 | 512 · 2.76 | 1024 · 5.48 | 2048 · 10.94 | 4096 · 21.66 |
| HLS dace | kernel | 99 · 0.19 | 99 · 0.19 | 128 · 0.25 | 124 · 0.24 | 120 · 0.23 | 116 · 0.22 |
| HLS dace | datapath | 128 · 0.69 | 256 · 1.38 | 512 · 2.75 | 1024 · 5.47 | 2048 · 10.89 | 4096 · 21.44 |

**vsum, nangate15**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| forge | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| forge | kernel | 132 · 0.26 | 132 · 0.26 | 132 · 0.26 | 132 · 0.26 | 132 · 0.26 | 132 · 0.26 |
| forge | datapath | 64 · 0.36 | 64 · 0.35 | 64 · 0.35 | 64 · 0.35 | 64 · 0.35 | 64 · 0.35 |
| HLS unopt | kernel | 198 · 0.40 | 204 · 0.41 | 206 · 0.41 | 208 · 0.41 | 210 · 0.42 | 212 · 0.43 |
| HLS unopt | datapath | 64 · 0.17 | 320 · 0.74 | 448 · 0.98 | 704 · 1.47 | 1216 · 2.44 | 2240 · 4.38 |
| HLS opt | kernel | 136 · 0.27 | 136 · 0.27 | 136 · 0.27 | 136 · 0.27 | 138 · 0.27 | 138 · 0.27 |
| HLS opt | datapath | 128 · 0.44 | 192 · 0.65 | 320 · 1.09 | 448 · 1.51 | 832 · 2.80 | 1728 · 5.75 |
| HLS dace | kernel | 102 · 0.20 |  |  |  |  |  |
| HLS dace | datapath | 128 · 0.58 |  |  |  |  |  |

**dot, nangate15**: flops · pJ per cycle per layer

| case | layer | W = 1 | W = 2 | W = 4 | W = 8 | W = 16 | W = 32 |
|---|---|---|---|---|---|---|---|
| dot 2 | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| dot 2 | kernel | 197 · 0.39 | 197 · 0.39 | 197 · 0.39 | 197 · 0.39 | 197 · 0.39 | 197 · 0.39 |
| dot 2 | datapath | 128 · 0.58 | 192 · 0.80 | 320 · 1.23 | 576 · 2.12 | 1088 · 3.91 | 2112 · 7.42 |
| dot 3 | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| dot 3 | kernel | 196 · 0.39 | 196 · 0.39 | 196 · 0.39 | 196 · 0.39 | 196 · 0.39 | 196 · 0.39 |
| dot 3 | datapath | 64 · 0.35 | 64 · 0.35 | 64 · 0.35 | 64 · 0.35 | 64 · 0.34 | 64 · 0.34 |
| dot 4 | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| dot 4 | kernel | 165 · 0.32 | 165 · 0.32 | 165 · 0.32 | 165 · 0.32 | 165 · 0.32 | 165 · 0.32 |
| dot 4 | datapath | 128 · 0.35 | 192 · 0.59 | 320 · 1.06 | 576 · 2.00 | 1088 · 3.87 | 2112 · 7.54 |
| dot 5 | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| dot 5 | kernel | 165 · 0.32 | 166 · 0.32 | 167 · 0.32 | 168 · 0.33 | 169 · 0.33 | 170 · 0.33 |
| dot 5 | datapath | 128 · 0.35 | 192 · 0.58 | 320 · 1.04 | 576 · 1.93 | 1088 · 3.62 | 2112 · 6.36 |
| dot 6 | interface | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 | 161 · 0.31 |
| dot 6 | kernel | 166 · 0.32 | 167 · 0.32 | 168 · 0.33 | 169 · 0.33 | 170 · 0.33 | 171 · 0.33 |
| dot 6 | datapath | 192 · 0.47 | 320 · 0.82 | 576 · 1.52 | 1088 · 2.90 | 2112 · 5.56 | 4160 · 10.24 |
| HLS unopt | kernel | 200 · 0.40 | 205 · 0.41 | 207 · 0.41 | 209 · 0.42 | 211 · 0.42 | 213 · 0.42 |
| HLS unopt | datapath | 128 · 0.31 | 576 · 1.35 | 832 · 1.84 | 1344 · 2.81 | 2368 · 4.74 | 4416 · 8.61 |
| HLS opt | kernel | 138 · 0.27 | 138 · 0.27 | 138 · 0.27 | 140 · 0.27 | 140 · 0.27 | 140 · 0.27 |
| HLS opt | datapath | 256 · 1.13 | 448 · 2.03 | 832 · 3.83 | 1728 · 7.78 | 3520 · 15.73 | 6592 · 29.47 |

## c. The registers at W = 8, nangate45

Per point, the registers of each `roles.json` entry together: their names, flops, cone (SYN1's), role, pJ per cycle and what they do. HLS's Verilog: `hls-exercises/rtl/done/<kernel>/<case>_w<W>/`; forge's control: `src/<kernel>/<case>_w8/`.

**`done/vecadd/forge_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1` | 32 | control | csr_setting | 0.229 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.229 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.229 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.235 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_given` | 32 | control | progress_counter | 0.235 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |

**`done/vecadd/unopt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 32 | control | setting_latch | 0.223 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `add_ln9_reg_232` | 32 | control | progress_counter | 0.197 | b + 1, registered: the beat counter's next value, loaded into b at the beat's end. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:78 (load :183) (add_ln9_reg_232)) |
| `l_1_reg_250`, `l_reg_102` | 8 | control | progress_counter | 0.050 | The lane index l of the lane loop (l_reg) and l + 1 (l_1_reg): 0 at each beat, +1 per lane; ends the lane loop at W. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:82 (load :196) (l_1_reg_250)) |
| `zext_ln170_reg_255` | 3 | control | progress_counter | 0.019 | The lane's bit offset l x 64, registered (only bits [8:6] vary): shifts the lane out of the beat and into the output. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:86 (load :204) (zext_ln170_reg_255)) |
| `b_fu_60` | 32 | control | progress_counter | 0.197 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `ap_CS_fsm` | 5 | control | fsm_state | 0.109 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `temp_1_reg_266`, `temp_reg_261` | 128 | data | data_pipeline | 0.743 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `a_reg_237`, `bb_reg_242` | 1024 | data | data_pipeline | 3.939 | An input beat or operand: A_TDATA (a) or B_TDATA (bb) registered as read (unopt W >= 2: the whole beat, unpacked lane by lane; opt W = 1: the single operand). (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:79 (load :182) (a_reg_237)) |
| `add_ln13_reg_271` | 64 | data | data_pipeline | 0.411 | One lane's result (a + b or a x b) in the lane loop, registered before it is merged into the output beat. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:92 (load :190) (add_ln13_reg_271)) |
| `empty_reg_89` | 512 | data | data_pipeline | 2.948 | The output beat being assembled lane by lane (each lane's result shifted into place), written to C_TDATA after the last lane. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:96 (load :166) (empty_reg_89)) |

**`done/vecadd/opt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 32 | control | setting_latch | 0.223 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `b_fu_76` | 32 | control | progress_counter | 0.230 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `ap_CS_fsm` | 3 | control | fsm_state | 0.021 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `ap_enable_reg_pp0_iter0`, `ap_enable_reg_pp0_iter1` | 2 | control | pipe_control | 0.014 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `add_ln13_1_reg_358`, `add_ln13_2_reg_363`, `add_ln13_3_reg_368`, `add_ln13_4_reg_373`, `add_ln13_5_reg_378`, `add_ln13_6_reg_383`, … (8 registers) | 512 | data | data_pipeline | 8.291 | A lane result (vecadd: a + b) registered before it is written to C_TDATA. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:82 (load :201) (add_ln13_1_reg_358)) |

**`done/vecadd/dace_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 28 | control | setting_latch | 0.195 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `N_reg_64` | 28 | control | derived_setting | 0.195 | N = loop_count x W, the element count, computed and kept at start for DaCe's loop (its low log2 W bits constant 0). (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:67 (load :158) (N_reg_64)) |
| `grp_module_vecadd_0_0_fu_40/add_ln19_reg_49` | 28 | control | derived_setting | 0.194 | DaCe's loop bound N - W + 1 (N - 1 at W = 2, N - 7 at W = 8), computed at start and compared with the element index i0. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0.v:58 (load :124) (add_ln19_reg_49)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/p_i0_fu_66` | 29 | control | progress_counter | 0.196 | DaCe's element index i0: 0 at start, + W per beat (+1 at W = 1); compared with the loop bound. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:85 (load :173) (p_i0_fu_66)) |
| `ap_CS_fsm`, `grp_module_vecadd_0_0_fu_40/ap_CS_fsm` | 5 | control | fsm_state | 0.035 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32_ap_start_reg`, `grp_module_vecadd_0_0_fu_40_ap_start_reg` | 2 | control | fsm_state | 0.014 | The start of a sub-module (DaCe's nested function or Vitis's loop module): set by the parent's FSM, cleared when the child is ready. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0.v:68 (grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32_ap_start_reg)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/flow_control_loop_pipe_sequential_init_U/ap_done_cache` | 1 | control | fsm_state | 0.007 | Vitis's loop-module done, kept until the next start: tells the parent the loop finished. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_flow_control_loop_pipe_sequential_init.v:45 (ap_done_cache)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/ap_enable_reg_pp0_iter1` | 1 | control | pipe_control | 0.007 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/flow_control_loop_pipe_sequential_init_U/ap_loop_init_int` | 1 | control | pipe_control | 0.007 | Vitis's loop-module first-iteration flag: set at start, cleared after the first iteration; selects the loop variable's initial value. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_flow_control_loop_pipe_sequential_init.v:43 (ap_loop_init_int)) |
| `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_1_reg_348`, `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_2_reg_353`, `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_3_reg_358`, `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_4_reg_363`, `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_5_reg_368`, `grp_module_vecadd_0_0_fu_40/grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/add_ln414_6_reg_373`, … (8 registers) | 512 | data | data_pipeline | 8.265 | A lane result a + b (dace::vec's operator+), registered before it is written to C_TDATA. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:72 (load :182) (add_ln414_1_reg_348)) |

**`done/vecmul/forge_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1` | 32 | control | csr_setting | 0.229 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.229 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.229 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.235 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_given` | 32 | control | progress_counter | 0.235 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |

**`done/vecmul/unopt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 32 | control | setting_latch | 0.223 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `add_ln9_reg_232` | 32 | control | progress_counter | 0.197 | b + 1, registered: the beat counter's next value, loaded into b at the beat's end. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:78 (load :183) (add_ln9_reg_232)) |
| `l_1_reg_250`, `l_reg_102` | 8 | control | progress_counter | 0.050 | The lane index l of the lane loop (l_reg) and l + 1 (l_1_reg): 0 at each beat, +1 per lane; ends the lane loop at W. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:82 (load :196) (l_1_reg_250)) |
| `zext_ln170_reg_255` | 3 | control | progress_counter | 0.019 | The lane's bit offset l x 64, registered (only bits [8:6] vary): shifts the lane out of the beat and into the output. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:86 (load :204) (zext_ln170_reg_255)) |
| `b_fu_60` | 32 | control | progress_counter | 0.197 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `ap_CS_fsm` | 5 | control | fsm_state | 0.100 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `temp_1_reg_266`, `temp_reg_261` | 128 | data | data_pipeline | 0.952 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `a_reg_237`, `bb_reg_242` | 1024 | data | data_pipeline | 3.938 | An input beat or operand: A_TDATA (a) or B_TDATA (bb) registered as read (unopt W >= 2: the whole beat, unpacked lane by lane; opt W = 1: the single operand). (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:79 (load :182) (a_reg_237)) |
| `mul_ln13_reg_271` | 64 | data | data_pipeline | 0.411 | One lane's result (a + b or a x b) in the lane loop, registered before it is merged into the output beat. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:92 (load :190) (add_ln13_reg_271)) |
| `empty_reg_89` | 512 | data | data_pipeline | 2.952 | The output beat being assembled lane by lane (each lane's result shifted into place), written to C_TDATA after the last lane. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:96 (load :166) (empty_reg_89)) |

**`done/vecmul/opt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 32 | control | setting_latch | 0.223 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `b_fu_76` | 32 | control | progress_counter | 0.230 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `ap_CS_fsm` | 3 | control | fsm_state | 0.021 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `ap_enable_reg_pp0_iter0`, `ap_enable_reg_pp0_iter1` | 2 | control | pipe_control | 0.014 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `temp_10_reg_395`, `temp_11_reg_400`, `temp_12_reg_405`, `temp_13_reg_410`, `temp_14_reg_415`, `temp_15_reg_420`, … (16 registers) | 1024 | data | data_pipeline | 14.694 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |

**`done/vecmul/dace_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `loop_count_preg` | 28 | control | setting_latch | 0.195 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `loop_count_ap_vld_preg` | 1 | control | setting_latch | 0.007 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `N_reg_64` | 28 | control | derived_setting | 0.195 | N = loop_count x W, the element count, computed and kept at start for DaCe's loop (its low log2 W bits constant 0). (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:67 (load :158) (N_reg_64)) |
| `grp_module_vecmul_0_0_fu_40/add_ln19_reg_49` | 28 | control | derived_setting | 0.194 | DaCe's loop bound N - W + 1 (N - 1 at W = 2, N - 7 at W = 8), computed at start and compared with the element index i0. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0.v:58 (load :124) (add_ln19_reg_49)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/p_i0_fu_66` | 29 | control | progress_counter | 0.196 | DaCe's element index i0: 0 at start, + W per beat (+1 at W = 1); compared with the loop bound. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:85 (load :173) (p_i0_fu_66)) |
| `ap_CS_fsm`, `grp_module_vecmul_0_0_fu_40/ap_CS_fsm` | 5 | control | fsm_state | 0.035 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32_ap_start_reg`, `grp_module_vecmul_0_0_fu_40_ap_start_reg` | 2 | control | fsm_state | 0.014 | The start of a sub-module (DaCe's nested function or Vitis's loop module): set by the parent's FSM, cleared when the child is ready. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0.v:68 (grp_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1_fu_32_ap_start_reg)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/flow_control_loop_pipe_sequential_init_U/ap_done_cache` | 1 | control | fsm_state | 0.007 | Vitis's loop-module done, kept until the next start: tells the parent the loop finished. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_flow_control_loop_pipe_sequential_init.v:45 (ap_done_cache)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/ap_enable_reg_pp0_iter1` | 1 | control | pipe_control | 0.007 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/flow_control_loop_pipe_sequential_init_U/ap_loop_init_int` | 1 | control | pipe_control | 0.007 | Vitis's loop-module first-iteration flag: set at start, cleared after the first iteration; selects the loop variable's initial value. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_flow_control_loop_pipe_sequential_init.v:43 (ap_loop_init_int)) |
| `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_10_reg_385`, `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_11_reg_390`, `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_12_reg_395`, `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_13_reg_400`, `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_14_reg_405`, `grp_module_vecmul_0_0_fu_40/grp_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1_fu_32/temp_15_reg_410`, … (16 registers) | 1024 | data | data_pipeline | 14.650 | A lane operand in DaCe's loop module: one lane of A_TDATA or B_TDATA, held for the multiply. (hls-exercises/rtl/done/vecmul/dace_w8/vecmul_dace_module_vecmul_0_0_Pipeline_VITIS_LOOP_19_1.v:81 (load :272) (temp_10_reg_385)) |

**`done/vsum/forge_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.459 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.229 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.229 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.236 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_t` | 32 | control | setting_latch | 0.232 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_given` | 32 | control | progress_counter | 0.232 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_d` | 32 | control | progress_counter | 0.238 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/acc_v_0` | 1 | control | pipe_control | 0.007 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `dp/blocks_0_4/m/acc` | 64 | data | data_state | 1.129 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |

**`done/vsum/unopt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `len_preg`, `loop_count_preg` | 64 | control | setting_latch | 0.445 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `len_ap_vld_preg`, `loop_count_ap_vld_preg` | 2 | control | setting_latch | 0.014 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `add_ln22_1_reg_281`, `add_ln22_reg_305` | 64 | control | progress_counter | 0.394 | b + 1 or cnt + 1, registered: the beat counter's or the sum's beat count's next value, loaded at the beat's end. (hls-exercises/rtl/done/vsum/unopt_w8/vsum.v:79 (load :223) (add_ln22_1_reg_281)) |
| `l_1_reg_295`, `l_reg_93` | 8 | control | progress_counter | 0.056 | The lane index l of the lane loop (l_reg) and l + 1 (l_1_reg): 0 at each beat, +1 per lane; ends the lane loop at W. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:82 (load :196) (l_1_reg_250)) |
| `b_fu_64` | 32 | control | progress_counter | 0.198 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `cnt_fu_60` | 32 | control | progress_counter | 0.198 | The beats in the sum in progress (cnt): +1 per beat, 0 when a result is written; compared with len. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:97 (load :233) (cnt_fu_80)) |
| `ap_CS_fsm` | 5 | control | fsm_state | 0.127 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `or_ln22_reg_310` | 1 | control | pipe_control | 0.007 | The registered end-of-sum test (cnt + 1 == len or the last beat), and its delayed copy: selects writing the result and clearing acc and cnt. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:75 (load :241) (or_ln22_reg_379)) |
| `temp_reg_300` | 64 | data | data_pipeline | 0.423 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `a_reg_287` | 512 | data | data_pipeline | 2.008 | An input beat or operand: A_TDATA (a) or B_TDATA (bb) registered as read (unopt W >= 2: the whole beat, unpacked lane by lane; opt W = 1: the single operand). (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:79 (load :182) (a_reg_237)) |
| `s_reg_104` | 64 | data | data_state | 0.456 | W >= 2 (unopt): the beat's sum s, accumulated lane by lane (s + lane), 0 at each beat; added to acc after the last lane. (hls-exercises/rtl/done/vsum/unopt_w8/vsum.v:93 (load :214) (s_reg_104)) |
| `acc_fu_56` | 64 | data | data_state | 0.255 | The accumulator acc: acc + s per beat, 0 after each result; feeds the result written to out. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:95 (load :217) (acc_fu_76)) |

**`done/vsum/opt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `len_preg`, `loop_count_preg` | 64 | control | setting_latch | 0.445 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `len_ap_vld_preg`, `loop_count_ap_vld_preg` | 2 | control | setting_latch | 0.014 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `b_fu_84` | 32 | control | progress_counter | 0.227 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `cnt_fu_80` | 32 | control | progress_counter | 0.228 | The beats in the sum in progress (cnt): +1 per beat, 0 when a result is written; compared with len. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:97 (load :233) (cnt_fu_80)) |
| `ap_CS_fsm` | 3 | control | fsm_state | 0.021 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `or_ln22_reg_379` | 1 | control | pipe_control | 0.007 | The registered end-of-sum test (cnt + 1 == len or the last beat), and its delayed copy: selects writing the result and clearing acc and cnt. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:75 (load :241) (or_ln22_reg_379)) |
| `ap_enable_reg_pp0_iter0`, `ap_enable_reg_pp0_iter1` | 2 | control | pipe_control | 0.014 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `temp_1_reg_354`, `temp_4_reg_359`, `temp_5_reg_364`, `temp_7_reg_349` | 256 | data | data_pipeline | 2.436 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `add_ln21_1_reg_369`, `add_ln21_4_reg_374` | 128 | data | data_pipeline | 1.238 | A stage register of the lane tree: a lane product (mul) or a partial sum of lanes (add), and its delayed copy (_pp0_iter*_reg) where the stages are unbalanced. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:88 (load :239) (add_ln21_1_reg_369)) |
| `acc_fu_76` | 64 | data | data_state | 0.621 | The accumulator acc: acc + s per beat, 0 after each result; feeds the result written to out. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:95 (load :217) (acc_fu_76)) |

**`done/dot/forge2_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.459 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.234 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.234 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.235 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_t` | 32 | control | setting_latch | 0.230 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mul_r` | 32 | control | derived_setting | 0.229 | The multiply unit's firing count, computed at START as JOBS x JOB_BEATS (its successor's R times T); the unit stops firing when mul_given reaches it. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:26 (load :67); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mul_given`, `ctrl/ctrl/sum_given` | 64 | control | progress_counter | 0.460 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_d` | 32 | control | progress_counter | 0.235 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_v_0` | 1 | control | pipe_control | 0.007 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mul_sum_occupancy` | 1 | control | pipe_control | 0.007 | A link buffer's occupancy between two units: + on the producer's give, - on the consumer's fire; stalls the producer when full and enables the consumer when not empty. (results/analysis/control/src/dot/forge2_w8/snax_forge_dot_ctrl.sv:32 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:223 (snax-forge 32dbcc6)) |
| `dp/bufs_0_4/m/slots_0_0`, `dp/bufs_0_4/m/slots_0_1`, `dp/bufs_0_4/m/slots_0_2`, `dp/bufs_0_4/m/slots_0_3`, `dp/bufs_0_4/m/slots_0_4`, `dp/bufs_0_4/m/slots_0_5`, … (8 registers) | 512 | data | data_pipeline | 5.156 | A LinkBuffer slot lane (dot 2, 6): holds the producer's beat (dot 2: the W products; dot 6: the W lane sums) from its give until the consumer reads it. (rtl/forge/done/dot/forge2_w8/rtl/sv/LinkBuffer_i64_n8_d1.sv:24 (load :44) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/LinkBuffer.scala:38 (snax-forge 32dbcc6)) |
| `dp/blocks_1_4/m/acc` | 64 | data | data_state | 1.117 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |

**`done/dot/forge3_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.464 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.234 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.234 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.236 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_t` | 32 | control | setting_latch | 0.233 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_r` | 32 | control | setting_latch | 0.230 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mul_r` | 32 | control | derived_setting | 0.229 | The multiply unit's firing count, computed at START as JOBS x JOB_BEATS (its successor's R times T); the unit stops firing when mul_given reaches it. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:26 (load :67); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mul_given`, `ctrl/ctrl/sum_given` | 64 | control | progress_counter | 0.468 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_d` | 32 | control | progress_counter | 0.238 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_v_0` | 1 | control | pipe_control | 0.007 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `dp/blocks_1_4/m/acc` | 64 | data | data_state | 1.122 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |

**`done/dot/forge4_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.464 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.234 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.234 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.235 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_t` | 32 | control | setting_latch | 0.231 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_r` | 32 | control | setting_latch | 0.232 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_given`, `ctrl/ctrl/sum_given` | 64 | control | progress_counter | 0.459 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_d` | 32 | control | progress_counter | 0.235 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_v_0`, `ctrl/ctrl/sum_v_0` | 2 | control | pipe_control | 0.014 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `dp/blocks_1_4/m/acc` | 64 | data | data_state | 0.462 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |
| `dp/blocks_0_4/m/s_0`, `dp/blocks_0_4/m/s_1`, `dp/blocks_0_4/m/s_2`, `dp/blocks_0_4/m/s_3`, `dp/blocks_0_4/m/s_4`, `dp/blocks_0_4/m/s_5`, … (8 registers) | 512 | data | data_state | 5.516 | One lane's running sum in the MAC lanes (dot 4, 5, 6): loads a x b on `first`, else s + a x b, on fire; read by the sum unit (directly or through the link buffer). (rtl/forge/done/dot/forge4_w8/rtl/sv/Mac_i64xi64_i64_i64_n8_acc.sv:33 (load :70) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/Mac.scala:79 (snax-forge 32dbcc6)) |

**`done/dot/forge5_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.459 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.229 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.229 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.235 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_t` | 32 | control | setting_latch | 0.229 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_given`, `ctrl/ctrl/sum_given` | 64 | control | progress_counter | 0.458 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_d` | 32 | control | progress_counter | 0.235 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_lane` | 3 | control | progress_counter | 0.022 | The serial sum's lane index (span > 1): cleared when the unit fires, +1 on each read; selects the lane SerialAccumulate adds next (io_units_*_lane). (results/analysis/control/src/dot/forge6_w8/snax_forge_dot_ctrl.sv:34 (load :101); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:215 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_v_0`, `ctrl/ctrl/sum_v_0` | 2 | control | pipe_control | 0.014 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `dp/blocks_1_4/m/acc` | 64 | data | data_state | 0.474 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |
| `dp/blocks_0_4/m/s_0`, `dp/blocks_0_4/m/s_1`, `dp/blocks_0_4/m/s_2`, `dp/blocks_0_4/m/s_3`, `dp/blocks_0_4/m/s_4`, `dp/blocks_0_4/m/s_5`, … (8 registers) | 512 | data | data_state | 5.161 | One lane's running sum in the MAC lanes (dot 4, 5, 6): loads a x b on `first`, else s + a x b, on fire; read by the sum unit (directly or through the link buffer). (rtl/forge/done/dot/forge4_w8/rtl/sv/Mac_i64xi64_i64_i64_n8_acc.sv:33 (load :70) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/Mac.scala:79 (snax-forge 32dbcc6)) |

**`done/dot/forge6_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `csr/regs_1`, `csr/regs_2` | 64 | control | csr_setting | 0.459 | A read-write CSR (JOBS at offset 1, JOB_BEATS at offset 2 when the group has a fold): written over the CSR bus before START, given to ctrl as io_starts_*_bits_* when START is written, read back over the bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:23 (load :54); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/regs_0` | 32 | control | csr_start | 0.234 | START, offset 0 (accelerator.json): the word last written to START. The start pulse comes from the write itself (address 0, bit 0), so this register only answers a read of START. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:22 (load :52); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:48 (snax-forge 32dbcc6)) |
| `csr/answer` | 32 | control | csr_readback | 0.234 | The CSR read buffer: loads every read's data, keeps it while rsp is not ready; drives csr_rsp_data_o when answerKept. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:31 (load :59); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:70 (snax-forge 32dbcc6)) |
| `csr/answerKept` | 1 | control | csr_readback | 0.007 | Set when a read's response was not taken (rsp valid, not ready); holds req.ready low and selects answer as the response. (results/analysis/control/src/dot/forge3_w8/snax_forge_csr.sv:30 (load :57); hw/chisel/src/main/scala/snax/forge/shell/AccCsr.scala:69 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/counter` | 32 | control | perf_counter | 0.234 | COUNTER: cleared by an accepted START, +1 every busy cycle, held after the run; read only by the CSR bus (io_counter). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:40 (load :90); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:97 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_t` | 32 | control | setting_latch | 0.229 | A unit's T, the beats per result, latched from JOB_BEATS (io_start_bits_beats_0) at START; compared with the unit's beat digit _d to end each result. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:24 (load :65); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:193 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_r` | 32 | control | setting_latch | 0.229 | The last unit's result count R, latched from JOBS (io_start_bits_jobs) at START; the run ends when its _given reaches it. For vecadd and vecmul (T = 1) it is the run's beat count. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:25 (load :66); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:201 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_given`, `ctrl/ctrl/sum_given` | 64 | control | progress_counter | 0.458 | A unit's results given so far (firings for a T = 1 unit): cleared at START, +1 on each result; compared with the unit's R. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:29 (load :82); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:212 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_d` | 32 | control | progress_counter | 0.234 | A unit's beat digit: the beat within the current result, cleared at START and at each result's last beat; drives the datapath's `first` (restart the accumulation). (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:28 (load :79); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:208 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/sum_lane` | 3 | control | progress_counter | 0.022 | The serial sum's lane index (span > 1): cleared when the unit fires, +1 on each read; selects the lane SerialAccumulate adds next (io_units_*_lane). (results/analysis/control/src/dot/forge6_w8/snax_forge_dot_ctrl.sv:34 (load :101); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:215 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/busy` | 1 | control | fsm_state | 0.007 | The group's busy bit: set by an accepted, non-empty START, cleared at the last result; gates every unit's firing; STATUS bit 0 and the busy pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:23 (load :63); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:191 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/done_1` | 1 | control | fsm_state | 0.007 | STATUS's sticky done bit: set by the done pulse, cleared by the next accepted START; read only by the CSR bus. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:39 (load :86); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:96 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/io_done_REG` | 1 | control | fsm_state | 0.007 | The done pulse, registered: high the cycle after the run's last result (or after an empty START); drives the <group>_done_o pin. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:41 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupCtrl.scala:112 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_v_0`, `ctrl/ctrl/sum_v_0` | 2 | control | pipe_control | 0.015 | A unit's pipeline valid slot (latency L slots, here 1): set when the unit fires and gives a result, held while frozen; the head is the unit's output valid. (results/analysis/control/src/dot/forge3_w8/snax_forge_dot_ctrl.sv:30 (load :85); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:214 (snax-forge 32dbcc6)) |
| `ctrl/ctrl/mac_sum_occupancy` | 1 | control | pipe_control | 0.007 | A link buffer's occupancy between two units: + on the producer's give, - on the consumer's fire; stalls the producer when full and enables the consumer when not empty. (results/analysis/control/src/dot/forge2_w8/snax_forge_dot_ctrl.sv:32 (load :91); hw/chisel/src/main/scala/snax/forge/ctrl/GroupRule.scala:223 (snax-forge 32dbcc6)) |
| `dp/bufs_0_4/m/slots_0_0`, `dp/bufs_0_4/m/slots_0_1`, `dp/bufs_0_4/m/slots_0_2`, `dp/bufs_0_4/m/slots_0_3`, `dp/bufs_0_4/m/slots_0_4`, `dp/bufs_0_4/m/slots_0_5`, … (8 registers) | 512 | data | data_pipeline | 3.563 | A LinkBuffer slot lane (dot 2, 6): holds the producer's beat (dot 2: the W products; dot 6: the W lane sums) from its give until the consumer reads it. (rtl/forge/done/dot/forge2_w8/rtl/sv/LinkBuffer_i64_n8_d1.sv:24 (load :44) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/LinkBuffer.scala:38 (snax-forge 32dbcc6)) |
| `dp/blocks_1_4/m/acc` | 64 | data | data_state | 0.474 | The accumulator of TreeAccumulate (vsum, dot 2, 3, 4) or SerialAccumulate (dot 5, 6): loads beat on `first`, else acc + beat, on fire; drives the result port. (rtl/forge/done/dot/forge3_w8/rtl/sv/TreeAccumulate_i64_i64_n8.sv:18 (load :27) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/TreeAccumulate.scala:46, hw/chisel/src/main/scala/snax/forge/datapath/SerialAccumulate.scala:46 (snax-forge 32dbcc6)) |
| `dp/blocks_0_4/m/s_0`, `dp/blocks_0_4/m/s_1`, `dp/blocks_0_4/m/s_2`, `dp/blocks_0_4/m/s_3`, `dp/blocks_0_4/m/s_4`, `dp/blocks_0_4/m/s_5`, … (8 registers) | 512 | data | data_state | 5.043 | One lane's running sum in the MAC lanes (dot 4, 5, 6): loads a x b on `first`, else s + a x b, on fire; read by the sum unit (directly or through the link buffer). (rtl/forge/done/dot/forge4_w8/rtl/sv/Mac_i64xi64_i64_i64_n8_acc.sv:33 (load :70) (bundle, not committed); hw/chisel/src/main/scala/snax/forge/datapath/Mac.scala:79 (snax-forge 32dbcc6)) |

**`done/dot/unopt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `len_preg`, `loop_count_preg` | 64 | control | setting_latch | 0.445 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `len_ap_vld_preg`, `loop_count_ap_vld_preg` | 2 | control | setting_latch | 0.014 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `add_ln22_1_reg_302`, `add_ln22_reg_336` | 64 | control | progress_counter | 0.394 | b + 1 or cnt + 1, registered: the beat counter's or the sum's beat count's next value, loaded at the beat's end. (hls-exercises/rtl/done/vsum/unopt_w8/vsum.v:79 (load :223) (add_ln22_1_reg_281)) |
| `l_1_reg_321`, `l_reg_101` | 8 | control | progress_counter | 0.050 | The lane index l of the lane loop (l_reg) and l + 1 (l_1_reg): 0 at each beat, +1 per lane; ends the lane loop at W. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:82 (load :196) (l_1_reg_250)) |
| `b_fu_66` | 32 | control | progress_counter | 0.197 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `cnt_fu_62` | 32 | control | progress_counter | 0.197 | The beats in the sum in progress (cnt): +1 per beat, 0 when a result is written; compared with len. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:97 (load :233) (cnt_fu_80)) |
| `ap_CS_fsm` | 6 | control | fsm_state | 0.133 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `or_ln22_reg_341` | 1 | control | pipe_control | 0.007 | The registered end-of-sum test (cnt + 1 == len or the last beat), and its delayed copy: selects writing the result and clearing acc and cnt. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:75 (load :241) (or_ln22_reg_379)) |
| `temp_1_reg_331`, `temp_reg_326` | 128 | data | data_pipeline | 0.934 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `a_reg_308`, `bb_reg_313` | 1024 | data | data_pipeline | 3.931 | An input beat or operand: A_TDATA (a) or B_TDATA (bb) registered as read (unopt W >= 2: the whole beat, unpacked lane by lane; opt W = 1: the single operand). (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:79 (load :182) (a_reg_237)) |
| `mul_ln19_reg_345` | 64 | data | data_pipeline | 0.349 | One lane's product a x b in the lane loop, registered before s + product. (hls-exercises/rtl/done/dot/unopt_w8/dot.v:102 (load :269) (mul_ln19_reg_345)) |
| `s_reg_112` | 64 | data | data_state | 0.388 | W >= 2 (unopt): the beat's sum s, accumulated lane by lane (s + lane), 0 at each beat; added to acc after the last lane. (hls-exercises/rtl/done/vsum/unopt_w8/vsum.v:93 (load :214) (s_reg_104)) |
| `acc_fu_58` | 64 | data | data_state | 0.248 | The accumulator acc: acc + s per beat, 0 after each result; feeds the result written to out. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:95 (load :217) (acc_fu_76)) |

**`done/dot/opt_w8`**

| registers | flops | cone | role | pJ/cycle | what it does (where) |
|---|---|---|---|---|---|
| `len_preg`, `loop_count_preg` | 64 | control | setting_latch | 0.445 | A run-time pin latched at start (ap_vld): loaded when <pin>_ap_vld is high, the driver's one-cycle pulse with the accepted start; read by the loop's end test. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:61 (load :151) (loop_count_preg)) |
| `len_ap_vld_preg`, `loop_count_ap_vld_preg` | 2 | control | setting_latch | 0.014 | The pin's valid bit, kept: set by <pin>_ap_vld, cleared at ap_done; selects the latched value over the port. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:63 (load :141) (loop_count_ap_vld_preg)) |
| `b_fu_86` | 32 | control | progress_counter | 0.227 | The beat counter b: 0 at start, +1 per beat; compared with loop_count to end the loop. (hls-exercises/rtl/done/vecadd/opt_w8/vecadd.v:98 (load :195) (b_fu_76)) |
| `cnt_fu_82` | 32 | control | progress_counter | 0.226 | The beats in the sum in progress (cnt): +1 per beat, 0 when a result is written; compared with len. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:97 (load :233) (cnt_fu_80)) |
| `ap_CS_fsm` | 3 | control | fsm_state | 0.021 | Vitis's FSM state (one-hot): idle, the loop, done; drives ap_idle, ap_ready, ap_done. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace.v:59 (load :116) (ap_CS_fsm)) |
| `icmp_ln22_1_reg_538` | 1 | control | pipe_control | 0.007 | The registered last-beat test b + 1 == loop_count, carried to the stage that writes the result and ends the loop. (hls-exercises/rtl/done/dot/opt_w8/dot.v:110 (load :404) (icmp_ln22_1_reg_538)) |
| `or_ln22_reg_583`, `or_ln22_reg_583_pp0_iter2_reg` | 2 | control | pipe_control | 0.014 | The registered end-of-sum test (cnt + 1 == len or the last beat), and its delayed copy: selects writing the result and clearing acc and cnt. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:75 (load :241) (or_ln22_reg_379)) |
| `ap_enable_reg_pp0_iter0`, `ap_enable_reg_pp0_iter1`, `ap_enable_reg_pp0_iter2`, `ap_enable_reg_pp0_iter3` | 4 | control | pipe_control | 0.027 | A loop pipeline stage's enable: iter0 set while the loop runs, each later stage the earlier one's delayed; gates that stage's registers. (hls-exercises/rtl/done/vecadd/dace_w8/vecadd_dace_module_vecadd_0_0_Pipeline_VITIS_LOOP_19_1.v:55 (load :165) (ap_enable_reg_pp0_iter1)) |
| `temp_10_reg_508`, `temp_11_reg_513`, `temp_12_reg_518`, `temp_13_reg_523`, `temp_14_reg_528`, `temp_15_reg_533`, … (16 registers) | 1024 | data | data_pipeline | 14.610 | A lane operand: one lane of A_TDATA or B_TDATA (opt: straight from the port; unopt: shifted out of the registered beat), held for the next stage's add or multiply. (hls-exercises/rtl/done/vecadd/unopt_w8/vecadd.v:90 (load :202) (temp_1_reg_266)) |
| `add_ln21_2_reg_587`, `add_ln21_3_reg_592`, `mul_ln21_1_reg_548`, `mul_ln21_2_reg_553`, `mul_ln21_3_reg_558`, `mul_ln21_4_reg_563`, … (10 registers) | 640 | data | data_pipeline | 6.108 | A stage register of the lane tree: a lane product (mul) or a partial sum of lanes (add), and its delayed copy (_pp0_iter*_reg) where the stages are unbalanced. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:88 (load :239) (add_ln21_1_reg_369)) |
| `acc_fu_78` | 64 | data | data_state | 0.614 | The accumulator acc: acc + s per beat, 0 after each result; feeds the result written to out. (hls-exercises/rtl/done/vsum/opt_w8/vsum.v:95 (load :217) (acc_fu_76)) |

## d. Cone against layer, and unclear registers

A register disagrees when its role's layer is datapath and SYN1's cone is control, or the other way round. 0 register rows disagree.

`unclear` registers: 0.
