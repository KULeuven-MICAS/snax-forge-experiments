# snax-forge-experiments

This repo collects the data from all snax-forge experiments in one place. The data comes from
several sources, and this repo also holds the scripts that depend on a technology: synthesis
scripts and post-synthesis simulations.

The tools that generate RTL never depend on this repo:

- [hls-exercises](https://github.com/rgantonio/hls-exercises) writes the HLS points.
- [snax-forge](https://github.com/KULeuven-MICAS/snax-forge) writes the generated accelerators.
- snax_cluster and snitch_cluster provide the clusters.

Each source writes its RTL with a `filelist.f`. This repo reads those from checkouts placed next
to it, hooked by hand, with no submodules. PDK files are never committed. They sit next to the
repo too, or are pointed to with environment variables.

```
<parent>/
  snax-forge-experiments/   this repo
  hls-exercises/            rtl/<tier>/<kernel>/<point>/filelist.f
  RTL_flow_Nangate15/       tech/nangate45/NangateOpenCellLibrary_typical.db
                            tech/nangate15/NanGate_15nm_OCL_typical_conditional_nldm.db
```

**Docs:** [`docs/`](docs/README.md) holds the settled decisions (`DECISIONS.md`, X1, X2, ...) and the tool pitfalls (`PITFALLS.md`); check new work against both.

## Layout

| Folder | What it holds |
|---|---|
| `syn/` | ASIC synthesis with Design Compiler on the Nangate 45 nm and 15 nm Open Cell Libraries, one tech file per technology in `syn/tech/` ([`syn/README.md`](syn/README.md)). Runs stay local in `syn/runs/`. |
| `results/hls/` | hls-exercises' bench summaries (`hls_cycles.csv`, `hls_loops.csv`, `forge_cycles.csv`, `report_<tier>.md`) and the run notes in `runs/`. hls-exercises' `bench/bench.py` writes here. |
| `sim/` | Gate-level simulation and PrimePower: `pwr.py` (the driver), `sources/` (tb.json adapters), `ref.py`, `tb/`, `scripts/`, and step 0's `probe/` ([`docs/power.md`](docs/power.md)). Runs stay local in `sim/runs/`. |
| `results/hls/<tech>/` | The results per technology (`nangate45`, `nangate15`): `synth_dc.csv`, `synth_dc_modules.csv` and every run's reports in `reports/` (`syn/syn.py`); `power_pt.csv`, `power_pt_modules.csv` and `power_reports/` (`sim/pwr.py`). |

Planned:

- `ram/`: OpenRAM macros, with a `tc_sram`-compatible wrapper for each.
- `cost/`: the fitted area and energy tables per technology, for snax-forge's first-order estimates.
- `results/forge/`: snax-forge's accelerators.

## Run

```bash
pixi install                                                  # once: the repo's Python (docs X15)
pixi run syn list 'done/vecadd/*'                             # hls-exercises' points
pixi run syn run done/vecadd/opt_w8 --tech nangate45          # one point at 10 ns on nangate45
pixi run syn summary                                          # every run so far, both technologies
pixi run pwr run 'done/vecadd/*' --tech nangate45             # dynamic energy of the synthesized points (docs/power.md)
```

## Synthesis

A technology is a JSON file in `syn/tech/`: the library, its time and capacitance units, the driving cell (`INV_X4`), the output load (four `INV_X4` inputs: 25.0 fF on nangate45, 13.2 fF on nangate15), the max transition (0.25 ns) and the wire-load setting (none applies on either). The constraints are written in ns and fF and scaled to the library's units at run time (nangate15's time unit is 1 ps), and DC stops before reading any RTL if the library's name or units differ from the tech file. The clock is 10 ns.

`results/hls/<tech>/synth_dc.csv` has one row per point: area (total, combinational, sequential, buf/inv), cells, critical path, slack and `fmax_mhz` in ns and MHz, max-cap and max-transition violations, dynamic and leakage power in uW, energy per cycle per power group in pJ, leakage per group in uW, the library's md5 and DC's version. `synth_dc_modules.csv` has one row per hierarchical cell (area and power). The columns are described in [`syn/README.md`](syn/README.md#columns).

Caveats:

- `clock_network` is the flops' clock-pin power only, with an ideal clock and no clock tree.
- Switching activity is DC's default, not simulated.
- `fmax_mhz` is a lower bound: at 10 ns DC does not upsize for speed.
- The HLS points are int64 only.
- Run notes in `results/hls/runs/` before 28 Oct 2026 are on gscl45nm (FreePDK45), now retired.

Python comes from the repo's pixi workspace (`pixi.toml`); the EDA tools from PATH (docs/README.md).
