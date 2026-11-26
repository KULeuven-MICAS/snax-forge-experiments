# The blocks alone

snax-forge's catalogue datapaths, the output packer and the input slicer characterized on their own (no csr, no ctrl), from int8 to int64, clock-gated (X79 · X87 · X88): area and dynamic energy per cycle on nangate45, for a first-order model of each block (X28–X37, X89). Each block is emitted alone by snax-forge's `gen-block`, synthesized with the forge settings (X30) and simulated through fixed windows: busy and idle for the compute blocks, the packer and the slicer, stream for LinkBuffer (X31, X94).

**Start with [`char_table.md`](char_table.md):** every block, how each scales over lanes and types, the model's constants and the model against the forge accelerators, and the known limits. snax-forge reads `nangate45/char.json` (X37, X83 · X85), and its estimate drops the hold term, which gating makes negligible (snax-forge D154 · D172).

## The block model

snax-forge prices a unit's energy for a task from a few constants per technology and two counts the task gives (X37).

| Symbol | Meaning | Where it comes from |
|---|---|---|
| $n_{fire}$ | the unit's fires in the task (one fire = one beat processed) | the task |
| $T$ | the task's cycles | the task |
| $n_{bits}$ | the unit's register bits: lanes × depth × the output's width (0 for SimdLanes; a FifoPacker's held slots and counter, of which $(d_{out} - 1)/d_{out}$ of a slot and the counter load per push; a FifoSlicer's word, counter and full flag, of which $64/d_{in}$ of the word and the counter load per pop) | the block's params; DC's `seq_cells` adds one clock gate per register enable (X83) |
| $e_{comb}$ | the block's combinational energy per fire | its busy window's `e_comb_pj` (LinkBuffer: its stream, per load), per point in `char.json` |
| $e_{load}$ | energy per flop bit per cycle when the flop loads new data | the mean busy `e_bit_pj` of the blocks whose flops all load every cycle (Mac, TreeAccumulate, SerialAccumulate busy, LinkBuffer at depth 1), per sequential cell: 17.82 fJ on nangate45 |
| $e_{hold}$ | energy per flop bit per cycle when the flop holds | the mean idle `e_bit_pj` of the registered blocks, per sequential cell: 0.0655 fJ on nangate45, a gate's idle energy shared by the bits behind it, so it spreads with the bits per gate (X33, X83) |
| $n_{bits,ctrl}$ | the control unit's sequential cells | the design |
| $f_{ctrl}$ | ctrl's energy per cycle over its flops × $e_{hold}$ | the mean over the 48 int64 tier-done forge points: 83.20 on nangate45, spread 43 to 148 |

A flop costs $e_{hold}$ every cycle and $e_{load} - e_{hold}$ more on the cycles it loads; a block's logic costs $e_{comb}$ per fire. So a unit's energy over a task, and its control unit's, are

$$E_{unit} = n_{fire}\thinspace\big(e_{comb} + n_{bits}\thinspace(e_{load} - e_{hold})\big) + T\thinspace n_{bits}\thinspace e_{hold}$$

$$E_{ctrl} = f_{ctrl}\thinspace n_{bits,ctrl}\thinspace T\thinspace e_{hold}$$

$e_{fire} = e_{comb} + n_{bits}(e_{load} - e_{hold})$ is the energy of one fire on top of holding.

**Types and lanes (X89).** $e_{comb}$ and the comb area are read at the unit's width pair, $w_{in}$ its widest input and $w_{out}$ its output (8, 16, 32 or 64 bits). Every compute block has its 10 pairs ($w_{out} \ge w_{in}$, the op at $w_{out}$) measured at one lane count $W_0$ (SimdLanes 1, the Mac and the folds 8; the int64 set at every lane count CHAR1 has), and over lanes it is that point plus a cost per lane $L$:

$$X(W, w_{in}, w_{out}) = X(W_0, w_{in}, w_{out}) + (W - W_0)\thinspace L$$

- `copy` (SimdLanes, Mac, LinkBuffer: lane copies, no fixed part): $L = X(W_0)/W_0$.
- `interpolate` (the int64 TreeAccumulate and SerialAccumulate): linear between their measured lanes.
- `slope` (a narrow TreeAccumulate or SerialAccumulate): $L = S_{64}\thinspace w_{in}/64$, with $S_{64} = (X(32, 64, 64) - X(8, 64, 64))/24$ the int64 cost per lane: a lane is a leaf or a mux input at $w_{in}$, while the accumulator's adder and register stay at $w_{out}$. TreeAccumulate at 8/32 and W = 32: 401.66 + 24 × 267.06 × 8/64 = 1202.9 µm² against 1214.3 measured.
- A LinkBuffer at a narrower dtype is the int64 one times $w/64$; FifoPacker has one point per type (d_out 2, 4, 8 at int32, int16, int8); FifoSlicer one per type and lanes (d_in 2 to 8), its pop at 1.11 to 1.30 of its busy window (X94). Against the forge accelerators (vecmul, vsum, dot 4, dot 5 at W = 8 and 32, N = 2048) the model's ctrl + datapath lands at 0.997 to 1.035 of the measured energy; against their narrow twins (int8 and int16 in, dot 3 at W = 8 and 32) at 0.92 to 1.40, high on int8 (1.24 to 1.40), and their datapath area at 0.99 to 1.12. It leaves out the csr, the memory and the streamers, which HWCOST prices from [`docs/cost_tables.md`](../../docs/cost_tables.md).
- A mixed pair, a and b of different widths (X98: int8 × int32 → int32, the SimdLanes mul at W = 1 and the Mac at W = 8), is its own entry at its exact `inTypes`, read by the same rule as its block (`copy`), not as its widest input's pair.
- A SimdLanes scalar form (X99) is its own entry at W = 1, `copy` over lanes, keyed by its scalars as snax-forge's lookup fills them: one stream (`streams` 1, `inTypes` a alone) with `k` baked or `kCsr`, or `op` `axpby` with `k1` baked or `k1Csr` and `k2` baked, `k2Csr` or neither. A scalar from a CSR is an input pin of opType's width; its cost is in the block's comb (no flops: the CSR is outside the datapath).

Known limits (numbers in `char_table.md`): an isolated fire of an accumulator costs 25–30 % more than a back-to-back one (X34, measured before clock gating); a rarely firing sum inside a design costs its inputs' toggling every cycle, which a per-fire model does not see. At a narrow pair with $w_{in} < w_{out}$ a register's upper bits copy the sign and toggle less, so $e_{load}$ prices it high by up to 2.2×; SerialAccumulate's narrow lanes cost more energy than $w_{in}/64$ of an int64 lane (32 % above the slope rule at 8/32, W = 32, on 0.4 pJ a fire).

## What this folder holds

| Path | What it holds |
|---|---|
| `char_table.md` | The table (`pixi run char-table`), generated from the CSVs below and `char.json` (refused if not current). |
| `<tech>/char.json` | The table snax-forge reads (`pixi run char-export`, X37, X89), from the clock-gated rows: `flop` (`area_um2`, the mean of `seq_area / seq_cells`, `leak_uw`, the mean sequential leakage per sequential cell, X101, `e_load_fj`, `e_hold_fj`, from the int64 points), `ctrl.counter_factor` ($f_{ctrl}$), `source` (the snax-forge commits: `snax_forge`, and `snax_forge_FifoSlicer`, `snax_forge_mixed`, `snax_forge_scalar` where those points were made at another), `bank` (a `Mac` bank's two forms over its rows-1 entry, X97: `comb_um2_lane_row` µm² per lane and row beyond the extra flops, a fire's energy over the base `e_pj_lane_log2_rows` · log₂ R + `e_pj_lane` pJ per lane, fitted up to `mux_bits_max` bits a read mux; snax-forge D193), and per block one entry per params (so one per type pair) with its `lanes_rule`, a narrow fold's `slope` (`comb_um2`, `e_comb_pj`, `leak_comb_uw` per lane) and points (`lanes`, `depth`, `comb_um2`, `e_comb_pj`, `leak_comb_uw` in µW; FifoPacker's and FifoSlicer's `flops` and `load_bits`). The points that check a rule (W = 8 SimdLanes and W = 32 folds at a narrow pair, the narrow LinkBuffers) are in `char_table.md`, not here. |
| `<tech>/char_synth.csv`, `char_synth_modules.csv` | One row per point and per hierarchical cell (`syn.py --source char`): `synth_dc.csv`'s columns plus `datapath`, `lanes`, `depth`, `op`, `form`, `in_type`, `out_type`, `snax_forge_commit` (X30). |
| `<tech>/char_power.csv` | One row per point and window (`pwr.py --source char`, X33): cycles, fires, the energy groups per cycle, `e_flop_pj`, `e_dyn_pj`, `e_bit_pj`. |
| `<tech>/reports/<point>.zip`, `power_reports/<point>.zip` | DC's kept reports; PT's reports per window and the point's `tb.json` (X51). |
| `runs/` | The run notes, one per round. |

The points are `char/points.json`: 27 blocks at int64, named `<block>/<case>_w<W>` (`lanes/add_w8`, `mac/acc_w32`, `tree/add_w4`, `serial/sum_w16`, `link/d4_w1`; X29), and 54 narrow points named with their pair, `<block>/<case>_w<W>_i<in>_i<out>` (`lanes/mul_w1_i8_i32`, `mac/acc_w8_i16_i64`), `link/d4_w1_i<w>` and `pack/d<d_out>_i<w>` (X89), and 6 slicer points, `slice/d<d_in>_i<w>_n<outLanes>` (X94), made at a later snax-forge commit than the others (`char.json`'s `source.snax_forge_FifoSlicer`). The mixed pairs (X98) are `lanes/mul_w1_i8xi32_i32` and `mac/acc_w8_i8xi32_i32`, a at int8 and b at int32, made at snax-forge `90e9fba` (`source.snax_forge_mixed`), whose Mac at rows 1 unseeded and SimdLanes are the RTL of `0416557`; `in_type` in the CSVs is `int8xint32`. The scalar forms (X99) are seven SimdLanes points at W = 1 made at snax-forge `8d9128c` (`source.snax_forge_scalar`; `SimdLanes.scala` as at `0416557`), named with their scalars: `lanes/mul_w1_i64_kcsr` and `lanes/mul_w1_i8_i32_kcsr` (`a * k`, k from a CSR), `lanes/axpby_w1_i64_k1csr_k2csr` and `lanes/axpby_w1_i32_k1csr_k2csr` (`k1 * a + k2 * b`), `lanes/axpby_w1_i32_k1csr` (`k1 * a + b`), `lanes/axpby_w1_i32_k1_3` (k1 baked to 3) and `lanes/max_w1_i32_k0` (`max(a, 0)`); the CSVs' `form` names the scalars (`kcsr`, `k1csr_k2csr`, `k1=3`, `k=0`). The Mac bank's study (X97) has 9 points that name `rows`, int8 in and int32 out: `mac/acc_w4_i8_i32` (rows 1) and `mac/bank_r<R>_w<W>_i8_i32` at R = 2, 4, 8, 16 and W = 4, 8, their `form` `acc_r<R>`; `char.json` and `char_table.md` leave them out (`char_table.bank_study`).

## How to rebuild

The commands, in order, are in [`docs/TOOL.md`](../../docs/TOOL.md): `char-rtl` (section 2), `syn run '*' --source char` (3), `pwr run '*' --source char` (4), `char-export`, then `char-table` (6); `pixi run python char/checks.py [--power | --bank]` prints the synthesis and power checks for a run note (`--bank`: the Mac bank's study, X97).

`char-rtl` refuses a dirty snax-forge checkout (`--allow-dirty` runs anyway) and records its commit in each bundle's `point.json`; a point is rebuilt from the commit its rows name.
