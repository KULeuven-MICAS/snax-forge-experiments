# Initial findings: tier A at three levels

CSYN2's first look at how close the graph's static estimate (ADFG) and SNAX-GVSoC's dynamic energy come to the synthesized cluster, on the 17 tier A points at W = 8 (14 own netlists, three pipelined points on their sequential twin's). These are working figures for reading the numbers, not the paper's; `report/tier_check.py` and its `tier_check.json` hold the same numbers with the orders per kernel, and the run notes `results/cluster/runs/2026-11-27_csyn2_r3.md` and `_r4c.md` read them.

    pixi run python results/initial_findings/figures.py [--tech nangate45]

It reads `cluster/points.json`, `results/cluster/<tech>/{breakdown,energy}.json`, `ge/<point>.json` and snax-forge's `paper/data/{forms,limits}.csv` (`SNAX_FORGE`, default `../snax-forge`), and writes the files below beside itself.

## The files

| File | What it shows |
|---|---|
| `energy_run_windows.png` | dynamic energy per part in the windows where the accelerators run (and the DMA copies), three bars per design, and the ratio of each total to the netlist's |
| `energy_program_window.png` | the same over the program window: DMA in, configuration, the runs, DMA out |
| `energy_program_window_leak.png` | the program window with the six parts' leakage stacked on top |
| `area.png` | the whole cluster's area per part, estimate against DC, and the ratio per part |
| `trends.png` | before and after pairs (contiguous → padded, sequential → pipeline), dynamic and with the design's leakage, the change in % on each level |
| `numbers.csv` | the totals behind the figures: cycles, dynamic energy and leakage per level, the netlist's L2 ↔ L1 transfers (`nl_dma_io_nj`), area |

The parts are COST2's, with the datapath and control as one "accelerator". The estimate's energy is the graph's static count; its leakage runs over its own cycles (the accelerator runs alone). A pipelined point has one window, the whole program window, so its run windows hold its DMA in and out too.

## What they show

- **Cycles and area are close.** SNAX-GVSoC's program window is within 3.6 % of the netlist's (short on all but the two int8 pipelined points, 0.4 and 2.0 % long); the whole cluster's area is within −1.9 to +0.3 % of DC's.
- **Energy follows the trends, not the totals.** Over the program window SNAX-GVSoC's dynamic energy is 0.57–0.82 of the netlist's but on the DMA copies (1.16–1.20) and `mvt_contiguous_w8` (1.02); with the design's leakage 0.77–0.92 on the same designs. Contiguous → padded on mvt: the estimate 0 %, SNAX-GVSoC −32 %, the netlist −10 %; sequential → pipeline with leakage: −27 to −31 % on all three levels for the int8 pairs.
- **The activity is priced well; what is missing is unpriced.** Above the idle floor (`energy.json`'s `run`, each run against the configuration window before it), SNAX-GVSoC's run windows are 0.88–1.13 of the netlist's energy on every sequential design without refused requests. The gap is the idle floor (4–28 % of the run windows), the L2 ↔ L1 transfers (7–16 nJ a program at int8, about 57 nJ at int64), and refused requests priced as grants (`mvt_contiguous_w8`, the contiguous pipelined bicg).
- **Per part the errors partly cancel:** the datapath priced high, the streamers, crossbar and banks low.
- **Leakage is large on nangate45 at 10 ns:** 40–60 % of the int8 forms' program-window energy; it scales with the clock period (D201 in snax-forge).

COST3 takes the refused requests and the L2 ↔ L1 transfers; the idle floor is left unpriced.
