# Decisions

What this repo has settled, one entry per choice: the rule, why, and when and where it was decided (the run note in `results/<source>/runs/` or `results/runs/`). How a flow is run is in the folder READMEs and [`power.md`](power.md); an entry points there instead of repeating it.

A later choice that changes an entry takes the next number and says which one it amends; numbers are never reused. Retired entries are listed at the end. The longer wording of every entry, with its full record of numbers, is in git history (`git log -p docs/DECISIONS.md`, before 12 Nov 2026).

| X | Decision |
|---|---|
| [X1](#x1-libraries) | Nangate 45 nm and 15 nm Open Cell Libraries, typical corner |
| [X2](#x2-clock) | Clock 10 ns throughout; `fmax_mhz` is a lower bound |
| [X3](#x3-wire-load-drive-and-load) | No wire-load model; `INV_X4` drive, four `INV_X4` inputs of load; max transition 0.25 ns |
| [X4](#x4-physical-constraints-and-the-unit-check) | Constraints in ns and fF, scaled to the library's units, with a unit check |
| [X5](#x5-results-per-technology) | One results tree per technology; only `KEPT_REPORTS` committed |
| [X6](#x6-run-folders-are-kept) | The mapped netlists in `syn/runs/` are kept |
| [X7](#x7-energy-from-simulated-activity) | Energy from a zero-delay simulation of the netlist, then PrimePower |
| [X8](#x8-activity-from-the-vcd-through-vcd2saif) | Activity: VCD, vcd2saif, `read_saif`; the VCD deleted at once |
| [X9](#x9-every-activity-file-is-checked) | Every SAIF checked; at least 99 % of nets annotated |
| [X11](#x11-flop-energy) | Flop energy is clock plus register |
| [X12](#x12-cycles-and-windows) | Vitis cycles: first `ap_start` edge to first `ap_done` edge |
| [X13](#x13-dynamic-energy-only) | Dynamic energy of the busy window only |
| [X14](#x14-tbjson-is-internal) | `tb.json` is internal; the producers are not changed |
| [X15](#x15-python-from-pixi) | Python from the repo's pixi workspace |
| [X16](#x16-parallel-jobs-from-free-licences) | Parallel jobs from free licences (amended by X59, X68) |
| [X17](#x17-licence-errors) | A licence error is retried once |
| [X18](#x18-no-dumps-kept) | No VCD, WLF or compiled library kept; SAIFs stay in the run zip |
| [X19](#x19-stimulus-and-expected-cycles) | rand64 stimulus, seed 0, 64 beats by default; expected cycles from cosim's line |
| [X20](#x20-power-results) | `power_pt.csv` and `power_pt_modules.csv` |
| [X21](#x21-the-forge-source) | The forge source: bundles from snax-forge, one commit per result |
| [X22](#x22-synthesis-of-a-forge-point) | A forge point: the shell wrapper, hierarchy kept, csr / ctrl / datapath / glue |
| [X23](#x23-power-of-a-forge-point) | A forge point's power: CSR-driven TB, window checked against BUSY_COUNTER |
| [X24](#x24-the-reference-task-n2048) | The reference task: N = 2048 elements on every side |
| [X25](#x25-pt-is-the-reference-the-setup-check-is-a-diagnostic) | PT is the reference; the PT-against-DC check is a diagnostic |
| [X28](#x28-the-char-source) | The char source: catalogue blocks through snax-forge's `gen-block` |
| [X29](#x29-the-char1-grid) | The CHAR1 grid: 27 points, int64 |
| [X30](#x30-synthesis-of-a-block-alone) | A block alone: the block as top, X22's settings |
| [X31](#x31-char1s-windows-and-stimulus) | CHAR1's busy, idle and stream windows |
| [X32](#x32-the-vcd-cut-per-window) | The VCD cut per window before vcd2saif |
| [X33](#x33-char_powercsvs-columns-and-e_hold) | `char_power.csv`; e_hold, one held-flop energy per technology |
| [X34](#x34-busy_t1-and-duty50-dropped) | `busy_t1` and `duty50` dropped; the isolated-fire cost a known limit |
| [X35](#x35-nangate45s-linkbuffer-slope-kept-as-measured) | nangate45's LinkBuffer slope kept as measured |
| [X37](#x37-charjson-the-table-snax-forge-reads) | `char.json`, the block model snax-forge reads |
| [X38](#x38-hsyn1s-scope) | Four HLS cases, W ≤ 16, a 10 ns HLS clock |
| [X39](#x39-the-bambu-and-xls-sources) | The bambu and xls sources, with a port guard |
| [X40](#x40-path-class-slacks-measured-after-compile) | Path-class slacks measured after compile |
| [X41](#x41-a-controldatapath-split-only-where-the-rtl-declares-it) | A control/datapath split only where the RTL declares it |
| [X42](#x42-the-cycle-csvs-imported-with-provenance) | Bambu's and XLS's cycle CSVs copied with a `SOURCE` file |
| [X44](#x44-power-of-the-bambu-and-xls-points) | Bambu's and XLS's windows and handshakes |
| [X45](#x45-the-tier-comparison-csvs) | `compare_done.csv` and `compare_untiered.csv`: raw rows, no ratios |
| [X47](#x47-sram-area-and-energy-from-cacti-7-at-45-nm) | SRAM area and energy from CACTI 7 at 45 nm; OpenRAM dropped |
| [X48](#x48-the-sram-lookup-table) | The SRAM table is a lookup, never fitted |
| [X49](#x49-memories-as-generated-liberty-and-verilog-models-from-cactis-numbers) | SRAM macros generated from CACTI's numbers |
| [X50](#x50-memory-energy-is-counted-accesses-times-the-table) | Memory energy = counted accesses x the table |
| [X51](#x51-outputs-zipped-one-per-point) | Every point's outputs are one zip |
| [X52](#x52-the-streamer-reader-and-the-sparse-interconnect-characterized) | The streamer reader and the sparse interconnect characterized |
| [X53](#x53-the-strm-tables-and-their-interpolation) | `streamer.csv` and `xbar.csv`, read by multilinear interpolation |
| [X54](#x54-the-interconnects-energy-interpolated-in-1inputs) | The interconnect's energy interpolated in 1/inputs |
| [X55](#x55-untiered-at-n2048) | Untiered at n2048 too |
| [X56](#x56-cycles-checked-within-5-) | The window is the measurement; expected cycles within 5 % |
| [X57](#x57-forges-untiered-points-at-int64) | forge's untiered points at int64 through the recipe's `dtypes` |
| [X58](#x58-a-forge-points-program-from-snax-forges-lower) | A forge point's CSR writes and stream order from snax-forge's LOWER |
| [X59](#x59-at-most-16-cores-and-some-licences-left-free) | At most 16 cores at once, licences left free |
| [X60](#x60-n2048-module-energies-beside-the-default-run) | `power_pt_modules.csv` keyed by point and size |
| [X61](#x61-the-tables-with-forge-and-n2048-untiered-on-nangate45) | forge in the tables; untiered n2048 on nangate45 only |
| [X62](#x62-a-vitis-ram-swapped-for-an-sram-macro) | A Vitis RAM swapped for an SRAM macro |
| [X63](#x63-the-parts-at-n2048-and-forges-total-without-csr) | The parts at n2048; forge without its csr is the like-for-like total |
| [X64](#x64-the-comparison-one-page-per-kernel) | `results/compare/`: one page per kernel |
| [X65](#x65-forges-csr-without-its-peripherals) | BUSY_COUNTER's peripherals are in no figure |
| [X66](#x66-the-clusters-sram-implementation-generated-from-its-memory-list) | The cluster's `tc_sram_impl.sv` generated from its memory list |
| [X67](#x67-the-cluster-source) | The cluster source: `cluster rtl`, `syn`, `gls` |
| [X68](#x68-the-clusters-constraints-and-run-budget) | The cluster's port constraints; one 16-core run at a time |
| [X69](#x69-no-sdf-unless-asked) | No SDF unless asked |
| [X70](#x70-the-interconnect-with-read-only-and-write-only-inputs-xbar_mix) | `xbar_mix`: the interconnect with read-only and write-only inputs |
| [X71](#x71-the-interconnects-read-only-and-write-only-inputs-in-the-cost-factor-form-by-default-crosspoint-form-as-an-option) | Their area in the cost: factor form, crosspoint form as an option |
| [X72](#x72-the-clusters-area-in-groups-against-hwcost) | The cluster's area in groups, against HWCOST |
| [X73](#x73-the-clusters-windows-and-span) | The cluster's windows from the quiet program's marks |
| [X74](#x74-primepower-on-the-whole-cluster) | PrimePower on the whole cluster, one session over the windows |
| [X75](#x75-the-macros-in-cluster-measurements) | Cluster macros as PT measures them |
| [X76](#x76-tb_bins-1-ns-clock-read-as-10-ns) | `tb_bin`'s 1 ns clock read as 10 ns |
| [X77](#x77-a-second-figure-forges-ctrl-and-datapath) | A second figure per kernel: forge's ctrl + datapath |
| [X78](#x78-a-recipes-cluster-points-side-by-side-over-w) | A recipe's cluster points side by side over W, beside HWCOST |
| [X79](#x79-clock-gating-as-a-synthesis-switch) | Clock gating as a synthesis switch: `CLK_GATE_ENABLE`, off by default |
| [X80](#x80-chosen-cluster-points-side-by-side) | `cluster-sweep --points`: chosen cluster points side by side, variants out of the W sweep |
| [X81](#x81-ramcount-one-more-access-per-instance) | RAMCOUNT: one more read or write per instance than the RTL, each listed |
| [X82](#x82-characterization-checks-reported-not-failed) | Characterization checks are reported, not failed, but where there is no data |
| [X83](#x83-the-clock-gated-block-tables) | The clock-gated block tables: `streamer_cg.csv`, `xbar_cg.csv`, `char_cg.json`, in the ungated formats |

## Synthesis

### X1. Libraries

Synthesis runs on the Nangate 45 nm Open Cell Library (typical, 1.10 V, 25 °C) and the Nangate 15 nm one (typical, 0.80 V, 25 °C), chosen per run with `--tech`, no default. New work is on nangate45 only (snax-forge D159); the nangate15 rows stay as data. **Why:** two open libraries give a technology axis with one flow; OSU gscl45nm, used before 28 Oct, has 31 cells and broken pin limits. *28 Oct (SYN); `2026-10-28_step0_libs.md`.*

### X2. Clock

10 ns on every point and technology. `fmax_mhz` = 1000 / (`clock_ns` − `slack_ns`) is a lower bound. **Why:** one clock makes area and energy per cycle comparable; at 10 ns DC keeps area-optimized structures and never upsizes for speed. *27 Oct; `2026-10-27_done.md`.*

### X3. Wire load, drive and load

No wire-load model on either library. Inputs driven by `INV_X4`; outputs loaded with four `INV_X4` inputs (25.0 fF on nangate45, 13.2 fF on nangate15); max transition 0.25 ns. A run whose `area.rpt` shows a wire-load model fails. **Why:** nangate15 has none and nangate45's default would change timing and power, so neither gets one; four inputs is the same fanout in each library's own cells (PITFALLS DC1). *28 Oct; `2026-10-28_syn_tech_probe.md`.*

### X4. Physical constraints and the unit check

`constraints.sdc` holds ns and fF; `syn.py` scales them to the library's units (nangate15 times by 1000). DC stops before reading RTL if the library's name or units differ from the tech file. **Why:** a library in other units takes every constraint 1000x off with no error (PITFALLS DC2). *28 Oct; `2026-10-28_syn_tech_probe.md`.*

### X5. Results per technology

Each technology has its own `results/<source>/<tech>/` tree. Only `KEPT_REPORTS` (`syn/README.md`) is committed per point. **Why:** areas compare only within a library; the kept reports are what the models read and what the run ran on. *28 Oct.*

### X6. Run folders are kept

The mapped netlists in `syn/runs/` are kept; a clean never deletes `syn/runs/` or `sim/runs/`, and synthesis reruns replace only their own points. **Why:** power reads DC's netlist with no resynthesis (X7), and a resynthesis can differ (PITFALLS DC3). *29 Oct.*

## Power

### X7. Energy from simulated activity

Energy comes from a functional, zero-delay Questa simulation of the mapped netlist (`+nospecify +notimingchecks`, `vopt +initreg+0 +acc=n`), then PrimePower in averaged mode on the same netlist, library and constraints as DC. No resynthesis. **Why:** DC's default activity follows the logic structure, not the work (PITFALLS DC4); the netlist is unplaced, so zero delay gives what a per-cycle model needs. *29 Oct; `2026-10-29_pwr_step0.md`.*

### X8. Activity from the VCD, through vcd2saif

The TB dumps a VCD of the design's own scopes over the window; `vcd2saif` cuts it into a SAIF, PT reads it with `read_saif`, and the VCD is deleted at once. Questa's own SAIF is not used. **Why:** Questa 2022.4's SAIF is wrong at zero delay (PITFALLS Q4); vcd2saif agrees with PT's `read_vcd` within 0.1 %. *29 Oct; `2026-10-29_pwr_r1.md`.*

### X9. Every activity file is checked

Before PT, each SAIF must satisfy T0 + T1 + TX = DURATION on every driven net, DURATION = cycles x clock period and the clock's TC = 2 x cycles. After PT at least 99 % of the nets must be annotated (95 % of the driven nets on a whole cluster, X74). A failed check fails the point. **Why:** annotation coverage alone passed a defective SAIF. *29 Oct; `2026-10-29_pwr_r1.md`.*

### X11. Flop energy

Flop energy is always e_clk + e_reg, never one group alone. **Why:** PT books a flop's clock-edge energy under register when its output toggles and under clock when it does not (PITFALLS PT3). *29 Oct.*

### X12. Cycles and windows

A Vitis run's cycles count the rising edges from the first that samples `ap_start` = 1 to the first that samples `ap_done` = 1; the window runs between the falling edges before those two. **Why:** the count equals cosim's latency with no offset, and falling-edge bounds hold exactly the rising edges inside. Bambu, XLS, forge and the cluster have their own windows (X23, X44, X73). *29 Oct.*

### X13. Dynamic energy only

The power flow reports dynamic energy of the busy window, per cycle as E_comb and E_flop = E_clk + E_reg + E_seq; energy per task is (E_comb + E_flop) x cycles. No leakage in the power results (it stays in `synth_dc.csv`), no idle window (except CHAR1, X31, and the cluster, X73). **Why:** snax-forge's models annotate only dynamic activity per active cycle. *29 Oct.*

### X14. tb.json is internal

`tb.json`, the description each TB is built from, is written by an adapter per source (`sim/sources/`) from what the producer already writes; hls-exercises, dslx-exercises and snax-forge are never changed to be measured. **Why:** this repo is the measuring side. *29 Oct.*

## Environment

### X15. Python from pixi

Python comes from the repo's pixi workspace (Python 3.11): `pixi run ...`, never the host's `python3`. **Why:** the server's `python3` is 3.6; one locked environment everywhere. *29 Oct.*

### X16. Parallel jobs from free licences

Count free licences with `lmutil lmstat` before a batch and size the parallel jobs from them; PT threads = cores // jobs. Amended by X59 (at most 16 cores) and X68 (cluster runs). **Why:** a job without a licence fails or waits. *29 Oct.*

### X17. Licence errors

A tool that fails with a licence error is retried once; a second failure is reported. **Why:** error -92 was transient (PITFALLS L1). *29 Oct.*

## Power runs

### X18. No dumps kept

No VCD, WLF or compiled design is kept; the VCD is deleted right after vcd2saif. A point's zip keeps `tb.json`, the SAIF and PT's reports (X51). **Why:** a VCD grows with nets x cycles and its SAIF replaces it; the rest rebuilds in seconds. *29 Oct.*

### X19. Stimulus and expected cycles

The default stimulus is rand64: full-range int64 from NumPy's `default_rng(0)`, stream by stream in `tb.json` order, then the data pins. The default HLS task is 64 beats (`b64`); every input bit must toggle at least once. Expected cycles come from cosim's line a x loop_count + b through its two sizes. **Why:** full-range data toggles every bit, so energy does not depend on how narrow the test values are. The compared task is n2048 (X24, X55); the cycle check is X56's. *29 Oct; `2026-10-29_pwr_r1.md`.*

### X20. Power results

`power_pt.csv` has one row per point, size and seed, with the per-cycle energies and per-task energy defined in [`power.md`](power.md#energy-quantities); `power_pt_modules.csv` has one row per hierarchical cell (X60). The checks fail a point but are not columns; tool versions go in the run note. **Why:** the cost model needs energy per cycle and per firing, split into combinational and flop, across W. *29 Oct; amended by X60, X62, X74.*

## SYN1: snax-forge

### X21. The forge source

`forge/points.json` lists the forge points, named like hls-exercises' (`<tier>/<kernel>/<case>_w<W>`). `pixi run forge-rtl` runs snax-forge's own tasks in the sibling checkout and zips each bundle into `rtl/forge/` (not committed). Every row records its snax-forge commit; a dirty bundle is refused; a re-label after a commit move needs a byte-for-byte rebundle diff. **Why:** a result must trace to exactly the RTL synthesized, without changing snax-forge. *1 Nov (SYN1); `results/forge/runs/2026-10-31_syn1_r1b.md`.*

### X22. Synthesis of a forge point

A forge point synthesizes its `<tag>_shell_wrapper` with the hierarchy kept (`compile_ultra -no_autoungroup`) and boundary optimization on, otherwise as HLS. Its rows add `csr_um2`, `ctrl_um2`, `datapath_um2` and `glue_um2` (the total minus the three). **Why:** the comparison needs control and datapath apart, and only a kept hierarchy gives them; the glue stays under 0.1 % of the total. *1 Nov; `2026-10-31_syn1_r1.md`.*

### X23. Power of a forge point

`sim/sources/forge.py` builds the TB from the bundle; `sim/tb/csr_seq.sv` writes the CSRs LOWER writes (X58), then START. The window opens before the edge that accepts START and closes one cycle before done; BUSY_COUNTER and snax-forge's expected cycles are recorded beside it (X56). Details in [`power.md`](power.md#forge---source-forge). **Why:** the same flow as HLS, driven as the cluster drives forge. *1 Nov; `2026-10-31_syn1_r2.md`.*

### X24. The reference task n2048

Comparisons use one task of N = 2048 elements per input stream on every side (`n2048`, 2048 / W beats). The forge points have only this size; the HLS points have it beside cosim's sizes and `b64`. **Why:** the same task at every W makes energy per task and per element comparable. *1 Nov; extended to untiered by X55.*

### X25. PT is the reference; the setup check is a diagnostic

PT with simulated activity is the reference for energy; DC's power is an early check only. `pwr setup-check` (PT against DC on one netlist with the same forced activity) prints its per-group differences for the run note and never fails a point. The wire-load and SAIF checks stay gates. **Why:** the two tools differ on nangate15 for library reasons (PITFALLS PT5), within 0.02 % on nangate45. *1 Nov; replaces X10.*

## CHAR1: snax-forge's blocks alone

### X28. The char source

`char/points.json` lists one catalogue datapath per point; `pixi run char-rtl` runs snax-forge's `gen-block` into `rtl/char/`, recording the commit; a dirty checkout is refused first. **Why:** as X21. *3 Nov (CHAR1).*

### X29. The CHAR1 grid

27 points at int64: ElementwiseLanes (now SimdLanes) add and mul at W = 1, 8, 32; accumulating Mac at W = 1, 8, 32; TreeAccumulate at W = 1–32; SerialAccumulate at W = 2–32; LinkBuffer at D = 1–16 (W = 1) and D = 1 at W = 8, 32. **Why:** the blocks and forms SYN1's accelerators use, enough points for a first-order model. *3 Nov.*

### X30. Synthesis of a block alone

`syn.py --source char` synthesizes the block itself as top (clock `clock`, asynchronous active-high `reset`) with X22's settings; results in `results/char/<tech>/char_synth.csv`. **Why:** a block alone then equals the same module inside an accelerator within 0.05 % where the accelerator drives its pins. *3 Nov.*

### X31. CHAR1's windows and stimulus

A block has no CSRs, so `sim/pwr.py --source char` drives it through fixed 128-cycle windows: `busy` (a fire every cycle) and `idle` (enable low, inputs held) for the compute blocks, `stream` (a full-rate FIFO) for LinkBuffer. Inputs change at the rising edge; each window follows a lead-in of its own kind. Details in [`power.md`](power.md#char---source-char). **Why:** a block model needs busy and idle apart, and falling-edge inputs doubled the transitions in a zero-delay run (TreeAccumulate 1.36x). *3 Nov; `2026-11-03_char1_r2.md`.*

### X32. The VCD cut per window

`sim/pwr.py` cuts the VCD into one file per window (`vcd_windows`) and runs vcd2saif on each cut, not on the shared VCD. Used by char, streamer, xbar and the cluster. **Why:** on a shared VCD vcd2saif adds a phantom toggle for a zero-width pulse before the window (PITFALLS VS1). *3 Nov.*

### X33. char_power.csv's columns and e_hold

`char_power.csv` has one row per point and window with X20's per-cycle energies. e_hold is the mean idle energy per flop bit of the registered blocks: 7.1476 fJ on nangate45, 1.8911 fJ on nangate15. A LinkBuffer that is not loading costs its flops x e_hold. **Why:** a held flop costs the same in every block (14 points within 0.2 %). *3 Nov; a clock-gated run's spread reported, not checked (X82).*

### X34. busy_t1 and duty50 dropped

The model has busy and idle (stream for LinkBuffer). Known limit: an isolated fire of an accumulator costs 25 to 30 % more than a back-to-back one (Mac, TreeAccumulate at W = 8 on nangate45). **Why:** `busy_t1` was within 5 % of busy, and `duty50` is a check, not a window the model uses. *3 Nov.*

### X35. nangate45's LinkBuffer slope kept as measured

nangate45's LinkBuffer stream energy is kept as PT gives it, although a streaming flop costs less than a held one there. A known limit. **Why:** a first-order model; the cause is not established. *3 Nov.*

### X37. char.json, the table snax-forge reads

`pixi run char-export` writes `results/char/<tech>/char.json`: the flop constants (area, e_load, e_hold), ctrl's counter factor, and per block its comb area and comb energy per fire, with a rule for other lane counts (`copy` or `interpolate`). The model it feeds is explained in [`results/char/README.md`](../results/char/README.md#the-block-model). **Why:** a model snax-forge evaluates from a block's params and a task's fires and cycles, with a few constants per technology; it lands within 0.99 to 1.04 of SYN2's kernels. *3 Nov; replaces X36.*

## HSYN1: four HLS cases

### X38. HSYN1's scope

forge is compared with four HLS cases: Vitis opt, Vitis dace, Bambu and Google XLS, every tool scheduled at a 10 ns HLS clock, W ≤ 16 (`MAX_W`). Vitis unopt and every W = 32 point are retired. `hls` names the Vitis source. **Why:** W = 32 overloads the interconnect (96 ports for three streams); unopt is a known-poor baseline; one clock for every tool. *5 Nov (HSYN1).*

### X39. The bambu and xls sources

`syn.py` has three HLS sources, each with its root, cases, clock and reset port (`syn/README.md`). Before DC, a port guard checks the source's clock and reset are on the top; `syn.py check-ports` runs it alone. **Why:** the hls source once listed Bambu's folders with Vitis's port names. *5 Nov.*

### X40. Path-class slacks measured after compile

After compile `dc_syn.tcl` measures the worst slack of in2reg, reg2reg, reg2out and in2out with `get_timing_paths` only, into `path_classes.rpt` and four `slack_*_ns` columns. **Why:** XLS's points are one combinational stage, which `fmax_mhz` alone hides. *5 Nov.*

### X41. A control/datapath split only where the RTL declares it

Area is split into control and datapath only where the hierarchy declares it: forge (X22) and Bambu (`controller_*`, `datapath_*`, glue). Vitis and XLS report totals. **Why:** splitting a flat netlist means guessing. *5 Nov.*

### X42. The cycle CSVs imported with provenance

`pixi run import-cycles` copies `bambu_cycles.csv` and `xls_cycles.csv` byte for byte from their repos, with a `SOURCE` file (repo, commit, path, sha256, date); it refuses an untracked or modified file. **Why:** a byte copy cannot drift, and `SOURCE` names the commit. *5 Nov.*

### X44. Power of the bambu and xls points

Bambu and XLS are measured as Vitis is, each with its own handshake: Bambu's window runs from `start_port` to `done_port` (its `cycles_done`); XLS's from the cfg transfer to the last output transfer (its `cycles` + 1, as its datapath is combinational). One port table, in `syn.py`'s `SOURCES`, serves synthesis and power. Details in [`power.md`](power.md#bambu---source-bambu). **Why:** each tool's own handshake marks its task. *5 Nov; `results/runs/2026-11-05_hsyn1_r5.md`.*

### X45. The tier comparison CSVs

`pixi run compare` writes `results/compare_done.csv` and `compare_untiered.csv` from the committed CSVs only: one row per tech, tier, kernel, W, tool, case and size, with areas, splits, energies, cycles and provenance, and no ratios. It writes nothing if a point or size is missing, a run failed, a key repeats or a split does not add up. **Why:** every comparison reads the same raw rows. *5 Nov; amended by X55, X61, X63.*

### X47. SRAM area and energy from CACTI 7 at 45 nm

SRAM banks (one read-write port, no ECC) are costed with CACTI 7 (commit `1ffd8df`, built by `pixi run ram-build`) at 45 nm, itrs-hp, design objective weighted to dynamic energy and area; dynamic energies scaled from 1.0 V to 1.10 V by 1.21. Nangate 45 nm only. **Why:** OpenRAM's analytical model gives one power for read, write and idle and an area only with layout; CACTI gives read and write energy and area in 0.2 s, close to published 45 nm figures. *6 Nov (RAM1); `results/ram/runs/2026-11-05_ram1_r1.md`.*

### X48. The SRAM lookup table

`results/ram/nangate45/ram_table.csv` holds every depth 32–4096 (step 32) and width 8–256 (step 8): 4,095 rows. It is a lookup, never interpolated or fitted; a size off the grid is the reader's choice. **Why:** CACTI's numbers jump up to 30 % between neighbouring sizes (PITFALLS C5); the best fit still misses by 6 % on average and 30 % at worst. *6 Nov.*

### X49. Memories as generated Liberty and Verilog models from CACTI's numbers

DC, Questa and PT see each SRAM as a macro written by `pixi run ram lib`: a Liberty model (area, read and write energy on the rising edge only when selected, pins borrowed from Nangate's `DFF_X1` and `BUF_X4`) and a behavioural Verilog model with `tc_sram_impl`'s ports that counts accesses (`RAMCOUNT`). Never committed. Details in [`ram/README.md`](../ram/README.md). **Why:** CACTI gives no Liberty; generated from the table's own numbers, the macro adds no second energy model. *6 Nov.*

### X50. Memory energy is counted accesses times the table

A single point with SRAM macros reports their energy as counted reads and writes x the macro's table energies, plus PT's energy of everything else ([`docs/cost_tables.md`](cost_tables.md#sram-banks)). An exception to X25 for macros; cluster points use X75. **Why:** averaged PT charges a macro's energy with independent pin probabilities, 12.5 % low on the probe (PITFALLS PT7); the counters are exact. *6 Nov.*

### X51. Outputs zipped one per point

Every point's bulky outputs are one deterministic zip, read and written through `arc/arc.py`; tools that need files get one point unpacked into `tmp/` at a time. What is zipped and the working rules are in `CLAUDE.md`; `pixi run arc check` must report nothing left at the end of a round. **Why:** Ryan's home has a file-count quota shared by every repo, and loose run outputs took about 116,000 inodes (now about 2,500). *6 Nov (ARC1); `results/runs/2026-11-06_arc1_r1.md`.*

## STRM1: the streamer reader and the sparse interconnect

### X52. The streamer reader and the sparse interconnect, characterized

snax_cluster's streamer reader (`strm__C0_Reader`, as the Streamer instantiates it) and its TCDM sparse interconnect are synthesized and powered over their parameters, totals only, Nangate 45 nm: readers over depth {2, 4, 8, 16} x loops 1–7 x channels {1, 2, 4, 6, 8, 16} (168), the interconnect over inputs 4–64 x banks {16, 32, 64} (27, energy only where inputs ≤ banks). A writer is priced as a reader. Stimuli, windows and settings in [`power.md`](power.md#streamer-and-interconnect---source-streamer---source-xbar) and [`cost_tables.md`](cost_tables.md). **Why:** the cost model needs these costs by their design parameters; the full-rate stimuli are the cases the model scales from. *6 Nov (STRM1); `results/strm/runs/2026-11-06_strm1_r1.md`; the flop check reported, not failed, by X82.*

### X53. The STRM tables and their interpolation

`pixi run strm-table` writes `results/strm/<tech>/streamer.csv` and `xbar.csv`. Readers read them by interpolating linearly along one axis at a time between the two grid values around the query; a grid value is exact; above inputs = banks the interconnect's energy takes the value at inputs = banks. The rule and its checks are in [`cost_tables.md`](cost_tables.md#reading-a-table). **Why:** area and energy are close to multilinear in the parameters. *6 Nov; the interconnect's energy amended by X54.*

### X54. The interconnect's energy interpolated in 1/inputs

The interconnect's energy per access is interpolated linearly in 1/inputs along the inputs axis; every other field stays linear in the raw values. **Why:** at fixed banks the energy per access is a + b/n (a per-cycle part shared by n grants), which 1/inputs reproduces exactly; leave-one-out error 2.5 % mean against 9.0 % linear in inputs. *6 Nov; `results/strm/runs/2026-11-06_strm1_r2.md`.*

## CSYN1: E7's untiered rows

### X55. Untiered at n2048

Every untiered point also runs one 2048-element task: relu and axpy n2048, matadd m32_n64, rowsum m16_n128. The forge points have only this size; energy is compared at n2048. **Why:** the same task at every W and tool, with at least 128 beats at W = 16. *10 Nov (CSYN1).*

### X56. Cycles checked within 5 %

Each tool's start-to-done window is the measurement. The expected cycles (forge's BUSY_COUNTER and snax-forge's model, HLS's cosim line) sit beside it, and a point fails only past 5 %. Replaces the exact match of X19 and X23. **Why:** a few cycles of fill change the energy very little; past 5 % means a wrong size, CSR or stimulus. *10 Nov.*

### X57. forge's untiered points at int64

forge's relu, matadd, axpy and axpy_baked are bundled at int64 through the recipe's own `dtypes` field (`forge/points.json`), written to a temporary recipe file; snax-forge is not changed. **Why:** those kernels are int32 in snax-forge, every other point int64. *10 Nov; `results/forge/runs/2026-11-10_csyn1_r1.md`.*

### X58. A forge point's program from snax-forge's LOWER

Every forge point is bundled at its n2048 shape, and the TB writes what snax-forge's LOWER writes for it (JOBS, JOB_BEATS, scalar CSRs, START) and feeds each stream in its streamer's element order. **Why:** a per-group rule did not hold for the untiered recipes; LOWER is the program the cluster runs. *10 Nov; replaces X23's per-group rule.*

### X59. At most 16 cores, and some licences left free

A round uses at most 16 cores at once and never every free licence: DC `-j 4 --cores 4`, power `--cores 16 -j 4`, one batch at a time. **Why:** the host and licences are shared; a multicore DC run can hold several DC-Expert licences (PITFALLS L4). *10 Nov; amends X16.*

### X60. n2048 module energies beside the default run

`power_pt_modules.csv` has a `size` column and holds each point's default run and its n2048 run, keyed by point and size. **Why:** the parts at n2048 need that run's modules without moving the default run. *10 Nov; amends X20.*

### X61. The tables with forge, and n2048 untiered on nangate45

The compare scripts take every forge case by its design name (PITFALLS E5); an untiered forge point exists on nangate45 only; untiered takes its parts from n2048 on nangate45 and from the default run on nangate15. **Why:** CSYN1 ran on nangate45 only (D159). *10 Nov; amends X45, X55.*

### X62. A Vitis RAM swapped for an SRAM macro

On nangate45, `syn.py` replaces each one-port RAM Vitis built by a CACTI macro of its size behind a wrapper with Vitis's ports (`ram/vitis_ram.py`); a RAM with no macro parks the point, or is built from flops with `--with-ram`. Its energy is counted (X50) into `e_ram_pj`; rows add `ram_um2` and `ram_kind`. dot's and axpy's 2048 x 64 buffers are macros; rowsum's 16-word two-port buffer is flops. **Why:** the dace points were parked for their buffers; the netlist differs from Vitis's only in the memory. *10 Nov; `results/hls/runs/2026-11-10_csyn1_r3.md`.*

### X63. The parts at n2048, and forge's total without csr

Each kernel page lists the parts at n2048: forge's csr, ctrl, datapath, total and total without csr; Bambu's ctrl and datapath; Vitis dace's RAM apart. forge's total without csr is the like-for-like figure against an HLS total, since the HLS tools take their sizes on plain pins and have no CSR file. Each row takes the parts of its own run. **Why:** a part's energy per task must come from the run whose window it multiplies. *10 Nov; amended by X65, X77.*

### X64. The comparison, one page per kernel

`pixi run compare-hls` writes `results/compare/`: a README (setup, summary, parts' basis, nangate15 check) and per kernel a page and a figure. Generated parts sit between `<!-- gen:NAME -->` markers; the insights around them are hand-written and kept across reruns. **Why:** one file had grown past 1,000 lines. *10 Nov; replaces X46.*

## CTRL2: snax-forge's leaner control unit

### X65. forge's csr without its peripherals

BUSY_COUNTER (snax-forge D168) sits in `<tag>_peripherals` inside the csr and is in no figure: the csr part is the csr cell minus it, the total without csr is the total minus the whole csr cell, i.e. ctrl + datapath + glue. It stays in the CSVs as `peripherals_um2` and `e_dyn_peripherals_pj`. **Why:** an observability counter is neither forge's interface nor its control, and no HLS block has one. *11 Nov (CTRL2); `results/forge/runs/2026-11-11_ctrl2_r5.md`.*

## CSYN1 Part B: the cluster

### X66. The cluster's SRAM implementation, generated from its memory list

A cluster's memories are RAM1's macros. `cluster/mem.py` reads clustergen's `--memories` list and writes one `tc_sram_impl.sv` with a branch per size (byte mask as the list sets it), the macros' models and `sram_models.f`; snax_cluster reads them through `SRAM_IMPL` and `SRAM_MODELS`. Generated per run, never committed. Checked against tech_cells_generic's model with Verilator: 0 mismatches. **Why:** every memory of the cluster goes through `tc_sram_impl`, so one generated file swaps them all, for any configuration. *11 Nov; `results/cluster/runs/2026-11-11_csyn1_r2.md`.*

### X67. The cluster source

A cluster point (`cluster/points.json`) is a snax-forge design built into snax_cluster's whole cluster, from snax_cluster's main, in three steps: `pixi run cluster rtl` (the bundle, the RTL run and the RTL with macros, both checked with D123), `cluster syn` (DC on snax_cluster's synthesis list, with gates for unresolved references and stray black boxes) and `cluster gls` (the netlist in the same testbench). The steps and what each keeps are in [`cluster/README.md`](../cluster/README.md). **Why:** this is the way any snax-forge design reaches a synthesized cluster, with snax_cluster's own lists. *11 Nov; `results/cluster/runs/2026-11-11_csyn1_r2.md`, `_r3.md`, `_r4.md`.*

### X68. The cluster's constraints and run budget

A cluster run adds `cluster/cluster.sdc` to `constraints.sdc`: asynchronous reset and static ports false-pathed, 30 % of the clock as I/O delay on the AXI ports and 10 % on the CSR ports. One cluster DC run at a time at `--cores 16`, nothing beside it, with `SYN_IGNORE_LOAD=1` (PITFALLS DC13). **Why:** a cluster sits in a SoC, so its boundary gets an outside budget; cluster runs are few and picked. *11 Nov; amends X16, X59 for cluster runs.*

### X69. No SDF unless asked

DC writes an SDF only with `syn.py --sdf`. **Why:** energy is from a zero-delay simulation (X7); nothing reads the SDF. *11 Nov.*

### X70. The interconnect with read-only and write-only inputs (xbar_mix)

The `xbar_mix` source synthesizes STRM1's interconnect with some inputs tied as the cluster ties them (a reader's channel read-only, a writer's write-only) plus the cluster template's ties: inputs {16, 32, 64} x banks {16, 32, 64}, each all read-write, all read-only and all write-only, plus two 36-input points. Area only. **Why:** HWCOST priced the cluster's interconnect at +74 % with every input read-write; DC removes what the constants make dead. *11 Nov; `results/xbar_mix/runs/2026-11-11_csyn1_r3c.md`; its flop count reported, not failed, by X82.*

### X71. The interconnect's read-only and write-only inputs in the cost: factor form by default, crosspoint form as an option

`pixi run xbar-kinds` writes `results/strm/<tech>/xbar_kinds.json` with two forms of the interconnect's area: the factor form (default), `xbar.csv`'s area times $1 - f_{ro}\thinspace n_{ro}/n - f_{wo}\thinspace n_{wo}/n$, and the crosspoint form (an option), a least-squares cost per crosspoint of each kind. Energy stays `xbar.csv`'s per access. Variables, fits and worked examples in [`cost_tables.md`](cost_tables.md#read-only-and-write-only-inputs). **Why:** the factor form keeps `xbar.csv` as the source and adds two numbers; on the cluster it lands at +10.8 % (crosspoint +7.5 %), within HWCOST's 30 % target. *11 Nov; `results/xbar_mix/runs/2026-11-11_csyn1_r3d.md`.*

### X72. The cluster's area in groups, against HWCOST

`cluster/groups.json` names the cluster's groups by path rules; each node of `area_hierarchy.rpt` adds its own area to the first group it matches, else its parent's, so the groups add up to the total. `pixi run cluster-breakdown` compares them with snax-forge's HWCOST five parts (priced by snax-forge itself, `pixi run cluster-hwcost`) and the accelerator with its point synthesized alone. **Why:** path rules keep the groups exact, and nothing is lost or counted twice. *11 Nov; `results/cluster/runs/2026-11-11_csyn1_r3b.md`.*

### X73. The cluster's windows and span

A cluster point's power is measured on the quiet program (`forge_quiet.elf`): each program section writes the next value to CSR `0x7c5`, which reaches the top port `obs_o`. Each section is one window, between quarter cycles before consecutive marks; the span runs from the first mark to the check's mark, so it ends when the data has left L1. Idle windows are measured too. **Why:** the marks come from the run on the netlist itself; on `dot3_w16` the windows equal the RTL's cycles exactly. *12 Nov (PWR1); amends X12, X13 for cluster points.*

### X74. PrimePower on the whole cluster

`pixi run cluster pwr <point>`: one netlist run dumps one VCD, one pass cuts it into the windows' SAIFs, and one PT session in averaged mode reports each window; at least 95 % of each window's driven nets annotated. `power_pt.csv` has one row per window, adding `e_macro_pj`, `e_io_pj` and `e_win_pj`; `pixi run cluster-energy` sums each window into X72's groups and compares the run phase with HWCOST's energy shares. **Why:** one VCD and one PT session keep a run to minutes; averaged mode matches the library's clock-pin energy where time-based mode halves it (PITFALLS PT10). *12 Nov; amends X20 for cluster rows.*

### X75. The macros in cluster measurements

A cluster's macros (TCDM banks, I-cache) are taken as PT measures them in averaged mode, with PITFALLS PT7's bias noted; no counted accesses for cluster points. **Why:** a cluster measurement gives the data as measured; the counted model is HWCOST's, and comparing the two is the point (the banks within 1 % on `dot3_w16`). *12 Nov.*

### X76. tb_bin's 1 ns clock read as 10 ns

snax_cluster's testbench clocks at 1 ns. Each cut VCD's header gets `$timescale 10ps` for `1ps`, so the run reads as 10 ns and X9's checks and PT's clock hold unchanged. **Why:** a zero-delay run's activity and energy per toggle do not depend on the period. *12 Nov.*

### X77. A second figure: forge's ctrl and datapath

`pixi run compare-hls` also writes `<tier>/<kernel>_ctrl_dp.png`: every forge case as its ctrl + datapath only (no csr, peripherals or glue) against the HLS totals, in the same layout as `<kernel>.png`, which is unchanged. **Why:** ctrl + datapath is the closest to what an HLS block holds; it differs from X63's total without csr only by the glue (at most 1.1 µm²). *12 Nov.*

### X78. A recipe's cluster points side by side over W

`pixi run cluster-sweep [--recipe dot_3]` reads `breakdown.json` and `energy.json` (X72, X74) for every point of the recipe and writes `results/cluster/<tech>/sweep.csv` (long form: point, W, source `gls`, `hwcost` or `alone`, window, group, metric, value), `sweep_energy.png` and `sweep_area.png`: per W the netlist's run window (`5_run`) and area in HWCOST's five parts plus what HWCOST does not price, beside HWCOST's five parts, absolute and in % of each side's five parts, and `sweep_energy_five.png` and `sweep_area_five.png` with the absolute panel alone, the five parts only on both sides, each bar's total above it; `--md` prints the per-W tables with the shell alone. Raw data only: no normalization and no check on the trend. **Why:** the W sweep is an experiment read by hand (Ryan, 12 Nov); one file holds every number and the figures show the two sides together. *13 Nov (PWR2); `results/cluster/runs/2026-11-13_pwr2_r2.md`.*

### X79. Clock gating as a synthesis switch

`dc_syn.tcl`'s `CLK_GATE_ENABLE` (from `SYN_CLK_GATE_ENABLE`, default 0) turns on DC's clock gating for one run: `syn/scripts/clock_gating.tcl` (stop if the library has no `latch_posedge` integrated gate; latch-based integrated gates, positive edge, `-minimum_bitwidth 2`, through the hierarchy; no test control point, no negedge logic, no operand isolation), `compile_ultra -no_autoungroup -gate_clock`, and `clock_gating.rpt`, `clock_gating_elements.rpt` and `clock_gating_ungated.rpt`, kept whatever their size. Nangate's `CLKGATE` cells, which DC marks black boxes (a statetable), are not counted as the cluster's macros. `syn.py run --clk-gate` and `pwr.py run --clk-gate` tag a source's run `_cg` and give its rows `clk_gate` 1, merged apart from the ungated rows (an empty `clk_gate` reads as 0); a cluster point sets it with `"syn": {"clk_gate": true}` under its own name. The reports and the cluster breakdowns read the ungated rows of a source point (`alone`, the HLS comparison). **Why:** the cluster's idle floor is mostly the clock of flops that are never gated (PWR1, PWR2), which HWCOST does not price; one switch through every flow lets a gated run sit beside the ungated one without changing either. On `dot3_w8_cg` DC gates 98.6 % of the registers with 1,653 `CLKGATE_X1`; area −6.5 %, the idle floor from 376.7 to 31.5 pJ per cycle, the run window from 161.43 to 62.23 nJ. *13 Nov (CG1); `results/cluster/runs/2026-11-13_cg1_r1.md`, `_r2.md`, `_r3.md`.*

### X80. Chosen cluster points side by side

`pixi run cluster-sweep --points A,B,... --out NAME` lays out the named points in the order given (variants included) with X78's tables, `sweep.csv` and figures, into `results/cluster/<tech>/NAME/`, each pair of bars labelled by point and W. The recipe's W sweep leaves out variant points (those with a `syn` field), so `sweep.csv` stays one point per W. **Why:** a variant such as `dot3_w8_cg` shares its W with another point; the same figures, one folder per comparison. *13 Nov (CG1).*

### X81. RAMCOUNT: one more access per instance

A cluster point's `gls` compares each memory instance's RAMCOUNT reads and writes with the RTL macro run's and passes when they are equal but for at most one more read or one more write per instance in the netlist run; each such instance is listed in `gls/check.json` (`ram_extra_writes`, `ram_extra_reads`) and named in the summary line. Amends X67's `gls` step, which allowed only the extra write. **Why:** under `+initreg+0` a netlist can access a memory once at the time-0 edge, during reset and before every window (PITFALLS Q8, Q14): the I-cache's write since CSYN1, the clock-gated netlist's TCDM read since CG1. D123 and the cycle count stay the gates; RAMCOUNT may become a report only later (Ryan, 13 Nov). *13 Nov (CG1 R2).*

## CG2: the clock-gated block tables

### X82. Characterization checks reported, not failed

A characterization row (`--source streamer`, `xbar`, `xbar_mix`, `char`) fails only when it has no data: a tool or licence error, an empty report, no power run, or a simulation whose data mismatch. `syn.py`'s flop check (`seq_cells` against `rtl_flop_bits`) and `xbar_mix`'s count are printed (`flops <point> on <tech>: ...`) and the row stays `ok`; window cycles, fill, stalls and fires against the ungated row, `clock_gating.rpt`'s counts, the e_hold spread and the gated/ungated provenance go into the run note. Amends X52's flop check, X70's and X33's spread. **Why:** a clock-gated run counts its integrated gates as sequential cells, and Ryan prefers these numbers logged and read rather than gated (13 Nov). *13 Nov (CG2 R1).*

### X83. The clock-gated block tables

`pixi run strm-table --clk-gate` writes `results/strm/<tech>/streamer_cg.csv` and `xbar_cg.csv`, and `pixi run char-export --clk-gate` writes `results/char/nangate45/char_cg.json`, from the `clk_gate` 1 rows, in the ungated tables' formats and read with X53's and X54's rules. An integrated clock gate is a sequential cell: no column of its own, `flops` is `seq_cells`, `flop.area_um2` the mean of `seq_area / seq_cells`, e_load and e_hold per sequential cell; the gate is not priced on its own. `xbar_kinds.json`'s f_ro and f_wo carry over. ctrl stays ungated: `char_cg.json`'s counter factor is `char.json`'s times `char.json`'s e_hold over its own, so E_ctrl is unchanged. Each writer prints the gated value over the ungated one per point. `pixi run cg2-reprice` prices dot_3's five HWCOST parts with either set, as snax-forge does, into `results/cluster/<tech>/hwcost_cg.csv`. **Why:** HWCOST's tables come from ungated blocks, while a gated cluster has almost no idle clock (CG1); the gated tables sit beside the ungated ones until snax-forge imports them (a later D-number). The per-cell constants undercount a register's bits by its gates' share (about 1/65 for 64 bits behind one gate), a first assumption (Ryan, 13 Nov). *13 Nov (CG2 R1).*

## Retired

| X | What it was | Retired by |
|---|---|---|
| X10 | PT setup check with pass tolerances | X25 (a diagnostic) |
| X26 | forge's control RTL copied as a reading aid | X43 |
| X27 | SYN2 read SYN1 from git; SYN1's local runs kept | X43 |
| X36 | `char_table.md` and a draft JSON | X37 |
| X43 | SYN1's and SYN2's analysis code and results deleted (git `e8c4e91`) | (the retirement itself) |
| X46 | `results/compare_hls.md`, one file | X64 |
