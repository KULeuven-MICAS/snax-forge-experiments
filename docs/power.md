# Power: `sim/pwr.py`

Dynamic energy of a mapped netlist from simulated activity (X7, X13): a zero-delay Questa run of DC's netlist, its window cut into a SAIF, PrimePower on the same netlist, library and constraints; no resynthesis. First proved by hand in `results/hls/runs/2026-10-29_pwr_step0.md`; commands in [`TOOL.md`](TOOL.md#4-measure-the-energy-pwr).

## Energy quantities

A run measures one window of $T$ cycles at $t_{clk}$ = 10 ns (X2). Each energy is PT's average power of a group times $t_{clk}$: an energy per cycle of the window.

| Symbol (column) | Meaning |
|---|---|
| $T$ (`cycles`) | the window's cycles, start to done (X12, X23, X44): the energy window |
| `cycles_ports` | the port window: the first input beat accepted to the last output beat accepted, both included, the same for every source (X119); §B's cycles |
| $B$ (`beats`) | beats per input stream in the window; a beat is W elements |
| $e_{clk}, e_{reg}, e_{seq}, e_{comb}$ (`e_clk_pj` ...) | PT's clock-network, register, other sequential and combinational groups, internal + switching, per cycle (pJ) |
| $e_{flop}$ (`e_flop_pj`) | $e_{clk} + e_{reg} + e_{seq}$, as PT splits a flop's clock edge by whether its output toggles (X11) |
| $e_{dyn}$ (`e_dyn_pj`) | $e_{flop} + e_{comb}$, per cycle |
| $P_{dyn}$ (`p_dyn_uw`) | $e_{dyn} / t_{clk}$, in µW |
| $E_{run}$ (`e_run_pj`) | $e_{dyn} \cdot T$ (plus counted memory energy with SRAM macros, X62) |
| per firing (`e_comb_fire_pj`, `e_flop_fire_pj`) | $e_{comb} \cdot T / B$ and $e_{flop} \cdot T / B$, per input beat |
| $n_{bits}$ (`flop_bits`) | the point's flops, `seq_cells` in `synth_dc.csv` |
| $e_{bit}$ (`e_bit_pj`) | $e_{flop} / n_{bits}$, per flop bit per cycle |

No leakage (it stays in `synth_dc.csv`). `power_pt.csv` has one row per point, size and seed, with `point`, `top`, `tech`, `clock_ns`, `W`, `size`, `config`, `seed`, `cycles`, `cycles_ports` and `status` (`ok`, `failed: <check>`, `skipped: ...`). Added by source: forge's `counter`, `expected_cycles` and differences (X56); the RAM's `ram_kind`, `ram_reads`, `ram_writes`, `e_ram_pj` (X62); char's window (X33); `e_beat_pj`, `e_access_pj` ([`cost_tables.md`](cost_tables.md)); the cluster's `e_macro_pj`, `e_io_pj`, `e_win_pj` (X74).

## Before a run

- The DC run's zip `syn/runs/<source>/<tech>/<tier>/<kernel>/<point>.zip` with `out/<top>_mapped.v`, `tech.json`, `reports/lib_info.txt`; `pwr` unpacks them into `tmp/` (X51). `pixi install` once (X15).
- Tools: `vlib`, `vlog`, `vopt`, `vsim` on PATH; `pt_shell` (or `PT_SHELL`), `lmutil` (or `LMUTIL`, PITFALLS L3), `vcd2saif` (else next to `pt_shell`), `dc_shell` for setup-check (or `DC_SHELL`); licences from `MGLS_LICENSE_FILE`, `SNPSLMD_LICENSE_FILE`.

## Flags

`--size all` runs `rtl/<point>/sizes.txt`, one compile per point; `--seed N` the rand64 seed; `-j N` caps workers. Patterns are globs over `rtl/` as in `syn.py` (`MAX_W`). `--initreg-seed N`, a check only: `vopt +initreg=ru`, `vsim +initreg+N`, tags `<size>_s<seed>_r<N>`, nothing in `results/` (PITFALLS Q9).

## Stages

One worker per point, J workers with nproc // J PT threads each, from the free licences (X16).

| stage | what | fails the point when |
|---|---|---|
| tb.json | `sim/sources/hls.py` from the top's ports, `filelist.f`, `params.json` (X14); a `# ram:` point is `skipped` | a port not covered, `control.kind` not `ap_ctrl_hs` |
| compile | `sim/tb/*.sv`, generated `tb.sv`, netlist with `vlog -timescale 1ns/1ps`; `vopt +initreg+0 +acc=n` against cell models in `sim/runs/<tech>/_cells` | vlog or vopt errors |
| stimulus | rand64 (or forge) per X19, each input uniform over its stream's dtype (X119), reference from `sim/ref.py` (a narrow point: snax-forge's kernel, X119), `$readmemh` files | an input bit never toggles in ≥ 64 beats (fewer: counted, printed); forge: `sim/ref.py` differs from `data.h`'s `EXP_*` |
| vsim | `vsim -c`, no SDF, `+nospecify +notimingchecks`, plusargs (`sim/scripts/run.do`); every output beat compared, DUT scopes dumped from the edge raising `ap_start` to the done edge | a mismatch, X/Z on a valid output, a timeout |
| cycles | the TB's count (X12) against cosim's line a x loop_count + b, or cosim at a cosim size (X19) | a different count, no integer line |
| vcd2saif | `-instance tb/dut -time t0 t1` in the VCD's unit; VCD deleted (X8, X18) | no SAIF |
| SAIF check | T0 + T1 + TX = DURATION on every driven net (all-Z entries apart, PITFALLS DC5), every entry parsed, DURATION = cycles x 10 ns, `ap_clk` TC = 2 x cycles (X9) | any of these |
| PT | `sim/scripts/pt_power.tcl`: .db (md5 checked), netlist, `constraints.sdc`, `set_load 0` / `set_resistance 0` on every net, `read_saif`, `report_power` and `-hierarchy` | PT errors, under 99 % annotated, wire capacitance or resistance in `wire_load.rpt` (PITFALLS PT1) |
| cleanup | `work/`, `vsim.wlf` deleted always | |

The TB (`sim/tb/`): `ap_ctrl_hs_seq.sv` (10 ns clock, 5 cycles of synchronous active-low reset, `ap_start` held until `ap_ready`, `ap_vld` pulsed on the first start cycle, a timeout), `axis_src.sv` (always valid), `axis_sink.sv` (always ready, compares, X/Z check). Outputs are sampled at falling edges, so nothing races. `tb.sv` dumps the DUT and sub-design scopes, not cells (PITFALLS LIB2). A licence error reruns once (X17), first log kept as `*.licence_retry.log`.

## Narrow streams and the port window (X119)

- **Element widths.** A stream's `dtype` is its element: an input carries `params.json`'s `dtype`, an output its `acc_dtype` (else `dtype`); `lanes` = TDATA bits / the element's bits, the same in `sim/sources/hls.py`, `bambu.py` and `xls.py` (dslx-exercises' `params.json` for XLS). X118's points: inputs 8 int8 lanes in 64 bits, vecadd's and relu's outputs 8 int32 lanes in 256 bits, dot's `out` one int32. `beats_hex` packs each lane at its width, lane 0 low; `axis_sink`'s `EW` prints a mismatch lane by lane. An int64 point's `tb.json` is byte for byte as before (`results/compare/runs/2026-11-28_hcmp1_r4b.md`).
- **Stimulus and reference.** rand64 draws each input uniform over its dtype from the seed, stream by stream (int64: X19's draws exactly). A narrow point's `tb.json` has `ref`: snax-forge's kernel (`params.json`'s `forge_kernel`), its type preset (`forge_types`, `i8`) and the dtypes snax-forge resolves for it (`forge/query.py types`), each stream's dtype checked against its container's. The expected outputs are snax-forge's kernel body on the inputs at those dtypes (`forge/query.py ref`, `kernel_ref`, as forge's own check), once per kernel and inputs in a batch; `sim/ref.py` stays for the int64 points. `--stim forge` is int64 only.
- **Sizes.** A narrow point runs its `params.json` sizes (n4096) and `b64`; no `n2048`. A forge point made at a size of the kernel's hls-exercises `params.json` is tagged with it (`forge_w8_i8_n4096`: `n4096`); at the n2048 shape it stays `n2048`. `power_pt_modules.csv` keeps the modules of `n4096` runs as of `n2048` runs.
- **Expected cycles.** Bambu's and XLS's at a size of their cycle CSV are that row's (`cycles_done`; `cycles` + 1), else the line through the rows; a narrow point has one size.
- **The port window.** Each sequencer (`ap_ctrl_hs_seq`, `bambu_seq`, `xls_seq`, `csr_seq`) takes `in_hs` and `out_hs` from the generated top (valid and ready on any input, on any output stream; XLS's cfg channel is not a stream), counts rising edges from reset's release (the first edge after it is cycle 1), samples both at the falling edge before each edge, as the sinks do, and prints `TB: ports first_in <c> last_out <c>`. `cycles_ports` = last_out − first_in + 1 goes into `power_pt.csv` beside `cycles`; a run without the line fails. The energy window stays each source's (X12, X23, X44): the task as the tool runs it. `pwr run` prints both per run; `cycles_ports` ≤ `cycles` + 1 is checked in the round's run note, not failed.

## Programs and streams entries (X120)

- **forge's programs.** A point whose program is more than one accelerator task of one group (several jobs, groups or accelerators, `JOBS_<SINK>` per chain, ROWS, a forked input, a copy) gets a `tb.json` with `control.groups` (each group's busy and done pins; CSRs named `<group>.<NAME>`, `<group>.<unit>.<NAME>`), one stream per wrapper port with its `segments` (each streamer task on it in program order: job, container, order, `value` initial or final), `scalars` by job, `design_point`, `left_out` (the DMA tasks not run) and `sizes.<tag>.program`: `write`, `scalar`, `start`, `wait`, `counter` in the order the program issues them (`forge/query.py program`, checked against the bundle's `main.c`). `sim/tb/csr_prog_seq.sv` runs it: a wait holds the next op until the group's done pulses equal its starts; the window runs from the first START to the last run's end; each job's BUSY_COUNTER is printed (`TB: counter <job> <value>`) and checked against its `group_counter`, the window against the jobs' sum in program order. The stimulus draws every container a stream reads first at its dtype (seed, in stream order); snax-forge's executor on the design point (`forge/query.py run`) gives the rest, intermediates and a copy's destination included, and its outputs must equal the kernel's (`ref_check`). A copy between jobs is left out: the stream reading its destination carries the graph's values. A one-task point builds as before (its `tb.json` byte for byte).
- **HLS streams entries.** A narrow point's stream element is snax-forge's dtype of the array the port carries: its hls-exercises `params.json` `streams` entry's `array`, else its name (an output `<a>_out` carries `<a>`: axpy's `y_out`). A port with an entry gets `follows` (array, beats, index) and `tb.json` the sizes' `dims`; rand64 draws each array once, full-range, in the order the input ports first carry it, and gives a port lane l of beat b element `index` of its array (the output's from snax-forge's kernel at the point's types, M and N its symbols). Scalar pins and XLS cfg fields are drawn at their dtype (int32 at i8); XLS's cfg widths are 32 bits for loop_count and len and the scalar's dtype for alpha and beta, their sum checked against `_cfg_TDATA`.
- **Dry checks.** `pwr tbjson --clk-gate` reads the clock-gated netlist's ports; `pwr tbjson --rtl-ports` (forge, Bambu, XLS) reads the RTL top's ports instead, before synthesis.

## Forge (`--source forge`)

Bundles `rtl/forge/<point>.zip` (`forge/bundles.py`), netlists in `syn/runs/forge/<tech>/` (X6); snax-forge unchanged.

- **tb.json** (`sim/sources/forge.py`, X14): from the bundle's JSON files (one group; a program, X120: above), the streamer hjson and the netlist's ports as C§17's wrapper has them (`clk_i`, `rst_ni`, CSR, `stream2acc_<k>_*`, `acc2stream_<k>_*`, `<group>_busy_o`, `<group>_done_o`); `forge/query.py` gives containers, the kernel and `expected_cycles` (`group_counter`).
- **Control `forge_csr`:** one size, the shape it was bundled at: `n2048` (X55: tier done N = 2048; relu, axpy N = 2048, matadd M = 32, N = 64, rowsum M = 16, N = 128) or X118's `n4096` (X119). LOWER's writes (`forge/query.py program`, X58): JOBS, JOB_BEATS, scalars (`K1`, or `K1_LO`, `K1_HI` at int64; axpy's alpha), START. At W = 4: relu, matadd, axpy, axpy_baked JOBS 512; rowsum JOBS 16, JOB_BEATS 32; rowsum_2 JOBS 4, JOB_BEATS 128; dot 4 JOBS 1, JOB_BEATS 512.
- **Stream order:** the streamer's visit order, as `order` when not the identity: `rowsum_2` beat t holds rows 4⌊t/128⌋ to 4⌊t/128⌋ + 3 of column t mod 128 (M = 16, N = 128, W = 4). axpy's in-place `y` has TB streams `y_in`, `y_out`, checked against αx + y.
- **The TB** (`sim/tb/csr_seq.sv`): `rst_ni` low 5 cycles, 2 idle, each write held until `csr_req_ready_o`, START last; sources valid from the first busy cycle.
- **The window:** START accepted in cycle a, busy a + 1 .. E, `<group>_done_o` high in E + 1, so BUSY_COUNTER = E - a (C§17). Falling edge before START's edge to the one before e_E: rising edges e_a .. e_{E-1}, E - a of them, as X12 (dump margins: PITFALLS Q6). BUSY_COUNTER (D168) is read back.
- **Checks:** outputs against `sim/ref.py`, itself checked against snax-forge's `SPEC.func` (`forge/query.py ref`, X57); `counter_diff`, `expected_diff` fail past 5 % (X56). X9 on `clk_i`; 99 % of non-floating nets (Z all window, e.g. STATUS bits 2 to 31, leave the denominator: PITFALLS PT6); every module a dump scope (DC6).
- **Stimulus:** rand64 (X19), seed 0, N / W beats, at least 64. Narrow (`types=i8`, `i16`; X90): num_slc = 64 / bits a word, little-endian (D142); a packed output (`d_out` 2: vsum and dot at int32) is one word, upper slice 0 (D174).
- **Runs and results:** tag `n2048_s0/`; X20's columns plus `recipe`, `snax_forge_commit`, `counter`, `counter_diff`; `config` is the JOBS and JOB_BEATS writes.
- **Setup check:** ports from `tech.json` (`SYN_CLK_PORT`, `SYN_RST_PORT`); within 0.02 % (X25).

## Char (`--source char`)

Catalogue datapaths, `FifoPacker`, `FifoSlicer` alone (`rtl/char/`, `char/blocks.py`); no CSRs or done, so the TB drives them as the control unit would, in fixed windows.

- **tb.json** (`sim/sources/char.py`): `data_in` (`{port, bits}`, rand64's low bits), `outs` (the slicer's `out_bits` through `out_valid`), and pins with bits (none: `wslot`, `rslot` at depth 1, `lane` at lanes 1); ports as wide as their type (D175); a SimdLanes of one stream has `a` alone, of three (axpbypcz) `a`, `b` and `c`, and a scalar it reads from its CSR is an input pin (`scalars`: `io_k`, `io_k1`, `io_k2`, `io_k3` at opType's width, checked in the netlist; X99); a HaloLink's outputs are its T × W taps `io_taps_<t>_<l>`, tap-major, its one pin `load` (X116). Kinds: lanes (SimdLanes), fold (Mac, TreeAccumulate), bank (Mac of R ≥ 2 rows, D191, `row`, `drain` of ⌈log₂ R⌉ bits; X97), serial, link, halo (HaloLink), pack, slice.
- **The TB:** `sim/tb/char_<kind>_seq.sv` with `char_seq_core.svh`. Reset 5 cycles; 4 settle slots; per window a lead-in (one slot; link's stream: D slots; halo's: H slots) and 128 slots (serial's busy: 128 beats of W slots). Inputs at the rising edge, outputs sampled at the falling edge against `char_ref`. A window runs from a quarter cycle before its first slot's rising edge to a quarter cycle before the edge after its last. Prints `TB: window <name> t0_ns <t0> t1_ns <t1> cycles <c> fires <f>`. A scalar pin holds one value a window, as a CSR the program writes once: drawn after the data (which stays as without it), a full-range rand64's low bits, applied at the window's lead-in from `+K_HEX` (one line a window) and kept in `tb.json`'s `scalar_values` (X99). A threshold's k is drawn instead from a generator of its own (`default_rng([seed, 1])`), uniform over a's range above its least value (1 to 255 for uint8), so its output toggles and every lanes count holds the same k (X117).
- **The windows:** lanes, fold, serial: `busy` (a fire or read every cycle, `first` at the lead-in) and `idle` (enable 0, inputs held). bank: `busy` after R restart slots, `row` = t mod R, `drain` = t − 1 mod R; `idle` holds them. link: `stream` only, after the D-slot fill a load every cycle into slot t mod D, `out` at t the beat of t - D; no idle window (flops x idle per-flop energy). halo: `stream` only, after the H-slot fill a load every cycle, each tap the held beats and the incoming one (X116). pack: `clear`, then `busy` (a push every cycle, `out_valid` every d_out-th) and `idle`; a fire is a push. slice: `clear`, then `busy` (`enable`, `in_valid`, `out_ready` high: a pop every cycle, a take every d_in cycles) and `idle`; a fire is a pop (X94).
- **Activity:** `vcd_windows` cuts one file per window (header, values before t0, events, a bare step at t1), vcd2saif `-time t0 t1` on each (PITFALLS Q6, VS1; X18).
- **Gates:** a mismatch or X/Z; cycles and fires not schedule()'s; an output change in idle; a data bit not taking both values in busy or stream (the scalar pins hold, so they are exempt); X9 per window on `clock`; under 99 % annotated; wire load (X25, PITFALLS PT1).
- **Results:** `results/char/<tech>/char_power.csv`, a row per point and window, the per-cycle energies and `e_bit_pj` = e_flop / `seq_cells`; `pixi run python char/checks.py --power` prints the checks (e_hold, LinkBuffer against 64 e_hold, lane copies, folds over W).

## Streamer and interconnect (`--source streamer`, `--source xbar`, `--source xbar_mix`)

snax_cluster's reader and sparse interconnect, alone and in `strm/xbar_mix.py`'s wrapper; the TB drives one busy window.

- **tb.json and the TB** (`sim/sources/strm.py`): generated whole, every port connected; reset 5 edges; requests sampled at the falling edge; data from `$urandom`, `vsim -sv_seed <--seed>` (PITFALLS Q11).
- **Reader** (`d<D>_l<L>_c<C>`): `ptr` 0, spatial stride 8 B, 1,024 beats as powers of two over L loops, larger outermost (1: 1024; 2: 32 x 32; 3: 8 x 8 x 16; 4: 4 x 4 x 8 x 8; 5: 4 x 4 x 4 x 4 x 4; 6: 2 x 2 x 4 x 4 x 4 x 4; 7: 2 x 2 x 2 x 2 x 4 x 4 x 4), within the 16-bit step (PITFALLS SC9); beat n reads words n C to n C + C - 1. TCDM grants at once, answers next cycle; output always ready. Window: the edge taking `io_start` to the edge taking the last beat (fill + 1,024 + stalls). Gates: 1,024 beats, channel i in bits 64 i, addresses 8 (n C + i), no X/Z, no stall after the fill (else `failed: <n> stalls after the fill (energy kept)`).
- **Interconnect** (`i<inputs>_b<banks>`), inputs <= banks only: input i requests bank (i + t) mod banks at a random row, `write` = t odd, `strb` ff, `amo`, `priority`, `user` 0; memory always ready, `memRsps_valid` 1, `tcdmRsps_ready` 1; 1,024 cycles, window 1,025 cycles. Gates: grants = inputs x 1,024, requests routed, read data valid.
- **By input kind** (`i<inputs>_b<banks>_r<ro>_w<wo>`, X70): the wrapper's tied ports (`tie()`) undriven; inputs ro+wo .. inputs-1 read-write as above (ro = wo = 0: the same `$urandom` calls), 0 .. ro-1 read only, ro .. ro+wo-1 write only. Gates by kind; rows add `ro`, `wo`.
- **Activity and PT:** `vcd_windows` cut (X32), X9 on `clock`, >= 99 % annotated, wire load (PITFALLS PT1).
- **Results:** `power_pt.csv` per point and seed: `cycles`, `fill`, `stalls`, `beats` or `grants`, `e_window_pj` = `e_dyn_pj` x cycles, **`e_beat_pj`** = `e_window_pj` / beats or **`e_access_pj`** = `e_window_pj` / grants, `snax_cluster_commit`; `report/strm_table.py` joins them with `synth_dc.csv` (X53).

## Bambu (`--source bambu`)

hls-exercises' `rtl/<tier>/<kernel>/bambu_w<W>/` (X44).

- **tb.json** (`sim/sources/bambu.py`): streams `<arg>_TDATA/_TVALID/_TREADY` in `axis` order, lanes = TDATA bits / the element's bits (X119); pins `loop_count`, `len`, `alpha`; `clock`, `reset` from `SOURCES`; sizes as Vitis.
- **Control `bambu_ctl`:** `start_port`, `done_port`; `idle_port` connected, never read.
- **The TB** (`sim/tb/bambu_seq.sv`): pins driven from time 0 and held; `reset` (sync, active low) 5 cycles, 2 idle, sources valid a cycle before a one-cycle `start_port` pulse.
- **The window:** falling edge before the first rising edge sampling `start_port` = 1 to the one before `done_port` = 1: Bambu's `cycles_done` (PITFALLS Q6).
- **Checks:** outputs against `sim/ref.py`; cycles against the line through `cycles_done` in `bambu_cycles.csv` (dot at W = 4 and 8: a = 2); X9 on `clock`; 99 % annotated, no wire load (PITFALLS PT1), DC6. About 17 600 SAIF nets at Z on `done/dot/bambu_w8` are DC5's undriven bits.
- **Stimulus:** rand64 (X19), streams then `alpha`; X20's results.
- **Setup check** (default `done/dot/bambu_w8`): within 0.03 % in every group.

## XLS (`--source xls`)

dslx-exercises' `rtl/<tier>/<kernel>/xls_w<W>/` (`SIM_XLS`, default `../dslx-exercises`, X44).

- **tb.json** (`sim/sources/xls.py`): channels `_<arg>_TDATA/_TVALID/_TREADY` matched by position to hls-exercises' `axis` (dot's `a`, `b`, `res` are `A`, `B`, `out`); `cfg` fields; clock `clk`, reset `rst`.
- **Control `xls_cfg`:** one cfg beat, the first field high, widths `CFG_BITS` (`loop_count` 32, `len` 32, `alpha` 64) summing to `_cfg_TDATA`'s 32, 64 or 96; `alpha` a rand64 pin; passed as `+CFG=<hex>`.
- **The TB** (`sim/tb/xls_seq.sv`): Bambu's reset and idle (`rst` = `~rst_n`); the cfg beat held until `_cfg_TREADY` = 1.
- **The window:** falling edge before the cfg transfer to the falling edge after the last output transfer: `cycles` + 1, the datapath combinational.
- **Checks:** as Bambu, the line through `xls_cycles.csv`'s `cycles` (a = 1, b = 0) plus 1, X9 on `clk`.
- **Setup check** (default `done/dot/xls_w16`): within 0.005 %. XLS resets all state, so a random start gives the same energy to the last digit.

## Run folder

Vitis runs in `sim/runs/<tech>/`, others in `sim/runs/<source>/<tech>/`. A point's folder lives while its worker runs, then is packed into its zip (X51; new run tags replace old), test-read and deleted.

```
sim/runs/<tech>/_cells/                         cell models, compiled once per technology (kept)
sim/runs/<tech>/batches.jsonl                   per batch: date, patterns, licence counts, J, threads
sim/runs/<tech>/<tier>/<kernel>/<point>.zip     tb.json; per run tag busy.saif and pt/*.rpt (char: s<seed>/<window>/)
sim/runs/<tech>/setup_check/<point>.zip         check.json, pt/reports/*.rpt, dc/reports/*.rpt
```

The rest of the folder (`tb.sv`, `logs/`, `stim/`, `vsim.log`, `vcd2saif.log`, `not_annotated.rpt`) is scratch; git ignores `sim/runs/`.

## What is committed

In `results/<source>/<tech>/` (X20; Vitis in `results/hls/`):

- `power_pt.csv`: a row per point, size and seed;
- `power_pt_modules.csv`: `point, tech, size, path, design, e_dyn_pj`, per hierarchical cell of the default run and each `n2048` and `n4096` seed-0 run (X60, X119);
- `power_reports/<tier>/<kernel>/<point>.zip` (X51): `power.rpt`, `power_hierarchy.rpt`, `switching_activity.rpt`, `tb.json`; other runs in `<size>_<seed>/`; deterministic (PITFALLS Z1).

Tool versions, licence counts and setup-check differences go into the run note.

**A point with a RAM (X62).** A dace point with a swapped macro (`resolved.ram` in `tech.json`) is simulated with the macro's `.v` (`+define+SRAM_INIT_ZERO`), its `.db` linked (`PWR_RAM_DBS`); each instance prints `RAMCOUNT <inst> <cell> reads <n> writes <n>`. The macros are PT's `black_box` group, replaced by `e_ram_pj` = reads x e_rd + writes x e_wr (X50), their output nets added to comb; `e_run_pj` = e_dyn x cycles + `e_ram_pj`; PT's figure is kept as `e_ram_pt_pj` (PITFALLS PT7). A flop RAM (`--with-ram`) is ordinary logic. Dace dot, axpy, rowsum run n2048 only; rowsum's n2048 is m16_n128.

**n2048 (X24, X55).** Every int64 `tb.json` has `n2048` (a narrow point has none, X119) after cosim's sizes and `b64` (`EXTRA_SIZES`): tier done N = 2048, relu and axpy n = 2048, matadd m32_n64, rowsum m16_n128 (W = 4: loop_count 512, len 32). Pins at n = 2048 (vecadd, vecmul `loop_count` = 2048 / W; vsum, dot `loop_count` = `len` = 2048 / W), cycles from cosim's line through n64 and n512 (X19). Not the default (`b64`); its reports in `n2048_s0/`, its modules beside the default's (X60).

`setup-check` (X25) runs PT and DC on one netlist with the same uniform activity and prints each group's difference (`check.json`); it fails only on wire load (PITFALLS PT1). Run it when the flow or a library changes.

## Notes

- The SAIF has an entry per net name per scope, PT counts the design's nets, so coverage is PT's count only.
- `vcd2saif` on PATH is DC's (Y-2026.03-SP2); step 0 used PT's (W-2024.09-SP4-1); both gave vecadd `opt_w8` 11.4086 against 11.40865 pJ.
