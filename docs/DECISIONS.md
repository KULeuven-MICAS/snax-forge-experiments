# Decisions

What this repo has settled. Each entry: date, decision, why, source (run note in `results/hls/runs/` or commit). A later decision that changes one adds a new number and says which it replaces; numbers are not reused.

| X | title |
|---|---|
| [X1](#x1-libraries) | Nangate 45 nm and 15 nm Open Cell Libraries, typical corner; gscl45nm retired |
| [X2](#x2-clock) | Clock 10 ns throughout; `fmax_mhz` is a lower bound |
| [X3](#x3-wire-load-drive-and-load) | No wire-load model; four `INV_X4` inputs of output load; max transition 0.25 ns |
| [X4](#x4-physical-constraints-and-the-unit-check) | Constraints in ns and fF, scaled to library units, with the unit check |
| [X5](#x5-results-per-technology) | One results tree and CSV per technology; only `KEPT_REPORTS` committed |
| [X6](#x6-run-folders-are-kept) | Mapped netlists in `syn/runs/` are kept |
| [X7](#x7-energy-from-simulated-activity) | Energy from a zero-delay Questa sim of the mapped netlist, then PrimePower, no resynthesis |
| [X8](#x8-activity-from-the-vcd-through-vcd2saif) | Activity: VCD, then vcd2saif, then `read_saif`; the VCD is deleted at once |
| [X9](#x9-every-activity-file-is-checked) | The SAIF is checked (DURATION, window, clock toggles) and >= 99 % of nets annotated |
| [X10](#x10-pt-setup-check) | PT setup check per technology: the forced-activity pair, not P0 against DC |
| [X11](#x11-flop-energy) | Flop energy compared as clock plus register |
| [X12](#x12-cycles-and-windows) | Cycles from the first `ap_start` edge to the first `ap_done` edge, as cosim |
| [X13](#x13-dynamic-energy-only) | Dynamic energy only, busy window, E_comb and E_flop per cycle |
| [X14](#x14-tbjson-is-internal) | `tb.json` is internal to this repo; producers are not changed |
| [X15](#x15-python-from-pixi) | Python from the repo's pixi workspace |
| [X16](#x16-parallel-jobs-from-free-licences) | Parallel jobs from free licences |
| [X17](#x17-licence-errors) | A tool that fails with a licence error is retried once |
| [X18](#x18-no-dumps-kept) | No VCD, WLF or compiled design is kept; SAIFs stay in `sim/runs/` |
| [X19](#x19-stimulus-and-expected-cycles) | Stimulus rand64, 64 beats, seed 0 (rowsum at m8_n64); expected cycles from cosim's line |
| [X20](#x20-power-results) | `power_pt.csv`'s columns and definitions; checks fail a point but are not stored |

## Synthesis

### X1. Libraries

- **Date:** 2026-10-28
- **Decision:** synthesis runs on the Nangate 45 nm Open Cell Library (`NangateOpenCellLibrary_typical.db`: typical, 1.10 V, 25 C) and the Nangate 15 nm Open Cell Library (`NanGate_15nm_OCL_typical_conditional_nldm.db`: typical, 0.80 V, 25 C), chosen per run with `--tech`; there is no default library. OSU gscl45nm (FreePDK45) is retired with its rows; run notes before 28 Oct 2026 are on it.
- **Why:** gscl45nm has 31 cells (676 buf/inv against nangate45's 104 on `done/vecadd/opt_w8`), pins with `max_capacitance` 0 and capacitance in pF. Two open libraries of different nodes give a technology axis with the same flow.
- **Source:** `2026-10-28_step0_libs.md`, `2026-10-28_syn_tech_probe.md`, `b6869b5`.

### X2. Clock

- **Date:** 2026-10-27 (kept on both libraries 2026-10-28)
- **Decision:** the ASIC clock is 10 ns on every point and technology (`--clock` exists but is not used for results). `fmax_mhz` = 1000 / (`clock_ns` - `slack_ns`) is a lower bound, not the library's speed.
- **Why:** one clock makes the points comparable in area and energy per cycle. At 10 ns DC meets timing with room to spare and keeps area-optimized structures; it does not upsize for speed.
- **Source:** `2026-10-27_done.md`, `2026-10-28_tech_rerun.md` (Odd things).

### X3. Wire load, drive and load

- **Date:** 2026-10-28
- **Decision:** no wire-load model on either library (nangate45 `wire_load off`, nangate15 `none`). Input drive `INV_X4`. Output load four `INV_X4` inputs: 25.0 fF on nangate45 (4 x 6.258), 13.2 fF on nangate15 (4 x 3.301). Max transition 0.25 ns. A run whose `area.rpt` shows a wire-load model is marked `failed: a wire-load model applied`.
- **Why:** nangate15 has no wire-load models and nangate45's default (`5K_hvratio_1_1`) would change its timing and switching power, so none on either treats both alike. The old `set_load 0.03` meant 30 fF on gscl45nm and 0.03 fF on nangate45; four `INV_X4` inputs is the same fanout in each library's own cells.
- **Source:** `2026-10-28_syn_tech_probe.md`, `b6869b5`; `syn/README.md` (Wire load).

### X4. Physical constraints and the unit check

- **Date:** 2026-10-28
- **Decision:** `constraints.sdc` holds physical values only (ns, fF). syn.py derives `T_SCALE` (library time units per ns: 1 on nangate45, 1000 on nangate15) and `C_SCALE` (1 on both) from the tech file, and DC multiplies every constraint by them. Right after the library is set, `dc_syn.tcl` reads the library's name and time and capacitance units from `report_lib`; if any differs from the tech file it exits with code 2 before reading RTL (`failed: library mismatch`).
- **Why:** a library in other units takes every constraint 1000x off with no error (a 10 ns clock read as 10 ps on nangate15).
- **Source:** `2026-10-28_step0_libs.md` (Conclusion), `2026-10-28_syn_tech_probe.md` (Checks), `b6869b5`.

### X5. Results per technology

- **Date:** 2026-10-28
- **Decision:** each technology has its own tree and CSVs: `results/hls/<tech>/synth_dc.csv`, `synth_dc_modules.csv`, `reports/`. Only the eight reports in `KEPT_REPORTS` (`area.rpt`, `area_hierarchy.rpt`, `reference.rpt`, `power.rpt`, `power_hierarchy.rpt`, `qor.rpt`, `tech.json`, `lib_info.txt`) are committed per point; a file over 1 MB is left out and named in `skipped.txt`.
- **Why:** area is in each library's own unit and comparable only within a library, so the rows are kept apart. The kept reports are what the area and energy model reads and what the run ran on; the rest checks a run and a rerun rebuilds it.
- **Source:** `b6869b5`, `b2b08a0`; `2026-10-28_tech_rerun.md`.

### X6. Run folders are kept

- **Date:** 2026-10-29
- **Decision:** the mapped netlists in `syn/runs/` are kept. Power and simulation prompts never delete or modify anything under `syn/runs/`; synthesis prompts clean only the points they rerun.
- **Why:** simulation and power read the netlist DC wrote, with no resynthesis (X7); a deleted run folder can only be rebuilt by a new synthesis, which could differ (`2026-10-27_wsweep_r2.md`: area moves by up to 0.02 % with names alone).
- **Source:** `2026-10-29_pwr_step0.md`.

## Power

### X7. Energy from simulated activity

- **Date:** 2026-10-29
- **Decision:** energy comes from simulated activity. A functional, zero-delay Questa simulation of the mapped netlist (no SDF, `vsim +nospecify +notimingchecks`; `vopt +initreg+0 +acc=n`, see PITFALLS Q1 and Q2), then PrimePower (`pt_shell`, averaged mode) on the same netlist with the same library, constraints and wire-load setting as DC (`pt_power.tcl`). No resynthesis.
- **Why:** DC's default activity follows the logic structure, not the work a point does (PITFALLS DC4). The netlist is unplaced, so there is no wire delay to annotate; zero delay gives the activity per cycle the model needs.
- **Source:** `2026-10-29_pwr_step0.md`, `19c1323`.

### X8. Activity from the VCD, through vcd2saif

- **Date:** 2026-10-29 (rewritten for `pwr_r1` the same day)
- **Decision:** activity comes from a Questa VCD of the DUT's scopes (the netlist's own nets and those of its sub-designs, not the cells'), dumped by the TB from the edge that raises `ap_start` to the done edge. `vcd2saif -instance tb/dut -time t0 t1` cuts the busy window in the VCD's time unit (ps here) into a SAIF, and PT reads it with `read_saif -strip_path tb/dut`. The VCD is deleted right after vcd2saif, whatever the result. Questa's `power report -bsaif` is not used. This replaces the kickoff's "Questa writes the SAIF" and step 0's `read_vcd -zero_delay -time`.
- **Why:** Questa 2022.4's SAIF is wrong in four ways at zero delay and 13 % low busy, 34 % low idle on vecadd `opt_w8`, with 100 % annotation coverage in PT (PITFALLS Q4). vcd2saif and `read_vcd` agree within 0.1 % (step 0: 1.0004 to 1.0010); a SAIF is small, can be checked in Python (X9) and kept (X18), where a VCD of a long run is not.
- **Source:** `2026-10-29_pwr_step0.md` (Questa's SAIF against the VCD), `2026-10-29_pwr_r1.md`.

### X9. Every activity file is checked

- **Date:** 2026-10-29 (rewritten for `pwr_r1` the same day)
- **Decision:** before PT, `sim/pwr.py` checks the window's SAIF: T0 + T1 + TX = DURATION on every driven net (a net at Z for the whole window is an undriven wire bit, counted apart; PITFALLS DC5), every entry parsed, DURATION = cycles x clock period, and the clock net's TC = 2 x cycles. After PT, at least 99 % of the design's nets must be annotated from the SAIF (`report_switching_activity`); the list of nets that are not is kept in the run folder. A failed check fails the point.
- **Why:** coverage alone said 3566/3566 for the defective Questa SAIF too; it says a net has a number, not that the number is right. The clock check caught a lost window edge while building the TB (PITFALLS Q6).
- **Source:** `2026-10-29_pwr_step0.md` (For the design: Coverage is not a SAIF check), `2026-10-29_pwr_r1.md`.

### X10. PT setup check

- **Date:** 2026-10-29 (tolerance amended after `pwr_r1` the same day)
- **Decision:** the PT setup check per technology is the forced-activity pair: `pt_power.tcl` and `dc_readback.tcl` with `PWR_MODE=uniform` (DC's default toggle rate and static probability annotated on every net but the clock), agreeing per power group within 0.1 %, except nangate15's combinational group within 2.5 %. PT is the reference tool for energy. P0 (PT with DC's defaults, propagated) against DC's `power.rpt` is not the check.
- **Why:** with identical annotated activity PT and DC agree to 0.00 % in every group on nangate45; with default activity they differ by 2.4 % (register 35 %) because their vectorless propagation differs, which says nothing about the setup (PITFALLS PT2). nangate15's combinational gap (+1.95 %) is non-switching internal power, which PT and DC handle differently (PITFALLS PT5), not the setup; PT, the sign-off power tool that reads the simulated activity, is the one the results use.
- **Status:** `pwr setup-check` implements it (`SETUP_TOL`, `SETUP_TOL_GROUP` in `sim/pwr.py`). Both technologies pass: nangate45 within 0.0013 %, nangate15 within 0.08 % and combinational +1.95 %.
- **Source:** `2026-10-29_pwr_step0.md` (P0 against DC), `2026-10-29_pwr_r1.md`.

### X11. Flop energy

- **Date:** 2026-10-29
- **Decision:** flop energy is compared as clock plus register (e_clk + e_reg), never one group alone.
- **Why:** PT books a flop's clock-edge energy under register when its output toggles and under clock when it does not (PITFALLS PT3); e_clk is 4.04 pJ idle against 2.40 busy on vecadd `opt_w8`.
- **Source:** `2026-10-29_pwr_step0.md` (Energy per cycle).

### X12. Cycles and windows

- **Date:** 2026-10-29
- **Decision:** a run's cycles count rising edges from the first edge that samples `ap_start` = 1 to the first edge that samples `ap_done` = 1. The busy window opens at the falling edge before the first start edge and closes at the falling edge before the done edge (`sim/tb/ap_ctrl_hs_seq.sv` prints both; step 0 marked them with `$stop`).
- **Why:** this count equals cosim's latency with no offset (66 against 66 on vecadd `opt_w8`). Falling-edge boundaries hold exactly the transitions of the rising edges inside the window, since nothing toggles at a falling edge.
- **Source:** `2026-10-29_pwr_step0.md` (Simulation: Result, Windows).

### X13. Dynamic energy only

- **Date:** 2026-10-29
- **Decision:** the power flow measures the busy window only, from start to done (X12), and reports two dynamic numbers per cycle: E_comb, and E_flop = E_clk + E_reg + E_seq. Idle windows are not measured. Leakage stays in `synth_dc.csv` and is not repeated in the power results. Energy per run is (E_comb + E_flop) x C_run.
- **Why:** snax-dfg and snax-gvsoc annotate only dynamic activity, as logic plus register energy per active cycle. E_flop sums the flop groups because PT books a flop's clock-edge energy under register or clock depending on whether its output toggles (X11), so the register group alone undercounts a register's cost per active cycle.
- **Source:** agreed after `2026-10-29_pwr_step0.md`; its idle rows (P3, P4) are kept for the record only.

### X14. tb.json is internal

- **Date:** 2026-10-29
- **Decision:** `tb.json`, the description the TB is built from, is internal to this repo. Producers are not changed: hls-exercises keeps writing `rtl/<point>/filelist.f` and `sizes.txt`; snax-forge keeps its bundle and `rtl.json`. One adapter per source builds `tb.json`: `sim/sources/hls.py`, from the point's Verilog ports and `params.json`; `sim/sources/forge.py`, later, at SYN1, from `rtl.json`. `tb.json` is written into each run folder at run time and committed with the point's reports in `power_reports/` (X20).
- **Why:** this repo is the data-collection side, and snax-forge must not need changes to be measured.
- **Source:** agreed 2026-10-29, after `2026-10-29_pwr_step0.md`.

## Environment

### X15. Python from pixi

- **Date:** 2026-10-29
- **Decision:** Python comes from the repo's pixi workspace (`pixi.toml`: Python 3.11, numpy): `pixi install` once, then `pixi run syn ...` and `pixi run python <script>`. Not the host's `python3` or `python3.11`.
- **Why:** the host's `python3` is 3.6.8 and cannot parse the scripts; `python3.11` on the host has no numpy. One pinned environment (`pixi.lock`) gives the same Python everywhere.
- **Source:** `620bb67`, `8bd46e5`; `2026-10-27_done.md` (Tools).

### X16. Parallel jobs from free licences

- **Date:** 2026-10-29 (rewritten for `pwr_r1` the same day; synthesis since 2026-10-28)
- **Decision:** count free licences with `lmutil lmstat` on both servers at the start of a batch, then:
  - power (`pwr run`): J = min(free `msimhdlsim`, free PrimePower, free PrimeTime, nproc) workers; each worker runs one point from start to end (compile, then per run vsim, vcd2saif and PT). PT threads per run = max(1, nproc // J) (`set_host_options -max_cores`). The counts, J and the threads go into the run note;
  - DC runs (`syn.py -j`): from free Design-Compiler licences (9 free gave `-j 2`), at `--cores 16` per run.
- **Why:** a job that cannot check out a licence fails or waits; J workers with nproc // J threads each use the cores without oversubscribing them.
- **Source:** `2026-10-29_pwr_step0.md` (Licences), `2026-10-28_tech_rerun.md` (Commands), `2026-10-29_pwr_r1.md`.

### X17. Licence errors

- **Date:** 2026-10-29
- **Decision:** a tool that fails with a licence error is retried once; a second failure stops and is reported.
- **Why:** licence errors can be transient: DC failed once with error -92 during an `lmreread` with 0 of 10 in use, and the rerun seconds later worked (PITFALLS L1).
- **Source:** `2026-10-29_pwr_step0.md` (Licences).

## Power runs

### X18. No dumps kept

- **Date:** 2026-10-29
- **Decision:** no VCD, WLF or compiled design library is kept. The VCD is deleted right after vcd2saif, whatever the result; `vsim.wlf` and the point's compiled `work/` at the end of each point. A run folder keeps `tb.json`, the stimulus, the logs, the SAIF, the PT reports and the list of nets not annotated. SAIFs stay in `sim/runs/` (git ignores it); only the reports in X20 are committed.
- **Why:** a VCD grows with nets x cycles (16.9 MB for vecadd `unopt_w32`, 6273 cycles) and is fully replaced by its SAIF (2.3 MB there); WLF and the compiled library are rebuilt in about 2 s.
- **Source:** `2026-10-29_pwr_r1.md`.

### X19. Stimulus and expected cycles

- **Date:** 2026-10-29
- **Decision:** the default stimulus is `rand64`: uniform full-range int64 from numpy `default_rng(seed)`, seed 0, drawn stream by stream in `tb.json` order, then the data pins (axpy's alpha). Every point runs 64 beats whatever W: loop_count = 64 (and len = 64 for dot and vsum), so n = 64 x W elements; matadd loop_count = 64. rowsum runs its cosim size m8_n64 as is. Every input stream bit must toggle at least once before the sim. `--stim forge` (hls-exercises' `data.h` at a cosim size, with `sim/ref.py` asserted equal to its `EXP_*`) is for validation only. Expected cycles come from `results/hls/hls_cycles.csv`: cosim's two sizes of the point give cycles = a x loop_count + b, with a and b integers; at a cosim size the comparison is exact. A mismatch fails the point.
- **Why:** full-range data toggles every bit, so the energy does not depend on how narrow a test's values are (forge's data cost 4.3 % less per busy cycle in step 0); 64 beats keeps every W's run the same work per beat. The cycle line checks the netlist against cosim at sizes cosim never ran.
- **Source:** `2026-10-29_pwr_step0.md` (forge against full), `2026-10-29_pwr_r1.md`.

### X20. Power results

- **Date:** 2026-10-29
- **Decision:** `results/hls/<tech>/power_pt.csv`, one row per point, size and seed (merged on those three), columns in this order:
  - `point`, `top`, `tech`, `clock_ns`, `W`, `size` (`b64`, or a cosim size), `config` (the pins, e.g. `loop_count=64`), `beats` (beats per input stream), `seed` (`forge` for the forge stimulus), `cycles`;
  - `e_clk_pj`, `e_reg_pj`, `e_seq_pj`, `e_comb_pj`: (internal + switching) of each PT power group x `clock_ns`, per cycle of the busy window;
  - `e_flop_pj` = e_clk + e_reg + e_seq; `e_dyn_pj` = e_flop + e_comb; `p_dyn_uw` = e_dyn / clock_ns x 1000;
  - `e_comb_fire_pj`, `e_flop_fire_pj` = per cycle x cycles / beats; `e_run_pj` = e_dyn x cycles;
  - `flop_bits` = `seq_cells` of the point in `synth_dc.csv`; `e_bit_pj` = e_flop / flop_bits;
  - `status`: `ok`, `failed: <which check>`, or `skipped: needs a RAM macro (...)` (a `# ram:` point, as syn.py).

  No leakage columns (X13). `power_pt_modules.csv` (`point, tech, path, design, e_dyn_pj`) has one row per hierarchical cell of the default run. Committed per point in `power_reports/<tier>/<kernel>/<point>/`: `power.rpt`, `power_hierarchy.rpt`, `switching_activity.rpt`, `tb.json` (other runs of the point in a subfolder `<size>_<seed>/`). The checks (X9, X19) fail a point but are not stored as columns; tool versions go in the run note.
- **Why:** the HWCOST model needs energy per cycle and per firing, split into combinational and flop energy, across the W sweeps; everything else is either a check or recoverable from the run folder.
- **Source:** `2026-10-29_pwr_r1.md`.
