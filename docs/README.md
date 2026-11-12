# docs

| Doc | What it holds |
|---|---|
| [`DECISIONS.md`](DECISIONS.md) | what this repo has settled, X1, X2, ...: the rule, why, and where it was decided |
| [`PITFALLS.md`](PITFALLS.md) | tool behaviour that gives wrong numbers without an error, per tool: symptom, cause, fix or check |
| [`power.md`](power.md) | the power flow: its energy quantities, commands, stages, each source's TB and window, what is kept |
| [`cost_tables.md`](cost_tables.md) | the tables HWCOST reads (SRAM banks, streamer reader, interconnect): what each number means, how it was measured, how to read between grid points, how far to trust it |

The folders and their READMEs are listed in the [top README](../README.md#layout). Vitis-side details (pragmas, ports, the cases, cosim) are in hls-exercises' [`docs/HLS_VS_FORGE.md`](https://github.com/rgantonio/hls-exercises/blob/main/docs/HLS_VS_FORGE.md).

## Zipped outputs (X51)

Every point's bulky outputs are one zip, read in place or unpacked into `tmp/` one point at a time; the working rules are in `CLAUDE.md`.

```sh
pixi run arc check            # unpacked run folders, report folders not zipped, tmp/ leftovers, inodes per folder
pixi run arc ls ZIP           # a zip's members and sizes
pixi run arc cat ZIP MEMBER   # one member on stdout
pixi run arc-test             # arc/test_arc.py
```

`arc check` must say `nothing left over` at the end of a round. The only plain files it allows among the outputs are `syn/runs/<source>/<tech>/summary.csv`, `sim/runs/**/batches.jsonl`, Questa's cell models in `sim/runs/<tech>/_cells/`, and `rtl/char/`'s `gen-block.json` and `char-rtl.log`.

## Environment

- **Python:** the repo's pixi workspace (Python 3.11): `pixi install` once, then everything through `pixi run` (X15). The server's `python3` is 3.6 and cannot run the scripts.
- **EDA tools** from PATH, or `DC_SHELL`, `PT_SHELL` and `LMUTIL` pointing at the binary. Questa (`vlog`, `vopt`, `vsim`) and `vcd2saif` from PATH.
- **Inputs elsewhere than the sibling folders:** `SYN_RTL` (hls-exercises' `rtl/`), `SYN_RTL_XLS` (dslx-exercises' `rtl/`), `SYN_LIB_NANGATE45`, `SYN_LIB_NANGATE15` (`syn/README.md`), `SIM_HLS`, `SIM_XLS`, `SNAX_FORGE`, `SNAX_CLUSTER`.
- **Licences:** check with `lmutil lmstat -a -c <server>` (Synopsys `1709@licserv`, Mentor `1717@licserv`, from `SNPSLMD_LICENSE_FILE` and `MGLS_LICENSE_FILE`) and size the parallel jobs from the free counts, within 16 cores (X16, X59). A cluster DC run holds the host alone (X68).
