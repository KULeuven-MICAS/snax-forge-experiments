# snax-forge-experiments

The measuring side of [snax-forge](https://github.com/KULeuven-MICAS/snax-forge): synthesis, power, memory and cost flows that depend on a technology, with their results committed. It measures snax-forge's generated accelerators and clusters, the HLS tools they are compared with, and the building blocks snax-forge's cost model (HWCOST) is priced from. Nangate 45 nm with Design Compiler, Questa and PrimePower; clock-gated synthesis is the basis (X79 · X87 · X88).

- **Start here:** [`docs/README.md`](docs/README.md), then [`docs/TOOL.md`](docs/TOOL.md) for every command and the setup (sibling repositories, tools, licences).
- **Before changing a flow:** the decisions it touches ([`docs/DECISIONS.md`](docs/DECISIONS.md), X1, X2, ...) and the tool pitfalls ([`docs/PITFALLS.md`](docs/PITFALLS.md)).

## Layout

| Folder | What it holds |
|---|---|
| `syn/` | Design Compiler: `syn.py`, the tech file, the scripts ([`syn/README.md`](syn/README.md)) |
| `sim/` | the power flow: `pwr.py`, the testbench adapters per source (`sources/`), the fixed testbenches (`tb/`), PT's and DC's scripts ([`docs/power.md`](docs/power.md)) |
| `forge/` | snax-forge's points (`points.json`), their bundling (`bundles.py`) and what the power flow asks snax-forge (`query.py`) |
| `char/` | the blocks alone: their points and generation ([`results/char/README.md`](results/char/README.md)) |
| `strm/` | the streamer reader and interconnect points ([`strm/README.md`](strm/README.md)) |
| `ram/` | CACTI and the SRAM macros ([`ram/README.md`](ram/README.md)) |
| `cluster/` | a design through the whole cluster ([`cluster/README.md`](cluster/README.md)) |
| `report/` | the scripts that turn results into tables, pages and figures |
| `arc/`, `tmp/` | the zip helpers (X51); `tmp/` holds one point unpacked at a time and is empty otherwise |
| `rtl/` | the bundles, one zip per point (not committed; rebuilt from the commit their rows name) |
| `results/<source>/<tech>/` | per source: `synth_dc.csv`, `synth_dc_modules.csv`, `power_pt.csv`, `power_pt_modules.csv`, the report zips; run notes in `results/<source>/runs/` |
| `results/strm/`, `results/ram/`, `results/char/` | the tables snax-forge reads: `streamer.csv`, `xbar.csv`, `xbar_kinds.json` ([`docs/cost_tables.md`](docs/cost_tables.md)); `ram_table.csv`; `char_cg.json` |
| `results/cluster/` | the cluster points: synthesis, power per window, HWCOST, the breakdowns and the sweep over W |
| `results/compare*` | forge against the HLS tools: `compare_done.csv`, `compare_untiered.csv` (raw rows) and `compare/` (one page and two figures per kernel) |
| `results/runs/` | run notes of rounds that span several sources |
