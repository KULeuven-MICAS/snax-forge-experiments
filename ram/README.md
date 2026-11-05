# ram

SRAM bank area and dynamic energy per access for snax-forge's HW cost model (HWCOST), from CACTI 7 at 45 nm (RAM1). OpenRAM was probed in R0 and dropped (`results/ram/runs/2026-11-05_ram1_r0.md`).

## Build CACTI

```sh
pixi run ram-build
```

Clones https://github.com/HewlettPackard/cacti into `ram/cacti/` at commit `1ffd8df` and runs `make` with the host's g++ (8.5.0 here; 15 s; the makefile's default is the debug build, `-O0`, which runs a point in about 0.2 s). `ram/cacti/` is git-ignored: CACTI's source is never committed. If `ram/cacti/` exists, the task only checks out the commit and runs `make` again.

## Run

```sh
pixi run ram point 512 64                          # one point: config, run, parse, print
pixi run ram point 512 64 --objective 0:0:0:100:0 --tag myvariant
pixi run ram all -j 32                             # RAM1 R1's points -> results/ram/nangate45/ram_cacti.csv
```

- Each point runs in `ram/runs/cacti/d<depth>_w<width>[_<tag>]/` (git-ignored) with `tech_params/` and `contention.dat` linked in: CACTI opens `tech_params/45nm.dat` relative to its working directory and segfaults without it (PITFALLS C1). The folder keeps `cacti.cfg`, `cacti.out`, `cacti.err`, CACTI's own `cacti.cfg.out`, `rc`, `time_s` and `key.json`.
- A folder whose config and CACTI commit are unchanged is not rerun (`key.json`).
- The config is CACTI's `cache.cfg` with: size d · w / 8 bytes, block w / 8 bytes, direct mapped, one read-write port and no other ports, one UCA bank, 0.045 µm, `"ram"`, itrs-hp cells and peripherals, bus width w, 300 K, design objective 0:50:0:0:50 (dynamic energy and area), deviate as in `cache.cfg`, `-Optimize "NONE"` (`cache.cfg`'s `ED^2` makes CACTI ignore the objective), `-Add ECC "false"` (`cache.cfg` adds one ECC bit per 8 data bits), print level DETAILED.
- A width that is not a whole number of bytes is padded up (39 to 40); the per-bit energies divide by the padded width (`width_cacti`).
- `all` first runs `vdd_check`: 512 x 64 with CACTI's `-print option "debug detail"`, which prints the tech tables; every itrs-hp block (`-Vdd[0]`) must be 1.0 V or the script stops.
- Energies are scaled from CACTI's 1.0 V (itrs-hp, 45 nm) to Nangate 45 nm's 1.10 V by 1.21 (`e_rd_pj`, `e_wr_pj`, `e_*_bit_fj`); the raw values are kept (`e_*_raw_pj`). Area, timing and leakage are CACTI's, not scaled.
- A point CACTI rejects is a row with `status` `failed: rc <rc>: <its message>`: under 64 bytes (`Cache size must >=64`, rc 0) or depth 16 (`no valid data array organizations found`: at least 2 x 16 rows).

## The CSV

`results/ram/nangate45/ram_cacti.csv`, one row per point: `depth`, `width`, `width_cacti`, `bits`, `status`, `area_um2` (height x width), `data_area_um2`, `height_um`, `width_um`, `e_rd_pj`, `e_wr_pj` (1.1 V), `e_rd_raw_pj`, `e_wr_raw_pj` (1.0 V), `e_rd_bit_fj`, `e_wr_bit_fj` (1.1 V, per `width_cacti` bit), `leak_uw` (subthreshold, CACTI's "Total leakage power of a bank"), `leak_gate_uw`, `t_access_ns`, `t_cycle_ns`, `ndwl`, `ndbl`, `nspd`, `ndcm`, `ndsam_l1`, `ndsam_l2`, `area_eff_pct`, `objective`, `ecc`, `cacti_commit`, `run`.
