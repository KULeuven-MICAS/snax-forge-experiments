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
