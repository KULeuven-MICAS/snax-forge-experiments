# snax-forge-experiments

This repo collects the data from all snax-forge experiments in one place. The data comes from
several sources, and this repo also holds the scripts that depend on a technology: synthesis
scripts and post-synthesis simulations.

The tools that generate RTL never depend on this repo:

- [hls-exercises](https://github.com/rgantonio/hls-exercises) writes the Vitis and Bambu points.
- [dslx-exercises](https://github.com/rgantonio/dslx-exercises) writes the Google XLS points.
- [snax-forge](https://github.com/KULeuven-MICAS/snax-forge) writes the generated accelerators.
- snax_cluster and snitch_cluster provide the clusters.

Each source writes its RTL with a `filelist.f`. This repo reads those from checkouts placed next
to it, hooked by hand, with no submodules. PDK files are never committed. They sit next to the
repo too, or are pointed to with environment variables.

```
<parent>/
  snax-forge-experiments/   this repo
  hls-exercises/            rtl/<tier>/<kernel>/<case>_w<W>/filelist.f (Vitis opt, dace; Bambu bambu); results_staging/bambu_cycles.csv
  dslx-exercises/           rtl/<tier>/<kernel>/xls_w<W>/filelist.f (Google XLS); results/xls_cycles.csv
  snax-forge/               recipes/, platforms/; forge/bundles.py runs its sandbox, design and bundle tasks
  RTL_flow_Nangate15/       tech/nangate45/NangateOpenCellLibrary_typical.db
                            tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db
```

**Docs:** [`docs/`](docs/README.md) holds the settled decisions (`DECISIONS.md`, X1, X2, ...) and the tool pitfalls (`PITFALLS.md`); check new work against both.

## Layout

| Folder | What it holds |
|---|---|
| `syn/` | ASIC synthesis with Design Compiler on the Nangate 45 nm and 15 nm Open Cell Libraries, one tech file per technology in `syn/tech/` ([`syn/README.md`](syn/README.md)); five sources (`--source hls`, Vitis, the default; `bambu`; `xls`; `forge`; `char`), the HLS ones at W <= 16 (X38, X39). Runs stay local in `syn/runs/<source>/`. |
| `results/bambu/`, `results/xls/` | Bambu's and XLS's points: `bambu_cycles.csv` and `xls_cycles.csv`, copied byte for byte from hls-exercises and dslx-exercises by `report/import_cycles.py` (`pixi run import-cycles`, X42), each with a `SOURCE` file (repo, commit, path, date); later `<tech>/` with `synth_dc.csv` (bambu rows with `ctrl_um2`, `datapath_um2`, `glue_um2`, X41), `synth_dc_modules.csv` and `reports/` (`syn/syn.py --source bambu` or `xls`). |
| `results/runs/` | Run notes of rounds that span several sources (HSYN1 on), named `<date>_<what>.md`. |
| `results/hls/` | Vitis's points (`hls` is Vitis, X38). hls-exercises' bench summaries (`hls_cycles.csv`, `hls_loops.csv`, `forge_cycles.csv`, `report_<tier>.md`) and the run notes in `runs/`. hls-exercises' `bench/bench.py` writes here. `forge_cycles.csv` (SNAX-GVSoC's and the RTL's counters for forge at the bench's sizes) stays unchanged. |
| `sim/` | Gate-level simulation and PrimePower: `pwr.py` (the driver; `--source hls` or `forge`), `sources/` (tb.json adapters: `hls.py`, `forge.py`), `ref.py`, `tb/`, `scripts/`, and step 0's `probe/` ([`docs/power.md`](docs/power.md)). Runs stay local in `sim/runs/` (forge's in `sim/runs/forge/`). |
| `forge/` | snax-forge's points (`points.json`: name, recipe, W), the driver that bundles them, `bundles.py` (`pixi run forge-rtl`), run in the snax-forge checkout next to this repo ([`syn/README.md`](syn/README.md#the-forge-source)), and `query.py`, which answers the power flow's questions with snax-forge's own code ([`docs/power.md`](docs/power.md#forge---source-forge)). |
| `rtl/forge/` | The bundles, one folder per point (`bundle.json`, `point.json`, `rtl/sv/`, `rtl/files.f`); git ignores `rtl/`, a bundle is rebuilt from its commit. |
| `results/forge/<tech>/` | snax-forge's accelerators per technology (`syn/syn.py --source forge`): `synth_dc.csv` (with `recipe`, `W`, `snax_forge_commit`), `synth_dc_modules.csv`, `reports/`; `power_pt.csv`, `power_pt_modules.csv`, `power_reports/` (`sim/pwr.py --source forge`); run notes in `results/forge/runs/`. |
| `char/`, `rtl/char/`, `results/char/` | CHAR1: snax-forge's catalogue blocks alone (no csr, no ctrl), 27 points at int64 in `char/points.json`, area and dynamic energy on both technologies (X28 to X37): `char/blocks.py` (`pixi run char-rtl`) writes them with snax-forge's `gen-block` into `rtl/char/` (git ignores it), `syn/syn.py --source char` synthesizes them (`char_synth.csv`), `sim/pwr.py --source char` simulates their busy, idle and stream windows (`char_power.csv`), `report/char_export.py` (`pixi run char-export`) writes the table snax-forge reads, `results/char/<tech>/char.json`, and `report/char_table.py` (`pixi run char-table`) writes `results/char/char_table.md`, with the model checked against SYN2 ([`results/char/README.md`](results/char/README.md)). |
| `report/` | `char_export.py` and `char_table.py` (CHAR1, above); `import_cycles.py` (`pixi run import-cycles`): the Bambu and XLS cycle CSVs copied with their provenance (X42). SYN1's and SYN2's analysis scripts and their results were retired in HSYN1 R3 (X43); git history keeps them. |
| `results/hls/<tech>/` | The results per technology (`nangate45`, `nangate15`): `synth_dc.csv`, `synth_dc_modules.csv` and every run's reports in `reports/` (`syn/syn.py`); `power_pt.csv`, `power_pt_modules.csv` and `power_reports/` (`sim/pwr.py`). |

Planned:

- `ram/`: OpenRAM macros, with a `tc_sram`-compatible wrapper for each.
- `cost/`: the fitted area and energy tables per technology, for snax-forge's first-order estimates.

## Run

```bash
pixi install                                                  # once: the repo's Python (docs X15)
pixi run syn list 'done/vecadd/*'                             # Vitis's points (opt, dace; W <= 16)
pixi run syn list --source bambu                              # Bambu's points; --source xls for XLS's
pixi run syn check-ports --source xls                         # the clock and reset port guard alone, no DC
pixi run syn run done/vecadd/opt_w8 --tech nangate45          # one point at 10 ns on nangate45
pixi run syn summary                                          # every run so far, both technologies
pixi run pwr run 'done/vecadd/*' --tech nangate45             # dynamic energy of the synthesized points (docs/power.md)
pixi run forge-rtl -j 2                                       # snax-forge's 48 bundles into rtl/forge/ (X21)
pixi run syn run 'done/*/forge*' --source forge --tech nangate45      # synthesize the forge points (X22)
pixi run pwr run 'done/*/forge*' --source forge --tech nangate45 --size n2048   # their power (X23)
pixi run pwr run 'done/*/*_w*' --tech nangate45 --size n2048            # tier done's HLS points at n2048 (X24)
pixi run char-rtl && pixi run syn run '*' --source char --tech nangate45 && pixi run pwr run '*' --source char --tech nangate45   # CHAR1: the blocks alone
pixi run char-export                                          # CHAR1: results/char/<tech>/char.json, the table snax-forge reads
pixi run char-table                                           # CHAR1: results/char/char_table.md, the model against SYN2
pixi run import-cycles                                        # results/bambu/bambu_cycles.csv and results/xls/xls_cycles.csv with SOURCE (X42)
```

The pixi tasks (`pixi.toml`): `syn`, `pwr`, `forge-rtl`, `char-rtl`, `char-export`, `char-table`, `import-cycles`. SYN1's and SYN2's analysis tasks (`table`, `analysis`, `split`, `control`, `syn2`) were retired in HSYN1 R3 (X43).

## Synthesis

A technology is a JSON file in `syn/tech/`: the library, its time and capacitance units, the driving cell (`INV_X4`), the output load (four `INV_X4` inputs: 25.0 fF on nangate45, 13.2 fF on nangate15), the max transition (0.25 ns) and the wire-load setting (none applies on either). The constraints are written in ns and fF and scaled to the library's units at run time (nangate15's time unit is 1 ps), and DC stops before reading any RTL if the library's name or units differ from the tech file. The clock is 10 ns.

`results/<source>/<tech>/synth_dc.csv` has one row per point: area (total, combinational, sequential, buf/inv), cells, critical path, slack and `fmax_mhz` in ns and MHz, the worst slack of four path classes (in2reg, reg2reg, reg2out, in2out; X40), max-cap and max-transition violations, dynamic and leakage power in uW, energy per cycle per power group in pJ, leakage per group in uW, the library's md5 and DC's version. `synth_dc_modules.csv` has one row per hierarchical cell (area and power). The columns are described in [`syn/README.md`](syn/README.md#columns).

Caveats:

- `clock_network` is the flops' clock-pin power only, with an ideal clock and no clock tree.
- Switching activity is DC's default, not simulated.
- `fmax_mhz` is a lower bound: at 10 ns DC does not upsize for speed.
- The HLS points are int64 only, at W <= 16 (X38).
- Run notes in `results/hls/runs/` before 28 Oct 2026 are on gscl45nm (FreePDK45), now retired.

Python comes from the repo's pixi workspace (`pixi.toml`); the EDA tools from PATH (docs/README.md).
