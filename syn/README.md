# syn

ASIC synthesis with Design Compiler, on a technology chosen per run: the Nangate 45 nm and 15 nm Open Cell Libraries. The points come from one of five sources (`--source`, [Sources](#sources)): three HLS tools, `hls` (Vitis, the default) and `bambu` from hls-exercises' `rtl/` and `xls` (Google XLS) from dslx-exercises' `rtl/`, each the tool's Verilog of one point and nothing else, so no FPGA flow and no HLS tool are needed; `forge`, snax-forge's generated accelerators, bundled into this repo's `rtl/forge/` ([the forge source](#the-forge-source)); and `char`, snax-forge's blocks alone (CHAR1, `rtl/char/`).

## Setup

- `dc_shell` on the path, or `DC_SHELL=/path/to/dc_shell`.
- hls-exercises checked out next to this repo, so the Vitis and Bambu points are at `../hls-exercises/rtl/` from the repo root. Elsewhere: `SYN_RTL=/path/to/hls-exercises/rtl`.
- dslx-exercises next to it, for the XLS points at `../dslx-exercises/rtl/`. Elsewhere: `SYN_RTL_XLS=/path/to/dslx-exercises/rtl`.
- RTL_flow_Nangate15 next to this repo too, holding both libraries. Elsewhere: `SYN_LIB_NANGATE45=/path/to/NangateOpenCellLibrary_typical.db` and `SYN_LIB_NANGATE15=/path/to/NanGate_15nm_OCL_typical_conditional_nldm.db`.

```
<parent>/
  hls-exercises/            writes rtl/<tier>/<kernel>/<case>_w<W>/filelist.f (Vitis: opt, dace; Bambu: bambu)
  dslx-exercises/           writes rtl/<tier>/<kernel>/xls_w<W>/filelist.f (Google XLS)
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

## Sources

| `--source` | Points from | Cases listed | Format | Clock | Reset | Extra columns |
|---|---|---|---|---|---|---|
| `hls` (default) | `SYN_RTL`, default `../hls-exercises/rtl` | `opt`, `dace` (Vitis) | Verilog | `ap_clk` | `ap_rst_n` | none |
| `bambu` | the same root as `hls` | `bambu` | Verilog | `clock` | `reset` | `ctrl_um2`, `datapath_um2`, `glue_um2` |
| `xls` | `SYN_RTL_XLS`, default `../dslx-exercises/rtl` | `xls` | Verilog | `clk` | `rst` | none |
| `forge` | `SYN_RTL_FORGE`, default `rtl/forge` | every zip with a `bundle.json` | SystemVerilog | `clk_i` | `rst_ni` | [the forge source](#the-forge-source) |
| `char` | `SYN_RTL_CHAR`, default `rtl/char` | every zip with an `emitted.json` | SystemVerilog | `clock` | `reset` | `datapath`, `lanes`, `depth`, `op`, `form`, `snax_forge_commit` |
| `streamer` | `SYN_RTL_STREAMER`, default `rtl/streamer` | every zip with a `config.json` | SystemVerilog | `clock` | `reset` | `depth`, `loops`, `channels`, `rtl_flop_bits`, `opt1207`, `snax_cluster_commit` ([the streamer and xbar sources](#the-streamer-and-xbar-sources)) |
| `xbar` | `SYN_RTL_XBAR`, default `rtl/xbar` | every zip with a `config.json` | SystemVerilog | `clock` | `reset` | `inputs`, `banks`, `rtl_flop_bits`, `opt1207`, `snax_cluster_commit` |
| `xbar_mix` | `SYN_RTL_XBAR_MIX`, default `rtl/xbar_mix` | every zip with a `config.json` | SystemVerilog | `clock` | `reset` | `inputs`, `banks`, `ro`, `wo`, `rtl_flop_bits`, `flops_removed`, `opt1207`, `snax_cluster_commit` ([the xbar_mix source](#the-xbar_mix-source)) |

**Case filters and `MAX_W`.** For the three HLS sources a point is a `*/*/*/filelist.f` folder named `<case>_w<W>`, with `<case>` in the source's cases and W <= `MAX_W` (16, a constant at the top of `syn.py`; docs X38: at most 16 64-bit channels per stream). Any other folder is not listed: Vitis's retired `unopt_w*`, every `*_w32`, a per-size folder such as `opt_n512_w8`, a clock variant such as `opt_w8_c10`, and, for `hls`, Bambu's `bambu_w*` that share its root (docs X39). With today's checkouts: `hls` 60 points (opt 40; dace 15 for vecadd, vecmul and matadd at W 1 to 16, plus `dace_w1` for vsum, dot, relu, axpy and rowsum), `bambu` 40, `xls` 40.

**The port guard.** Before DC starts, `run` reads the `# top:` module's port list from the point's HDL files (ANSI or not) and checks that the source's clock and reset ports are on it. If one is missing the row's status is `failed: no clock port <name> on <top>` (or `reset`) and DC is not run. `pixi run syn check-ports [patterns] [--source S]` runs the guard alone on every listed point and prints one line per point, then the count that pass; it exits 1 if any fails. It needs no DC.

**How each tool resets.** Found in the RTL; the reset port is kept ideal in `constraints.sdc` either way.

| Case | Port | Style | Which flops are reset |
|---|---|---|---|
| Vitis | `ap_rst_n`, active low | synchronous | control only; data registers have no reset (PITFALLS Q1) |
| Bambu | `reset`, active low | mostly synchronous | the FSM (`present_state`) and the stream modules' started flags; the beat registers (`register_SE`) have none; one 1-bit `register_AR` uses the same port asynchronously |
| XLS | `rst`, active high | synchronous | all proc state, 32 to 160 bits (`--reset_data_path=true`) |
| forge | `rst_ni`, active low | asynchronous | its RegInit registers (X22) |
| streamer | `reset`, active high | asynchronous (`RequireAsyncReset`) | the reader's RegInit registers |
| xbar | `reset`, active high | synchronous (a plain Chisel `Module`) | the arbiters' round-robin state |

**Bambu's split (docs X41).** Bambu's top holds a `controller_*` and a `datapath_*` instance. A bambu row adds `ctrl_um2` (the `controller_*` instance with its children), `datapath_um2` (the `datapath_*` instance with its children) and `glue_um2` (`area_um2` minus the two), from the point's `synth_dc_modules.csv` rows (absolute totals, as forge's). A point without exactly one `controller_*` and one `datapath_*` row fails (`failed: Bambu split (...)`). Bambu's `datapath_*` also holds its loop counter and its stream interfaces. Vitis and XLS rows report totals only: their netlists are flat, and a split would have to be inferred.

## Run

A point is named `<tier>/<kernel>/<point>`, the folder under the source's `rtl/` (for example `done/vecadd/opt_w8`, one hardware point that every size runs on). Patterns are shell globs over those names; quote them.

```bash
pixi run syn list 'done/vecadd/*'                                           # the points a pattern picks
pixi run syn run done/vecadd/opt_w8 --tech nangate45 --dry-run              # print the commands only
pixi run syn run done/vecadd/opt_w8 --tech nangate45                        # one point at 10 ns
pixi run syn run 'done/*/opt_w8' --tech nangate15 -j 2                      # several, 2 DC runs at once
pixi run syn summary --tech nangate15                                       # every nangate15 run so far
pixi run syn list --tech nangate45                                          # the points with a nangate45 row
pixi run syn list --source bambu                                            # Bambu's points
pixi run syn run done/dot/xls_w16 --source xls --tech nangate45 --dry-run   # an XLS point
pixi run syn check-ports --source bambu                                     # the port guard alone, every point
pixi run syn run done/dot/forge3_w8 --source forge --tech nangate45 --clk-gate   # the same point, clock-gated (X79)
```

`--source hls|bambu|xls|forge|char` picks the points (default `hls`); `list`, `run`, `summary` and `check-ports` all take it. `--clock` is the ASIC clock period in ns (default 10). `--cores` is the cores per DC run (default 16). `-j` is the number of DC runs at once, each of which holds a license. Without `--tech`, `list` lists the points and `summary` shows every technology.

syn.py passes DC: `SYN_FILELIST`, `SYN_LIB_DB` and `SYN_LIB_NAME`, `SYN_TIME_UNIT` and `SYN_CAP_UNIT` (the units to expect), `SYN_T_SCALE` and `SYN_C_SCALE`, `SYN_DRIVE_CELL`, `SYN_OUT_LOAD_FF`, `SYN_MAX_TRANS_NS`, `SYN_WIRE_LOAD`, `SYN_CLOCK_NS` and `SYN_CORES`, and from the source `SYN_FORMAT`, `SYN_CLK_PORT` and `SYN_RST_PORT` ([Sources](#sources)). `dc_syn.tcl` takes the hls values when the three are not set. The dry run prints the port guard's result and these variables.

**Clock gating (X79).** `--clk-gate` sets `SYN_CLK_GATE_ENABLE=1`, which turns on `dc_syn.tcl`'s `CLK_GATE_ENABLE`: `scripts/clock_gating.tcl` is sourced before the compile (it stops the run if the library has no `latch_posedge` integrated clock gate, then sets the style: latch-based integrated gates, positive edge, at least 2 bits a bank, through the hierarchy), the compile is `compile_ultra -no_autoungroup -gate_clock`, and three reports join the others: `clock_gating.rpt` (`report_clock_gating`), `clock_gating_elements.rpt` (each gate with the bits it gates) and `clock_gating_ungated.rpt` (each ungated register and why), kept whatever their size. The run is tagged `_cg` after the clock tag (`<point>[_c<clock>]_cg.zip`), and its rows have `clk_gate` 1; the CSVs merge on point, clock and `clk_gate`, so it sits beside the ungated run and never replaces it. A cluster point turns it on with `"syn": {"clk_gate": true}` in `cluster/points.json` instead: its own name tells it apart (no `_cg` tag), and its row's `clk_gate` comes from the environment DC ran with. Off by default; every other run is as before.

## What a run leaves

Everything under `syn/runs/` stays local; git ignores it. Each source and technology has its own tree and summary (`<source>` is `hls`, `bambu`, `xls`, `forge` or `char`). DC works in the point's run folder; when it ends, `syn.py` packs what is kept into the point's zip next to it (`KEEP_RUN` at the top of `syn.py`, docs X51), test-reads the zip and deletes the folder, scratch with it. Everything that reads a run afterwards (the summary row, `synth_dc_modules.csv`, the committed reports, `sim/pwr.py` and `pt_power.tcl`) reads the zip; `pixi run arc ls <zip>` lists it and `pixi run arc cat <zip> <member>` prints a member.

```
syn/runs/<source>/<tech>/<tier>/<kernel>/<point>[_c<clock>][_cg].zip   (clock tag only when not 10 ns, _cg with --clk-gate)
  out/<top>_mapped.v, tech.json, logs/dc_shell.log, logs/dc_stdout.log,
  reports/{area,area_hierarchy,reference,power,power_hierarchy,qor,path_classes}.rpt, reports/lib_info.txt
syn/runs/<source>/<tech>/summary.csv   one row per point and clock
```

The run folder, while DC runs (all but the zip's members is scratch):

```
syn/runs/<source>/<tech>/<tier>/<kernel>/<point>[_c<clock>]/
  WORK/            DC's work library
  logs/            dc_shell.log, dc_stdout.log, check_design.log
  reports/         qor, area, area_hierarchy, reference, timing, constraint_setup, clock, port,
                   design_rules, power, power_hierarchy, power_verbose_hierarchy, path_classes
                   (.rpt), lib_info.txt
  out/             <top>_mapped.v (and .sdf with --sdf, X69)
  tech.json        the tech file, the resolved values (.db path, its md5, T_SCALE, C_SCALE,
                   the DC environment) and what DC read into lib_info.txt
```

Every `run` keeps `results/<source>/<tech>/` in step, and that is what is committed (char's two CSVs are named `char_synth.csv` and `char_synth_modules.csv`):

```
results/<source>/<tech>/synth_dc.csv            a copy of the summary
results/<source>/<tech>/synth_dc_modules.csv    one row per hierarchical cell
results/<source>/<tech>/reports/<tier>/<kernel>/<point>[_c<clock>][_cg].zip
                                           area.rpt, area_hierarchy.rpt, reference.rpt, power.rpt,
                                           power_hierarchy.rpt, qor.rpt, path_classes.rpt, tech.json,
                                           lib_info.txt (and with --clk-gate the three clock_gating*.rpt,
                                           whatever their size); a file over 1 MB is left out and named in
                                           skipped.txt
```

Only those nine files are committed per run (`KEPT_REPORTS` at the top of `syn.py`): they are what the area and energy model reads (area and power in total, per level of hierarchy and per cell type in `reference.rpt`), the QoR summary, the path-class slacks, and what the run ran on (`tech.json`, `lib_info.txt`). The run's zip keeps those plus the netlist and the two DC logs; everything else is scratch, deleted with the run folder: `timing.rpt` (the largest, about 30 kB a point), `constraint_setup.rpt`, `clock.rpt`, `port.rpt`, `design_rules.rpt`, `power_verbose_hierarchy.rpt`, `check_design.log`, the sdf (written only with `--sdf`, X69), `default.svf`, `WORK/` and `alib-52/` (X51). Those check a run (the clock, the loads, the paths) rather than feed the model, and a rerun rebuilds them. Each committed report zip is deterministic (X51): a rerun with the same reports gives the same bytes, so it changes in git only when a report does (DC's `Date` line and `qor.rpt`'s CPU times are enough, PITFALLS Z1).

`port.rpt` covers a sample of ports (clock, reset, the first and last data input and output): the full report runs to hundreds of kB on the wide AXI-stream tops. `design_rules.rpt` holds the design's max transition and max fanout in library units and a tally of every output's max pin load.

## Columns

`synth_dc.csv`, every number plain with its unit in the name:

| column | what it is |
|---|---|
| `point`, `top`, `tech`, `clock_ns` | the point, its top module, the technology, the clock period |
| `status` | `ok`, `ok, timing violated`, `failed: ...` (no clock or reset port on the top, no area report, `licence (<the line>)`, library mismatch, a wire-load model applied, power groups that do not sum, Bambu's split) or `skipped: needs a RAM macro ...` |
| `errors` | `Error:` lines in `dc_shell.log` |
| `area_um2`, `comb_area_um2`, `seq_area_um2`, `buf_inv_area_um2` | `area.rpt`: total cell, combinational, noncombinational, buf/inv area |
| `cells`, `seq_cells` | number of cells, of sequential cells |
| `crit_path_ns`, `slack_ns` | `qor.rpt`'s critical path length and slack, converted from library units to ns |
| `fmax_mhz` | 1000 / (`clock_ns` - `slack_ns`) |
| `slack_in2reg_ns`, `slack_reg2reg_ns`, `slack_reg2out_ns`, `slack_in2out_ns` | the worst setup slack of each path class (docs X40), from `path_classes.rpt`, in ns; empty when the class has no path, and in rows synthesized before HSYN1 R3 |
| `maxcap_nets`, `maxtrans_nets` | `qor.rpt`: Max Cap Violations, Max Trans Violations |
| `dyn_power_uw`, `leak_power_uw` | `power.rpt`'s total dynamic and cell leakage power, in uW |
| `e_clk_pj`, `e_reg_pj`, `e_seq_pj`, `e_comb_pj`, `e_total_pj` | energy per cycle of the power groups clock_network, register, sequential, combinational: (internal + switching) [uW] x `clock_ns` / 1000; the total is their sum, and syn.py checks it against `dyn_power_uw` x `clock_ns` / 1000 |
| `leak_clk_uw`, `leak_reg_uw`, `leak_seq_uw`, `leak_comb_uw` | the same groups' leakage, in uW |
| `lib_md5`, `dc_version` | the .db's md5 and DC's version |
| `date`, `run` | when the row was written, the run folder (its zip is `<run>.zip`) |

`power.rpt` states its units (`Dynamic Power Units`, `Leakage Power Units`: 1 uW and 1 nW on nangate45, 1 mW and 1 pW on nangate15), and the totals carry their own suffix; syn.py reads both and converts to uW.

A forge row has seven more columns after `run`, described in [the forge source](#the-forge-source): `recipe`, `W`, `snax_forge_commit`, `csr_um2`, `ctrl_um2`, `datapath_um2`, `glue_um2`. A bambu row has three: `ctrl_um2`, `datapath_um2`, `glue_um2` ([Sources](#sources)).

**Path classes.** After compile and the other reports, `dc_syn.tcl` measures four path classes with `get_timing_paths -delay_type max -max_paths 1 -from ... -to ...` and nothing else (no `group_path`, nothing that could change the compile): in2reg (inputs to register data pins), reg2reg (register clock pins to register data pins), reg2out (register clock pins to outputs) and in2out (inputs to outputs). Inputs are every input but the clock and the reset port. `path_classes.rpt` has one line per class: the class, the slack in library time units (`none` when there is no path), the start point and the endpoint. XLS's points are one combinational stage, so their in2out slack is what `fmax_mhz` hides.

`synth_dc_modules.csv`: `point, tech, clock_ns, path, design, area_um2, comb_um2, seq_um2, bbox_um2, dyn_power_uw, leak_power_uw`, one row per hierarchical cell of `area_hierarchy.rpt` (the top, then the paths below it) joined by path with `power_hierarchy.rpt`. `area_um2` is the cell's absolute total, its children included; `comb_um2`, `seq_um2` and `bbox_um2` count only the cell's own level. The power columns include the children and carry about 3 digits: DC's hierarchical power report ignores `-significant_digits`. A flat top gives one row.

## Licence errors

A DC run that fails on a licence is rerun once by `run` itself (docs X17, PITFALLS L1). After each DC run, `syn.py` looks in `logs/dc_shell.log` and `logs/dc_stdout.log` for a licence failure (`LICENCE_ERROR` at the top of `syn.py`): a line with `licensing error`, `Unable to obtain feature` or `is not enabled. (DCSH-1)`, or an `Error:` or `Fatal:` line that names a licence. A bare "license" is not enough, as every good run's banner says `license agreement` and its DesignWare table `Licensed DW Building Blocks`. On a match it prints `retry <point> on <tech>: licence error: <the line>`, empties the run folder and runs DC again; the run ends with `licence retries: <n> (<points>)`. After a second licence failure the row's status is `failed: licence (<the line>)`. A rerun that fails otherwise gets the usual status. This applies to every source.

## Caveats

- `clock_network` is the flops' clock-pin internal power only: the clock is ideal and there is no clock tree.
- Switching activity is DC's default (`power_default_toggle_rate` 0.1, `power_default_static_probability` 0.5, recorded in `lib_info.txt`), not simulated activity.
- `fmax_mhz` is a lower bound: at 10 ns DC meets timing with room to spare and does not upsize for speed.
- The HLS points are int64 only.
- The DC, library, Questa, PrimeTime and licence pitfalls found so far are in [`docs/PITFALLS.md`](../docs/PITFALLS.md).

## Files

| File | What it is |
|---|---|
| `syn.py` | The driver: picks points, checks their clock and reset ports, reads the tech file, sets the environment, runs DC in the point's run folder, reads the reports into `summary.csv`, and keeps `results/<source>/<tech>/` in step |
| `tech/<tech>.json` | One technology: library, units, driving cell, output load, max transition, wire load |
| `scripts/dc_syn.tcl` | One DC run: reads the point's `filelist.f` (as `SYN_FORMAT`: `verilog`, or `sverilog` for forge, char, streamer and xbar), sets the library and checks its name and units, writes `lib_info.txt`, keeps wire-load models out, links with DesignWare, `compile_ultra -no_autoungroup`, writes reports, the path classes and the mapped netlist |
| `scripts/constraints.sdc` | Clock on `$clk_port` ([Sources](#sources)) at `$clock_ns`, uncertainties, the tech file's input drive, output load and max transition, small IO delays, all scaled to the library's units, and the reset `$rst_port` kept as an ideal network (its tree belongs to place and route) |

## The filelist

hls-exercises' `bench/bench.py` (Vitis) and `bench/bambu.py` (Bambu), and dslx-exercises for XLS, write `filelist.f` into every point folder in their `rtl/`. It holds the top module on a `# top:` line, then the Verilog files relative to the folder (Vitis puts the top's own file last; Bambu its `panda_libtech.v` library). Any tool can read it:

```
# top: vecadd
vecadd.v
```

A `# ram:` line names a memory Vitis built. Neither library has RAM cells, and DC would build the memory from flops (hours, and no fair area), so `run` parks such a point with the status `skipped: needs a RAM macro (<files>); <tech> has no RAM cells, RAM1 builds one (OpenRAM)`. `--with-ram` runs it anyway.

## The forge source

`--source forge` synthesizes snax-forge's accelerators: per point, the accelerator `snax_forge_shell_wrapper` (its modules `snax_forge_csr`, `snax_forge_ctrl` and `snax_forge_datapath`, snax-forge `docs/CONTRACTS.md` §17–18), with no streamers, as the HLS blocks have none.

**Where the points come from.** `forge/points.json` lists them: name, snax-forge recipe and W. `pixi run forge-rtl [patterns] [--list] [--dry-run] [-j N] [--allow-dirty]` (`forge/bundles.py`) runs, per point, snax-forge's `sandbox` (the recipe at `--set W=<w>`), `design` (its last `.snaxdfg` on `platforms/snax_forge.json`) and `bundle`, in the snax-forge checkout next to this repo (`SNAX_FORGE`, default `../snax-forge`) and through that checkout's own pixi environment, into `rtl/forge/<point>/`, then packs the folder into `rtl/forge/<point>.zip` and deletes it (X51). git ignores `rtl/`: a bundle is rebuilt from its commit. A bundle whose `bundle.json` says `dirty: true` is refused unless `--allow-dirty`. Each bundle gets `point.json` (point, recipe, W, `snax_forge_commit`, `dirty`, date) and `forge-rtl.log` (the three tasks' output). The names join with hls-exercises': vecadd and vecmul `done/<kernel>/forge_w<W>`, vsum_tree `done/vsum/forge_w<W>`, dot_k `done/dot/forge<k>_w<W>`.

**The points.** A forge point is a zip under `rtl/forge/` (`SYN_RTL_FORGE` overrides) holding a `bundle.json`; its top is `bundle.json`'s `top`, read from the zip. Sizes are run-time CSRs, so one bundle serves every N.

**The filelist.** `run` unpacks the bundle into `tmp/` for the length of the DC run (deleted after, also on a failure) and writes the point's `filelist.f` into the run folder: `# top: <top>`, then the bundle's `rtl/files.f` with each path (relative to the bundle's `rtl/`) in the unpacked bundle. The port guard reads the sources straight from the zip. `dc_syn.tcl` reads it as it reads an HLS filelist. There is no `# ram:` handling.

**The ports.** The RTL is SystemVerilog (`SYN_FORMAT=sverilog`); the clock is `clk_i` and the reset `rst_ni`, active low and asynchronous (firtool's flops take the active-high `reset` the wrapper derives from it). `rst_ni` is kept ideal like `ap_rst_n`.

**The results tree.** As for the HLS sources, under `forge`: runs in `syn/runs/forge/<tech>/<tier>/<kernel>/<point>.zip` with `syn/runs/forge/<tech>/summary.csv`, committed results in `results/forge/<tech>/` (`synth_dc.csv`, `synth_dc_modules.csv`, `reports/` with one zip of `KEPT_REPORTS` per point). A forge row of `synth_dc.csv` has seven more columns after `run`: `recipe`, `W` (from `point.json`), `snax_forge_commit` (from `bundle.json`), and the area split of the wrapper, in um2: `csr_um2`, `ctrl_um2` and `datapath_um2` (the absolute total, children included, of the rows of `synth_dc_modules.csv` whose design is `snax_forge_csr`, `snax_forge_ctrl` and `snax_forge_datapath`, the keys of `bundle.json`'s `modules`), and `glue_um2` = `area_um2` minus the three.

**The glue.** DC's boundary optimization is left on, so forge compiles like the HLS points (`compile_ultra -no_autoungroup`). It moves a few cells to the wrapper's own level: the inverter that turns `rst_ni` into the active-high `reset` of firtool's flops, and inverters on outputs taken out of the modules (`dot_3` at W = 4: 2.1 um2 on nangate45, 0.3 um2 on nangate15). `glue_um2` is their area. `run` prints a point whose glue is negative or above 1 % of the total (`GLUE_MAX`), or that has no row for one of the three modules (then the glue is empty); it does not fail it.

```bash
pixi run forge-rtl --list 'done/dot/*'                                     # the forge points
pixi run forge-rtl -j 6                                                    # all 48 bundles into rtl/forge/
pixi run syn list --source forge                                           # the bundles syn.py sees
pixi run syn run done/dot/forge3_w4 --source forge --tech nangate45        # one point
pixi run syn summary --source forge                                        # every forge run so far
```

## The streamer and xbar sources

`--source streamer` and `--source xbar` (X52) synthesize snax_cluster's streamer reader alone (`strm__C0_Reader`, as the Streamer uses it) and its TCDM sparse interconnect (`SparseInterconnect`), one point per grid value: `rtl/streamer/d<depth>_l<loops>_c<channels>.zip` and `rtl/xbar/i<inputs>_b<banks>.zip`, which `pixi run strm-rtl` writes (`strm/README.md`).

**The points.** Every zip there with a `config.json`; the top is its `filelist.f`'s `# top:` line. `run` unpacks the zip into `tmp/` for the DC run and writes the run folder's `filelist.f` with the unpacked `<top>.sv`. Settings as every source: X1 to X4, 10 ns, `compile_ultra -no_autoungroup`. `run` starts the largest points first (xbar by inputs x banks, streamer by channels x depth, then loops), so the longest runs do not end the batch alone.

**The flop check.** A row adds `rtl_flop_bits`, the register and memory bits the bundle's RTL declares under the top (`strm/gen.py`'s `flop_bits`, firtool's simulation-only `_RANDOM*` temporaries left out, PITFALLS SC7), and `opt1207`, the registers DC removed as unloaded (its unique OPT-1207 lines). A row whose `seq_cells` differs from `rtl_flop_bits` is printed (`flops <point> on <tech>: DC <n> sequential cells, RTL <m> bits, <k> OPT-1207`) and stays `ok` (X82): ungated, STRM1 found every point equal; a clock-gated run counts its integrated gates as sequential cells too. Rows also carry the grid's params and `snax_cluster_commit` (from `config.json`).

```bash
pixi run syn list --source streamer
pixi run syn run '*' --source xbar --tech nangate45 -j 4 --cores 4
pixi run syn run 'd8_*' --source streamer --tech nangate45 -j 4 --cores 4
```

`rtl/xbar/` also holds `i36_b32` (`strm/grid.json`'s `extra`, the base of xbar_mix's cluster points), so `syn run '*' --source xbar` would synthesize it too; it is not one of STRM1's 27 points and not in `results/xbar/`.

## The xbar_mix source

`--source xbar_mix` (X70) synthesizes an xbar point's `SparseInterconnect` inside `strm/xbar_mix.py`'s wrapper, top `xbar_mix`: inputs `0..ro-1` read-only (`bits_write`, `bits_data`, `bits_amo` tied 0), `ro..ro+wo-1` write-only (`bits_write` 1, `bits_amo` 0, response data open), the rest read-write, and on every point the ties of snax_cluster's `sparse_interconnect_wrapper.sv.tpl` (every `io_tcdmRsps_*_ready` and `io_memRsps_*_valid` 1, `io_memRsps_*_ready` and `io_memReqs_*_bits_priority` open). The zips are `rtl/xbar_mix/i<inputs>_b<banks>_r<ro>_w<wo>.zip` (`pixi run strm-rtl --set xbar_mix`, `strm/README.md`); `run` treats them as the xbar points, two files in the run's `filelist.f`, largest first by inputs x banks. A row adds `ro` and `wo`; `rtl_flop_bits` is the SparseInterconnect's (the wrapper declares no register), and `flops_removed` is `rtl_flop_bits` minus DC's flops: DC may remove the registers the ties make dead, so a removed flop is printed per point (`flops <point>: DC removed ...`) and does not fail the row. A row with more sequential cells than the RTL declares, or with no count, is printed the same way and stays `ok` (X82).

```bash
pixi run syn run '*' --source xbar_mix --tech nangate45 -j 4 --cores 4
```
