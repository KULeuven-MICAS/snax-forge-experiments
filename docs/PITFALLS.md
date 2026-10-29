# Pitfalls

Tool behaviour that gives wrong numbers, or no numbers, without an error. Grouped by tool. Each entry: symptom, cause, fix or check, and the run note (in `results/hls/runs/`) that found it. The decisions they led to are in [`DECISIONS.md`](DECISIONS.md).

## DC

### DC1. `auto_wire_load_selection false` does not remove nangate45's wire-load model

- **Symptom:** on nangate45, `area.rpt` says `Wire load has zero net area` and `power.rpt` has a `Wire Load Model` table naming `5K_hvratio_1_1`, although `auto_wire_load_selection` is false.
- **Cause:** the library sets `default_wire_load 5K_hvratio_1_1`. `auto_wire_load_selection false` plus `remove_wire_load_model` still leaves it; removing the library's `default_wire_load` is what clears it. With the model, `done/vecadd/opt_w8`'s critical path was 5.85618 ns; without it, 4.54185 (-22.4 %).
- **Fix or check:** `dc_syn.tcl` (`wire_load off`) sets `auto_wire_load_selection false`, runs `remove_attribute [get_libs <lib>] default_wire_load` before elaboration and `remove_wire_load_model [current_design]` after link. Check: `area.rpt` says `No wire load specified`; syn.py marks any other run `failed: a wire-load model applied`.
- **Found in:** `2026-10-28_syn_tech_probe.md`, `2026-10-28_step0_libs.md`.

### DC2. A library in other units takes every constraint 1000x off

- **Symptom:** none; DC runs and reports normally.
- **Cause:** SDC values are read in the library's units. nangate15's time unit is 1 ps, so a 10 ns clock written as `10` is 10 ps, as are the uncertainties, I/O delays and max transition. Before X4, `set_load 0.03` meant 30 fF on gscl45nm (pF) and 0.03 fF on nangate45 (an INV_X1 input is 1.70 fF).
- **Fix or check:** constraints in ns and fF, scaled by `T_SCALE` and `C_SCALE`, and the unit check: `dc_syn.tcl` exits 2 before reading RTL when the library's name or units differ from the tech file (`failed: library mismatch`). Tested with the nangate45 .db given as nangate15 (X4).
- **Found in:** `2026-10-28_step0_libs.md` (Conclusion), `2026-10-28_syn_tech_probe.md` (Checks).

### DC3. Results depend slightly on names and order

- **Symptom:** the same Verilog apart from names gives a slightly different area: vsum against rowsum `unopt_w2`, 0.012 % on nangate45 (identical on nangate15). A rename-only change in Vitis's output moved the area of 6 points by 1 to 23 µm² (at most 0.02 %).
- **Cause:** DC's optimization depends a little on net names and the order of statements.
- **Fix or check:** treat differences of this size as noise, not as a design difference; compare against an equal-Verilog pair (vecadd / matadd, vsum / rowsum) when in doubt.
- **Found in:** `2026-10-28_tech_rerun.md` (Checks, Odd things), `2026-10-27_wsweep_r2.md`.

### DC4. Power at default activity follows logic structure, not work

- **Symptom:** at equal area, vecmul `dace_w16` is 100.1 pJ per cycle and `opt_w16` 13.47 pJ on nangate45 (124,948 vs 124,575 µm²), 30.3 vs 5.82 pJ on nangate15; nearly all of the gap is `e_comb_pj` (88.2 vs 5.16 pJ on 45).
- **Cause:** with no vectors DC sets toggle rate 0.1 and static probability 0.5 on the inputs and propagates them through whatever logic sits in front of the multipliers, whether or not that logic works in a real run.
- **Fix or check:** the `e_*_pj` columns of `synth_dc.csv` compare points only as far as the default activity holds; energy comparisons use simulated activity (X7).
- **Found in:** `2026-10-28_tech_rerun.md` (Odd things).

## Libraries

### LIB1. nangate15's flops all have async reset or set

- **Symptom:** every flop on nangate15 is `DFFRNQ_X1` or `DFFSNQ_X1` (vecadd `opt_w8`: 582 `DFFSNQ_X1`, set pin unused); there is no plain DFF.
- **Cause:** the library has no other flop. Vitis's synchronous reset then costs a flop with an unused async pin plus the reset logic.
- **Fix or check:** nothing to fix; keep it in mind when comparing sequential area and energy between nangate45 and nangate15.
- **Found in:** `2026-10-28_step0_libs.md`, `syn/README.md` (Technologies).

### LIB2. Neither cell model file uses `` `celldefine ``

- **Symptom:** `power add -r -nocellnet` in vsim gives the same nets as `power add -r`; cell-internal nets (such as a tied input pin, `U1074/A1` on vecadd `opt_w8`) are included.
- **Cause:** `NangateOpenCellLibrary.v` has no `` `celldefine ``, and `NanGate_15nm_OCL_functional.v` was exported with "`` `celldefine `` : false", so vsim cannot tell a cell from a module. `-nocellnet` has no effect.
- **Fix or check:** on flat netlists use `power add <dut>/*` without `-r` (Q3). On netlists with sub-designs, expect cell-internal nets that PT will not map.
- **Found in:** `2026-10-29_pwr_step0.md` (Cell models, power add).

### LIB3. nangate15's model file has no `` `timescale ``

- **Symptom:** the nangate15 cells and DC's netlists compile with no timescale of their own, unlike the TB and nangate45's cells.
- **Cause:** `NanGate_15nm_OCL_functional.v` has none, and DC's netlists have none either (nangate45's model file has `1ns/1ps`).
- **Fix or check:** compile both with `vlog -timescale 1ns/1ps`.
- **Found in:** `2026-10-29_pwr_step0.md` (Cell models).

### LIB4. nangate15 reports time in ps and leakage in pW

- **Symptom:** `qor.rpt` paths and slack in ps; `power.rpt` in mW and pW on nangate15 (uW and nW on nangate45).
- **Cause:** the library's units (time 1 ps, leakage 1 pW).
- **Fix or check:** read every number with its unit; syn.py converts times to ns and power to uW from the reports' own unit lines.
- **Found in:** `2026-10-28_step0_libs.md`, `syn/README.md` (Columns).

## Questa

### Q1. Gate-level X from Vitis registers without reset

- **Symptom:** the netlist simulation never finishes. On nangate45 all 64 beats pass, then `C_TVALID` goes X and `ap_done` never rises (timeout); on nangate15 X appears after 6 beats.
- **Cause:** Vitis starts unreset registers in an `initial` block (`b_fu_76`, the beat counter: `#0 b_fu_76 = 32'd0`). The netlist has no such block, so its flops start at X, and DC's logic for the clear at the start edge also depends on the X compare `b_fu_76 == loop_count`, so the X stays (X pessimism, not a design bug).
- **Fix or check:** `vopt +initreg+0` on both technologies: every reg and UDP state starts at 0, as the RTL's initial blocks do. The TB's X check on `C_TVALID` and its timeout catch it. A seeded `+initreg` (random) run would show whether a point depends on the 0.
- **Found in:** `2026-10-29_pwr_step0.md` (Power-on state).

### Q2. `+acc=n` is needed or `power add` finds no nets

- **Symptom:** `power add /tb_vecadd_opt_w8/dut/*` gives `vsim-3561 No objects found matching 'dut'`; the SAIF is empty.
- **Cause:** vopt optimizes the netlist's nets away from visibility without `+acc`.
- **Fix or check:** `vopt ... +acc=n`; it works for `power add` and `vcd add` and costs nothing measurable (5000 runs: 29.9 s without `+acc`, 25.3 s with `+acc=n`, within run-to-run noise).
- **Found in:** `2026-10-29_pwr_step0.md` (+acc).

### Q3. `power add` with or without `-r`

- **Symptom:** `power add <dut>/*` on a netlist with sub-designs misses the nets inside them; with `-r` it picks up cell-internal nets too.
- **Cause:** without `-r` only the top level's nets are added (3572 on vecadd `opt_w8`, ports included). `-r` descends into sub-designs and, with no `` `celldefine `` (LIB2), into cells.
- **Fix or check:** without `-r` on flat netlists; `-r` on netlists with sub-designs (107 hierarchical references across the 116 netlists), and expect cell-internal nets PT will not map. (The VCD route, X8, uses `vcd add` and the same choice applies.)
- **Found in:** `2026-10-29_pwr_step0.md` (power add, For the design).

### Q4. `power report -bsaif` is wrong at zero delay (Questa 2022.4)

- **Symptom:** Questa's SAIF gives 13% less energy busy and 34% less idle than the VCD of the same run (P1q / P1v 0.872, P2q / P2v 0.884; P3q / P3v and P4q / P4v 0.658), while PT reports 100% annotation coverage and no warning.
- **Cause:** four defects after `power reset` / `power on`:
  1. DURATION is the time since 0, not the window (750,000 and 2,750,000 ps for windows of 660,000 and 2,000,000); PT divides TC by it.
  2. Nets with no event in the window get T0 = T1 = TX = 0 (246 of 3572 in busy, 3558 in idle), so PT has no static probability for them: idle leakage 86.4 µW instead of 108.7.
  3. TC drops toggles with the zero-width glitches it counts in IG: TC differs from the VCD's on 3326 of 3570 nets in busy, and the sum is 77,599 against 94,918 (-18%).
  4. The first edge of each window is lost: in idle `ap_clk` has TC 399 (VCD 400), and the done edge's transitions are missing.
  Cumulative reports without `power reset` repair 1 and 2, but TC is not monotonic, so no difference of reports repairs 3.
- **Fix or check:** do not use it; read the VCD (X8). Check every activity file (X9).
- **Found in:** `2026-10-29_pwr_step0.md` (Questa's SAIF against the VCD).

### Q5. VCD size

- **Symptom:** the VCD of vecadd `opt_w8` (3572 nets, 275 cycles, reset and both windows) is 749,555 bytes, 0.75 MB; it grows with nets and cycles.
- **Cause:** a VCD stores every transition.
- **Fix or check:** large points or long runs may need per-window dumps (`vcd on` / `vcd off` around the windows, or one VCD per window) or `read_vcd -pipe_exec`.
- **Found in:** `2026-10-29_pwr_step0.md` (Activity files, For the design).

## PrimeTime

### PT1. PT applies the library's default wire-load model, hidden

- **Symptom:** on nangate45 nets carry wire capacitance and resistance that DC did not have (net `n964`: +15.44 fF and 0.31 kΩ; 3564 of 3566 nets with `wire_capacitance_max` > 0).
- **Cause:** PT applies the library's `default_wire_load` (`5K_hvratio_1_1`) whatever `auto_wire_load_selection false` and `remove_wire_load_model` say, before or after link. `report_design` hides it (`wire_load_model_max --`, and `default_wire_load` on the library reads empty); `report_wire_load` shows it, selection type `library default`.
- **Fix or check:** `set_load 0` and `set_resistance 0` on every net (`set_load -wire_load 0` is rejected on nets). Check `wire_load.rpt`: `with wire_capacitance_max > 0: 0, with net_resistance_max > 0: 0`. On nangate15 it is a no-op, but harmless.
- **Found in:** `2026-10-29_pwr_step0.md` (Wire load).

### PT2. Default-activity propagation differs from DC's around enable logic

- **Symptom:** P0 (PT with DC's default toggle rate 0.1 and static probability 0.5) against DC's `power.rpt`: total +2.4%, register +35%, combinational +2.3%, clock -0.2%.
- **Cause:** vectorless propagation differs at the hold mux in front of each result flop, whose select is the pipeline enable from the FSM, a feedback loop PT and DC resolve differently (the 512 C data flops +37 to 39%, FSM flops +34%). With the same activity annotated on every net, the two agree to 0.00%.
- **Fix or check:** do not use P0 as the setup check; use the forced-activity pair (X10).
- **Found in:** `2026-10-29_pwr_step0.md` (P0 against DC).

### PT3. A flop's clock-edge energy moves between register and clock

- **Symptom:** e_clk is higher idle than busy (vecadd `opt_w8`: 4.0356 pJ per idle cycle, 2.3986 busy) while e_reg falls to almost 0.
- **Cause:** PT books a flop's clock-edge energy under `register` when its output toggles and under `clock_network` when it does not.
- **Fix or check:** compare e_clk + e_reg (X11); E_flop sums the flop groups (X13).
- **Found in:** `2026-10-29_pwr_step0.md` (Energy per cycle).

### PT4. `read_vcd -time` takes ns; `vcd2saif -time` takes the VCD's unit

- **Symptom:** the same window must be written `90 750` for `read_vcd` and `90000 750000` for `vcd2saif` on the step 0 VCD; the wrong unit gives a window 1000x off.
- **Cause:** PT's `read_vcd -time` is in ns; `vcd2saif -time` is in the VCD's timescale (ps here).
- **Fix or check:** take the VCD's timescale from its header and convert; X9's window-length check catches a wrong unit.
- **Found in:** `2026-10-29_pwr_step0.md` (Commands, For the design).

## Licences

### L1. Transient error -92 from DC

- **Symptom:** `Design-Compiler Internal licensing error number -92: Feature removed during lmreread` at start, with 0 of 10 licences in use.
- **Cause:** the licence server reread its file while DC checked out.
- **Fix or check:** retry once (X17); the rerun seconds later worked.
- **Found in:** `2026-10-29_pwr_step0.md` (Licences).

### L2. Feature names

- **Symptom:** `lmstat` has no `qhsim*` feature and no `PrimeTime-PX`; vsim's log names no feature.
- **Cause:** the Questa features on this server are `msim*`; vsim checks out one `msimhdlsim` (seen with `lmstat` during a run). Each PT power run holds one `PrimeTime` and one `PrimePower` (`list_licenses`).
- **Fix or check:** count `msimhdlsim`, `PrimeTime` and `PrimePower` for X16; `Design-Compiler` for synthesis.
- **Found in:** `2026-10-29_pwr_step0.md` (Licences).

### L3. `lmutil` not on PATH

- **Symptom:** `lmutil: command not found` (or `lmstat`) in a non-interactive shell.
- **Cause:** it is put on PATH from `~/.bashrc`, which a non-interactive shell may not read; earlier runs used Vivado's `lmutil`.
- **Fix or check:** set `LMUTIL` to the binary (Questa's: `/esat/micas-data/software/Mentor/questasim_2022.4/linux_x86_64/lmutil`).
- **Found in:** `2026-10-28_step0_libs.md`, `2026-10-29_pwr_step0.md` (Tools).
