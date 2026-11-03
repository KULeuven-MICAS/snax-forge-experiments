# CHAR1: snax-forge's blocks alone

CHAR1 characterizes snax-forge's catalogue datapaths on their own, with no csr and no ctrl around them: area now (R0), dynamic energy later (R1, R2), and the table last (R3). Each block is emitted alone by snax-forge's `gen-block` (`Emit --block`, C§17) with the asynchronous reset it has inside an accelerator, and synthesized with SYN1 and SYN2's settings (X1 to X4, X22: 10 ns, no wire-load model, `compile_ultra -no_autoungroup`, boundary optimization on), so a block alone compares with the same module inside SYN2's accelerators.

## What this folder holds

| Path | What it holds |
|---|---|
| `<tech>/char_synth.csv` | One row per point (`syn/syn.py --source char`): `synth_dc.csv`'s columns, then `datapath`, `lanes`, `depth`, `op`, `form` and `snax_forge_commit` from the point's `point.json`. |
| `<tech>/char_synth_modules.csv` | One row per hierarchical cell (area and power), as `synth_dc_modules.csv`. |
| `<tech>/reports/<point>/` | The kept reports of each run (`KEPT_REPORTS`: area, power, reference, qor, `tech.json`, `lib_info.txt`). |
| `runs/` | The run notes, one per round (`<date>_char1_r<k>.md`). |

The points are `char/points.json`: 27 blocks at int64, named `<block>/<case>_w<W>` (`lanes/add_w8`, `mac/acc_w32`, `tree/add_w4`, `serial/sum_w16`, `link/d4_w1`).

## How to rebuild

```bash
pixi run char-rtl                                              # all 27 blocks into rtl/char/ (gen-block in ../snax-forge)
pixi run syn run '*' --source char --tech nangate45 -j 10 --cores 3    # DC, -j from free licences (X16)
pixi run syn run '*' --source char --tech nangate15 -j 10 --cores 3
pixi run python char/checks.py                                 # the run note's checks, as Markdown
```

`char-rtl` refuses a dirty snax-forge checkout (`--allow-dirty` runs anyway) and records its commit in each `rtl/char/<point>/point.json`; git ignores `rtl/` and `syn/runs/`, so a point is rebuilt from the commit its rows name.
