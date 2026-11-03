# CHAR1: snax-forge's blocks alone

CHAR1 characterizes snax-forge's catalogue datapaths on their own, with no csr and no ctrl around them: area (R0), dynamic energy per window (R1 built the flow on six points; R2 runs all 27 on both technologies with the windows the model uses: busy and idle, LinkBuffer's stream), and the table last (R3). Each block is emitted alone by snax-forge's `gen-block` (`Emit --block`, C§17) with the asynchronous reset it has inside an accelerator, and synthesized with SYN1 and SYN2's settings (X1 to X4, X22: 10 ns, no wire-load model, `compile_ultra -no_autoungroup`, boundary optimization on), so a block alone compares with the same module inside SYN2's accelerators.

## What this folder holds

| Path | What it holds |
|---|---|
| `<tech>/char_synth.csv` | One row per point (`syn/syn.py --source char`): `synth_dc.csv`'s columns, then `datapath`, `lanes`, `depth`, `op`, `form` and `snax_forge_commit` from the point's `point.json`. |
| `<tech>/char_synth_modules.csv` | One row per hierarchical cell (area and power), as `synth_dc_modules.csv`. |
| `<tech>/reports/<point>/` | The kept reports of each run (`KEPT_REPORTS`: area, power, reference, qor, `tech.json`, `lib_info.txt`). |
| `<tech>/char_power.csv` | One row per point and window (`sim/pwr.py --source char`), R2's: busy and idle for ElementwiseLanes, Mac, TreeAccumulate and SerialAccumulate, stream for LinkBuffer (47 rows per technology; R1's rows are in git at `char1-r1`): the window's cycles and fires, the energy per cycle of each PT power group, `e_flop_pj`, `e_dyn_pj`, `e_bit_pj`, `status` and `snax_forge_commit` ([`docs/power.md`](../../docs/power.md), Char). |
| `<tech>/power_reports/<point>/<window>/` | PT's `power.rpt` and `switching_activity.rpt` per window, and the point's `tb.json` in `<point>/`. |
| `runs/` | The run notes, one per round (`<date>_char1_r<k>.md`). |

The points are `char/points.json`: 27 blocks at int64, named `<block>/<case>_w<W>` (`lanes/add_w8`, `mac/acc_w32`, `tree/add_w4`, `serial/sum_w16`, `link/d4_w1`).

## How to rebuild

```bash
pixi run char-rtl                                              # all 27 blocks into rtl/char/ (gen-block in ../snax-forge)
pixi run syn run '*' --source char --tech nangate45 -j 10 --cores 3    # DC, -j from free licences (X16)
pixi run syn run '*' --source char --tech nangate15 -j 10 --cores 3
pixi run python char/checks.py                                 # the run note's checks, as Markdown
pixi run pwr run '*' --source char --tech nangate45             # the windows' energy (docs/power.md, Char); J from free licences (X16)
pixi run pwr run '*' --source char --tech nangate15
pixi run python char/checks.py --power                         # R2's checks
```

`char-rtl` refuses a dirty snax-forge checkout (`--allow-dirty` runs anyway) and records its commit in each `rtl/char/<point>/point.json`; git ignores `rtl/` and `syn/runs/`, so a point is rebuilt from the commit its rows name.
