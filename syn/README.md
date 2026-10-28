# syn

ASIC synthesis with Design Compiler on FreePDK45 (OSU `gscl45nm`). For now the points are hls-exercises' bench points: Vitis's Verilog of one point in hls-exercises' `rtl/`, nothing else, so no FPGA flow and no Vitis are needed. snax-forge's generated accelerators come next, from the same driver.

## Setup

- `dc_shell` on the path, or `DC_SHELL=/path/to/dc_shell`.
- hls-exercises checked out next to this repo, so the points are at `../hls-exercises/rtl/` from the repo root. Elsewhere: `SYN_RTL=/path/to/hls-exercises/rtl`.
- FreePDK45 next to this repo too, so the library is at `../FreePDK45/osu_soc/lib/files/gscl45nm.db`. Elsewhere: `SYN_LIB=/path/to/gscl45nm.db`.

```
<parent>/
  hls-exercises/            writes rtl/<tier>/<kernel>/<point>/filelist.f
  snax-forge-experiments/   this repo: syn/ reads those, results/ keeps the summaries
  FreePDK45/
```

## Run

A point is named `<tier>/<kernel>/<point>`, the folder under hls-exercises' `rtl/` (for example `done/vecadd/opt_w8`, one hardware point that every size runs on). Patterns are shell globs over those names; quote them.

```bash
python3 syn/syn.py list 'done/vecadd/*'                       # the points a pattern picks
python3 syn/syn.py run done/vecadd/opt_w8 --dry-run           # print the commands only
python3 syn/syn.py run done/vecadd/opt_w8                     # one point at 10 ns
python3 syn/syn.py run 'done/*/opt_w8' --clock 5 -j 2         # several, 2 DC runs at once
python3 syn/syn.py summary                                    # every run so far
```

`--clock` is the ASIC clock period in ns (default 10). `--cores` is the cores per DC run (default 16). `-j` is the number of DC runs at once, each of which holds a license.

## What a run leaves

Everything stays in `syn/runs/`, which git ignores. HLS points run under `syn/runs/hls/`:

```
syn/runs/hls/<tier>/<kernel>/<point>[_c<clock>]/   (clock tag only when not 10 ns)
  WORK/            DC's work library
  logs/            dc_shell.log, dc_stdout.log, check_design.log
  reports/         qor, area, area_hierarchy, timing, constraint_setup, power, power_hierarchy, ...
  out/             <top>_mapped.v, .sdf
syn/runs/hls/summary.csv   one row per point and clock: area, cells, critical path, slack, power
                           (copied to results/hls/synth_dc.csv, which is committed)
```

## Files

| File | What it is |
|---|---|
| `syn.py` | The driver: picks points, sets the environment, runs DC in the point's run folder, reads the reports into `summary.csv` |
| `scripts/dc_syn.tcl` | One DC run: reads the point's `filelist.f`, links against `gscl45nm.db` and DesignWare, lifts the library's zero `max_capacitance` limits (below), `compile_ultra -no_autoungroup`, writes reports and the mapped netlist |
| `scripts/constraints.sdc` | Clock on `ap_clk` at `$clock_ns`, uncertainties, `INVX4` input drive, output load, small IO delays, and the synchronous reset `ap_rst_n` kept as an ideal network (its tree belongs to place and route) |

## The filelist

hls-exercises' `bench/bench.py` writes `filelist.f` into every point folder in its `rtl/`. It holds the top module on a `# top:` line, then the Verilog files relative to the folder, the top's own file last. Any tool can read it:

```
# top: vecadd
vecadd_regslice_both.v
vecadd.v
```

## The library's zero max-cap limits

`gscl45nm.db` sets `max_capacitance = 0` on the outputs of AOI21X1, AOI22X1, NAND2X1, NAND3X1, NOR2X1, DFFSR and TBUFX1. Every net those cells drive is then a max-cap violation whatever its load: 522 of 3,988 nets in the first `opt_n512_w8` run. Design rules come before timing in DC, so compile would spend effort and buffers on limits it can never meet.

`dc_syn.tcl` removes those zero limits after linking. If DC refuses to remove a library attribute, it raises them to 10 instead. The log says how many pins it touched, and `summary.csv`'s `maxcap_nets` column shows what is left.
