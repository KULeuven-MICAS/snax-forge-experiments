# CHAR1: snax-forge's blocks alone

snax-forge's catalogue datapaths characterized on their own (no csr, no ctrl), at int64: area and dynamic energy per cycle on nangate45 and nangate15, for a first-order model of each block (X28–X37). Each block is emitted alone by snax-forge's `gen-block`, synthesized with the forge settings (X30) and simulated through fixed windows: busy and idle for the compute blocks, stream for LinkBuffer (X31).

**Start with [`char_table.md`](char_table.md):** every block on both technologies, how each scales, the model's constants and the model against SYN2's accelerators, and the known limits. snax-forge reads `<tech>/char.json`.

## The block model

snax-forge prices a unit's energy for a task from a few constants per technology and two counts the task gives (X37).

| Symbol | Meaning | Where it comes from |
|---|---|---|
| $n_{fire}$ | the unit's fires in the task (one fire = one beat processed) | the task |
| $T$ | the task's cycles | the task |
| $n_{bits}$ | the unit's register bits: lanes × depth × the output's width (0 for SimdLanes) | the block's params; checked equal to DC's `seq_cells` at every point |
| $e_{comb}$ | the block's combinational energy per fire | its busy window's `e_comb_pj` (LinkBuffer: its stream, per load), per point in `char.json` |
| $e_{load}$ | energy per flop bit per cycle when the flop loads new data | the mean busy `e_bit_pj` of the blocks whose flops all load every cycle (Mac, TreeAccumulate, SerialAccumulate busy, LinkBuffer at depth 1): 17.17 fJ on nangate45 |
| $e_{hold}$ | energy per flop bit per cycle when the flop holds | the mean idle `e_bit_pj` of the registered blocks (14 points within 0.2 %): 7.15 fJ on nangate45 (X33) |
| $n_{bits,ctrl}$ | the control unit's flop bits | the design |
| $f_{ctrl}$ | ctrl's energy per cycle over its flops × $e_{hold}$ | the mean over SYN2's 48 forge points: 1.06 on nangate45, 1.12 on nangate15 |

A flop costs $e_{hold}$ every cycle and $e_{load} - e_{hold}$ more on the cycles it loads; a block's logic costs $e_{comb}$ per fire. So a unit's energy over a task, and its control unit's, are

$$E_{unit} = n_{fire}\thinspace\big(e_{comb} + n_{bits}\thinspace(e_{load} - e_{hold})\big) + T\thinspace n_{bits}\thinspace e_{hold}$$

$$E_{ctrl} = f_{ctrl}\thinspace n_{bits,ctrl}\thinspace T\thinspace e_{hold}$$

$e_{fire} = e_{comb} + n_{bits}(e_{load} - e_{hold})$ is the energy of one fire on top of holding. A lane count `char.json` does not hold takes the block's `lanes_rule`: `copy` (W × the 1-lane point: SimdLanes, Mac, LinkBuffer) or `interpolate` (linear in lanes: TreeAccumulate, SerialAccumulate). Against SYN2's accelerators (vecmul, vsum, dot 4, dot 5 at W = 8 and 32, N = 2048) the model's ctrl + datapath lands at 0.992 to 1.037 of the measured energy. It leaves out the csr, the memory and the streamers, which HWCOST prices from [`docs/cost_tables.md`](../../docs/cost_tables.md).

Known limits (numbers in `char_table.md`): an isolated fire of an accumulator costs 25–30 % more than a back-to-back one (X34); nangate45's LinkBuffer stream costs less per flop than a held flop (X35).

## What this folder holds

| Path | What it holds |
|---|---|
| `char_table.md` | The table (`pixi run char-table`), generated from the CSVs below and `char.json` (refused if not current). |
| `<tech>/char.json` | The table snax-forge reads (`pixi run char-export`, X37): `flop` (`area_um2`, `e_load_fj`, `e_hold_fj`), `ctrl.counter_factor` ($f_{ctrl}$), and per block its params, `lanes_rule` and points (`lanes`, `depth`, `comb_um2`, `e_comb_pj`). |
| `nangate45/char_cg.json` | The same table from the clock-gated runs (`pixi run char-export --clk-gate`, X83): an integrated clock gate counted as a sequential cell, `flop.area_um2` the mean of `seq_area / seq_cells`, ctrl's factor rescaled so E_ctrl stays `char.json`'s. Not read by snax-forge yet. |
| `<tech>/char_synth.csv`, `char_synth_modules.csv` | One row per point and per hierarchical cell (`syn.py --source char`): `synth_dc.csv`'s columns plus `datapath`, `lanes`, `depth`, `op`, `form`, `snax_forge_commit` (X30). |
| `<tech>/char_power.csv` | One row per point and window (`pwr.py --source char`, X33): cycles, fires, the energy groups per cycle, `e_flop_pj`, `e_dyn_pj`, `e_bit_pj`. |
| `<tech>/reports/<point>.zip`, `power_reports/<point>.zip` | DC's kept reports; PT's reports per window and the point's `tb.json` (X51). |
| `runs/` | The run notes, one per round. |

The points are `char/points.json`: 27 blocks at int64, named `<block>/<case>_w<W>` (`lanes/add_w8`, `mac/acc_w32`, `tree/add_w4`, `serial/sum_w16`, `link/d4_w1`; X29).

## How to rebuild

```bash
pixi run char-rtl                                                      # all 27 blocks into rtl/char/ (gen-block in ../snax-forge, X28)
pixi run syn run '*' --source char --tech nangate45 -j 4 --cores 4     # DC (X59)
pixi run pwr run '*' --source char --tech nangate45 --cores 16 -j 4    # the windows' energy (docs/power.md, Char)
pixi run char-export                                                   # <tech>/char.json
pixi run char-export --clk-gate                                        # nangate45/char_cg.json from the gated rows (X83)
pixi run char-table                                                    # char_table.md (after char-export)
pixi run python char/checks.py [--power]                               # the synthesis and power checks, as Markdown
```

`char-rtl` refuses a dirty snax-forge checkout (`--allow-dirty` runs anyway) and records its commit in each bundle's `point.json`; a point is rebuilt from the commit its rows name.
