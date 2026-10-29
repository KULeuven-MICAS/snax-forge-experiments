# docs

The settled choices of this repo and the tool nuances that give wrong numbers without an error. Check a new prompt, script or result against both before trusting it.

- [`DECISIONS.md`](DECISIONS.md): what was decided, numbered X1, X2, ..., each with its date, reason and source.
- [`PITFALLS.md`](PITFALLS.md): per tool (DC, libraries, Questa, PrimeTime, licences), each symptom with its cause, its fix or check, and the run note that found it.

Vitis-side nuances (pragmas, ports, the cases, cosim) live in hls-exercises' [`docs/HLS_VS_FORGE.md`](https://github.com/rgantonio/hls-exercises/blob/main/docs/HLS_VS_FORGE.md).

## Folders

| Folder | What it holds |
|---|---|
| `syn/` | ASIC synthesis with Design Compiler: `syn.py` (the driver), `tech/<tech>.json` (one per technology), `scripts/` (`dc_syn.tcl`, `constraints.sdc`). See [`syn/README.md`](../syn/README.md). Runs go to `syn/runs/hls/<tech>/...`, which git ignores and which is kept (X6): the mapped netlists there are what simulation and power read. |
| `sim/probe/` | Power step 0, by hand, on `done/vecadd/opt_w8`: the TB, the vsim do-file, `pt_power.tcl` (PrimePower), `dc_readback.tcl` (DC on the same netlist), `make_vectors.py`, `saif_compare.py`, `pwr_table.py`. Scratch output goes to `sim/runs/`, which git ignores. |
| `results/hls/<tech>/` | The synthesis results per technology (`nangate45`, `nangate15`): `synth_dc.csv`, `synth_dc_modules.csv`, and per point the eight reports in `KEPT_REPORTS` under `reports/<tier>/<kernel>/<point>/`. `syn/syn.py` writes here. |
| `results/hls/runs/` | Run notes, one per run, named `<date>_<what>.md`, with a folder of the same name when the note keeps reports or logs. Notes before 28 Oct 2026 are on gscl45nm (retired, X1). |
| `results/hls/` | hls-exercises' bench summaries: `hls_cycles.csv`, `hls_loops.csv`, `forge_cycles.csv`, `report_<tier>.md`. |

## Sibling repos

Checked out next to this one, hooked by hand, with no submodules:

```
<parent>/
  snax-forge-experiments/   this repo
  hls-exercises/            rtl/<tier>/<kernel>/<point>/filelist.f (and sizes.txt, params.json)
  RTL_flow_Nangate15/       tech/nangate45/NangateOpenCellLibrary_typical.db, NangateOpenCellLibrary.v
                            tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db, NanGate_15nm_OCL_functional.v
```

Elsewhere: `SYN_RTL`, `SYN_LIB_NANGATE45`, `SYN_LIB_NANGATE15` (`syn/README.md`).

## Environment

- Python: the repo's pixi workspace (`pixi.toml`: Python 3.11, numpy). Run `pixi install` once from the repo root, then every script through pixi: `pixi run syn ...`, `pixi run python <script> ...` (X15). The host's `python3` is 3.6 and cannot run the scripts.
- EDA tools come from the shell's PATH, or from `DC_SHELL`, `PT_SHELL` and `LMUTIL` pointing at the binary (`syn.py` reads `DC_SHELL`; the power flow reads the other two). Questa (`vlog`, `vopt`, `vsim`) and `vcd2saif` come from PATH. The versions in use are in the step 0 note's Tools table (`results/hls/runs/2026-10-29_pwr_step0.md`).
- Licences: check before a batch with `lmutil lmstat -a -c <server>` (Synopsys `1709@licserv`, Mentor `1717@licserv`, from `SNPSLMD_LICENSE_FILE` and `MGLS_LICENSE_FILE`), and size the parallel jobs from the free counts (X16).
