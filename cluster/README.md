# cluster

A snax-forge design built into snax_cluster's whole cluster, synthesized, run on its netlist and powered per program section (X66–X76). A point is one entry of `points.json` (`point`, `recipe`, `W`, `sets`, `srams` the macro instances it holds, `alone` its accelerator synthesized alone; and the two container images). Points so far: dot 3 at N = 2048 and W = 2, 4, 8, 16 and 32 (`dot3_w<W>`, PWR1 and PWR2).

## Commands

```bash
pixi run cluster rtl dot3_w16            # step 1: the bundle, then the RTL run, plain and with the SRAM macros
pixi run cluster syn dot3_w16 --cores 16 # step 2: DC on the whole cluster (alone on the host, X68)
pixi run cluster gls dot3_w16            # step 3: the netlist in step 1's testbench
pixi run cluster pwr dot3_w16            # PrimePower per program section on the netlist (X73-X76)
pixi run cluster-hwcost dot3_w16         # snax-forge's HWCOST for the point (X72)
pixi run cluster-breakdown --md          # the area in groups, against HWCOST and the accelerator alone (X72)
pixi run cluster-energy --md             # the energy per window in groups, against HWCOST (X74)
pixi run cluster-sweep --md              # a recipe's points over W: run window and area beside HWCOST, sweep.csv and figures (X78)
```

Each step takes snax_cluster from `SNAX_CLUSTER` (default `../snax_cluster`), clean and on `origin/main` unless `--allow-branch`, and records its commit. snax_cluster's make targets run in its container (`podman run --rm -v "$PWD":"$PWD" -w "$PWD" <image>`, the mount the parent folder of the sibling repos). The point's work folder is `tmp/cluster/<point>/`, deleted when the step ends, also on a failure.

## The steps

| Step | What it does | Checks | Kept |
|---|---|---|---|
| `rtl` | `pixi run forge` in snax-forge's image gives the bundle, the ELF, its quiet build (`sw/forge_quiet.elf`, `sw/obs_marks.json`) and `forge_expected.txt`, zipped as `rtl/cluster/<point>.zip` with `provenance.json`; reused while commit and image match. Then `rtl-gen`, clustergen's memory list and X66's `tc_sram_impl.sv`, and two vsim runs: the plain RTL and the RTL with the macros (`SRAM_IMPL`, `SRAM_MODELS`) | D123 on both runs; equal cycles; every `[tc_sram_impl]` print against `srams`; nothing of tech_cells_generic's `tc_sram` compiled | `rtl/` in `sim/runs/cluster/nangate45/<point>.zip`, with `check.json` |
| `syn` | the same `tc_sram_impl.sv` (must equal step 1's), snax_cluster's `gen-syn` list, then DC through `syn/syn.py`'s `cluster` source with `cluster/cluster.sdc` on top of `constraints.sdc` (X68) and `cluster_check.tcl` after the reports | the library and wire-load checks; no unresolved reference; the macros the only black boxes and their count `srams`'s; every leaf cell from Nangate or the macros | `syn/runs/cluster/nangate45/<point>.zip`; a row in `results/cluster/nangate45/synth_dc.csv` (with `macro_um2`, `macros`, both commits); `reports/<point>.zip` with `cluster_check.rpt`, `cluster_ports.rpt` and `tree.txt` |
| `gls` | step 2's netlist compiled into its own library (`work-vsim/gls`) and run in step 1's testbench through snax_cluster's `SIM_TYPE=gate_level_sim`, zero delay, `+initreg+0` | D123; cycles equal to step 1's; the netlist really loaded; RAMCOUNT reads equal to step 1's macro run, writes at most one more (PITFALLS Q14) | `gls/` in the point's `sim/runs` zip |
| `pwr` | part 1: the quiet ELF on the netlist, one VCD from time 0 to the check's mark, cut into one SAIF per program section (X73, X76); part 2: one PrimePower session over the windows (X74) | X9's SAIF checks per window; at least 95 % of the driven nets annotated | `pwr/` and `pt/` in the point's `sim/runs` zip; `results/cluster/nangate45/power_pt.csv` (one row per window) and `power_reports/<point>.zip` |

`dot3_w16` on the one-core cluster (snax-forge D170): 1,261,630 µm², slack +1.232 ns at 10 ns, RTL and netlist PASS in 810 cycles.

## Files

| File | What it is |
|---|---|
| `cluster.py` | the steps' driver (`pixi run cluster rtl|syn|gls|pwr`) |
| `power.py` | `cluster pwr`, parts 1 and 2 |
| `mem.py` | the cluster's `tc_sram_impl.sv`, the macros' models and `sram_models.f` from clustergen's list (X66) |
| `check.py` | D123 and the run checks |
| `cluster.sdc`, `cluster_check.tcl` | X68's extra constraints; the post-synthesis gates |
| `tree.py` | `area_hierarchy.rpt` as an indented tree (`tree.txt`) |
| `groups.json`, `hwcost.py` | the area and energy groups and snax-forge's HWCOST for a point (X72) |
| `eqv_tb.sv` | the Verilator bench of `tc_sram_impl.sv` against tech_cells_generic's (result in its header) |
| `test_*.py` | `pixi run python cluster/test_<name>.py` |

Results in `results/cluster/nangate45/`: `synth_dc.csv`, `reports/`, `power_pt.csv`, `power_reports/`, `hwcost/<point>.json`, `breakdown.json`, `energy.json`, `sweep.csv`, `sweep_energy.png`, `sweep_area.png`; run notes in `results/cluster/runs/`.
