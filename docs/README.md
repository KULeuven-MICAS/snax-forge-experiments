# docs

The settled choices of this repo and the tool nuances that give wrong numbers without an error. Check a new prompt, script or result against both before trusting it.

- [`DECISIONS.md`](DECISIONS.md): what was decided, numbered X1, X2, ..., each with its date, reason and source.
- [`PITFALLS.md`](PITFALLS.md): per tool (DC, libraries, Questa, PrimeTime, licences, CACTI, environment), each symptom with its cause, its fix or check, and the run note that found it.
- [`power.md`](power.md): how to run `pwr`, its stages, the run folder and what is committed.
- [`cost_tables.md`](cost_tables.md): the cost tables HWCOST reads (SRAM banks, streamer reader, sparse interconnect): how each number is measured, how a cost is read between grid points (step by step, with worked examples), how well it agrees, and what the numbers assume; written to be reused as a methods section (X47–X54).
- [`notes_control_boundary.md`](notes_control_boundary.md): working notes from SYN1's review: forge's control against HLS's, register by register, the block boundary, the HLS register stage, and the options to pick from.

Vitis-side nuances (pragmas, ports, the cases, cosim) live in hls-exercises' [`docs/HLS_VS_FORGE.md`](https://github.com/rgantonio/hls-exercises/blob/main/docs/HLS_VS_FORGE.md).

## Folders

| Folder | What it holds |
|---|---|
| `syn/` | ASIC synthesis with Design Compiler: `syn.py` (the driver), `tech/<tech>.json` (one per technology), `scripts/` (`dc_syn.tcl`, `constraints.sdc`). See [`syn/README.md`](../syn/README.md). Runs go to `syn/runs/<source>/<tech>/...` (`hls`, `bambu`, `xls`, `forge`, `char`), one zip per point (X51), which git ignores and which is kept (X6): the mapped netlists there are what simulation and power read. |
| `sim/` | The power flow ([`power.md`](power.md)): `pwr.py` (the driver), `sources/hls.py` (tb.json, X14), `ref.py` (references), `tb/` (fixed SystemVerilog), `scripts/` (`run.do`, `pt_power.tcl`). Runs go to `sim/runs/`, one zip per point, which git ignores; SAIFs stay in the zips (X18, X51). |
| `sim/probe/` | Power step 0, by hand, on `done/vecadd/opt_w8`: the TB, the vsim do-file, `pt_power.tcl` (PrimePower), `dc_readback.tcl` (DC on the same netlist, used by `pwr setup-check`), `make_vectors.py`, `saif_compare.py`, `pwr_table.py`. Kept unchanged. |
| `results/hls/<tech>/` | The results per technology (`nangate45`, `nangate15`): `synth_dc.csv`, `synth_dc_modules.csv`, and per point the reports in `KEPT_REPORTS` as one zip, `reports/<tier>/<kernel>/<point>.zip` (`syn/syn.py`, X51); `power_pt.csv`, `power_pt_modules.csv` and `power_reports/<tier>/<kernel>/<point>.zip` (`sim/pwr.py`, X20, X51). |
| `results/hls/runs/` | Run notes, one per run, named `<date>_<what>.md`, with a folder of the same name when the note keeps reports or logs. Notes before 28 Oct 2026 are on gscl45nm (retired, X1). |
| `results/bambu/`, `results/xls/` | Bambu's and XLS's cycle CSVs with their `SOURCE` files (X42), and their synthesis results per technology from HSYN1 on. |
| `results/runs/` | Run notes of rounds that span several sources (HSYN1 on). |
| `results/hls/` | Vitis (X38). hls-exercises' bench summaries: `hls_cycles.csv`, `hls_loops.csv`, `forge_cycles.csv`, `report_<tier>.md`. `forge_cycles.csv` stays unchanged. |
| `results/forge/<tech>/`, `results/forge/runs/` | snax-forge's points (X21 to X23): the same files as `results/hls/<tech>/`, with `recipe`, `W` and `snax_forge_commit`; SYN1's run notes. |
| `rtl/` | The bundles forge/bundles.py, char/blocks.py and strm/gen.py write, one zip per point: `rtl/forge/<point>.zip`, `rtl/char/<point>.zip`, `rtl/streamer/<point>.zip`, `rtl/xbar/<point>.zip` (git-ignored; a bundle is rebuilt from its commit). |
| `strm/`, `results/strm/` | STRM1: snax_cluster's streamer reader and TCDM sparse interconnect (X52, X53). `strm/grid.json` (the grid, the snax_cluster commit, the image) and `strm/gen.py` (`pixi run strm-rtl`, the bundles in `rtl/streamer/` and `rtl/xbar/`); see [`strm/README.md`](../strm/README.md). DC and power through `syn.py` and `pwr.py` `--source streamer` and `--source xbar`, results in `results/streamer/<tech>/` and `results/xbar/<tech>/` (`synth_dc.csv`, `power_pt.csv`, report zips); the tables snax-forge reads, `results/strm/<tech>/streamer.csv` and `xbar.csv` (`report/strm_table.py`, with the reference interpolation); run notes in `results/strm/runs/`. |
| `arc/`, `tmp/` | `arc/arc.py`, the zip helpers every script imports (`pack`, `read`, `names`, `unpacked`, `check`, X51), and its tests; `tmp/` (git-ignored) holds the folders it unpacks into, one point at a time, and is empty when nothing runs. |
| `ram/`, `results/ram/` | RAM1: SRAM bank area and energy per access from CACTI 7 at 45 nm (X47): `ram/ram.py`, CACTI in `ram/cacti/` and runs in `ram/runs/` (both git-ignored): the CACTI cache `ram/runs/cacti.zip`, the macros `ram/runs/lib/<name>.zip` (X51); the lookup table `results/ram/nangate45/ram_table.csv` (X48) and run notes in `results/ram/runs/`. See [`ram/README.md`](../ram/README.md). |
| `cluster/` | CSYN1 Part B: a snax-forge design in snax_cluster's whole cluster (X66, X67). `points.json` (the points: `point`, `recipe`, `W`, `sets`, and `srams`, the macro instances the cluster holds; and the two images), `cluster.py` (`pixi run cluster rtl <point> [--allow-branch]`; `syn` in R3, `gls` in R4), `mem.py` (the cluster's `tc_sram_impl.sv`, the macros' models and `sram_models.f` from clustergen's memory list, X66), `check.py` (D123 and the run checks), their tests `test_mem.py` and `test_check.py` (`pixi run python cluster/test_<name>.py`), and `eqv_tb.sv` (the Verilator equivalence bench of `tc_sram_impl.sv` against tech_cells_generic's, with its result in its header). The point's work folder is `tmp/cluster/<point>/`, deleted when the step ends. |
| `rtl/cluster/` | The cluster points' bundles, one zip per point (`<point>.zip`, git-ignored, X51): `bundle/` (snax-forge's bundle folder with `forge_expected.txt`), `sw/forge.elf`, `forge.log`, `forge.txt` (forge's terminal output) and `provenance.json` (snax-forge commit, image and id, the command, the ELF's sha256). The step's results go to `sim/runs/cluster/nangate45/<point>.zip`, `rtl/` for step 1 (X67). |
| `results/cluster/` | The cluster source's results (X67): run notes in `results/cluster/runs/`; `results/cluster/nangate45/` from step 2 (R3) on. |

## Zipped outputs (X51)

Every point's bulky outputs are one zip, read in place or unpacked into `tmp/` one point at a time (`CLAUDE.md`, "Files are zipped", holds the working rules). The commands:

```sh
pixi run arc check            # unpacked run folders, report folders not zipped, tmp/ leftovers, inodes per folder
pixi run arc ls ZIP           # a zip's members and sizes
pixi run arc cat ZIP MEMBER   # one member on stdout
pixi run arc migrate [KIND]   # convert folders left from before X51 (rtl syn sim ram results; rerunnable)
pixi run arc-test             # arc/test_arc.py
```

`arc check` must say `nothing left over` at the end of a round. It allows only plain files that are not outputs of a point: `syn/runs/<source>/<tech>/summary.csv`, `sim/runs/**/batches.jsonl`, Questa's cell models in `sim/runs/<tech>/_cells/`, and `rtl/char/`'s `gen-block.json` and `char-rtl.log`.

## Sibling repos

Checked out next to this one, hooked by hand, with no submodules:

```
<parent>/
  snax-forge-experiments/   this repo
  hls-exercises/            rtl/<tier>/<kernel>/<point>/filelist.f (and sizes.txt, params.json): Vitis and Bambu
  dslx-exercises/           rtl/<tier>/<kernel>/xls_w<W>/filelist.f: Google XLS
  RTL_flow_Nangate15/       tech/nangate45/NangateOpenCellLibrary_typical.db, NangateOpenCellLibrary.v
                            tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db, NanGate_15nm_OCL_functional.v
```

Elsewhere: `SYN_RTL`, `SYN_RTL_XLS`, `SYN_LIB_NANGATE45`, `SYN_LIB_NANGATE15` (`syn/README.md`), and `SIM_HLS` for the hls-exercises checkout `sim/pwr.py` reads.

## Environment

- Python: the repo's pixi workspace (`pixi.toml`: Python 3.11, numpy). Run `pixi install` once from the repo root, then every script through pixi: `pixi run syn ...`, `pixi run pwr ...`, `pixi run python <script> ...` (X15). The host's `python3` is 3.6 and cannot run the scripts.
- EDA tools come from the shell's PATH, or from `DC_SHELL`, `PT_SHELL` and `LMUTIL` pointing at the binary (`syn.py` reads `DC_SHELL`, `sim/pwr.py` the other two). Questa (`vlog`, `vopt`, `vsim`) and `vcd2saif` come from PATH. The versions in use are in the step 0 note's Tools table (`results/hls/runs/2026-10-29_pwr_step0.md`).
- Licences: check before a batch with `lmutil lmstat -a -c <server>` (Synopsys `1709@licserv`, Mentor `1717@licserv`, from `SNPSLMD_LICENSE_FILE` and `MGLS_LICENSE_FILE`), and size the parallel jobs from the free counts (X16).
