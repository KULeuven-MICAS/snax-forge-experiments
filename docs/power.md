# Power: `sim/pwr.py`

Dynamic energy per cycle and per firing of a mapped netlist, from simulated activity (docs X7, X13). For each point: a functional, zero-delay Questa simulation of the netlist DC wrote into `syn/runs/hls/<tech>/`, its busy window cut into a SAIF, and PrimePower on the same netlist with the same library, constraints and wire-load setting as DC. No resynthesis. The flow was proved by hand in step 0 (`results/hls/runs/2026-10-29_pwr_step0.md`, `sim/probe/`, unchanged) and first run in `2026-10-29_pwr_r1.md`.

## Before a run

- The point's synthesis run exists: `syn/runs/<source>/<tech>/<tier>/<kernel>/<point>.zip` with `out/<top>_mapped.v`, `tech.json` and `reports/lib_info.txt` (`pixi run syn run ... --source <source>`); `pwr` unpacks those three into `tmp/` for the point (X51) and PT reads them there.
- `pixi install` once (docs X15).
- Tools: `vlib`, `vlog`, `vopt`, `vsim` from PATH; `pt_shell` from PATH or `PT_SHELL`; `lmutil` from PATH or `LMUTIL` (a non-interactive shell may not have it on PATH, PITFALLS L3); `vcd2saif` from PATH, else next to `pt_shell`; `dc_shell` (setup-check only) from `DC_SHELL` or PATH. Licence servers from `MGLS_LICENSE_FILE` and `SNPSLMD_LICENSE_FILE`.

## Commands

```bash
pixi run pwr tbjson done/vecadd/opt_w8                                   # print the point's tb.json
pixi run pwr setup-check --tech nangate45                                # diagnostic: PT against DC, forced activity (X10, X25)
pixi run pwr setup-check --tech nangate15                                # prints each group's difference for the run note
pixi run pwr run 'done/vecadd/*' --tech nangate45                        # rand64, 64 beats, seed 0
pixi run pwr run 'done/vecadd/*_w8' --tech nangate45 --size n512         # at a cosim size
pixi run pwr run 'done/*/*_w*' --tech nangate45 --size n2048             # SYN1: one task of N = 2048 (tier done)
pixi run pwr run done/vecadd/opt_w8 --tech nangate45 --stim forge --size n512   # data.h, validation only
pixi run pwr run 'done/*/*' 'untiered/*/*' --tech nangate45 --size all   # whole tasks: every size in sizes.txt
pixi run pwr summary 'done/vecadd/*' --tech nangate45                    # print power_pt.csv
pixi run pwr tbjson done/dot/forge5_w4 --source forge                    # a forge point's tb.json
pixi run pwr run 'done/*/forge*' --source forge --tech nangate45 --size n2048
pixi run pwr setup-check --source forge --tech nangate45                 # on done/vecadd/forge_w4
pixi run pwr run done/dot/bambu_w8 --source bambu --tech nangate45       # Bambu (b64; --size all, --size n2048)
pixi run pwr run done/dot/xls_w16 --source xls --tech nangate45          # XLS
pixi run pwr setup-check --source bambu --tech nangate45                 # on done/dot/bambu_w8 (xls: done/dot/xls_w16)
pixi run pwr run done/dot/bambu_w8 --source bambu --tech nangate45 --initreg-seed 1   # check: random register start
```

`--size all` runs every size in the point's `rtl/<point>/sizes.txt` (the task sizes), one compile per point; `--seed N` changes the rand64 seed; `-j N` caps the workers below what the licences allow. Patterns are shell globs over the source's `rtl/` folders, as in `syn.py` (its case filters and `MAX_W`). `--initreg-seed N` is a check, never the default: it replaces vopt's `+initreg+0` with Questa's random register start (`vopt +initreg=ru`: 4-state variables, nangate45's behavioral flops, and sequential UDPs, nangate15's; `vsim +initreg+N`), tags the runs `<size>_s<seed>_r<N>` and writes nothing to `results/` (PITFALLS Q9).

## Stages

One worker per point; J workers at once and nproc // J PT threads each, from the free licences at the start (X16).

| stage | what | fails the point when |
|---|---|---|
| tb.json | `sim/sources/hls.py` from the top's Verilog ports, `filelist.f` and `params.json` (X14); a `# ram:` point is `skipped` | a port is not covered, or `control.kind` is not `ap_ctrl_hs` |
| compile | `sim/tb/*.sv` and the generated `tb.sv`; the netlist with `vlog -timescale 1ns/1ps`; `vopt +initreg+0 +acc=n` against the cell models compiled once per technology into `sim/runs/<tech>/_cells` | vlog or vopt errors |
| stimulus | rand64 (or forge) per X19, the reference from `sim/ref.py`, `$readmemh` files | an input stream bit never toggles in a run of 64 beats or more (fewer: counted in the run's info, printed); forge: `sim/ref.py` differs from `data.h`'s `EXP_*` |
| vsim | `vsim -c` with no SDF, `+nospecify +notimingchecks`, data and sizes by plusargs (`sim/scripts/run.do`); the TB compares every output beat and dumps the DUT's scopes from the edge raising `ap_start` to the done edge | a mismatch, X/Z on a valid output, a timeout |
| cycles | the TB's count (X12) against cosim's line a x loop_count + b, or cosim exactly at a cosim size (X19) | a different count, or no integer line |
| vcd2saif | `-instance tb/dut -time t0 t1` in the VCD's unit; the VCD is deleted at once (X8, X18) | no SAIF |
| SAIF check | T0 + T1 + TX = DURATION on every driven net (all-Z entries are undriven wire bits, counted apart: PITFALLS DC5), every entry parsed, DURATION = cycles x 10 ns, `ap_clk` TC = 2 x cycles (X9) | any of these |
| PT | `sim/scripts/pt_power.tcl`: tech.json's .db (md5 checked), netlist, `constraints.sdc`, `set_load 0` / `set_resistance 0` on every net (PITFALLS PT1), `read_saif`, `report_power` and `-hierarchy` | PT errors, under 99 % of nets annotated, or a net with wire capacitance or resistance in `wire_load.rpt` (PITFALLS PT1) |
| cleanup | `work/` and `vsim.wlf` deleted, whatever happened | |

The TB (`sim/tb/`): `ap_ctrl_hs_seq.sv` (10 ns clock, 5 cycles of synchronous active-low reset, `ap_start` held until an edge samples `ap_ready`, the pins' `ap_vld` pulsed on the first start cycle, the window, a timeout), `axis_src.sv` (always valid, holds each beat until its handshake) and `axis_sink.sv` (always ready, compares each beat, X/Z check). DUT outputs are sampled at falling edges, where nothing toggles, so the TB never races with the cell models' flops. `tb.sv`, generated per point, wires `tb.json`'s ports and holds `$dumpvars` on the DUT and each sub-design scope found in the netlist (not the cells': PITFALLS LIB2).

A tool that fails on a licence error is run once more (X17); its first log is kept as `*.licence_retry.log`.

## Forge (`--source forge`)

snax-forge's accelerators (SYN1): the bundles in `rtl/forge/<point>.zip` (`forge/bundles.py`), unpacked into `tmp/` for the point (`forge/query.py` reads the folder), the netlists DC wrote in `syn/runs/forge/<tech>/` (`syn.py --source forge`, X6). snax-forge is not changed. The default stays `--source hls`, and the HLS path is as above.

- **tb.json** (`sim/sources/forge.py`, X14): from the bundle's `point.json` (recipe, W, `snax_forge_commit`), `bundle.json` (the top), `accelerator.json` (its one group's CSRs by offset, its outer ports in order with lanes and dtype; a point with more than one group is refused, dot 1 is not in SYN1), the streamer hjson (each mover's `num_channel`) and the netlist's port list, every port covered as C§17's wrapper has them (`clk_i`, `rst_ni`, the CSR port, `stream2acc_<k>_*`, `acc2stream_<k>_*`, `<group>_busy_o`, `<group>_done_o`). The rest comes from snax-forge's own code, through `forge/query.py` run in snax-forge's pixi environment with `forge/bundles.py`'s cleaned environment: each port's container (the design point's graph, as its `gen/rtl.py` finds it), the recipe's kernel, and `expected_cycles`, the group's busy cycles from `gen/rtl.py`'s `group_counter` (snax-gvsoc's group rule, every input valid and the output ready) with JOBS and the units' T as the program writes them.
- **Control `forge_csr`:** the CSR port's names, the group's `busy` and `done` pins and its CSR offsets. One size, `n2048` (N = 2048 for every SYN1 comparison): an elementwise group writes JOBS = N / W, a group with a fold (a unit with JOB_BEATS) JOBS = 1 and JOB_BEATS = N / W, then START. No other read-write CSR is accepted.
- **The TB** (`sim/tb/csr_seq.sv`, with `axis_src` and `axis_sink` as for HLS): `rst_ni` low for 5 cycles and released at a falling edge (asynchronous reset), 2 idle cycles, then each write offered from a rising edge until a falling edge samples `csr_req_ready_o` (`csr_rsp_ready_i` always 1; a write has no response), START last; `go` rises with the START write, so the sources are valid from the first busy cycle, and the sinks are always ready.
- **The window:** START is accepted in cycle a, the group is busy in a + 1 .. E and `<group>_done_o` is high in E + 1, so COUNTER = E - a (C§17). The window opens at the falling edge before the edge that accepts START and closes at the falling edge before e_E, one cycle before the first falling edge that samples done = 1: its rising edges are e_a .. e_{E-1}, E - a of them, as X12 counts an HLS run. Dumping runs from the edge that offers START to the edge after done is seen (PITFALLS Q6). After the run the TB reads COUNTER over the CSR port and prints it beside the window's cycles.
- **Checks:** every output beat against `sim/ref.py` (vecadd, vecmul, vsum, dot); the window's cycles = COUNTER read back = `expected_cycles`, any mismatch fails the point; once per kernel, size and seed in a batch, `sim/ref.py` against snax-forge's kernel body (`kernels/<...>/<kernel>.py`, its `SPEC.func`, run by `forge/query.py ref` on the same inputs; the inputs depend on N and the seed only). The SAIF check is X9's with `clk_i`; PT must annotate 99 % of the nets that are not floating: a net PT leaves at default that the SAIF has at Z for the whole window has no driver (STATUS bits 2 to 31, PITFALLS PT6) and leaves the denominator. Every module of the netlist must get a dump scope (PITFALLS DC6).
- **Stimulus:** rand64 only (X19): N full-range int64 per input stream, seed 0, stream by stream in tb.json order; N / W beats, at least 64 at every W, so the toggle check applies.
- **Runs and results:** `sim/runs/forge/<tech>/<point>.zip`, run tag `n2048_s0/` (the cell models stay in `sim/runs/<tech>/_cells/`); `results/forge/<tech>/power_pt.csv`, `power_pt_modules.csv` and `power_reports/`, with X20's columns plus `recipe` and `snax_forge_commit`. `config` is the CSR writes before START, `beats` the beats per input stream, and per firing is per input beat.
- **Setup check:** `pt_power.tcl` and `dc_readback.tcl` take the clock and reset ports from the run's `tech.json` (`dc_env`'s `SYN_CLK_PORT`, `SYN_RST_PORT`), else `ap_clk` and `ap_rst_n`, since `constraints.sdc` names them (SYN1 R0). On nangate15 the forge points' register group is below DC's: -0.55 % (`done/vecadd/forge_w4`), -1.08 % (`done/dot/forge5_w4`), -0.25 % (`done/vsum/forge_w8`), against -0.08 % on the HLS point and within 0.02 % on nangate45 (PITFALLS PT5); the check is a diagnostic (X25).

## Char (`--source char`)

CHAR1's blocks alone: snax-forge's catalogue datapaths in `rtl/char/<point>.zip` (`char/blocks.py`, R0) and their netlists in `syn/runs/char/<tech>/` (`syn.py --source char`). A block has no CSRs, no START and no done, so the TB drives its data and pins as its group's control unit would, through fixed windows, and the energy per cycle of each window is measured apart. First run in CHAR1 R1 (`results/char/runs/2026-11-03_char1_r1.md`, six points, R1's windows); R2 has the windows below and runs all 27 points on both technologies.

- **tb.json** (`sim/sources/char.py`): from `point.json`, `emitted.json` and the netlist's ports, every port covered: `clock`, `reset`, the 64-bit data inputs one per lane (`data_in`, in the catalogue's port order then lane order: rand64 draws one stream per port in this order), the 64-bit outputs (`outs`), and the kind's pins that have bits (a pin of no bits is absent: LinkBuffer's `wslot` and `rslot` at depth 1, SerialAccumulate's `lane` at lanes 1; ElementwiseLanes keeps an unused `clock` and `reset`). The kind comes from the datapath: lanes (ElementwiseLanes), fold (the accumulating Mac, TreeAccumulate), serial (SerialAccumulate), link (LinkBuffer).
- **The TB**: `sim/tb/char_<kind>_seq.sv` with the shared `char_seq_core.svh` (compiled with `+incdir+sim/tb`) and the generated `tb.sv`. Reset asynchronous, active high, 5 cycles, released at a falling edge; 4 settle slots with every input low; then per window a lead-in of the window's own kind (one slot; link's stream: D slots, the fill) and the window's 128 slots (serial's busy is 128 beats of W slots). A slot's inputs are applied at its rising edge, after the flops take the slot before (as SYN1 and SYN2's TBs and a block's neighbours inside an accelerator change them), its outputs are sampled at its falling edge and compared with `sim/ref.py`'s `char_ref`, and the next rising edge takes it. A window runs from a quarter cycle before its first slot's rising edge to a quarter cycle before the rising edge after its last slot: its own input changes, captures of its own kind only (the lead-in's and its own but the last, which falls on the next lead-in's edge), and no event at either end. The TB prints `TB: window <name> t0_ns <t0> t1_ns <t1> cycles <c> fires <f>` and `TB: changes <name> <n>` per window.
- **The windows** per kind (R2): lanes, fold and serial have `busy` (new data, `fire` or `read` every cycle; a fold's lead-in is the restart, `first`; serial's `first` at lane 0 of the first beat) and `idle` (the enable at 0, every other input held, `first` included); link has `stream` only, a FIFO at full rate: after the D-slot fill, a load of new data every cycle into slot t mod D with `rslot` the oldest slot, the same one (read before the edge that overwrites it), so `out` at cycle t is the beat loaded at t - D (checked against the reference). A link that is not loading costs about its flops times the idle per-flop energy the other blocks measure, so it has no idle window. R1's `busy_t1` (within 5 % of busy) and `duty50` are gone from the schedules; R1's run note keeps duty50's finding, that an isolated fire costs 25 to 30 % more than a back-to-back one for the accumulators.
- **Activity**: dumping runs from the first lead-in's rising edge to the rising edge after the last window (PITFALLS Q6). The VCD is cut into one file per window (`vcd_windows`: the header, every variable's value at the last time step before t0, the window's events, a bare time step at t1), and vcd2saif `-time t0 t1` runs on each cut: on the shared VCD vcd2saif counts one toggle in the window for a net whose last change before t0 was a zero-width pulse, which the zero-delay simulation makes (PITFALLS VS1). The VCD and the cuts are deleted at once (X18).
- **Gates** (any fails the point, or the window): an output mismatch or X/Z at any sample; the windows' cycles and fires not schedule()'s; an output change in idle; a data input bit that never takes both values in busy or stream; X9's SAIF check per window with the clock `clock`; under 99 % of the nets annotated; a net with wire capacitance or resistance (X25, PITFALLS PT1).
- **Results**: `results/char/<tech>/char_power.csv`, one row per point and window (`point`, `datapath`, `lanes`, `depth`, `op`, `form`, `tech`, `clock_ns`, `window`, `cycles`, `fires`, `seed`, `e_clk_pj`, `e_reg_pj`, `e_seq_pj`, `e_comb_pj`, `e_flop_pj`, `e_dyn_pj`, `e_bit_pj` = e_flop / `char_synth.csv`'s `seq_cells`, `status`, `snax_forge_commit`), every energy per cycle of its window; `power_reports/<point>/<window>/` (`power.rpt`, `switching_activity.rpt`) and the point's `tb.json` in `power_reports/<point>/`. Runs in `sim/runs/char/<tech>/<point>/s<seed>/<window>/` (the SAIF, `pt/`, `result.json`). `pixi run python char/checks.py --power` prints R2's checks (the registered blocks' idle e_bit and its mean e_hold, LinkBuffer's depth sweep against 64 e_hold, lane copies, the folds against W, alone against inside SYN2).

```bash
pixi run pwr tbjson tree/add_w8 --source char                                   # a block's tb.json
pixi run pwr run 'tree/*' 'mac/*' --source char --tech nangate45 -j 6           # the blocks' windows
pixi run python char/checks.py --power --tech nangate45
```

## Streamer and interconnect (`--source streamer`, `--source xbar`)

STRM1 (X52): snax_cluster's streamer reader alone and its TCDM sparse interconnect, from `rtl/streamer/`, `rtl/xbar/` (`strm/gen.py`) and their netlists in `syn/runs/<source>/<tech>/` (`syn.py --source streamer|xbar`). Neither has a done, so the TB drives the work itself and measures one busy window. First run in STRM1 R0 (`results/strm/runs/2026-11-06_strm1_r0.md`, the probe), the whole grid in R1.

- **tb.json and the TB** (`sim/sources/strm.py`): the TB is generated whole per point (the port names carry the channel and bank index), no fixed file of `sim/tb/`; `tb.json` holds the params, the stimulus's numbers and the netlist's ports, and every netlist port must be connected and every connected port on the netlist. Reset active high (the reader's asynchronous, the interconnect's synchronous), 5 edges, released at a falling edge. Requests and outputs are sampled at the falling edge, the TB's models answer at the rising edge (nonblocking). Data from `$urandom`, seeded by `vsim -sv_seed <--seed>` (PITFALLS Q11).
- **Reader** (`d<D>_l<L>_c<C>`): `ptr` 0, spatial stride 8 B, bounds 1,024 beats split as powers of two over the L loops, loop 0 first and the larger ones outermost (1: 1024; 2: 32 x 32; 3: 8 x 8 x 16; 4: 4 x 4 x 8 x 8; 5: 4 x 4 x 4 x 4 x 4; 6: 2 x 2 x 4 x 4 x 4 x 4; 7: 2 x 2 x 2 x 2 x 4 x 4 x 4), so every stride stays within the counter's 16-bit step (PITFALLS SC9), unit strides (loop 0 steps 8 C bytes, loop k over loop k-1's range: beat n reads words n C to n C + C - 1), `io_start` for one cycle. The TCDM grants every request at once (ready 1) and answers it the next cycle with a new random 64-bit word; the output is always ready. Window: from a quarter cycle before the edge that takes `io_start` to a quarter cycle before the edge that takes the last beat (its cycles = the fill + 1,024 + any stall). Gates: 1,024 beats; every beat = the responses in order per channel (channel i in bits 64 i); every request address 8 (n C + i); no X/Z; no stall after the fill (a stall still runs PT, and the row is `failed: <n> stalls after the fill (energy kept)`).
- **Interconnect** (`i<inputs>_b<banks>`), only where inputs <= banks (the others have no conflict-free stimulus and are left out with a message): cycle t, input i requests bank (i + t) mod banks at a random row, `write` = t odd for every input (reads and writes alternate), random write data, `strb` ff, `amo`, `priority` and `user` 0; the memory side always ready, `memRsps_valid` 1 (as `sparse_interconnect_wrapper` ties it), a read bank's data a new random word at the next edge; `tcdmRsps_ready` 1; 1,024 cycles. Window: from a quarter cycle before the edge applying cycle 0 to a quarter cycle before the edge after cycle 1,024 (its read responses): 1,025 cycles. Gates: every input granted every cycle (grants = inputs x 1,024), each bank's request (row, write, data, strb) its input's, no bank valid without an input, each read response valid with its bank's data, no X/Z.
- **Activity and PT**: the TB dumps the DUT's nets and its sub-designs' from time 0; `vcd_windows` cuts the window and vcd2saif runs on the cut (X32), both VCDs deleted at once (X18); X9's SAIF check with the clock `clock`; PT with `pt_power.tcl` unchanged; >= 99 % of the nets annotated; the wire-load check (PITFALLS PT1).
- **Results**: `results/<source>/<tech>/power_pt.csv`, one row per point and seed: the params, `cycles`, the reader's `bounds`, `fill`, `stalls`, `beats` or the interconnect's `grants`, the energies per cycle (`e_clk_pj`, `e_reg_pj`, `e_seq_pj`, `e_comb_pj`, `e_flop_pj`, `e_dyn_pj`), `e_window_pj` = `e_dyn_pj` x cycles, **`e_beat_pj`** = `e_window_pj` / beats or **`e_access_pj`** = `e_window_pj` / grants, `p_dyn_uw`, `annotated`, `status`, `snax_cluster_commit`; `power_reports/<point>.zip` (`power.rpt`, `power_hierarchy.rpt`, `switching_activity.rpt`, `tb.json`). Runs in `sim/runs/<source>/<tech>/<point>.zip` (`tb.json`, `s<seed>/busy.saif`, `s<seed>/pt/`). `report/strm_table.py` joins them with `synth_dc.csv` into `results/strm/<tech>/` (X53).

```bash
pixi run pwr run '*' --source xbar --tech nangate45          # the 17 points with inputs <= banks
pixi run pwr run 'd8_*' --source streamer --tech nangate45
```

## Bambu (`--source bambu`)

Bambu's points (HSYN1, X44): `rtl/<tier>/<kernel>/bambu_w<W>/` in hls-exercises (`bench/bambu.py`), the netlists in `syn/runs/bambu/<tech>/` (`syn.py --source bambu`). hls-exercises is not changed.

- **tb.json** (`sim/sources/bambu.py`): the top from `filelist.f`, the streams `<arg>_TDATA/_TVALID/_TREADY` in `bench/tier_<tier>/<kernel>/params.json`'s `axis` order (the Vitis kernel's params.json; the top has no `p_` prefix), lanes = TDATA bits / 64, int64; the pins `loop_count`, `len` (where the kernel has it) and `alpha` (axpy, `scalars`); clock `clock` and reset `reset` from `syn.py`'s `SOURCES` (`sim/sources/__init__.py` `ports`); every port of the netlist covered or the point fails. Sizes as for Vitis: the params.json sizes, `b64` when every config pin equals `loop_count`, `n2048` for tier done; `--size all` runs `rtl/<point>/sizes.txt`.
- **Control `bambu_ctl`:** `start_port`, `done_port`, and `idle_port`, an output that is connected and never read or checked.
- **The TB** (`sim/tb/bambu_seq.sv`, with `axis_src` and `axis_sink`): the pins are plain inputs, driven by the generated top from time 0 (before reset is released) and held for the whole run, since Bambu reads them on every iteration; `reset` (synchronous, active low) low for 5 cycles, 2 idle cycles, the sources valid one cycle before the start, then a one-cycle `start_port` pulse; the sinks always ready.
- **The window:** opens at the falling edge before the first rising edge that samples `start_port` = 1 and closes at the falling edge before the first rising edge that samples `done_port` = 1; its rising edges are Bambu's `cycles_done`. Dumping from the edge raising `start_port` to the done edge (PITFALLS Q6).
- **Checks:** every output beat against `sim/ref.py`; the window's cycles against the line a x loop_count + b through `cycles_done` at the point's sizes in `results/bambu/bambu_cycles.csv` (status ok rows; integer, exact at those sizes; dot at W = 4 and 8: a = 2); X9's SAIF check with `clock`; at least 99 % of PT's nets annotated, no wire load (PITFALLS PT1), every module a dump scope (DC6). The SAIF holds about 17 600 nets at Z for the whole window on `done/dot/bambu_w8`: undriven bits of DC's declared vector wires (DC5), not PT nets.
- **Stimulus:** rand64 (X19), the streams in tb.json order, then `alpha`.
- **Runs and results:** `sim/runs/bambu/<tech>/<point>.zip`, run tags `<size>_s0/`; `results/bambu/<tech>/power_pt.csv`, `power_pt_modules.csv`, `power_reports/`, X20's columns.
- **Setup check** (`--source bambu`, default `done/dot/bambu_w8`): nangate45 within 0.03 % in every group; nangate15 register -0.91 %, combinational +2.22 % (PITFALLS PT5).

## XLS (`--source xls`)

Google XLS's points (HSYN1, X44): `rtl/<tier>/<kernel>/xls_w<W>/` in dslx-exercises (`SIM_XLS`, default `../dslx-exercises`), the netlists in `syn/runs/xls/<tech>/`. dslx-exercises is not changed.

- **tb.json** (`sim/sources/xls.py`): the top from `filelist.f`; from `kernels/<tier>/<kernel>/params.json`, the channels `_<arg>_TDATA/_TVALID/_TREADY` (`inputs`, then `outputs`), each matched by position to hls-exercises' `axis` for `sim/ref.py`'s names (dot's `a`, `b`, `res` are `A`, `B`, `out`), and the cfg fields (`cfg`); clock `clk`, reset `rst` from `syn.py`'s `SOURCES`; every port covered. Sizes as for Bambu, `--size all` from dslx-exercises' `rtl/<point>/sizes.txt`.
- **Control `xls_cfg`:** one cfg beat on `_cfg_TDATA/_TVALID/_TREADY`. The fields in params.json's `cfg` order, the first in the high bits, widths from `CFG_BITS` (`loop_count` 32, `len` 32, `alpha` 64); their sum must equal `_cfg_TDATA`'s width (32, 64 or 96) or the point fails. Config fields from the cfg expressions at the size (`loop_count` = n // W, ...); `alpha` drawn as a rand64 data pin after the streams. `sim/pwr.py` packs the word and passes it as `+CFG=<hex>`.
- **The TB** (`sim/tb/xls_seq.sv`): the same reset and idle cycles (`rst`, active high, is the TB's `~rst_n`); the sources valid one cycle before the cfg beat; the cfg beat held until a rising edge samples `_cfg_TREADY` = 1 (the cfg transfer edge). XLS holds every `_TREADY` low in reset and `_cfg_TREADY` low until cfg is valid.
- **The window:** opens at the falling edge before the cfg transfer edge and closes at the falling edge after the rising edge that transfers the last output beat (every sink complete): its rising edges are XLS's `cycles` + 1, since the datapath is combinational and the cycle ending at the last transfer edge computes the last beat. Dumping from the edge raising `_cfg_TVALID` to the edge after the window.
- **Checks:** as for Bambu, with the line through `cycles` in `results/xls/xls_cycles.csv` (a = 1, b = 0) plus 1, and X9 on `clk`.
- **Runs and results:** `sim/runs/xls/<tech>/<point>.zip`, run tags `<size>_s0/`; `results/xls/<tech>/power_pt.csv`, `power_pt_modules.csv`, `power_reports/`, X20's columns.
- **Setup check** (`--source xls`, default `done/dot/xls_w16`): nangate45 within 0.005 %; nangate15 register -0.45 %, combinational +2.00 % (PITFALLS PT5).
- **Random register start:** XLS resets all proc state (`--reset_data_path=true`), so a random start gives the same energy to the last digit.

## Run folder

Vitis's runs are in `sim/runs/<tech>/`, the other sources' in `sim/runs/<source>/<tech>/`; the cell models stay in `sim/runs/<tech>/_cells/`. What is kept of a point is one zip (X51); the point's folder exists only while its worker runs, then `pwr` packs it into the zip (merged: the folder's run tags replace the zip's, the zip's other runs stay), test-reads the zip and deletes the folder. The DC run's three files and a forge or char bundle are unpacked into `tmp/` for the point and deleted after.

```
sim/runs/<tech>/_cells/                         cell models, compiled once per technology (a cache, kept)
sim/runs/<tech>/batches.jsonl                   per batch: date, patterns, licence counts, J, threads
sim/runs/<tech>/<tier>/<kernel>/<point>.zip     tb.json; per run tag busy.saif and pt/*.rpt (char: per window
                                                <window>/<window>.saif and <window>/pt/*.rpt under s<seed>/)
sim/runs/<tech>/setup_check/<point>.zip         check.json, pt/reports/*.rpt, dc/reports/*.rpt
```

The point's folder while its worker runs (all but the zip's members is scratch, deleted):

```
sim/runs/<tech>/<tier>/<kernel>/<point>/
  tb.json, tb.sv                                the point's description and generated top
  logs/                                         vlog_tb, vlog_netlist, vopt
  <size>_s<seed>/ or <size>_forge/              one run
    stim/                                       <arg>.hex per stream (inputs and expected), pins.json
    vsim.log, transcript, vcd2saif.log
    busy.saif                                   the window's activity (kept, X18)
    pt/                                         pt_shell.log, power.rpt, power_hierarchy.rpt, switching_activity.rpt,
                                                units.rpt, wire_load.rpt, licenses.rpt, not_annotated.rpt
    not_annotated.rpt                           nets PT did not annotate from the SAIF (a copy of pt/'s)
sim/runs/<tech>/setup_check/<point>/            pt/, dc/, check.json
```

Rerunning a point replaces only the runs it reruns in the point's zip; the other runs and their SAIFs stay. No `result.json` is written any more (X51): the row is in the CSVs, the rest was printed. git ignores `sim/runs/`.

## What is committed

In `results/<source>/<tech>/` (X20; Vitis in `results/hls/`):

- `power_pt.csv`: one row per point, size and seed, merged on those three, in the columns of X20;
- `power_pt_modules.csv`: `point, tech, path, design, e_dyn_pj`, one row per hierarchical cell of the point's default run;
- `power_reports/<tier>/<kernel>/<point>.zip` (X51): `power.rpt`, `power_hierarchy.rpt`, `switching_activity.rpt` of the default run and the point's `tb.json`; other runs of the point in `<size>_<seed>/` inside it; char: one `<window>/` per window with `power.rpt` and `switching_activity.rpt`, and `tb.json`. Deterministic: it changes in git only when a report does (PT's `Date` line is enough, PITFALLS Z1).

Tool versions, licence counts, the setup check and the validation go into the run note in `results/hls/runs/`.

**n2048 for tier done (SYN1).** A tier-done point's `tb.json` (vecadd, vecmul, vsum, dot) has the size `n2048` after cosim's and `b64` (`sim/sources/hls.py` `EXTRA_SIZES`): one task of N = 2048 elements, the size every forge row runs. Its pins come from `params.json`'s `config` at n = 2048 (vecadd and vecmul `loop_count` = 2048 / W; vsum and dot `loop_count` = `len` = 2048 / W), its expected cycles from cosim's line through n64 and n512 (X19; every tier-done point's line is integer), its stimulus rand64 at 2048 / W beats. It is not the default run (`b64` stays that): its rows are in `power_pt.csv` with size `n2048`, its reports in `power_reports/<point>/n2048_s0/`, and `power_pt_modules.csv` keeps the default run's modules. The untiered points have no `n2048` (matadd and rowsum are vecadd's and vsum's Verilog, PITFALLS DC3; relu and axpy have no forge counterpart). First run in SYN1 R3 (`results/forge/runs/2026-11-01_syn1_r3.md`).

`setup-check` is a diagnostic (X25): it runs PT and DC on the same netlist with the same uniform activity and prints each power group's difference (dynamic and leakage) and the wire-load counts, kept in `check.json`; the differences go into the run note. It fails only on the wire-load check (PITFALLS PT1), never on a difference. Run it when the flow or a library changes. PT is the reference tool for energy; DC's power in `synth_dc.csv` is an early check only.

## Notes

- The SAIF has an entry per net name in each scope (ports of sub-designs included, and undriven wire bits at Z), PT counts the design's nets; the totals differ, most on hierarchical netlists, so coverage is PT's count only.
- On the ESAT servers `vcd2saif` on PATH is DC's (Y-2026.03-SP2); step 0 used PT's (W-2024.09-SP4-1). Both gave the same energy on vecadd `opt_w8` (forge, 11.4086 against 11.40865 pJ).
