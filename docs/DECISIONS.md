# Decisions

What this repository has settled: one entry per live choice, in its current form. How a flow runs is in [`TOOL.md`](TOOL.md), the folder READMEs and [`power.md`](power.md); what the tables mean is in [`cost_tables.md`](cost_tables.md); tool behaviour that bites is in [`PITFALLS.md`](PITFALLS.md).

Rules:

- An entry is a choice someone may want to reverse. It says what was decided, why, and where the detail lives, in a few short bullets. A change is written into the entry, not chained after it.
- Entries merged into one keep all their numbers in its heading, so a cite of any of them still finds it. A number is never changed or reused; the text of a removed entry is in git history.
- A new decision gets the next free number, under the area it belongs to, and names the run note that found it. Next free number: **X94**.

Numbers retired, never reused: X10 (PT's setup check with pass tolerances, now X25's diagnostic), X26, X27 and X43 (SYN1's and SYN2's analysis code and local runs, deleted), X36 (a draft block table, now X37), X46 (one comparison file, now X64), X35 (the LinkBuffer stream cheaper per flop than a held flop, a limit of the ungated table, gone with it).

## Environment and runs

### X6 — Run folders are kept

- **Decided:** the mapped netlists in `syn/runs/` and the power runs in `sim/runs/` are kept; a clean never deletes them, and a rerun replaces only its own points.
- **Why:** power reads DC's netlist with no resynthesis (X7), and a resynthesis can differ (PITFALLS DC3).
- **Where:** `CLAUDE.md`, "Working rules".

### X15 — Python from pixi

- **Decided:** Python comes from the repository's pixi workspace (Python 3.11), `pixi run ...`, never the host's `python3`; scripts live in files.
- **Why:** the server's `python3` is 3.6; one locked environment everywhere.
- **Where:** `pixi.toml`; `docs/README.md`, "Environment".

### X16 · X59 — Parallel jobs from free licences, at most 16 cores

- **Decided:** free licences are counted with `lmutil lmstat` before a batch and size the parallel jobs; PT threads are cores // jobs. A round uses at most 16 cores, or up to 24 on Ryan's word that the host is quiet (at least 8 left free), and never every free licence: DC `-j 4 --cores 4` (`-j 6` at 24 cores), power `--cores 16 -j 4`, one batch at a time. Cluster runs have their own budget (X68).
- **Why:** the host and licences are shared; a job without a licence fails or waits, and a multicore DC run can hold several DC-Expert licences (PITFALLS L4).
- **Where:** `TOOL.md`, section 1; `results/forge/runs/2026-11-10_csyn1_r1.md`.

### X17 — Licence errors are retried once

- **Decided:** a tool that fails on a licence error is retried once; a second failure is reported.
- **Why:** error -92 was transient (PITFALLS L1).
- **Where:** `syn/syn.py` `run_dc`, `sim/pwr.py`, `cluster/power.py`.

### X51 — Outputs zipped one per point

- **Decided:** every point's bulky outputs are one deterministic zip, read and written through `arc/arc.py`; a tool that needs files gets one point unpacked into `tmp/` at a time. `pixi run arc check` reports nothing left over at the end of a round.
- **Why:** Ryan's home has a file-count quota shared by every repository; loose run outputs took about 116,000 inodes, the zips about 2,500.
- **Where:** `CLAUDE.md`, "Files are zipped"; `results/runs/2026-11-06_arc1_r1.md`.

## Libraries and synthesis

### X1 — Nangate 45 nm

- **Decided:** synthesis runs on the Nangate 45 nm Open Cell Library (typical, 1.10 V, 25 °C), named per run with `--tech nangate45`. The 15 nm library and its rows were removed (X88).
- **Why:** an open library with memories from CACTI at the same node (X47); OSU gscl45nm, used before 28 Oct, has 31 cells and broken pin limits.
- **Where:** `syn/tech/nangate45.json`; `results/hls/runs/2026-10-28_step0_libs.md`.

### X2 — Clock 10 ns

- **Decided:** 10 ns on every point; `fmax_mhz` = 1000 / (`clock_ns` − `slack_ns`) is a lower bound.
- **Why:** one clock makes area and energy per cycle comparable; at 10 ns DC keeps area-optimized structures and never upsizes for speed.
- **Where:** `syn/scripts/constraints.sdc`; `results/hls/runs/2026-10-27_done.md`.

### X3 — No wire load; drive and load

- **Decided:** no wire-load model. Inputs driven by `INV_X4`, outputs loaded with four `INV_X4` inputs (25.0 fF), max transition 0.25 ns. A run whose `area.rpt` shows a wire-load model fails.
- **Why:** the library's default would change timing and power, and is not removed by `auto_wire_load_selection false` alone (PITFALLS DC1).
- **Where:** `syn/scripts/dc_syn.tcl`; `results/hls/runs/2026-10-28_syn_tech_probe.md`.

### X4 — Constraints in ns and fF, with a unit check

- **Decided:** `constraints.sdc` holds ns and fF; `syn.py` scales them to the library's units, and DC stops before reading RTL when the library's name or units differ from the tech file.
- **Why:** a library in other units takes every constraint 1000x off with no error (PITFALLS DC2).
- **Where:** `syn/README.md`, "Technologies".

### X5 — Results per technology

- **Decided:** each technology has its own `results/<source>/<tech>/`; only `KEPT_REPORTS` are committed per point.
- **Why:** areas compare only within a library; the kept reports are what the models read.
- **Where:** `syn/README.md`, "What a run leaves".

### X40 — Path-class slacks after compile

- **Decided:** after compile, `dc_syn.tcl` measures the worst slack of in2reg, reg2reg, reg2out and in2out with `get_timing_paths`, into `path_classes.rpt` and four `slack_*_ns` columns.
- **Why:** XLS's points are one combinational stage, which `fmax_mhz` alone hides.
- **Where:** `syn/README.md`, "Columns".

### X41 — A control/datapath split only where the RTL declares it

- **Decided:** area is split into control and datapath only where the hierarchy declares it: forge (X22) and Bambu (`controller_*`, `datapath_*`, glue). Vitis and XLS report totals.
- **Why:** splitting a flat netlist means guessing.
- **Where:** `syn/README.md`, "Columns".

### X69 — No SDF unless asked

- **Decided:** DC writes an SDF only with `syn.py --sdf`.
- **Why:** energy comes from a zero-delay simulation (X7); nothing reads the SDF.
- **Where:** `syn/syn.py`.

### X79 · X87 · X88 — Clock-gated synthesis is the basis

- **Decided:** `dc_syn.tcl`'s `CLK_GATE_ENABLE` (from `SYN_CLK_GATE_ENABLE`, default 0) turns on DC's clock gating for a run: `clock_gating.tcl` (stop if the library has no `latch_posedge` integrated gate; positive edge, `-minimum_bitwidth 2`, through the hierarchy, no test or negedge logic, no operand isolation), `compile_ultra -no_autoungroup -gate_clock`, and the three `clock_gating*.rpt`, kept whatever their size. `syn.py run --clk-gate` and `pwr.py run --clk-gate` tag a run `_cg` and its rows `clk_gate` 1, merged apart from ungated rows (an empty `clk_gate` reads as 0); a cluster point sets `"syn": {"clk_gate": true}` under its own name. The switch's default stays off; a point or source says `clk_gate` itself.
- **Decided:** gated synthesis is the basis: new cluster points are gated and HWCOST's block tables are the gated ones (X83). The ungated data that had a gated twin was removed: the ungated STRM rows and tables, the ungated cluster points and their sweep, and the 15 nm library (X1). The HLS points (Vitis, Bambu, XLS), the forge accelerators alone, the char blocks and the `xbar_mix` grid are gated, their ungated rows removed: every source is gated.
- **Why:** clock gating is what a real design gets. The ungated run windows were 46 to 82 % idle clocking at W ≤ 16 and overstated the cluster's energy 2 to 5 times; with the gated tables HWCOST's streamers come within −3 to −7 % (−23 to −34 % ungated), while memory and the datapath do not move. On `dot3_w8_cg` DC gates 98.6 % of the registers with `CLKGATE_X1` cells; area −6.5 %.
- **Where:** `syn/README.md`, "Clock gating"; `results/cluster/runs/2026-11-13_cg1_r1.md`, `2026-11-15_cg3_r3.md`, `2026-11-15_cg4_r1.md`; `results/runs/2026-11-15_cg6_r1.md`, `2026-11-15_cg6_r2.md`, `2026-11-16_cg5_r1.md`, `2026-11-16_cg5_r2.md`.

## Power

### X7 — Energy from simulated activity

- **Decided:** energy comes from a functional, zero-delay Questa simulation of the mapped netlist (`+nospecify +notimingchecks`, `vopt +initreg+0 +acc=n`), then PrimePower in averaged mode on the same netlist, library and constraints as DC. No resynthesis.
- **Why:** DC's default activity follows the logic structure, not the work (PITFALLS DC4); the netlist is unplaced, so zero delay gives what a per-cycle model needs.
- **Where:** `power.md`; `results/hls/runs/2026-10-29_pwr_step0.md`.

### X8 — Activity from the VCD, through vcd2saif

- **Decided:** the testbench dumps a VCD of the design's own scopes over the window, `vcd2saif` turns it into a SAIF, PT reads it with `read_saif`, and the VCD is deleted at once. Questa's own SAIF is not used.
- **Why:** Questa 2022.4's SAIF is wrong at zero delay (PITFALLS Q4); vcd2saif agrees with PT's `read_vcd` within 0.1 %.
- **Where:** `power.md`, "Stages"; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X9 — Every activity file is checked

- **Decided:** each SAIF must satisfy T0 + T1 + TX = DURATION on every driven net, with DURATION = cycles x clock period and the clock's TC = 2 x cycles; after PT at least 99 % of the nets are annotated (95 % of the driven nets on a whole cluster). A failed check fails the point.
- **Why:** annotation coverage alone passed a defective SAIF.
- **Where:** `sim/pwr.py` `saif_check`; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X11 — Flop energy is clock plus register

- **Decided:** flop energy is always e_clk + e_reg, never one group alone.
- **Why:** PT books a flop's clock-edge energy under register when its output toggles and under clock when it does not (PITFALLS PT3).
- **Where:** `power.md`, "Energy quantities".

### X12 — Vitis's cycles and window

- **Decided:** a Vitis run's cycles count the rising edges from the first that samples `ap_start` = 1 to the first that samples `ap_done` = 1; the window runs between the falling edges before those two. Bambu, XLS, forge and the cluster have their own windows (X23, X44, X73).
- **Why:** the count equals cosim's latency with no offset, and falling-edge bounds hold exactly the rising edges inside.
- **Where:** `power.md`, "Stages".

### X13 — Dynamic energy of the busy window

- **Decided:** the power flow reports the busy window's dynamic energy, per cycle as E_comb and E_flop = E_clk + E_reg + E_seq; energy per task is (E_comb + E_flop) x cycles. No leakage (it stays in `synth_dc.csv`); idle windows only for the blocks alone (X31) and the cluster (X73).
- **Why:** snax-forge's models annotate only dynamic activity per active cycle.
- **Where:** `power.md`, "Energy quantities".

### X18 — No dumps kept

- **Decided:** no VCD, WLF or compiled design is kept; the VCD goes right after vcd2saif. A point's zip keeps `tb.json`, the SAIF and PT's reports.
- **Why:** a VCD grows with nets x cycles and its SAIF replaces it; the rest rebuilds in seconds.
- **Where:** `power.md`, "Run folder".

### X19 — rand64 stimulus

- **Decided:** the default stimulus is rand64: full-range int64 from NumPy's `default_rng(0)`, stream by stream in `tb.json` order, then the data pins; the default HLS task is 64 beats (`b64`), and every input bit must toggle at least once. Expected cycles come from cosim's line a x loop_count + b through its two sizes.
- **Why:** full-range data toggles every bit, so energy does not depend on how narrow the test values are.
- **Where:** `power.md`, "Stages"; `results/hls/runs/2026-10-29_pwr_r1.md`.

### X90 — A narrow forge point: rand64 at the element's dtype, in packed words

- **Decided:** a forge point at a narrow type preset (`types=i8` or `i16` in its sets) draws each input container full-range at its element dtype (int8, int16) with X19's generator and seed, wraps the reference's outputs to the output dtype (int32, as snax-forge's ACC), and moves num_slc = 64 / bits elements a 64-bit word, little-endian (snax-forge D142); a packed output (D174, `d_out` > 1) is checked as a whole word, the slices past the last result 0. The reference check runs snax-forge's kernel body at the design point's dtypes and type parameters (`forge/query.py point`).
- **Why:** full range at the element's width toggles every bit of every word, as rand64 does at int64; int64 values in an int8 port would be cut by the streamer, and the kernel's wrap at int32 is what the hardware computes.
- **Where:** `power.md`, "Forge"; `results/runs/2026-11-16_char2_r7.md`.

### X20 · X60 · X74 — Power results

- **Decided:** `power_pt.csv` has one row per point, size and seed with the per-cycle and per-task energies; `power_pt_modules.csv` has one row per hierarchical cell, keyed by point and size, holding each point's default run and its n2048 run. A cluster point's `power_pt.csv` has one row per window, adding `e_macro_pj`, `e_io_pj` and `e_win_pj`. The checks fail a point but are not columns; tool versions go in the run note.
- **Decided:** a whole cluster is measured by `pixi run cluster pwr <point>`: one netlist run dumps one VCD, one pass cuts it into the windows' SAIFs, one PT session in averaged mode reports each window.
- **Why:** the cost model needs energy per cycle and per firing, split into combinational and flop; the parts at n2048 need that run's modules without moving the default run; one VCD and one PT session keep a cluster run to minutes, and averaged mode matches the library's clock-pin energy where time-based mode halves it (PITFALLS PT10).
- **Where:** `power.md`, "Energy quantities" and "What is committed"; `cluster/README.md`; `results/cluster/runs/2026-11-12_pwr1_r2.md`.

### X25 — PT is the reference; the setup check is a diagnostic

- **Decided:** PT with simulated activity is the reference for energy; DC's power is an early check. `pwr setup-check` (PT against DC on one netlist with the same forced activity) prints its per-group differences for the run note and never fails a point; the wire-load and SAIF checks stay gates.
- **Why:** the two tools agree within 0.02 % on nangate45 and differ around enable logic by how they propagate default activity (PITFALLS PT2).
- **Where:** `power.md`, "Commands"; `TOOL.md`.

### X76 — tb_bin's 1 ns clock read as 10 ns

- **Decided:** snax_cluster's testbench clocks at 1 ns; each cut VCD's header gets `$timescale 10ps` for `1ps`, so the run reads as 10 ns and X9's checks and PT's clock hold unchanged.
- **Why:** a zero-delay run's activity and energy per toggle do not depend on the period.
- **Where:** `sim/pwr.py` `vcd_windows`; `results/cluster/runs/2026-11-12_pwr1_r1.md`.

## Memory

### X47 — SRAM area and energy from CACTI 7 at 45 nm

- **Decided:** SRAM banks (one read-write port, no ECC) are costed with CACTI 7 (commit `1ffd8df`, `pixi run ram-build`) at 45 nm, itrs-hp, the objective weighted to dynamic energy and area; dynamic energies scaled from 1.0 V to 1.10 V by 1.21.
- **Why:** OpenRAM's analytical model gives one power for read, write and idle and an area only with layout; CACTI gives read and write energy and area in 0.2 s, close to published 45 nm figures.
- **Where:** `ram/README.md`; `results/ram/runs/2026-11-05_ram1_r1.md`.

### X48 — The SRAM table is a lookup

- **Decided:** `results/ram/nangate45/ram_table.csv` holds every depth 32–4096 (step 32) and width 8–256 (step 8), 4,095 rows; never interpolated or fitted, a size off the grid is the reader's choice.
- **Why:** CACTI's numbers jump up to 30 % between neighbouring sizes (PITFALLS C5); the best fit still misses by 6 % on average.
- **Where:** `cost_tables.md`, "SRAM banks".

### X49 — SRAM macros generated from CACTI's numbers

- **Decided:** DC, Questa and PT see each SRAM as a macro written by `pixi run ram lib`: a Liberty model (area, read and write energy on the rising edge when selected, pins borrowed from Nangate's `DFF_X1` and `BUF_X4`) and a behavioural Verilog model with `tc_sram_impl`'s ports that counts accesses (`RAMCOUNT`). Never committed.
- **Why:** CACTI gives no Liberty; generated from the table's own numbers, the macro adds no second energy model.
- **Where:** `ram/README.md`.

### X50 — A point's memory energy is counted accesses times the table

- **Decided:** a single point with SRAM macros reports their energy as counted reads and writes x the macro's table energies, plus PT's energy of everything else. Cluster points take the macros as PT measures them (X75).
- **Why:** averaged PT charges a macro's energy with independent pin probabilities, 12.5 % low on the probe (PITFALLS PT7); the counters are exact.
- **Where:** `cost_tables.md`, "SRAM banks".

## Cost tables

### X28 — The char source

- **Decided:** `char/points.json` lists one catalogue datapath per point; `pixi run char-rtl` runs snax-forge's `gen-block` into `rtl/char/`, recording the commit; a dirty checkout is refused first.
- **Why:** a result must trace to exactly the RTL synthesized, as X21.
- **Where:** `TOOL.md`; `results/char/README.md`.

### X29 — The block grid

- **Decided:** 27 points at int64: SimdLanes add and mul at W = 1, 8, 32; the accumulating Mac at W = 1, 8, 32; TreeAccumulate at W = 1–32; SerialAccumulate at W = 2–32; LinkBuffer at D = 1–16 (W = 1) and D = 1 at W = 8, 32. Beside them the type axis's points (X89).
- **Why:** the blocks and forms forge's accelerators use, enough points for a first-order model.
- **Where:** `char/points.json`.

### X30 — A block alone

- **Decided:** `syn.py --source char` synthesizes the block itself as top (clock `clock`, asynchronous active-high `reset`) with X22's settings, into `results/char/<tech>/char_synth.csv`.
- **Why:** a block alone equals the same module inside an accelerator within 0.05 % where the accelerator drives its pins.
- **Where:** `results/char/README.md`; `results/char/runs/2026-11-03_char1_r0.md`.

### X31 — The blocks' windows

- **Decided:** a block has no CSRs, so `pwr.py --source char` drives it through fixed 128-cycle windows: `busy` (a fire every cycle) and `idle` (enable low, inputs held) for the compute blocks, `stream` (a full-rate FIFO) for LinkBuffer. Inputs change at the rising edge; each window follows a lead-in of its own kind.
- **Why:** a block model needs busy and idle apart, and falling-edge inputs doubled the transitions in a zero-delay run (TreeAccumulate 1.36x).
- **Where:** `power.md`, "Char"; `results/char/runs/2026-11-03_char1_r2.md`.

### X32 — The VCD cut per window

- **Decided:** `sim/pwr.py` cuts the VCD into one file per window (`vcd_windows`) and runs vcd2saif on each cut, never on the shared VCD. Used by char, streamer, xbar and the cluster.
- **Why:** on a shared VCD vcd2saif adds a phantom toggle before the window (PITFALLS VS1).
- **Where:** `power.md`, "Stages".

### X33 — char_power.csv and e_hold

- **Decided:** `char_power.csv` has one row per point and window with the per-cycle energies. e_hold is the mean idle energy per sequential cell of the registered blocks (0.0655 fJ, gated, X83). A LinkBuffer that is not loading costs its flops x e_hold. A clock-gated run's spread is reported, not checked (X82).
- **Why:** a held register costs its clock gate's share in every block, so the 14 points spread only with the bits behind each gate (X83).
- **Where:** `results/char/README.md`.

### X34 — busy_t1 and duty50 dropped

- **Decided:** the model has busy and idle (stream for LinkBuffer). Known limit: an isolated fire of an accumulator costs 25 to 30 % more than a back-to-back one.
- **Why:** `busy_t1` was within 5 % of busy, and `duty50` is a check, not a window the model uses.
- **Where:** `results/char/char_table.md`, "Known limits".

### X37 — char.json, the block model snax-forge reads

- **Decided:** `pixi run char-export` writes `results/char/<tech>/char.json` from the clock-gated rows: the flop constants (area, e_load, e_hold, per sequential cell, X83, from the int64 points), control's counter factor, and per block and type pair its comb area and comb energy per fire, with a rule for other lane counts (`copy`, `interpolate`, or a narrow fold's `slope`, X89). The counter factor is the mean, over the tier-done forge points with a power row, of `ctrl/ctrl`'s energy per cycle over its sequential cells (`seq_um2` / `flop.area_um2`, rounded) times e_hold: the 48 int64 points (forge/points.json's tier-done points without a `types=` set).
- **Why:** a model snax-forge evaluates from a block's params and a task's fires and cycles, with a few constants; on the gated rows it lands within 0.997 to 1.035 of the forge accelerators' kernels at W = 8 and 32 (0.99 to 1.04 ungated); on the narrow ones (int8 and int16 in) at 0.92 to 1.40 in energy, 0.99 to 1.12 in area (X89).
- **Where:** `results/char/README.md`, "The block model"; `results/runs/2026-11-16_cg5_r2.md`, `2026-11-16_char2_r7.md`.

### X89 — The type axis: each pair at one lane count, one rule over lanes

- **Decided:** every compute block is measured at its 10 width pairs (w_in, w_out in 8, 16, 32, 64, w_out ≥ w_in, the op at w_out) at one lane count W0: SimdLanes add and mul at W0 = 1, the accumulating Mac, TreeAccumulate and SerialAccumulate at W0 = 8; each input port is driven at its own width with rand64's low bits, outputs checked at theirs against D175's arithmetic; FifoPacker (one lane in, one word out) at int32, int16, int8 with busy (a push every cycle) and idle windows. Over lanes a block is its pair's point plus a cost per lane: the point per lane for the lane-copy blocks (`copy`), and for a narrow fold the int64 cost per lane between W = 8 and 32 times w_in / 64 (`slope`). A narrow LinkBuffer is the int64 one times w / 64. The flop constants stay the int64 points'.
- **Why:** DC removes the logic on copied sign bits, so a block's comb follows the bits it computes (an add about w_in, a multiply about w_in x min(2 w_in, w_out)) in a way that differs per block: scaling the other blocks by SimdLanes' ratios missed by up to 2x, while each block's own pairs need about 20 minutes of DC. A fold's lane is a leaf or a mux input at w_in while its accumulator stays at w_out, which the int64 shape over lanes does not carry (0.67 to 0.78 of the measured area at W = 32): the slope rule lands within 1 to 5 % on area and 2 to 32 % on energy (SerialAccumulate's, on 0.4 pJ a fire).
- **Where:** `results/char/char_table.md`, "The type axis"; `power.md`, "Char"; `results/char/runs/2026-11-16_char2_r2.md`, `_r4.md`.

### X52 · X82 — The streamer reader and the sparse interconnect, characterized

- **Decided:** snax_cluster's streamer reader (`strm__C0_Reader`) and its TCDM sparse interconnect are synthesized and powered over their parameters, totals only: readers over depth {2, 4, 8, 16} x loops 1–7 x channels {1, 2, 4, 6, 8, 16} (168), the interconnect over inputs 4–64 x banks {16, 32, 64} (27, energy only where inputs ≤ banks). A writer is priced as a reader.
- **Decided:** a characterization row (`streamer`, `xbar`, `xbar_mix`, `char`) fails only when it has no data: a tool or licence error, an empty report, no power run, a data mismatch. `syn.py`'s flop check (`seq_cells` against `rtl_flop_bits`) and `xbar_mix`'s count are printed and the row stays `ok`; window cycles, `clock_gating.rpt`'s counts and the e_hold spread go into the run note.
- **Why:** the cost model needs these costs by their design parameters, and the full-rate stimuli are the cases it scales from; a gated run counts its integrated gates as sequential cells, and these numbers are read, not gated (Ryan, 13 Nov).
- **Where:** `cost_tables.md`; `power.md`, "Streamer and interconnect"; `results/strm/runs/2026-11-06_strm1_r1.md`, `2026-11-13_cg2_r3.md`.

### X53 · X54 — The STRM tables and their interpolation

- **Decided:** `pixi run strm-table` writes `results/strm/<tech>/streamer.csv` and `xbar.csv`. A reader interpolates linearly along one axis at a time between the two grid values around the query, a grid value exact; the interconnect's energy per access is linear in 1/inputs along the inputs axis, every other field linear in the raw values; above inputs = banks the energy takes the value at inputs = banks.
- **Why:** area and energy are close to multilinear in the parameters; at fixed banks the energy per access is a + b/n (a per-cycle part shared by n grants), which 1/inputs reproduces exactly (leave-one-out error 2.5 % mean against 9.0 % linear in inputs).
- **Where:** `cost_tables.md`, "Reading a table"; `results/strm/runs/2026-11-06_strm1_r2.md`.

### X70 — The interconnect with read-only and write-only inputs (xbar_mix)

- **Decided:** the `xbar_mix` source synthesizes the interconnect with some inputs tied as the cluster ties them (a reader's channel read-only, a writer's write-only) plus the cluster template's ties: inputs {16, 32, 64} x banks {16, 32, 64}, each all read-write, all read-only and all write-only, plus two 36-input points; the 18 with $n \le b$ powered by input kind (X93).
- **Why:** HWCOST priced the cluster's interconnect at +74 % with every input read-write; DC removes what the constants make dead.
- **Where:** `syn/README.md`, "The xbar_mix source"; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`; clock-gated in `results/runs/2026-11-16_cg5_r1.md`.

### X71 — The read-only and write-only inputs in the cost: factor form, crosspoint form as an option

- **Decided:** `pixi run xbar-kinds` writes `results/strm/<tech>/xbar_kinds.json` with two forms of the interconnect's area: the factor form (default), `xbar.csv`'s area times $1 - f_{ro}\thinspace n_{ro}/n - f_{wo}\thinspace n_{wo}/n$, and the crosspoint form (an option), a least-squares cost per crosspoint of each kind. The energy by kind is X93's.
- **Why:** the factor form keeps `xbar.csv` as the source and adds two numbers; fitted on the clock-gated grid, on the one-core gated cluster it lands at +10.5 % (crosspoint +7.6 %), within HWCOST's 30 % target.
- **Where:** `cost_tables.md`, "Read-only and write-only inputs"; `results/xbar_mix/runs/2026-11-11_csyn1_r3d.md`, `results/runs/2026-11-16_cg5_r2.md`.

### X93 — The interconnect's energy by input kind, one factor pair per bank count

- **Decided:** the `xbar_mix` points with $n \le b$ (18) are powered with the xbar stimulus by input kind (`--source xbar_mix`): a read-only input reads, a write-only one writes, at the xbar stimulus's banks, rows and random data. `pixi run xbar-kinds` adds the energy's factor form to `xbar_kinds.json`: $e_k(b) = e_{access}(b, b)\thinspace(1 - g_k(b))$, $g_k(b)$ the saving of an all-kind-k point against the all-read-write one at $n = b$, linear in $b$ between 16, 32 and 64. A read-write input keeps $e_{access}$. Amends X70 (no longer area only), X71 and X54 (the price read at $(b, b)$, now by kind).
- **Why:** `xbar.csv` priced every request as a read-write one, while a cluster's inputs are mostly streamer channels of one kind; the dot 3 cluster paid 0.67 to 0.81 of it. One constant per kind does not fit (the saving moves with banks per input), and the price is read at $(b, b)$ already. With the factors the cluster's interconnect is 0.94 to 0.99 at W ≤ 8.
- **Where:** `cost_tables.md`, "The energy by input kind" and Example 7; `results/xbar_mix/runs/2026-11-17_ge1_r4.md`, `results/xbar_mix/runs/2026-11-17_ge1_r5.md`.

### X83 · X85 — The clock-gated block tables

- **Decided:** the cost tables are made from the `clk_gate` 1 rows: `streamer.csv`, `xbar.csv`, `xbar_kinds.json` and `char.json` (X37), all read with X53's rules. An integrated clock gate is a sequential cell: `flops` is `seq_cells`, `flop.area_um2` the mean of `seq_area / seq_cells`, e_load, e_hold and control's cells per sequential cell; the gate is not priced on its own.
- **Decided:** a query beyond a table's grid continues the line through the axis's two outermost grid values, clamped at 0, as snax-forge's estimate does (`strm_table.Table.at(..., extrapolate=True)`); without it a query outside the grid is refused. snax-forge imports these tables and prices the gated cluster points itself (`pixi run cluster-hwcost`).
- **Why:** a gated cluster has almost no idle clock. The per-cell constants undercount a register's bits by its gates' share (about 1/65 for 64 bits behind one gate), a first assumption (Ryan, 13 Nov). A gated register's idle energy is its gate's, about 4.9 fJ per cycle shared by the bits behind it, so the mean per cell (0.0655 fJ) spreads from 0.0024 (2,048 bits per gate) to 0.0754 fJ (64); snax-forge's estimate drops the hold term, which this makes negligible.
- **Where:** `cost_tables.md`; `results/strm/runs/2026-11-14_cg2_r4.md`, `results/cluster/runs/2026-11-14_cg3_r1.md`, `results/runs/2026-11-16_cg5_r2.md`.

## Sources

### X14 — tb.json is internal

- **Decided:** `tb.json`, the description each testbench is built from, is written by an adapter per source (`sim/sources/`) from what the producer already writes; hls-exercises, dslx-exercises and snax-forge are never changed to be measured.
- **Why:** this repository is the measuring side.
- **Where:** `power.md`, "Stages".

### X21 — The forge source

- **Decided:** `forge/points.json` lists the forge points, named like hls-exercises' (`<tier>/<kernel>/<case>_w<W>`). `pixi run forge-rtl` runs snax-forge's own tasks in the sibling checkout and zips each bundle into `rtl/forge/` (not committed). Every row records its snax-forge commit; a dirty bundle is refused; a re-label after a commit move needs a byte-for-byte rebundle diff.
- **Why:** a result must trace to exactly the RTL synthesized, without changing snax-forge.
- **Where:** `TOOL.md`; `results/forge/runs/2026-10-31_syn1_r1b.md`.

### X22 — Synthesis of a forge point

- **Decided:** a forge point synthesizes its `<tag>_shell_wrapper` with the hierarchy kept (`compile_ultra -no_autoungroup`) and boundary optimization on, otherwise as HLS; its rows add `csr_um2`, `ctrl_um2`, `datapath_um2` and `glue_um2` (the total minus the three).
- **Why:** the comparison needs control and datapath apart, and only a kept hierarchy gives them; the glue stays under 0.1 % of the total.
- **Where:** `syn/README.md`, "The forge source"; `results/forge/runs/2026-10-31_syn1_r1.md`.

### X23 · X58 — Power of a forge point, driven as LOWER drives it

- **Decided:** every forge point is bundled at its n2048 shape; `sim/sources/forge.py` builds the testbench from the bundle, and `sim/tb/csr_seq.sv` writes what snax-forge's LOWER writes (JOBS, JOB_BEATS, scalar CSRs), then START, feeding each stream in its streamer's element order. The window opens before the edge that accepts START and closes one cycle before done; BUSY_COUNTER and snax-forge's expected cycles sit beside it (X56).
- **Why:** the same flow as HLS, driven as the cluster drives forge; a per-group rule did not hold for the untiered recipes, and LOWER is the program the cluster runs.
- **Where:** `power.md`, "Forge"; `results/forge/runs/2026-10-31_syn1_r2.md`, `2026-11-10_csyn1_r1.md`.

### X24 — The reference task n2048

- **Decided:** comparisons use one task of N = 2048 elements per input stream on every side (`n2048`, 2048 / W beats). The forge points have only this size; the HLS points have it beside cosim's sizes and `b64`. Untiered kernels use relu and axpy n2048, matadd m32_n64, rowsum m16_n128.
- **Why:** the same task at every W and tool makes energy per task and per element comparable, with at least 128 beats at W = 16.
- **Where:** `power.md`, "Stages".

### X38 — The HLS cases

- **Decided:** forge is compared with four HLS cases: Vitis opt, Vitis dace, Bambu and Google XLS, every tool scheduled at a 10 ns HLS clock, W ≤ 16 (`MAX_W`). `hls` names the Vitis source.
- **Why:** W = 32 overloads the interconnect (96 ports for three streams); Vitis unopt is a known-poor baseline; one clock for every tool.
- **Where:** `syn/README.md`, "Sources"; `results/runs/2026-11-05_hsyn1_r5.md`.

### X39 — The bambu and xls sources, with a port guard

- **Decided:** `syn.py` has three HLS sources, each with its root, cases, clock and reset port; before DC a port guard checks the source's clock and reset are on the top (`syn.py check-ports` runs it alone).
- **Why:** the hls source once listed Bambu's folders with Vitis's port names.
- **Where:** `syn/README.md`, "Sources".

### X42 — The cycle CSVs imported with provenance

- **Decided:** `pixi run import-cycles` copies `bambu_cycles.csv` and `xls_cycles.csv` byte for byte from their repositories with a `SOURCE` file (repo, commit, path, sha256, date); it refuses an untracked or modified file.
- **Why:** a byte copy cannot drift, and `SOURCE` names the commit.
- **Where:** `TOOL.md`.

### X44 — Power of the bambu and xls points

- **Decided:** Bambu and XLS are measured as Vitis is, each with its own handshake: Bambu's window from `start_port` to `done_port` (its `cycles_done`), XLS's from the cfg transfer to the last output transfer (its `cycles` + 1, the datapath being combinational). One port table in `syn.py`'s `SOURCES` serves synthesis and power.
- **Why:** each tool's own handshake marks its task.
- **Where:** `power.md`, "Bambu" and "XLS"; `results/runs/2026-11-05_hsyn1_r5.md`.

### X56 — Cycles checked within 5 %

- **Decided:** each tool's start-to-done window is the measurement; the expected cycles (forge's BUSY_COUNTER and snax-forge's model, HLS's cosim line) sit beside it, and a point fails only past 5 %.
- **Why:** a few cycles of fill change the energy very little; past 5 % means a wrong size, CSR or stimulus.
- **Where:** `sim/pwr.py` `CYCLES_TOL`.

### X57 — forge's untiered points at int64

- **Decided:** forge's relu, matadd, axpy and axpy_baked are bundled at int64 through the recipe's own `dtypes` field (`forge/points.json`), written to a temporary recipe file; snax-forge is not changed.
- **Why:** those kernels are int32 in snax-forge, every other point int64.
- **Where:** `forge/bundles.py`; `results/forge/runs/2026-11-10_csyn1_r1.md`.

### X62 — A Vitis RAM swapped for an SRAM macro

- **Decided:** `syn.py` replaces each one-port RAM Vitis built by a CACTI macro of its size behind a wrapper with Vitis's ports (`ram/vitis_ram.py`); a RAM with no macro parks the point, or is built from flops with `--with-ram`. Its energy is counted (X50) into `e_ram_pj`; rows add `ram_um2` and `ram_kind`.
- **Why:** the dace points were parked for their buffers; the netlist differs from Vitis's only in the memory, read only after it is written.
- **Where:** `syn/README.md`, "Sources"; `results/hls/runs/2026-11-10_csyn1_r3.md`.

## Cluster

### X66 — The cluster's SRAM implementation, generated from its memory list

- **Decided:** a cluster's memories are the CACTI macros: `cluster/mem.py` reads clustergen's `--memories` list and writes one `tc_sram_impl.sv` with a branch per size, the macros' models and `sram_models.f`; snax_cluster reads them through `SRAM_IMPL` and `SRAM_MODELS`. Generated per run, never committed.
- **Why:** every memory of the cluster goes through `tc_sram_impl`, so one generated file swaps them all, for any configuration; checked against tech_cells_generic's model with Verilator, 0 mismatches.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r2.md`.

### X67 · X81 · X84 — The cluster source and its checks

- **Decided:** a cluster point (`cluster/points.json`) is a snax-forge design built into snax_cluster's whole cluster, from snax_cluster's main, in four steps: `pixi run cluster rtl` (the RTL run and the RTL with macros, both checked with D123), `cluster syn` (DC on snax_cluster's synthesis list, gates for unresolved references and stray black boxes), `cluster gls` (the netlist in the same testbench) and `cluster pwr` (X20 · X60 · X74).
- **Decided:** the netlist run is gated on its data (the `forge data:` line equal to the expected one and to the RTL macro run's) and its timing (cycles and each counter within 10 % of the RTL run's), the swap and `[SUCCESS]`; D123 against SNAX-GVSoC and RAMCOUNT are reported. RAMCOUNT allows at most one more read or write per instance in the netlist run, each listed.
- **Why:** this is how any snax-forge design reaches a synthesized cluster, with snax_cluster's own lists; the data and the cycles say whether a netlist is right, and under `+initreg+0` a netlist can access a memory once at the time-0 edge (PITFALLS Q8, Q14).
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r4.md`, `2026-11-14_cg3_r1.md`.

### X68 — The cluster's constraints and run budget

- **Decided:** a cluster run adds `cluster/cluster.sdc` to `constraints.sdc`: asynchronous reset and static ports false-pathed, 30 % of the clock as I/O delay on the AXI ports and 10 % on the CSR ports. One cluster DC, Questa or PT run at a time at `--cores 16`, nothing beside it, with `SYN_IGNORE_LOAD=1` (PITFALLS DC13). This replaces X16 · X59's budget for cluster runs.
- **Why:** a cluster sits in a SoC, so its boundary gets an outside budget; cluster runs are few and picked.
- **Where:** `cluster/README.md`.

### X72 — The cluster's area in groups, against HWCOST

- **Decided:** `cluster/groups.json` names the cluster's groups by path rules; each node of `area_hierarchy.rpt` adds its own area to the first group it matches, else its parent's, so the groups add up to the total. `pixi run cluster-breakdown` compares them with snax-forge's five HWCOST parts (`pixi run cluster-hwcost`) and the accelerator with its point synthesized alone.
- **Why:** path rules keep the groups exact; nothing is lost or counted twice.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-11_csyn1_r3b.md`.

### X73 — The cluster's windows and span

- **Decided:** a cluster point's power is measured on the quiet program (`forge_quiet.elf`): each program section writes the next value to CSR `0x7c5`, which reaches the top port `obs_o`. Each section is one window, between quarter cycles before consecutive marks; the span runs from the first mark to the check's mark. Idle windows are measured too. Vitis's window rule is X12.
- **Why:** the marks come from the run on the netlist itself; on `dot3_w16` the windows equal the RTL's cycles exactly.
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-12_pwr1_r1.md`.

### X75 — The macros in cluster measurements

- **Decided:** a cluster's macros (TCDM banks, I-cache) are taken as PT measures them in averaged mode, with PITFALLS PT7's bias noted; no counted accesses for cluster points.
- **Why:** a cluster measurement gives the data as measured; the counted model is HWCOST's, and comparing the two is the point (the banks within 1 % on `dot3_w16`).
- **Where:** `cluster/README.md`.

### X78 · X80 · X86 — A recipe's cluster points side by side over W

- **Decided:** `pixi run cluster-sweep [--recipe dot_3]` reads `breakdown.json` and `energy.json` for the recipe's points, one per W, and writes `results/cluster/<tech>/sweep.csv` (long form: point, W, source `gls`, `hwcost` or `alone`, window, group, metric, value) and four figures: `sweep_energy.png` and `sweep_area.png` (per W the netlist's run window and area in HWCOST's five parts plus what HWCOST does not price, beside HWCOST's five parts, absolute and in % of each side's five parts) and `sweep_energy_five.png` and `sweep_area_five.png` (the absolute panel, the five parts only). The bars stack memory, control, streamers, crossbar, datapath from the bottom, the not-priced part on top. `--points A,B,... --out NAME` lays out chosen points into `NAME/`, not committed. Raw data only: no normalization, no check on the trend.
- **Why:** the W sweep is read by hand (Ryan, 12 Nov); one file holds every number, and what changes least sits at the bottom so the change shows on top (Ryan, 15 Nov).
- **Where:** `cluster/README.md`; `results/cluster/runs/2026-11-13_pwr2_r2.md`, `2026-11-15_cg3_r4.md`.

### X91 — The Snitch-only clusters through the cluster flow, and their checks

- **Decided:** snax_cluster's `cfg/snax_snitch_cluster_{1,5,9}.hjson` (one hive, rv32ima, the logarithmic TCDM interconnect, forge's L1) go through the cluster flow with `cluster/snb.py` and `cluster/snb_points.json`: `snb syn` per config (one netlist each, clock-gated, adopted while its sha256 is the file's and snax_cluster changed no RTL), `snb rtl`, `gls` and `pwr` per run (`<config>_<kernel>_<type>`, snitch-forge's program at fixed sizes and seed 42). It reuses mem.py, syn.py (source `snb`), cluster.py's steps and swap check and power.py's do-file, cut and part 2 (its `Site`), with this cluster's wrapper and testbench instance.
- **Decided:** a run is gated on `[SUCCESS]`, `snitch-forge errors: 0` (the program checks itself against data.h's golden), its header line (kernel, type, sizes, workers), the sections' cycles and one compute line per worker; the RTL run on the macros' compile, the netlist run on the swap. Left out against X67 · X81 · X84: the plain RTL run, D123, the `[tc_sram_impl]` count, RAMCOUNT and the 10 % timing gates; the netlist's and the windows' cycles are recorded beside the RTL's. No waveform log in any run.
- **Decided:** `groups.json`'s `tcdm_interconnect` also takes the logarithmic interconnect (`gen_no_snax_tcdm_interconnect.i_tcdm_interconnect`); E11's area has four coarse parts (memory, interconnect, cores, rest), the cores' SNAX CSR translators in rest. $C_\text{run}$ (for $\eta_A$) is the plain RTL run's run section, which every run has; energy uses the quiet run's window and its own cycles $C_w$, never $C_\text{run}$, as the two builds differ by up to 4 %; $n_\text{op}$ comes from the kernel's maths.
- **Why:** these programs have no SNAX-GVSoC model and no expected file, and R7's 26 netlist runs equalled the RTL to the cycle; the flow's own helpers keep the baseline measured the way forge's points are.
- **Where:** `cluster/README.md`, "snb"; `results/snb/runs/2026-11-16_snb1_r7.md`, `2026-11-17_snb1_r6.md`.

### X92 — E11's energy is dynamic only, leakage a side number

- **Decided:** E11's $E_\text{run}$ and $\eta_E$ use the run window's dynamic energy (internal plus switching, power_pt.csv's `e_win_pj`, the macros as PT measures them, X75). Leakage, $E_\text{leak} = P_\text{leak}\thinspace C_w\thinspace t_\text{clk}$ from the window's power.rpt, is reported beside it with the macros' part, never added in.
- **Why:** the Snitch runs take 50 to 200 times forge's cycles, so leakage over the window would swamp the comparison with a number set by the macros' CACTI leakage and the clock period, not by the work; forge's cluster rows are dynamic only too.
- **Where:** `cluster/README.md`, "snb"; `report/snb_report.py`.

## Reports and comparison

### X45 · X55 · X61 — The tier comparison CSVs

- **Decided:** `pixi run compare` writes `results/compare_done.csv` and `compare_untiered.csv` from the committed CSVs only: one row per tech, tier, kernel, W, tool, case and size, with areas, splits, energies, cycles and provenance, and no ratios. Every untiered point also runs its n2048 task and takes its parts from it; the compare scripts take every forge case by its design name (PITFALLS E5). Every source is read on its clock-gated rows (X79 · X87 · X88), and the pages and figures say so. It writes nothing if a source has no gated rows, a point or size is missing, a run failed, a key repeats or a split does not add up.
- **Why:** every comparison reads the same raw rows.
- **Where:** `TOOL.md`; `report/compare.py`'s docstring; `results/runs/2026-11-16_cg5_r3.md`.

### X63 · X65 — The parts at n2048, and forge's total without csr

- **Decided:** each kernel page lists the parts at n2048: forge's csr, ctrl, datapath, total and total without csr; Bambu's ctrl and datapath; Vitis dace's RAM apart. Each row takes the parts of its own run. forge's total without csr (ctrl + datapath + glue) is the like-for-like figure against an HLS total; BUSY_COUNTER's `<tag>_peripherals` (snax-forge D168) is in no figure and stays in the CSVs as `peripherals_um2` and `e_dyn_peripherals_pj`.
- **Why:** a part's energy per task must come from the run whose window it multiplies; the HLS tools take their sizes on plain pins and have no CSR file, and an observability counter is neither forge's interface nor its control.
- **Where:** `results/compare/README.md`; `results/forge/runs/2026-11-11_ctrl2_r5.md`.

### X64 — The comparison, one page per kernel

- **Decided:** `pixi run compare-hls` writes `results/compare/`: a README (setup, summary, parts' basis) and per kernel a page and a figure. Generated parts sit between `<!-- gen:NAME -->` markers; the insights around them are hand-written and kept across reruns.
- **Why:** one file had grown past 1,000 lines.
- **Where:** `results/compare/README.md`.

### X77 — A second figure: forge's ctrl and datapath

- **Decided:** `pixi run compare-hls` also writes `<tier>/<kernel>_ctrl_dp.png`: every forge case as its ctrl + datapath only (no csr, peripherals or glue) against the HLS totals, in the same layout as `<kernel>.png`.
- **Why:** ctrl + datapath is the closest to what an HLS block holds; it differs from X63's total without csr only by the glue (at most 1.1 µm²).
- **Where:** `results/compare/README.md`.
