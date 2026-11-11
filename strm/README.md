# strm

STRM1: the area and dynamic energy of snax_cluster's streamer reader and TCDM sparse interconnect on Nangate 45 nm, as tables snax-forge's HW cost model reads (docs X52, X53). A reader's cost also stands for a writer's.

## The flow

```bash
pixi run strm-rtl [--only POINT ...] [--set streamer|xbar] [--list]      # rtl/streamer/, rtl/xbar/ (one zip per point)
pixi run strm-rtl --set xbar_mix                                         # CSYN1 R3c: rtl/xbar_mix/, from rtl/xbar/'s SV
pixi run syn run '*' --source xbar_mix --tech nangate45 -j 4 --cores 4
pixi run python strm/test_xbar_mix.py
pixi run syn run '*' --source xbar --tech nangate45 -j 4 --cores 4       # DC, largest first
pixi run syn run '*' --source streamer --tech nangate45 -j 4 --cores 4
pixi run pwr run '*' --source xbar --tech nangate45                      # zero-delay sim, SAIF, PT (inputs <= banks)
pixi run pwr run '*' --source streamer --tech nangate45
pixi run strm-table [--loo]                                              # results/strm/nangate45/streamer.csv, xbar.csv
pixi run strm-table-test
```

## Files

| File | What it holds |
|---|---|
| `grid.json` | the snax_cluster repo, checkout path, branch and commit; the image; the technology; per set (`streamer`, `xbar`) the point name pattern, the axes and the fixed values with where each comes from |
| `gen.py` | `pixi run strm-rtl`: the bundles (below) and `flop_bits`, the register and memory bits a bundle's RTL declares, which `syn.py`'s flop check compares with DC's flops |
| `xbar_mix.py` | CSYN1 R3c (X70): `wrapper(sv_text, ro, wo)`, the module `xbar_mix` around a point's `SparseInterconnect` with read-only and write-only inputs and the cluster template's ties; `ports(sv_text)`, the module's ports as firtool writes them |
| `test_xbar_mix.py` | its test on a stub SparseInterconnect (`pixi run python strm/test_xbar_mix.py`; the Verilator lint part runs only where `verilator` is on PATH, not on the host) |

## Generation (`gen.py`)

- snax_cluster is read only. Its checkout must be at `grid.json`'s commit; the sources are exported from that commit with `git archive` (`hw/chisel`, `hw/chisel_acc`, and the chisel-float submodule at its gitlink, PITFALLS SC4) into `tmp/strm/src/`, where sbt compiles, so nothing is built inside snax_cluster.
- One sbt call per batch in the image (`grid.json`'s `image`), with the home folder's sbt, coursier and firtool caches mounted under `/root` (PITFALLS SC6): `compile`, then one `runMain` per point.
- Reader: `snax.streamer.StreamerGen`, the hjson entry point snaxgen uses: one reader with `temporal_dim` L, `num_channel` C, spatial bounds `[C]`, `fifo_depth` D (both the address and the data buffer depth), 64-bit TCDM of 128 KiB, no datapath extension, no configurable channel or byte mask (as snax-forge's `platforms/snax_forge_cluster.hjson`). The zip keeps `strm__C0_Reader` and the modules under it (PITFALLS SC1, SC2), not the CSR manager.
- Interconnect: `snax.sparse_interconnect.SparseInterconnectGen` with `NumInp`, `NumOut` and the widths snaxgen gives a 128 KiB TCDM (`grid.json`, `xbar.fixed._doc`); top `SparseInterconnect`.
- A point's zip, `rtl/streamer/d<D>_l<L>_c<C>.zip` or `rtl/xbar/i<inputs>_b<banks>.zip` (git-ignored, X51): `<top>.sv` (firtool's macro preamble, then the top's modules, children first), `filelist.f` (`# top: <top>`, then `<top>.sv`), `config.json` (what was generated; a point whose zip has the same `config.json` is skipped), `point.json` (versions, modules, the runMain seconds) and `gen.log`. `tmp/strm/` is deleted at the end, also on a failure. sbt stops at the first failing point (PITFALLS SC5): the points after it are reported as not run and made by the next call.

## The xbar_mix set (CSYN1 R3c, X70)

- What it measures: the TCDM interconnect as the cluster drives it. `grid.json`'s `xbar_mix`: for inputs {16, 32, 64} x banks {16, 32, 64}, three mixes, `r0_w0` (every input read-write), `r<inputs>_w0` (every input read-only) and `r0_w<inputs>` (every input write-only); then `i36_b32_r0_w0` and the cluster's own mix `i36_b32_r32_w1` (32 reader channels, one writer, the two cores and the AXI port read-write). 29 points.
- No sbt: a point's `SparseInterconnect.sv` is its base xbar point's, the same bytes from `rtl/xbar/i<inputs>_b<banks>.zip`. A missing or stale base is generated first in the same call, as the xbar set does (sbt, so snax_cluster must be at `grid.json`'s commit). `i36_b32` is not on xbar's axes: it is `xbar`'s `extra` list, the points after the axes' product.
- A point's zip, `rtl/xbar_mix/i<inputs>_b<banks>_r<ro>_w<wo>.zip`: `SparseInterconnect.sv`, `xbar_mix.sv` (`xbar_mix.wrapper`), `filelist.f` (`# top: xbar_mix`, both files), `config.json` (the base point's config with `set`, `point`, `params` and `top` its own, plus `base`, `ro`, `wo` and `xbar_mix_md5`, `xbar_mix.py`'s md5, so an edit of the wrapper remakes every point) and `point.json` (the base's tool versions and commits, the SV's md5, both modules' port counts).

## Where the rest is

- DC: `syn/syn.py --source streamer|xbar` (`syn/README.md`, Sources): runs in `syn/runs/<source>/nangate45/`, results in `results/<source>/nangate45/synth_dc.csv`, with the flop check.
- Power: `sim/pwr.py --source streamer|xbar` with `sim/sources/strm.py` (`docs/power.md`, Streamer and interconnect): runs in `sim/runs/<source>/nangate45/`, results in `results/<source>/nangate45/power_pt.csv`.
- Tables and interpolation: `report/strm_table.py` (X53), `results/strm/nangate45/`.
- Run notes: `results/strm/runs/` (R0, the probe; R1, the grid); xbar_mix's in `results/xbar_mix/runs/`.
