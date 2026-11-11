# forge before and after CTRL2 (snax-forge D168)

csr excludes `<tag>_peripherals` (BUSY_COUNTER), snax-forge D168.

Part of [the comparison](README.md). The only page that keeps forge's numbers from before CTRL2: CSYN1 Part A (X64, snax-forge `e8bb93e` and `f9764d5`) against CTRL2 R5 (snax-forge `3c7ea00`), nangate45, n2048, the 70 forge points at W = 1 to 16, every one resynthesized and powered again. Run note: [`2026-11-11_ctrl2_r5.md`](../forge/runs/2026-11-11_ctrl2_r5.md).

**What changed.** snax-forge D168 keeps the settings (JOBS, each JOB_BEATS, the scalars) only in `<tag>_csr`, which holds a write to a busy group's START or settings until the cycle after its run ends, and the control unit `<tag>_<group>_ctrl` reads them live: an elementwise ctrl loses its 32-bit copy of JOBS (66 to 34 flops, 711 to 438 µm², 0.51 to 0.27 pJ per cycle at W = 1), a fold also its copy of JOB_BEATS (vsum and dot 3 131 to 67 flops, 1,294 to 760 µm²; dot 2 196 to 132, dot 4 164 to 100). Over the 70 points the ctrl's area falls 28 to 41 % and its energy per cycle 33 to 49 %; its flops equal snax-forge's `estimate/bits.py` count at every point. BUSY_COUNTER moved out of the settings into `<tag>_peripherals`, a child of the csr (279 µm², 313 at dot 4, 5 and 6 at W = 8 where DC maps it larger; 0.24 to 0.25 pJ per cycle), which the reported csr leaves out (X65): the csr falls 22 to 36 % (850 to 548 µm² for an elementwise unit, 1,107 to 794 for a fold, 1,375 to 1,073 for axpy), the peripherals and 22 to 33 µm² of the csr's own logic (at those three dot points the whole csr is 1,109 µm², so 1,103 to 796 without peripherals). The datapath is within 0.05 % and every window is the same cycle count as before. ctrl + datapath falls 0.3 to 35 % in area (relu at W = 1: 780 to 507 µm²) and 0.2 to 25 % in energy per element (relu at W = 1: 0.958 to 0.714 pJ). On X63's basis, forge's total without csr, BUSY_COUNTER is outside the total before and inside it after, so an elementwise unit stays where it was (area +0.0 to +0.9 %, energy −0.9 to +0.1 %) and a fold gains its JOB_BEATS copy (rowsum and vsum at W = 1: −11.9 % in area, −8.5 % in energy). Against the HLS cases, 9 verdicts turn in forge's favour and none against it: vsum and rowsum now beat XLS on energy at W = 4 and on area at W = 8, dot 3 beats XLS on area at W = 8, and at W = 2 dot 4 and 5 beat Vitis opt on energy and dot 2 and 6 beat XLS on energy.

**How to read the tables.** A cell is before → after, one value where the two agree at the table's precision. csr before is the whole csr, after the csr without its peripherals. The two right-hand columns compare forge's total without csr (before: total minus the whole csr; after: total minus the csr without peripherals, BUSY_COUNTER in) with each HLS case at the same W, in energy per element and in area; a changed verdict is shown before → **after**. ctrl pJ/cycle is PT's energy of the ctrl instance per cycle of the window; ctrl + datapath pJ/element is the two parts' energy over the window divided by 2048.

<!-- gen:tables -->
### vecadd (done)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 850 → 548 | 713 → 438 | 0.509 → 0.265 | 66 → 34 | 270 | 982 → 708 | 1.28 → 1.04 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 2 | 850 → 548 | 713 → 438 | 0.51 → 0.269 | 66 → 34 | 539 | 1,252 → 978 | 1.03 → 0.908 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 4 | 850 → 548 | 713 → 438 | 0.519 → 0.273 | 66 → 34 | 1,079 | 1,792 → 1,517 | 0.903 → 0.841 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 8 | 850 → 548 | 713 → 438 | 0.521 → 0.276 | 66 → 34 | 2,158 | 2,870 → 2,596 | 0.841 → 0.81 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 16 | 850 → 548 | 713 → 438 | 0.53 → 0.28 | 66 → 34 | 4,316 | 5,028 → 4,754 | 0.805 → 0.79 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |

### vecmul (done)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 850 → 548 | 713 → 438 | 0.509 → 0.265 | 66 → 34 | 6,913 | 7,625 → 7,351 | 11.8 → 11.6 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 2 | 850 → 548 | 713 → 438 | 0.51 → 0.269 | 66 → 34 | 13,825 | 14,538 → 14,263 | 11.6 → 11.4 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 4 | 850 → 548 | 713 → 438 | 0.519 → 0.273 | 66 → 34 | 27,650 | 28,363 → 28,089 | 11.4 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 8 | 850 → 548 | 713 → 438 | 0.521 → 0.276 | 66 → 34 | 55,300 | 56,013 → 55,739 | 11.3 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 16 | 850 → 548 | 713 → 438 | 0.53 → 0.28 | 66 → 34 | 110,601 | 111,313 → 111,039 | 11.3 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |

### vsum (done)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 1,107 → 794 | 1,295 → 761 | 0.969 → 0.495 | 131 → 67 | 841 | 2,136 → 1,602 | 2.85 → 2.38 | beats Vitis opt, Bambu; loses to Vitis dace, XLS | beats Vitis opt, Bambu; loses to Vitis dace, XLS |
| forge | 2 | 1,107 → 794 | 1,294 → 760 | 0.973 → 0.499 | 131 → 67 | 1,107 | 2,401 → 1,868 | 1.62 → 1.39 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |
| forge | 4 | 1,107 → 794 | 1,294 → 760 | 0.978 → 0.503 | 131 → 67 | 1,644 → 1,643 | 2,937 → 2,404 | 0.989 → 0.87 | beats Vitis opt, Bambu; loses to XLS → **beats Vitis opt, Bambu, XLS** | beats Vitis opt, Bambu; loses to XLS |
| forge | 8 | 1,107 → 794 | 1,294 → 760 | 0.984 → 0.507 | 131 → 67 | 2,713 | 4,007 → 3,473 | 0.674 → 0.614 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu; loses to XLS → **beats Vitis opt, Bambu, XLS** |
| forge | 16 | 1,107 → 794 | 1,294 → 760 | 0.993 → 0.513 | 131 → 67 | 4,849 | 6,144 → 5,610 | 0.513 → 0.482 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |

### dot (done)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge 2 | 1 | 1,107 → 794 | 2,087 → 1,502 | 1.45 → 0.97 | 196 → 132 | 8,215 | 10,302 → 9,717 | 14.9 → 14.4 | beats Vitis dace, Bambu; loses to Vitis opt, XLS | beats Vitis dace, Bambu; loses to Vitis opt, XLS |
| forge 2 | 2 | 1,107 → 794 | 2,086 → 1,501 | 1.46 → 0.978 | 196 → 132 | 15,854 | 17,940 → 17,355 | 13.4 → 13.2 | beats Bambu; loses to Vitis opt, XLS → **beats Bambu, XLS; loses to Vitis opt** | beats Bambu; loses to Vitis opt, XLS |
| forge 2 | 4 | 1,107 → 794 | 2,085 → 1,501 | 1.47 → 0.987 | 196 → 132 | 31,137 | 33,223 → 32,638 | 12.7 → 12.6 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 2 | 8 | 1,107 → 794 | 2,086 → 1,501 | 1.49 → 0.998 | 196 → 132 | 61,699 → 61,700 | 63,785 → 63,201 | 12.3 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 2 | 16 | 1,107 → 794 | 2,086 → 1,501 | 1.51 → 1.01 | 196 → 132 | 122,823 → 122,824 | 124,909 → 124,325 | 12.1 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 3 | 1 | 1,107 → 794 | 1,295 → 761 | 0.967 → 0.495 | 131 → 67 | 7,753 | 9,048 → 8,514 | 13.7 → 13.2 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge 3 | 2 | 1,107 → 794 | 1,295 → 761 | 0.971 → 0.499 | 131 → 67 | 14,931 | 16,226 → 15,692 | 12.5 → 12.3 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu; loses to XLS |
| forge 3 | 4 | 1,107 → 794 | 1,294 → 761 | 0.976 → 0.503 | 131 → 67 | 29,292 → 29,291 | 30,586 → 30,052 | 11.9 → 11.8 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu; loses to XLS |
| forge 3 | 8 | 1,107 → 794 | 1,295 → 761 | 0.982 → 0.507 | 131 → 67 | 58,009 | 59,303 → 58,770 | 11.6 → 11.5 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu; loses to XLS → **beats Vitis opt, Bambu, XLS** |
| forge 3 | 16 | 1,107 → 794 | 1,295 → 761 | 0.991 → 0.513 | 131 → 67 | 115,442 | 116,736 → 116,202 | 11.4 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge 4 | 1 | 1,107 → 794 | 1,699 → 1,141 | 1.21 → 0.732 | 164 → 100 | 8,091 | 9,791 → 9,233 | 13.8 → 13.4 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis dace, Bambu; loses to Vitis opt, XLS |
| forge 4 | 2 | 1,107 → 794 | 1,700 → 1,142 | 1.21 → 0.736 | 164 → 100 | 15,988 | 17,688 → 17,130 | 13.2 → 12.9 | beats Bambu, XLS; loses to Vitis opt → **beats Vitis opt, Bambu, XLS** | beats Bambu; loses to Vitis opt, XLS |
| forge 4 | 4 | 1,107 → 794 | 1,700 → 1,143 | 1.22 → 0.741 | 164 → 100 | 31,797 | 33,496 → 32,940 | 12.9 → 12.8 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 4 | 8 | 1,103 → 796 | 1,700 → 1,142 | 1.22 → 0.747 | 164 → 100 | 63,393 → 63,394 | 65,093 → 64,536 | 12.7 → 12.6 | beats Bambu; loses to Vitis opt, XLS | beats Bambu; loses to Vitis opt, XLS |
| forge 4 | 16 | 1,107 → 794 | 1,700 → 1,142 | 1.24 → 0.756 | 164 → 100 | 126,596 | 128,296 → 127,738 | 12.6 | beats Bambu; loses to Vitis opt, XLS | beats Bambu; loses to Vitis opt, XLS |
| forge 5 | 1 | 1,107 → 794 | 1,672 → 1,116 | 1.2 → 0.732 | 164 → 100 | 8,091 | 9,763 → 9,207 | 13.8 → 13.4 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis dace, Bambu; loses to Vitis opt, XLS |
| forge 5 | 2 | 1,107 → 794 | 1,708 → 1,150 | 1.22 → 0.743 | 165 → 101 | 16,175 | 17,883 → 17,325 | 13.1 → 12.9 | beats Bambu, XLS; loses to Vitis opt → **beats Vitis opt, Bambu, XLS** | beats Bambu; loses to Vitis opt, XLS |
| forge 5 | 4 | 1,107 → 794 | 1,740 → 1,178 | 1.24 → 0.757 | 166 → 102 | 31,590 | 33,330 → 32,768 | 12.7 → 12.6 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 5 | 8 | 1,103 → 796 | 1,750 → 1,174 | 1.25 → 0.769 | 167 → 103 | 62,332 → 62,299 | 64,082 → 63,473 | 12.5 → 12.4 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 5 | 16 | 1,107 → 794 | 1,757 → 1,170 | 1.26 → 0.781 | 168 → 104 | 123,898 → 123,894 | 125,655 → 125,064 | 12.4 → 12.3 | beats Bambu, XLS; loses to Vitis opt | beats Bambu; loses to Vitis opt, XLS |
| forge 6 | 1 | 1,107 → 794 | 1,708 → 1,151 | 1.21 → 0.739 | 165 → 101 | 8,553 | 10,261 → 9,704 | 14.3 → 13.8 | beats Vitis opt, Vitis dace, Bambu; loses to XLS | beats Vitis dace, Bambu; loses to Vitis opt, XLS |
| forge 6 | 2 | 1,107 → 794 | 1,717 → 1,160 | 1.22 → 0.751 | 166 → 102 | 17,097 → 17,098 | 18,815 → 18,258 | 13.5 → 13.2 | beats Bambu; loses to Vitis opt, XLS → **beats Bambu, XLS; loses to Vitis opt** | loses to Vitis opt, Bambu, XLS |
| forge 6 | 4 | 1,107 → 794 | 1,726 → 1,170 | 1.24 → 0.763 | 167 → 103 | 33,402 | 35,128 → 34,571 | 13 → 12.9 | beats Bambu; loses to Vitis opt, XLS | loses to Vitis opt, Bambu, XLS |
| forge 6 | 8 | 1,103 → 796 | 1,759 → 1,195 | 1.25 → 0.777 | 168 → 104 | 66,024 → 65,990 | 67,783 → 67,185 | 12.8 | beats Bambu; loses to Vitis opt, XLS | loses to Vitis opt, Bambu, XLS |
| forge 6 | 16 | 1,107 → 794 | 1,765 → 1,202 | 1.27 → 0.789 | 169 → 105 | 131,264 → 131,265 | 133,029 → 132,466 | 12.8 | beats Bambu; loses to Vitis opt, XLS | loses to Vitis opt, Bambu, XLS |

### matadd (untiered)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 850 → 548 | 713 → 438 | 0.509 → 0.265 | 66 → 34 | 270 | 982 → 708 | 1.28 → 1.04 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 2 | 850 → 548 | 713 → 438 | 0.51 → 0.269 | 66 → 34 | 539 | 1,252 → 978 | 1.03 → 0.908 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 4 | 850 → 548 | 713 → 438 | 0.519 → 0.273 | 66 → 34 | 1,079 | 1,792 → 1,517 | 0.903 → 0.841 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 8 | 850 → 548 | 713 → 438 | 0.521 → 0.276 | 66 → 34 | 2,158 | 2,870 → 2,596 | 0.841 → 0.81 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 16 | 850 → 548 | 713 → 438 | 0.53 → 0.28 | 66 → 34 | 4,316 | 5,028 → 4,754 | 0.805 → 0.79 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |

### relu (untiered)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 850 → 548 | 711 → 438 | 0.509 → 0.265 | 66 → 34 | 68.4 | 780 → 506 | 0.958 → 0.714 | beats Vitis opt, Vitis dace, Bambu; loses to XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 2 | 850 → 548 | 711 → 438 | 0.512 → 0.269 | 66 → 34 | 137 | 848 → 575 | 0.698 → 0.576 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |
| forge | 4 | 850 → 548 | 711 → 438 | 0.519 → 0.273 | 66 → 34 | 273 | 985 → 712 | 0.565 → 0.503 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |
| forge | 8 | 850 → 548 | 711 → 438 | 0.522 → 0.276 | 66 → 34 | 547 | 1,258 → 985 | 0.499 → 0.469 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |
| forge | 16 | 850 → 548 | 711 → 438 | 0.529 → 0.28 | 66 → 34 | 1,094 | 1,805 → 1,532 | 0.468 → 0.452 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |

### axpy (untiered)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 1,375 → 1,073 | 712 → 438 | 0.509 → 0.265 | 66 → 34 | 7,106 | 7,818 → 7,545 | 10 → 9.77 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge | 2 | 1,375 → 1,073 | 712 → 438 | 0.51 → 0.269 | 66 → 34 | 14,020 | 14,732 → 14,459 | 9.79 → 9.67 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge | 4 | 1,375 → 1,073 | 712 → 438 | 0.519 → 0.273 | 66 → 34 | 27,836 | 28,548 → 28,275 | 9.64 → 9.58 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge | 8 | 1,375 → 1,073 | 712 → 438 | 0.521 → 0.276 | 66 → 34 | 55,469 | 56,181 → 55,907 | 9.56 → 9.53 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge | 16 | 1,375 → 1,073 | 712 → 438 | 0.53 → 0.28 | 66 → 34 | 110,661 → 110,662 | 111,373 → 111,100 | 9.57 → 9.55 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge baked | 1 | 850 → 548 | 713 → 438 | 0.509 → 0.265 | 66 → 34 | 535 | 1,248 → 974 | 1.65 → 1.41 | beats Vitis opt, Vitis dace, Bambu, XLS | beats Vitis opt, Vitis dace, Bambu, XLS |
| forge baked | 2 | 850 → 548 | 713 → 438 | 0.51 → 0.269 | 66 → 34 | 1,071 | 1,784 → 1,509 | 1.4 → 1.28 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge baked | 4 | 850 → 548 | 713 → 438 | 0.519 → 0.273 | 66 → 34 | 2,142 | 2,854 → 2,580 | 1.27 → 1.21 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge baked | 8 | 850 → 548 | 713 → 438 | 0.521 → 0.276 | 66 → 34 | 4,284 | 4,996 → 4,722 | 1.21 → 1.18 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge baked | 16 | 850 → 548 | 713 → 438 | 0.53 → 0.28 | 66 → 34 | 8,567 | 9,280 → 9,006 | 1.17 → 1.16 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |

### rowsum (untiered)

| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | ctrl + datapath pJ/element | energy against HLS | area against HLS |
|---|---|---|---|---|---|---|---|---|---|---|
| forge | 1 | 1,107 → 794 | 1,295 → 761 | 0.974 → 0.497 | 131 → 67 | 841 | 2,136 → 1,602 | 2.86 → 2.38 | beats Vitis opt, Vitis dace, Bambu; loses to XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge | 2 | 1,107 → 794 | 1,294 → 760 | 0.982 → 0.504 | 131 → 67 | 1,107 | 2,401 → 1,868 | 1.63 → 1.39 | beats Vitis opt, Bambu; loses to XLS | beats Vitis opt, Bambu; loses to XLS |
| forge | 4 | 1,107 → 794 | 1,294 → 760 | 0.995 → 0.513 | 131 → 67 | 1,644 → 1,643 | 2,937 → 2,404 | 0.999 → 0.879 | beats Vitis opt, Bambu; loses to XLS → **beats Vitis opt, Bambu, XLS** | beats Vitis opt, Bambu; loses to XLS |
| forge | 8 | 1,107 → 794 | 1,294 → 760 | 1.02 → 0.527 | 131 → 67 | 2,713 | 4,007 → 3,473 | 0.676 → 0.614 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu; loses to XLS → **beats Vitis opt, Bambu, XLS** |
| forge | 16 | 1,107 → 794 | 1,294 → 760 | 1.06 → 0.554 | 131 → 67 | 4,849 | 6,144 → 5,610 | 0.519 → 0.487 | beats Vitis opt, Bambu, XLS | beats Vitis opt, Bambu, XLS |
| forge 2 | 1 | 1,107 → 794 | 1,295 → 761 | 0.974 → 0.497 | 131 → 67 | 841 | 2,136 → 1,602 | 2.86 → 2.38 | beats Vitis opt, Vitis dace, Bambu; loses to XLS | beats Vitis opt, Vitis dace, Bambu; loses to XLS |
| forge 2 | 2 | 1,107 → 794 | 1,294 → 760 | 0.977 → 0.5 | 131 → 67 | 1,682 | 2,976 → 2,443 | 2.38 → 2.14 | beats Bambu; loses to Vitis opt, XLS | beats Bambu; loses to Vitis opt, XLS |
| forge 2 | 4 | 1,107 → 794 | 1,294 → 760 | 0.982 → 0.504 | 131 → 67 | 3,366 → 3,367 | 4,660 → 4,126 | 2.13 → 2.01 | loses to Vitis opt, Bambu, XLS | beats Bambu; loses to Vitis opt, XLS |
| forge 2 | 8 | 1,107 → 794 | 1,294 → 760 | 0.987 → 0.509 | 131 → 67 | 6,732 | 8,026 → 7,492 | 2.02 → 1.96 | loses to Vitis opt, Bambu, XLS | loses to Vitis opt, Bambu, XLS |
| forge 2 | 16 | 1,107 → 794 | 1,295 → 760 | 0.994 → 0.513 | 131 → 67 | 13,463 | 14,758 → 14,224 | 1.96 → 1.93 | loses to Vitis opt, Bambu, XLS | loses to Vitis opt, Bambu, XLS |

<!-- /gen -->
