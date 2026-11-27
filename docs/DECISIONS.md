# Decisions

What this repository has settled: one entry per live choice, in its current form. Flows are in [`TOOL.md`](TOOL.md), the folder READMEs and [`power.md`](power.md); the tables in [`cost_tables.md`](cost_tables.md); tool behaviour in [`PITFALLS.md`](PITFALLS.md).

Rules:

- An entry is a choice someone may want to reverse: what was decided, why, and where the detail lives. A change is written into the entry, not chained after it.
- Entries merged into one keep all their numbers in its heading, so a cite of any of them still finds it. A number is never changed or reused; a removed entry's text is in git history.
- A new decision gets the next free number, under its area, and names the run note that found it. Next free number: **X114**.

Retired numbers: X10 (now in X25's heading), X36 (in X37's), X46 (in X64's); X26, X27, X35 and X43 under "Retired" at the end.

## Environment and runs

### X6 — Run folders are kept

- **Decided:** a clean never deletes `syn/runs/` (netlists) or `sim/runs/` (power runs); a rerun replaces only its own points.
- **Why:** power reads DC's netlist with no resynthesis (X7), and a resynthesis can differ (PITFALLS DC3).
- **Where:** `CLAUDE.md`, "Working rules".

### X15 — Python from pixi

- **Decided:** Python 3.11 from the pixi workspace (`pixi run ...`), never the host's `python3`; scripts in files.
- **Why:** the server's `python3` is 3.6; one locked environment.
- **Where:** `pixi.toml`; `TOOL.md`, section 1.

### X16 · X59 — Jobs from free licences, 16 cores

- **Decided:** count free licences (`lmutil lmstat`) before a batch; PT threads = cores // jobs. At most 16 cores (24 on Ryan's word, 8 left free), never every licence: DC `-j 4 --cores 4` (`-j 6` at 24), power `--cores 16 -j 4`, one batch at a time. Cluster runs: X68.
- **Why:** host and licences are shared; a multicore DC run can hold several DC-Expert licences (PITFALLS L4).
- **Where:** `TOOL.md`, section 1; `results/forge/runs/2026-11-10_csyn1_r1.md`.

### X17 — Licence errors are retried once

- **Decided:** a licence failure is retried once; a second is reported.
- **Why:** error -92 was transient (PITFALLS L1).
- **Where:** `syn/syn.py` `run_dc`, `sim/pwr.py`, `cluster/power.py`.

### X51 — Outputs zipped one per point

- **Decided:** each point's bulky outputs are one deterministic zip through `arc/arc.py`, unpacked into `tmp/` one point at a time; `pixi run arc check` ends every round with nothing left over.
- **Why:** the home's file quota is shared; loose outputs took about 116,000 inodes, the zips about 2,500.
- **Where:** `CLAUDE.md`, "Files are zipped"; `results/runs/2026-11-06_arc1_r1.md`.

## Libraries and synthesis

### X1 — Nangate 45 nm

- **Decided:** Nangate 45 nm Open Cell Library (typical, 1.10 V, 25 °C), `--tech nangate45`; the 15 nm library was removed (X88).
- **Why:** open, with CACTI memories at the same node (X47); OSU gscl45nm has 31 cells and broken pin limits.
- **Where:** `syn/tech/nangate45.json`; `results/hls/runs/2026-10-28_step0_libs.md`.

### X2 — Clock 10 ns

- **Decided:** 10 ns on every point; `fmax_mhz` = 1000 / (`clock_ns` − `slack_ns`) is a lower bound.
- **Why:** one clock makes area and energy per cycle comparable; DC never upsizes for speed at 10 ns.
- **Where:** `syn/scripts/constraints.sdc`; `results/hls/runs/2026-10-27_done.md`.

### X3 — No wire load; drive and load

- **Decided:** no wire-load model; inputs driven by `INV_X4`, outputs loaded with four `INV_X4` inputs (25.0 fF), max transition 0.25 ns; a run whose `area.rpt` shows a model fails.
- **Why:** the default changes timing and power and survives `auto_wire_load_selection false` (PITFALLS DC1).
- **Where:** `syn/scripts/dc_syn.tcl`; `results/hls/runs/2026-10-28_syn_tech_probe.md`.

### X4 — Units checked

- **Decided:** `constraints.sdc` in ns and fF, scaled by `syn.py`; DC stops when the library's name or units differ from the tech file.
- **Why:** other units put every constraint 1000x off silently (PITFALLS DC2).
- **Where:** `syn/README.md`, "Technologies".

### X5 — Results per technology

- **Decided:** `results/<source>/<tech>/` per technology; only `KEPT_REPORTS` committed.
- **Why:** areas compare only within a library; the kept reports are what the models read.
- **Where:** `syn/README.md`, "What a run leaves".

### X40 — Path-class slacks

- **Decided:** worst in2reg, reg2reg, reg2out, in2out slack into `path_classes.rpt` and `slack_*_ns`.
- **Why:** XLS's points are one combinational stage, which `fmax_mhz` hides.
- **Where:** `syn/README.md`, "Columns".

### X41 — Split only where declared

- **Decided:** split only where the hierarchy declares it: forge (X22), Bambu (`controller_*`, `datapath_*`, glue); Vitis and XLS report totals.
- **Why:** splitting a flat netlist means guessing.
- **Where:** `syn/README.md`, "Columns".

### X69 — No SDF unless asked

- **Decided:** DC writes an SDF only with `syn.py --sdf`.
- **Why:** energy comes from a zero-delay run (X7); nothing reads it.
- **Where:** `syn/syn.py`.

### X79 · X87 · X88 — Clock-gated synthesis is the basis

- **Decided:** `--clk-gate` (`SYN_CLK_GATE_ENABLE`, default 0) runs `clock_gating.tcl` (`latch_posedge` gates, `-minimum_bitwidth 2`) with `compile_ultra -gate_clock`, tags the run `_cg` and its rows `clk_gate` 1. Every source and HWCOST's tables (X83) are gated; ungated twins and the 15 nm library (X1) were removed.
- **Why:** real designs are gated; ungated windows were 46 to 82 % idle clocking, the cluster's energy 2 to 5 times too high; gated, HWCOST's streamers are within −3 to −7 %.
- **Where:** `syn/README.md`, "Clock gating"; `results/cluster/runs/2026-11-13_cg1_r1.md`, `2026-11-15_cg3_r3.md`, `2026-11-15_cg4_r1.md`; `results/runs/2026-11-15_cg6_r1.md`, `_r2.md`, `2026-11-16_cg5_r1.md`, `_r2.md`.

## Power

### X7 — Energy from simulated activity

- **Decided:** a zero-delay Questa run of the mapped netlist (`+nospecify +notimingchecks`, `vopt +initreg+0 +acc=n`), then PrimePower averaged mode with DC's netlist, library and constraints; no resynthesis.
- **Why:** DC's default activity follows structure, not work (PITFALLS DC4); zero delay suits an unplaced netlist and a per-cycle model.
- **Where:** `power.md`; `results/hls/runs/2026-10-29_pwr_step0.md`.

### X8 — Activity through vcd2saif

- **Decided:** the TB dumps a VCD over the window, `vcd2saif` makes the SAIF for PT's `read_saif`, the VCD goes at once; Questa's SAIF is unused.
- **Why:** Questa 2022.4's SAIF is wrong at zero delay (PITFALLS Q4); vcd2saif matches PT's `read_vcd` within 0.1 %.
- **Where:** `power.md`, "Stages"; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X9 — Every SAIF is checked

- **Decided:** T0 + T1 + TX = DURATION (cycles x period) on every driven net, the clock's TC = 2 x cycles; at least 99 % of nets annotated (95 % of driven nets on a cluster); a failure fails the point.
- **Why:** coverage alone passed a defective SAIF.
- **Where:** `sim/pwr.py` `saif_check`; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X11 — Flop energy is clock plus register

- **Decided:** flop energy is always e_clk + e_reg.
- **Why:** PT books a clock edge under register when the output toggles, else under clock (PITFALLS PT3).
- **Where:** `power.md`, "Energy quantities".

### X12 — Vitis's window

- **Decided:** rising edges from the first sampling `ap_start` = 1 to the first sampling `ap_done` = 1; the window runs between the falling edges before them. Other sources: X23, X44, X73.
- **Why:** equals cosim's latency with no offset.
- **Where:** `power.md`, "Stages".

### X13 — Busy-window dynamic energy

- **Decided:** per cycle E_comb and E_flop = E_clk + E_reg + E_seq; per task (E_comb + E_flop) x cycles. No leakage (in `synth_dc.csv`); idle windows only for blocks (X31) and the cluster (X73).
- **Why:** snax-forge's models take dynamic activity per active cycle.
- **Where:** `power.md`, "Energy quantities".

### X18 — No dumps kept

- **Decided:** no VCD, WLF or compiled design kept; the zip holds `tb.json`, the SAIF and PT's reports.
- **Why:** a VCD grows with nets x cycles; the rest rebuilds in seconds.
- **Where:** `power.md`, "Run folder".

### X19 — rand64 stimulus

- **Decided:** full-range int64 from NumPy's `default_rng(0)`, stream by stream in `tb.json` order, then the pins; default HLS task 64 beats (`b64`), every input bit toggling. Expected cycles from cosim's line a x loop_count + b.
- **Why:** energy must not depend on how narrow the test values are.
- **Where:** `power.md`, "Stages"; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X90 — Narrow forge points

- **Decided:** at `types=i8` or `i16` each input is full-range at its dtype (X19's seed), packed num_slc = 64 / bits a word little-endian (snax-forge D142), outputs wrapped to int32 (OP_TYPE); a packed output (D174) is checked whole. The reference runs at the point's dtypes (`forge/query.py point`).
- **Why:** every bit toggles as rand64 at int64 does, and the int32 wrap is what the hardware computes.
- **Where:** `power.md`, "Forge"; `results/runs/2026-11-16_char2_r7.md`.

### X20 · X60 · X74 — Power results

- **Decided:** `power_pt.csv` one row per point, size and seed; `power_pt_modules.csv` one per hierarchical cell (default and n2048 runs); a cluster one per window (`e_win_pj`), from one VCD and one averaged PT session.
- **Why:** the model needs energy per cycle and firing; time-based mode halves clock-pin energy (PITFALLS PT10).
- **Where:** `power.md`, "Energy quantities" and "What is committed"; `results/cluster/runs/2026-11-12_pwr1_r2.md`.

### X25 · X10 — PT the reference, setup check a diagnostic

- **Decided:** PT with simulated activity is the reference, DC's power an early check; `pwr setup-check` prints PT-vs-DC differences and never fails a point (X10's tolerances gone); the wire-load and SAIF checks stay gates.
- **Why:** they agree within 0.02 % on nangate45 and differ only in default-activity propagation (PITFALLS PT2).
- **Where:** `power.md`, "What is committed"; `TOOL.md`, section 4.

### X76 — 1 ns clock read as 10 ns

- **Decided:** each cut VCD's `$timescale 1ps` becomes `10ps`, so snax_cluster's 1 ns run reads as 10 ns.
- **Why:** zero-delay activity does not depend on the period; X9 and PT's clock then hold.
- **Where:** `sim/pwr.py` `vcd_windows`; `results/cluster/runs/2026-11-12_pwr1_r1.md`.

## Memory

### X47 · X100 — SRAM from CACTI 7, lstp cells

- **Decided:** one-port banks, no ECC, from CACTI 7 (`pixi run ram-build`) at 45 nm, itrs-lstp cells and peripherals, weighted to dynamic energy and area; lstp's 1.1 V is Nangate's 1.10 V, so nothing is scaled; a bank's leakage is CACTI's subthreshold plus gate leakage, one value. The itrs-hp table and macros are dropped.
- **Why:** OpenRAM gives one power for read, write and idle; CACTI gives both energies, area and leakage in 0.2 s. An L1 at 100 MHz would use low-standby-power cells: at itrs-hp a 512 x 64 bank leaked 2.33 mW, so 32 banks 0.75 nJ a cycle, more than any design's dynamic energy; at lstp it leaks 0.14 µW with its area and energies within 0.2–4.3 % and a 1.02 ns read.
- **Where:** `ram/README.md`; `results/ram/runs/2026-11-05_ram1_r1.md`, `results/ram/runs/2026-11-26_cost2_r1.md`.

### X48 — SRAM table a lookup

- **Decided:** `ram_table.csv`: depth 32–4096 (step 32) x width 8–256 (step 8), 4,095 rows, never interpolated.
- **Why:** CACTI jumps up to 30 % between neighbours (PITFALLS C5); the best fit misses by 6 %.
- **Where:** `cost_tables.md`, "SRAM banks".

### X49 — Generated SRAM macros

- **Decided:** `pixi run ram lib` writes a Liberty model (pins from `DFF_X1`, `BUF_X4`) and a counting Verilog model (`RAMCOUNT`) with `tc_sram_impl`'s ports; never committed.
- **Why:** CACTI has no Liberty; the table's own numbers add no second model.
- **Where:** `ram/README.md`.

### X50 — Counted memory accesses

- **Decided:** a single point's macros cost counted reads and writes x table energies, plus PT for the rest; clusters: X75.
- **Why:** averaged PT is 12.5 % low on macros (PITFALLS PT7); counters are exact.
- **Where:** `cost_tables.md`, "SRAM banks".

## Cost tables

### X28 — The char source

- **Decided:** `char/points.json`, one catalogue datapath a point; `pixi run char-rtl` runs `gen-block` into `rtl/char/`, refusing a dirty checkout.
- **Why:** a result traces to the RTL synthesized (as X21).
- **Where:** `TOOL.md`; `results/char/README.md`.

### X29 — The block grid

- **Decided:** 27 int64 points: SimdLanes add, mul and the accumulating Mac at W = 1, 8, 32; TreeAccumulate W = 1–32; SerialAccumulate W = 2–32; LinkBuffer D = 1–16 (W = 1), D = 1 at W = 8, 32; beside them X89, X94, X97, X98, X99.
- **Why:** the forms forge uses, enough for a first-order model.
- **Where:** `char/points.json`.

### X30 — A block alone

- **Decided:** `syn.py --source char` synthesizes the block as top (`clock`, async high `reset`), X22's settings, into `char_synth.csv`.
- **Why:** alone equals inside an accelerator within 0.05 %.
- **Where:** `results/char/README.md`; `results/char/runs/2026-11-03_char1_r0.md`.

### X31 — Block windows

- **Decided:** fixed 128-cycle windows: `busy` and `idle` for compute blocks, `stream` for LinkBuffer; inputs change at the rising edge, after a lead-in of the window's kind.
- **Why:** the model needs busy and idle apart; falling-edge inputs doubled transitions (TreeAccumulate 1.36x).
- **Where:** `power.md`, "Char"; `results/char/runs/2026-11-03_char1_r2.md`.

### X32 — VCD cut per window

- **Decided:** `vcd_windows` cuts one VCD per window and vcd2saif runs on each cut (char, streamer, xbar, cluster).
- **Why:** on a shared VCD vcd2saif adds a phantom toggle (PITFALLS VS1).
- **Where:** `power.md`, "Stages".

### X33 — char_power.csv and e_hold

- **Decided:** one row per point and window; e_hold = mean idle energy per sequential cell of the registered blocks (0.0655 fJ, gated); an idle LinkBuffer costs flops x e_hold; the spread is reported, not checked (X82).
- **Why:** a held register costs its gate's share, so points spread with the bits per gate (X83).
- **Where:** `results/char/README.md`.

### X34 — busy_t1, duty50 dropped

- **Decided:** busy and idle only (stream for LinkBuffer); an isolated accumulator fire costs 25 to 30 % more, a known limit.
- **Why:** `busy_t1` was within 5 % of busy; `duty50` is a check.
- **Where:** `results/char/char_table.md`, "Known limits".

### X37 · X36 — char.json, the block model

- **Decided:** `char-export` writes `char.json` from gated rows (replacing X36's draft): flop constants per sequential cell, control's counter factor (over 48 int64 forge points), per block and type pair comb area and energy a fire with a lane rule (X89).
- **Why:** it lands within 0.997 to 1.035 of the forge kernels at W = 8 and 32; 0.92 to 1.40 in energy on narrow types.
- **Where:** `results/char/README.md`, "The block model"; `results/runs/2026-11-16_cg5_r2.md`, `2026-11-16_char2_r7.md`.

### X89 — The type axis

- **Decided:** each compute block at its 10 width pairs (8 to 64, w_out ≥ w_in) at one lane count (W0 = 1 for SimdLanes, 8 for the folds), FifoPacker at int32, int16, int8; over lanes `copy` for lane-copy blocks, `slope` (int64 per-lane cost x w_in / 64) for narrow folds; LinkBuffer x w / 64.
- **Why:** DC trims sign bits differently per block (shared ratios missed by 2x); the slope lands within 1 to 5 % on area.
- **Where:** `results/char/char_table.md`, "The type axis"; `results/char/runs/2026-11-16_char2_r2.md`, `_r4.md`.

### X94 — The input slicer

- **Decided:** `FifoSlicer` (D180) at int32 x1, int16 x1, x2, int8 x1, x2, x4 (d_in 8, 4, 2), gated; `slice` windows `busy` and `idle`; `char.json` one entry per lane type and lanes, `flops` = 64 + ⌈log₂ d_in⌉ + 1, `load_bits` = 64 / d_in + ⌈log₂ d_in⌉ a pop.
- **Why:** HWCOST listed it in `char.missing`; d_in sets the cost; the pop lands at 1.11 to 1.30 of busy.
- **Where:** `results/char/char_table.md`, "FifoSlicer"; `results/char/runs/2026-11-17_tiera1_r5d.md`.

### X97 — The Mac's bank of rows

- **Decided:** the `Mac` with R rows (D191) at int8/int32, R = 2 to 16, W = 4, 8, against its rows-1 base, gated, TB kind `bank`; fitted forms in `char.json`'s `bank` (D193): area 59.8 µm² × W · R beyond the flops, W · (0.343 log₂ R + 0.316) pJ a fire.
- **Why:** the flop-only estimate gave 0.76 to 0.87 of the area, up to 3.37 times the energy; with the forms 0.99 to 1.01 and 0.90 to 1.06 (MUX2 point aside, PITFALLS DC20).
- **Where:** `results/char/runs/2026-11-23_tiera2_b6x.md`; `char/checks.py --bank`.

### X98 — Mixed input pairs

- **Decided:** a SimdLanes mul (W = 1) and the accumulating Mac (W = 8) with a at int8 and b at int32, op and out int32, gated, each its own `char.json` entry at its exact `inTypes`, built at their own snax-forge commit (`source.snax_forge_mixed`); `char_table` keys a pair by both input widths (`pair_key`, in column `i8xi32`) and the CSVs' `in_type` is `int8xint32`, the widest input kept for the rules that compare widths (`pair`).
- **Why:** atax's second half multiplies A at int8 by t = A x at int32, and the cost lookup priced that block at int32 × int32 (snax-forge D176); measured, the Mac's comb is 7,690 µm² and 11.06 pJ a fire against 17,197 µm² and 25.67 pJ, 0.31 and 0.32 of the way from int8 × int8 to int32 × int32.
- **Where:** `results/char/runs/2026-11-24_tiera3_x1.md`; `results/char/char_table.md`, "Mixed input pairs".

### X99 — SimdLanes' scalar forms

- **Decided:** the seven SimdLanes scalar forms snax-forge's estimate looks up, each its own `char.json` entry at W = 1 keyed by its scalars, `copy` over lanes, gated, built at their own snax-forge commit (`source.snax_forge_scalar`): one stream with k (`mul` by k from a CSR at int64 and at int8 → int32, `max` with k = 0 baked at int32) and axpby with k1 and k2 (both from CSRs at int64 and int32, k1 from a CSR alone, k1 baked to 3, at int32). A scalar from a CSR is an input pin of opType's width that the testbench holds at one random full-width value a window (drawn after the data, applied at the window's lead-in), outside the toggle check; `char_table` lists the forms after the plain SimdLanes rows, the scalars in the op column, and sets each beside the plain SimdLanes at its pair and W.
- **Why:** gesummv's forms scale a matrix by a CSR scalar or end in one axpby, and axpy and relu have scalars too; `char.json` had no SimdLanes with a scalar, so the estimate priced all of them at 0 (`char.missing`). Measured, a scale by a CSR k is the plain multiplier's netlist (the int8 one X98's int8 × int32 mul) at 0.79 to 0.80 of its energy a fire, k held; axpby with both scalars from CSRs is two multipliers and an add in area (2.03 to 2.04 muls beyond the add) at 1.34 to 1.44 muls of energy; k1 baked to 3 is a second adder; relu's max with 0 a quarter of an add.
- **Where:** `results/char/runs/2026-11-25_tiera4_x1.md`; `results/char/char_table.md`, "Scalar forms"; `power.md`, "Char".

### X52 · X82 — Reader and interconnect characterized

- **Decided:** reader over depth {2, 4, 8, 16} x loops 1–7 x channels {1, 2, 4, 6, 8, 16} (168), interconnect over inputs 4–64 x banks {16, 32, 64} (27, energy where inputs ≤ banks), totals only; a writer priced as a reader. A row fails only with no data; flop counts are printed.
- **Why:** the model scales from these full-rate costs; gate counts are read, not gated (Ryan, 13 Nov).
- **Where:** `cost_tables.md`; `power.md`, "Streamer and interconnect"; `results/strm/runs/2026-11-06_strm1_r1.md`, `2026-11-13_cg2_r3.md`.

### X53 · X54 — STRM tables and interpolation

- **Decided:** `pixi run strm-table` writes `streamer.csv`, `xbar.csv`; linear one axis at a time between grid values, the interconnect's energy linear in 1/inputs; above inputs = banks the value at inputs = banks (by kind, X93).
- **Why:** near multilinear; energy a + b/n fits 1/inputs exactly (leave-one-out 2.5 % against 9.0 %).
- **Where:** `cost_tables.md`, "Reading a table"; `results/strm/runs/2026-11-06_strm1_r2.md`.

### X70 — xbar_mix: tied inputs

- **Decided:** `xbar_mix` ties inputs as the cluster does: inputs {16, 32, 64} x banks {16, 32, 64}, all read-write, read-only and write-only, plus two 36-input points; the 18 with $n \le b$ powered by kind (X93).
- **Why:** HWCOST was +74 % with every input read-write; DC removes what the ties make dead.
- **Where:** `syn/README.md`, "The xbar_mix source"; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`; `results/runs/2026-11-16_cg5_r1.md`.

### X71 — Tied inputs in the area

- **Decided:** `xbar_kinds.json`'s default area is `xbar.csv`'s times $1 - f_{ro}\thinspace n_{ro}/n - f_{wo}\thinspace n_{wo}/n$; a least-squares cost per crosspoint kind is the option. Energy: X93.
- **Why:** two numbers on `xbar.csv`; +10.5 % on the gated cluster (crosspoint +7.6 %), within HWCOST's 30 %.
- **Where:** `cost_tables.md`, "Read-only and write-only inputs"; `results/xbar_mix/runs/2026-11-11_csyn1_r3d.md`.

### X93 — Interconnect energy by input kind

- **Decided:** $e_k(b) = e_{access}(b, b)\thinspace(1 - g_k(b))$, $g_k$ the all-kind-k saving at $n = b$, linear in $b$ over 16, 32, 64; read-write keeps $e_{access}$. Amends X70, X71, X54.
- **Why:** one-kind channels paid 0.67 to 0.81 of the read-write price; with the factors 0.94 to 0.99 at W ≤ 8.
- **Where:** `cost_tables.md`, "The energy by input kind"; `results/xbar_mix/runs/2026-11-17_ge1_r4.md`, `_r5.md`.

### X83 · X85 — Clock-gated block tables

- **Decided:** tables from `clk_gate` 1 rows, a clock gate a sequential cell; beyond a grid the outermost line continues, clamped at 0 (`extrapolate=True`).
- **Why:** gated clusters barely idle-clock; a gate's 4.9 fJ a cycle is shared, so e_hold (0.0655 fJ) spreads 0.0024 to 0.0754 fJ and the hold term is negligible.
- **Where:** `cost_tables.md`; `results/strm/runs/2026-11-14_cg2_r4.md`, `results/cluster/runs/2026-11-14_cg3_r1.md`.

### X101 — Leakage in the tables

- **Decided:** the tables carry the clock-gated points' leakage beside their area, no new runs: `char.json`'s `flop.leak_uw` (the mean sequential leakage per sequential cell over the int64 points, as `flop.area_um2`) and each point's `leak_comb_uw`, read by the entry's lanes rule; `streamer.csv` and `xbar.csv`'s `leak_uw` (DC's `leak_power_uw`). A block leaks $P_{comb} + n_{bits} P_{flop}$.
- **Why:** leakage is paid every cycle a design runs and follows what is placed, as area does; over the 87 char points the formula is a median 0.09 % from DC, at most 10 %.
- **Where:** `cost_tables.md`, "Leakage"; `results/char/README.md`; `results/runs/2026-11-26_cost2_r1c.md`.

## Sources

### X14 — tb.json is internal

- **Decided:** an adapter per source (`sim/sources/`) writes `tb.json` from the producer's outputs; producers are never changed to be measured.
- **Why:** this repository is the measuring side.
- **Where:** `power.md`, "Stages".

### X21 — The forge source

- **Decided:** `forge/points.json` (`<tier>/<kernel>/<case>_w<W>`); `pixi run forge-rtl` zips snax-forge's bundles into `rtl/forge/`, each row recording its commit; dirty bundles refused, a re-label needs a byte-for-byte rebundle diff.
- **Why:** trace to the RTL without changing snax-forge.
- **Where:** `TOOL.md`; `results/forge/runs/2026-10-31_syn1_r1b.md`.

### X22 — Forge synthesis

- **Decided:** `<tag>_shell_wrapper` with hierarchy kept (`-no_autoungroup`), boundary optimization on; rows add `csr_um2`, `ctrl_um2`, `datapath_um2`, `glue_um2`.
- **Why:** only a kept hierarchy splits control and datapath; glue under 0.1 %.
- **Where:** `syn/README.md`, "The forge source"; `results/forge/runs/2026-10-31_syn1_r1.md`.

### X23 · X58 — Forge power, driven as LOWER

- **Decided:** bundled at n2048; `csr_seq.sv` writes LOWER's JOBS, JOB_BEATS and scalar CSRs then START, streams in streamer order; the window runs from START's edge to one cycle before done, BUSY_COUNTER beside it (X56).
- **Why:** LOWER is what the cluster runs; a per-group rule failed for untiered recipes.
- **Where:** `power.md`, "Forge"; `results/forge/runs/2026-10-31_syn1_r2.md`, `2026-11-10_csyn1_r1.md`.

### X24 — Reference task n2048

- **Decided:** one task of N = 2048 per input stream (`n2048`, 2048 / W beats) on every side; untiered relu, axpy n2048, matadd m32_n64, rowsum m16_n128.
- **Why:** comparable at every W and tool, at least 128 beats at W = 16.
- **Where:** `power.md`, "Stages".

### X38 — The HLS cases

- **Decided:** Vitis opt, Vitis dace, Bambu, Google XLS at a 10 ns HLS clock, W ≤ 16 (`MAX_W`).
- **Why:** W = 32 needs 96 interconnect ports; Vitis unopt is a known-poor baseline.
- **Where:** `syn/README.md`, "Sources"; `results/runs/2026-11-05_hsyn1_r5.md`.

### X39 — HLS sources, port guard

- **Decided:** three HLS sources with own root, cases, clock and reset; a port guard runs before DC (`syn.py check-ports`).
- **Why:** Bambu's folders were once read with Vitis's port names.
- **Where:** `syn/README.md`, "Sources".

### X42 — Cycle CSVs with provenance

- **Decided:** `pixi run import-cycles` copies the cycle CSVs byte for byte with a `SOURCE` file; untracked or modified files refused.
- **Why:** a byte copy cannot drift.
- **Where:** `TOOL.md`.

### X44 — Bambu and XLS power

- **Decided:** measured as Vitis by their own handshakes: Bambu `start_port` to `done_port`, XLS cfg transfer to last output (`cycles` + 1); one port table in `SOURCES`.
- **Why:** each handshake marks its task.
- **Where:** `power.md`, "Bambu" and "XLS"; `results/runs/2026-11-05_hsyn1_r5.md`.

### X56 — Cycles within 5 %

- **Decided:** the window is the measurement; expected cycles sit beside it, failing a point only past 5 %.
- **Why:** past 5 % means a wrong size, CSR or stimulus.
- **Where:** `sim/pwr.py` `CYCLES_TOL`.

### X57 — Untiered forge at int64

- **Decided:** relu, matadd, axpy, axpy_baked bundled at int64 through a temporary recipe's `dtypes`.
- **Why:** int32 in snax-forge, every other point int64.
- **Where:** `forge/bundles.py`; `results/forge/runs/2026-11-10_csyn1_r1.md`.

### X62 — Vitis RAM to SRAM macro

- **Decided:** each one-port Vitis RAM becomes a CACTI macro (`ram/vitis_ram.py`), else the point parks or `--with-ram` builds it from flops; counted energy (X50) in `e_ram_pj`.
- **Why:** unparks the dace points; only the memory differs.
- **Where:** `syn/README.md`, "Sources"; `results/hls/runs/2026-11-10_csyn1_r3.md`.

## Cluster

### X66 — Cluster SRAMs generated

- **Decided:** `cluster/mem.py` turns clustergen's `--memories` into one `tc_sram_impl.sv`, models and `sram_models.f`, read via `SRAM_IMPL`, `SRAM_MODELS`; per run, uncommitted.
- **Why:** one file swaps every memory; 0 Verilator mismatches against tech_cells_generic.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r2.md`.

### X67 · X81 · X84 — Cluster source and checks

- **Decided:** a snax-forge design in snax_cluster's main cluster, in `cluster rtl`, `syn`, `gls`, `pwr`; the netlist run gated on data, timing (within 10 %), swap and `[SUCCESS]`; D123 and RAMCOUNT (one extra access per instance) reported.
- **Why:** data and cycles prove the netlist; `+initreg+0` allows one time-0 access (PITFALLS Q8, Q14).
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r4.md`, `2026-11-14_cg3_r1.md`.

### X68 — Cluster constraints and budget

- **Decided:** `cluster/cluster.sdc`: reset and static ports false-pathed, I/O delay 30 % (AXI), 10 % (CSR); one cluster run alone at `--cores 16` (PT 24 where the licences allow, X109), `SYN_IGNORE_LOAD=1` (PITFALLS DC13), replacing X16 · X59 here.
- **Why:** a cluster sits in a SoC; cluster runs are few.
- **Where:** `cluster/README.md`.

### X72 — Cluster area in groups

- **Decided:** `cluster/groups.json` path rules; a node's area goes to its first matching group, else its parent's; `cluster-breakdown` compares with HWCOST's five parts.
- **Why:** nothing lost or counted twice.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r3b.md`.

### X73 — Cluster windows and span

- **Decided:** the quiet program writes CSR `0x7c5` (port `obs_o`) per section; windows between marks, idle ones too; the span from the first mark to the check's.
- **Why:** marks from the netlist run; on `dot3_w16` they equal the RTL cycles.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-12_pwr1_r1.md`.

### X75 — Cluster macros as measured

- **Decided:** a cluster's macros as averaged PT measures them (PT7's bias noted), no counts.
- **Why:** comparing measured with HWCOST's counts is the point (banks within 1 % on `dot3_w16`).
- **Where:** `cluster/README.md`.

### X78 · X80 · X86 — Cluster sweep over W

- **Decided:** `cluster-sweep` writes `sweep.csv` (long form) and four figures (energy and area, all parts and five parts), stacking memory, control, streamers, crossbar, datapath, then not-priced; `--points --out` for a look. Raw data only.
- **Why:** read by hand (Ryan, 12 Nov); what changes least at the bottom (Ryan, 15 Nov).
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-13_pwr2_r2.md`, `2026-11-15_cg3_r4.md`.

### X91 — Snitch-only clusters

- **Decided:** `snax_snitch_cluster_{1,5,9}` through `cluster/snb.py`: one gated netlist a config, runs `<config>_<kernel>_<type>` gated on `[SUCCESS]` and `snitch-forge errors: 0`, not D123, RAMCOUNT or 10 %; E11: four area parts, $C_\text{run}$ from the RTL run, energy on $C_w$.
- **Why:** no SNAX-GVSoC model; R7's 26 netlist runs equalled the RTL to the cycle.
- **Where:** `cluster/README.md`, "snb"; `results/snb/runs/2026-11-16_snb1_r7.md`, `2026-11-17_snb1_r6.md`.

### X92 — E11 energy dynamic only

- **Decided:** $E_\text{run}$ and $\eta_E$ from `e_win_pj`; $E_\text{leak} = P_\text{leak}\thinspace C_w\thinspace t_\text{clk}$ reported beside, never added.
- **Why:** Snitch runs take 50 to 200 times forge's cycles; leakage would swamp the work.
- **Where:** `cluster/README.md`, "snb"; `report/snb_report.py`.

### X95 — A copy's energy against D184

- **Decided:** D182's transposed copy runs as `dma_transpose` on `snitch1_cg` at 64 × 64, int8 and int64, its window summed by group against D184's price; `e11: false`.
- **Why:** D184 is a lower bound; no synthesis needed; int8 vs int64 tests burst cost.
- **Where:** `cluster/README.md`, "snb"; `report/dma_copy.py`.

### X96 — A burst touches a superbank

- **Decided:** banks also read against the SAIF's counts: each burst reads and writes 8 banks (a 64-byte superbank), 32 768 reads and writes for 4096 bursts; D184's banks are 327.87 nJ counted, PT's 251.0 nJ (23.4 % under; PITFALLS PT7, PT11).
- **Why:** the accesses are 8 times D184's, so a byte burst costs what a word does.
- **Where:** `results/snb/runs/2026-11-19_tiera1_r7g.md`; `results/snb/nangate45/dma_copy.json`.

### X102 — The DMA engine per burst

- **Decided:** a copy's engine (the iDMA, its AXI-to-memory, the wide AXI path) costs `e_burst_pj` per burst on top of D184's L1 accesses: the `dma` and `axi` groups' energy in the copy's run window less their floor with the DMA idle (`dot3_w8_cg`'s run window), per burst, the mean of the int8 and int64 copies: 106.40 pJ (`dma_copy.json`'s `engine`).
- **Why:** X95's copy cost 3× D184; the engine is about 106 pJ a burst, the rest is paid every cycle whatever runs (X103).
- **Where:** `report/dma_copy.py`; `cost_tables.md`, "The DMA engine"; `results/runs/2026-11-26_cost2_r1c.md`. Amended by X113.

### X103 — The cluster's fixed parts

- **Decided:** `cluster_fixed.json` holds, per group HWCOST leaves out but the banks, its area, its PrimePower leakage in `dot3_w8_cg`'s run window (the I-cache macros from the lstp table) and its idle floor in that window, summed into three parts: core, DMA, rest. The TCDM bank logic has no floor: it moves with L1 traffic.
- **Why:** snax-forge's area parts and the energy run's cluster line need what every design pays (6.27 mW of leakage and 23.6 pJ a cycle at W = 8); one point stands for all, the floor moving by about 1 pJ a cycle over W = 2–32 (CG3). CSYN2's per-instance reports can replace the point.
- **Where:** `report/cluster_fixed.py`; `cost_tables.md`, "The cluster's fixed parts"; `results/runs/2026-11-26_cost2_r1c.md`.

### X104 — A point's sets are its forge command

- **Decided:** `pixi run forge` takes the point's `sets` and nothing else; `W` is the point's label. The dot points carry `W=<W>` as their first set, so their command and bundles are unchanged.
- **Why:** tier A's recipes name their lanes `W_x1` or take W from a default, and their sets are `paper/`'s rows copied verbatim.
- **Where:** `cluster/cluster.py` (`bundle_command`); `cluster/README.md`.

### X105 — One netlist per hardware

- **Decided:** a point with `netlist_of` adopts its twin's netlist when the twin's syn run has one and the two bundles' hardware (`bundle/snax_forge.hjson` without its comment lines, `bundle/rtl/` with `emitted.json`'s `rtl` path left out, both naming forge's output folder) is byte-equal: no DC, `syn/adopted.json` in its run zip, and `gls` and `pwr` run its own ELF on the twin's netlist. When the hardware differs it is synthesized on its own.
- **Why:** a schedule or a layout changes the program, not the cluster; DC is most of a point's time.
- **Where:** `cluster/cluster.py` (`adopt`, `netlist_point`), `cluster/check.py` (`hardware_diff`).

### X106 — Dynamic and leakage per group, apart

- **Decided:** `cluster-energy` records each group's leakage per window (µW, and nJ over the window) beside its dynamic energy, never summed into it; `groups.json` maps the groups to snax-forge's eight parts (core, DMA, datapath, control, streamers, crossbar, memory, rest; `acc_csr`, `acc_interface` and `tcdm_logic` in rest). Amends X13 for the reports only.
- **Why:** §D compares dynamic alone and dynamic with leakage; the sum is made where it is read.
- **Where:** `report/cluster_energy.py`, `cluster/groups.json`, `report/tier_check.py`.

### X107 — The lstp macros only

- **Decided:** before DC and before PT the three macros' `.db` are checked against COST2 R1b's sha256 (`check.LSTP_DB_SHA256`); a mismatch stops the step; the checksums go into `tech.json` and `pt_check.json`.
- **Why:** every cluster netlist before CSYN2 linked the hp macros; the two kinds differ only in their numbers.
- **Where:** `cluster/check.py` (`db_check`); `results/ram/runs/2026-11-26_cost2_r1b.md`.

### X108 — The programs checked before DC

- **Decided:** the `rtl` step also runs the quiet ELF on the RTL with the macros (`obs_o` logged, no VCD) and the point's energy run on SNAX-GVSoC (`flow --energy`, kept as `ge/<point>.json`). Its gates are the data line of both default runs and `[SUCCESS]` with no output in all three; D123 and the quiet windows are recorded, never gates: within 10 % OK, within 20 % WARNING, beyond INVESTIGATE, a window of at most 20 cycles SMALL (its gap in cycles). `pwr` checks the netlist's windows against the point's own quiet RTL run. Amends X67 · X81 · X84 for the `rtl` step.
- **Why:** a wrong program is found before a night of DC; the RTL's timing is the truth, the model's gap is investigated, not gated (Ryan, 26 Nov).
- **Where:** `cluster/cluster.py` (`gvsoc_energy`, `quiet_rtl`, `quiet_windows`), `cluster/check.py` (`data_ok`, `quiet_compare`).

### X109 — One run at a time, more cores

- **Decided:** `cluster/batch.sh` takes `CORES` (PT's threads, 24 where the licences allow, else 16; DC's cores, capped at 16, as DC refuses more and then runs on one core), `--steps`, and `KEEP_GOING=1` (a failed step skips the rest of its point, the batch goes on); still one DC, Questa or PT run at a time.
- **Why:** parallel cluster runs would share snax_cluster's generated folders and the Scala caches; more cores per run is safe.
- **Where:** `cluster/batch.sh`.

### X110 — Untracked files do not make a checkout dirty

- **Decided:** the cluster driver's clean check on snax-forge and snax_cluster ignores untracked files (`git status --untracked-files=no`), as forge's bundle `dirty` flag does; a tracked change still refuses the run.
- **Why:** the editor's Save writes Ryan's own recipes into `recipes/custom/`; they change no bundle.
- **Where:** `cluster/cluster.py` (`check_repos`).

### X111 — A refused request's price

- **Decided:** a refused request costs $r$ of a granted one per part, fitted on `mvt_contiguous_w8_cg` against `mvt_padded_w8_cg` (one netlist, equal grants, 23 637 more refusals): the netlist's difference less the fitted floor (X112) over the 2 729 extra cycles, over SNAX-GVSoC's difference at the granted price: $r_{strm}$ = 0.085, $r_{xbar}$ = 0 (−0.026, clamped); the banks pay nothing (−0.33 nJ). Checked on `bicg_pipeline_contiguous_w8_cg` against its sequential twin: streamers and crossbar −2.37 nJ at the netlist, −1.89 in the model.
- **Why:** pricing a refusal as a grant made SNAX-GVSoC's contiguous mvt 32 % above its padded twin against the netlist's 10 %; the stall cycles' cost is the floor's.
- **Where:** `report/model_fit.py`; `cost_tables.md`, "The model's gate-level terms"; `results/cluster/runs/2026-11-27_cost3_r1.md`.

### X112 — The idle floor and the L2 ↔ L1 transfers

- **Decided:** the floor per cycle of the parts that stay clocked, from the configuration window (accelerators and DMA idle) of the five `dot3_w*_cg` points: the streamers 0.126 pJ a mover or channel (least squares through 0), the crossbar 1.424 + 0.0574 pJ an input (least squares), the DMA 3.378 pJ. A transfer beat (a DMA access to a superbank of 8 banks) costs the `dma` group's energy in the points' `dma_in` and `dma_out` windows less the DMA's floor, per beat: $e_{l2}$ = 54.48 pJ (54.47–54.49 on the five). The banks there cost 4.17 pJ an access, a candidate for the DMA's bank accesses beside CACTI's 3.39 and 6.45 (`e_bank_dma_pj`).
- **Why:** the configuration window is the one every point has with nothing moving; counts the estimate knows exactly beat areas, the streamers' estimated area being 6–35 % under DC's on tier A. Held out on tier A: the floor within −17 to +6 % (streamers), −5 to +22 % (crossbar), −2 to +4 % (DMA); $e_{l2}$ 54.3–59.7 pJ.
- **Where:** `report/model_fit.py`; `cost_tables.md`, "The model's gate-level terms"; `results/cluster/runs/2026-11-27_cost3_r1.md`.

### X113 — The DMA engine per burst, the DMA alone

- **Decided:** `e_burst_pj` is the `dma` group alone, less its floor in `dot3_w8_cg`'s configuration window (3.37 pJ a cycle, X112's), per burst, the mean of X102's two copies: 78.08 pJ (76.18 at int8, 79.99 at int64). A copy's beat takes no crossbar access: the copies' crossbar sits at its floor (−0.06 and 1.11 pJ a burst above it, against D184's 3.29). Amends X102.
- **Why:** the netlist books the AXI in the rest, so X102's 106.40 pJ put the AXI's share in the DMA part and the copies at 1.22 of the netlist's DMA; the DMA reaches the banks through its own superbank port.
- **Where:** `report/dma_copy.py`, `report/model_fit.py`; `cost_tables.md`, "The DMA engine"; `results/cluster/runs/2026-11-27_cost3_r1.md`.

## Reports and comparison

### X45 · X55 · X61 — Comparison CSVs

- **Decided:** `pixi run compare` writes `compare_done.csv` and `compare_untiered.csv` from committed gated rows only (no ratios), untiered parts from n2048, forge by design name (PITFALLS E5); nothing written on a gap, failure, repeat or split mismatch.
- **Why:** every comparison reads the same raw rows.
- **Where:** `TOOL.md`; `report/compare.py`; `results/runs/2026-11-16_cg5_r3.md`.

### X63 · X65 — Parts at n2048, total without csr

- **Decided:** kernel pages list n2048 parts; forge's total without csr (ctrl + datapath + glue) is the like-for-like figure; `<tag>_peripherals` (D168) stays in the CSVs only.
- **Why:** HLS has no CSR file; a part's energy comes from its own run.
- **Where:** `results/compare/README.md`; `results/forge/runs/2026-11-11_ctrl2_r5.md`.

### X64 · X46 — One page per kernel

- **Decided:** `compare-hls` writes `results/compare/` (replacing X46's single file): a README and per kernel a page and figure, generated parts between `<!-- gen:NAME -->` markers.
- **Why:** the one file passed 1,000 lines.
- **Where:** `results/compare/README.md`.

### X77 — forge's ctrl and datapath figure

- **Decided:** `<tier>/<kernel>_ctrl_dp.png`: forge's ctrl + datapath against HLS totals.
- **Why:** closest to an HLS block; differs from X63's figure only by glue (at most 1.1 µm²).
- **Where:** `results/compare/README.md`.

## Retired

### X26 · X27 · X35 · X43 — Retired, no successor

- **Decided:** X26, X27, X43 (SYN1's and SYN2's analysis code and local runs) and X35 (a limit of the ungated LinkBuffer table) are deleted, never reused.
- **Why:** their code, runs and table are gone (X79 · X87 · X88).
- **Where:** git history; the run notes citing them.
