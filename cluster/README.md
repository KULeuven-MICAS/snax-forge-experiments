# cluster

A snax-forge design built into snax_cluster's whole cluster, synthesized, run on its netlist and powered per program section (X66, X67 · X81 · X84, X68, X72–X76). A point is one entry of `points.json` (`point`, `recipe`, `W`, `sets`, `srams` the macro instances it holds, `alone` its accelerator synthesized alone, optional `syn` its DC settings; and the two container images). The points are dot 3 at N = 2048 and W = 2, 4, 8, 16 and 32, clock-gated (`dot3_w<W>_cg`, `"syn": {"clk_gate": true}`, X79 · X87 · X88). The commands are in [`docs/TOOL.md`](../docs/TOOL.md#7-take-a-design-through-the-whole-cluster).

Each step takes snax_cluster from `SNAX_CLUSTER` (default `../snax_cluster`), clean and on `origin/main` unless `--allow-branch`, and records its commit. snax_cluster's make targets run in its container (`podman run --rm -v "$PWD":"$PWD" -w "$PWD" <image>`, the mount the parent folder of the sibling repos). The point's work folder is `tmp/cluster/<point>/`, deleted when the step ends, also on a failure.

## The steps

| Step | What it does | Checks | Kept |
|---|---|---|---|
| `rtl` | `pixi run forge` in snax-forge's image gives the bundle, the ELF, its quiet build (`sw/forge_quiet.elf`, `sw/obs_marks.json`) and `forge_expected.txt`, zipped as `rtl/cluster/<point>.zip` with `provenance.json`; reused while commit and image match. Then `rtl-gen`, clustergen's memory list and X66's `tc_sram_impl.sv`, and two vsim runs: the plain RTL and the RTL with the macros (`SRAM_IMPL`, `SRAM_MODELS`) | D123 on both runs; equal cycles; every `[tc_sram_impl]` print against `srams`; nothing of tech_cells_generic's `tc_sram` compiled | `rtl/` in `sim/runs/cluster/nangate45/<point>.zip`, with `check.json` |
| `syn` | the same `tc_sram_impl.sv` (must equal step 1's), snax_cluster's `gen-syn` list, then DC through `syn/syn.py`'s `cluster` source with `cluster/cluster.sdc` on top of `constraints.sdc` (X68) and `cluster_check.tcl` after the reports | the library and wire-load checks; no unresolved reference; the macros the only black boxes and their count `srams`'s; every leaf cell from Nangate or the macros | `syn/runs/cluster/nangate45/<point>.zip`; a row in `results/cluster/nangate45/synth_dc.csv` (with `macro_um2`, `macros`, both commits); `reports/<point>.zip` with `cluster_check.rpt`, `cluster_ports.rpt` and `tree.txt` |
| `gls` | step 2's netlist compiled into its own library (`work-vsim/gls`) and run in step 1's testbench through snax_cluster's `SIM_TYPE=gate_level_sim`, zero delay, `+initreg+0` | gates: the data line equal to the expected one and step 1's; cycles and every counter within 10 % of step 1's macro run; the netlist really loaded; `[SUCCESS]` in both runs. Reported: D123, and RAMCOUNT against step 1's macro run (one more read or write per instance allowed and listed, PITFALLS Q14) | `gls/` in the point's `sim/runs` zip |
| `pwr` | part 1: the quiet ELF on the netlist, one VCD from time 0 to the check's mark, cut into one SAIF per program section (X73, X76); part 2: one PrimePower session over the windows (X74) | X9's SAIF checks per window; at least 95 % of the driven nets annotated | `pwr/` and `pt/` in the point's `sim/runs` zip; `results/cluster/nangate45/power_pt.csv` (one row per window) and `power_reports/<point>.zip` |

`dot3_w16_cg` on the one-core cluster (snax-forge D170), clock-gated: 1,173,293 µm², slack +1.676 ns at 10 ns, RTL and netlist PASS in 810 cycles.

## Files

| File | What it is |
|---|---|
| `cluster.py` | the steps' driver (`pixi run cluster rtl|syn|gls|pwr`) |
| `power.py` | `cluster pwr`, parts 1 and 2 |
| `mem.py` | the cluster's `tc_sram_impl.sv`, the macros' models and `sram_models.f` from clustergen's list (X66) |
| `check.py` | D123, the netlist run's data and timing gates and the run checks |
| `cluster.sdc`, `cluster_check.tcl` | X68's extra constraints; the post-synthesis gates |
| `tree.py` | `area_hierarchy.rpt` as an indented tree (`tree.txt`) |
| `groups.json`, `hwcost.py` | the area and energy groups and snax-forge's HWCOST for a point (X72) |
| `snb.py`, `snb_points.json` | the Snitch-only clusters through the same steps (`pixi run snb <step>`, section snb below) |
| `eqv_tb.sv` | the Verilator bench of `tc_sram_impl.sv` against tech_cells_generic's (result in its header) |
| `test_*.py` | `pixi run python cluster/test_<name>.py` |

Results in `results/cluster/nangate45/`: `synth_dc.csv`, `reports/`, `power_pt.csv`, `power_reports/`, `hwcost/<point>.json`, `breakdown.json`, `energy.json`, and the sweep over W: `sweep.csv`, `sweep_energy.png`, `sweep_area.png`, `sweep_energy_five.png`, `sweep_area_five.png` (X78 · X80 · X86); run notes in `results/cluster/runs/`. The Snitch-only clusters' results are in `results/snb/nangate45/` (below).

## The steps in detail

A point is an entry of cluster/points.json (point, recipe, W, sets, and srams: the macro instances the cluster holds, per macro; optional syn: DC settings of the point, today only {"clk_gate": true}); the file also names the two images. A point with syn.clk_gate turns on dc_syn.tcl's CLK_GATE_ENABLE (SYN_CLK_GATE_ENABLE=1: the clock-gating style, compile_ultra -no_autoungroup -gate_clock and the clock_gating*.rpt reports). snax_cluster is read from SNAX_CLUSTER (default ../snax_cluster): clean, HEAD on origin/main (`git merge-base --is-ancestor HEAD origin/main`) unless --allow-branch. snax-forge is read from SNAX_FORGE (default ../snax-forge): clean (PITFALLS E7). Both commits are recorded. The folder holding the three repos is mounted at its own path in every `podman run --rm` (no -it, stdin closed), with the home folder's Scala caches at /root (strm/gen.py's podman_cmd, PITFALLS SC6).

The bundle, rtl/cluster/<point>.zip: `pixi run forge <recipe> --set W=<W> --set <sets...>` in snax-forge's image from the snax-forge checkout, the recipe found as forge/bundles.py finds it. A dirty bundle (bundle.json `dirty`) or one whose commit is not the checkout's is refused. The zip holds bundle/ (the bundle folder, forge_expected.txt with it), sw/forge.elf (the ELF forge prints), the quiet build beside it (sw/forge_quiet.elf and its legend sw/obs_marks.json, snax-forge D135, for step 4), forge.log, forge.txt (forge's terminal output) and provenance.json (snax-forge commit, image and id, the command, both ELFs' sha256). A zip whose provenance has the same commit, image id and command is reused.

### rtl

rtl, in tmp/cluster/<point>/ (the bundle zip unpacked there; the cluster file is the bundle's own snax_forge.hjson), from snax_cluster's target/snitch_cluster:

1. image: make clean-generated clean-vsim, then make rtl-gen CFG_OVERRIDE=<cluster file>; a separate call: util/clustergen.py -c <cluster file> -o <point tmp> --memories (memories.json)
2. cluster/mem.py memories.json -> mem/ (tc_sram_impl.sv, models/, sram_models.f, mem.json)
3. the plain run: vsim_preparation in the image, snax-forge-sim SIM=vsim and snax-forge-run SIM=vsim ELF=<elf> outside it (Questa on PATH, bender from snax_cluster's .pixi/envs/default/bin)
4. the macro run: the same three calls with SRAM_IMPL=mem/tc_sram_impl.sv SRAM_MODELS=mem/sram_models.f (the vsim stamp rebuilds work-vsim/; no second rtl-gen)
5. the checks (cluster/check.py): D123 on both runs against forge_expected.txt, equal forge cycles, the [tc_sram_impl] prints (their number, and the macro at each one's end) against the point's srams, the macro run's vlog.log (tc_sram_impl.sv and every macro compiled, nothing of tech_cells_generic's tc_sram), [SUCCESS] in both runs
6. sim/runs/cluster/nangate45/<point>.zip, under rtl/ (other members kept): memories.json, mem.json, tc_sram_impl.sv, sram_models.f, plain/ and macro/ (each run's snax-forge-vsim.txt; the macro run's vlog.log and vopt.log), logs/ (every step's log), check.json. Packed also when a step failed. Then tmp/cluster/<point>/ is deleted and `make clean-vsim clean-generated` runs in snax_cluster, also on a failure.

Each step's log path is printed when it starts. One line at the end: PASS or FAIL with the cycles and the instances; a failure names the check or step and prints at most 30 lines of its log.

### syn

syn (step 2), from the same bundle zip, in tmp/cluster/<point>/:

1. image: make clean-generated clean-syn, make rtl-gen CFG_OVERRIDE=<cluster file>; clustergen --memories; cluster/mem.py --text-only: its tc_sram_impl.sv must equal step 1's (rtl/tc_sram_impl.sv in sim/runs/cluster/nangate45/<point>.zip), or the run stops
2. image: make gen-syn CFG_OVERRIDE=<cluster file> SRAM_IMPL=<that file> (work-syn/syn_flist.tcl)
3. DC through syn/syn.py's source `cluster` (dc_env, run_dc with its licence retry, finish_run, write_summary): the run folder syn/runs/cluster/nangate45/<point>/ gets syn_flist.tcl, cluster/cluster.sdc and tc_sram_impl.sv, and the macros' .db (from ram/runs/lib/<name>.zip) for SYN_RAM_DBS; dc_syn.tcl sources the list (SYN_FLIST_TCL), elaborates snax_forge_cluster_wrapper (SYN_TOP), adds cluster.sdc after constraints.sdc (SYN_EXTRA_SDC) and runs cluster/cluster_check.tcl after the reports (SYN_POST_TCL); no SDF; SYN_IGNORE_LOAD=1, so DC keeps --cores under a loaded host (UIO-231); with the point's syn.clk_gate, SYN_CLK_GATE_ENABLE=1. DC's stdout goes to logs/dc_stdout.log as it runs; its path is printed first.
4. tree.txt (cluster/tree.py, area_hierarchy.rpt to depth 4) beside the reports; the run zip syn/runs/cluster/nangate45/<point>.zip keeps syn.py's KEEP_RUN and the cluster's files; a row in results/cluster/nangate45/synth_dc.csv and the report zip results/cluster/nangate45/reports/<point>.zip.
5. after DC ends, also on a failure: tmp/cluster/<point>/ deleted, make clean-syn clean-generated in snax_cluster.

### gls

gls (step 3): step 2's netlist (out/snax_forge_cluster_wrapper_mapped.v of syn/runs/cluster/nangate45/<point>.zip) in step 1's testbench, with step 1's ELF and check; zero delay, functional. snax_cluster's hook SIM_TYPE=gate_level_sim (GLS_NETLIST, GLS_CELLS, with SRAM_IMPL and SRAM_MODELS) compiles the cells, the macro models and the netlist into work-vsim/gls, and vopt takes -Lf work-vsim/gls, +initreg+0, +acc=n; vsim +nospecify +notimingchecks.

1. checks before anything runs: the repos as rtl and syn; step 1 PASS, step 2's netlist there; the bundle zip's ELF the one both steps used (the bundle is reused, never made again: the netlist is of it); no file changed under hw/, util/, target/snitch_cluster/cfg/ or Bender.yml between the netlist's snax_cluster commit and HEAD but Makefiles, .mk and docs (RTL_CHANGE)
2. in tmp/cluster/<point>/: the bundle and the netlist unpacked; image: make clean-generated clean-vsim, rtl-gen; clustergen --memories; cluster/mem.py, whose tc_sram_impl.sv must equal step 1's; the cell models as sim/pwr.py finds them (pwr.cell_model)
3. vsim_preparation in the image, snax-forge-sim SIM=vsim and snax-forge-run SIM=vsim ELF=<elf> outside it, all three with the same SRAM_IMPL, SRAM_MODELS, SIM_TYPE, GLS_NETLIST, GLS_CELLS. The two host steps' Questa processes are sampled from /proc every PEAK_EVERY s (peak resident memory, first and last seen); Questa's own elapsed times are read from vlog.log (the netlist's vlog), vopt.log and the run's output.
4. the checks. Gates: the data line equal to the expected one and to step 1's macro run (data); forge cycles and every counter within check.TIMING_PCT (10 %) of the macro run's (cycles, exact values kept); the swap (vopt loaded snax_forge_cluster_wrapper and Nangate cells from work-vsim/gls, its command has +initreg+0 and +acc=n; the run prints no [tc_sram_impl]); [SUCCESS] in both runs. Reported, not gates (gate false in check.json): D123 against SNAX-GVSoC (the rtl step's gate), and RAMCOUNT (one line per instance of points.json's srams; against step 1's macro run, without the paths: reads equal, writes equal but for at most one more on an instance, the netlist's access at time 0 under +initreg+0, listed as ram_extra_writes or ram_extra_reads; PITFALLS Q14)
5. under gls/ of sim/runs/cluster/nangate45/<point>.zip (other members kept): snax-forge-vsim.txt, vlog.log, vopt.log, logs/, check.json; then vsim.wlf (VSIM_FLAGS' `log -r /*`) deleted with its size in check.json, tmp/cluster/<point>/ deleted and make clean-vsim clean-generated in snax_cluster, also on a failure. One line at the end.

### pwr

Part 1: the quiet build (sw/forge_quiet.elf of rtl/cluster/<point>.zip, snax-forge D135) on step 3's netlist with our own vsim command and do-file, which dump a VCD of the cluster's design scopes and log every change of the wrapper's obs_o (the program section's mark, sw/obs_marks.json); the log is turned into one window per section, every window is cut from the VCD in one pass, vcd2saif makes a SAIF of each cut, and each SAIF is checked. Part 2 (PT) reads the SAIFs from the point's zip. snax-forge, snax_cluster and snax-gvsoc are read, never changed.

tb_bin's clock is 1 ns (TCK = 1ns, -t 1ps), the flow's clock 10 ns (sim/pwr.py's CLOCK_NS, PT's constraints.sdc). The activity of a zero-delay run does not depend on the period, so each cut's header gets `$timescale 10ps $end` in place of Questa's 1ps: every time reads ten times longer, as if the run were at 10 ns, and the SAIF checks and PT's clock hold unchanged.

1. checks before anything runs, as gls: the repos (clean, snax_cluster on origin/main unless --allow-branch); step 1 (rtl/check.json) and step 3 (gls/check.json) PASS; the netlist in syn/runs/cluster/nangate45/<point>.zip; the bundle zip's forge.elf the one the steps used; sw/forge_quiet.elf's sha256 equal to provenance's quiet_elf_sha256; no RTL change in snax_cluster between the netlist's commit and HEAD (cluster.rtl_changes)
2. in tmp/cluster/<point>/, as gls: the bundle and the netlist unpacked; image: make clean-generated clean-vsim, rtl-gen; clustergen --memories; cluster/mem.py, whose tc_sram_impl.sv must equal step 1's; the cell models (pwr.cell_model); vsim_preparation in the image and snax-forge-sim SIM=vsim on the host with gls's options (SRAM_IMPL, SRAM_MODELS, SIM_TYPE=gate_level_sim, GLS_NETLIST, GLS_CELLS), Questa's peak memory sampled (cluster.Peak). No snax-forge-run. vopt and vlog are checked as gls's swap check (cluster.swap_check).
3. the vsim command: bin/snitch_cluster.vsim's vsim line, its one `-do "log -r /*; run -a"` (VSIM_FLAGS) replaced by `-do <work>/pwr/pwr.do`, -batch where snax-forge-run puts it ($3), the quiet ELF as the binary ($1, realpath) and $2 empty; written to pwr/vsim_cmd.sh and run from target/snitch_cluster, its output in pwr/vsim.txt. It passes with `[SUCCESS] Program finished successfully` and no program output (no line outside Questa's `#` transcript but fesvr's).
4. pwr/pwr.do: onbreak {resume}, onfinish stop; `vcd file pwr/dut.vcd` and pwr/vcd_add.do (sourced): one non-recursive `vcd add` per design scope (designs, not cells; LIB2), the wrapper's own nets, then every path of pwr.scopes(netlist, top) under the wrapper's instance, each in braces with its escaped identifiers kept (PITFALLS Q15); a `when` on the wrapper's obs_o (a port, visible under +acc=n, Q16) writes `<ps> <value>` per change to pwr/obs_log.txt, flushed, and at the check's mark runs `vcd off` and `vcd flush`; the run goes on to the program's exit. The dump runs from time 0 (a `when` can only turn it on at the mark's edge, a quarter cycle after the window opens). `run -all`, `quit -f`; no `log`, no `power`. The windows come from obs_o only.
5. the windows (pwr/windows.json): the marks of obs_log.txt in order, each once, from the legend's first up to the check's mark; section k from t_k - 250 ps to t_{k+1} - 250 ps (a quarter cycle before the edge where its mark appears, a time with no events), (t_{k+1} - t_k) / 1000 cycles, a non-integer count failing. Each window's cycles against the quiet vsim run on the RTL (REF_CYCLES); beyond REF_TOL on any window the run stops.
6. the cut: one pwr.vcd_windows pass over dut.vcd for every window, the cuts' $timescale 10ps (timescale_10ps; the VCD's must be 1ps), the window bounds the ps numbers; dut.vcd deleted right after the pass, whatever the result, its size recorded first.
7. vcd2saif per window as pwr.py's char source (-instance tb_bin/i_dut/i_snax_forge_cluster -time t0 t1), each cut deleted after its vcd2saif; at most min(nproc, windows) jobs at once, with no more cuts on disk than jobs; then pwr.saif_check(saif, cycles, "clk_i") per window (DURATION = cycles x 10 ns, clk_i TC = 2 x cycles).
8. under pwr/ of sim/runs/cluster/nangate45/<point>.zip (other members kept): pwr.do, vcd_add.do, vsim_cmd.sh, vsim.txt, obs_log.txt, windows.json, <mark>_<kind>/w.saif and vcd2saif.log per window, logs/, check.json; also on a failure. Then vsim.wlf (none expected) dropped, tmp/cluster/<point>/ deleted, make clean-vsim clean-generated in snax_cluster. The SAIFs live only in this zip (sim/runs/ is git-ignored).

One line at the end; a failure names the check or step and prints at most 30 lines of its log.

Part 2, run by the same command; part 1 is skipped when the zip's pwr/check.json is PASS for the same netlist sha256, quiet ELF sha256 and snax_cluster commit (--again reruns it):

1. PT's threads from --cores (default 16), lowered to the host's free cores (nproc minus the load); a session takes one PrimeTime and one PrimePower (L2), and one of each must stay free
2. in tmp/cluster/<point>/pt/: the DC run's tech.json, reports/lib_info.txt, the netlist and cluster.sdc; the macros' .db (ram/runs/lib/<name>.zip, points.json's srams); every window's SAIF from pwr/ of the run zip
3. one pt_shell (sim/scripts/pt_power.tcl, PWR_MODE=cluster): the library and the macros linked with the netlist, the wire load zeroed (PT1), constraints.sdc then cluster.sdc (PWR_EXTRA_SDC), then per window of PWR_WINDOWS reset_switching_activity, read_saif -strip_path tb_bin/i_dut/i_snax_forge_cluster, update_power, the reports and a done file; a licence error is retried once; peak memory from /usr/bin/time
4. per window, each check failing the window and the run: the wire-load counts 0 (PT1); at least ANN_MIN % of the driven nets annotated, the driven nets PT's nets minus the not-annotated ones the window's SAIF has at Z for the whole window (PT6, DC18; the SAIF streamed, names compared with backslashes and trailing spaces dropped); the SAIF's entries as part 1 counted them; every row of power.rpt parsed, no group but PT_GROUPS; the hierarchy's top total equal to power.rpt's
5. results/cluster/nangate45/power_pt.csv, one row per window merged on (point, mark): the per-cycle energies of sim/pwr.py plus e_macro_pj (black_box + memory, the macros as PT measures them in averaged mode, PITFALLS PT7) and e_io_pj, e_dyn_pj, p_dyn_uw, e_win_pj = e_dyn x cycles, the annotation, tx_nets (part 1), the commits, status; no leakage
6. results/cluster/nangate45/power_reports/<point>.zip: per window power.rpt, power_hierarchy.rpt, switching_activity.rpt, units.rpt; wire_load.rpt, licenses.rpt, windows.json, pt_check.json. pt/ of the run zip: the not-annotated lists, pt_shell.log, the done files, logs/, pt_check.json; also on a failure. Then tmp/cluster/<point>/ is deleted. One line at the end.

## The reports

### cluster-breakdown

For every point of cluster/points.json that has its DC reports (results/cluster/<tech>/reports/<point>.zip, step 2 of cluster/cluster.py), reads area_hierarchy.rpt (cluster/tree.py's parse) and sums it into cluster/groups.json's groups: a node belongs to the first group with a rule it matches, else to its parent's group, and its own area (total minus its children's) goes there, so the groups add up to the top's total. Then, where they exist:

hwcost  snax-forge's five parts (results/cluster/<tech>/hwcost/<point>.json, cluster/hwcost.py) against the groups groups.json maps them to; the parts' sum against those groups' sum, and HWCOST's shares of its own total beside the groups' shares of theirs (the viewer's bar, D167) alone   the accelerator's shell inside the cluster (csr, ctrl, dp, the rest, the whole) against its point synthesized alone (points.json's `alone`, a row of results/forge/<tech>/synth_dc.csv)

Writes results/cluster/<tech>/breakdown.json; --md also prints the tables as Markdown. The macros' area is checked against synth_dc.csv's `macro_um2` (the TCDM banks and I-cache macros together). Standard library and arc/arc.py.

### cluster-energy

For every point of cluster/points.json that has its PrimePower reports (results/cluster/<tech>/power_reports/ <point>.zip, `pixi run cluster pwr` part 2), reads each window's power_hierarchy.rpt and sums each node's own dynamic power (internal + switching, its total minus its children's; leakage out) into cluster/groups.json's groups by the same rules (report/cluster_breakdown.py's `groups`), so the groups add up to the top's dynamic power. A window w of C_w cycles at t_clk (10 ns as the cuts read the run) gives each group g

E_g,w = (P_int + P_sw)_g,w * C_w * t_clk,    E_w = sum_g E_g,w,    E_span = sum_w E_w

over the span's windows (the first mark to the end of the last DMA out). Then, where they exist:

run     the run phase: each run window against the acc_config window before it (the idle reference, the same cluster with nothing moving but the clock): per group the energy per cycle in both, the run window's energy, and its part above idle, (e_run - e_idle) * C_run, which may be negative where the clock's booking moves (PITFALLS PT10's run note) hwcost  snax-forge's five energy parts (results/cluster/<tech>/hwcost/<point>.json, nJ per task) against the groups groups.json's `hwcost` maps them to, in the run window(s): the run's energy and its part above idle, each side's shares of its own five-part sum. HWCOST is an estimate with no bit-level switching; the shares are what is compared, not the absolute numbers alone   the accelerator's shell in the run window against its point measured alone (points.json's `alone`, a row of results/forge/<tech>/power_pt.csv, its busy window): energy and energy per cycle

Each window's top dynamic power must equal power_pt.csv's `e_dyn_pj` (the same report, PT's groups) within 0.01 %, or the point fails. Writes results/cluster/<tech>/energy.json; --md also prints the tables as Markdown. Standard library and arc/arc.py.

### cluster-sweep

Reads what cluster-breakdown and cluster-energy wrote (`breakdown.json`, `energy.json`) and lays out the run window only (`5_run`, the busy section) for the recipe's points, one per W, in order of W; `--points` names any points instead, in the order given, and `--out NAME` writes into `results/cluster/<tech>/NAME/`, the bars labelled by point, for a look, not committed.

- **energy:** the netlist's run-window energy in HWCOST's five parts (datapath, control, streamers, crossbar, memory; the groups `groups.json`'s `hwcost` maps to each), the groups HWCOST does not price as one more line, and HWCOST's five parts (nJ per task); shares of each side's own five-part sum, the netlist's also of its whole run window.
- **area:** the same layout in µm², the cluster's groups beside HWCOST's five parts.
- **alone:** the accelerator's shell in the run window and alone (`points.json`'s `alone`): cycles, pJ per cycle, nJ, µm².

A part's share is $s_p = E_p / \sum_q E_q$ over the five parts, on each side. No normalization, no check on the trend: the data is laid out, its reading is the user's. `sweep.csv` is long form (point, W, source, window, group, metric, value; source `gls` the netlist, `hwcost` snax-forge's estimate, `alone` the shell alone). The figures: `sweep_energy.png` and `sweep_area.png`, per W the netlist's bar beside HWCOST's, absolute on the left and in % of the five parts on the right; `sweep_energy_five.png` and `sweep_area_five.png`, the absolute panel alone with the five parts only, each bar's total above it. The bars stack memory, control, streamers, crossbar and datapath from the bottom, the netlist's not-priced part on top. `--md` prints the tables as Markdown.

## snb: the Snitch-only clusters

snax_cluster's own clusters with no accelerator (`cfg/snax_snitch_cluster_{1,5,9}.hjson`: 1, 5 or 9 rv32ima cores in one hive, the logarithmic TCDM interconnect, forge's 128 KiB L1), running snitch-forge's plain C kernels, as E11's baseline (X91, X92). `snb.py` drives them through the same four steps as a forge point, with cluster.py's and power.py's helpers; what differs is where the program comes from and what is checked.

`snb_points.json` has the configs and the kernels. A config is one netlist (`snitch1_cg`, `snitch5_cg`, `snitch9_cg`, clock-gated as forge's points), with its cfg path, cores, workers (compute cores; the one core of `_1` computes too), macros and the sha256 of the netlist the runs use. A run is `<config>_<kernel>_<type>` (e.g. `snitch1_cg_dot_int64`): the kernel's snitch-forge program at its sizes in the file and seed 42. Every make call names the config by its relative path (`CFG_OVERRIDE=cfg/snax_snitch_cluster_<n>.hjson`), as snax_cluster's apps Makefile builds snitch-forge only then.

| Step | What it does | Gates | Kept |
|---|---|---|---|
| `snb rtl RUN` | in the image: `make clean-sw`, `make sw` (the config's runtime), the kernel's plain and `QUIET=1` builds with the run's `TYPE`, `SEED` and sizes; data.h's first line checked; then rtl-gen, clustergen's memory list, X66's `tc_sram_impl.sv`, and the plain ELF on the RTL with the macros | `[SUCCESS]` and no `[FAILURE]`; `snitch-forge errors: 0`; the header line the run's (kernel, type, sizes, workers); the three sections' cycles and a compute line per worker; the macros compiled, nothing of tech_cells_generic's `tc_sram` | `rtl/snb/<run>.zip` (both ELFs, data.h, the marks' legend, `sw.log`, `provenance.json`); `rtl/` in `sim/runs/snb/nangate45/<run>.zip`; a row of `results/snb/nangate45/runs.csv` |
| `snb syn CONFIG` | as `cluster syn` through syn.py's `snb` source (top `snax_snitch_cluster_wrapper`). A kept run is adopted, with no DC, when its netlist is the config's `netlist_sha256`, its row is ok and snax_cluster changed no RTL since its commit (`--again` runs DC anyway) | as `cluster syn` | `syn/runs/snb/nangate45/<config>.zip`; `results/snb/nangate45/synth_dc.csv` and `reports/<config>.zip` |
| `snb gls RUN` | the config's netlist built as `cluster gls` does (`SIM_TYPE=gate_level_sim`), the swap checked with this wrapper, then the plain ELF on it | the program's gates as `rtl`; the swap (wrapper and cells from `work-vsim/gls`, `+initreg+0`, `+acc=n`, no `[tc_sram_impl]` print). Recorded, not gated: each section's cycles beside the RTL run's | `gls/` and `build/` in the run zip; the `gls_*` columns of `runs.csv` |
| `snb pwr RUN` | part 1 as `cluster pwr`'s (the quiet ELF, power.py's do-file with this wrapper's `obs_o`, the windows from snitch-forge's marks, the cut, a SAIF per window); part 2 is power.py's own, with this cluster's `Site` | the run passes with no program output; X9's SAIF checks; at least 95 % of the driven nets annotated. Recorded, not gated: each window's cycles beside the plain RTL run's section | `pwr/` and `pt/` in the run zip; `results/snb/nangate45/power_pt.csv` and `power_reports/<run>.zip` |

Left out against a forge point (X91): the plain RTL run beside the macro run, D123 and the expected file (there is no SNAX-GVSoC model of these programs; the program checks its own result against data.h's golden), the `[tc_sram_impl]` count, RAMCOUNT, and the 10 % timing gates at gate level and in the windows. Every run, RTL or netlist, uses its own do-file (`onfinish stop`, `run -all`, `quit -f`) in place of VSIM_FLAGS' `log -r /*`, so no waveform log is written. A new ELF (another sha256 in `rtl`) empties the run's `gls_*` columns of `runs.csv`.

### E11's measures: `pixi run snb-report`

`report/snb_report.py` reads the committed results only and writes `results/snb/nangate45/e11.json` (`--md` prints the tables).

- **Area,** $A$: DC's total of the config, and its groups (`groups.json`, the logarithmic interconnect's rule included) in four coarse parts that add up to it; forge's four accelerator groups must be empty here.

| Part | Groups |
|---|---|
| memory | `tcdm_banks`, `tcdm_logic` |
| interconnect | `tcdm_interconnect` |
| cores | `cores` (with the shared mul/div), `icache_macros`, `icache_logic`, `peripherals` |
| rest | `dma`, `axi`, `others`, `acc_interface` (the cores' SNAX CSR translators, 1,595 µm² per core) |

- **Operations,** $n_\text{op}$: from the kernel's maths at its sizes (`snb_points.json`'s `n_op`), never from instructions, so the extra instructions int64 takes on RV32 are cost and not work; a multiply-accumulate counts two.
- **Cycles,** $C_\text{run}$: the plain RTL run's `snitch-forge cycles run`, core 0's `mcycle` between the barrier after DMA in and the one before DMA out; the same barriers bound the quiet build's run window, whose cycles are listed beside it.
- **Area efficiency,** with $t_\text{clk} = 10$ ns:

$$\eta_A = \frac{n_\text{op}}{C_\text{run}\thinspace t_\text{clk}\thinspace A} \quad [\text{GOPS/mm}^2]$$

- **Energy per task,** $E_\text{run}$: the run window's dynamic energy as power_pt.csv has it (internal plus switching, the macros as PT measures them), $E_\text{run} = P_{\text{dyn},\text{run}}\thinspace C_w\thinspace t_\text{clk}$ with $C_w$ the window's cycles, and $\eta_E = n_\text{op} / E_\text{run}$ in op/pJ.
- **Leakage,** a side number (X92): $E_\text{leak} = P_\text{leak}\thinspace C_w\thinspace t_\text{clk}$, $P_\text{leak}$ the window's `Cell Leakage Power` in power.rpt, with the macros' part beside it; never added into $E_\text{run}$.

Worked example, dot at int64 on `snitch9_cg` (R7's numbers): $n_\text{op} = 2 \cdot 2048 = 4096$, $C_\text{run} = 11944$, $A = 1.185665$ mm², so

$$\eta_A = \frac{4096}{11944 \cdot 10^{-8}\ \text{s} \cdot 1.185665\ \text{mm}^2} \approx 2.89 \cdot 10^{7}\ \text{op/s/mm}^2 = 0.0289\ \text{GOPS/mm}^2$$

against 1.89 GOPS/mm² for forge's `dot3_w16_cg` (4096 op in 185 cycles on 1.173 mm²).
