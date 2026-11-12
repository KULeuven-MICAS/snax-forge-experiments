# The cost tables

snax-forge's first-order cost model (HWCOST) prices a design from four files made in this repo, all on Nangate 45 nm: the SRAM banks (`results/ram/nangate45/ram_table.csv`), the streamer's data mover (`results/strm/nangate45/streamer.csv`), the TCDM sparse interconnect (`results/strm/nangate45/xbar.csv`) and its read-only and write-only inputs (`results/strm/nangate45/xbar_kinds.json`). This page explains, for each one, what a number means, how it was measured, how a cost is read between grid points and how far that can be trusted. The costs are for comparing design variants with each other, not for sign-off. Only dynamic energy is used.

## Symbols

| Symbol | Meaning | Unit |
|---|---|---|
| $D$ | a streamer reader's FIFO depth (its address and data buffers) | entries |
| $L$ | a reader's number of loops (`temporal_dim`) | — |
| $C$ | a reader's number of 64-bit channels | — |
| $n$ | the interconnect's inputs (request ports); $n = n_{rw} + n_{ro} + n_{wo}$ | — |
| $n_{rw}, n_{ro}, n_{wo}$ | read-write, read-only and write-only inputs: a reader's channel is read-only, a writer's write-only, the cores and the AXI port read-write | — |
| $b$ | the interconnect's banks (one bank port each) | — |
| $d, w$ | an SRAM bank's depth and width | words, bits |
| $E_{\mathrm{dyn}}$ | PrimePower's dynamic energy over a measurement window | pJ |
| $e_{\mathrm{beat}}$ | a reader's energy per beat (one word per channel delivered) | pJ |
| $e_{\mathrm{access}}$ | the interconnect's energy per granted request | pJ |
| $e_{\mathrm{rd}}, e_{\mathrm{wr}}$ | an SRAM bank's energy per read and per write | pJ |
| $N_{\mathrm{rd}}, N_{\mathrm{wr}}$ | a run's counted reads and writes of one bank | — |
| $A$ | area | µm² |
| $\alpha, \beta$ | the interconnect's energy per access and energy per cycle, fitted per bank count | pJ |
| $f_{ro}, f_{wo}$ | the share of area a read-only or write-only input saves against a read-write one | — |
| $c_{rw}, c_{ro}, c_{wo}$ | area per crosspoint (one input × one bank) of each input kind | µm² |
| $k_n, k_b, k_0$ | the crosspoint form's per-input, per-bank and constant terms (`d`, `e`, `g` in `xbar_kinds.json`) | µm² |

## The tables at a glance

| File | Prices | Grid | Area | Energy |
|---|---|---|---|---|
| `ram_table.csv` | one SRAM bank, one read-write port | $d$ 32–4096 (step 32) × $w$ 8–256 (step 8): 4,095 rows | $A$ | $e_{\mathrm{rd}}$, $e_{\mathrm{wr}}$ |
| `streamer.csv` | one reader (a writer is priced the same) | $D$ {2, 4, 8, 16} × $L$ 1–7 × $C$ {1, 2, 4, 6, 8, 16}: 168 points | $A$ | $e_{\mathrm{beat}}$ |
| `xbar.csv` | the sparse interconnect, 64-bit ports, every input read-write | $n$ {4, 8, …, 64} × $b$ {16, 32, 64}: 27 points | $A$ | $e_{\mathrm{access}}$ where $n \le b$ (17 points) |
| `xbar_kinds.json` | read-only and write-only inputs | $n$ {16, 32, 64} × $b$ {16, 32, 64}, each all read-write, all read-only, all write-only: 27 points | $f_{ro}, f_{wo}$; $c_{rw}, c_{ro}, c_{wo}, k_n, k_b, k_0$ | none (`xbar.csv`'s) |

## How the logic is measured

The reader and the interconnect come from snax_cluster's own Chisel generators at one pinned commit (`ea9c837`, `strm/grid.json`). Each grid point is generated, synthesized and simulated alone (X52):

- **Synthesis:** Design Compiler on Nangate 45 nm (typical, 1.10 V, 25 °C), 10 ns clock, no wire-load model, hierarchy kept (X1–X4, X22). Every point met timing. A flop check compares DC's flops with the bits the RTL declares: all 195 points matched. No clock gating, as in the RTL.
- **Power:** a zero-delay Questa simulation of the netlist; its window cut from the VCD, turned into a SAIF and read by PrimePower in averaged mode (X7–X9). Every SAIF checked, every net annotated. Random data with seed 0 (seed 1 moves a reader's energy by 0.15 %).

Both stimuli are full rate: the case a design reaches when nothing stalls.

## SRAM banks

**What a row gives.** Area $A$, read energy $e_{\mathrm{rd}}$ and write energy $e_{\mathrm{wr}}$ per access of one bank of $d$ words × $w$ bits, one read-write port. A 512 × 64 TCDM bank: 13,523 µm², 3.54 pJ per read, 6.47 pJ per write.

**How it is found.** CACTI 7 at 45 nm (commit `1ffd8df`; itrs-hp cells and periphery, no ECC, design objective weighted to dynamic energy and area), one run per row (X47). CACTI works at 1.0 V, so its energies are scaled to the cell library's 1.10 V by the square of the voltage ratio:

$$e = e_{\mathrm{CACTI}} \cdot \left(\frac{1.1}{1.0}\right)^2 = 1.21\thinspace e_{\mathrm{CACTI}}$$

Area and timing are CACTI's, unscaled.

**How it is read.** As a lookup: take the exact row. Never interpolate: CACTI's numbers jump by up to 30 % between neighbouring sizes where its array organization changes (X48). A run's memory energy is its counted accesses times the rows of its banks $m$ (X50):

$$E_{\mathrm{mem}} = \sum_m \left(N_{\mathrm{rd},m}\thinspace e_{\mathrm{rd},m} + N_{\mathrm{wr},m}\thinspace e_{\mathrm{wr},m}\right)$$

The same numbers are written into generated Liberty macros for synthesis and PrimeTime (X49), so a synthesized cluster and the cost model price a bank the same way.

## Streamer reader

**What a point gives.** Area $A$ and energy per beat $e_{\mathrm{beat}}$ of one reader with FIFO depth $D$, $L$ loops and $C$ channels on a 128 KiB TCDM, as the streamer instantiates it (no CSR manager). A writer has the same address generator and buffers minus the response path, so pricing it as a reader is slightly pessimistic.

**How it is measured.** The reader streams 1,024 beats from address 0 with unit strides (loop bounds powers of two whose product is 1,024). Memory grants every request at once and answers the next cycle; the output is always ready. After a 3-cycle fill every point delivers one beat per cycle, so the window is 1,027 cycles and

$$e_{\mathrm{beat}} = \frac{E_{\mathrm{dyn}}(\text{window})}{1024}$$

**What drives the cost.** At $D$ = 8, $L$ = 2, $C$ = 4:

| Axis | Shape | Why |
|---|---|---|
| $C$ | straight: about +4,723 µm², +667 flops and +4.91 pJ per beat per channel | each channel has its own request and response path and buffer slice |
| $L$ | nearly flat: +34 flops (two 17-bit counters), about +530 µm² and +0.26–0.49 pJ per beat per loop | the address generator's counters and adders |
| $D$ | 9.77, 14.41, 20.30, 32.40 pJ per beat at $D$ = 2, 4, 8, 16 | the buffers hold $C \times D \times 81$ bits (64 data, 17 address) |

Most of the depth cost is clock: with no clock gating every buffer entry is clocked every cycle, about 4.1 fJ per flop, whether it holds data or not.

**How it is read.** Linear interpolation on each axis ([Reading a table](#reading-a-table)). Depth is the one axis that bends: depth 4 predicted from 2 and 8 comes out 6–8 % low in energy.

### Example 1: one axis

$D$ = 8, $L$ = 2, $C$ = 3. Only $C$ lies between grid values (2 and 4):

| $D$, $L$, $C$ | $e_{\mathrm{beat}}$ (pJ) | $A$ (µm²) |
|---|---|---|
| 8, 2, 2 | 10.4858 | 10,694.8 |
| 8, 2, 4 | 20.2973 | 20,155.1 |

$$t = \frac{3 - 2}{4 - 2} = 0.5, \qquad e_{\mathrm{beat}} = 10.4858 + 0.5\thinspace(20.2973 - 10.4858) = 15.3916 \text{ pJ}$$

and $A = 10{,}694.8 + 0.5\thinspace(20{,}155.1 - 10{,}694.8) = 15{,}424.9$ µm² (`reader_cost(t, 8, 2, 3)`).

### Example 2: two axes

$D$ = 6, $L$ = 3, $C$ = 3. $D$ lies between 4 and 8, $C$ between 2 and 4; at $L$ = 3 the corners are 7.8641 (4, 2), 14.7329 (4, 4), 10.7979 (8, 2), 20.6058 (8, 4) pJ.

1. Along $C$ at $D$ = 4, $t$ = 0.5: $7.8641 + 0.5\thinspace(14.7329 - 7.8641) = 11.2985$.
2. Along $C$ at $D$ = 8: $10.7979 + 0.5\thinspace(20.6058 - 10.7979) = 15.7019$.
3. Along $D$, $t = (6 - 4)/(8 - 4) = 0.5$: $11.2985 + 0.5\thinspace(15.7019 - 11.2985) = 13.5002$ pJ per beat.

Three axes off the grid take eight corners: four steps along the first axis, two along the second, one along the third.

## Interconnect

**What a point gives.** Area $A$ and energy per granted access $e_{\mathrm{access}}$ of `SparseInterconnect` with $n$ 64-bit inputs and $b$ banks, every input a read-write port. Area on all 27 points; energy only where $n \le b$.

**How it is measured.** A stimulus that never conflicts: at cycle $t$ input $i$ requests bank $(i + t) \bmod b$ at a random row, reads and writes alternate, the banks are always ready and answer reads the next cycle. Every input is granted every cycle (16,384 grants for 16 inputs over 1,024 cycles), and

$$e_{\mathrm{access}} = \frac{E_{\mathrm{dyn}}(\text{window})}{\text{grants}}$$

With $n > b$ some inputs must conflict, so no clean stimulus exists and those points have area only. The 512-bit DMA path is the same for every design and is not swept.

**Why energy goes as 1/n.** Part of each cycle's energy does not depend on how many requests pass: the clock into the registers (never gated) and the bank side, which toggles every cycle. Call it $\beta$ per cycle. The rest is paid per request, $\alpha$ per access. Over $T$ cycles with $n$ grants each:

$$E_{\mathrm{dyn}} = T\thinspace(\beta + n\thinspace\alpha) \qquad \Rightarrow \qquad e_{\mathrm{access}}(n) = \frac{E_{\mathrm{dyn}}}{T\thinspace n} = \alpha + \frac{\beta}{n}$$

$\alpha$ and $\beta$ are found by a least-squares fit of $\alpha + \beta / n$ to each bank count's measured points. They are not used for pricing; they explain the shape:

| $b$ | $\alpha$ (pJ per access) | $\beta$ (pJ per cycle) | worst residual |
|---|---|---|---|
| 16 | 2.21 | 6.12 | 0.02 pJ |
| 32 | 2.34 | 13.02 | 0.05 pJ |
| 64 | 3.91 | 24.36 | 0.54 pJ |

$\beta$ grows by about 0.38 pJ per bank, as a cost every bank pays every cycle should. The 64-bank row also rises slowly above 32 inputs (each bank arbitrates over all inputs) and dips at 32 inputs (4.13 pJ against about 4.6 either side; not traced). Area is close to a fixed cost per crosspoint, 157–166 µm² per input per bank, so it is linear in $n$ and $b$.

**How it is read.** Area linear in $n$ and $b$. Energy linear in $1/n$ and in $b$ (X54): two grid points fix $\alpha$ and $\beta$, so interpolating in $1/n$ follows $\alpha + \beta / n$ exactly between them. Above $n = b$ the energy takes the value at $n = b$, the largest $n$ measured for that bank count; since $e_{\mathrm{access}}$ falls with $n$, this is pessimistic.

### Example 3: energy in 1/n

$n$ = 12, $b$ = 32, between the points (8, 32): 3.985046 pJ, 40,117.3 µm² and (16, 32): 3.111931 pJ, 82,784.5 µm².

$$t = \frac{1/12 - 1/8}{1/16 - 1/8} = \frac{0.083333 - 0.125}{0.0625 - 0.125} = 0.66667, \qquad e_{\mathrm{access}} = 3.985046 + 0.66667\thinspace(3.111931 - 3.985046) = 3.4030 \text{ pJ}$$

Area in $n$: $t$ = 0.5, $A = 40{,}117.3 + 0.5\thinspace(82{,}784.5 - 40{,}117.3) = 61{,}450.9$ µm². For comparison, energy linear in $n$ gives 3.5485 pJ, 4 % higher.

### Example 4: more inputs than banks

$n$ = 40, $b$ = 32. The energy takes the 32-bank row's value at $n$ = 32: 2.7394 pJ per access. The area was measured: 210,443.8 µm².

## Read-only and write-only inputs

`xbar.csv` prices every input as read-write, but in a cluster most inputs are streamer channels that only read or only write. A reader ties its write bit and write data to 0, a writer never reads its response data, no streamer drives the atomic-operation field, and the cluster ties every response ready and bank response valid to 1. Synthesis removes what those constants make dead. The `xbar_mix` set measured it (X70), and `xbar_kinds.json` gives it in two forms (X71).

**The factor form (default).** Keep `xbar.csv` and scale its area:

$$A = A_{\mathrm{table}}(n, b)\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big), \qquad f_{ro} = 0.3965, \quad f_{wo} = 0.4108$$

*How $f_{ro}$ and $f_{wo}$ are found:* at each of the 9 $(n, b)$ pairs, $1 - A(\text{all read-only}) / A(\text{all read-write})$, then the mean of the 9 (they range only 0.389–0.407); $f_{wo}$ the same with all write-only (0.407–0.415).

*Why the shares $n_{ro}/n$ and $n_{wo}/n$:* every input owns $b$ crosspoints of about the same size, $c_{rw} \approx A_{\mathrm{table}} / (n\thinspace b)$. A read-only input keeps its crosspoints but each loses its write side, a fraction $f_{ro}$ of its area; a write-only input loses its response side, $f_{wo}$. Summing over the inputs:

$$A = c_{rw}\thinspace b\thinspace\big[n_{rw} + (1 - f_{ro})\thinspace n_{ro} + (1 - f_{wo})\thinspace n_{wo}\big] = c_{rw}\thinspace b\thinspace n\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big)$$

**The crosspoint form (option).** A cost per crosspoint of each kind, plus small terms, with no table:

$$A = b\thinspace(c_{rw}\thinspace n_{rw} + c_{ro}\thinspace n_{ro} + c_{wo}\thinspace n_{wo}) + k_n\thinspace n + k_b\thinspace b + k_0$$

with $c_{rw}$ = 159.34, $c_{ro}$ = 95.06, $c_{wo}$ = 93.65, $k_n$ = 26.30, $k_b$ = −19.43, $k_0$ = −201.0 µm².

*How they are found:* ordinary least squares (unweighted, in µm²) over the 27 grid points, the two 36-input points held out as checks; worst residual 2.9 %. The two forms agree: $1 - c_{ro}/c_{rw}$ = 0.403 ≈ $f_{ro}$ and $1 - c_{wo}/c_{rw}$ = 0.412 ≈ $f_{wo}$.

Energy keeps `xbar.csv`'s $e_{\mathrm{access}}$ for every input kind.

### Example 5: the cluster's interconnect

Two cores: $n$ = 36, $b$ = 32, with $n_{ro}$ = 32, $n_{wo}$ = 1, $n_{rw}$ = 3.

*Factor form.* $A_{\mathrm{table}}(36, 32)$, linear between $n$ = 32 and 40: $164{,}650.3 + \frac{36 - 32}{40 - 32}(210{,}443.8 - 164{,}650.3) = 187{,}547.0$ µm². The factor: $1 - 0.3965 \cdot \frac{32}{36} - 0.4108 \cdot \frac{1}{36} = 0.6361$. So $A$ = 119,308 µm².

*Crosspoint form.* $159.34 \cdot 32 \cdot 3 + 95.06 \cdot 32 \cdot 32 + 93.65 \cdot 32 \cdot 1 + 26.30 \cdot 36 - 19.43 \cdot 32 - 201.0 = 115{,}763$ µm².

| | Synthesized | Factor | Crosspoint | Every input read-write |
|---|---|---|---|---|
| The same mix alone (`i36_b32_r32_w1`) | 118,952 µm² | +0.3 % | −2.7 % | |
| Inside the two-core cluster | 107,685 µm² | +10.8 % | +7.5 % | +74 % |
| Inside the one-core cluster ($n$ = 35, $n_{rw}$ = 2) | 102,884 µm² | +10.6 % (113,776) | +7.5 % (110,638) | |

The cluster's remaining 10 % is constants the forms do not model (priority, user and strobe bits, bank outputs nothing reads).

### Example 6: all read-only

$n$ = 16, $b$ = 16, every input read-only. Factor: 41,886.0 × (1 − 0.3965) = 25,278 µm². Crosspoint: $95.06 \cdot 16 \cdot 16 + 26.30 \cdot 16 - 19.43 \cdot 16 - 201.0 = 24{,}245$ µm². Synthesized: 24,970 µm² (factor +1.2 %, crosspoint −2.9 %). The factor's +1.2 % is mostly the cluster template's ties: $f_{ro}$ is measured with them on both points, while `xbar.csv` was synthesized without them and is about 2 % larger.

**Range.** Both forms were checked for $n$ and $b$ in 16–64. Beyond 64 inputs both extrapolate linearly; the cost per crosspoint drifts up about 3 % from 40 inputs on, so a 128-input interconnect may land a few percent above the line. Not synthesized.

## Reading a table

Every interpolated lookup is linear along one axis at a time, between the two grid values around the query; a grid value is taken exactly. On an axis measured in a scale $g$, with grid values $x_0 < x < x_1$ and table values $y_0, y_1$:

$$t = \frac{g(x) - g(x_0)}{g(x_1) - g(x_0)}, \qquad y = y_0 + t\thinspace(y_1 - y_0)$$

$g(x) = x$ is plain linear interpolation; $g(x) = 1/x$ follows a curve $\alpha + \beta / x$ exactly. Several axes are done one after the other; the order does not change the result.

| Table | Area | Energy |
|---|---|---|
| `streamer.csv` | linear in $D$, $L$, $C$ | linear in $D$, $L$, $C$ |
| `xbar.csv` | linear in $n$, $b$ | linear in $1/n$ and $b$ |
| `ram_table.csv` | lookup only | lookup only |

`report/strm_table.py` (`Table.at`, `reader_cost`, `xbar_cost`) is the reference; it refuses a query outside the grid ($D$ 2–16, $L$ 1–7, $C$ 1–16, $n$ 4–64, $b$ 16–64). snax-forge copies the rule and extrapolates outside the grid with a warning. Tested by `pixi run strm-table-test`; a copy of the rule should reproduce the examples above.

## How far it can be trusted

**Leave-one-out** (`pixi run strm-table --loo`): each interior grid point is predicted from its neighbours with its own value left out. That doubles the gap the rule bridges, so a real query between two grid values does better.

| Quantity | Points | Mean error | Worst |
|---|---|---|---|
| Reader area | 40 | 0.83 % | +1.66 % ($D$ 4, $L$ 2, $C$ 2) |
| Reader energy | 40 | 4.01 % | −8.68 % ($D$ 4, $L$ 6, $C$ 6) |
| Interconnect area | 21 | 1.08 % | +3.04 % ($n$ 8, $b$ 16) |
| Interconnect energy, in $1/n$ | 11 | 2.49 % | +11.32 % ($n$ 32, $b$ 64, the dip); all others within 3.9 % |
| Interconnect energy, in $n$ (not used) | 11 | 8.98 % | +24.32 % ($n$ 8, $b$ 64) |

Reader, axis by axis (one axis interpolated, the other two on grid values): channels 0.12 % area and 0.45 % energy mean error, loops 0.03 % and 0.42 %, depth 0.74 % and 3.95 %. Depth in $\log_2 D$ does worse (20.2 % area, 9.3 % energy).

**Fits tried instead of the table** for the interconnect's energy, per bank count, checked the same way; none beats the table:

| Form | Parameters | Mean | Worst |
|---|---|---|---|
| Table, linear in $1/n$ | — | 2.5 % | +11.3 % |
| $\alpha + \beta/n + \gamma\thinspace n$ | 3 | 2.7 % | +10.8 % |
| $\alpha + k\thinspace n^p$ | 3 | 4.5 % | +14.9 % |
| $\alpha + \beta/n$ | 2 | 4.6 % | +15.1 % |
| $\alpha + \beta/n + \gamma/n^2$ | 3 | 5.0 % | +15.3 % |
| $\alpha + \beta\thinspace e^{-n/\tau}$ | 3 | 5.9 % | +21.9 % |
| $k\thinspace n^p$ | 2 | 11.1 % | +18.5 % |
| $\alpha + \beta\thinspace n + \gamma\thinspace n^2$ | 3 | 13.6 % | +23.7 % |

The SRAM table has every size as a row, so it needs no such check; fits of it were rejected (the best still 6 % off on average, 30 % at worst, X48).

## What the numbers assume

- **Full rate.** A reader never stalls, and every interconnect input is granted every cycle. An interconnect with mostly idle inputs still pays $\beta$ every cycle over fewer accesses, so its real energy per access is higher than the table's; conflicts add arbitration not in the table either.
- **A writer priced as a reader:** slightly pessimistic.
- **No clock gating**, as in the RTL.
- **Two models side by side:** logic on the Nangate cell library, SRAM from CACTI's 45 nm model, whose cells (about 0.41 µm² per bit with periphery at 512 × 64) are close to a foundry 45 nm SRAM and denser than FreePDK45's. Memory-against-logic ratios inherit that; comparisons between designs on the same memories do not.
- **Averaged PrimeTime for logic, counted accesses for memories:** averaged PrimeTime sees each pin's probability, not which pins were high together, and charged a macro 12.5 % low on a probe (PITFALLS PT7).
- **Nangate 45 nm, typical corner, no place and route.**

## Sources

- Decisions: X1–X4, X7–X9, X22 (the flows); X47–X50 (SRAM); X52–X54 (streamer and interconnect); X70, X71 (input kinds).
- Run notes: `results/ram/runs/2026-11-05_ram1_r1.md`, `2026-11-06_ram1_r2.md`, `2026-11-06_ram1_r3.md`; `results/strm/runs/2026-11-06_strm1_r1.md`, `2026-11-06_strm1_r2.md`; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`, `2026-11-11_csyn1_r3d.md`.
- Code: `ram/ram.py`, `strm/gen.py`, `report/strm_table.py`, `strm/xbar_mix.py`, `report/xbar_kinds.py`.
