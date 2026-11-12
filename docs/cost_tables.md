# The cost tables: how they are measured and interpolated

snax-forge's HW cost model (HWCOST) prices a design from three tables made in this repo, all on Nangate 45 nm: the SRAM banks (`results/ram/nangate45/ram_table.csv`), the streamer's data mover (`results/strm/nangate45/streamer.csv`) and the TCDM sparse interconnect (`results/strm/nangate45/xbar.csv`). This page says how each number was measured, how a cost is read between grid points, how well that agrees with the measurements, and what the numbers assume. It is written to be reused as a methods section; every number below comes from the run notes cited at the end.

## What each table gives

| Table | Unit priced | Axes (grid) | Area | Energy |
|---|---|---|---|---|
| `ram_table.csv` | one SRAM bank, one read-write port | depth 32–4096 words (step 32) × width 8–256 bits (step 8): 4,095 points | µm² | pJ per read, pJ per write |
| `streamer.csv` | one reader (also used for a writer) | FIFO depth {2, 4, 8, 16} × loops 1–7 × channels {1, 2, 4, 6, 8, 16}: 168 points | µm² | pJ per beat |
| `xbar.csv` | the sparse interconnect, 64-bit ports | inputs {4, 8, …, 64} × banks {16, 32, 64}: 27 points | µm² | pJ per access (17 points, inputs ≤ banks) |
| `xbar_kinds.json` | the interconnect's read-only and write-only inputs (X71) | inputs {16, 32, 64} × banks {16, 32, 64}, each all read-write, all read-only and all write-only: 27 points | a factor on `xbar.csv`'s area (default) or a cost per crosspoint (option) | — (energy stays `xbar.csv`'s) |

Only dynamic energy is used; leakage is recorded where a tool gives it but never enters a cost (X50). The costs are first-order and meant for comparing design variants against each other, not for absolute sign-off.

## How the numbers are measured

### Common setup for the streamer and the interconnect

Both come from snax_cluster's own Chisel generators at one pinned commit (`ea9c837`, `strm/grid.json`), run read-only in snax_cluster's container (sbt 1.11.3, Chisel 6.4.0, firtool 1.62.0); each grid point is generated, synthesized and simulated alone (X52).

- **Synthesis** (X1–X4, X22): Design Compiler, Nangate 45 nm Open Cell Library at its typical corner (1.10 V, 25 °C), a 10 ns clock on every point (fmax is reported as a lower bound from the slack), no wire-load model, inputs driven by `INV_X4`, outputs loaded with 25 fF, 0.25 ns maximum transition, `compile_ultra` with the hierarchy kept. Every point met timing (worst slack 5.46 ns). A flop check compares DC's sequential cells with the bits the RTL declares; all 195 points matched, so nothing was optimized away. No clock gating is present or inserted, as for the other blocks (X30).
- **Power** (X7–X9): a zero-delay Questa simulation of the mapped netlist (no SDF), its activity over a cut window written as a VCD, converted to SAIF with `vcd2saif` and read by PrimePower in averaged mode with the same library and constraints as DC. Each SAIF is checked (every net's time adds up to the window, the clock toggles twice per cycle) and every point annotated 100 % of its nets. Random data use seed 0; seed 1 changed a reader's energy by 0.15 %, and a rerun with seed 0 reproduced it exactly.

### The reader

A point is the `Reader` module as the streamer instantiates it (one reader, `fifo_depth` D for both its address and data buffers, `temporal_dim` L, `num_channel` C with spatial bounds `[C]`, 64-bit ports onto a 128 KiB TCDM), without the CSR manager. firtool trims the request fields a reader never drives; none of them holds a register. A writer has the same address generator, requestors and buffers minus the reader's response path and output repeat, so the reader's cost stands for a writer's too, slightly pessimistically.

Stimulus: the loops stream 1,024 beats from address 0 with unit strides, the loop bounds powers of two whose product is 1,024 with the larger ones outermost. The memory side grants every request at once and returns random data the next cycle; the output is always ready. Every point streamed its 1,024 beats after a 3-cycle fill with no stall, at every depth. The energy per beat is

$$e_{\mathrm{beat}} = \frac{E_{\mathrm{dyn}}(\mathrm{window})}{1024}$$

with the window from the start edge to the last beat (1,027 cycles, the fill included).

### The interconnect

A point is `SparseInterconnect` with `inputs` 64-bit request ports, `banks` 64-bit bank ports and access granularity 1, at the widths snax_cluster uses for a 128 KiB TCDM. Area is measured on all 27 points. Energy is measured only where inputs ≤ banks, with a stimulus that never conflicts: at cycle $t$ input $i$ requests bank $(i + t) \bmod B$ at a random row, reads and writes alternate every cycle with random write data, and the bank side is always ready and answers reads with random data the next cycle. Every input is granted every cycle (16,384 grants for 16 inputs over 1,024 cycles), and

$$e_{\mathrm{access}} = \frac{E_{\mathrm{dyn}}(\mathrm{window})}{\mathrm{grants}}$$

The wide 512-bit DMA path is not swept: it is the same for every design and enters as a fixed term.

### The SRAM banks

The banks are not synthesized: OpenRAM's analytical model gave one power for read, write and idle and an area only with layout (RAM1 R0), so area and energy come from CACTI 7 at 45 nm (commit `1ffd8df`; itrs-hp cells and periphery, one read-write port, no ECC, design objective weighted to dynamic energy and area) (X47). CACTI's dynamic energies at its 1.0 V are scaled to the cell library's 1.10 V:

$$e = e_{\mathrm{CACTI}} \cdot \left(\frac{1.1}{1.0}\right)^2 = 1.21\thinspace e_{\mathrm{CACTI}}$$

Area and timing are CACTI's. A 512 × 64 TCDM bank: 13,523 µm², 3.54 pJ per read, 6.47 pJ per write. A run's memory energy is its counted accesses times these (X50):

$$E_{\mathrm{mem}} = \sum_m \left(N_{\mathrm{rd},m}\thinspace e_{\mathrm{rd},m} + N_{\mathrm{wr},m}\thinspace e_{\mathrm{wr},m}\right)$$

The same numbers are written into generated `.lib` macros for synthesis and PrimeTime (X49).

## How a cost is read between grid points

The SRAM table is a lookup: every bank in steps of 32 words and 8 bits is a row, and CACTI's numbers jump by up to 30 % between neighbouring sizes where its array organization changes, so it is never interpolated (X48). The other two tables are interpolated.

Every lookup is linear interpolation along one axis at a time, between the two grid values around the query (a grid value is matched exactly, with no interpolation on that axis). Along an axis measured in a scale $g$, between grid values $x_0 < x < x_1$ with table values $y_0$ and $y_1$:

$$t = \frac{g(x) - g(x_0)}{g(x_1) - g(x_0)}, \qquad y = y_0 + t\thinspace (y_1 - y_0)$$

With $g(x) = x$ this is ordinary linear interpolation. With $g(x) = 1/x$ the weight $t$ is taken in $1/x$, which follows a curve of the form $a + b/x$ exactly. Two or three axes are done one after the other (bilinear, trilinear); the order does not change the result.

| Table | Area | Energy |
|---|---|---|
| `streamer.csv` | linear in depth, loops, channels | linear in depth, loops, channels |
| `xbar.csv` | linear in inputs and banks | linear in **1/inputs** and in banks (X54) |

A query outside the grid on any axis is refused (depth 2–16, loops 1–7, channels 1–16, inputs 4–64, banks 16–64), as is one whose corners include a missing value. The interconnect's energy above inputs = banks takes each bank count's value at inputs = banks, the most inputs measured for it; the energy per access falls with inputs, so this is pessimistic. The code is `report/strm_table.py` (`Table.at`, `reader_cost`, `xbar_cost`), tested by `pixi run strm-table-test`; a cost model that copies the rule should reproduce the examples below.

### Example 1: a reader between two channel counts

A reader with FIFO depth 8, 2 loops and 3 channels. Depth 8 and 2 loops are grid values, so only the channel axis is interpolated, between 2 and 4 channels:

| depth, loops, channels | e_beat_pj | area_um2 |
|---|---|---|
| 8, 2, 2 | 10.4858 | 10,694.8 |
| 8, 2, 4 | 20.2973 | 20,155.1 |

$$t = \frac{3 - 2}{4 - 2} = 0.5, \qquad e = 10.4858 + 0.5\thinspace (20.2973 - 10.4858) = 15.3916 \text{ pJ per beat}$$

Area the same way: $10{,}694.8 + 0.5\thinspace (20{,}155.1 - 10{,}694.8) = 15{,}424.9$ µm². `reader_cost(t, 8, 2, 3)` returns both.

### Example 2: a reader between grid values on two axes

A reader with depth 6, 3 loops and 3 channels: depth lies between 4 and 8, channels between 2 and 4, loops is a grid value. The four corners at 3 loops:

| depth, channels | e_beat_pj |
|---|---|
| 4, 2 | 7.8641 |
| 4, 4 | 14.7329 |
| 8, 2 | 10.7979 |
| 8, 4 | 20.6058 |

1. Along channels at depth 4, $t = (3 - 2)/(4 - 2) = 0.5$: $7.8641 + 0.5\thinspace (14.7329 - 7.8641) = 11.2985$.
2. Along channels at depth 8, the same $t$: $10.7979 + 0.5\thinspace (20.6058 - 10.7979) = 15.7019$.
3. Along depth, $t = (6 - 4)/(8 - 4) = 0.5$: $11.2985 + 0.5\thinspace (15.7019 - 11.2985) = 13.5002$ pJ per beat.

With all three axes between grid values the same steps run over the eight corners of the cube: four interpolations along the first axis, two along the second, one along the third.

### Example 3: the interconnect's energy, in 1/inputs

An interconnect with 12 inputs and 32 banks. Banks is a grid value; inputs lies between 8 and 16:

| inputs, banks | e_access_pj | area_um2 |
|---|---|---|
| 8, 32 | 3.985046 | 40,117.3 |
| 16, 32 | 3.111931 | 82,784.5 |

Energy, in $g(n) = 1/n$:

$$t = \frac{1/12 - 1/8}{1/16 - 1/8} = \frac{0.083333 - 0.125}{0.0625 - 0.125} = 0.66667$$

$$e = 3.985046 + 0.66667\thinspace (3.111931 - 3.985046) = 3.4030 \text{ pJ per access}$$

Area, in $g(n) = n$: $t = (12 - 8)/(16 - 8) = 0.5$, so $40{,}117.3 + 0.5\thinspace (82{,}784.5 - 40{,}117.3) = 61{,}450.9$ µm².

For comparison, interpolating the energy linearly in inputs gives $t = 0.5$ and 3.5485 pJ, 4 % higher; the fit $e = 2.344 + 13.02/n$ through all five 32-bank points gives 3.429 pJ.

### Example 4: more inputs than banks

An interconnect with 40 inputs and 32 banks. Its energy was not measured (no stimulus is conflict-free there), so the 32-bank row is completed with its value at 32 inputs, 2.739443 pJ, and that is the answer: 2.7394 pJ per access. Its area was measured: 210,443.8 µm².

## Why the shapes are what they are

### The reader

| Reader axis | Shape at depth 8, 2 loops, 4 channels | Where it comes from |
|---|---|---|
| Channels | straight: about +4,723 µm², +667 flops and +4.91 pJ per beat per channel | each channel adds its own request and response path and its buffer slice |
| Loops | nearly flat: +34 flops (two 17-bit counters), about +530 µm² and +0.26 to 0.49 pJ per beat per loop | the address generator's counters and adders |
| Depth | 9.77, 14.41, 20.30, 32.40 pJ per beat at depths 2, 4, 8, 16 | the buffers: C × D × 81 bits (64 data and 17 address bits per channel and entry) |

Split by PT's power groups at 4 channels and 2 loops, the clock's energy grows with the buffer bits (3.31, 6.01, 11.41, 22.31 pJ per cycle at depths 2 to 16), the registers' hardly moves (1.95 to 2.19, since only the slot being written toggles) and the combinational logic's jumps from depth 2 to 4 (4.49 to 6.31) and then grows slowly (6.63, 7.86). The clock part is about 4.1 fJ per flop per cycle: with no clock gating every buffer entry is clocked every cycle, used or not, so a deeper FIFO costs energy per beat even when its extra entries are never filled.

### Why 1/inputs for the interconnect's energy

Each cycle, part of the interconnect's energy does not depend on how many requests it carries: the clock into its registers (not clock-gated) and the bank side's logic, which toggles every cycle. The rest is paid per request: the address and data through the crossbar and the arbiter that grants it. Over a window of $C$ cycles with $n$ grants each cycle (the conflict-free stimulus, every input granted every cycle), with $b$ the per-cycle part and $a$ the per-access part:

$$E = C\thinspace (b + n\thinspace a) \qquad \Rightarrow \qquad e(n) = \frac{E}{C\thinspace n} = a + \frac{b}{n}$$

So the energy per access falls as the fixed per-cycle part $b$ is shared by more grants. Fitted per bank count on the measured points:

| banks | $a$ (pJ per access) | $b$ (pJ per cycle) | worst residual |
|---|---|---|---|
| 16 | 2.21 | 6.12 | 0.02 pJ |
| 32 | 2.34 | 13.02 | 0.05 pJ |
| 64 | 3.91 | 24.36 | 0.54 pJ |

$b$ grows with the banks (about 0.38 pJ per bank per cycle), as a cost paid by every bank every cycle should. Two points fix $a$ and $b$, so interpolation in $1/n$ reproduces $a + b/n$ exactly between any two grid values, which interpolation in $n$ cannot. The 64-bank row also rises slowly above 32 inputs (4.59 to 4.80 pJ from 40 to 64): each bank arbitrates over all its inputs, so a term growing with $n$ joins in, $a + b/n + c\thinspace n$; the table holds it, and it is small next to the $b/n$ part. It also dips at 32 inputs (4.13 pJ against about 4.6 on either side), which was not traced.

Area is close to a fixed cost per crosspoint (about 157–166 µm² per input per bank), so it stays linear in inputs and banks.

## How well the interpolation agrees

Leave-one-out (`pixi run strm-table --loo`): each interior grid point is predicted from its neighbours with its own value left out. That doubles the gap the rule bridges, so a query between two real grid values sees less error than this, and a grid value (FIFO depth 8, say) is exact.

| Quantity | Points | Mean error | Worst |
|---|---|---|---|
| Reader area | 40 | 0.83 % | +1.66 % (depth 4, 2 loops, 2 channels) |
| Reader energy | 40 | 4.01 % | −8.68 % (depth 4, 6 loops, 6 channels) |
| Interconnect area | 21 | 1.08 % | +3.04 % (8 inputs, 16 banks) |
| Interconnect energy, in 1/inputs | 11 | 2.49 % | +11.32 % (32 inputs, 64 banks, the measured dip); all others within 3.9 % |
| Interconnect energy, in inputs (X53, replaced by X54) | 11 | 8.98 % | +24.32 % (8 inputs, 64 banks) |

The reader axis by axis (each interior grid value predicted from its two neighbours on one axis, the other two held at grid values):

| Reader axis | Area mean / worst | Energy mean / worst |
|---|---|---|
| Channels | 0.12 % / +0.81 % | 0.45 % / −1.72 % |
| Loops | 0.03 % / −0.17 % | 0.42 % / +3.10 % |
| Depth | 0.74 % / +1.49 % | 3.95 % / −8.33 % |

Depth is the only axis that bends, and only in energy: depth 4 predicted from depths 2 and 8 comes out 6–8 % low at every channel count, because of the combinational jump from depth 2 to 4. Interpolating in log₂(depth) does worse (20.2 % area, 9.3 % energy mean), so depth stays linear.

Fitted forms were tried for the interconnect's energy too, each fitted per bank count and checked the same way (STRM1 R2); none does better than the table in 1/inputs, and all miss most at the same 32-input, 64-bank point:

| Interconnect energy | Parameters | Mean | Worst |
|---|---|---|---|
| Table, linear in 1/inputs | — | 2.5 % | +11.3 % |
| $a + b/n + c\thinspace n$ | 3 | 2.7 % | +10.8 % |
| $a + k\thinspace n^p$ | 3 | 4.5 % | +14.9 % |
| $a + b/n$ | 2 | 4.6 % | +15.1 % |
| $a + b/n + c/n^2$ | 3 | 5.0 % | +15.3 % |
| $a + b\thinspace e^{-n/\tau}$ | 3 | 5.9 % | +21.9 % |
| $k\thinspace n^p$ | 2 | 11.1 % | +18.5 % |
| $a + b\thinspace n + c\thinspace n^2$ | 3 | 13.6 % | +23.7 % |

The 16-bank row has three measured points, so every three-parameter form passes through them exactly and cannot be checked there; the table claims nothing beyond its points. The SRAM table needs no such check: every bank size is a row, and fits of it were rejected for the same reason (X48: the best still 6 % off on average for energy, up to 30 % at its worst point).

## Read-only and write-only inputs on the interconnect

`xbar.csv` prices every input as a full read-write port. In a cluster most inputs are streamer channels that only read or only write: a reader drives its write bit and write data as 0, a writer drives the write bit as 1 and never reads its response data, no streamer drives the atomic-operation field, and the cluster's interconnect wrapper ties every response ready and every bank response valid to 1. Synthesis removes what those constants make dead. X70 measured it (set `xbar_mix`), and `xbar_kinds.json` (X71, `report/xbar_kinds.py`) gives it in two forms. With $n$ inputs, $b$ banks and $n = n_{rw} + n_{ro} + n_{wo}$ (read-write, read-only and write-only inputs):

$$\textbf{factor (default):} \quad A = A_{table}(n, b)\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big), \qquad f_{ro} = 0.3965, \quad f_{wo} = 0.4108$$

$$\textbf{crosspoint (option):} \quad A = b\thinspace(c_{rw}\thinspace n_{rw} + c_{ro}\thinspace n_{ro} + c_{wo}\thinspace n_{wo}) + d\thinspace n + e\thinspace b + g$$

with $c_{rw}$ = 159.34, $c_{ro}$ = 95.06, $c_{wo}$ = 93.65, $d$ = 26.30, $e$ = −19.43, $g$ = −201.0 µm².

**How the numbers are found.** $f_{ro}$ is the mean, over the 9 (inputs, banks) pairs, of $1 - A(\text{all read-only}) / A(\text{all read-write})$ at the same pair; $f_{wo}$ likewise with all write-only. They vary little (0.389–0.407 and 0.407–0.415), so the averaging hardly matters. The crosspoint coefficients are an ordinary least-squares fit (unweighted squared error in µm²) over the 27 grid points, with the two 36-input points held out as checks; the worst residual on the grid is 2.9 %. The two forms agree: $1 - c_{ro}/c_{rw}$ = 0.403 ≈ $f_{ro}$ and $1 - c_{wo}/c_{rw}$ = 0.412 ≈ $f_{wo}$.

**Why $n_{ro}/n$.** Each bank chooses among $n$ requests and each input chooses its response among $b$ banks, so both sides grow as $n\thinspace b$ and every input owns $b$ crosspoints of about the same size ($A_{table}(n, b) \approx c_{rw}\thinspace b\thinspace n$: 156.7–166.1 µm² per crosspoint over all of `xbar.csv`). A read-only input keeps its crosspoints but each loses its write side, a share $f_{ro}$; a write-only input loses its response side, $f_{wo}$. Then

$$A = c_{rw}\thinspace b\thinspace\big[n_{rw} + (1 - f_{ro})\thinspace n_{ro} + (1 - f_{wo})\thinspace n_{wo}\big] = c_{rw}\thinspace b\thinspace n\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big)$$

so $n_{ro}/n$ is the share of the crosspoints that shrink, and the factor multiplies the table's all read-write area.

### Example 5: the two-core cluster's interconnect (36 inputs, 32 banks; 32 read-only, 1 write-only, 3 read-write)

Factor form. $A_{table}(36, 32)$, linear between `i32_b32` and `i40_b32`: $164{,}650.3 + \frac{36 - 32}{40 - 32}(210{,}443.8 - 164{,}650.3) = 187{,}547.0$ µm². The factor: $1 - 0.3965 \cdot \frac{32}{36} - 0.4108 \cdot \frac{1}{36} = 1 - 0.3524 - 0.0114 = 0.6361$. So $A = 187{,}547.0 \times 0.6361 = 119{,}308$ µm².

Crosspoint form. $159.34 \cdot 32 \cdot 3 + 95.06 \cdot 32 \cdot 32 + 93.65 \cdot 32 \cdot 1 + 26.30 \cdot 36 - 19.43 \cdot 32 - 201.0 = 15{,}296 + 97{,}346 + 2{,}997 + 947 - 622 - 201 = 115{,}763$ µm².

Synthesized with the same ties: 118,952 µm² (factor +0.3 %, crosspoint −2.7 %). In CSYN1's synthesized two-core cluster: 107,685 µm² (factor +10.8 %, crosspoint +7.5 %; every input read-write would give +74 %).

The one-core cluster (snax-forge D170, CORE1 R4) has 35 inputs, 2 of them read-write: $A_{table}(35, 32) = 181{,}823$ µm², factor 0.6257, so 113,776 µm²; crosspoint form 110,638 µm². In the synthesized cluster: 102,884 µm² (factor +10.6 %, crosspoint +7.5 %).

### Example 6: 16 inputs, 16 banks, all read-only

Factor form: `xbar.csv`'s 41,886.0 µm² × (1 − 0.3965) = 25,278 µm². Crosspoint form: $95.06 \cdot 16 \cdot 16 + 26.30 \cdot 16 - 19.43 \cdot 16 - 201.0 = 24{,}336 + 421 - 311 - 201 = 24{,}245$ µm². Synthesized: 24,970 µm² (factor +1.2 %, crosspoint −2.9 %). The factor form's +1.2 % is mostly the template's ties: $f$ is measured with them on both points, while `xbar.csv` was synthesized without them and is about 2 % larger.

**Range.** Both forms were checked for 16–64 inputs and 16–64 banks. Beyond 64 inputs both extrapolate linearly (the factor form through `xbar.csv`'s own extrapolation); the cost per crosspoint drifts up by about 3 % from 40 inputs on (each bank's arbiter), so a 128-input interconnect may come out a few percent above the line. Not synthesized.

## What the numbers assume

- **Full-rate stimuli.** A reader is never stalled, and every interconnect input is granted every cycle. An interconnect whose inputs are mostly idle still pays the per-cycle part $b$ over fewer accesses, so its real energy per access is higher than the table's for its input count; conflicts, which add arbitration per access, are not in the table either.
- **A reader stands for a writer**, which has no response path: slightly pessimistic for writers.
- **Input kinds on the interconnect** come from the design (a reader's channels read-only, a writer's write-only, the cores and AXI read-write); the factor and crosspoint forms leave out the further constants a whole cluster has (priority, user and strobe bits on streamer ports, bank outputs nothing reads), which left the cluster's interconnect about 10 % under the factor form (X70, X71).
- **No clock gating** anywhere, as in the RTL: every register's clock pin toggles every cycle.
- **Two models side by side.** Logic is synthesized on the Nangate cell library; the SRAM banks come from CACTI's 45 nm model, whose cells are denser than FreePDK45's (about 0.41 µm² per bit with periphery at 512 × 64), close to a foundry 45 nm SRAM. Memory-against-logic ratios inherit that difference; comparisons between designs on the same memories do not.
- **Averaged PrimeTime** for logic, **counted accesses** for memories: averaged PrimeTime sees each pin's probability, not which pins were high together, and charged a memory macro 12.5 % low on a probe (PITFALLS PT7), so memory energy is counted instead (X50).
- **Nangate 45 nm only**, at its typical corner; no place and route.

## Sources

- Decisions: X1–X4, X7–X9, X22, X25, X30 (the flows); X47–X50 (the SRAM banks); X52–X54 (the streamer and interconnect); X70, X71 (read-only and write-only inputs).
- Run notes: `results/ram/runs/2026-11-05_ram1_r0.md`, `2026-11-05_ram1_r1.md`, `2026-11-06_ram1_r2.md`, `2026-11-06_ram1_r3.md`; `results/strm/runs/2026-11-06_strm1_r0.md`, `2026-11-06_strm1_r1.md`, `2026-11-06_strm1_r2.md`; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`, `2026-11-11_csyn1_r3d.md`.
- Code: `ram/ram.py`, `strm/gen.py`, `syn/syn.py`, `sim/pwr.py` with `sim/sources/strm.py`, `report/strm_table.py`, `strm/xbar_mix.py`, `report/xbar_kinds.py`.
