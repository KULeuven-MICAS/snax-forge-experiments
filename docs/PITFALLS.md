# Pitfalls

Tool behaviour that gives wrong numbers, or no numbers, without an error. Grouped by tool (and the environment). Each entry: symptom, cause, fix or check, and the run note (in `results/hls/runs/`) that found it. The decisions they led to are in [`DECISIONS.md`](DECISIONS.md).

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

### DC5. Undriven bits in declared vector wires

- **Symptom:** a SAIF from vcd2saif has entries with `(T0 0) (T1 0) (TX 0) (TZ <DURATION>) (TC 0)`: 2 in vecadd `opt_w8` (`b_fu_76[1]`, ...), 2044 in `unopt_w32` (2043 of them bits of `zext_ln170_reg_255`). A parser that expects TC right after TX skips them without a word, and a check of T0 + T1 + TX = DURATION then misses them (the first version of `sim/pwr.py`'s check did).
- **Cause:** DC keeps a vector wire's declaration (`wire [2047:0] zext_ln170_reg_255;`) after removing the logic behind most of its bits, or connects only a flop's QN (`b_fu_76_reg[1]`). Those bits have no driver, sit at Z the whole simulation, and are not nets in PT.
- **Fix or check:** parse the optional TZ, count an all-Z entry apart, fail a net that is Z for part of the window, and fail when the parser matches fewer entries than the SAIF has `(T0` fields (`saif_check` in `sim/pwr.py`).
- **Found in:** `2026-10-29_pwr_r1.md`.

### DC6. Some module headers in DC's netlists are indented

- **Symptom:** a parser of the mapped netlist misses a sub-design: dot, vecmul and axpy's 64-bit multiplier (`    module dot_mul_64s_64s_64_1_1_..._WIDTH64 (` at line 9, four spaces in). In `sim/pwr.py` the multiplier's scope was not dumped, and PT annotated 1718 of 6349 nets on dot `unopt_w1` (42 of 116 points of dot, vecmul and axpy failed on nangate45: those with a multiplier on this gate, axpy opt first on Q7).
- **Cause:** DC writes the first module after the header block with leading spaces in these netlists; the other modules start in column 0.
- **Fix or check:** match `^\s*module` and `^\s*endmodule`. The 99 % annotation gate (X9) is what caught it; a missed small sub-design (a few nets) would pass it, so `pwr_tasks` checked that every module of all 232 netlists gets a dump scope.
- **Found in:** `2026-10-29_pwr_tasks.md`.

### DC7. DC Y-2026.03-SP2 crashes on a 1-bit-select mux inside an adder, under a branch on the same bit

- **Symptom:** `compile_ultra` dies with `Error id=834758` and `Fatal: Internal system error, cannot recover`, in DC's compile child process (`dcfarm: detected bad exit for job ...`), during Pass 1 Mapping, on snax-forge's dot_5 and dot_6 at W = 2, both technologies; `syn.py` writes `failed: no area report` (before SYN1 R1 it wrote `failed: library mismatch`, see the fix in R1's run note). W = 4 to 32 of the same designs passed.
- **Cause:** the 37-line `SerialAccumulate_i64_i64_n2` that firtool emitted from snax-forge's `acc := Mux(first && lane === 0, x, acc + x)`, `x = in(lane)`. In dot 5 and 6 the sum's T is 1, so `first` is constant true and folded away; at 2 lanes `lane` is one bit, and firtool's partial simplification gave `if (io_lane) acc <= acc + (io_lane ? io_in_1 : io_in_0); else acc <= io_in_0;`: its rule `mux(c, a, mux(c, b, d)) -> mux(c, a, d)` removed the select in the `else` branch, where it is a direct operand, but not in the `then` branch, where it sits inside the adder. A 1-bit-select mux inside an adder, under a branch on the same bit: valid RTL, and Y-2026.03-SP2 crashes on it, on the block alone too. The same block without the inner mux (`acc <= acc + io_in_1`) or in the n = 4 form (`if (io_lane == 0) acc <= _GEN[io_lane]; else acc <= acc + _GEN[io_lane]`) passes (771 and 918 um2 on nangate45). The original block passes on W-2024.09-SP5 and V-2023.12-SP4 (both 771.9 um2, the inner mux simplified away), so it is a regression of Y-2026.03-SP2. Not the disk (also crashes in tmpfs with 125 GB free; a 1 GB write to the home works; DC's resource line shows 1427 GB free), not parallel runs (crashes run one at a time with no other DC process on the host), not the core count or adaptive multithreading (crashes at 1 core with it off), not boundary optimization or sequential output inversion (crashes with `-no_boundary_optimization` and with `-no_seq_output_inversion`).
- **Fix or check:** fixed in snax-forge (branch `ry/span1-read`, commit `2741b46`, KULeuven-MICAS/snax-forge#46): `SerialAccumulate.scala` writes the update as `acc := Mux(first && lane === 0, 0, acc) + x`, the adder's acc input cleared on a restart and the lane selected once; at 2 lanes firtool now emits `acc <= (io_lane ? acc : 64'h0) + (io_lane ? io_in_1 : io_in_0)`, with no branch on `io_lane`, and dot_5 and dot_6 at W = 2 synthesize on both technologies. If DC dies with this error id on other RTL, look for the same shape (a mux inside arithmetic under a branch on its own select) and try the block alone, then W-2024.09-SP5.
- **Found in:** `results/forge/runs/2026-10-31_syn1_r1.md`; cause and fix in `results/forge/runs/2026-10-31_syn1_r1b.md`.

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
- **Fix or check:** dump only the window and delete the VCD after vcd2saif (X8, X18), as `sim/pwr.py` does: the largest VCD of `pwr_r1` was 16.9 MB (vecadd `unopt_w32`, 6273 cycles), its SAIF 2.3 MB. `read_vcd -pipe_exec` is the other way out.
- **Found in:** `2026-10-29_pwr_step0.md` (Activity files, For the design), `2026-10-29_pwr_r1.md`.

### Q6. `$dumpon` at a window boundary loses the boundary's clock edge

- **Symptom:** the SAIF of vecadd `opt_w8`'s busy window has `ap_clk` TC 131 for 66 cycles, not 132; everything else looks normal.
- **Cause:** the window boundaries sit on falling edges (X12). `$dumpon` at the opening falling edge writes the values after that edge, so its transition is not a value change in the VCD, and vcd2saif does not count it.
- **Fix or check:** dump from the rising edge before the window (the edge that raises `ap_start`) to the rising edge after it (the done edge), and let `vcd2saif -time t0 t1` cut the window: TC 132 and energy as step 0 (`sim/tb/ap_ctrl_hs_seq.sv`). X9's clock check catches it.
- **Found in:** `2026-10-29_pwr_r1.md` (building the TB).

### Q7. A falling edge at time 0, and TVALID high in reset

- **Symptom:** the sink of axpy `opt_w*` counts 65 beats for 64 and every beat mismatches: beat 0 is `0000000000000002` "at 0".
- **Cause:** `logic clk = 1'b0` is an X -> 0 change at time 0, so `@(negedge clk)` fires at time 0; axpy opt's netlist drives `y_out_TVALID` = 1 while in reset (with `+initreg+0`). A sink that samples whenever TVALID = 1 takes that as a beat, and every later beat is off by one.
- **Fix or check:** count beats only once reset is released (`rst_n === 1`), as `sim/tb/axis_sink.sv` does.
- **Found in:** `2026-10-29_pwr_tasks.md`.

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

### PT5. nangate15: PT and DC differ on input-pin internal power

- **Symptom:** the setup check (X10) fails on nangate15: with the same uniform activity on every net, PT's combinational group is +1.95 % above DC's (internal +3.66 %, 15.469 against 14.922 µW; switching -0.12 %), register -0.08 %, clock -0.0003 %, leakage equal. nangate45 agrees within 0.0013 %.
- **Cause:** nangate15's cells have input-pin `internal_power` groups for toggles that do not switch the output (`when : "!A2 & ZN"` on NAND2_X1), and negative table entries (97 in NAND2_X1); nangate45 has neither. PT books more of it than DC: per cell type, internal power differs on NAND4_X1 (+32 %), NOR4_X1, OAI21_X1 and AND4_X1 (about +15 % each), NAND2_X1 (+14 %), AOI22_X1 (+10 %), NOR2_X1 (+8 %), while DFFSNQ_X1, FA_X1, XOR2/XNOR2, INV and BUF agree within 0.03 %. The switching difference (up to -1.3 % on NAND2/NOR2) is consistent with nangate15's `rise/fall_capacitance_range`; not traced further.
- **Fix or check:** the setup is the same in both tools (netlist, loads, constraints, leakage equal). The setup check allows 2.5 % on nangate15's combinational group and 0.1 % elsewhere, and PT is the reference tool for energy (X10).
- **Found in:** `2026-10-29_pwr_r1.md` (setup-check).

## Licences

### L1. Transient error -92 from DC

- **Symptom:** `Design-Compiler Internal licensing error number -92: Feature removed during lmreread` at start, with 0 of 10 licences in use.
- **Cause:** the licence server reread its file while DC checked out.
- **Fix or check:** retry once (X17); the rerun seconds later worked. `syn.py run` does this itself since SYN1 R1 (`syn/README.md`, Licence errors): it prints the matched line, reruns the point once and counts the retry; a second licence failure is `failed: licence (<the line>)`. The first try may print only `Fatal: Design Compiler is not enabled. (DCSH-1)`, with no "licens" in it (SYN1 R0).
- **Found in:** `2026-10-29_pwr_step0.md` (Licences), `results/forge/runs/2026-10-31_syn1_r0.md`.

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

## Environment

### E1. `pixi run python -c "..."` loses the inner quotes

- **Symptom:** `SyntaxError` from a one-liner that runs under plain `python -c`: `'...'` strings inside the double-quoted code arrive without their quotes.
- **Cause:** pixi runs the command through its own task shell, which parses the quoting again.
- **Fix or check:** put the code in a script file and run `pixi run python <file>` (or a heredoc to `pixi run python -`).
- **Found in:** `2026-10-29_pwr_r1.md`.
