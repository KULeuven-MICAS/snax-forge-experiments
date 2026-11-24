# docs

| Doc | What it holds |
|---|---|
| [`TOOL.md`](TOOL.md) | every command by job, with an example; the setup |
| [`DECISIONS.md`](DECISIONS.md) | what is settled, X1, X2, ...: what, why, where |
| [`PITFALLS.md`](PITFALLS.md) | tool behaviour that gives wrong numbers silently, by tool |
| [`power.md`](power.md) | the power flow: quantities, stages, each source's testbench and window |
| [`cost_tables.md`](cost_tables.md) | the tables HWCOST reads: meaning, measurement, interpolation, trust |

Folders and their READMEs: the [top README](../README.md#layout). Vitis-side details: hls-exercises' [`docs/HLS_VS_FORGE.md`](https://github.com/rgantonio/hls-exercises/blob/main/docs/HLS_VS_FORGE.md).

## Zipped outputs (X51)

Every point's outputs are one zip, read in place or unpacked into `tmp/` one point at a time (rules in `CLAUDE.md`, commands in [`TOOL.md`](TOOL.md#9-keep-the-repository-clean)). `arc check` allows only `syn/runs/<source>/<tech>/summary.csv`, `sim/runs/**/batches.jsonl`, `sim/runs/<tech>/_cells/` and `rtl/char/`'s `gen-block.json`, `char-rtl.log` as plain files.

## A round

- Start with `git pull` here and in each sibling the round reads ([`TOOL.md`](TOOL.md#1-set-up)).
- End with a run note (`results/<source>/runs/<date>_<task>_<round>.md`), new X-numbers and pitfalls, `pixi run test` where code changed, and `pixi run arc check` saying `nothing left over`.
