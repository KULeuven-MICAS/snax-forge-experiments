# Pitfalls

Tool behaviour that gives wrong numbers, or none, without an error: one line each, by tool, with the fix and its decision. IDs are never reused; retired: LIB1, LIB3, LIB4, PT5 (the 15 nm library, X88).

## DC

- **DC1.** `auto_wire_load_selection false` keeps nangate45's `default_wire_load 5K_hvratio_1_1` (critical path 22 % longer): `dc_syn.tcl` removes it, `syn.py` fails an `area.rpt` naming a model (X3).
- **DC2.** SDC is read in the library's units, 1000x off in others: ns and fF scaled by `T_SCALE`, `C_SCALE`; stop on a unit mismatch (X4).
- **DC3.** Other names or order move area up to 0.02 %: noise; compare equal-Verilog pairs.
- **DC4.** Default toggle rate 0.1 follows structure, not work (vecmul dace 100 pJ against opt 13.5 pJ a cycle): simulate (X7).
- **DC5.** Vector wires keep undriven bits at Z: `saif_check` parses TZ, counts all-Z apart.
- **DC6.** Some module headers are indented: match `^\s*module`; X9's 99 % catches a miss.
- **DC7.** Y-2026.03-SP2 crashes (Error id=834758) on a 1-bit-select mux in an adder under a branch on that bit: snax-forge writes `Mux(first && lane === 0, 0, acc) + x`.
- **DC8.** Bambu's declaration initializers are dropped (VER-708): `vopt +initreg+0` (Q1).
- **DC9.** DC removes unloaded Bambu registers (OPT-1207, 96 bits on `done/dot/bambu_w8`): compare `seq_cells` with RTL bits minus unique OPT-1207 lines.
- **DC10.** Vitis flops are trimmed with no OPT-1207: sum `Inferred memory devices` minus unique OPT-1206, OPT-1207 lines (Bambu: DC9).
- **DC11.** A one-point rerun adds empty path-class columns (X40) to old rows: compare CSVs cell by cell.
- **DC12.** An SRAM macro's power is outside the four groups: out of the sum check, counted (X50, X62); a non-macro black box fails.
- **DC13.** On a loaded host DC keeps fewer cores (UIO-231): `SYN_IGNORE_LOAD=1` (X68); check OPT-1500.
- **DC14.** A stopped DC leaves its multicore child holding logs (NFS `.nfs` stubs): stop every `common_shell_exec`, wait.
- **DC15.** `**logic_0**`, `**logic_1**` look like black boxes: `cluster_check.tcl` lists them as constants.
- **DC16.** `sparse_interconnect_wrapper` holds 193 µm² beside `sparse_interconnect_i`: say which level.
- **DC17.** `syn.py run --dry-run -j N` interleaves lines: compare at `-j 1`.
- **DC18.** An unloaded output port has no driver and reads Z: take status from the RTL run.
- **DC19.** `syn/runs/<source>/<tech>/summary.csv` is never pruned: `syn.py` merges a batch into `synth_dc.csv` (X79 · X87 · X88).
- **DC20.** A large inferred mux maps to MUX2 trees (16 × 256: 7,680 MUX2, 14,300 µm², comb x2, energy x3), smaller ones (up to 16 × 128, 8 × 256) to AOI22: check `reference.rpt`'s MUX2 count before fitting (X97).

## Libraries

- **LIB2.** Neither cell model file uses `` `celldefine ``, so `-nocellnet` does nothing: `power add <dut>/*` without `-r` on flat netlists (Q3).
- **LIB5.** nangate45's `.lib` puts a group and its first attribute on one line: split at `{`, `}`, `;` outside quotes (`ram/pins.py`, `statements`).
- **LIB6.** lc_shell on a generated macro: nangate45's `default_*` and a `char_config` group clear the LBDB lines; two black-box functionality warnings stay (X49).
- **LIB7.** lc_shell Y-2026.03 `write_lib -format lib` writes nothing (UIL-23): compare with `report_lib`, check outputs exist.

## Questa

- **Q1.** Vitis's unreset registers start in `initial` blocks the netlist lacks: `vopt +initreg+0`, X check, timeout.
- **Q2.** Without `+acc=n` `power add` finds no nets; it costs nothing measurable.
- **Q3.** `power add -r` adds cell-internal nets (LIB2): `-r` only with sub-designs.
- **Q4.** `power report -bsaif` (2022.4) is 13 to 34 % low at zero delay: VCD and vcd2saif (X8, X9).
- **Q5.** A VCD grows with nets x cycles: dump the window, delete after vcd2saif (X18).
- **Q6.** `$dumpon` at a boundary loses its clock edge: dump from the edge before to the one after; X9 catches it.
- **Q7.** `logic clk = 0` fires `@(negedge clk)` at time 0, and TVALID can be high in reset: count beats after reset (`axis_sink.sv`).
- **Q8.** nangate45's flops start with Q and QN both 0 under `+initreg+0`: hold reset 5 cycles.
- **Q9.** Random start: `vopt +initreg=ru`, `vsim +initreg+<seed>`; `--initreg-seed N` is a check, writes no `results/`.
- **Q10.** An `initial` block beside `always_ff` on one variable (vopt-7061): declaration initializers; check with `vsim -c`.
- **Q11.** `process::self().srandom()` does not seed other processes' `$urandom`: `vsim -sv_seed <seed>`; check two seeds differ.
- **Q12.** The macro models are SystemVerilog in `.v`, read as Verilog-2001 without `-sv`: `sram_models.f` starts with `-sv`.
- **Q13.** vsim's and the program's prints interleave: `cluster/check.py` finds prints by start and end.
- **Q14.** Netlist memories take one access at time 0 (I-cache writes, gated TCDM reads): `ram_compare` allows one per instance (X67 · X81 · X84).
- **Q15.** Escaped identifiers end in a space inside `%m` paths: parse to the last whitespace, brace them in vsim.
- **Q16.** Under `+acc=n` TB variables are invisible to vsim commands: use DUT ports.
- **Q17.** `char_seq_core.svh` is `include`d in each char sequencer's body, so its names (`k` the sample count, `bi`, `beats`, `exps`, `sample`) are the sequencer's: a port of the same name fails vlog (vlog-2388) and every point of the kind fails `vlog_tb` in half a second; the lanes sequencer's scalar port is `scal`.

## vcd2saif

- **VS1.** `-time t0 t1` on a shared VCD counts a zero-width pulse before t0 (idle 0.028 instead of 0 pJ a cycle): cut per window (X32).
- **VS2.** A change to or from X is no toggle: at most one missed toggle per net leaving X, VS1's size.

## PrimeTime

- **PT1.** PT applies a hidden default wire load: `set_load 0`, `set_resistance 0`; `pwr.py` fails nonzero `wire_load.rpt` counts.
- **PT2.** Default-activity propagation differs from DC's around enable logic (register +35 %): equal forced activity agrees (X25).
- **PT3.** A clock edge is booked under register or clock by output toggle: use e_clk + e_reg (X11).
- **PT4.** `read_vcd -time` is ns, `vcd2saif -time` the VCD's unit: read the header; X9 catches it.
- **PT6.** Floating constant-port nets count as not annotated: nets at Z all window leave the denominator.
- **PT7.** Averaged mode charges `when` power with independent pin probabilities, macros 12.5 % low: count (X50) or take as measured (X75).
- **PT8.** `report_switching_activity -nosplit` stops the script (CMD-010): leave it out.
- **PT9.** The SAIF holds a port net per level, PT once: denominator from PT.
- **PT10.** Time-based mode gives about half the clock-pin energy of held flops: averaged (X20 · X60 · X74). On `mvt_column_cg` (COST3 R3) clock network internal 0.58 and register internal 0.43 of averaged, switching and combinational equal; the logic 0.75 in all, the macros 1.21 (PT7 gone).
- **PT12.** A time-based hierarchy row is Int, Switch, Leak, Peak Power, Peak Time (`t0-t1`), Glitch, X-tran, Total, %: the averaged parsers take peak power as the total; `power.hier_top` reads the eighth number.
- **PT11.** Equal macro energy in every bank (2 048 cycles of `req_i`, 1 024 of `we_i`; 32 equal to seven digits) is not a floor: count `req_i`, `we_i` in the SAIF (X96).

## Licences

- **L1.** DC's error -92 is transient (maybe only `DCSH-1`): retry once (X17).
- **L2.** Questa takes one `msimhdlsim`; PT power one `PrimeTime` and one `PrimePower`; synthesis `Design-Compiler` (X16 · X59).
- **L3.** `lmutil` off a non-interactive PATH: set `LMUTIL`.
- **L4.** `compile_ultra` also needs DC-Expert, else area 0: size from both; `syn.py` fails area 0.

## CACTI

- **C1.** CACTI reads `tech_params/` from its cwd, else segfaults silently: `ram.py` links it per point.
- **C2.** `-Optimize "ED^2"` overrides the objective: set `NONE` (X47).
- **C3.** `cache.cfg` turns ECC on (about 12 % more): off (X47).
- **C4.** A rejected size exits rc 0: fail unless `cacti.out` has every field.
- **C5.** Numbers jump up to 30 % between sizes: exact lookup (X48).
- **C6.** Cycle time omits H-tree delays: access time for clk-to-`rdata_o`, cycle time only for `min_period`.

## Environment

- **E1.** `pixi run python -c "..."` loses inner quotes: use a script (X15).
- **E2.** `forge/query.py` loads a bundle's design point with the checkout's code: check out its `snax_forge_commit` or rebundle.
- **E3.** `git diff --word-diff` marks whole CSV rows: compare by key.
- **E4.** relu, matadd, axpy bundle int32: `dtypes` int64 (X57); `forge.py` refuses non-int64 ports.
- **E5.** Module names carry the design's name: compare with `forge/sv_diff.py`.
- **E6.** hls-exercises' CSVs are CRLF, hidden by `Path.read_text`: bytes or `newline=""`; check `git diff --stat`.
- **E7.** A submodule off main's pin dirties every bundle: `git -C ../snax-forge submodule update <sub>` first.
- **E8.** `forge/query.py ref` runs the checkout's kernel body, so a branch changing one (PACK1a's `OP_TYPE = int32`) fails it: forge power on main, record branch and HEAD (CG5 R1); since CHAR2 R7 axpy and matadd carry `OP_TYPE` int64, older bundles do not.
- **E9.** `syn.py`, `pwr.py` write CRLF while forge's CSVs are LF since the CG5 merge: `sed -i 's/\r$//'` and check `git diff --stat` (CHAR2 R7); other sources stay CRLF.

## snax_cluster's generators

- **SC1.** `StreamerGen --tag-name strm` names `strm__C0_Reader`: `strm/gen.py` matches it.
- **SC2.** firtool trims ports the parent never reads, the cost wanted (X52 · X82): `strm.py` connects what the netlist has.
- **SC3.** `StreamerGen` needs `--header-dir`: into `tmp/strm/`.
- **SC4.** `git archive` leaves chisel-float empty: archive the submodule at its gitlink.
- **SC5.** `sbt -batch` stops at the first failure: the next call makes the rest.
- **SC6.** The image's Scala caches are empty (rate limits): mount the home caches under `/root`.
- **SC7.** `reg` counts include `_RANDOM*`: skip them (`flop_bits`).
- **SC8.** A temporal stride of 0 is repeat mode: unit strides, addresses checked.
- **SC9.** The loop stride is 16 bits, not 17 (65,536 B becomes 0): larger bounds outermost, refuse over 65,535 B.
- **SC10.** The synthesis list lacked iDMA: `-t rtl` in `SYN_BENDER`; LINK-5 fails unresolved references.

## Zips

- **Z1.** Report zips change with dates, CPU times and cores: compare member by member, commit only meant changes.
- **Z2.** On NFS a folder a process still holds cannot go (`.nfs` stubs), and `arc.workdir` ignores delete errors: `ram table -j 32` left 35 empty `tmp/cacti_*` folders. Run `pixi run arc check` after a batch and remove what it lists.
