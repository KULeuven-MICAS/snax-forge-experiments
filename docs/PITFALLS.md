# Pitfalls

Tool behaviour that gives wrong numbers, or no numbers, without an error. One line per pitfall, grouped by tool: what goes wrong, why, and the fix or check, with the decision it led to. The run notes that found them are in git history.

IDs are never reused; retired: LIB1, LIB3, LIB4 and PT5 (the 15 nm library, removed by X88).

## DC

- **DC1. `auto_wire_load_selection false` does not remove nangate45's wire-load model.** The library's `default_wire_load 5K_hvratio_1_1` stays; `dc_syn.tcl` removes that attribute before elaboration and `syn.py` fails a run whose `area.rpt` names a model (X3; a critical path 22 % longer with it).
- **DC2. A library in other units takes every constraint 1000x off.** SDC values are read in the library's units; constraints are written in ns and fF, scaled by `T_SCALE` and `C_SCALE`, and `dc_syn.tcl` stops on a name or unit mismatch (X4).
- **DC3. Results depend slightly on names and order.** The same Verilog with other names moves the area by up to 0.02 %; treat that as noise and compare an equal-Verilog pair when in doubt.
- **DC4. Power at default activity follows logic structure, not work.** DC's toggle rate 0.1 on every input runs through logic that never works in a real run (vecmul dace 100 pJ against opt 13.5 pJ per cycle at equal area); energy comes from simulated activity (X7).
- **DC5. Undriven bits in declared vector wires.** DC keeps a vector's declaration after removing the logic behind most bits, which sit at Z; `saif_check` parses the optional TZ, counts all-Z entries apart and fails a parse that misses entries.
- **DC6. Some module headers in DC's netlists are indented.** The first module after the header block starts with spaces, so a parser misses it (a multiplier's scope went undumped); match `^\s*module`, and X9's 99 % annotation catches a large miss.
- **DC7. DC Y-2026.03-SP2 crashes on a 1-bit-select mux inside an adder, under a branch on the same bit.** firtool's partial fold of SerialAccumulate at 2 lanes killed `compile_ultra` (Error id=834758); fixed in snax-forge by writing the update as `Mux(first && lane === 0, 0, acc) + x`.
- **DC8. Bambu's declaration initializers are dropped (VER-708).** DC ignores Verilog power-on values, so those flops start at X; the power flow starts every flop at 0 with `vopt +initreg+0` (Q1).
- **DC9. A Bambu point has fewer flops than its register instances.** DC removes unloaded registers (OPT-1207, 96 bits on `done/dot/bambu_w8`); compare `seq_cells` with the RTL's bits minus the unique OPT-1207 lines.
- **DC10. Vitis's flops: the elaborator trims bits and compile removes constants, with no OPT-1207.** Sum the `Inferred memory devices` widths and subtract the unique OPT-1206 and OPT-1207 lines; for Bambu use the instance parameters (DC9).
- **DC11. A rerun of one point widens the whole synth CSV.** Old rows predate the path-class columns (X40) and get them empty on the next write; compare such CSVs cell by cell on the committed columns.
- **DC12. An SRAM macro is DC's and PT's black box: its power is outside the four groups.** `syn.py` leaves the black box out of the sum check for a macro row and `pwr.py` replaces its internal energy with the counted accesses (X50, X62); a black box that is not a macro still fails.
- **DC13. On a loaded host DC runs on fewer cores than asked, for the whole run.** `set_host_options` checks the load once (UIO-231); `SYN_IGNORE_LOAD=1` sets `disable_multicore_resource_checks` before it, as the cluster runs do (X68); check OPT-1500's core count.
- **DC14. A stopped DC leaves its multicore child running, which holds the run's logs open.** Stop every `common_shell_exec` of the run and wait before cleaning up; on NFS an open file leaves an `.nfs` stub.
- **DC15. DC's tied-constant pseudo-cells look like unresolved black boxes.** `**logic_0**` and `**logic_1**` have no library cell; `cluster_check.tcl` lists them as constants, out of the reference and black-box gates.
- **DC16. The cluster's interconnect has two levels in `area_hierarchy.rpt`.** `sparse_interconnect_wrapper` holds 193 µm² of its own beside `sparse_interconnect_i`; compare a lone SparseInterconnect with the inner level and say which level a number is.
- **DC17. `syn.py run --dry-run -j N` interleaves its points' lines.** Compare dry runs at `-j 1`, where the order is fixed.
- **DC18. An output port nothing loads stays in the netlist with no driver.** Such a port reads Z for the whole run although the logic behind it works; take an internal status from the RTL run, never from a netlist port.

## Libraries

- **LIB2. Neither cell model file uses `` `celldefine ``.** vsim cannot tell a cell from a module, so `-nocellnet` has no effect; use `power add <dut>/*` without `-r` on flat netlists (Q3).
- **LIB5. nangate45's `.lib` puts a group and its first attribute on one line.** A line-based Liberty reader loses its nesting; split the text into statements at `{`, `}` and `;` outside quotes (`ram/pins.py`, `statements`).
- **LIB6. lc_shell on a generated memory macro: the warnings and what each change does.** Copying nangate45's `default_*` values and a `char_config` group clears the LBDB lines; the two functionality warnings of a black-box cell stay and are expected (X49).
- **LIB7. lc_shell Y-2026.03 writes no Liberty back from a `.db`.** `write_lib -format lib` fails (UIL-23) and writes nothing; compare `.db` files with `report_lib`, and check each output exists before a diff.

## Questa

- **Q1. Gate-level X from Vitis registers without reset.** Vitis starts unreset registers in `initial` blocks the netlist does not have; `vopt +initreg+0` starts every flop at 0, and the testbench's X check and timeout catch the rest.
- **Q2. `+acc=n` is needed or `power add` finds no nets.** vopt hides the netlist's nets otherwise; `+acc=n` costs nothing measurable.
- **Q3. `power add` with or without `-r`.** Without `-r` only the top level's nets are added, with it cell-internal nets too (LIB2); `-r` only on netlists with sub-designs.
- **Q4. `power report -bsaif` is wrong at zero delay (Questa 2022.4).** It gives 13 to 34 % less energy than the VCD of the same run with no warning; use the VCD and vcd2saif (X8, X9).
- **Q5. VCD size.** A VCD grows with nets x cycles; dump only the window and delete it after vcd2saif (X18).
- **Q6. `$dumpon` at a window boundary loses the boundary's clock edge.** Dump from the rising edge before the window to the one after it and let vcd2saif cut the window; X9's clock check catches a lost edge.
- **Q7. A falling edge at time 0, and TVALID high in reset.** `logic clk = 0` fires `@(negedge clk)` at time 0, and a netlist may drive TVALID in reset; count beats only once reset is released (`axis_sink.sv`).
- **Q8. nangate45's flops start with Q and QN both 0 under `+initreg+0`.** Outputs before the first clock edge are not to be trusted; every testbench holds reset for 5 cycles.
- **Q9. A random register start: `vopt +initreg=ru` and `vsim +initreg+<seed>`.** The spec selects the variable kinds, the seed is vsim's; `pwr.py run --initreg-seed N` is a check, never the default, and writes nothing to `results/`.
- **Q10. An `initial` block next to `always_ff` drives the same variable (vopt-7061).** Use declaration initializers and an internal register for the read data; check with `vsim -c`, not vlog alone.
- **Q11. `process::self().srandom()` in an `initial` block does not seed the `always` blocks' `$urandom`.** Each process has its own generator; seed with `vsim -sv_seed <seed>` (`pwr.py --seed`) and check two seeds give different SAIFs.
- **Q12. The SRAM macro models are SystemVerilog in `.v` files.** vlog reads `.v` as Verilog-2001 without `-sv`; `cluster/mem.py` writes `-sv` as the first line of `sram_models.f`.
- **Q13. vsim's prints and the program's output share the log through separate buffers.** Lines interleave at buffer boundaries; `cluster/check.py` finds each print by its start and end and each `forge` line by a search inside the line.
- **Q14. A netlist's memories take one access at time 0 under `+initreg+0`.** The I-cache's macros write once, a gated netlist's TCDM banks read once, during reset and before every window; `ram_compare` allows one more access per instance and lists it (X67 · X81 · X84).
- **Q15. A DC netlist's instance paths hold escaped identifiers that end in a space.** `%m` prints spaces inside the path; parse a path as everything up to the last whitespace before the next field, and put such paths in braces in vsim.
- **Q16. Under `vopt +acc=n` a testbench's variables are not visible to vsim's commands.** Refer to the DUT's ports in a gate-level run; `cluster gls` keeps `+acc=n`.

## vcd2saif

- **VS1. `vcd2saif -time t0 t1` on a shared VCD adds a phantom toggle before the window.** A zero-width pulse before t0 counts as a toggle in the window (idle 0.028 instead of 0 pJ per cycle); cut the VCD per window first (`vcd_windows`, X32).
- **VS2. A change to or from X is no toggle in vcd2saif's count.** The macro models start X, so the cluster's first DMA window has many X nets; a window misses at most one toggle per net leaving X, the size of VS1.

## PrimeTime

- **PT1. PT applies the library's default wire-load model, hidden.** `report_design` does not show it; `set_load 0` and `set_resistance 0` on every net, and `pwr.py` fails a run whose `wire_load.rpt` counts are not 0.
- **PT2. Default-activity propagation differs from DC's around enable logic.** The two resolve the hold mux's feedback differently (register +35 %); with the same activity on every net they agree, which is the setup check (X25).
- **PT3. A flop's clock-edge energy moves between register and clock.** It is booked under register when the output toggles, under clock when it does not; always use e_clk + e_reg (X11).
- **PT4. `read_vcd -time` takes ns; `vcd2saif -time` takes the VCD's unit.** Take the unit from the VCD's header; X9's window-length check catches a wrong one.
- **PT6. PT counts floating port nets of a constant output as not annotated.** DC leaves bit-blasted constant ports without a driver; `pwr.py` takes nets the SAIF has at Z for the whole window out of the coverage denominator and records them.
- **PT7. Averaged mode charges `when` internal power with independent pin probabilities.** A macro's read and write energy come out 12.5 % low on the probe; count accesses for a point (X50), take PT's as measured on a cluster (X75).
- **PT8. `report_switching_activity -nosplit` stops the script.** The option does not exist there (CMD-010); leave it out.
- **PT9. PT's nets are not the SAIF's entries.** The SAIF holds a port net once per level it crosses, PT once; take the annotation's denominator from PT.
- **PT10. Time-based PrimePower gives about half the clock-pin energy of held flops on the cluster's netlist.** Averaged mode agrees with the `.lib`'s count; use it for the cluster's windows (X20 · X60 · X74).

## Licences

- **L1. Transient error -92 from DC.** The server reread its file during checkout; retry once (X17). The first try may print only `DCSH-1`, with no "licens" in it.
- **L2. Feature names.** Questa takes one `msimhdlsim`; a PT power run one `PrimeTime` and one `PrimePower`; synthesis `Design-Compiler`. Count those (X16 · X59).
- **L3. `lmutil` not on PATH.** A non-interactive shell may not read `~/.bashrc`; set `LMUTIL` to the binary.
- **L4. `compile_ultra` needs a DC-Expert licence as well as Design-Compiler.** Without one DC reports an empty design (area 0); size the jobs from both counts, and `syn.py` fails a row with a licence error or an area of 0.

## CACTI

- **C1. CACTI reads `tech_params/` relative to its working directory.** Run elsewhere it segfaults with no message; `ram/ram.py` links `tech_params` into each point's folder.
- **C2. `cache.cfg`'s `-Optimize "ED^2"` overrides the design objective.** Set it to `NONE` (X47); two objectives with identical numbers are this.
- **C3. `cache.cfg` turns ECC on.** About 12 % more area and energy than a bank without ECC needs; `ram.py` turns it off (X47).
- **C4. A size CACTI rejects exits with rc 0.** Do not trust the return code; `ram.py` marks a point failed unless `cacti.out` holds every field.
- **C5. CACTI's numbers jump between neighbouring sizes.** The organization changes per size, up to 30 % steps; look up the exact size (X48).
- **C6. CACTI's cycle time is shorter than its access time.** The cycle time leaves out the H-tree delays; the `.lib` uses the access time for clk-to-`rdata_o`, the cycle time only for `min_period`.

## Environment

- **E1. `pixi run python -c "..."` loses the inner quotes.** pixi's task shell parses the quoting again; put the code in a script file (X15).
- **E2. A forge power run needs snax-forge at a commit that still loads the bundle's design point.** `forge/query.py` loads the design point with the checkout's own code; check out the bundle's `snax_forge_commit` for the run, or rebuild the bundles.
- **E3. `git diff --word-diff` on a CSV marks whole rows.** A row has no spaces; compare CSVs by key, cell by cell.
- **E4. snax-forge's relu, matadd and axpy recipes bundle int32 datapaths.** Their kernels are int32; `forge/points.json` gives them `dtypes` int64 (X57), and `sim/sources/forge.py` refuses a port that is not int64.
- **E5. snax-forge's module names carry the design's name.** `snax_forge_<design>_shell_wrapper` and the renamed lanes block make every file differ; compare with `forge/sv_diff.py`, which masks them.
- **E6. hls-exercises' CSVs have CRLF line ends, and `Path.read_text` hides them.** Edit them as bytes or with `newline=""`, and check `git diff --stat` before committing.
- **E7. A snax-forge submodule off main's pin marks every bundle dirty.** A squash merge moves the pin, not the submodule's checkout; run `git -C ../snax-forge submodule update <sub>` before bundling.

## snax_cluster's generators

- **SC1. A reader of a streamer set is named with a double underscore.** `StreamerGen --tag-name strm` gives `strm__C0_Reader`; `strm/gen.py` builds the name the same way.
- **SC2. The bundled reader is the reader as the Streamer uses it.** firtool trims the ports the parent never reads; that is the cost the model wants (X52 · X82), and `sim/sources/strm.py` connects what the netlist has.
- **SC3. `StreamerGen` always writes a CSR header.** It needs `--header-dir`; `strm/gen.py` points it into `tmp/strm/`.
- **SC4. `git archive` leaves out submodules.** chisel-float comes out empty; `strm/gen.py` archives the submodule's checkout at its gitlink's commit.
- **SC5. `sbt -batch` stops at the first failing command.** Later points of the call are reported as not run, and the next call makes them.
- **SC6. The image has no Scala caches of its own.** Every run downloaded sbt and firtool and got rate-limited; `strm/gen.py` mounts the home folder's caches under `/root`.
- **SC7. Counting `reg` declarations overstates a firtool design's registers.** Skip the simulation-only `_RANDOM*` temporaries (`strm/gen.py`'s `flop_bits`).
- **SC8. A temporal stride of 0 is the reader's repeat mode.** The testbench uses unit strides, never 0, and checks every request address.
- **SC9. A reader's loop stride is 16 bits, not the 17 its port has.** A stride of 65,536 B becomes 0; `sim/sources/strm.py` puts the larger bounds outermost and refuses a stride over 65,535 B.
- **SC10. snax_cluster's synthesis list had no iDMA.** Fixed in snax_cluster (`-t rtl` in `SYN_BENDER`); `cluster_check.tcl` and `syn.py`'s LINK-5 count fail a row with an unresolved reference.

## Zips

- **Z1. A rerun's report zip changes in git with the same numbers.** Reports carry dates, CPU times and the run's cores; compare a rerun's zip member by member with those lines aside, and commit it only with a change that is meant.
