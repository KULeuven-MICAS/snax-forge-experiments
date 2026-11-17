# The tools

Every command of snax-forge-experiments, grouped by job. Each entry says what the command does, what it reads and writes, the flags that matter, and an example; `...` stands for lines left out, and printed numbers are as printed when written. How each flow works inside is in the folder READMEs and [`power.md`](power.md); the decisions behind them are in [`DECISIONS.md`](DECISIONS.md).

| Job | Commands | Section |
|---|---|---|
| Set up | the sibling repos, `pixi install`, the tools and licences | 1 |
| Make the RTL of a source | `forge-rtl`, `char-rtl`, `strm-rtl`, `import-cycles` | 2 |
| Synthesize | `syn` | 3 |
| Measure the energy | `pwr` | 4 |
| Make the memories | `ram-build`, `ram` | 5 |
| Make the tables HWCOST reads | `strm-table`, `xbar-kinds`, `char-export`, `char-table` | 6 |
| Take a design through the whole cluster | `cluster`, `cluster/batch.sh`, `cluster-hwcost`, `cluster-breakdown`, `cluster-energy`, `cluster-sweep` | 7 |
| Compare forge with the HLS tools | `compare`, `compare-hls` | 8 |
| Keep the repository clean | `arc`, `test`, `lint` | 9 |

## 1. Set up

The sibling repositories sit next to this one, with no submodules; PDK files are never committed.

```
<parent>/
  snax-forge-experiments/   this repository
  snax-forge/               the generator: recipes, bundles, HWCOST
  snax_cluster/             the cluster
  hls-exercises/            Vitis and Bambu points: rtl/<tier>/<kernel>/<case>_w<W>/filelist.f
  dslx-exercises/           Google XLS points: rtl/<tier>/<kernel>/xls_w<W>/filelist.f
  RTL_flow_Nangate15/       tech/nangate45/: the library and its cell models
```

- **Python:** `pixi install` once, then everything through `pixi run` (X15). The server's `python3` is 3.6.
- **EDA tools** from PATH, or `DC_SHELL`, `PT_SHELL` and `LMUTIL` pointing at the binary; Questa (`vlog`, `vopt`, `vsim`) and `vcd2saif` from PATH (`vcd2saif` also next to `pt_shell`).
- **Inputs elsewhere than the sibling folders:** `SYN_RTL` (hls-exercises' `rtl/`), `SYN_RTL_XLS` (dslx-exercises' `rtl/`), `SYN_LIB_NANGATE45` (the `.db`), `SIM_HLS`, `SIM_XLS`, `SNAX_FORGE`, `SNAX_CLUSTER`.
- **Licences:** `lmutil lmstat -a -c <server>` (Synopsys `1709@licserv`, Mentor `1717@licserv`, from `SNPSLMD_LICENSE_FILE` and `MGLS_LICENSE_FILE`); size the parallel jobs from the free counts within 16 cores (X16 · X59), a cluster run alone on the host (X68). Count `Design-Compiler` and `DC-Expert` for synthesis, `msimhdlsim`, `PrimeTime` and `PrimePower` for power (PITFALLS L2, L4).
- **The file quota:** `quota -v` before a large batch; every point's outputs are one zip (CLAUDE.md, X51).

## 2. Make the RTL of a source

Each source's RTL is made from its own repository, one zip per point under `rtl/` (git-ignored), and records the commit it came from.

**`forge-rtl`** (`forge/bundles.py`) makes snax-forge's accelerator bundles for `forge/points.json`: per point, in the snax-forge checkout, `sandbox` at `--set W=<w>` (and the point's `sets`, then the global `--set` values), `design` on `platforms/snax_forge.json` and `bundle`, into `rtl/forge/<point>.zip` with a `point.json` (recipe, W, sets, dtypes, commit). A dirty snax-forge is refused unless `--allow-dirty` (X21); a point's `dtypes` are written into a temporary recipe (X57). The first point runs alone while hw/chisel's Emit classpath does not exist.

```bash
pixi run forge-rtl --list 'done/dot/*'
pixi run forge-rtl -j 6                              # every point
pixi run forge-rtl 'untiered/*' --set N=2048         # a global set after each point's own
```

**`char-rtl`** (`char/blocks.py`) makes the catalogue blocks alone for `char/points.json`, one call of snax-forge's `gen-block`, into `rtl/char/<point>.zip` (X28).

**`strm-rtl`** (`strm/gen.py`) makes snax_cluster's streamer reader, sparse interconnect and xbar_mix points for `strm/grid.json` (`--set streamer|xbar|xbar_mix`, `--only` names or globs), in snax_cluster's image, into `rtl/streamer/`, `rtl/xbar/`, `rtl/xbar_mix/`; details in [`strm/README.md`](../strm/README.md).

**`import-cycles`** (`report/import_cycles.py`) copies `bambu_cycles.csv` and `xls_cycles.csv` byte for byte from hls-exercises and dslx-exercises with a `SOURCE` file (X42); it refuses an untracked or modified file.

## 3. Synthesize: `syn`

Design Compiler on one technology per run, one point per DC run, the points from `--source` (`hls` the default, `bambu`, `xls`, `forge`, `char`, `streamer`, `xbar`, `xbar_mix`; `cluster` runs through `cluster syn`). Patterns are shell globs over `<tier>/<kernel>/<point>`; quote them. The sources, columns and what a run leaves are in [`syn/README.md`](../syn/README.md).

| Command | What it does |
|---|---|
| `syn list [PATTERN ...] [--source S] [--tech T]` | the points a pattern picks (with `--tech`, those with a row) |
| `syn run PATTERN ... --tech nangate45 [--source S] [--clock NS] [--cores N] [-j N] [--dry-run] [--sdf] [--clk-gate] [--with-ram]` | DC per point into `syn/runs/<source>/<tech>/<point>.zip`, a row in `results/<source>/<tech>/synth_dc.csv` and its report zip |
| `syn summary [PATTERN ...] [--source S] [--tech T]` | the rows so far |
| `syn check-ports [PATTERN ...] [--source S]` | the port guard alone (X39) |

- `--clk-gate` turns on DC's clock gating (X79 · X87 · X88): the run is tagged `_cg` and its rows have `clk_gate` 1.
- `-j` is DC runs at once, each holding a licence; `--cores` the cores per run (default 16); size both from the free licences within 16 cores (X16 · X59).
- `--dry-run` prints the commands; compare dry runs at `-j 1` (PITFALLS DC17).
- `--with-ram` builds a Vitis RAM from flops where no SRAM macro can be made (X62).

```bash
pixi run syn run done/vecadd/opt_w8 --tech nangate45 --dry-run
pixi run syn run 'done/*/forge*' --source forge --tech nangate45 -j 4 --cores 4 --clk-gate
pixi run syn summary --source forge --tech nangate45
```

Check each row's `status` (`ok`, `ok, timing violated`, `failed: ...`, `skipped: ...`) and, for streamer, xbar and char, the printed `flops <point> on <tech>: ...` lines (reported, not failed, X52 · X82).

## 4. Measure the energy: `pwr`

Dynamic energy of a mapped netlist from simulated activity (X7): a zero-delay Questa run of the netlist, its window cut into a SAIF, PrimePower on the same netlist. Each source's testbench, window and checks are in [`power.md`](power.md).

| Command | What it does |
|---|---|
| `pwr tbjson POINT [--source S] [--tech T]` | print the point's `tb.json` |
| `pwr run PATTERN ... --tech nangate45 [--source S] [--size TAG\|all] [--seed N] [--stim rand64\|forge] [-j N] [--cores C] [--clk-gate] [--initreg-seed N]` | the runs into `sim/runs/.../<point>.zip`, rows in `results/<source>/<tech>/power_pt.csv`, `power_pt_modules.csv` and `power_reports/` |
| `pwr setup-check --tech nangate45 [--source S] [--point P]` | PT against DC with forced activity on one point, per power group: a diagnostic (X25) |
| `pwr summary [PATTERN ...] [--source S] [--tech T]` | print `power_pt.csv` |
| `pwr modules --source S --tech T` | fill `power_pt_modules.csv`'s size column on old rows (a one-off) |

- `--size all` runs every size in the point's `sizes.txt`; `n2048` is the reference task (X24); `--source char`, `streamer` and `xbar` take no size.
- `--clk-gate` measures the `_cg` netlists; `--initreg-seed N` is a check with Questa's random register start that writes nothing to `results/` (PITFALLS Q9).
- Workers come from the free `msimhdlsim`, `PrimeTime` and `PrimePower` licences; PT threads are cores // workers.

```bash
pixi run pwr run 'done/vecadd/*' --tech nangate45                      # rand64, 64 beats, seed 0
pixi run pwr run 'done/*/forge*' --source forge --tech nangate45 --size n2048
pixi run pwr run '*' --source xbar --tech nangate45 --clk-gate         # the points with inputs <= banks
pixi run pwr setup-check --source forge --tech nangate45
```

Check each row's `status` and, for forge, `counter_diff` and `expected_diff` (within 5 % of the window, X56).

## 5. Make the memories: `ram-build`, `ram`

SRAM bank area and energy from CACTI 7 at 45 nm (X47), and the macros DC, Questa and PT see (X49); details in [`ram/README.md`](../ram/README.md).

| Command | What it does |
|---|---|
| `ram-build` | clone CACTI into `ram/cacti/` at `1ffd8df` and build it (once) |
| `ram point DEPTH WIDTH [--objective ...] [--ecc] [--tag T]` | one point: config, run, parse, print every column |
| `ram table [-j N]` | the lookup table, `results/ram/nangate45/ram_table.csv` (X48) |
| `ram lib DEPTH WIDTH [--mask 8]` | one macro (`.lib`, `.db`, `.v`) into `ram/runs/lib/<name>.zip` |
| `ram libs ram/macros.json [-j N]` | the macros of a list |

```bash
pixi run ram-build
pixi run ram table -j 32
pixi run ram lib 512 64 --mask 8         # ram/runs/lib/sram_d512_w64_m8.zip
```

## 6. Make the tables HWCOST reads

snax-forge copies these with its `pixi run import-costs`; what each number means, and how to read between grid points, is in [`cost_tables.md`](cost_tables.md).

**`strm-table`** (`report/strm_table.py`) joins the streamer's and interconnect's gated `synth_dc.csv` and `power_pt.csv` rows into `results/strm/<tech>/streamer.csv` and `xbar.csv` (X52 · X82, X83 · X85); `--loo` also prints the leave-one-out check of the interpolation (X53 · X54).

```
$ pixi run strm-table
results/strm/nangate45/streamer.csv: 168 rows, 168 ok
results/strm/nangate45/xbar.csv: 27 rows, 27 ok
```

**`xbar-kinds`** (`report/xbar_kinds.py`) fits the interconnect's read-only and write-only inputs from the xbar_mix rows into `results/strm/<tech>/xbar_kinds.json`: the factor form and the crosspoint form, with their checks against the 36-input points and the cluster (X71).

**`char-export`** (`report/char_export.py`) writes the block model, `results/char/<tech>/char.json`, from the clock-gated rows (X37, X83 · X85): a clock gate counts as a sequential cell, the control factor is the mean over the tier-done forge points with a power row. It prints each block whose sequential cells differ from its bits (its clock gates).

**`char-table`** (`report/char_table.py`) writes `results/char/char_table.md`, every number of the block model and its known limits.

## 7. Take a design through the whole cluster

A cluster point (`cluster/points.json`) is a snax-forge design built into snax_cluster's whole cluster; the steps, their checks and what each keeps are in [`cluster/README.md`](../cluster/README.md). One cluster DC, Questa or PT run at a time (X68), and never snax_cluster's `clean-logs` after a run.

| Command | What it does |
|---|---|
| `cluster rtl POINT [--allow-branch]` | step 1: the bundle, then the RTL run, plain and with the SRAM macros, both checked with D123 |
| `cluster syn POINT [--cores 16] [--allow-branch]` | step 2: DC on the whole cluster |
| `cluster gls POINT [--allow-branch]` | step 3: the netlist in step 1's testbench, gated on data and timing (X67 · X81 · X84) |
| `cluster pwr POINT [--cores 16] [--again] [--allow-branch]` | step 4: one VCD of the quiet build, one SAIF per program section, one PT session (X20 · X60 · X74) |
| `cluster/batch.sh POINT ...` | the steps of several points in series, overnight (`BATCH_OUT` names the log folder, `--from STEP` starts the first point later) |
| `cluster-hwcost POINT` | snax-forge's HWCOST for the point, priced by snax-forge itself, into `results/cluster/<tech>/hwcost/<point>.json` |
| `cluster-breakdown [--md]` | the area in groups against HWCOST and the accelerator alone, `breakdown.json` (X72) |
| `cluster-energy [--md]` | the energy per window in groups, the run window against HWCOST, `energy.json` |
| `cluster-sweep [--recipe dot_3] [--md]` | the recipe's points over W beside HWCOST: `sweep.csv` and four figures (X78 · X80 · X86) |
| `cluster-sweep --points A,B,... --out NAME [--md]` | chosen points side by side in `NAME/`, for a look, not committed |

```
$ pixi run cluster-breakdown
results/cluster/nangate45/breakdown.json: dot3_w8_cg, dot3_w2_cg, dot3_w4_cg, dot3_w16_cg, dot3_w32_cg
$ pixi run cluster-energy
results/cluster/nangate45/energy.json: dot3_w8_cg, dot3_w2_cg, dot3_w4_cg, dot3_w16_cg, dot3_w32_cg
```

snax_cluster's Snitch-only clusters go through the same steps with `snb` (`cluster/snb_points.json`; the steps, gates and E11's measures in [`cluster/README.md`](../cluster/README.md#snb-the-snitch-only-clusters)). A config is one netlist, a run is `<config>_<kernel>_<type>`; X68's budget holds.

| Command | What it does |
|---|---|
| `snb rtl RUN [--allow-branch]` | the run's plain and quiet ELF in the image, then the plain one on the RTL with the macros; a row of `results/snb/nangate45/runs.csv` |
| `snb syn CONFIG [--cores 16] [--again] [--allow-branch]` | DC on the whole cluster; a kept netlist equal to the config's `netlist_sha256` is adopted with no DC |
| `snb gls RUN [--allow-branch]` | the config's netlist in the same testbench, the plain ELF on it (X91) |
| `snb pwr RUN [--cores 16] [--again] [--allow-branch]` | the quiet ELF on the netlist, one SAIF per section, one PT session |
| `snb-report [--md]` | E11's numbers: area in four parts, $n_\text{op}$, $C_\text{run}$, $\eta_A$, and $E_\text{run}$, $\eta_E$, $E_\text{leak}$ where power exists (X92), into `results/snb/nangate45/e11.json` |

```
$ pixi run snb syn snitch1_cg
snb syn snitch1_cg: kept syn/runs/snb/nangate45/snitch1_cg.zip (netlist 27135498b719 of snax_cluster c5621396983e, no RTL change since, row ok); --again runs DC
$ pixi run snb-report
results/snb/nangate45/e11.json: 3 configs, 0 runs, 0 with energy
```

`cluster-hwcost` runs in snax-forge's environment (`SNAX_FORGE`, default `../snax-forge`; `SNAX_FORGE_PYTHON` for a plain venv) and records snax-forge's commit and whether its tree was clean; price from a clean checkout.

## 8. Compare forge with the HLS tools

**`compare`** (`report/compare.py`) writes `results/compare_done.csv` and `compare_untiered.csv` from the committed CSVs, one row per tech, tier, kernel, W, tool, case and size: every source's clock-gated rows, and writes nothing when a source has no gated rows or a point or size is missing (X45 · X55 · X61); `--check` checks only.

```
$ pixi run compare
compare: written, done 325 rows, untiered 281 rows
  done      forge  40
  done      vitis  125
...
```

**`compare-hls`** (`report/compare_hls.py`) writes `results/compare/`: the README's generated parts and one page and two figures per kernel (X64, X77). The text outside the `gen` markers is written by hand and kept. `python report/compare_summary.py [REV]` prints the ratios behind the README's summary table.

## 9. Keep the repository clean

| Command | What it does |
|---|---|
| `arc check` | unpacked run folders, report folders not zipped, `tmp/` leftovers, the inodes per top-level folder; must end `nothing left over` (X51) |
| `arc ls ZIP` | a zip's members and sizes |
| `arc cat ZIP MEMBER` | one member on stdout |
| `test` | every test script (`*/test_*.py`), no EDA tool |
| `lint` | ruff's F rules (unused imports and names), through `pixi exec` |

```
$ pixi run arc check
...
arc check: nothing left over
$ pixi run lint
All checks passed!
```

One test alone: `pixi run python report/test_strm_table.py`. Markdown prose is one line per paragraph, list item and table row: `python ../snax-forge/util/md_reflow.py --check <files>` from the sibling checkout.
