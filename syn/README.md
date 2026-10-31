# syn

ASIC synthesis with Design Compiler, on a technology chosen per run: the Nangate 45 nm and 15 nm Open Cell Libraries. The points come from one of two sources (`--source`): `hls` (the default), hls-exercises' bench points, Vitis's Verilog of one point in hls-exercises' `rtl/`, nothing else, so no FPGA flow and no Vitis are needed; or `forge`, snax-forge's generated accelerators, bundled into this repo's `rtl/forge/` ([the forge source](#the-forge-source)).

## Setup

- `dc_shell` on the path, or `DC_SHELL=/path/to/dc_shell`.
- hls-exercises checked out next to this repo, so the points are at `../hls-exercises/rtl/` from the repo root. Elsewhere: `SYN_RTL=/path/to/hls-exercises/rtl`.
- RTL_flow_Nangate15 next to this repo too, holding both libraries. Elsewhere: `SYN_LIB_NANGATE45=/path/to/NangateOpenCellLibrary_typical.db` and `SYN_LIB_NANGATE15=/path/to/NanGate_15nm_OCL_typical_conditional_nldm.db`.

```
<parent>/
  hls-exercises/            writes rtl/<tier>/<kernel>/<point>/filelist.f
  snax-forge-experiments/   this repo: syn/ reads those, results/ keeps the summaries
  RTL_flow_Nangate15/       tech/nangate45/NangateOpenCellLibrary_typical.db
                            tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db
```

## Environment

The repo has its own pixi workspace (`pixi.toml` at the root: Python 3.11 and numpy, nothing else). Run `pixi install` once from the repo root, then run every script through pixi: `pixi run syn ...` (tasks run from the repo root and take their arguments after the task name). The EDA tools (`dc_shell`, and later `vsim`, `pt_shell`, `lmutil`) come from the shell's PATH; pixi only puts its own `bin/` in front.

## Technologies

A technology is one file, `tech/<tech>.json`. `run` needs `--tech <tech>`; there is no default library.

| field | nangate45 | nangate15 |
|---|---|---|
| `lib_env` (overrides `lib_default`) | `SYN_LIB_NANGATE45` | `SYN_LIB_NANGATE15` |
| `lib_default` (from the repo root) | `../RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db` | `../RTL_flow_Nangate15/tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db` |
| `lib_name` | `NangateOpenCellLibrary` | `NanGate_15nm_OCL` |
| `units` | time `1ns`, cap `1ff` | time `1ps`, cap `1ff` |
| `drive_cell` | `INV_X4` | `INV_X4` |
| `out_load_ff` | 25.0 (four INV_X4 inputs, 4 x 6.258) | 13.2 (four INV_X4 inputs, 4 x 3.301) |
| `max_transition_ns` | 0.25 | 0.25 |
| `wire_load` | `off` (the library has models; none is used) | `none` (the library has none) |
| `fixes` | none | none |
| corner (`notes`) | typical, 1.10 V, 25 C | typical, 0.80 V, 25 C |

nangate15's flops all have an async reset or set (DFFRNQ_X1, DFFSNQ_X1), so Vitis's synchronous reset costs a flop with an unused reset pin plus reset logic.

### Units and scaling

`constraints.sdc` holds physical values only, in ns and fF. syn.py derives from the tech file's units `T_SCALE`, library time units per ns (1 on nangate45, 1000 on nangate15), and `C_SCALE`, library capacitance units per fF (1 on both), and DC multiplies every constraint by them: the clock is `$clock_ns * T_SCALE`, the uncertainties 0.1 ns (setup) and 0.02 ns (hold), the I/O delays 0.01 ns, the max transition the tech file's, and the output load `out_load_ff * C_SCALE`. `set_max_fanout 32` has no unit. The clock is 10 ns on both.

### The unit check

Right after the library is set, `dc_syn.tcl` reads the library's name and its time and capacitance units from `report_lib`. If any differs from the tech file, it prints both and exits with code 2 before reading any RTL; the summary row says `failed: library mismatch`. A .db in other units would otherwise take every constraint 1000x off with no error (a 10 ns clock read as 10 ps).

It then writes `reports/lib_info.txt`: the library name and units as read, the operating condition (process, voltage, temperature), the library's default wire-load model, DC's `$sh_product_version`, and `power_default_toggle_rate` and `power_default_static_probability`.

### Wire load

No wire-load model applies on either library. On nangate45, whose library sets `default_wire_load 5K_hvratio_1_1`, `dc_syn.tcl` sets `auto_wire_load_selection false`, removes the library's `default_wire_load` before elaboration and runs `remove_wire_load_model` on the design after link (`auto_wire_load_selection false` alone still leaves `5K_hvratio_1_1`). On nangate15 (`none`) it checks that the library has no default model. Either way `area.rpt` says `No wire load specified` and `power.rpt` has no `Wire Load Model` table; syn.py marks a run whose area report says otherwise as failed.

## Run

A point is named `<tier>/<kernel>/<point>`, the folder under hls-exercises' `rtl/` (for example `done/vecadd/opt_w8`, one hardware point that every size runs on). Patterns are shell globs over those names; quote them.

```bash
pixi run syn list 'done/vecadd/*'                                           # the points a pattern picks
pixi run syn run done/vecadd/opt_w8 --tech nangate45 --dry-run              # print the commands only
pixi run syn run done/vecadd/opt_w8 --tech nangate45                        # one point at 10 ns
pixi run syn run 'done/*/opt_w8' --tech nangate15 -j 2                      # several, 2 DC runs at once
pixi run syn summary --tech nangate15                                       # every nangate15 run so far
pixi run syn list --tech nangate45                                          # the points with a nangate45 row
```

`--source hls|forge` picks the points (default `hls`); `list`, `run` and `summary` all take it. `--clock` is the ASIC clock period in ns (default 10). `--cores` is the cores per DC run (default 16). `-j` is the number of DC runs at once, each of which holds a license. Without `--tech`, `list` lists the points and `summary` shows every technology.

syn.py passes DC: `SYN_FILELIST`, `SYN_LIB_DB` and `SYN_LIB_NAME`, `SYN_TIME_UNIT` and `SYN_CAP_UNIT` (the units to expect), `SYN_T_SCALE` and `SYN_C_SCALE`, `SYN_DRIVE_CELL`, `SYN_OUT_LOAD_FF`, `SYN_MAX_TRANS_NS`, `SYN_WIRE_LOAD`, `SYN_CLOCK_NS` and `SYN_CORES`, and from the source `SYN_FORMAT` (`verilog`; forge `sverilog`), `SYN_CLK_PORT` (`ap_clk`; forge `clk_i`) and `SYN_RST_PORT` (`ap_rst_n`; forge `rst_ni`). `dc_syn.tcl` takes the hls values when the three are not set.

## What a run leaves

Everything under `syn/runs/` stays local; git ignores it. Each technology has its own tree and summary:

```
syn/runs/hls/<tech>/<tier>/<kernel>/<point>[_c<clock>]/   (clock tag only when not 10 ns)
  WORK/            DC's work library
  logs/            dc_shell.log, dc_stdout.log, check_design.log
  reports/         qor, area, area_hierarchy, reference, timing, constraint_setup, clock, port,
                   design_rules, power, power_hierarchy, power_verbose_hierarchy (.rpt), lib_info.txt
  out/             <top>_mapped.v, .sdf
  tech.json        the tech file, the resolved values (.db path, its md5, T_SCALE, C_SCALE,
                   the DC environment) and what DC read into lib_info.txt
syn/runs/hls/<tech>/summary.csv   one row per point and clock
```

Every `run` keeps `results/hls/<tech>/` in step, and that is what is committed:

```
results/hls/<tech>/synth_dc.csv            a copy of the summary
results/hls/<tech>/synth_dc_modules.csv    one row per hierarchical cell
results/hls/<tech>/reports/<tier>/<kernel>/<point>[_c<clock>]/
                                           area.rpt, area_hierarchy.rpt, reference.rpt, power.rpt,
                                           power_hierarchy.rpt, qor.rpt, tech.json, lib_info.txt;
                                           a file over 1 MB is left out and named in skipped.txt
```

Only those eight files are committed per run (`KEPT_REPORTS` at the top of `syn.py`): they are what the area and energy model reads (area and power in total, per level of hierarchy and per cell type in `reference.rpt`), the QoR summary, and what the run ran on (`tech.json`, `lib_info.txt`). Everything else stays in the run folder: `timing.rpt` (the largest, about 30 kB a point), `constraint_setup.rpt`, `clock.rpt`, `port.rpt`, `design_rules.rpt`, `power_verbose_hierarchy.rpt`, the logs, the netlist and the sdf. Those check a run (the clock, the loads, the paths) rather than feed the model, and a rerun rebuilds them.

`port.rpt` covers a sample of ports (clock, reset, the first and last data input and output): the full report runs to hundreds of kB on the wide AXI-stream tops. `design_rules.rpt` holds the design's max transition and max fanout in library units and a tally of every output's max pin load.

## Columns

`synth_dc.csv`, every number plain with its unit in the name:

| column | what it is |
|---|---|
| `point`, `top`, `tech`, `clock_ns` | the point, its top module, the technology, the clock period |
| `status` | `ok`, `ok, timing violated`, `failed: ...` (no area report, library mismatch, a wire-load model applied, power groups that do not sum) or `skipped: needs a RAM macro ...` |
| `errors` | `Error:` lines in `dc_shell.log` |
| `area_um2`, `comb_area_um2`, `seq_area_um2`, `buf_inv_area_um2` | `area.rpt`: total cell, combinational, noncombinational, buf/inv area |
| `cells`, `seq_cells` | number of cells, of sequential cells |
| `crit_path_ns`, `slack_ns` | `qor.rpt`'s critical path length and slack, converted from library units to ns |
| `fmax_mhz` | 1000 / (`clock_ns` - `slack_ns`) |
| `maxcap_nets`, `maxtrans_nets` | `qor.rpt`: Max Cap Violations, Max Trans Violations |
| `dyn_power_uw`, `leak_power_uw` | `power.rpt`'s total dynamic and cell leakage power, in uW |
| `e_clk_pj`, `e_reg_pj`, `e_seq_pj`, `e_comb_pj`, `e_total_pj` | energy per cycle of the power groups clock_network, register, sequential, combinational: (internal + switching) [uW] x `clock_ns` / 1000; the total is their sum, and syn.py checks it against `dyn_power_uw` x `clock_ns` / 1000 |
| `leak_clk_uw`, `leak_reg_uw`, `leak_seq_uw`, `leak_comb_uw` | the same groups' leakage, in uW |
| `lib_md5`, `dc_version` | the .db's md5 and DC's version |
| `date`, `run` | when the row was written, the run folder |

`power.rpt` states its units (`Dynamic Power Units`, `Leakage Power Units`: 1 uW and 1 nW on nangate45, 1 mW and 1 pW on nangate15), and the totals carry their own suffix; syn.py reads both and converts to uW.

`synth_dc_modules.csv`: `point, tech, clock_ns, path, design, area_um2, comb_um2, seq_um2, bbox_um2, dyn_power_uw, leak_power_uw`, one row per hierarchical cell of `area_hierarchy.rpt` (the top, then the paths below it) joined by path with `power_hierarchy.rpt`. `area_um2` is the cell's absolute total, its children included; `comb_um2`, `seq_um2` and `bbox_um2` count only the cell's own level. The power columns include the children and carry about 3 digits: DC's hierarchical power report ignores `-significant_digits`. A flat top gives one row.

## Caveats

- `clock_network` is the flops' clock-pin internal power only: the clock is ideal and there is no clock tree.
- Switching activity is DC's default (`power_default_toggle_rate` 0.1, `power_default_static_probability` 0.5, recorded in `lib_info.txt`), not simulated activity.
- `fmax_mhz` is a lower bound: at 10 ns DC meets timing with room to spare and does not upsize for speed.
- The HLS points are int64 only.
- Run notes in `results/hls/runs/` before 28 Oct 2026 are on gscl45nm (FreePDK45), now retired.
- The DC, library, Questa, PrimeTime and licence pitfalls found so far are in [`docs/PITFALLS.md`](../docs/PITFALLS.md).

## Files

| File | What it is |
|---|---|
| `syn.py` | The driver: picks points, reads the tech file, sets the environment, runs DC in the point's run folder, reads the reports into `summary.csv`, and keeps `results/hls/<tech>/` in step |
| `tech/<tech>.json` | One technology: library, units, driving cell, output load, max transition, wire load |
| `scripts/dc_syn.tcl` | One DC run: reads the point's `filelist.f` (as `SYN_FORMAT`: `verilog`, or `sverilog` for forge), sets the library and checks its name and units, writes `lib_info.txt`, keeps wire-load models out, links with DesignWare, `compile_ultra -no_autoungroup`, writes reports and the mapped netlist |
| `scripts/constraints.sdc` | Clock on `$clk_port` (`ap_clk`; forge `clk_i`) at `$clock_ns`, uncertainties, the tech file's input drive, output load and max transition, small IO delays, all scaled to the library's units, and the reset `$rst_port` (`ap_rst_n`, synchronous; forge `rst_ni`, asynchronous) kept as an ideal network (its tree belongs to place and route) |

## The filelist

hls-exercises' `bench/bench.py` writes `filelist.f` into every point folder in its `rtl/`. It holds the top module on a `# top:` line, then the Verilog files relative to the folder, the top's own file last. Any tool can read it:

```
# top: vecadd
vecadd.v
```

A `# ram:` line names a memory Vitis built. Neither library has RAM cells, and DC would build the memory from flops (hours, and no fair area), so `run` parks such a point with the status `skipped: needs a RAM macro (<files>); <tech> has no RAM cells, RAM1 builds one (OpenRAM)`. `--with-ram` runs it anyway.

## The forge source

`--source forge` synthesizes snax-forge's accelerators: per point, the accelerator `snax_forge_shell_wrapper` (its modules `snax_forge_csr`, `snax_forge_ctrl` and `snax_forge_datapath`, snax-forge `docs/CONTRACTS.md` §17–18), with no streamers, as the HLS blocks have none.

**Where the points come from.** `forge/points.json` lists them: name, snax-forge recipe and W. `pixi run forge-rtl [patterns] [--list] [--dry-run] [-j N] [--allow-dirty]` (`forge/bundles.py`) runs, per point, snax-forge's `sandbox` (the recipe at `--set W=<w>`), `design` (its last `.snaxdfg` on `platforms/snax_forge.json`) and `bundle`, in the snax-forge checkout next to this repo (`SNAX_FORGE`, default `../snax-forge`) and through that checkout's own pixi environment, into `rtl/forge/<point>/`. git ignores `rtl/`: a bundle is rebuilt from its commit. A bundle whose `bundle.json` says `dirty: true` is refused unless `--allow-dirty`. Each bundle gets `point.json` (point, recipe, W, `snax_forge_commit`, `dirty`, date) and `forge-rtl.log` (the three tasks' output). The names join with hls-exercises': vecadd and vecmul `done/<kernel>/forge_w<W>`, vsum_tree `done/vsum/forge_w<W>`, dot_k `done/dot/forge<k>_w<W>`.

**The points.** A forge point is a folder under `rtl/forge/` (`SYN_RTL_FORGE` overrides) holding a `bundle.json`; its top is `bundle.json`'s `top`. Sizes are run-time CSRs, so one bundle serves every N.

**The filelist.** `run` writes the point's `filelist.f` into the run folder: `# top: <top>`, then the bundle's `rtl/files.f` with each path (relative to the bundle's `rtl/`) made absolute. `dc_syn.tcl` reads it as it reads an HLS filelist. There is no `# ram:` handling.

**The ports.** The RTL is SystemVerilog (`SYN_FORMAT=sverilog`); the clock is `clk_i` and the reset `rst_ni`, active low and asynchronous (firtool's flops take the active-high `reset` the wrapper derives from it). `rst_ni` is kept ideal like `ap_rst_n`.

**The results tree.** As for HLS, under `forge` in place of `hls`: runs in `syn/runs/forge/<tech>/<tier>/<kernel>/<point>/` with `syn/runs/forge/<tech>/summary.csv`, committed results in `results/forge/<tech>/` (`synth_dc.csv`, `synth_dc_modules.csv`, `reports/` with `KEPT_REPORTS`). A forge row of `synth_dc.csv` has three more columns after `run`: `recipe`, `W` (from `point.json`) and `snax_forge_commit` (from `bundle.json`).

```bash
pixi run forge-rtl --list 'done/dot/*'                                     # the forge points
pixi run forge-rtl -j 6                                                    # all 48 bundles into rtl/forge/
pixi run syn list --source forge                                           # the bundles syn.py sees
pixi run syn run done/dot/forge3_w4 --source forge --tech nangate45        # one point
pixi run syn summary --source forge                                        # every forge run so far
```
