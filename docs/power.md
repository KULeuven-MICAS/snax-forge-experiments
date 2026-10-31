# Power: `sim/pwr.py`

Dynamic energy per cycle and per firing of a mapped netlist, from simulated activity (docs X7, X13). For each point: a functional, zero-delay Questa simulation of the netlist DC wrote into `syn/runs/hls/<tech>/`, its busy window cut into a SAIF, and PrimePower on the same netlist with the same library, constraints and wire-load setting as DC. No resynthesis. The flow was proved by hand in step 0 (`results/hls/runs/2026-10-29_pwr_step0.md`, `sim/probe/`, unchanged) and first run in `2026-10-29_pwr_r1.md`.

## Before a run

- The point's synthesis run exists: `syn/runs/hls/<tech>/<tier>/<kernel>/<point>/out/<top>_mapped.v` and `tech.json` (`pixi run syn run ...`).
- `pixi install` once (docs X15).
- Tools: `vlib`, `vlog`, `vopt`, `vsim` from PATH; `pt_shell` from PATH or `PT_SHELL`; `lmutil` from PATH or `LMUTIL` (a non-interactive shell may not have it on PATH, PITFALLS L3); `vcd2saif` from PATH, else next to `pt_shell`; `dc_shell` (setup-check only) from `DC_SHELL` or PATH. Licence servers from `MGLS_LICENSE_FILE` and `SNPSLMD_LICENSE_FILE`.

## Commands

```bash
pixi run pwr tbjson done/vecadd/opt_w8                                   # print the point's tb.json
pixi run pwr setup-check --tech nangate45                                # PT against DC, forced activity (X10)
pixi run pwr setup-check --tech nangate15                                # (0.1 % per group; nangate15 combinational 2.5 %)
pixi run pwr run 'done/vecadd/*' --tech nangate45                        # rand64, 64 beats, seed 0
pixi run pwr run 'done/vecadd/*_w8' --tech nangate45 --size n512         # at a cosim size
pixi run pwr run done/vecadd/opt_w8 --tech nangate45 --stim forge --size n512   # data.h, validation only
pixi run pwr run 'done/*/*' 'untiered/*/*' --tech nangate45 --size all   # whole tasks: every size in sizes.txt
pixi run python sim/report_energy.py                                     # results/hls/report_energy.md from power_pt.csv
pixi run pwr summary 'done/vecadd/*' --tech nangate45                    # print power_pt.csv
pixi run pwr tbjson done/dot/forge5_w4 --source forge                    # a forge point's tb.json
pixi run pwr run done/vecadd/forge_w4 done/dot/forge5_w4 --source forge --tech nangate45 --size n2048
pixi run pwr setup-check --source forge --tech nangate45                 # on done/vecadd/forge_w4
```

`--size all` runs every size in the point's `rtl/<point>/sizes.txt` (the task sizes), one compile per point; `--seed N` changes the rand64 seed; `-j N` caps the workers below what the licences allow. Patterns are shell globs over hls-exercises' `rtl/` folders, as in `syn.py`.

## Stages

One worker per point; J workers at once and nproc // J PT threads each, from the free licences at the start (X16).

| stage | what | fails the point when |
|---|---|---|
| tb.json | `sim/sources/hls.py` from the top's Verilog ports, `filelist.f` and `params.json` (X14); a `# ram:` point is `skipped` | a port is not covered, or `control.kind` is not `ap_ctrl_hs` |
| compile | `sim/tb/*.sv` and the generated `tb.sv`; the netlist with `vlog -timescale 1ns/1ps`; `vopt +initreg+0 +acc=n` against the cell models compiled once per technology into `sim/runs/<tech>/_cells` | vlog or vopt errors |
| stimulus | rand64 (or forge) per X19, the reference from `sim/ref.py`, `$readmemh` files | an input stream bit never toggles in a run of 64 beats or more (fewer: counted in `result.json`); forge: `sim/ref.py` differs from `data.h`'s `EXP_*` |
| vsim | `vsim -c` with no SDF, `+nospecify +notimingchecks`, data and sizes by plusargs (`sim/scripts/run.do`); the TB compares every output beat and dumps the DUT's scopes from the edge raising `ap_start` to the done edge | a mismatch, X/Z on a valid output, a timeout |
| cycles | the TB's count (X12) against cosim's line a x loop_count + b, or cosim exactly at a cosim size (X19) | a different count, or no integer line |
| vcd2saif | `-instance tb/dut -time t0 t1` in the VCD's unit; the VCD is deleted at once (X8, X18) | no SAIF |
| SAIF check | T0 + T1 + TX = DURATION on every driven net (all-Z entries are undriven wire bits, counted apart: PITFALLS DC5), every entry parsed, DURATION = cycles x 10 ns, `ap_clk` TC = 2 x cycles (X9) | any of these |
| PT | `sim/scripts/pt_power.tcl`: tech.json's .db (md5 checked), netlist, `constraints.sdc`, `set_load 0` / `set_resistance 0` on every net (PITFALLS PT1), `read_saif`, `report_power` and `-hierarchy` | PT errors, or under 99 % of nets annotated |
| cleanup | `work/` and `vsim.wlf` deleted, whatever happened | |

The TB (`sim/tb/`): `ap_ctrl_hs_seq.sv` (10 ns clock, 5 cycles of synchronous active-low reset, `ap_start` held until an edge samples `ap_ready`, the pins' `ap_vld` pulsed on the first start cycle, the window, a timeout), `axis_src.sv` (always valid, holds each beat until its handshake) and `axis_sink.sv` (always ready, compares each beat, X/Z check). DUT outputs are sampled at falling edges, where nothing toggles, so the TB never races with the cell models' flops. `tb.sv`, generated per point, wires `tb.json`'s ports and holds `$dumpvars` on the DUT and each sub-design scope found in the netlist (not the cells': PITFALLS LIB2).

A tool that fails on a licence error is run once more (X17); its first log is kept as `*.licence_retry.log`.

## Forge (`--source forge`)

snax-forge's accelerators (SYN1): the bundles in `rtl/forge/<point>/` (`forge/bundles.py`), the netlists DC wrote in `syn/runs/forge/<tech>/` (`syn.py --source forge`, X6). snax-forge is not changed. The default stays `--source hls`, and the HLS path is as above.

- **tb.json** (`sim/sources/forge.py`, X14): from the bundle's `point.json` (recipe, W, `snax_forge_commit`), `bundle.json` (the top), `accelerator.json` (its one group's CSRs by offset, its outer ports in order with lanes and dtype; a point with more than one group is refused, dot 1 is not in SYN1), the streamer hjson (each mover's `num_channel`) and the netlist's port list, every port covered as C§17's wrapper has them (`clk_i`, `rst_ni`, the CSR port, `stream2acc_<k>_*`, `acc2stream_<k>_*`, `<group>_busy_o`, `<group>_done_o`). The rest comes from snax-forge's own code, through `forge/query.py` run in snax-forge's pixi environment with `forge/bundles.py`'s cleaned environment: each port's container (the design point's graph, as its `gen/rtl.py` finds it), the recipe's kernel, and `expected_cycles`, the group's busy cycles from `gen/rtl.py`'s `group_counter` (snax-gvsoc's group rule, every input valid and the output ready) with JOBS and the units' T as the program writes them.
- **Control `forge_csr`:** the CSR port's names, the group's `busy` and `done` pins and its CSR offsets. One size, `n2048` (N = 2048 for every SYN1 comparison): an elementwise group writes JOBS = N / W, a group with a fold (a unit with JOB_BEATS) JOBS = 1 and JOB_BEATS = N / W, then START. No other read-write CSR is accepted.
- **The TB** (`sim/tb/csr_seq.sv`, with `axis_src` and `axis_sink` as for HLS): `rst_ni` low for 5 cycles and released at a falling edge (asynchronous reset), 2 idle cycles, then each write offered from a rising edge until a falling edge samples `csr_req_ready_o` (`csr_rsp_ready_i` always 1; a write has no response), START last; `go` rises with the START write, so the sources are valid from the first busy cycle, and the sinks are always ready.
- **The window:** START is accepted in cycle a, the group is busy in a + 1 .. E and `<group>_done_o` is high in E + 1, so COUNTER = E - a (C§17). The window opens at the falling edge before the edge that accepts START and closes at the falling edge before e_E, one cycle before the first falling edge that samples done = 1: its rising edges are e_a .. e_{E-1}, E - a of them, as X12 counts an HLS run. Dumping runs from the edge that offers START to the edge after done is seen (PITFALLS Q6). After the run the TB reads COUNTER over the CSR port and prints it beside the window's cycles.
- **Checks:** every output beat against `sim/ref.py` (vecadd, vecmul, vsum, dot); the window's cycles = COUNTER read back = `expected_cycles`, any mismatch fails the point; once per kernel, size and seed in a batch, `sim/ref.py` against snax-forge's kernel body (`kernels/<...>/<kernel>.py`, its `SPEC.func`, run by `forge/query.py ref` on the same inputs; the inputs depend on N and the seed only). The SAIF check is X9's with `clk_i`; PT must annotate 99 % of the nets that are not floating: a net PT leaves at default that the SAIF has at Z for the whole window has no driver (STATUS bits 2 to 31, PITFALLS PT6) and leaves the denominator. Every module of the netlist must get a dump scope (PITFALLS DC6).
- **Stimulus:** rand64 only (X19): N full-range int64 per input stream, seed 0, stream by stream in tb.json order; N / W beats, at least 64 at every W, so the toggle check applies.
- **Runs and results:** `sim/runs/forge/<tech>/<point>/n2048_s0/` (the cell models stay in `sim/runs/<tech>/_cells/`); `results/forge/<tech>/power_pt.csv`, `power_pt_modules.csv` and `power_reports/`, with X20's columns plus `recipe` and `snax_forge_commit`. `config` is the CSR writes before START, `beats` the beats per input stream, and per firing is per input beat.
- **Setup check:** `pt_power.tcl` and `dc_readback.tcl` take the clock and reset ports from the run's `tech.json` (`dc_env`'s `SYN_CLK_PORT`, `SYN_RST_PORT`), else `ap_clk` and `ap_rst_n`, since `constraints.sdc` names them (SYN1 R0). On the forge point nangate15's register group is -0.55 % (PITFALLS PT5).

## Run folder

```
sim/runs/<tech>/_cells/                         cell models, compiled once per technology
sim/runs/<tech>/batches.jsonl                   per batch: date, patterns, licence counts, J, threads
sim/runs/<tech>/<tier>/<kernel>/<point>/
  tb.json, tb.sv                                the point's description and generated top
  logs/                                         vlog_tb, vlog_netlist, vopt
  <size>_s<seed>/ or <size>_forge/              one run
    stim/                                       <arg>.hex per stream (inputs and expected), pins.json
    vsim.log, transcript, vcd2saif.log
    busy.saif                                   the window's activity (kept, X18)
    pt/                                         pt_shell.log, power.rpt, power_hierarchy.rpt, switching_activity.rpt,
                                                units.rpt, wire_load.rpt, licenses.rpt, not_annotated.rpt
    not_annotated.rpt                           nets PT did not annotate from the SAIF
    result.json                                 the row, expected cycles, window, SAIF stats, coverage, stage times
sim/runs/<tech>/setup_check/<point>/            pt/, dc/, check.json
```

Rerunning a point replaces only the run folders it reruns; other runs of the point and their SAIFs stay. git ignores `sim/runs/`.

## What is committed

In `results/hls/<tech>/` (X20):

- `power_pt.csv`: one row per point, size and seed, merged on those three, in the columns of X20;
- `power_pt_modules.csv`: `point, tech, path, design, e_dyn_pj`, one row per hierarchical cell of the point's default run;
- `power_reports/<tier>/<kernel>/<point>/`: `power.rpt`, `power_hierarchy.rpt`, `switching_activity.rpt` of the default run and the point's `tb.json`; other runs of the point in `<size>_<seed>/` below it.

Tool versions, licence counts, the setup check and the validation go into the run note in `results/hls/runs/`.

`setup-check` passes when PT and DC, given the same uniform activity, agree within 0.1 % in every power group (dynamic and leakage), except nangate15's combinational group within 2.5 % (PITFALLS PT5). PT is the reference tool for energy; DC only checks that PT's setup (netlist, library, loads, constraints) is DC's.

## Notes

- The SAIF has an entry per net name in each scope (ports of sub-designs included, and undriven wire bits at Z), PT counts the design's nets; the totals differ, most on hierarchical netlists, so coverage is PT's count only.
- On the ESAT servers `vcd2saif` on PATH is DC's (Y-2026.03-SP2); step 0 used PT's (W-2024.09-SP4-1). Both gave the same energy on vecadd `opt_w8` (forge, 11.4086 against 11.40865 pJ).
