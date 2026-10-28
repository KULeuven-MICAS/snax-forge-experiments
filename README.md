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
  FreePDK45/                osu_soc/lib/files/gscl45nm.db
```

## Layout

| Folder | What it holds |
|---|---|
| `syn/` | ASIC synthesis with Design Compiler on FreePDK45 ([`syn/README.md`](syn/README.md)). Runs stay local in `syn/runs/`. |
| `results/hls/` | hls-exercises' bench summaries (`hls_cycles.csv`, `hls_loops.csv`, `forge_cycles.csv`, `report_<tier>.md`), the synthesis summary `synth_dc.csv`, and the run notes in `runs/`. hls-exercises' `bench/bench.py` writes here. |

Planned:

- `ram/`: OpenRAM macros, with a `tc_sram`-compatible wrapper for each.
- `cost/`: the fitted area and energy tables per technology, for snax-forge's first-order estimates.
- `results/forge/`: snax-forge's accelerators.
- An open 15 nm library next to FreePDK45.

## Run

```bash
python3 syn/syn.py list 'done/vecadd/*'     # hls-exercises' points
python3 syn/syn.py run done/vecadd/opt_w8   # one point at 10 ns
python3 syn/syn.py summary                  # every run so far
```

Python 3.7 or newer, standard library only. On the ESAT servers, use `python3.11`.
