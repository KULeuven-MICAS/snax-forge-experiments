# Interpolating the STRM tables

How a cost is read from `results/strm/<tech>/streamer.csv` and `xbar.csv` for a size between grid points, step by step, with the numbers from the Nangate 45 nm tables. The code is `report/strm_table.py` (`Table.at`, `reader_cost`, `xbar_cost`); the decisions are X53 and X54. A cost model that copies the rule should give the same numbers as the examples below.

## The rule

Every lookup is linear interpolation along one axis at a time, between the two grid values around the query (a grid value is matched exactly, with no interpolation on that axis). Along an axis measured in a scale $g$, between grid values $x_0 < x < x_1$ with table values $y_0$ and $y_1$:

$$t = \frac{g(x) - g(x_0)}{g(x_1) - g(x_0)}, \qquad y = y_0 + t\,(y_1 - y_0)$$

With $g(x) = x$ this is ordinary linear interpolation. With $g(x) = 1/x$ the weight $t$ is taken in $1/x$, which follows a curve of the form $a + b/x$ exactly. Two or three axes are done one after the other (bilinear, trilinear); the order does not change the result.

| Table | Axes | Area | Energy |
|---|---|---|---|
| `streamer.csv` (a reader; also a writer, X52) | depth, loops, channels | linear in each | linear in each |
| `xbar.csv` (the sparse interconnect) | inputs, banks | linear in each | linear in **1/inputs**, linear in banks |

A query outside the grid on any axis is refused (depth 2–16, loops 1–7, channels 1–16, inputs 4–64, banks 16–64); so is one whose corners include a missing value. The interconnect's energy is measured only where inputs ≤ banks; above that, each bank count's row takes its value at inputs = banks (the most inputs measured for that bank count), which is pessimistic because the energy per access falls with inputs.

## Example 1: a reader between two channel counts

A reader with FIFO depth 8, 2 loops and 3 channels. Depth 8 and 2 loops are grid values, so only the channel axis is interpolated, between 2 and 4 channels:

| depth, loops, channels | e_beat_pj | area_um2 |
|---|---|---|
| 8, 2, 2 | 10.4858 | 10,694.8 |
| 8, 2, 4 | 20.2973 | 20,155.1 |

$$t = \frac{3 - 2}{4 - 2} = 0.5, \qquad e = 10.4858 + 0.5\,(20.2973 - 10.4858) = 15.3916 \text{ pJ per beat}$$

Area the same way: $10{,}694.8 + 0.5\,(20{,}155.1 - 10{,}694.8) = 15{,}424.9$ µm². `reader_cost(t, 8, 2, 3)` returns both.

## Example 2: a reader between grid values on two axes

A reader with depth 6, 3 loops and 3 channels: depth lies between 4 and 8, channels between 2 and 4, loops is a grid value. The four corners at 3 loops:

| depth, channels | e_beat_pj |
|---|---|
| 4, 2 | 7.8641 |
| 4, 4 | 14.7329 |
| 8, 2 | 10.7979 |
| 8, 4 | 20.6058 |

1. Along channels at depth 4, $t = (3 - 2)/(4 - 2) = 0.5$: $7.8641 + 0.5\,(14.7329 - 7.8641) = 11.2985$.
2. Along channels at depth 8, the same $t$: $10.7979 + 0.5\,(20.6058 - 10.7979) = 15.7019$.
3. Along depth, $t = (6 - 4)/(8 - 4) = 0.5$: $11.2985 + 0.5\,(15.7019 - 11.2985) = 13.5002$ pJ per beat.

With all three axes between grid values the same steps run over the eight corners of the cube: four interpolations along the first axis, two along the second, one along the third.

## Example 3: the interconnect's energy, in 1/inputs

An interconnect with 12 inputs and 32 banks. Banks is a grid value; inputs lies between 8 and 16:

| inputs, banks | e_access_pj | area_um2 |
|---|---|---|
| 8, 32 | 3.985046 | 40,117.3 |
| 16, 32 | 3.111931 | 82,784.5 |

Energy, in $g(n) = 1/n$:

$$t = \frac{1/12 - 1/8}{1/16 - 1/8} = \frac{0.083333 - 0.125}{0.0625 - 0.125} = 0.66667$$

$$e = 3.985046 + 0.66667\,(3.111931 - 3.985046) = 3.4030 \text{ pJ per access}$$

Area, in $g(n) = n$: $t = (12 - 8)/(16 - 8) = 0.5$, so $40{,}117.3 + 0.5\,(82{,}784.5 - 40{,}117.3) = 61{,}450.9$ µm².

For comparison, interpolating the energy linearly in inputs gives $t = 0.5$ and 3.5485 pJ, 4 % higher; the fit $e = 2.344 + 13.02/n$ through all five 32-bank points gives 3.429 pJ.

## Example 4: more inputs than banks

An interconnect with 40 inputs and 32 banks. Its energy was not measured (no stimulus is conflict-free there), so the 32-bank row is completed with its value at 32 inputs, 2.739443 pJ, and that is the answer: 2.7394 pJ per access. Its area was measured: 210,443.8 µm².

## Why 1/inputs for the interconnect's energy

Each cycle, part of the interconnect's energy does not depend on how many requests it carries: the clock into its registers (no clock gating, X52) and the bank side's logic, which toggles every cycle. The rest is paid per request: the address and data through the crossbar and the arbiter that grants it. Over a window of $C$ cycles with $n$ grants each cycle (the conflict-free stimulus, every input granted every cycle):

$$E = C\,(P + n\,a) \qquad \Rightarrow \qquad e(n) = \frac{E}{C\,n} = a + \frac{P}{n} = a + \frac{b}{n}$$

So the energy per access falls as the fixed per-cycle part $b$ is shared by more grants. Fitted per bank count on the measured points:

| banks | $a$ (pJ per access) | $b$ (pJ per cycle) | worst residual |
|---|---|---|---|
| 16 | 2.21 | 6.12 | 0.02 pJ |
| 32 | 2.34 | 13.02 | 0.05 pJ |
| 64 | 3.91 | 24.36 | 0.54 pJ |

$b$ grows with the banks (about 0.38 pJ per bank per cycle), as a cost paid by every bank every cycle should. Two points fix $a$ and $b$, so interpolation in $1/n$ reproduces $a + b/n$ exactly between any two grid values, which interpolation in $n$ cannot. The 64-bank row also rises slowly above 32 inputs (4.59 to 4.80 pJ from 40 to 64): each bank arbitrates over all its inputs, so a term growing with $n$ joins in, $a + b/n + c\,n$; the table holds it, and it is small next to the $b/n$ part.

Area is close to a fixed cost per crosspoint (about 157–166 µm² per input per bank), so it stays linear in inputs and banks.

What the energy assumes: every input requests every cycle. An interconnect whose inputs are mostly idle still pays the per-cycle part $b$, over fewer accesses, so its real energy per access is higher than the table's for its input count.

## How well it works

Leave-one-out (`pixi run strm-table --loo`): each interior grid point predicted from its neighbours with its own value left out, which doubles the gap the rule bridges, so a query between two real grid values sees less error than this.

| Quantity | Points | Mean error | Worst |
|---|---|---|---|
| Reader area | 40 | 0.83 % | +1.66 % (depth 4, 2 loops, 2 channels) |
| Reader energy | 40 | 4.01 % | −8.68 % (depth 4, 6 loops, 6 channels; energy is not linear in depth between 2 and 8) |
| Interconnect area | 21 | 1.08 % | +3.04 % (8 inputs, 16 banks) |
| Interconnect energy, in 1/inputs | 11 | 2.49 % | +11.32 % (32 inputs, 64 banks, a measured dip); all others within 3.9 % |
| Interconnect energy, in inputs (X53, replaced) | 11 | 8.98 % | +24.32 % (8 inputs, 64 banks) |

The reader axis by axis: each interior grid value predicted from its two neighbours on one axis only, the other two axes held at grid values, which shows which axis bends.

| Reader axis | Area mean / worst | Energy mean / worst | Shape at depth 8, 2 loops, 4 channels |
|---|---|---|---|
| Channels | 0.12 % / +0.81 % | 0.45 % / −1.72 % | straight: about +4,700 µm² and +4.9 pJ per beat per channel |
| Loops | 0.03 % / −0.17 % | 0.42 % / +3.10 % | nearly flat: about +530 µm² and +0.3 pJ per beat per loop |
| Depth | 0.74 % / +1.49 % | 3.95 % / −8.33 % | 9.77, 14.41, 20.30, 32.40 pJ per beat at depths 2, 4, 8, 16 |

Depth is the only axis that bends, and only in energy: from depth 4 up each FIFO entry adds about 1.5 pJ per beat at 4 channels, while 2 to 4 adds about 2.3 pJ per entry, so depth 4 predicted from 2 and 8 comes out 6–8 % low at every channel count (not traced). Interpolating in log₂(depth) does worse (area 20.2 %, energy 9.3 % mean), so depth stays linear. The FIFO registers are not clock-gated, so every entry is clocked every cycle, used or not: about 4.6 fJ per register bit per cycle. A deeper FIFO costs energy per beat even when the extra entries are never filled.

Fitted forms were tried too, each fitted per bank count and checked the same way (STRM1 R2); none does better than the table in 1/inputs, and all miss most at the same 32-input, 64-bank point:

| Interconnect energy | Parameters | Mean | Worst |
|---|---|---|---|
| Table, linear in 1/inputs | — | 2.5 % | +11.3 % |
| $a + b/n + c\,n$ | 3 | 2.7 % | +10.8 % |
| $a + k\,n^p$ | 3 | 4.5 % | +14.9 % |
| $a + b/n$ | 2 | 4.6 % | +15.1 % |
| $a + b/n + c/n^2$ | 3 | 5.0 % | +15.3 % |
| $a + b\,e^{-n/\tau}$ | 3 | 5.9 % | +21.9 % |
| $k\,n^p$ | 2 | 11.1 % | +18.5 % |
| $a + b\,n + c\,n^2$ | 3 | 13.6 % | +23.7 % |

The 16-bank row has three measured points, so every three-parameter form passes through them exactly and cannot be checked there; the table claims nothing beyond its points.
