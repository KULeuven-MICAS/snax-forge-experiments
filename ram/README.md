# ram

SRAM bank area and dynamic energy per access for snax-forge's HW cost model (HWCOST), from CACTI 7 at 45 nm (RAM1). OpenRAM was probed in R0 and dropped (`results/ram/runs/2026-11-05_ram1_r0.md`).

## Build CACTI

```sh
pixi run ram-build
```

Clones https://github.com/HewlettPackard/cacti into `ram/cacti/` at commit `1ffd8df` and runs `make` with the host's g++ (8.5.0 here; 15 s; the makefile's default is the debug build, `-O0`, which runs a point in about 0.2 s). `ram/cacti/` is git-ignored: CACTI's source is never committed. If `ram/cacti/` exists, the task only checks out the commit and runs `make` again.

## Run

```sh
pixi run ram table -j 32                           # the lookup table -> results/ram/nangate45/ram_table.csv (X48)
pixi run ram point 512 64                          # one point: config, run, parse, print every column
pixi run ram point 512 64 --objective 0:0:0:100:0 --tag myvariant
pixi run ram point 512 64 --ecc --tag ecc
```

- `table` runs every depth from 32 to 4096 in steps of 32 words and every width from 8 to 256 in steps of 8 bits (4,096 points; 4,095 are modelled, 32 x 8 is under 64 bytes and left out). About 4 minutes on 2 cores from scratch, seconds when cached. It stops if a cached point was run with another CACTI commit, objective or ECC setting.
- Each point runs in `ram/runs/cacti/d<depth>_w<width>[_<tag>]/` (git-ignored) with `tech_params/` and `contention.dat` linked in: CACTI opens `tech_params/45nm.dat` relative to its working directory and segfaults without it (PITFALLS C1). The folder keeps `cacti.cfg`, `cacti.out`, `cacti.err`, CACTI's own `cacti.cfg.out`, `rc`, `time_s` and `key.json`.
- A folder whose config and CACTI commit are unchanged is not rerun (`key.json`).
- The config is CACTI's `cache.cfg` with: size d · w / 8 bytes, block w / 8 bytes, direct mapped, one read-write port and no other ports, one UCA bank, 0.045 µm, `"ram"`, itrs-hp cells and peripherals, bus width w, 300 K, design objective 0:50:0:0:50 (dynamic energy and area), deviate as in `cache.cfg`, `-Optimize "NONE"` (`cache.cfg`'s `ED^2` makes CACTI ignore the objective, PITFALLS C2), `-Add ECC "false"` (`cache.cfg` adds one ECC bit per 8 data bits, PITFALLS C3), print level DETAILED (X47).
- `point` pads a width that is not a whole number of bytes (39 to 40); the per-bit energies divide by the padded width (`width_cacti`).
- `table` first runs `vdd_check`: 512 x 64 with CACTI's `-print option "debug detail"`, which prints the tech tables; every itrs-hp block (`-Vdd[0]`) must be 1.0 V or the script stops.
- Energies are scaled from CACTI's 1.0 V (itrs-hp, 45 nm) to Nangate 45 nm's 1.10 V by 1.21; area, timing and leakage are CACTI's, not scaled.
- A point CACTI rejects gets `status` `failed: rc <rc>: <its message>`: under 64 bytes (`Cache size must >=64`, rc 0, PITFALLS C4) or depth 16 (`no valid data array organizations found`).

## The table

`results/ram/nangate45/ram_table.csv` (X48), one row per modelled point, sorted by depth then width: `depth` (words), `width` (bits), `area_um2` (CACTI's height x width), `e_rd_pj` and `e_wr_pj` (dynamic energy per access at 1.1 V; a write is a full-word write), `t_access_ns`, `t_cycle_ns`, `leak_uw` (subthreshold, CACTI's "Total leakage power of a bank"; not used by the cost model), and CACTI's organization `ndwl`, `ndbl`, `nspd`, `ndcm`, `ndsam_l1`, `ndsam_l2`. CACTI commit, objective and the 1.21 scaling are the same on every row and are written by `table` when it runs (and in X47).

It is a lookup table, not a fit: a reader takes the row of the exact (depth, width). With depths in steps of 32 and widths in steps of 8, (d, w) is data row `(d / 32 - 1) * 32 + w / 8 - 2`, counting from 0 after the header (the full grid's index, minus one for 32 x 8, the first point, which is left out). Interpolating between rows is not advised: CACTI's numbers jump by up to 30 % between neighbouring sizes where its organization changes (PITFALLS C5). What a reader does with a size that is not on the grid is the reader's choice (snax-forge's HWCOST).

`point` prints every column CACTI gives (`COLUMNS` in `ram.py`), for one-off checks.

## Nangate 45 nm pin values

```sh
pixi run python ram/pins.py
```

Writes `ram/nangate45_pins.json` (committed) from the Liberty text `NangateOpenCellLibrary_typical.lib` next to the `.db` that `syn/tech/nangate45.json` points to (`SYN_LIB_NANGATE45` overrides it, as in `syn.py`): the library units, `nom_*`, the `typical` operating conditions, the slew and delay thresholds (30/70 %, 50 %) and the `default_*` attributes, the internal-power unit (1 fJ, derived from 1 fF x (1 V)², the library has no attribute for it), `DFF_X1` `D` and `CK` capacitance, the setup and hold of `D` against `CK` and `CK`'s min pulse width (each the largest entry of its table), and `BUF_X4/Z`'s `max_capacitance` and rise and fall transition (the middle entry of the 7 x 7 table). Each value has a `source` (file, line, group path, attribute). The macro generator reads only this file, never the library. In R3 the `.db` gave the same capacitances, units and `nom_*` as the text (`dc_shell`, `get_attribute` and `report_lib`).

## SRAM macros for DC, Questa and PT (X49)

```sh
pixi run ram lib 512 64 --mask 8         # one macro -> ram/runs/lib/sram_d512_w64_m8/
pixi run ram libs ram/macros.json -j 4   # every macro in the list, at most as many at once as free Library-Compiler licences
```

A macro is named `sram_d<depth>_w<width>`, plus `_m<mask>` with `--mask`. Its folder in `ram/runs/lib/<name>/` (git-ignored, never committed) holds `<name>.lib`, `<name>.db`, `<name>.v`, `lc.tcl` and `lc.log` (lc_shell), `result.json` (the numbers, lc_shell's warnings) and `key.json` (the CACTI row, the md5 of `nangate45_pins.json`, the generator version and the md5 of the generated `.lib` and `.v` text). A folder whose key is unchanged and whose last run was ok is not regenerated. `lc_shell` is `/esat/micas-data/software/Synopsys/lc/Y-2026.03-SP2/bin/lc_shell` (not on PATH; `LC_SHELL` overrides it); a macro fails on any `Error` line, a non-zero rc or a missing `.db`. `ram/macros.json` lists what the cluster and DaCe need now: the TCDM bank 512 x 64 with mask 8 (also DaCe's dot buffer), the icache data 128 x 256 and the icache tag 128 x 39.

**Numbers.** `row(depth, cacti_width(width))`: the cached CACTI point, the same numbers as `ram_table.csv` for sizes on its grid. Ports keep the real width (39 stays 39); the costs are those of the width padded to whole bytes (40).

**Ports,** all active high, as `tc_sram_impl` with one port and no `impl_*`: `clk_i`, `req_i`, `we_i`, `addr_i[$clog2(depth)-1:0]`, `wdata_i[width-1:0]`, `be_i[width/mask-1:0]` (only with `--mask`), `rdata_o[width-1:0]`. No reset.

**The `.lib`** (one library per macro, named as the cell), with every value's origin:

| what | value | from |
|---|---|---|
| units, `nom_*`, operating conditions `typical`, slew and delay thresholds, `default_*` | 1 ns, 1 fF, 1 V, 1 mA, 1 nW, 1 kΩ; 1.0, 1.10 V, 25 C; 30/70 %, 50 % | `nangate45_pins.json` (nangate45's `.lib`) |
| `char_config` | `internal_power_calculation : exclude_switching_on_rise_and_fall` | the energy on `clk_i` is the macro's own; `rdata_o`'s load is switching power DC and PT add (PITFALLS LIB6) |
| `area` | CACTI's `area_um2` | the CACTI row |
| `dont_use`, `dont_touch` | true | |
| `cell_leakage_power` | CACTI's leakage in nW (not used by the cost model) | the CACTI row |
| `clk_i` | `clock : true`, capacitance of `DFF_X1/CK`, `min_period` CACTI's `t_cycle_ns`, min pulse width high and low half of it | the CACTI row, `nangate45_pins.json` |
| `clk_i` `internal_power` | `rise_power` = read energy `when "req_i & !we_i"`, write energy `when "req_i & we_i"`, 0 `when "!req_i"`; `fall_power` 0 in all three; in fJ (1 fF x (1 V)²) | the CACTI row at 1.1 V (x 1.21) |
| `req_i`, `we_i`, `addr_i`, `wdata_i`, `be_i` | capacitance of `DFF_X1/D`; `setup_rising` and `hold_rising` to `clk_i` with `DFF_X1`'s rise and fall constraints (the largest entry of each table) | `nangate45_pins.json` |
| `rdata_o` | `max_capacitance` of `BUF_X4/Z`; a `rising_edge` arc from `clk_i`, `cell_rise` = `cell_fall` = CACTI's `t_access_ns`, `BUF_X4`'s rise and fall transition (the middle entry of its table) | the CACTI row, `nangate45_pins.json` |

Every table is `scalar`; buses have one `type` per width. A byte-masked write is charged as a full write (CACTI gives one write energy), as the `.lib`'s comment block says, with the CACTI commit, the point, the 1.21 scaling and the generator. There is no `memory` group: lc_shell compiles without it, and its two remaining warnings (no `function` on `rdata_o`, LIBG-10) are expected for a black box (PITFALLS LIB6).

**The `.v`** (SystemVerilog, `timescale 1ns/1ps`, one `always_ff @(posedge clk_i)`) behaves as `tc_sram` (tech_cells_generic v0.2.14, snax_cluster's `Bender.lock`) at `NumPorts 1`, `Latency 1`: `rdata_o` is a register loaded at every rising edge, with `mem[addr_i]` on a read (`req_i & !we_i`) and with the word at the last read address (its value before the edge) on a write or while deselected. So after a read it shows the word read, after a write it keeps the last read word (and shows a write to that word one cycle later), and while deselected it holds. A write stores only the bytes whose `be_i` bit is set. Contents start X; with `+define+SRAM_INIT_ZERO` contents, read address and `rdata_o` start 0 (as `tc_sram` after reset with `SimInit "zeros"`). Without a reset port the read address starts X, which shows the same X as `tc_sram` after reset until the first read. Under `` `ifndef SYNTHESIS `` two 64-bit counters count reads (`req_i & !we_i`) and writes (`req_i & we_i`, masked or not) at the rising edge, and a `final` block prints one line: `RAMCOUNT <%m> <cell> reads <n> writes <n>`. In R3 the `.v` matched `tc_sram` cycle for cycle over 20,000 random cycles, X and zero start.

**Memory energy** of a run is `reads x e_rd_pj + writes x e_wr_pj` from `RAMCOUNT` and the table, or time-based PT on the VCD (exact in R3); averaged PT (SAIF) takes `req_i` and `we_i` as independent and was 12.5 % low (PITFALLS PT7).
