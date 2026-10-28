# Run note: syn technology as a setting, nangate45 and nangate15, 28 Oct 2026

syn/ is now technology-neutral. A technology is a file `syn/tech/<tech>.json`, the constraints are written in ns and fF and scaled to the library's units at run time, and DC checks the library's name and units before reading any RTL. Two technologies: nangate45 (Nangate 45 nm Open Cell Library) and nangate15 (Nangate 15 nm Open Cell Library). gscl45nm is retired, along with its rows, its zero-max-cap fix and every mention of it in the flow. Probe: `done/vecadd/opt_w8` on both. Repos: snax-forge-experiments from `cdf36d9`, hls-exercises from `f9e490f`, both clean on main before the change.

## Commands

```bash
git checkout main && git pull && git status --short     # both repos: up to date, clean
rm -rf syn/runs/                                        # gscl45nm runs and step-0 probes (git-ignored)
find . -name __pycache__ -prune -exec rm -rf {} +       # both repos
lmutil lmstat -c 1709@licserv.esat.kuleuven.be -f Design-Compiler   # Vivado's lmutil (lmstat is not on PATH)
#   Total of 10 licenses issued; Total of 1 license in use -> 9 free
#   J = 9 // 4 = 2; nproc 32 -> cores = 32 // 2 = 16 (syn.py's default --cores)
# scratch DC sessions in the scratchpad (not in syn/runs): report_lib parsing, exit 2, wire-load commands,
# report_power -nosplit / -significant_digits, and a hierarchical point (done/vecmul/unopt_w1) for the modules CSV
python3.11 syn/syn.py run done/vecadd/opt_w8 --tech nangate15 --dry-run
python3.11 syn/syn.py run done/vecadd/opt_w8 --tech nangate45 &      # J = 2: both at once, 16 cores each
python3.11 syn/syn.py run done/vecadd/opt_w8 --tech nangate15 &
SYN_LIB_NANGATE15=../RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db \
  python3.11 syn/syn.py run done/vecadd/opt_w8 --tech nangate15      # the unit check: must stop
rm -rf syn/runs/hls/nangate15/done/vecadd/opt_w8 results/hls/nangate15/reports/done/vecadd/opt_w8
#   and its row out of syn/runs/hls/nangate15/summary.csv and results/hls/nangate15/synth_dc.csv
python3.11 syn/syn.py run done/vecadd/opt_w8 --tech nangate15        # the good nangate15 run again
python3.11 syn/syn.py summary; python3.11 syn/syn.py list --tech nangate45
git rm results/hls/synth_dc.csv
```

The probe ran three times: the first run, a rerun after `-significant_digits 6` was added to the power reports, and a third after `port.rpt` was cut to a sample of ports. The area, timing and power numbers were the same in all three. The rows below are from the last run. Each DC run took about 70 s.

## What changed

snax-forge-experiments:

| file | change |
|---|---|
| `syn/tech/nangate45.json` (new) | lib_env `SYN_LIB_NANGATE45`, lib_default `../RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db`, lib_name `NangateOpenCellLibrary`, units 1ns / 1ff, drive_cell `INV_X4`, out_load_ff 25.0 (4 x 6.258), max_transition_ns 0.25, wire_load `off`, fixes `[]`, notes: typical, 1.10 V, 25 C |
| `syn/tech/nangate15.json` (new) | lib_env `SYN_LIB_NANGATE15`, lib_default `../RTL_flow_Nangate15/tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db`, lib_name `NanGate_15nm_OCL`, units 1ps / 1ff, drive_cell `INV_X4`, out_load_ff 13.2 (4 x 3.301), max_transition_ns 0.25, wire_load `none`, fixes `[]`, notes: typical, 0.80 V, 25 C, and the async-reset/set-only flops |
| `syn/syn.py` | `run` requires `--tech` (choices: `syn/tech/*.json`), `list` and `summary` take it as a filter (`list --tech` shows the points with a row in that tech). The library comes from the tech file's lib_env, else lib_default; `SYN_LIB` and `DEFAULT_LIB` are gone. DC gets `SYN_FILELIST`, `SYN_LIB_DB`, `SYN_LIB_NAME`, `SYN_TIME_UNIT`, `SYN_CAP_UNIT`, `SYN_T_SCALE`, `SYN_C_SCALE`, `SYN_DRIVE_CELL`, `SYN_OUT_LOAD_FF`, `SYN_MAX_TRANS_NS`, `SYN_WIRE_LOAD`, `SYN_CLOCK_NS`, `SYN_CORES`. Runs in `syn/runs/hls/<tech>/<tier>/<kernel>/<point>[_c<clock>]/`, summary `syn/runs/hls/<tech>/summary.csv`, copied to `results/hls/<tech>/synth_dc.csv`. Each run writes `tech.json` (tech file, resolved values, .db path and md5, DC environment and return code, parsed `lib_info.txt`). New columns (below), unit conversion of qor times and power, energy per power group with the sum check, `synth_dc_modules.csv`, and the reports copied into results from `write_summary`. Status `failed: library mismatch`, `failed: a wire-load model applied` and `failed: power groups do not sum ...` added. New RAM parking message. Docstring: tech files, env vars, the real 15 nm file name |
| `syn/scripts/dc_syn.tcl` | Reads every value from the environment above. After the library is set: the library name (the loaded library other than gtech/standard.sldb/dw_foundation.sldb) and its `Time Unit` and `Capacitive Load Unit` from `report_lib` (redirect, regexp, `1.000000ff` -> `1ff`); a mismatch prints both and `exit 2` before `analyze`. Writes `reports/lib_info.txt` (library, db, time_unit, cap_unit, operating condition, process, voltage_v, temperature_c, default_wire_load, dc_version = `$sh_product_version`, `power_default_toggle_rate`, `power_default_static_probability`). Zero-max-cap block removed. Wire load: `set auto_wire_load_selection false`; `off`: `remove_attribute [get_libs <lib>] default_wire_load` before elaboration and `remove_wire_load_model [current_design]` after link; `none`: exit 2 if the library has a default model. New reports: `reference.rpt` (`report_reference -nosplit`), `clock.rpt` (`report_clock`, `report_clock -skew`), `port.rpt` (`report_port -verbose -nosplit` on a sample of ports), `design_rules.rpt` (max_transition, max_fanout, tally of every output's max pin load). `report_power` with `-significant_digits 6`, both hierarchical power reports also `-nosplit` (DC accepts it). Header without FreePDK45 / gscl45nm |
| `syn/scripts/constraints.sdc` | clock `$clock_ns * $t_scale`; uncertainty `0.1 * $t_scale` / `0.02 * $t_scale`; I/O delays `0.01 * $t_scale`; `set_max_transition $max_trans_ns * $t_scale`; `set_load $out_load_ff * $c_scale`; `set_driving_cell -lib_cell $drive_cell`; max_fanout 32 unchanged; the FreePDK45 comment replaced |
| `README.md`, `syn/README.md` | tech files, units and scaling, the unit check, wire load, layout, columns, modules CSV, caveats |
| `results/hls/synth_dc.csv` | removed (`git rm`): gscl45nm rows plus the one 28 Oct nangate45 row |
| `results/hls/nangate45/`, `results/hls/nangate15/` (new) | `synth_dc.csv`, `synth_dc_modules.csv`, `reports/done/vecadd/opt_w8/` |

hls-exercises:

| file | change |
|---|---|
| `docs/HLS_VS_FORGE.md` section 6 | Nangate 45 nm and 15 nm Open Cell Libraries, tech files, the constraints, `--tech` in the run command, parking without a library name, OpenRAM macro per technology, output in `snax-forge-experiments/results/hls/<tech>/`; the "open 15 nm library" sentence dropped |
| `README.md` | `<tech>/synth_dc.csv` in the results table, `--tech` in the synthesis commands, a pointer to `results/hls/<tech>/` |
| `bench/tier_*/*/README.md` (8 kernels) | "DC on FreePDK45 at 10 ns" now says the area and critical-path columns are from the retired gscl45nm (FreePDK45) run and that synthesis now runs on the Nangate 45 nm and 15 nm Open Cell Libraries, results in `snax-forge-experiments/results/hls/<tech>/`. The tables keep their gscl45nm numbers until the tiers are resynthesized |

## Probe: done/vecadd/opt_w8 at 10 ns

| column | nangate45 | nangate15 |
|---|---|---|
| `point` | done/vecadd/opt_w8 | done/vecadd/opt_w8 |
| `top` | vecadd | vecadd |
| `tech` | nangate45 | nangate15 |
| `clock_ns` | 10 | 10 |
| `status` | ok | ok |
| `errors` | 0 | 0 |
| `area_um2` | 6057.085922 | 1693.040637 |
| `comb_area_um2` | 3425.282017 | 949.272599 |
| `seq_area_um2` | 2631.803905 | 743.768038 |
| `buf_inv_area_um2` | 53.998000 | 93.536259 |
| `cells` | 1956 | 2521 |
| `seq_cells` | 582 | 582 |
| `crit_path_ns` | 4.54185 | 0.5762699 |
| `slack_ns` | 5.31191 | 9.305025 |
| `fmax_mhz` | 213.3065 | 1438.901 |
| `maxcap_nets` | 0 | 0 |
| `maxtrans_nets` | 0 | 0 |
| `dyn_power_uw` | 374.2914 | 148.5236 |
| `leak_power_uw` | 110.3181 | 56.7788 |
| `e_clk_pj` | 2.285471 | 1.09673 |
| `e_reg_pj` | 0.1877926 | 0.05163097 |
| `e_seq_pj` | 0 | 0 |
| `e_comb_pj` | 1.269652 | 0.3368721 |
| `e_total_pj` | 3.742915 | 1.485233 |
| `leak_clk_uw` | 0 | 0 |
| `leak_reg_uw` | 45.92292 | 26.4116 |
| `leak_seq_uw` | 0 | 0 |
| `leak_comb_uw` | 64.39516 | 30.36722 |
| `lib_md5` | 09a484fa91bd090e4975b6a605c0aa9c | 86fdb9ac95951e07419ef62d7f3323bb |
| `dc_version` | Y-2026.03-SP2 | Y-2026.03-SP2 |
| `date` | 2026-10-28T18:51:42 | 2026-10-28T18:53:27 |
| `run` | syn/runs/hls/nangate45/done/vecadd/opt_w8 | syn/runs/hls/nangate15/done/vecadd/opt_w8 |

`synth_dc_modules.csv` (vecadd is flat, one row each):

```
point,tech,clock_ns,path,design,area_um2,comb_um2,seq_um2,bbox_um2,dyn_power_uw,leak_power_uw
done/vecadd/opt_w8,nangate45,10,vecadd,vecadd,6057.0859,3425.2820,2631.8039,0.0000,374.291,110
done/vecadd/opt_w8,nangate15,10,vecadd,vecadd,1693.0406,949.2726,743.7680,0.0000,148.9,56.8
```

The modules' power is from `power_hierarchy.rpt`, which prints about 3 digits (`1.59e-02  0.133` mW on nangate15) whatever `-significant_digits` says, so 148.9 uW there against 148.5236 in the main row. Tested on a hierarchical point too, `done/vecmul/unopt_w1` on nangate45 (scratch run, not in results): two rows, `vecmul` (area 7525.672, own comb 292.6, seq 307.496, dyn 982.989 uW) and `mul_64s_64s_64_1_1_U1` (6925.576, dyn 935.39 uW), joined by path.

## Checks

| check | result |
|---|---|
| nangate15 clock | `clock.rpt`: `clk 10000.00 {0 5000}`; timing.rpt's path ends at 10000 ps less uncertainty and setup (`data required time 9891.29492`) |
| nangate15 uncertainty | `clock.rpt` (report_clock -skew): Plus 20.00 (hold), Minus 100.00 (setup) |
| nangate15 I/O delays | `port.rpt`: input delay max 10.00, output delay max 10.00; `timing.rpt`: `input external delay 10.00000` |
| nangate15 max transition | `design_rules.rpt`: `max_transition: 250.000000` |
| nangate15 output load | `design_rules.rpt`: `outputs: 518`, `output max pin load rise/fall 13.20/13.20: 518 ports` |
| nangate15 crit_path_ns < 10 | 0.5762699 (qor.rpt: 576.26990 ps, slack 9305.02539 ps) |
| nangate45 wire load | `area.rpt`: `Net Interconnect area: undefined (No wire load specified)`; `power.rpt`: no `Wire Load Model` table (only the `Wire Load Model Mode: top` header line); the same on nangate15 |
| nangate45 output load | `design_rules.rpt`: `output max pin load rise/fall 25.00/25.00: 518 ports` |
| nangate45 uncertainty, delays, transition | 0.10 / 0.02, 0.01, 0.25 |
| every CSV column filled | yes, both rows (no empty field) |
| e_total_pj = dyn_power_uw x clock_ns / 1000 | nangate45 3.742915 vs 3.742914 (rel 2.7e-7); nangate15 1.485233 vs 1.485236 (rel 2.0e-6) |
| synth_dc_modules.csv | one row per technology (above) |
| errors in dc_shell.log | 0 on both |
| unit check | `--tech nangate15` with `SYN_LIB_NANGATE15` on the nangate45 .db: exit 2, no `analyze` in the log, empty `reports/`, status `failed: library mismatch (logs/dc_shell.log)`; run folder, its results reports and summary row deleted afterwards |

The unit check's message:

```
dc_syn.tcl: library mismatch in /users/micas/rantonio/no_backup/kul_main/RTL_flow_Nangate15/tech/nangate45/NangateOpenCellLibrary_typical.db
dc_syn.tcl:   tech file expects  name NanGate_15nm_OCL, time unit 1ps, cap unit 1ff
dc_syn.tcl:   library reports    name NangateOpenCellLibrary, time unit 1ns, cap unit 1ff
```

Wire load, from scratch runs of `compile_ultra` on nangate45: `set auto_wire_load_selection false` plus `remove_wire_load_model` alone still leaves `5K_hvratio_1_1` (area.rpt: `Wire load has zero net area`, power.rpt shows the table). Removing the library's `default_wire_load` is what clears it, with or without `auto_wire_load_selection false`.

The input ports carry the driving cell's library design rules (UID-401, as before): on nangate15 `port.rpt` shows max trans 480.00 and max cap 400.00 on the data inputs, the INV_X4 output's library limits. The design's own max transition is the 250 ps above.

Reports in results (bytes), nothing over 1 MB, nothing skipped:

```
   1039  results/hls/nangate45/reports/done/vecadd/opt_w8/area.rpt
   1800  results/hls/nangate45/reports/done/vecadd/opt_w8/area_hierarchy.rpt
   1073  results/hls/nangate45/reports/done/vecadd/opt_w8/clock.rpt
    281  results/hls/nangate45/reports/done/vecadd/opt_w8/constraint_setup.rpt
    174  results/hls/nangate45/reports/done/vecadd/opt_w8/design_rules.rpt
    383  results/hls/nangate45/reports/done/vecadd/opt_w8/lib_info.txt
   3705  results/hls/nangate45/reports/done/vecadd/opt_w8/port.rpt
   2258  results/hls/nangate45/reports/done/vecadd/opt_w8/power.rpt
   1105  results/hls/nangate45/reports/done/vecadd/opt_w8/power_hierarchy.rpt
   1122  results/hls/nangate45/reports/done/vecadd/opt_w8/power_verbose_hierarchy.rpt
   2484  results/hls/nangate45/reports/done/vecadd/opt_w8/qor.rpt
   2999  results/hls/nangate45/reports/done/vecadd/opt_w8/reference.rpt
   2116  results/hls/nangate45/reports/done/vecadd/opt_w8/tech.json
  28665  results/hls/nangate45/reports/done/vecadd/opt_w8/timing.rpt
   1044  results/hls/nangate15/reports/done/vecadd/opt_w8/area.rpt
   1798  results/hls/nangate15/reports/done/vecadd/opt_w8/area_hierarchy.rpt
   1073  results/hls/nangate15/reports/done/vecadd/opt_w8/clock.rpt
    281  results/hls/nangate15/reports/done/vecadd/opt_w8/constraint_setup.rpt
    176  results/hls/nangate15/reports/done/vecadd/opt_w8/design_rules.rpt
    374  results/hls/nangate15/reports/done/vecadd/opt_w8/lib_info.txt
   3705  results/hls/nangate15/reports/done/vecadd/opt_w8/port.rpt
   2271  results/hls/nangate15/reports/done/vecadd/opt_w8/power.rpt
   1104  results/hls/nangate15/reports/done/vecadd/opt_w8/power_hierarchy.rpt
   1121  results/hls/nangate15/reports/done/vecadd/opt_w8/power_verbose_hierarchy.rpt
   2515  results/hls/nangate15/reports/done/vecadd/opt_w8/qor.rpt
   1909  results/hls/nangate15/reports/done/vecadd/opt_w8/reference.rpt
   2236  results/hls/nangate15/reports/done/vecadd/opt_w8/tech.json
  30359  results/hls/nangate15/reports/done/vecadd/opt_w8/timing.rpt
```

The full `report_port -verbose` was 582,285 B for vecadd (1581 ports) on the first run. Over every point and both technologies that would put about 100 MB of near-identical port lines in git, so `port.rpt` keeps a sample (clock, reset, first and last data input and output) and `design_rules.rpt` tallies the load on all outputs.

## nangate45 against the 28 Oct row

| | 28 Oct (`697f86f`) | now | change |
|---|---|---|---|
| area_um2 | 6057.617922 | 6057.085922 | -0.532 (-0.01 %) |
| comb_area_um2 | 3425.814017 | 3425.282017 | -0.532 (-0.02 %) |
| seq_area_um2 | 2631.803905 | 2631.803905 | 0 |
| buf_inv_area_um2 | 57.19 | 53.998 | -3.192 (-5.6 %) |
| cells | 1963 | 1956 | -7 |
| crit_path_ns | 5.85618 | 4.54185 | -1.31433 (-22.4 %) |
| slack_ns | 3.99712 | 5.31191 | +1.31479 |
| dyn_power_uw | 373.4629 | 374.2914 | +0.8285 (+0.22 %) |
| leak_power_uw | 110.2557 | 110.3181 | +0.0624 (+0.06 %) |

Two inputs changed: no wire-load model (it was `5K_hvratio_1_1`) and a 25 fF output load (it was 0.03 fF). The flops are the same (582, 2631.80). The critical path is 22 % shorter: it runs from `A_TDATA[320]` to `add_ln13_5_reg_378_reg[63]`, and without the wire-load model its nets carry no wire capacitance. Net switching power rose (41.39 uW against 38.97) and internal power fell (332.90 against 334.49). The 28 Oct reports were deleted with syn/runs/, so the old critical path cannot be compared stage by stage.

nangate15 against nangate45: 0.28x the area, 0.13x the critical path, 0.40x the energy per cycle and 0.51x the leakage. Its 582 flops are 743.77 um2, all DFFSNQ_X1 (async set, pin unused; `reference.rpt`). It has more cells (2521 against 1956) and 1.7x the buf/inv area.
