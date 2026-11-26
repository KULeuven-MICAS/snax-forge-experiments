# The tools

Every command by job, one example each; flows in the folder READMEs and [`power.md`](power.md).

| Job | Commands | Section |
|---|---|---|
| Set up | siblings, `pixi install`, licences | 1 |
| Make the RTL of a source | `forge-rtl`, `char-rtl`, `strm-rtl`, `import-cycles` | 2 |
| Synthesize | `syn` | 3 |
| Measure the energy | `pwr` | 4 |
| Make the memories | `ram-build`, `ram` | 5 |
| Make the tables HWCOST reads | `strm-table`, `xbar-kinds`, `char-export`, `char-table`, `cluster-fixed` | 6 |
| Take a design through the whole cluster | `cluster`, `cluster/batch.sh`, `cluster-hwcost`, `cluster-breakdown`, `cluster-energy`, `cluster-sweep`, `ge-check`, `snb`, `snb-report`, `dma-copy` | 7 |
| Compare forge with the HLS tools | `compare`, `compare-hls` | 8 |
| Keep the repository clean | `arc`, `test`, `lint` | 9 |

## 1. Set up

Sibling repositories beside this one, no submodules, no PDK files committed: `snax-forge/`, `snax_cluster/`, `hls-exercises/` (Vitis and Bambu, `rtl/<tier>/<kernel>/<case>_w<W>/filelist.f`), `dslx-exercises/` (XLS), `RTL_flow_Nangate15/` (`tech/nangate45/`).

- `pixi install`, then `pixi run` (X15). EDA tools from PATH, or `DC_SHELL`, `PT_SHELL`, `LMUTIL`. Other paths: `SYN_RTL`, `SYN_RTL_XLS`, `SYN_LIB_NANGATE45`, `SIM_HLS`, `SIM_XLS`, `SNAX_FORGE`, `SNAX_CLUSTER`.
- **Licences:** `lmutil lmstat -a -c <server>` (Synopsys `1709@licserv`, Mentor `1717@licserv`); count `Design-Compiler`, `DC-Expert`, `msimhdlsim`, `PrimeTime`, `PrimePower` (PITFALLS L2, L4) within 16 cores (X16 · X59), a cluster run alone (X68).
- **Quota:** `quota -v` before a large batch (X51).

## 2. Make the RTL of a source

One zip per point under `rtl/` (git-ignored), each recording its commit.

- **`forge-rtl`** (`forge/bundles.py`): snax-forge's `sandbox`, `design`, `bundle` per `forge/points.json` point into `rtl/forge/<point>.zip`; dirty checkout refused unless `--allow-dirty` (X21), `dtypes` via a temporary recipe (X57), `--list` lists. Example: `pixi run forge-rtl 'untiered/*' --set N=2048`.
- **`char-rtl`** (`char/blocks.py`): `gen-block` for `char/points.json` into `rtl/char/` (X28). Example: `pixi run char-rtl --list`.
- **`strm-rtl`** (`strm/gen.py`): reader, interconnect, xbar_mix points of `strm/grid.json` in snax_cluster's image (`--set streamer|xbar|xbar_mix`, `--only`); see [`strm/README.md`](../strm/README.md). Example: `pixi run strm-rtl --set xbar --list`.
- **`import-cycles`** (`report/import_cycles.py`): byte copies of `bambu_cycles.csv`, `xls_cycles.csv` with `SOURCE` (X42). Example: `pixi run import-cycles`.

## 3. Synthesize: `syn`

DC per point, `--source` `hls` (default), `bambu`, `xls`, `forge`, `char`, `streamer`, `xbar`, `xbar_mix`; quoted globs; see [`syn/README.md`](../syn/README.md).

| Command | What it does |
|---|---|
| `syn list [PATTERN ...] [--source S] [--tech T]` | the points picked |
| `syn run PATTERN ... --tech nangate45 [--source S] [--clock NS] [--cores N] [-j N] [--dry-run] [--sdf] [--clk-gate] [--with-ram]` | DC into `syn/runs/<source>/<tech>/<point>.zip`, a row in `synth_dc.csv` |
| `syn summary [PATTERN ...] [--source S] [--tech T]` | the rows so far |
| `syn check-ports [PATTERN ...] [--source S]` | the port guard alone (X39) |

`--clk-gate` tags `_cg` (X79 · X87 · X88); `--dry-run` at `-j 1` (PITFALLS DC17); `--with-ram` (X62). Check `status` and, for streamer, xbar, char, the printed `flops` lines (X52 · X82).

```bash
pixi run syn run 'done/*/forge*' --source forge --tech nangate45 -j 4 --cores 4 --clk-gate
```

## 4. Measure the energy: `pwr`

Testbenches, windows and checks per source are in [`power.md`](power.md).

| Command | What it does |
|---|---|
| `pwr tbjson POINT [--source S] [--tech T]` | print `tb.json` |
| `pwr run PATTERN ... --tech nangate45 [--source S] [--size TAG\|all] [--seed N] [--stim rand64\|forge] [-j N] [--cores C] [--clk-gate] [--initreg-seed N]` | runs into `sim/runs/`, rows in `power_pt.csv`, `power_pt_modules.csv`, `power_reports/` |
| `pwr setup-check --tech nangate45 [--source S] [--point P]` | PT against DC, a diagnostic (X25) |
| `pwr summary [PATTERN ...] [--source S] [--tech T]` | print `power_pt.csv` |
| `pwr modules --source S --tech T` | fill old rows' size column (one-off) |

`n2048` is the reference task (X24); char, streamer, xbar, xbar_mix take no size. Check `status` and forge's `counter_diff`, `expected_diff` (5 %, X56).

```bash
pixi run pwr run 'done/*/forge*' --source forge --tech nangate45 --size n2048
```

## 5. Make the memories: `ram-build`, `ram`

CACTI 7 banks (X47) and macros (X49); see [`ram/README.md`](../ram/README.md).

| Command | What it does |
|---|---|
| `ram-build` | clone CACTI into `ram/cacti/` at its pinned commit and build it |
| `ram point DEPTH WIDTH [--objective ...] [--ecc] [--tag T]` | one point, every column |
| `ram table [-j N]` | `results/ram/nangate45/ram_table.csv` (X48) |
| `ram lib DEPTH WIDTH [--mask 8]` | one macro into `ram/runs/lib/<name>.zip` |
| `ram libs ram/macros.json [-j N]` | a list's macros |

```bash
pixi run ram lib 512 64 --mask 8         # ram/runs/lib/sram_d512_w64_m8.zip
```

## 6. Make the tables HWCOST reads

snax-forge copies them with `pixi run import-costs`; meanings in [`cost_tables.md`](cost_tables.md).

- **`strm-table`** (`report/strm_table.py`): gated rows into `streamer.csv`, `xbar.csv` (X52 · X82, X83 · X85); `--loo` the leave-one-out check (X53 · X54). Example: `pixi run strm-table` prints `streamer.csv: 168 rows, 168 ok`.
- **`xbar-kinds`** (`report/xbar_kinds.py`): `xbar_kinds.json`, area forms (X71) and energy factors (X93). Example: `pixi run xbar-kinds`.
- **`char-export`** (`report/char_export.py`): `char.json` from gated rows (X37, X83 · X85). Example: `pixi run char-export`.
- **`char-table`** (`report/char_table.py`): `results/char/char_table.md`. Example: `pixi run char-table`.
- **`cluster-fixed`** (`report/cluster_fixed.py`): `results/cluster/<tech>/cluster_fixed.json`, the cluster's fixed parts (X103). Example: `pixi run cluster-fixed --md`.

## 7. Take a design through the whole cluster

Steps and checks in [`cluster/README.md`](../cluster/README.md); one cluster run at a time (X68), never snax_cluster's `clean-logs` after one.

| Command | What it does |
|---|---|
| `cluster rtl POINT [--allow-branch]` | bundle, RTL runs plain and with macros, D123 |
| `cluster syn POINT [--cores 16] [--allow-branch]` | DC on the whole cluster |
| `cluster gls POINT [--allow-branch]` | the netlist run, gated (X67 · X81 · X84) |
| `cluster pwr POINT [--cores 16] [--again] [--allow-branch]` | one VCD, a SAIF per section, one PT session (X20 · X60 · X74) |
| `cluster/batch.sh POINT ...` | steps in series (`BATCH_OUT`, `--steps S,S`, `--from STEP`, `CORES`, `KEEP_GOING=1`; X109) |
| `cluster-hwcost POINT` | HWCOST into `hwcost/<point>.json` (snax-forge's environment, `SNAX_FORGE`, `SNAX_FORGE_PYTHON`; a clean checkout) |
| `cluster-breakdown [--md]` | area in groups, `breakdown.json` (X72) |
| `cluster-energy [--md]` | energy per window in groups, `energy.json` |
| `cluster-sweep [--recipe dot_v3] [--points A,B,... --out NAME] [--md]` | `sweep.csv` and figures (X78 · X80 · X86) |
| `ge-check [--recipe dot_v3] [--md]` | snax-forge's D177 energy against hwcost and the netlist, Kendall's tau (cluster/README.md, "ge-check") |
| `snb rtl RUN`, `snb gls RUN`, `snb pwr RUN [--cores 16] [--again]` (all `[--allow-branch]`) | Snitch-only runs `<config>_<kernel>_<type>` (X91) |
| `snb syn CONFIG [--cores 16] [--again]` | a config's netlist, adopted with no DC if its sha256 matches |
| `snb-report [--md]` | E11's numbers into `e11.json` (X92) |
| `dma-copy [--md]` | `dma_transpose` against D184 into `dma_copy.json` (X95), and the engine's price per burst `e_burst_pj` (X102) |

`snb`'s steps: [`cluster/README.md`](../cluster/README.md#snb-the-snitch-only-clusters).

```
$ pixi run cluster-breakdown
results/cluster/nangate45/breakdown.json: dot3_w8_cg, dot3_w2_cg, dot3_w4_cg, dot3_w16_cg, dot3_w32_cg
```

## 8. Compare forge with the HLS tools

- **`compare`** (`report/compare.py`): `compare_done.csv`, `compare_untiered.csv` from gated rows (X45 · X55 · X61); `--check` only checks. Example: `pixi run compare` prints `compare: written, done 325 rows, untiered 281 rows`.
- **`compare-hls`** (`report/compare_hls.py`): `results/compare/` pages and figures (X64, X77). Example: `pixi run compare-hls`; `python report/compare_summary.py [REV]` prints the summary's ratios.

## 9. Keep the repository clean

| Command | What it does |
|---|---|
| `arc check` | leftovers and inodes; must end `nothing left over` (X51) |
| `arc ls ZIP` | a zip's members |
| `arc cat ZIP MEMBER` | one member on stdout |
| `test` | every test script, no EDA tool |
| `lint` | ruff's F rules via `pixi exec` |

Example: `pixi run arc check` ends `arc check: nothing left over`. One test: `pixi run python report/test_strm_table.py`. Markdown check: `python ../snax-forge/util/md_reflow.py --check <files>`.
