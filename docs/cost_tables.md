# The cost tables

snax-forge's first-order cost model (HWCOST) prices a design from four files made in this repo, all on Nangate 45 nm: the SRAM banks (`results/ram/nangate45/ram_table.csv`), the streamer's data mover (`results/strm/nangate45/streamer.csv`), the TCDM sparse interconnect (`results/strm/nangate45/xbar.csv`) and its read-only and write-only inputs (`results/strm/nangate45/xbar_kinds.json`). This page explains, for each one, what a number means, how it was measured, how a cost is read between grid points and how far that can be trusted, then the leakage every table carries (X101), the DMA engine's price per burst (X102) and the cluster's fixed parts (X103). The costs are for comparing design variants with each other, not for sign-off. Dynamic energy and leakage are kept apart: snax-forge shows leakage only when asked. Every table comes from clock-gated synthesis (X83 · X85), `xbar_kinds.json`'s factors included.

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
| $P_{\mathrm{leak}}$ | leakage power | µW |
| $T_{\mathrm{clk}}$ | the clock period, 10 ns (X2) | ns |
| $\alpha, \beta$ | the interconnect's energy per access and energy per cycle, fitted per bank count | pJ |
| $f_{ro}, f_{wo}$ | the share of area a read-only or write-only input saves against a read-write one | — |
| $g_{ro}(b), g_{wo}(b)$ | the share of energy per access a read-only or write-only input saves against a read-write one, at $b$ banks | — |
| $e_{ro}, e_{wo}$ | the interconnect's energy per request of a read-only or write-only input | pJ |
| $c_{rw}, c_{ro}, c_{wo}$ | area per crosspoint (one input × one bank) of each input kind | µm² |
| $k_n, k_b, k_0$ | the crosspoint form's per-input, per-bank and constant terms (`d`, `e`, `g` in `xbar_kinds.json`) | µm² |

## The tables at a glance

| File | Prices | Grid | Area | Energy |
|---|---|---|---|---|
| `ram_table.csv` | one SRAM bank, one read-write port | $d$ 32–4096 (step 32) × $w$ 8–256 (step 8): 4,095 rows | $A$, $P_{\mathrm{leak}}$ | $e_{\mathrm{rd}}$, $e_{\mathrm{wr}}$ |
| `streamer.csv` | one reader (a writer is priced the same) | $D$ {2, 4, 8, 16} × $L$ 1–7 × $C$ {1, 2, 4, 6, 8, 16}: 168 points | $A$, $P_{\mathrm{leak}}$ | $e_{\mathrm{beat}}$ |
| `xbar.csv` | the sparse interconnect, 64-bit ports, every input read-write | $n$ {4, 8, …, 64} × $b$ {16, 32, 64}: 27 points | $A$, $P_{\mathrm{leak}}$ | $e_{\mathrm{access}}$ where $n \le b$ (17 points) |
| `xbar_kinds.json` | read-only and write-only inputs | $n$ {16, 32, 64} × $b$ {16, 32, 64}, each all read-write, all read-only, all write-only: 27 points, 18 of them powered ($n \le b$) | $f_{ro}, f_{wo}$; $c_{rw}, c_{ro}, c_{wo}, k_n, k_b, k_0$ | $g_{ro}(b), g_{wo}(b)$ at $b$ {16, 32, 64} |

## How the logic is measured

The reader and the interconnect come from snax_cluster's own Chisel generators at one pinned commit (`ea9c837`, `strm/grid.json`). Each grid point is generated, synthesized and simulated alone (X52):

- **Synthesis:** Design Compiler on Nangate 45 nm (typical, 1.10 V, 25 °C), 10 ns clock, no wire-load model, hierarchy kept (X1–X4, X22), with DC's clock gating (X79), as the cluster is synthesized. Every point met timing. An integrated clock gate counts as a sequential cell, so the flop check against the bits the RTL declares is reported, not failed (X52 · X82).
- **Power:** a zero-delay Questa simulation of the netlist; its window cut from the VCD, turned into a SAIF and read by PrimePower in averaged mode (X7–X9). Every SAIF checked, every net annotated. Random data with seed 0 (seed 1 moves a reader's energy by 0.15 %).

Both stimuli are full rate: the case a design reaches when nothing stalls.

## SRAM banks

**What a row gives.** Area $A$, read energy $e_{\mathrm{rd}}$ and write energy $e_{\mathrm{wr}}$ per access, and leakage power $P_{\mathrm{leak}}$ of one bank of $d$ words × $w$ bits, one read-write port. A 512 × 64 TCDM bank: 13,503 µm², 3.39 pJ per read, 6.45 pJ per write, 0.14 µW of leakage.

**How it is found.** CACTI 7 at 45 nm (commit `1ffd8df`; itrs-lstp cells and periphery, no ECC, design objective weighted to dynamic energy and area), one run per row (X47 · X100). lstp works at 1.1 V, the cell library's 1.10 V, so every number is CACTI's, unscaled. The leakage is the sum of the two CACTI prints:

$$P_{\mathrm{leak}} = P_{\mathrm{sub}} + P_{\mathrm{gate}}$$

For the 512 × 64 bank, 0.093 + 0.048 = 0.14 µW; the 32 banks of a cluster leak 4.5 µW, 0.045 pJ a cycle at 10 ns. Low standby power is what an L1 at 100 MHz would use: the high-performance cells leaked 2.33 mW a bank.

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
| $C$ | straight: about +3,888 µm², +688 flops and +2.75 pJ per beat per channel | each channel has its own request and response path and buffer slice |
| $L$ | nearly flat: about +35 flops, +489 µm² and +0.02–0.27 pJ per beat per loop | the address generator's counters and adders |
| $D$ | 7.68, 9.85, 11.54, 15.03 pJ per beat at $D$ = 2, 4, 8, 16 | the buffers hold $C \times D \times 81$ bits (64 data, 17 address) |

With clock gating a buffer entry that only holds costs little: from $D$ = 8 to 16 the reader gains 2,676 flops and 3.48 pJ per beat, 1.3 fJ per added flop.

**How it is read.** Linear interpolation on each axis ([Reading a table](#reading-a-table)). Depth is the one axis that bends: depth 4 predicted from 2 and 8 comes out 6–10 % low in energy.

### Example 1: one axis

$D$ = 8, $L$ = 2, $C$ = 3. Only $C$ lies between grid values (2 and 4):

| $D$, $L$, $C$ | $e_{\mathrm{beat}}$ (pJ) | $A$ (µm²) |
|---|---|---|
| 8, 2, 2 | 6.0367 | 8,897.7 |
| 8, 2, 4 | 11.5441 | 16,691.8 |

$$t = \frac{3 - 2}{4 - 2} = 0.5, \qquad e_{\mathrm{beat}} = 6.0367 + 0.5\thinspace(11.5441 - 6.0367) = 8.7904 \text{ pJ}$$

and $A = 8{,}897.7 + 0.5\thinspace(16{,}691.8 - 8{,}897.7) = 12{,}794.7$ µm² (`reader_cost(t, 8, 2, 3)`).

### Example 2: two axes

$D$ = 6, $L$ = 3, $C$ = 3. $D$ lies between 4 and 8, $C$ between 2 and 4; at $L$ = 3 the corners are 5.2744 (4, 2), 9.9340 (4, 4), 6.1246 (8, 2), 11.6321 (8, 4) pJ.

1. Along $C$ at $D$ = 4, $t$ = 0.5: $5.2744 + 0.5\thinspace(9.9340 - 5.2744) = 7.6042$.
2. Along $C$ at $D$ = 8: $6.1246 + 0.5\thinspace(11.6321 - 6.1246) = 8.8784$.
3. Along $D$, $t = (6 - 4)/(8 - 4) = 0.5$: $7.6042 + 0.5\thinspace(8.8784 - 7.6042) = 8.2413$ pJ per beat.

Three axes off the grid take eight corners: four steps along the first axis, two along the second, one along the third.

## Interconnect

**What a point gives.** Area $A$ and energy per granted access $e_{\mathrm{access}}$ of `SparseInterconnect` with $n$ 64-bit inputs and $b$ banks, every input a read-write port. Area on all 27 points; energy only where $n \le b$.

**How it is measured.** A stimulus that never conflicts: at cycle $t$ input $i$ requests bank $(i + t) \bmod b$ at a random row, reads and writes alternate, the banks are always ready and answer reads the next cycle. Every input is granted every cycle (16,384 grants for 16 inputs over 1,024 cycles), and

$$e_{\mathrm{access}} = \frac{E_{\mathrm{dyn}}(\text{window})}{\text{grants}}$$

With $n > b$ some inputs must conflict, so no clean stimulus exists and those points have area only. The 512-bit DMA path is the same for every design and is not swept.

**Why energy goes as 1/n.** Part of each cycle's energy does not depend on how many requests pass: the clock into the registers DC does not gate and the bank side, which toggles every cycle. Call it $\beta$ per cycle. The rest is paid per request, $\alpha$ per access. Over $T$ cycles with $n$ grants each:

$$E_{\mathrm{dyn}} = T\thinspace(\beta + n\thinspace\alpha) \qquad \Rightarrow \qquad e_{\mathrm{access}}(n) = \frac{E_{\mathrm{dyn}}}{T\thinspace n} = \alpha + \frac{\beta}{n}$$

$\alpha$ and $\beta$ are found by a least-squares fit of $\alpha + \beta / n$ to each bank count's measured points. They are not used for pricing; they explain the shape:

| $b$ | $\alpha$ (pJ per access) | $\beta$ (pJ per cycle) | worst residual |
|---|---|---|---|
| 16 | 2.21 | 6.31 | 0.02 pJ |
| 32 | 2.35 | 13.44 | 0.05 pJ |
| 64 | 3.93 | 25.17 | 0.56 pJ |

$\beta$ grows by about 0.39 pJ per bank, as a cost every bank pays every cycle should. The 64-bank row also rises slowly above 32 inputs (each bank arbitrates over all inputs) and dips at 32 inputs (4.16 pJ against about 4.64 either side; not traced). Area is close to a fixed cost per crosspoint, 157–166 µm² per input per bank, so it is linear in $n$ and $b$.

**How it is read.** Area linear in $n$ and $b$. Energy linear in $1/n$ and in $b$ (X54): two grid points fix $\alpha$ and $\beta$, so interpolating in $1/n$ follows $\alpha + \beta / n$ exactly between them. Above $n = b$ the energy takes the value at $n = b$, the largest $n$ measured for that bank count; since $e_{\mathrm{access}}$ falls with $n$, this is pessimistic.

### Example 3: energy in 1/n

$n$ = 12, $b$ = 32, between the points (8, 32): 4.043928 pJ, 40,287.8 µm² and (16, 32): 3.152293 pJ, 83,108.2 µm².

$$t = \frac{1/12 - 1/8}{1/16 - 1/8} = \frac{0.083333 - 0.125}{0.0625 - 0.125} = 0.66667, \qquad e_{\mathrm{access}} = 4.043928 + 0.66667\thinspace(3.152293 - 4.043928) = 3.4495 \text{ pJ}$$

Area in $n$: $t$ = 0.5, $A = 40{,}287.8 + 0.5\thinspace(83{,}108.2 - 40{,}287.8) = 61{,}698.0$ µm². For comparison, energy linear in $n$ gives 3.5981 pJ, 4 % higher.

### Example 4: more inputs than banks

$n$ = 40, $b$ = 32. The energy takes the 32-bank row's value at $n$ = 32: 2.7526 pJ per access. The area was measured: 210,357.6 µm².

## Read-only and write-only inputs

`xbar.csv` prices every input as read-write, but in a cluster most inputs are streamer channels that only read or only write. A reader ties its write bit and write data to 0, a writer never reads its response data, no streamer drives the atomic-operation field, and the cluster ties every response ready and bank response valid to 1. Synthesis removes what those constants make dead. The `xbar_mix` set measured it (X70), and `xbar_kinds.json` gives it in two forms (X71).

**The factor form (default).** Keep `xbar.csv` and scale its area:

$$A = A_{\mathrm{table}}(n, b)\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big), \qquad f_{ro} = 0.3953, \quad f_{wo} = 0.4097$$

*How $f_{ro}$ and $f_{wo}$ are found:* at each of the 9 $(n, b)$ pairs, $1 - A(\text{all read-only}) / A(\text{all read-write})$, then the mean of the 9 (they range only 0.388–0.404); $f_{wo}$ the same with all write-only (0.405–0.414). All on the clock-gated points.

*Why the shares $n_{ro}/n$ and $n_{wo}/n$:* every input owns $b$ crosspoints of about the same size, $c_{rw} \approx A_{\mathrm{table}} / (n\thinspace b)$. A read-only input keeps its crosspoints but each loses its write side, a fraction $f_{ro}$ of its area; a write-only input loses its response side, $f_{wo}$. Summing over the inputs:

$$A = c_{rw}\thinspace b\thinspace\big[n_{rw} + (1 - f_{ro})\thinspace n_{ro} + (1 - f_{wo})\thinspace n_{wo}\big] = c_{rw}\thinspace b\thinspace n\thinspace\Big(1 - f_{ro}\frac{n_{ro}}{n} - f_{wo}\frac{n_{wo}}{n}\Big)$$

**The crosspoint form (option).** A cost per crosspoint of each kind, plus small terms, with no table:

$$A = b\thinspace(c_{rw}\thinspace n_{rw} + c_{ro}\thinspace n_{ro} + c_{wo}\thinspace n_{wo}) + k_n\thinspace n + k_b\thinspace b + k_0$$

with $c_{rw}$ = 159.62, $c_{ro}$ = 95.48, $c_{wo}$ = 93.93, $k_n$ = 22.68, $k_b$ = −17.16, $k_0$ = −103.8 µm².

*How they are found:* ordinary least squares (unweighted, in µm²) over the 27 grid points, the two 36-input points held out as checks; worst residual 2.8 %. The two forms agree: $1 - c_{ro}/c_{rw}$ = 0.402 ≈ $f_{ro}$ and $1 - c_{wo}/c_{rw}$ = 0.412 ≈ $f_{wo}$.

The energy is priced by input kind too, below.

### The energy by input kind

`xbar.csv`'s stimulus makes every input alternate reads and writes with random 64-bit write data, so $e_{\mathrm{access}}$ is a read-write input's. A reader's channel has no write side and a writer's no response data, so a request of each costs less. The `xbar_mix` points with $n \le b$ were powered with the xbar stimulus by kind (X93): a read-only input reads at the same banks and rows, a write-only one writes random data. The price is read at $(b, b)$, one per bank count (X54), so the factor is too:

$$e_k(b) = e_{\mathrm{access}}(b, b)\thinspace\big(1 - g_k(b)\big), \qquad g_k(b) = 1 - \frac{e^{mix}_k(b, b)}{e^{mix}_{rw}(b, b)}, \qquad k \in \lbrace ro, wo \rbrace$$

- $e^{mix}_k(b, b)$ is the `xbar_mix` point with $b$ inputs on $b$ banks, all of kind $k$; $e^{mix}_{rw}$ the same point all read-write. Their ratio cancels the cluster template's ties, which put the all-read-write `xbar_mix` points 0.9 to 4.8 % above `xbar.csv`.
- A read-write input (a core, the AXI port) keeps $e_{\mathrm{access}}$. Between measured bank counts $g_k$ is linear in $b$; outside them it takes the nearest one's.

| $b$ | $e^{mix}_{rw}$ | $e^{mix}_{ro}$ | $e^{mix}_{wo}$ | $g_{ro}$ | $g_{wo}$ | $e_{ro}$ | $e_{wo}$ |
|---|---|---|---|---|---|---|---|
| 16 | 2.6797 | 1.6810 | 1.4365 | 0.3727 | 0.4639 | 1.6461 | 1.4067 |
| 32 | 2.8406 | 1.8981 | 1.5010 | 0.3318 | 0.4716 | 1.8393 | 1.4545 |
| 64 | 4.8972 | 3.6562 | 3.4804 | 0.2534 | 0.2893 | 3.6240 | 3.4497 |

Energies in pJ per access; $e_{ro}$ and $e_{wo}$ on `xbar.csv`'s $e_{\mathrm{access}}(b, b)$ (2.6241, 2.7526, 4.8540).

*Why one pair per bank count, not one constant as for the area:* the saving moves with banks per input. At $n < b$ a read-only input saves more (0.413 at 16 inputs on 32 banks, 0.531 on 64) and a write-only one less (0.285 and −0.039: its fresh write data reaches every bank's mux, seen in the toggles, not proven). The six pairs' means (0.398, 0.264) would miss the 32-bank point by 13 and 35 %. All six pairs are in `xbar_kinds.json`'s `energy.pairs`; only $n = b$ prices.

### Example 7: the cluster's interconnect, by kind

dot 3 at W = 8, N = 2048 on 32 banks: 4096 words read by the readers' 16 read-only channels, 1 written by the writer's write-only channel. $e_{ro}$ = 2.752585 × (1 − 0.331792) = 1.839299 pJ, $e_{wo}$ = 2.752585 × (1 − 0.471583) = 1.454513 pJ:

$$E = 4096 \times 1.839299 + 1 \times 1.454513 = 7535.2 \text{ pJ} = 7.535 \text{ nJ}$$

against 4097 × 2.752585 pJ = 11.277 nJ at the read-write price. The gated cluster's `tcdm_interconnect` in its `run` window, dot 3 at N = 2048:

| W | cluster (nJ) | by kind, from the words (nJ) | ratio | read-write price | by kind, from SNAX-GVSoC's requests (nJ) | ratio |
|---|---|---|---|---|---|---|
| 2 | 7.75 | 7.535 | 0.97 | 1.45 | 7.539 | 0.97 |
| 4 | 7.60 | 7.535 | 0.99 | 1.48 | 7.543 | 0.99 |
| 8 | 8.04 | 7.535 | 0.94 | 1.40 | 7.550 | 0.94 |
| 16 | 8.95 | 7.535 | 0.84 | 1.26 | 7.565 | 0.85 |
| 32 | 18.14 | 7.535 | 0.42 | 0.62 | 15.010 | 0.83 |

SNAX-GVSoC's requests count refusals at a grant's price (snax-forge D177); at W = 32 they are 8161 against 4097 words. The cluster's price per request still rises with W (1.85 to 2.22 pJ) while the full-rate points do not show it, so W = 16 and 32 sit 15 % low.

### Example 5: the cluster's interconnect

The mix as synthesized alone: $n$ = 36, $b$ = 32, with $n_{ro}$ = 32, $n_{wo}$ = 1, $n_{rw}$ = 3.

*Factor form.* $A_{\mathrm{table}}(36, 32)$, linear between $n$ = 32 and 40: $164{,}995.0 + \frac{36 - 32}{40 - 32}(210{,}357.6 - 164{,}995.0) = 187{,}676.3$ µm². The factor: $1 - 0.3953 \cdot \frac{32}{36} - 0.4097 \cdot \frac{1}{36} = 0.6372$. So $A$ = 119,595 µm².

*Crosspoint form.* $159.62 \cdot 32 \cdot 3 + 95.48 \cdot 32 \cdot 32 + 93.93 \cdot 32 \cdot 1 + 22.68 \cdot 36 - 17.16 \cdot 32 - 103.8 = 116{,}264$ µm².

| | Synthesized | Factor | Crosspoint | Every input read-write |
|---|---|---|---|---|
| The same mix alone (`i36_b32_r32_w1`) | 119,307 µm² | +0.2 % | −2.6 % | +57 % |
| Inside the one-core cluster (`dot3_w16_cg`, $n$ = 35, $n_{rw}$ = 2) | 103,257 µm² | +10.5 % (114,095) | +7.6 % (111,137) | +76 % (182,006) |

The cluster's remaining 8–10 % is constants the forms do not model (priority, user and strobe bits, bank outputs nothing reads).

### Example 6: all read-only

$n$ = 16, $b$ = 16, every input read-only. Factor: 42,048.5 × (1 − 0.3953) = 25,427 µm². Crosspoint: $95.48 \cdot 16 \cdot 16 + 22.68 \cdot 16 - 17.16 \cdot 16 - 103.8 = 24{,}427$ µm². Synthesized: 25,132 µm² (factor +1.2 %, crosspoint −2.8 %). The factor's +1.2 % is mostly the cluster template's ties: $f_{ro}$ is measured with them on both points, while `xbar.csv` was synthesized without them and is about 2 % larger.

**Range.** Both forms were checked for $n$ and $b$ in 16–64. Beyond 64 inputs both extrapolate linearly; the cost per crosspoint drifts up about 3 % from 40 inputs on, so a 128-input interconnect may land a few percent above the line. Not synthesized.

## Leakage

**What a table gives.** Every table carries its points' leakage power beside their area (X101): `leak_uw` in `ram_table.csv` (CACTI's subthreshold plus gate leakage, X47 · X100), `streamer.csv` and `xbar.csv` (DC's `leak_power_uw` of the point), and in `char.json` a flop's `flop.leak_uw` and each block point's `leak_comb_uw`. Leakage is read as the area is: the streamer and the interconnect by the same interpolation, a block's comb leakage by its entry's lanes rule, a bank by exact lookup.

**A block.** As its area, its comb part plus its flops:

$$P_{\mathrm{leak}} = P_{\mathrm{comb}} + n_{\mathrm{bits}}\thinspace P_{\mathrm{flop}}$$

$P_{\mathrm{flop}}$ is the mean over the 21 int64 points with sequential cells of their sequential leakage (registers and clock gates) per sequential cell, as $A_{\mathrm{flop}}$ is found: 0.0836 µW on nangate45, 0.0816 to 0.0845. Over the 87 char points the formula is a median 0.09 % under DC's leakage, at most 10 % (`link/d4_w1_i8`).

**How it becomes energy.** Leakage is paid every cycle a design runs, whatever it does:

$$E_{\mathrm{leak}} = P_{\mathrm{leak}}\cdot N\cdot T_{\mathrm{clk}}$$

Example: a reader at $D$ = 8, $L$ = 2, $C$ = 4 leaks 0.018 µW/µm² of its area; the logic leaks about that much everywhere (char 0.016–0.026, streamers 0.018–0.019), the interconnect a little more (0.024–0.029). The 32 lstp banks of a cluster leak 4.5 µW in all. $T_{\mathrm{clk}}$ is 10 ns everywhere (X2); leakage energy scales linearly with it, so the numbers are for comparison at that clock.

## The DMA engine

**What it gives.** `results/snb/nangate45/dma_copy.json`'s `engine.e_burst_pj`: the energy one burst of a DMA copy inside L1 costs in the engine (the iDMA, its AXI-to-memory and the wide AXI path), on top of the burst's bank and crossbar accesses (snax-forge D184): 106.40 pJ (X102).

**How it is found.** From the gate-level copy of a 64 × 64 matrix (`snitch1_cg_dma_transpose_int8` and `_int64`, X95): the `dma` and `axi` groups' energy in the copy's window, less what they spend per cycle with the DMA idle (their floor in `dot3_w8_cg`'s run window: 4.81 and 6.03 pJ a cycle), per burst:

$$e_{\mathrm{burst}} = \frac{(E_{\mathrm{dma}} - C\thinspace p^{\mathrm{idle}}_{\mathrm{dma}}) + (E_{\mathrm{axi}} - C\thinspace p^{\mathrm{idle}}_{\mathrm{axi}})}{N_{\mathrm{burst}}}$$

with $C$ = 10,967 cycles and $N_{\mathrm{burst}}$ = 4,096: 72.32 + 30.41 = 102.73 pJ at int8, 76.13 + 33.94 = 110.07 pJ at int64, the mean 106.40 pJ. The element's size moves it by 7 %, so one price serves every type.

## The cluster's fixed parts

**What it gives.** `results/cluster/nangate45/cluster_fixed.json` (X103): what the cluster pays whatever its accelerators, per group of `cluster/groups.json` that is not one of HWCOST's five parts or a TCDM bank, in three parts: the core (the Snitch core with its mul/div, the I-cache logic and macros), the DMA, and the rest (AXI, peripherals, TCDM bank logic, the CSR path). Per group: area, leakage and idle floor.

**How it is found.** From `dot3_w8_cg`'s run window: area from DC's hierarchy (`breakdown.json`), leakage from PrimePower's hierarchy in the window (the leakage column summed into the groups; the I-cache macros from the lstp table, not the reports' older macros), idle floor from the window's dynamic energy per group (`energy.json`), the accelerator running and the DMA idle. The TCDM bank logic has no floor: it moves with L1 traffic (2 pJ a cycle idle, 5–16 running) and is left to be priced per access.

| Part | Area (µm²) | Leakage (µW) | Idle floor (pJ a cycle) |
|---|---:|---:|---:|
| core | 88,914 | 847 | 4.76 |
| DMA | 73,719 | 1,407 | 4.81 |
| rest | 227,921 | 4,017 | 14.03 |

At 10 ns the fixed parts cost $6.27\ \mathrm{mW} \cdot 10\ \mathrm{ns} + 23.6\ \mathrm{pJ} \approx 86$ pJ a cycle. Their area is exactly what HWCOST leaves out of the synthesized cluster but its banks (`breakdown.json`'s `not_costed_um2`).

## Reading a table

Every interpolated lookup is linear along one axis at a time, between the two grid values around the query; a grid value is taken exactly. On an axis measured in a scale $g$, with grid values $x_0 < x < x_1$ and table values $y_0, y_1$:

$$t = \frac{g(x) - g(x_0)}{g(x_1) - g(x_0)}, \qquad y = y_0 + t\thinspace(y_1 - y_0)$$

$g(x) = x$ is plain linear interpolation; $g(x) = 1/x$ follows a curve $\alpha + \beta / x$ exactly. Several axes are done one after the other; the order does not change the result.

| Table | Area | Energy |
|---|---|---|
| `streamer.csv` | linear in $D$, $L$, $C$ | linear in $D$, $L$, $C$ |
| `xbar.csv` | linear in $n$, $b$ | linear in $1/n$ and $b$ |
| `ram_table.csv` | lookup only | lookup only |

`report/strm_table.py` (`Table.at`, `reader_cost`, `xbar_cost`) is the reference; it refuses a query outside the grid ($D$ 2–16, $L$ 1–7, $C$ 1–16, $n$ 4–64, $b$ 16–64). snax-forge copies the rule and extrapolates outside the grid with a warning. Tested by `pixi run test`; a copy of the rule should reproduce the examples above.

## How far it can be trusted

**Leave-one-out** (`pixi run strm-table --loo`): each interior grid point is predicted from its neighbours with its own value left out. That doubles the gap the rule bridges, so a real query between two grid values does better.

| Quantity | Points | Mean error | Worst |
|---|---|---|---|
| Reader area | 40 | 0.56 % | −1.01 % ($D$ 4, $L$ 3, $C$ 4) |
| Reader energy | 40 | 5.09 % | −11.42 % ($D$ 4, $L$ 6, $C$ 6) |
| Interconnect area | 21 | 1.05 % | +3.14 % ($n$ 8, $b$ 16) |
| Interconnect energy, in $1/n$ | 11 | 2.61 % | +11.68 % ($n$ 32, $b$ 64, the dip); all others within 4.3 % |
| Interconnect energy, in $n$ (not used) | 11 | 9.20 % | +24.67 % ($n$ 8, $b$ 64) |

Reader, axis by axis (one axis interpolated, the other two on grid values): channels 0.15 % area and 1.44 % energy mean error, loops 0.03 % and 0.69 %, depth 0.55 % and 4.37 %. Depth in $\log_2 D$ does worse (18.9 % area, 4.8 % energy).

**Fits tried instead of the table** for the interconnect's energy, per bank count, checked the same way (the two forms with an exponent fitted by least squares over a grid of it); none beats the table on the mean:

| Form | Parameters | Mean | Worst |
|---|---|---|---|
| Table, linear in $1/n$ | — | 2.6 % | +11.7 % |
| $\alpha + \beta/n + \gamma\thinspace n$ | 3 | 2.7 % | +11.1 % |
| $\alpha + \beta\thinspace e^{-n/\tau}$ | 3 | 3.9 % | +13.2 % |
| $\alpha + k\thinspace n^p$ | 3 | 4.4 % | +15.3 % |
| $\alpha + \beta/n$ | 2 | 4.6 % | +15.4 % |
| $\alpha + \beta/n + \gamma/n^2$ | 3 | 4.9 % | +15.7 % |
| $k\thinspace n^p$ | 2 | 11.2 % | +19.0 % |
| $\alpha + \beta\thinspace n + \gamma\thinspace n^2$ | 3 | 13.8 % | +24.1 % |

The SRAM table has every size as a row, so it needs no such check; fits of it were rejected (the best still 6 % off on average, 30 % at worst, X48).

## What the numbers assume

- **Full rate.** A reader never stalls, and every interconnect input is granted every cycle. An interconnect with mostly idle inputs still pays $\beta$ every cycle over fewer accesses, so its real energy per access is higher than the table's; conflicts add arbitration not in the table either.
- **A writer priced as a reader:** slightly pessimistic.
- **Clock gating as DC inserts it** (X79): a flop that holds costs almost nothing, as in the synthesized cluster.
- **Two models side by side:** logic on the Nangate cell library, SRAM from CACTI's 45 nm model, whose cells (about 0.41 µm² per bit with periphery at 512 × 64) are close to a foundry 45 nm SRAM and denser than FreePDK45's. Memory-against-logic ratios inherit that; comparisons between designs on the same memories do not.
- **Averaged PrimeTime for logic, counted accesses for memories:** averaged PrimeTime sees each pin's probability, not which pins were high together, and charged a macro 12.5 % low on a probe (PITFALLS PT7).
- **Nangate 45 nm, typical corner, no place and route.**

## Sources

- Decisions: X1–X4, X7–X9, X22 (the flows); X47–X50, X100 (SRAM); X101–X103 (leakage, the DMA engine, the fixed parts); X52 · X82, X53 · X54 (streamer and interconnect); X79, X83 · X85 (clock gating); X70, X71 (input kinds).
- Run notes: `results/ram/runs/2026-11-05_ram1_r1.md`, `2026-11-06_ram1_r2.md`, `2026-11-06_ram1_r3.md`; `results/strm/runs/2026-11-06_strm1_r1.md`, `2026-11-06_strm1_r2.md`, `2026-11-13_cg2_r1.md` to `2026-11-14_cg2_r4.md`; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`, `2026-11-11_csyn1_r3d.md`; `results/runs/2026-11-16_cg5_r1.md`, `2026-11-16_cg5_r2.md` (the grid clock-gated).
- Code: `ram/ram.py`, `strm/gen.py`, `report/strm_table.py`, `strm/xbar_mix.py`, `report/xbar_kinds.py`, `report/char_export.py`, `report/dma_copy.py`, `report/cluster_fixed.py`.
