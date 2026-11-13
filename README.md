# snax-forge-experiments

The measuring side of snax-forge: synthesis, power, memory and cost flows that depend on a technology, with their results committed. It measures snax-forge's generated accelerators and clusters, the HLS tools they are compared with, and the building blocks snax-forge's cost model (HWCOST) is priced from. Nangate 45 nm throughout (15 nm rows from before 6 Nov stay as data).

**Docs:** [`docs/`](docs/README.md): the decisions (`DECISIONS.md`, X1, X2, ...), the tool pitfalls (`PITFALLS.md`), the power flow (`power.md`) and the cost tables (`cost_tables.md`). Check new work against the decisions and pitfalls it touches.

## What changed

| Date | Task | What it added | Decisions |
|---|---|---|---|
| 27–29 Oct | flow | Design Compiler on Nangate 45 and 15 nm; the power flow (zero-delay Questa, vcd2saif, PrimePower) | X1–X20 |
| 31 Oct–2 Nov | SYN1, SYN2 | snax-forge's accelerators beside Vitis at one 2048-element task | X21–X25 |
| 3 Nov | CHAR1 | snax-forge's blocks alone; `char.json`, the block model | X28–X37 |
| 5 Nov | HSYN1 | Bambu and XLS beside Vitis; the comparison CSVs | X38–X45 |
| 6 Nov | RAM1, ARC1 | SRAM banks from CACTI, as a table and as macros; every output zipped | X47–X51 |
| 6–7 Nov | STRM1 | the streamer reader and the interconnect tables | X52–X54 |
| 10 Nov | CSYN1 A | forge's untiered points, DaCe's buffers as macros, `results/compare/` | X55–X64 |
| 11 Nov | CTRL2 | forge's leaner control; BUSY_COUNTER out of every figure | X65 |
| 11 Nov | CSYN1 B | a snax-forge design through the whole cluster (RTL, synthesis, netlist); the interconnect's input kinds; the area in groups against HWCOST | X66–X72 |
| 12 Nov | CORE1, PWR1 | the one-core cluster; the cluster's energy per program section | X73–X76 |
| 12 Nov | docs | forge's ctrl + datapath figure per kernel; the docs trimmed (older wording in git history) | X77 |
| 12–13 Nov | PWR2 | dot 3 at W = 2 to 32 through the whole cluster flow overnight; the sweep beside HWCOST | X78 |

## Sibling repos

Checked out next to this one, no submodules. PDK files are never committed.

```
<parent>/
  snax-forge-experiments/   this repo
  snax-forge/               the generator: recipes, bundles, HWCOST
  snax_cluster/             the cluster (CSYN1 Part B on)
  hls-exercises/            Vitis and Bambu points: rtl/<tier>/<kernel>/<case>_w<W>/filelist.f
  dslx-exercises/           Google XLS points: rtl/<tier>/<kernel>/xls_w<W>/filelist.f
  RTL_flow_Nangate15/       tech/nangate45/, tech/nangate15/: the libraries and cell models
```

Environment variables, tools and licences are in [`docs/README.md`](docs/README.md#environment).

## Layout

| Folder | What it holds |
|---|---|
| `syn/` | Design Compiler: `syn.py`, one tech file per library, the scripts; sources `hls` (Vitis), `bambu`, `xls`, `forge`, `char`, `streamer`, `xbar`, `xbar_mix`, `cluster` ([`syn/README.md`](syn/README.md)) |
| `sim/` | the power flow: `pwr.py`, the TB adapters per source, the fixed TBs, PT's script ([`docs/power.md`](docs/power.md)) |
| `forge/` | snax-forge's points (`points.json`) and their bundling (`bundles.py`, `query.py`) |
| `char/` | CHAR1's block points and their generation ([`results/char/README.md`](results/char/README.md)) |
| `ram/` | CACTI and the SRAM macros ([`ram/README.md`](ram/README.md)) |
| `strm/` | the streamer and interconnect points ([`strm/README.md`](strm/README.md)) |
| `cluster/` | a design through the whole cluster ([`cluster/README.md`](cluster/README.md)) |
| `report/` | the scripts that turn results into tables and pages: `compare.py`, `compare_hls.py`, `char_export.py`, `char_table.py`, `strm_table.py`, `xbar_kinds.py`, `cluster_breakdown.py`, `cluster_energy.py`, `cluster_sweep.py`, `import_cycles.py` |
| `arc/`, `tmp/` | the zip helpers (X51); `tmp/` holds one point unpacked at a time and is empty otherwise |
| `rtl/` | the bundles, one zip per point (not committed; rebuilt from the commit their rows name) |
| `results/<source>/<tech>/` | per source and technology: `synth_dc.csv`, `synth_dc_modules.csv`, `power_pt.csv`, `power_pt_modules.csv`, the report zips; run notes in `results/<source>/runs/` |
| `results/compare*` | the comparison: `compare_done.csv`, `compare_untiered.csv` (raw rows, X45) and `compare/` (one page and two figures per kernel, X64, X77) |
| `results/ram/`, `results/strm/`, `results/char/` | the tables snax-forge reads: `ram_table.csv`; `streamer.csv`, `xbar.csv`, `xbar_kinds.json` ([`docs/cost_tables.md`](docs/cost_tables.md)); `char.json` |
| `results/hls/` | Vitis's points, plus hls-exercises' bench summaries (`hls_cycles.csv`, `report_<tier>.md`) |
| `results/runs/` | run notes of rounds that span several sources |

## Run

```bash
pixi install                                                        # once (X15)
pixi run syn list 'done/vecadd/*'                                   # a source's points (--source, default hls)
pixi run syn run done/vecadd/opt_w8 --tech nangate45                # one point at 10 ns
pixi run pwr run 'done/vecadd/*' --tech nangate45 --size n2048      # their energy at the reference task (docs/power.md)
pixi run forge-rtl -j 2                                             # snax-forge's bundles into rtl/forge/
pixi run syn run 'done/*/forge*' --source forge --tech nangate45    # and their synthesis; pwr likewise
pixi run import-cycles                                              # Bambu's and XLS's cycle CSVs with SOURCE (X42)
pixi run compare && pixi run compare-hls                            # the comparison CSVs and pages (X45, X64)
pixi run char-export && pixi run char-table                         # CHAR1's char.json and table
pixi run ram table                                                  # the SRAM table (ram/README.md)
pixi run strm-table && pixi run xbar-kinds                          # the streamer and interconnect tables
pixi run cluster rtl|syn|gls|pwr dot3_w16                           # the whole cluster (cluster/README.md)
pixi run arc check                                                  # nothing left unzipped at the end of a round (X51)
```

Parallel runs take their size from free licences and stay within 16 cores (X59).
