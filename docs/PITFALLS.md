# Pitfalls

Tool behaviour that gives wrong numbers, or no numbers, without an error. Grouped by tool (and the environment, and the zips of X51). Each entry: symptom, cause, fix or check, and the run note (in `results/hls/runs/`) that found it. The decisions they led to are in [`DECISIONS.md`](DECISIONS.md).

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

### DC8. Bambu's declaration initializers are dropped (VER-708)

- **Symptom:** on a Bambu point DC warns five times `The construct 'declaration initial assignment' is not supported in synthesis; it is ignored. (VER-708)`: `register_SE`'s `reg reg_out1 = 0` (`panda_libtech.v:78`), `SIMPLEJOIN_FU`'s `current = 0` and `started = 0` (424, 425), `register_AR`'s `reg_out1 = 0` (534) and the controller's `present_state = S_9` (`dot.v:1040`). No error, and the row is ok.
- **Cause:** Bambu writes power-on values as Verilog initializers; DC ignores them, so the netlist's flops start at X. The controller's `present_state` is also reset by `reset` (active low); the beat registers (`register_SE`) have no reset, as Vitis's data registers (Q1).
- **Fix or check:** nothing for synthesis (an ASIC has no RTL power-on state). For gate-level simulation (R5), the same as Q1: `vopt +initreg+0` starts every flop at 0, as the initializers do; check that the bambu power source keeps it, and that its TB holds `reset` low for a few cycles first.
- **Found in:** `results/runs/2026-11-05_hsyn1_r4.md`.

### DC9. A Bambu point has fewer flops than its register instances: DC removes unloaded registers (OPT-1207)

- **Symptom:** `done/dot/bambu_w8` has `seq_cells` 1264 on both technologies, against 1347 bits of `register_*` instances in `dot.v` (1360 with the controller's state, the stream modules' and `SIMPLEJOIN_FU`'s flags). No error.
- **Cause:** DC removes 96 register bits with `Information: The register '...' will be removed. (OPT-1207)`: `reg_3` and `reg_5` (32 bits each) drive the address input (`in2`) of the A and B AXI-stream read modules, which a stream does not use, and `reg_0` (32 bits) only feeds its own increment and select back into itself. 1360 - 96 = 1264.
- **Fix or check:** compare a Bambu point's `seq_cells` with the RTL's register bits minus the bits in `logs/dc_shell.log`'s OPT-1207 lines (each line is printed twice there: count the unique ones). A flop count from the RTL alone overstates Bambu's registers.
- **Found in:** `results/runs/2026-11-05_hsyn1_r4.md`.

### DC10. Vitis's flops: the elaborator trims bits and compile removes constants, with no OPT-1207

- **Symptom:** Vitis's dace points have 1 to 19 fewer `seq_cells` than the flop bits of their Verilog (every `<=` target's declared width): vecadd `dace_w16` 1163 against 1144, `dace_w1` 164 against 163. No OPT-1207 line.
- **Cause:** two steps. The elaborator (Presto) infers some registers narrower than declared, with no message: the `Inferred memory devices` tables in `dc_shell.log` give `loop_count_preg_reg` 31 bits for a 32-bit reg (1 to 5 bits per point). Then compile removes constant registers, `Information: The register '...' is a constant and will be removed. (OPT-1206)` (2 to 14 per point; Bambu's removals are unloaded registers, OPT-1207, DC9). Verilog bits - trimmed bits - OPT-1206 - OPT-1207 = `seq_cells` on all 31 Vitis points of tier done; the opt points lose none.
- **Fix or check:** to compare `seq_cells` with an HLS tool's RTL, sum the `Inferred memory devices` widths and subtract the unique OPT-1206 and OPT-1207 lines. For Bambu this table does not work: it lists each library design once (`register_SE_BITSIZE_in132_...`), not once per instance; use the instance parameters (DC9).
- **Found in:** `results/runs/2026-11-05_hsyn1_r6.md`.

### DC11. A rerun of one forge or char point widens the whole synth CSV

- **Symptom:** after `syn run` on one forge or char point, `git diff` shows every line of `results/forge/<tech>/synth_dc.csv` or `results/char/<tech>/char_synth.csv` changed, though only the rerun row's `date` differs in value.
- **Cause:** those CSVs were committed (SYN2, CHAR1) before X40 added the four `slack_<class>_ns` columns (HSYN1); `syn.py` writes every row with its current columns, so the old rows get the four columns empty and the rerun row gets them filled. The Vitis, Bambu and XLS CSVs already have them.
- **Fix or check:** compare such CSVs cell by cell on the committed columns, not line by line; rerunning the source's points fills the columns.
- **Found in:** `results/runs/2026-11-06_arc1_r1.md` (step 4).
- **Also:** `syn.py` writes the source's CSV from every run in `syn/runs/<source>/<tech>/`, so a local rerun that was never committed (ARC1's `done/vecadd/forge_w8`, 2026-11-06) comes back with any later run of the source: CSYN1 R1 and R2 each brought back its `date` (and in R1 its X40 slacks, accepted in R2). After a `syn run`, compare the CSV with the last commit by key, for the rows the run did not make (`results/forge/runs/2026-11-10_csyn1_r2.md`).

### DC12. An SRAM macro is DC's and PT's black box: its power is outside the four groups

- **Symptom:** a dace point with an SRAM macro (X62) synthesizes, and `syn.py` fails the row: `failed: power groups do not sum to the total dynamic power` (`done/dot/dace_w1` at DC's default activity: clock, register, sequential and combinational sum to 953.9 µW of the 1015.6 µW total; the black box holds the other 61.6).
- **Cause:** the macro's `.lib` cell has no function (PITFALLS LIB6), so DC and PT book it in the `black_box` group: its internal energy (at DC's default activity, or PT's averaged mode, PT7), its leakage (CACTI's, 8.5 mW for 2048 x 64), and the switching of the nets it drives.
- **Fix or check:** `syn.py` leaves the black box out of the sum check for a macro row; `sim/pwr.py` replaces its internal energy with the counted accesses (X50) and adds its output-net switching to the combinational group (X62). A row with a black box that is not a macro is still a failure.
- **Found in:** `results/hls/runs/2026-11-10_csyn1_r3.md`.

### DC13. On a loaded host DC runs on fewer cores than asked, for the whole run

- **Symptom:** the cluster run asked for 16 cores and DC printed `You requested 16 cores. However, load on host micas-lapserv1... is 25.10. Tool will ignore the request and use 7 cores. (UIO-231)`, then `Running optimization using a maximum of 7 cores. (OPT-1500)` at compile.
- **Cause:** `set_host_options -max_cores` checks the host's load once, when it runs, and lowers the cores for the rest of the run. `disable_multicore_resource_checks true` turns that check off, but `dc_syn.tcl` set it on the line after `set_host_options`, where it changes nothing.
- **Fix or check:** `SYN_IGNORE_LOAD=1` sets `disable_multicore_resource_checks true` before `set_host_options` (`dc_syn.tcl`); `cluster/cluster.py` sets it (X68), the other sources do not (their runs are unchanged). Check `OPT-1500`'s core count in `dc_stdout.log`: the cluster's rerun at load 31 used 16.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r3.md`.

### DC14. A stopped DC leaves its multicore child running, which holds the run's logs open

- **Symptom:** after `kill` of the cluster's DC (`common_shell_exec`), deleting the run folder failed with `OSError: [Errno 16] Device or resource busy: '.nfs0000...'` and `[Errno 39] Directory not empty: 'logs'`; a second `common_shell_exec`, a child of the first, was still running.
- **Cause:** a multicore DC runs a child process; killing the parent does not stop it, and on NFS a file it still holds open becomes an `.nfs` stub that cannot be removed until it exits.
- **Fix or check:** stop every `common_shell_exec` of the run (`pgrep -u $USER common_shell_ex`) and wait until none is left before cleaning up. `cluster/cluster.py`'s cleanup no longer packs over the zip `finish_run` wrote (the first stop lost its DC log that way) and runs each step even after one fails.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r3.md`.

### DC15. DC's tied-constant pseudo-cells look like unresolved black boxes

- **Symptom:** on a small cluster-like test design `cluster_check.tcl` reported `**logic_0**` as a leaf reference with no library cell and `is_black_box` true, so the unresolved and black-box gates failed.
- **Cause:** DC represents a net tied to 0 or 1 by a `**logic_0**` or `**logic_1**` pseudo-cell; it has no library cell and no area, and `report_reference` does not list it.
- **Fix or check:** `cluster_check.tcl` writes them as `constant` lines and leaves them out of the reference, library and black-box lines.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r3.md` (step 1's smoke test).

### DC16. The cluster's interconnect has two levels in `area_hierarchy.rpt`

- **Symptom:** the cluster's interconnect area quoted as `sparse_interconnect_i`'s, 107,878 um2, is the level above it.
- **Cause:** `i_cluster/gen_yes_snax_tcdm_interconnect.gen_sparse_interconnect.i_tcdm_interconnect` is `sparse_interconnect_wrapper` (107,877.9 um2), whose own logic (192.85 um2 of combinational cells) sits beside its child `sparse_interconnect_i`, the `SparseInterconnect` (107,685.0 um2). A row's columns are the instance, absolute total, percent, then the instance's own combinational, noncombinational and black-box area, then the design.
- **Fix or check:** compare a lone `SparseInterconnect` (xbar, xbar_mix) with `sparse_interconnect_i`, and say which level a number is. Sum a subtree's own columns for its comb and seq split (for `dot3_w16`: 105,722.5 and 1,962.5 um2).
- **Found in:** `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`.

### DC17. `syn.py run --dry-run -j N` interleaves its points' lines

- **Symptom:** a before-and-after `--dry-run` comparison of a whole source differs although nothing changed: points' blocks swap and lines of two points mix.
- **Cause:** `run` maps the points over a thread pool of `-j` workers, also with `--dry-run`, and each worker prints its point's lines as it goes.
- **Fix or check:** compare dry runs at `-j 1`, where the order is fixed (R3c: `xbar` 594 lines and `streamer` 3,696 lines, byte for byte).
- **Found in:** `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`.

### DC18. An output port nothing loads stays in the netlist with no driver

- **Symptom:** in the cluster netlist run (PWR1 R1) core 0's `axi_dma_busy_o` (`snitch_cc`) and dot_3's `dot_busy_o` (`snax_forge_dot_3_shell_wrapper`) are Z for the whole run, although the DMA and the group work: vsim's `find nets` finds both and `examine` gives `z`, and every window's SAIF has them at TZ = DURATION. On the RTL (CORE1 R2) the group's busy covers 133 of the run window's 185 cycles.
- **Cause:** nothing in the cluster loads either port, so DC (`compile_ultra`, hierarchy kept) removed the logic that drives them but kept the port in the module's header: each is declared `output` with no driver. The same boundary optimization leaves the SAIF's other Z nets (513,914 on `dot3_w16`): sub-design port bits nothing loads or that are tied constant, such as the crossbars' unused AXI data ports and the interconnect's read-only `io_tcdmReqs_*_bits_data`, which PT has no net for (PT6).
- **Fix or check:** take an internal status signal from the RTL run, not the netlist; a port kept in the netlist is no proof that it is driven (look for a driver in the module body, or at its SAIF entry). The cluster's windows come from `obs_o`, a port of the top driven by registers (X73).
- **Found in:** `results/cluster/runs/2026-11-12_pwr1_r1.md`.

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

### LIB5. nangate45's `.lib` puts a group and its first attribute on one line

- **Symptom:** a line-based Liberty reader loses its group nesting in nangate45's `NangateOpenCellLibrary_typical.lib` (RAM1 R3's first `ram/pins.py` raised on an unbalanced `}`).
- **Cause:** the zero-power groups are written `rise_power(scalar) {values ("0.0");` with the closing `}` on the next line (line 32065 and on).
- **Fix or check:** split the text into statements at `{`, `}` and `;` outside quotes, not at line ends (`ram/pins.py`, `statements`).
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md`.

### LIB6. lc_shell on a generated memory macro: the warnings and what each change does

- **Symptom:** `lc_shell` (Y-2026.03-SP2) compiles a minimal macro `.lib` with rc 0 and prints LBDB-172 six times (`default_fanout_load`, `default_inout_pin_cap`, `default_input_pin_cap`, `default_output_pin_cap`, `default_cell_leakage_power`, `default_leakage_power_density` not specified), LBDB-366 (`internal_power_calculation` in `char_config` required for an NLPM library), "Pin/bus ... has no 'function' attribute" on the output bus and LIBG-10 (failed to recognize the functionality of the cell).
- **Cause:** a black-box cell has no functional description; the library-level attributes have defaults lc_shell applies and reports.
- **Fix or check:** copy nangate45's `default_*` values (the same as lc_shell's defaults) and add `char_config () { internal_power_calculation : exclude_switching_on_rise_and_fall; }`: the LBDB lines go. The two functionality warnings stay and are expected; `is_memory_cell : true` changes nothing, and a cell `memory ()` group replaces them with LIBG-280 (memory groups deprecated, Information). None of this is needed for the `.db`, DC or PT (`ram/ram.py` writes no `memory` group).
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md`, `results/ram/runs/2026-11-05_ram1_r0.md` (LBDB-366, LIBG-280).

### LIB7. lc_shell Y-2026.03 writes no Liberty back from a `.db`

- **Symptom:** `write_lib <lib> -format lib -output x.lib` after `read_db` stops with `Error: Invalid output format 'lib'. (UIL-23)` and writes nothing; a script that diffs two such files then compares two missing files and can report them equal.
- **Cause:** this lc_shell writes `db` only.
- **Fix or check:** compare two `.db` files with `report_lib <lib>` (or DC's `get_attribute` on the lib pins, as RAM1 R3), and check that each output exists and is not empty before diffing.
- **Found in:** `results/runs/2026-11-06_arc1_r1.md` (step 4).

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
- **Also:** Bambu's `done/dot/bambu_w8` on nangate15 with a random register start (Q9) has `out_TVALID` = 1 before the first clock edge (a flop's random value); neither Bambu nor XLS raises TVALID in reset with `+initreg+0` (HSYN1 R5, `results/runs/2026-11-05_hsyn1_r5.md`). The same sinks handle it.

### Q8. nangate45's flops start with Q and QN both 0 under `+initreg+0`

- **Symptom:** before the first clock edge, XLS's `done/dot/xls_w16` on nangate45 drives `_res_TDATA` = `0000200000000000` with every register at 0; after the first edge it is 0.
- **Cause** (most likely; not traced net by net): nangate45's model file writes a flop as a behavioral module with two regs, `Q` and `QN` (`output reg Q, QN`, DFFR_X1). `+initreg+0` sets both to 0, so QN is not ~Q until the first edge loads them; logic that uses a flop's QN sees the wrong value for that half cycle. A random start (Q9) sets them independently too. nangate15's flops are UDPs with one state, `QN` a `not` of it.
- **Fix or check:** none needed: every TB holds reset for 5 cycles, so every flop has been clocked long before dumping starts. A TB that samples outputs before the first clock edge must not trust them on nangate45.
- **Found in:** `results/runs/2026-11-05_hsyn1_r5.md`.

### Q9. A random register start in Questa 2022.4: `vopt +initreg=ru` and `vsim +initreg+<seed>`

- **Symptom:** none by itself; the option is easy to get wrong. `vopt +initreg+0` (the default here) sets every variable and sequential UDP to 0. `vopt +initreg` with no value and no spec prepares 4-state (`r`), 2-state (`b`), enum (`e`) and UDP (`u`) variables for randomization, the TB's own `bit` and `int` flags and counters included.
- **Cause:** the spec selects the variable kinds (vopt -help: `+initreg[=<spec>][+0|1|X|Z]`); the seed is a vsim option (`+initreg+<seed>`), not vopt's.
- **Fix or check:** `sim/pwr.py run --initreg-seed N` uses `vopt +initreg=ru` (4-state regs: nangate45's behavioral flops; UDPs: nangate15's) and `vsim +initreg+N`; the sequencers give every flag an initial value. Check that it took: the outputs fed by unreset registers differ from 0 before the first edge (Bambu's `out_TDATA` = `10c0e48981e32dca` on nangate45 at seed 1). It is a check, never the default, and writes nothing to `results/`.
- **Found in:** `results/runs/2026-11-05_hsyn1_r5.md`.

### Q10. An `initial` block next to `always_ff` drives the same variable: vopt-7061

- **Symptom:** vlog accepts the model; vopt warns `(vopt-7061) Variable 'mem' driven in an always_ff block, may not be driven by any other process`, once per variable.
- **Cause:** RAM1 R3's first macro `.v` zeroed `mem`, the read address and `rdata_o` in an `initial` block under `SRAM_INIT_ZERO`, beside the `always_ff` that writes them.
- **Fix or check:** declaration initializers (`logic [63:0] mem [0:511] = '{default: '0};`) and an internal `rdata_q` with `assign rdata_o = rdata_q`; vopt is then clean. Check with `vsim -c` (elaboration), not vlog alone.
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md`.

### Q11. `process::self().srandom()` in an `initial` block does not seed the `always` blocks' `$urandom`

- **Symptom:** a TB that calls `process::self().srandom(<seed>)` in an `initial` block and draws its data with `$urandom` in `always` blocks gives the same data, and the same energy to every digit, whatever the seed (STRM1: `d8_l2_c4` at 20.29018 pJ per beat with seed 1 in R0 and seed 0 in R1).
- **Cause:** every SystemVerilog process has its own random generator, seeded at elaboration from the root seed. `srandom` reseeds only the process that calls it, here the `initial` block; the `always` blocks' generators keep their seeds from the root seed, which `vsim -sv_seed` sets (0 by default).
- **Fix or check:** seed through `vsim -sv_seed <seed>`, as `sim/pwr.py --source streamer|xbar` does with `--seed`; check that two seeds give different SAIFs.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r1.md`.

### Q12. RAM1's macro models are SystemVerilog in `.v` files: vlog reads them as Verilog-2001

- **Symptom:** the cluster's macro build (`snax-forge-sim` with `SRAM_MODELS`) stops with `(vlog-13069) .../sram_d128_w39.v(10): near "clk_i": syntax error, unexpected IDENTIFIER, expecting ')'` and `(vlog-13036) ... near "++": Operator only allowed in SystemVerilog`, 5 errors in the three models.
- **Cause:** `ram/ram.py`'s `gen_v` writes `input logic` ports, `always_ff`, `'{default: '0}` and `int b++` loops into `<macro>.v`; vlog takes a `.v` file as Verilog-2001 unless `-sv` is given, and snax_cluster compiles `SRAM_MODELS` with `vlog -f <file>` and no `-sv`. Verilator reads `.v` as SystemVerilog, so R2a's equivalence bench did not show it.
- **Fix or check:** `cluster/mem.py` writes `-sv` as the first line of `sram_models.f` (vlog takes options from a `-f` file; snax_cluster's `SRAM_MODELS_FILES` skips lines starting with `-` or `+`); `cluster/test_mem.py` checks it. A netlist run that compiles the models (R4) needs `-sv` too.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r2.md` (step 3).

### Q13. vsim's prints and the program's output share the log through separate buffers: a line can be cut by the other's

- **Symptom:** the cluster's macro run counted 35 `[tc_sram_impl]` prints for 36 instances; in `logs/snax-forge-vsim.txt` one print reads `# [tc_sram_impl] tb_bin....i_snitch_data_memforge cycles: 828`, the program's four `forge` lines follow, then the print's end, `.gen_banks[28].i_data_mem.gen_sram_d512_w64_m8: sram_d512_w64_m8`. The time-0 prints come out near the end of the run, beside the program's lines.
- **Cause:** `snax-forge-run` pipes vsim's stdout through `tee`; vsim's transcript lines and the testbench's C++ output of the program are written by separate buffers, each flushed when full or at exit, so the two interleave at buffer boundaries, not at line ends.
- **Fix or check:** read the log as a stream, not as whole lines: `cluster/check.py` counts the prints by their start (`[tc_sram_impl] `) and takes each one's macro from its end (`.gen_<macro>: <macro>`), and finds the `forge` lines with a search inside each line (`test_check.py` has R2's split). A `forge` line cut in two would fail D123 (a false FAIL, never a false PASS).
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r2.md` (step 3).

### Q14. The cluster netlist's I-cache macros take one write at time 0 under `+initreg+0`

- **Symptom:** `pixi run cluster gls dot3_w16` (CSYN1 R4): the 32 TCDM banks' RAMCOUNT lines equal the RTL macro run's, every macro's reads are equal, but the I-cache's four macros (2 data `sram_d128_w256_m8`, 2 tag `sram_d128_w39`) count 238 writes against 237. A trace of their ports puts the extra write at time 0, with `rst_ni` low and `addr_i` = `7'h7f`, in all four at once; the RTL run has none there (its `req_i` is X at time 0, which RAMCOUNT's `=== 1'b1` does not count).
- **Cause** (most likely; not traced net by net): Q8. Under `+initreg+0` nangate45's flops start with Q and QN both 0, so logic that reads a QN sees 1 until the first clock edge: the I-cache's flush logic drives request, write enable and an all-ones address at the time-0 edge. Harmless: reset is held, and the flush rewrites every line during reset (32 cycles of writes in the netlist, 31 in the RTL); D123 and the cycle count (828) are equal.
- **Fix or check:** `cluster/check.py`'s `ram_compare` allows exactly one more write on an instance of the netlist run, with reads equal on every instance; each such instance is listed in `gls/check.json` (`ram_extra_writes`: macro, reads, RTL and netlist writes) and named in the summary line (`writes equal but 4 macros +1 at reset (PITFALLS Q8)`). Two or more extra writes, any read difference, or an instance missing or added still fail (`test_check.py`). RAM1's models (`ram/ram.py`) were not changed to skip the time-0 edge: the model text is part of the macro cache key, so a change would rebuild every macro.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r4.md`.

### Q15. A DC netlist's instance paths hold escaped identifiers that end in a space

- **Symptom:** the cluster netlist run (CSYN1 R4) printed all 36 RAMCOUNT lines, but `cluster/check.py` read none: `RAMCOUNT (\S+) (\w+) reads ...` found no match. A vsim `when` on a macro port by its path stops with `vsim-3561 No objects found`.
- **Cause:** DC (`dc_syn.tcl` runs no `change_names`) names flattened generate blocks as escaped identifiers, `\gen_banks[0].i_data_mem` and `\gen_sram_d512_w64_m8.i_macro`, and an escaped identifier ends at a space, so `%m` prints `...i_snitch_data_mem.\gen_banks[0].i_data_mem .\gen_sram_d512_w64_m8.i_macro  sram_d512_w64_m8 reads 139 writes 139`: spaces inside the path and two before the macro. In vsim the path is `/.../\gen_banks[0].i_data_mem /...`; `find instances` prints the same instance as `{/.../gen_banks[0].i_data_mem} /...`, without the backslash.
- **Fix or check:** parse a path as everything up to the last whitespace before the next field (`RAMCOUNT (\S.*?)\s+(\w+) reads`; `test_check.py` holds two of R4's real lines). In vsim, `examine {/.../\gen_banks[0].i_data_mem /i_macro}/addr_i` works with the path in braces; a `when` condition does not take such a path, so trigger on a port with a plain path (the wrapper's `clk_i`) and `examine` the escaped one inside the handler. For `vcd add` the braces hold the whole word with its `/*` (`vcd add {/.../\gen_core[0].i_snitch_cc /*}`): `vcd add {...}/*` is a Tcl error, `extra characters after close-brace` (PWR1 R1). The VCD names such a scope without the backslash and the space (`gen_core[0].i_snitch_cc`), the SAIF from it with its brackets and dots escaped (`gen_core\[0\]\.i_snitch_cc`). Compare RTL and netlist runs without paths, or with backslashes and spaces removed and `/` for `.`.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r4.md`.

### Q16. Under `vopt +acc=n` a testbench's variables are not visible to vsim's commands

- **Symptom:** in the cluster netlist run, `when {/tb_bin/clk_i == 1'b1} {...}` stops with `vsim-3561 No objects found matching 'clk_i'`; the same `when` works on the RTL build, which is optimized with `+acc`.
- **Cause:** `+acc=n` keeps nets visible and nothing else; `tb_bin`'s `clk_i` and `rst_ni` are `logic` variables. Ports are nets, so the wrapper's `clk_i` and `rst_ni` stay visible.
- **Fix or check:** in a gate-level run, refer to the DUT's ports (`/tb_bin/i_dut/i_snax_forge_cluster/clk_i`), or add the testbench's scope to the access option for a debugging build only; `cluster gls` keeps `+acc=n` (Q2).
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r4.md`.

## vcd2saif

### VS1. `vcd2saif -time t0 t1` on a shared VCD adds a phantom toggle before the window

- **Symptom:** a window with no activity has toggles: on CHAR1's ElementwiseLanes `lanes/add_w8` (nangate45), 519 of the idle window's 3586 nets have TC 1 although the VCD has no change at all between t0 and t1, so idle cost 0.028 pJ per cycle instead of 0. The SAIF passes X9's checks (DURATION, the clock's TC, T0 + T1 + TX).
- **Cause:** the zero-delay simulation makes zero-width pulses: in one time step a net changes two or more times and ends where it began (a 64-bit adder when its inputs change). vcd2saif (Y-2026.03-SP2, the one on PATH) counts one toggle in the window for every net whose last change before t0 was such a pulse, however long before t0 it was: moving t0 later or t1 earlier does not remove it. Every one of the 519 nets, and no other, is such a pulse (checked net by net against the VCD). Inside a window vcd2saif counts net toggles correctly (pulses dropped); only the pulse before t0 leaks in, at most one toggle per net per window.
- **Fix or check:** cut the VCD into one file per window and run vcd2saif on the cut (`sim/pwr.py`'s `vcd_windows`, `--source char`): the header, every variable's value at the last time step before t0 as plain value changes (a `$dumpvars` block there makes vcd2saif start the window at the next event), the window's events, and a bare time step at t1 (vcd2saif ends a file's window at its last time step); both details cost 2.5 ns of DURATION when missing. On the cuts TC equals the VCD's net toggles on every net and T0, T1, TX equal the shared VCD's SAIF. SYN1 and SYN2's single-window runs (`--source hls` and `--source forge`) still run `vcd2saif -time` on the shared VCD after reset and the setup writes, so they may carry up to one phantom toggle per net over a window of 64 cycles or more; they are not rechecked here.
- **Found in:** `results/char/runs/2026-11-03_char1_r1.md`.

### VS2. A change to or from X is no toggle in vcd2saif's count

- **Symptom:** the cluster's DMA windows have far more nets with X time than the others: on `dot3_w16` 104,919 in `dma load_A` and 96,751 in `dma store_out`, against 2,708 to 3,156 in the other four windows. The SAIFs pass X9 (T0 + T1 + TX = DURATION).
- **Cause:** the X comes from the models, not the netlist. In the first DMA window the banks' read data is X before any read (RAM1's macro models start X and do not reset their read address, X66): `snax_tcdm_rsp[*][p][data]` (2,048 bits at the wrapper) is X for 15.5 % of the window, and the interconnect and response buffers carry it on. In `dma store_out` the DMA writes one word, so 448 of `wide_out_req_o[w][data]`'s 512 bits (the unfilled byte lanes) are X for 71 % of the window. vcd2saif counts TC on changes between 0 and 1, so a change to or from X is not counted.
- **Fix or check:** X66 is kept (models start X, no `SRAM_INIT_ZERO`). X stands for a value that holds still here, so a window misses at most one toggle per net leaving X, the size of VS1. In the SAIFs, 91,247 of the 104,919 X nets of `dma load_A` and 92,233 of the 96,751 of `dma store_out` hold X and one value with TC 0; 13,672 and 4,518 hold X, 0 and 1 (TC up to 253 and 1), and for those the SAIF does not say how often they leave X. Count a window's nets with X time (`saif_check`'s `tx_nets`) before reading its energy.
- **Found in:** `results/cluster/runs/2026-11-12_pwr1_r1.md`.

## PrimeTime

### PT1. PT applies the library's default wire-load model, hidden

- **Symptom:** on nangate45 nets carry wire capacitance and resistance that DC did not have (net `n964`: +15.44 fF and 0.31 kΩ; 3564 of 3566 nets with `wire_capacitance_max` > 0).
- **Cause:** PT applies the library's `default_wire_load` (`5K_hvratio_1_1`) whatever `auto_wire_load_selection false` and `remove_wire_load_model` say, before or after link. `report_design` hides it (`wire_load_model_max --`, and `default_wire_load` on the library reads empty); `report_wire_load` shows it, selection type `library default`.
- **Fix or check:** `set_load 0` and `set_resistance 0` on every net (`set_load -wire_load 0` is rejected on nets). Check `wire_load.rpt`: `with wire_capacitance_max > 0: 0, with net_resistance_max > 0: 0`; `sim/pwr.py` fails a run, and the setup check, when either count is not 0 (X25). On nangate15 it is a no-op, but harmless.
- **Found in:** `2026-10-29_pwr_step0.md` (Wire load).

### PT2. Default-activity propagation differs from DC's around enable logic

- **Symptom:** P0 (PT with DC's default toggle rate 0.1 and static probability 0.5) against DC's `power.rpt`: total +2.4%, register +35%, combinational +2.3%, clock -0.2%.
- **Cause:** vectorless propagation differs at the hold mux in front of each result flop, whose select is the pipeline enable from the FSM, a feedback loop PT and DC resolve differently (the 512 C data flops +37 to 39%, FSM flops +34%). With the same activity annotated on every net, the two agree to 0.00%.
- **Fix or check:** do not use P0 as the setup check; use the forced-activity pair (X10), a diagnostic since X25.
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

- **Symptom:** the setup check (X10, a diagnostic since X25) fails on nangate15: with the same uniform activity on every net, PT's combinational group is +1.95 % above DC's (internal +3.66 %, 15.469 against 14.922 µW; switching -0.12 %), register -0.08 %, clock -0.0003 %, leakage equal. nangate45 agrees within 0.0013 %.
- **Cause:** nangate15's cells have input-pin `internal_power` groups for toggles that do not switch the output (`when : "!A2 & ZN"` on NAND2_X1), and negative table entries (97 in NAND2_X1); nangate45 has neither. PT books more of it than DC: per cell type, internal power differs on NAND4_X1 (+32 %), NOR4_X1, OAI21_X1 and AND4_X1 (about +15 % each), NAND2_X1 (+14 %), AOI22_X1 (+10 %), NOR2_X1 (+8 %), while DFFSNQ_X1, FA_X1, XOR2/XNOR2, INV and BUF agree within 0.03 %. The switching difference (up to -1.3 % on NAND2/NOR2) is consistent with nangate15's `rise/fall_capacitance_range`; not traced further.
- **Fix or check:** the setup is the same in both tools (netlist, loads, constraints, leakage equal). PT is the reference tool for energy and the setup check is a diagnostic that never fails a point (X25, which replaces X10's tolerances: 2.5 % on nangate15's combinational group, 0.1 % elsewhere); its differences go into the run note.
- **Found in:** `2026-10-29_pwr_r1.md` (setup-check).
- **On snax-forge's wrapper** (`pwr setup-check --source forge`, `done/vecadd/forge_w4`, SYN1 R2): nangate45 agrees within 0.02 % in every group; nangate15's register group is -0.55 % (switching -1.49 %, 1.92299 against 1.95198 µW; internal -0.15 %), over its 0.1 %, and combinational +1.17 %, within 2.5 %. The activity is the same in both tools; holding `rst_ni` static changes nothing (the flops' asynchronous reset is not it); a few register-driven nets have up to 1.5 % less load in PT (`_ctrl_io_groups_0_status[0]` 35.34 against 35.88 fF). Only nangate15 has `rise/fall_capacitance_range` (338 entries, none on nangate45), the same switching difference this entry found on NAND2/NOR2, here on the flops' output nets. Why the register group differs, checked on `dot/forge5_w4` (2026-11-01): the two tools add up a net's pin load differently on nangate15's `rise/fall_capacitance_range`. PT takes the larger of the sum of the load pins' rise-range upper bounds and the sum of their fall-range upper bounds; DC sums, pin by pin, the larger of the two upper bounds (it matches DC's net load on 227 of the 227 flop nets DC's flat report names), so PT's load is at most DC's and lower where the pins of a net disagree (`io_status[0]`: 6.091 against 6.600 fF). nangate45 has no ranges. Settled in X25 (no tolerance; PT is the reference, the register group is 1.3 % to 14 % of e_dyn on these points). Found in `results/forge/runs/2026-10-31_syn1_r2.md`. SYN1 R3 on nangate15: `done/dot/forge5_w4` register -1.08 %, combinational +2.21 %; `done/vsum/forge_w8` register -0.25 %, combinational +1.79 %; the HLS point `done/vecadd/opt_w8` again register -0.08 %, combinational +1.95 % (as in `2026-10-29_pwr_r1.md`), so the register gap is the forge netlists' (`results/forge/runs/2026-11-01_syn1_r3.md`).
- **On Bambu and XLS** (`pwr setup-check --source bambu|xls`, HSYN1 R5): nangate45 within 0.03 % (Bambu register -0.026 %) and 0.005 % in every group; nangate15 `done/dot/bambu_w8` register -0.91 %, combinational +2.22 %; `done/dot/xls_w16` register -0.45 %, combinational +2.00 %; clock and leakage equal. The same pattern as Vitis and forge (`results/runs/2026-11-05_hsyn1_r5.md`).

### PT6. PT counts floating port nets of a constant output as not annotated

- **Symptom:** on snax-forge's wrapper, PT annotates 2130 of 2190 nets from the SAIF (97.3 %, under X9's 99 %): the 60 left are `ctrl/io_groups_0_status[2..31]` and `csr/io_status_0[2..31]`, at `Default` activity. vcd2saif has them at Z for the whole window.
- **Cause:** STATUS bits 2 to 31 are constant 0 (R1's LINT-52). With boundary optimization DC removes the constant, bit-blasts the ports (`\io_status_0[5] `) and leaves both ends without a driver or a cell pin. Unlike DC5's undriven wire bits, they are hierarchical port nets, so PT counts them. They cost nothing: with the 60 forced to toggle rate 0, PT's power is the same in every group to seven digits.
- **Fix or check:** `sim/pwr.py` (forge source) takes a non-annotated net that the SAIF has at Z for the whole window out of the coverage denominator, records them (`floating` in `result.json`), and still requires 99 % of the rest (X23); every other net must be annotated. The HLS check is unchanged.
- **Since CTRL1** (snax-forge `f9764d5`, D152): STATUS is 2 bits wide, so its constant bits and their floating port nets are gone; SYN2 R2 had no floating net in any of its 96 runs and the exclusion is no longer needed. It stays in `sim/pwr.py` (it changes nothing when there is none) for SYN1's netlists.
- **Found in:** `results/forge/runs/2026-10-31_syn1_r2.md`.

### PT7. Averaged mode charges `when` internal power with independent pin probabilities

- **Symptom:** a memory macro whose `.lib` charges the read energy `when "req_i & !we_i"` and the write energy `when "req_i & we_i"` (rising edge of `clk_i`) gets 12.46 % less internal energy in PrimePower's averaged mode (SAIF from vcd2saif) than the counted accesses times the `.lib`'s energies; time-based mode on the same VCD gives the counted figure to 1e-7.
- **Cause:** the SAIF holds each net's own static probability and toggle count, not joint states, so PT takes P(req & !we) = P(req) x P(!we). On the probe's 1,000 reads, 1,500 writes and 1,500 idle cycles (we_i low when idle) that is 0.39 reads and 0.23 writes per cycle against the true 0.25 and 0.375; the averaged figure equals that product to 0.004 pJ. The gap depends on the mix and on what we_i does while idle.
- **Fix or check:** report memory energy as counted accesses x the table (the macro `.v`'s `RAMCOUNT`), or from time-based PT on the VCD, not from averaged PT.
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md` (step 6).

### PT8. `report_switching_activity -nosplit` stops the script

- **Symptom:** `Error: unknown option '-nosplit' (CMD-010)` written into the redirected report, then `Errors detected during redirect` (CMD-013) and the script stops (CMD-081); the reports after it are missing.
- **Cause:** `report_switching_activity` has no `-nosplit` (W-2024.09-SP5); `report_power` has.
- **Fix or check:** no `-nosplit` on it (as `sim/scripts/pt_power.tcl`).
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md`.

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

### L4. `compile_ultra` needs a DC-Expert licence as well as Design-Compiler

- **Symptom:** with J DC runs sized from the free Design-Compiler licences alone (9), some runs end with `Error: All 'DC-Expert' licenses are in use. (SEC-50)` at `compile_ultra`; DC still writes its reports, of an empty design: `area.rpt` with a total cell area of 0. Before commit `c44ac94` syn.py took such a row as ok (area 0, slack 9.88 ns, errors 1) after its licence retry also failed.
- **Cause:** `compile_ultra` checks out DC-Expert besides Design-Compiler; both have 10 licences on 1709@licserv, used by other people independently. LICENCE_ERROR matched the line and the run was retried once (X17), but read_run failed a row only when the area report was missing.
- **Fix or check:** J = min(free Design-Compiler, free DC-Expert) at each batch's start (`lmutil lmstat -f Design-Compiler`, `-f DC-Expert`); since `c44ac94` syn.py fails a row with a licence error or an area of 0 whatever its reports say.
- **Found in:** `results/runs/2026-11-05_hsyn1_r6.md`.

## CACTI

### C1. CACTI reads `tech_params/` relative to its working directory

- **Symptom:** CACTI 7 (`1ffd8df`) run from any folder but its own echoes its input parameters and dies with a segmentation fault (rc 139, core dumped), with no message about a missing file.
- **Cause:** `parameter.cc` opens `"tech_params/<node>.dat"` (here `tech_params/45nm.dat`) by a relative path and does not check the `fopen`.
- **Fix or check:** run CACTI from `ram/cacti/`, or link `tech_params` into the run folder; `ram/ram.py` runs each point in a folder under `tmp/` (X51; `ram/runs/cacti/<point>/` before) with `tech_params` (and `contention.dat`) linked in. A run with rc 139 and no `Cache Parameters:` block in its output is this.
- **Found in:** `results/ram/runs/2026-11-05_ram1_r1.md`.

### C2. `cache.cfg`'s `-Optimize "ED^2"` overrides the design objective

- **Symptom:** changing `-design objective` or `-deviate` has no effect on the organization CACTI picks or on its numbers.
- **Cause:** with `-Optimize ED or ED^2` set to `ED` or `ED^2` (`cache.cfg` has `"ED^2"`), `find_optimal_uca` (`Ucache.cc`) minimizes the energy-delay product and ignores the objective weights and the deviate line.
- **Fix or check:** `-Optimize ED or ED^2 (ED, ED^2, NONE): "NONE"`; `ram.py` sets it (X47). Two runs with different objectives that give identical numbers are this.
- **Found in:** `results/ram/runs/2026-11-05_ram1_r1.md`.

### C3. `cache.cfg` turns ECC on

- **Symptom:** area, energy and leakage about 12 % higher than the bank needs (512 x 64: area +11.2 %, read +13.5 %, write +13.0 %).
- **Cause:** `cache.cfg` has `-Add ECC - "true"`, which adds one bit per 8 data bits to every data signal on the H-trees (`ECC_adjustment`).
- **Fix or check:** `-Add ECC - "false"` for a bank without ECC (a TCDM bank has none); `ram.py` sets it (X47), `point --ecc` turns it on for a one-off check.
- **Found in:** `results/ram/runs/2026-11-05_ram1_r1.md`.

### C4. A size CACTI rejects exits with rc 0

- **Symptom:** CACTI exits 0 and writes no results; the reason is one line on stderr (`Cache size must >=64`).
- **Cause:** CACTI checks the size before modelling and returns normally after printing the message. Depth 16 fails at every width with `ERROR: no valid data array organizations found` (rc 1): it needs at least 2 x 16 rows.
- **Fix or check:** do not trust the return code; `ram.py` marks a point failed unless `cacti.out` holds the access time, both energies, the data array's area and the height x width, and gives stderr's error lines in `status`. Smallest modelled sizes: 64 bytes and 32 words.
- **Found in:** `results/ram/runs/2026-11-05_ram1_r1.md`.

### C5. CACTI's numbers jump between neighbouring sizes

- **Symptom:** interpolating between table points, or fitting a curve, misses by up to 30 to 40 % at some sizes, however dense the points; for example 480 x 200 reads at 14.07 pJ where 448 x 200 reads at 9.53 pJ.
- **Cause:** CACTI picks the array organization (Nspd, Ndcm, Ndbl) per size; where the choice changes between two neighbouring sizes, area and energy step. Against the mean of its four neighbours on the 32-word by 8-bit grid, a point differs by 0.4 / 1.1 / 1.0 % on average (area / read / write) and up to 15 / 28 / 30 %.
- **Fix or check:** look up the exact size in `ram_table.csv` (X48) instead of interpolating or fitting; the `nspd` and `ndcm` columns show where the organization changes.
- **Found in:** `results/ram/runs/2026-11-06_ram1_r2.md`.

### C6. CACTI's cycle time is shorter than its access time

- **Symptom:** `t_cycle_ns` < `t_access_ns` in the table: 0.210 against 0.269 ns at 512 x 64, 0.222 against 0.235 at 128 x 256, 0.151 against 0.198 at 128 x 40.
- **Cause:** CACTI's SRAM cycle time is the mat's own cycle: the delay inside the mat plus wordline reset and bitline restore, or a predecoder's delay if longer (`uca.cc`, `UCA::compute_delays`); the access time adds the H-tree delays to and from the mats, which the cycle time leaves out.
- **Fix or check:** the generated `.lib` uses `t_access_ns` for clk-to-`rdata_o` and `t_cycle_ns` only for `min_period` and the min pulse widths; at the 10 ns clock (X2) neither limits.
- **Found in:** `results/ram/runs/2026-11-06_ram1_r3.md`.

## Environment

### E1. `pixi run python -c "..."` loses the inner quotes

- **Symptom:** `SyntaxError` from a one-liner that runs under plain `python -c`: `'...'` strings inside the double-quoted code arrive without their quotes.
- **Cause:** pixi runs the command through its own task shell, which parses the quoting again.
- **Fix or check:** put the code in a script file and run `pixi run python <file>` (or a heredoc to `pixi run python -`).
- **Found in:** `2026-10-29_pwr_r1.md`.

### E2. A forge power run needs snax-forge at a commit that still loads the bundle's design point

- **Symptom:** `pwr run ... --source forge` on a SYN2 bundle fails at tb.json with `snax_forge.design.problems.DesignError: ... [graph.brm] node add: no BRM 'elementwise_add' in the library (['accumulate', 'mac', 'simd'])`; DC on the same bundle works.
- **Cause:** `sim/sources/forge.py` asks snax-forge (`forge/query.py point`) about the bundle, and `query.py` loads the design point `bundle.json` names (`out/design/syn1/<point>/design_point.json` in the snax-forge checkout) with the checkout's own code. From DRY1-2 (snax-forge #52) the BRM library is indexed by family, and a design point from before (the bundles' `f9764d5`) no longer loads, on `main` as on the DRY1-3 branch.
- **Fix or check:** run the forge power flow with snax-forge at the bundle's `snax_forge_commit` (its `point.json`): `git -C ../snax-forge checkout --detach <commit>`, the run, then back (the pixi lock is the same from `f9764d5` to `f49c394`), or rebuild the bundles (`pixi run forge-rtl`). From snax-forge D168 (CTRL2) a bundle made before it fails the same way, in snax-forge's own platform check: `[platform.keys] acc_csr: unknown keys ['counter_width'] (allowed: ['job_width', 'busy_counter_width'])`; `sim/sources/forge.py` now refuses a bundle without a BUSY_COUNTER CSR before it asks snax-forge, with that cause in the message.
- **Found in:** `results/runs/2026-11-06_arc1_r1.md` (step 4); the D168 case in `results/forge/runs/2026-11-11_ctrl2_r5.md` (step 1).

### E3. `git diff --word-diff` on a CSV marks whole rows

- **Symptom:** a word diff of a results CSV shows complete rows removed and added though a single cell changed.
- **Cause:** a CSV row has no spaces, so it is one word.
- **Fix or check:** compare CSVs by key, cell by cell (parse both with `csv.DictReader`); keep line-level diffs for checking that a file is byte for byte the same.
- **Found in:** `results/runs/2026-11-06_arc1_r1.md` (step 4).

### E4. snax-forge's relu, matadd and axpy recipes bundle int32 datapaths

- **Symptom:** `untiered/relu/forge_w4`'s bundle (snax-forge `e8bb93e`) has ports `int32 x 4` on 2 channels, axpy's K1 is one 32-bit CSR; nothing fails, the rowsums and every tier done recipe are int64, and every HLS point is int64.
- **Cause:** snax-forge's kernels `relu`, `matadd` and `axpy` are int32 (its D113, two per 64-bit word); a recipe keeps the kernel's dtypes unless its `dtypes` field says otherwise, and these recipes have none.
- **Fix or check:** X57: `forge/points.json` gives these points `dtypes` int64 and `forge/bundles.py` feeds the sandbox snax-forge's recipe with that field. Check `accelerator.json`'s port dtypes (and a scalar's `K1_LO`, `K1_HI`) before measuring a new recipe; `sim/sources/forge.py` refuses any port that is not int64.
- **Found in:** `results/forge/runs/2026-11-10_csyn1_r1.md` (step 1).
- **Also in hls-exercises' DaCe sources:** `bench/gen/gen_dace.py` builds DaCe's SDFG from snax-forge's kernel, so regenerating axpy's dace case on today's snax-forge turned every `int64_t` of `axpy_0_0.cpp` into `int` (CSYN1 R3). `gen_dace.py` now builds every container at `params.json`'s `dtype` (`KernelSpec.with_dtypes`); diff a regenerated dace source before running Vitis on it.

### E5. snax-forge's module names carry the design's name since D157

- **Symptom:** a bundle from snax-forge `e8bb93e` has `snax_forge_dot_4_shell_wrapper`, `snax_forge_dot_4_ctrl`, ... where the SYN1 bundles (`f9764d5`) had `snax_forge_shell_wrapper`, `snax_forge_ctrl`; vecadd's `ElementwiseLanes_*` is `SimdLanes_*`. A byte diff of the SV says every file changed.
- **Cause:** the tag is `<accelerator_slot>_<design name>` (snax-forge's `gen/accelerator.py` `tag`), and the lanes block was renamed; `accelerator.json` also nests groups under `accelerators` (`forge/query.py`'s `flat` reads both forms).
- **Fix or check:** compare SV with the tag and block names masked, `forge/sv_diff.py` (CSYN1 R1: dot_4 and vecadd at W = 4 identical; R2: the 41 tier done points at W <= 16 and vsum W = 32 identical, the other six W = 32 points no longer bundle, `connect.xbar_inputs`). `syn.py` takes the three modules from `bundle.json` and follows the names; `report/compare.py`'s `PARTS` still names `snax_forge_csr`, `snax_forge_ctrl`, `snax_forge_datapath` and must match by suffix before it reads rows of new bundles.
- **Found in:** `results/forge/runs/2026-11-10_csyn1_r1.md` (step 1).

### E6. hls-exercises' CSVs have CRLF line ends, and `Path.read_text` hides them

- **Symptom:** removing six rows from `results/hls/hls_cycles.csv` with a script made git show every one of its 121 lines changed.
- **Cause:** `bench.py` writes the CSVs with `csv.writer`, whose line end is `\r\n`; `Path.read_text()` translates it to `\n`, so a test for `"\r\n"` in the text is false and the file was written back with `\n`.
- **Fix or check:** edit such files as bytes (or keep `newline=""` and `csv.writer`'s default), and check `git diff --stat` before committing.
- **Found in:** `results/hls/runs/2026-11-10_csyn1_r3.md`.

## snax_cluster's generators (STRM1)

### SC1. A reader of a streamer set is named with a double underscore

- **Symptom:** the reader of `StreamerGen --tag-name strm` is `strm__C0_Reader`, not `strm_C0_Reader`; a script that builds the name from the tag misses the module.
- **Cause:** `StreamerGen` sets `tagName` to `<tag-name>_`, and `Streamer` names reader i `tagName + "_C" + i`.
- **Fix or check:** `strm/gen.py` builds the name the same way (`config.json`'s `top`) and fails a point whose SV has no such module.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC2. The bundled reader is the reader as the Streamer uses it: firtool trims its unread ports

- **Symptom:** `strm__C0_Reader` has no `io_bufferEmpty` port, and its TCDM request ports carry only `addr` and `priority`, with no `write`, `data` or `strb`, although `ReaderIO` declares them.
- **Cause:** firtool elaborates the whole Streamer; in a module that is not the top it removes the output ports the parent never reads and propagates the constants the parent ties. No register goes with them (DC's flops equal the RTL's bits on every point); only the comb logic of `dataBuffer.io.allEmpty`'s reduction is missing.
- **Also:** at 1 channel (`spatial_bounds [1]`) the spatial stride multiplies only channel 0's index, 0, so `io_aguCfg_spatialStrides_0` is gone too (STRM1 R1: the TB's port check refused the 28 `*_c1` points until the TB followed the netlist's ports).
- **Fix or check:** none needed for STRM1: the cost of a reader inside a streamer is what the model wants (X52). A reader emitted as its own top (`ReaderEmitter`) would keep the ports. A TB connects what the netlist has: `sim/sources/strm.py` checks every connected port against the netlist's and every netlist port against the connected ones.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`, `results/strm/runs/2026-11-06_strm1_r1.md`.

### SC3. `StreamerGen` always writes a CSR header

- **Symptom:** without `--header-dir`, `StreamerGen` stops with `--header-dir is not provided`; with it, `streamer_csr_addr_map.h` appears there.
- **Cause:** `Streamer.writeCsrAddrMap` runs in the class body, as a side effect of elaboration (it keeps `make rtl` self-contained).
- **Fix or check:** `strm/gen.py` points `--header-dir` into `tmp/strm/` and drops the header with the folder.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC4. `git archive` leaves out submodules

- **Symptom:** in a `git archive` copy of snax_cluster's `hw/chisel` and `hw/chisel_acc`, `hw/chisel_acc/subprojects/chisel-float` is an empty folder, which `hw/chisel/build.sbt` needs (`ProjectRef`).
- **Cause:** chisel-float is a submodule, and `git archive` writes a gitlink as an empty folder.
- **Fix or check:** `strm/gen.py` reads the gitlink (`git ls-tree <commit> hw/chisel_acc/subprojects/chisel-float`) and archives the submodule's checkout at that commit into the copy; it refuses when the checkout does not have the commit.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC5. `sbt -batch` stops at the first failing command

- **Symptom:** one point whose `runMain` fails leaves every later point of the same sbt call ungenerated, with no error of its own.
- **Cause:** sbt runs its command-line commands in order and stops at the first failure.
- **Fix or check:** `strm/gen.py` reports the points after a failure as not run (`runMain not run (sbt stopped before it)`); the next call skips the points already made and generates the rest. R1 had no failure.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC6. The image has no Scala caches of its own

- **Symptom:** every `podman run` of image `d3d8f5572ff4` downloads the sbt launcher, sbt, Chisel's dependencies and firtool; on 2026-11-04 about 70 such runs in a day got the host rate-limited by Maven (HTTP 429, then a launcher `shasum mismatch`).
- **Cause:** the image has no `/root/.sbt`, coursier or `llvm-firtool` cache, and a container's are gone when it exits.
- **Fix or check:** mount the home folder's caches under `/root` (`strm/gen.py`: `~/.sbt`, `~/.ivy2`, `~/.cache/coursier`, `~/.cache/sbt`, `~/.cache/llvm-firtool`, created when missing); with them STRM1's generation downloaded nothing (about 3,000 inodes, 778 MB).
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC7. Counting `reg` declarations overstates a firtool design's registers

- **Symptom:** a count of every `reg` in firtool's SV gives 32 more bits per `ram_<d>x<w>` and more for each register block than DC's flops.
- **Cause:** firtool declares `_RANDOM` and `_RANDOM_MEM` temporaries inside its `ifdef ENABLE_INITIAL_REG_` and `ENABLE_INITIAL_MEM_` blocks, which exist only in simulation.
- **Fix or check:** skip `_RANDOM*` (`strm/gen.py`'s `flop_bits`): the count then equals DC's `seq_cells` on every STRM1 point (syn.py's flop check).
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC8. A temporal stride of 0 is the reader's repeat mode

- **Symptom:** a reader configured with `temporalStrides_0` = 0 delivers `temporalBounds_0` copies of each beat and generates fewer addresses than the bounds' product.
- **Cause:** `Reader` sets loop 0's bound to 1 for the address generator when its stride is 0 and repeats each beat `temporalBounds_0` times on the output (`HandShakeRepeater`).
- **Fix or check:** the STRM1 TB uses unit strides, never 0 (`sim/sources/strm.py`'s `strides`), and checks every request address.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r0.md`.

### SC9. A reader's loop stride is 16 bits, not the 17 its port has

- **Symptom:** a reader at 16 channels and 6 or 7 loops, configured with an outermost stride of 65,536 B, delivers every beat with the right data but sends half of its 16,384 requests to the wrong address (8,192 address mismatches); nothing else fails.
- **Cause:** `io_aguCfg_temporalStrides_<k>` is `addressWidth` (17) bits, but `ProgrammableCounter`'s `step` input is `width - 1` (16) bits, so a stride of 2^16 B becomes 0: loop k never moves. With 1,024 beats over 6 or 7 loops and the larger bounds innermost, the outermost bound is 2 and its stride 8 x 16 x 512 = 65,536 B.
- **Fix or check:** the largest stride a reader takes is 65,535 B. `sim/sources/strm.py` puts the larger bounds outermost (the outermost stride is then at most 32,768 B on the grid) and refuses a stride over the step's range before simulating; the TB checks every request address.
- **Found in:** `results/strm/runs/2026-11-06_strm1_r1.md`.

### SC10. snax_cluster's synthesis list had no iDMA

- **Symptom:** DC on the whole cluster: `Unable to resolve reference 'idma_inst64_top' in 'snitch_cc_...'. (LINK-5)`, and the netlist would hold no DMA engine; `syn_flist.tcl` had iDMA's include paths and none of its files.
- **Cause:** iDMA's `Bender.yml` puts every source (`idma_inst64_top`, the midends, the backends, `target/rtl/idma_generated.sv`) under bender target `rtl`; vsim and vcs pass `-t rtl`, `gen-syn`'s `SYN_BENDER` passed only `-t synthesis`.
- **Fix or check:** snax_cluster #693 (main `7c14681c`) adds `-t rtl` to `SYN_BENDER`; it adds exactly iDMA's 34 files. `cluster_check.tcl` and syn.py's LINK-5 count fail a cluster row with an unresolved reference.
- **Found in:** `results/cluster/runs/2026-11-11_csyn1_r3.md`.

### E7. A snax-forge submodule off main's pin marks every bundle dirty

- **Symptom:** snax-forge's `git status --porcelain` lists ` M gvsoc/snax-gvsoc` although nothing was edited, and `forge/bundles.py` would refuse every bundle as dirty (its `bundle.json` `dirty: true`).
- **Cause:** snax-forge's `gen/bundle.py` `provenance` takes the work tree as dirty on any `git status --porcelain` line, a submodule whose checkout differs from the commit the superproject pins included. After a branch is squash-merged, `git pull` on main moves the pin to the squash commit of the submodule's own PR while the submodule stays on the branch's commit (CTRL2: snax-gvsoc `0a378cdf` on `ry/ctrl2`, main pins `85552fc4`); the trees can be the same.
- **Fix or check:** before bundling, `git -C ../snax-forge status --porcelain` must be empty; for a submodule line, check the submodule has no local change (`git -C <sub> status --porcelain`) and run `git -C ../snax-forge submodule update <sub>`. The bundles do not read the submodule.
- **Found in:** `results/forge/runs/2026-11-11_ctrl2_r5.md` (step 3).

## Zips (X51)

### Z1. A rerun's report zip changes in git with the same numbers

- **Symptom:** after a `syn` or `pwr` rerun that changes no number, `results/<source>/<tech>/reports/<point>.zip` and `power_reports/<point>.zip` show as modified.
- **Cause:** the zips are deterministic in their contents, not in the tools': every DC and PT report has a `Date   :` line, `qor.rpt` the compile's CPU times, and `tech.json` the `--cores` of the run.
- **Fix or check:** compare a rerun's zip with the committed one member by member, the `Date` lines, `qor.rpt`'s CPU-time lines and `tech.json`'s cores aside; commit a rerun's zips only with a change that is meant.
- **Found in:** `results/runs/2026-11-06_arc1_r1.md` (step 4).
