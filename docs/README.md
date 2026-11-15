# docs

| Doc | What it holds |
|---|---|
| [`TOOL.md`](TOOL.md) | every command, grouped by job, with what it reads and writes and an example; the setup |
| [`DECISIONS.md`](DECISIONS.md) | what this repository has settled, X1, X2, ...: what, why and where, by area |
| [`PITFALLS.md`](PITFALLS.md) | tool behaviour that gives wrong numbers without an error, one line each, by tool |
| [`power.md`](power.md) | the power flow: its energy quantities, stages, each source's testbench and window, what is kept |
| [`cost_tables.md`](cost_tables.md) | the tables HWCOST reads (SRAM banks, streamer reader, interconnect): what each number means, how it was measured, how to read between grid points, how far to trust it |

The folders and their READMEs are listed in the [top README](../README.md#layout). Vitis-side details (pragmas, ports, the cases, cosim) are in hls-exercises' [`docs/HLS_VS_FORGE.md`](https://github.com/rgantonio/hls-exercises/blob/main/docs/HLS_VS_FORGE.md).

## Zipped outputs (X51)

Every point's bulky outputs are one zip, read in place or unpacked into `tmp/` one point at a time; the working rules are in `CLAUDE.md` and the commands (`arc check`, `arc ls`, `arc cat`) in [`TOOL.md`](TOOL.md#9-keep-the-repository-clean). `arc check` must say `nothing left over` at the end of a round. The only plain files it allows among the outputs are `syn/runs/<source>/<tech>/summary.csv`, `sim/runs/**/batches.jsonl`, Questa's cell models in `sim/runs/<tech>/_cells/`, and `rtl/char/`'s `gen-block.json` and `char-rtl.log`.

## A round

- Start with `git pull` here and in every sibling repository the round reads ([`TOOL.md`](TOOL.md#1-set-up)).
- End with a run note (`results/<source>/runs/<date>_<task>_<round>.md`), the new X-numbers and pitfalls the round found, `pixi run test` where code changed, and `pixi run arc check`.
