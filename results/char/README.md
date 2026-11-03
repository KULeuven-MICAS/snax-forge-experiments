# CHAR1: snax-forge's blocks alone

CHAR1 characterizes snax-forge's catalogue datapaths on their own, with no csr and no ctrl around them, at int64: area and dynamic energy per cycle on nangate45 and nangate15, for a first-order model of each block (docs/DECISIONS.md X28 to X37). Each block is emitted alone by snax-forge's `gen-block` (`Emit --block`, C§17) with the asynchronous reset it has inside an accelerator, synthesized with SYN1 and SYN2's settings (X30), and simulated through fixed windows: busy and idle for ElementwiseLanes, Mac, TreeAccumulate and SerialAccumulate, stream for LinkBuffer (X31). The rounds: R0 the blocks and their synthesis, R1 the power flow on six points, R2 the sweep, R3 the table and the X-numbers, R4 `char.json` and the model checked against SYN2 (`runs/`).

**Start with [`char_table.md`](char_table.md):** e_hold, every block with both technologies side by side, how each scales, the model (its constants, e_fire per point, and the model against SYN2's vecmul, vsum, dot 4 and dot 5), and the known limits. snax-forge reads `<tech>/char.json`.

## What this folder holds

| Path | What it holds |
|---|---|
| `char_table.md` | The table (`report/char_table.py`, `pixi run char-table`), generated from the CSVs below and `char.json` (refused if not current); every number computed. |
| `<tech>/char.json` | **The table snax-forge reads** (`report/char_export.py`, `pixi run char-export`; X37), from `char_synth.csv` and `char_power.csv` and, for the counter factor, SYN2's module CSVs: `tech`, `clock_ns`, `units`, `source`; `flop` (`area_um2`, `e_load_fj`, `e_hold_fj`); `ctrl.counter_factor`; `blocks`, per datapath entries of `params` (`hw/chisel/blocks.json`'s but lanes and depth), `lanes_rule` (`copy` or `interpolate`) and `points` (`lanes`, `depth` for LinkBuffer, `comb_um2`, `e_comb_pj`). |
| `<tech>/char_synth.csv` | One row per point (`syn/syn.py --source char`): `synth_dc.csv`'s columns, then `datapath`, `lanes`, `depth`, `op`, `form` and `snax_forge_commit` from the point's `point.json` (X30). |
| `<tech>/char_synth_modules.csv` | One row per hierarchical cell (area and power), as `synth_dc_modules.csv`. |
| `<tech>/reports/<point>/` | The kept reports of each synthesis run (`KEPT_REPORTS`: area, power, reference, qor, `tech.json`, `lib_info.txt`). |
| `<tech>/char_power.csv` | One row per point and window (`sim/pwr.py --source char`): busy and idle for ElementwiseLanes, Mac, TreeAccumulate and SerialAccumulate, stream for LinkBuffer, 47 rows per technology (R2); the window's cycles and fires, the energy per cycle of each PT power group, `e_flop_pj`, `e_dyn_pj`, `e_bit_pj`, `status` and `snax_forge_commit` (X33; [`docs/power.md`](../../docs/power.md), Char). R1's six points are in git at `03b7a83`. |
| `<tech>/power_reports/<point>/<window>/` | PT's `power.rpt` and `switching_activity.rpt` per window, and the point's `tb.json` in `<point>/`. |
| `runs/` | The run notes, one per round (`<date>_char1_r<k>.md`, R0 to R4). |

The points are `char/points.json`: 27 blocks at int64, named `<block>/<case>_w<W>` (`lanes/add_w8`, `mac/acc_w32`, `tree/add_w4`, `serial/sum_w16`, `link/d4_w1`; X29).

## How to rebuild

```bash
pixi run char-rtl                                                      # all 27 blocks into rtl/char/ (gen-block in ../snax-forge, X28)
pixi run syn run '*' --source char --tech nangate45 -j 10 --cores 3    # DC, -j from free licences (X16)
pixi run syn run '*' --source char --tech nangate15 -j 10 --cores 3
pixi run pwr run '*' --source char --tech nangate45                    # the windows' energy (docs/power.md, Char); J from free licences (X16)
pixi run pwr run '*' --source char --tech nangate15
pixi run char-export                                                   # <tech>/char.json
pixi run char-table                                                    # char_table.md (after char-export)
pixi run python char/checks.py                                         # R0's synthesis checks, as Markdown
pixi run python char/checks.py --power                                 # R2's power checks
```

`char-rtl` refuses a dirty snax-forge checkout (`--allow-dirty` runs anyway) and records its commit in each `rtl/char/<point>/point.json`; git ignores `rtl/`, `syn/runs/` and `sim/runs/`, so a point is rebuilt from the commit its rows name.
