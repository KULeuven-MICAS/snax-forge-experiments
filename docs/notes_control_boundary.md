# Notes: control, datapath and the block boundary (SYN1, forge against HLS)

Working notes from the review of SYN1's analysis, 1 Nov 2026, kept to ideate on. They are self-contained: enough context and numbers to read without the repos. The generated, reproducible version of every number here is in `results/analysis/syn1/syn1_analysis.md` (sections 9 and 10), with the run notes `results/forge/runs/2026-11-01_syn1_split.md` and `results/hls/runs/2026-11-01_hls_c10.md`. Where this note and the analysis differ, the analysis is right.

## 1. The setting

SYN1 compares snax-forge's generated accelerators with Vitis HLS designs of the same kernels: vecadd, vecmul, vsum (sum of a vector) and dot (dot product), each at W = 1 to 32 lanes of int64. The HLS side has three cases: unopt (NPBench's loops, no directives), opt (the beat loop pipelined at II = 1, the lanes unrolled) and dace (DaCe-generated). Forge has one design per kernel, and dot has five variants (dot 2 to dot 6, different block choices: multiply lanes, adder tree, serial sum, link buffer).

Both sides are synthesized with Design Compiler at a 10 ns clock on Nangate 45 nm and 15 nm, simulated at gate level on one task of N = 2048 elements, and measured with PrimePower on the busy window (start to done). e_run is the dynamic energy of that task. Both sides have the same stream ports (data, valid, ready per stream, W × 64 bits); forge's streamers, which feed it from memory, are outside the synthesized block.

Forge's block is a wrapper with three instances: `csr` (the CSR register file), `ctrl` (the group's control: counters, handshakes) and `dp` (the datapath). Vitis writes HLS's control flat beside its datapath, so HLS had no control number until the split below.

Cycles: forge's count is the testbench's window from the accepted START to done, and every run checks it against the COUNTER CSR read back and snax-forge's own cycle model. Forge needs N / W + 0 to 2 cycles (dot 5 and 6: + W + 1, + W + 2, their serial sum's tail); HLS opt N / W + 2 to 4 (its pipeline's fill). Forge's 0 extra cycles on vecadd and vecmul come from combinational lanes, and partly from the boundary: its streamers' latency is not in the window.

## 2. How control and datapath were split (one rule on both sides)

PrimePower was run again on every point's netlist with the SAIF its power run kept, and every leaf cell's area and power dumped (218 runs: 61 HLS and 48 forge points per technology). The rule: **datapath** is the forward cone of the data input ports (Vitis `*_TDATA`, forge `stream2acc_*_data_i`), through logic and through every flop it reaches until nothing new is reached; **control** is every other cell.

Checks: every rerun's power summary equals the committed run's; the cells' area equals DC's within 0.0019 µm², their energy the committed e_dyn within 0.0001 %. On forge the rule reproduces the hierarchy: no csr or ctrl cell is in the data cone, every dp flop is; the only differences are a little logic inside dp's blocks behind ctrl's enables and lane select (at most 0.18 % of the area, 0.113 % of e_dyn).

Found on the way: the analysis's Verilog parser missed registers assigned a bit range at a time (`N_reg_64[30 : 4] <= ...`); fixed, 8 rows of section 3 changed (vecadd and vecmul unopt and dace).

## 3. What the split shows

Control, nangate45, over every kernel and W: HLS opt 623 to 1,435 µm² and 0.51 to 1.32 pJ per cycle; forge 1,798 to 5,177 µm² and 1.46 to 2.81 pJ per cycle. Forge's control costs 1.9x to 2.9x HLS opt's energy per cycle, same kernel and W.

Control's share of e_run, W = 1 → 32, nangate45: vecadd HLS opt 25.9 → 1.4 %, forge 65.3 → 5.8 %; vsum HLS opt 29.4 → 3.7 %, forge 53.3 → 14.9 %; dot HLS opt 6.0 → 0.3 %, forge's variants about 16 → 1 %. The share falls with W because control's energy per cycle is nearly constant and the cycles fall as N / W.

Flops carry most of control's energy: 83 to 98 % on forge, 57 to 97 % on HLS opt and dace. A control flop costs about 7 fJ per cycle on nangate45 on both sides (HLS median 6.95, forge 7.17), and 91 to 100 % of that is internal power, the clock pin's: a register costs the same whether it changes or not, since neither side gates its clocks. So **control energy is about the number of control flops times 7 fJ per cycle.**

## 4. The apparent paradox: more control, less energy

Forge's total e_run is below HLS opt's in 91 of 96 forge design-W-technology cases, while its control is the larger in all of them. Energy per task, nangate45, nJ:

| | e_run | control | datapath flops | datapath logic |
|---|---|---|---|---|
| vecadd HLS opt, W = 8 | 3.12 | 0.14 | 2.14 | 0.85 |
| vecadd forge, W = 8 | 1.97 | 0.38 | 0.00 | 1.59 |
| dot HLS opt, W = 32 | 30.15 | 0.09 | 5.45 | 24.62 |
| dot forge (dot 3), W = 32 | 23.32 | 0.18 | 0.07 | 23.07 |

The difference is the datapath's flops. HLS opt keeps a register stage inside its block (vecadd its results, vecmul and vsum their operands, dot its operands and products); forge's lanes have none, because forge's operand registers are in the streamers, outside SYN1's boundary. Forge is the higher only where its control dominates a tiny datapath: vecadd at W = 1 and vsum at W = 1 (both technologies), vsum at W = 2 (nangate45).

Removing HLS's register stage would save only its internal energy, not its switching: a register that drives the output port pays the port's 25 fF load, and without it the logic pays it (forge's datapath logic shows exactly that). For vecadd at W = 8, HLS opt's datapath flops are 1.10 nJ internal and 1.03 nJ switching, and forge's datapath logic switches 1.10 nJ. Against HLS opt minus its datapath flops' internal energy (an estimate), forge is below in 47 of 96 cases: vecmul 11 of 12, vecadd 6 of 12, vsum 4 of 12, dot 26 of 60. dot's datapath logic alone is about the same on both sides (forge 0.92 to 1.01x HLS opt). **So forge's energy lead comes mostly from the boundary, not from a better datapath.**

## 5. Why HLS has that register stage, and the 10 ns try

The axis register slices (Vitis's skid buffers on every stream port) are already off in tier done (hls-exercises `params.json`: `"axis_register_mode": "off"`). What remains are Vitis's own pipeline registers, from scheduling at its default clock target of 3.33 ns.

A short experiment set the HLS clock target to 10 ns (the ASIC's) for vecadd and vecmul opt at W = 8. **The stage stayed.** vecadd's Verilog came out identical apart from its header. vecmul moved its registers from the operands (16 × 64 = 1,024 bits, the multipliers then driving the output) to the products (8 × 64 = 512 bits, driving the output). Both keep a pipeline of depth 2 and 10 cycles for 8 beats. Vitis's timing estimate for vecmul went from 3.648 ns to 4.664 ns: it now chains the multiply after the read, and still writes one stage later. The stage is a scheduling choice, not a timing one. Not tried yet: a latency directive on the beat loop (`set_directive_latency -max 0`), or a combinational top. The 10 ns Verilog is left uncommitted in hls-exercises (`rtl/done/vecadd/opt_w8_c10/`, `rtl/done/vecmul/opt_w8_c10/`), because its names match the batch globs `done/*/*_w*`.

## 6. Control ports, side by side

| Function | Forge | HLS |
|---|---|---|
| Clock, reset | `clk_i`, `rst_ni` | `ap_clk`, `ap_rst_n` |
| Start | a CSR write to address 0 with bit 0 set, over the CSR request bus: `csr_req_valid_i`, `csr_req_ready_o`, `csr_req_write_i`, `csr_req_addr_i[31:0]`, `csr_req_data_i[31:0]` | one wire `ap_start`, held high by the driver until `ap_ready` |
| Configuration | more CSR writes on the same bus: JOBS (address 1), for vsum and dot JOB_BEATS (address 2) | pins `loop_count[31:0]` + `loop_count_ap_vld`, for vsum and dot `len[31:0]` + `len_ap_vld`, given for one cycle at start |
| Read-back | CSR response bus: `csr_rsp_valid_o`, `csr_rsp_ready_i`, `csr_rsp_data_o[31:0]` (START, JOBS, STATUS, COUNTER) | none |
| Status | `<group>_busy_o`, `<group>_done_o`, the STATUS CSR | `ap_idle`, `ap_ready`, `ap_done` |

Forge's control arrives through an addressable bus that also reads back; HLS's through dedicated wires whose values the driver outside holds.

## 7. Control registers, side by side (nangate45, W = 8)

dot (forge dot 3 against HLS dot opt), flops and energy per cycle:

| Function | Forge dot 3 | HLS dot opt | Both? |
|---|---|---|---|
| Hold the settings | CSRs JOBS + JOB_BEATS: 64 (0.46 pJ) | `loop_count_preg` + `len_preg` + 2 valid bits: 66 (0.46 pJ) | yes, same cost; both 32-bit |
| Copies of the settings | ctrl's `sum_t`, `sum_r`, `mul_r` (= jobs × beats), loaded at START: 96 (0.69 pJ) | none | forge only |
| Start | START CSR, 32 bits: 32 (0.23 pJ) | none: `ap_start` comes from outside | forge only |
| CSR read buffer | `answer` + `answerKept`: 33 (0.24 pJ) | none: no read port | forge only |
| Performance counter | COUNTER, counts every busy cycle: 32 (0.24 pJ) | none: the testbench counts | forge only |
| Progress counters | `mul_given` (the multiply unit's beats), `sum_d` (beat within the current sum), `sum_given` (results out): 96 (0.71 pJ) | `b` (beats), `cnt` (beat within the current sum): 64 (0.45 pJ) | partly: same job, forge counts per unit (one counter more) |
| State | busy, done, done pulse, valid: 4 (0.03 pJ) | FSM 3, pipeline enables 4, loop conditions 3: 10 (0.07 pJ) | yes, small |
| **Total** | **357 flops, 2.60 pJ per cycle** | **140 flops, 0.98 pJ per cycle** | |

vecadd is the same pattern: forge has JOBS (32), its copy `acc_r` (32), START (32), the read buffer (33), COUNTER (32), one progress counter `acc_given` (32) and 3 state bits, 196 flops and 1.42 pJ per cycle; HLS opt has `loop_count_preg` + valid (33), the beat counter `b` (32) and 5 state bits, 70 flops and 0.49 pJ per cycle.

Notes on single registers: the START pulse fires from the CSR write itself (address 0, bit 0), so the 32-bit START register only keeps the written value for reading back. HLS's pins are 32-bit too (`cfg_t` is `uint32_t`): HLS does not save width, it holds fewer words. HLS dace also keeps copies of its pin (`N_reg_*`, `trunc_*`).

## 8. The same flops in three groups

| Group | Forge dot 3 | HLS dot opt |
|---|---|---|
| Shared minimal control: settings held once, two counters, state | 132 flops, about 0.96 pJ per cycle | 140 flops, 0.98 pJ per cycle |
| Configuration interface: START word, CSR read buffer, COUNTER | 97 flops, about 0.71 pJ per cycle | none: outside the block |
| Per-unit structure for runs of several jobs: ctrl's copies of the settings, the extra counter | 128 flops, about 0.93 pJ per cycle | none: one job per start |

Like for like, the two control blocks cost about the same. Forge's extra 2.1 to 2.9x (control flops) is what HLS's boundary leaves outside (the CSR interface) or what HLS does not implement (several jobs per START). Without the copies, START word, read buffer and COUNTER, forge's control flops are 0.9 to 1.3x HLS opt's over all kernels, W and both technologies.

## 9. The proposed boundary: settings outside, sequencing in the block

Idea (from the review): forge's "control" should be only the settings (the CSRs: how many loops, when to start), and the loop counters and valid-ready handshakes should belong to the datapath blocks, as in HLS, where the block owns its loop control and the settings come from outside. Re-split on that boundary (dot, nangate45, W = 8):

| | Forge dot 3 | HLS dot opt |
|---|---|---|
| Settings, the external control (CSRs or pins, START, read buffer, COUNTER) | 161 flops: JOBS, JOB_BEATS, START, read buffer, COUNTER | 66 flops: the latched pins `loop_count`, `len` |
| Sequencing inside the block (counters, handshake, state) | 196 flops: 96 copies of the settings, 96 counters, 4 state | 74 flops: 64 counters, 10 FSM, enable and condition bits |

Even on this boundary forge's sequencing is larger: 96 of its flops are copies of the settings and 32 are a third counter.

As a comparison boundary it is a good one, and it can be computed from SYN1's existing data. As an RTL change it reverses snax-forge's D147: "Every block is a datapath of data and enables only, under one control unit per group (`<tag>_<group>_ctrl`) generated from the description, so control is written once for model and RTL, never per variant." D146 sets the group's interface: one JOBS per group, its own START, STATUS, COUNTER, busy and done pins, so groups run apart. Reasons for D147: one generated control shared by snax-gvsoc's model and the RTL; a block library of data and enables that composes and keeps CHAR1's per-block cost tables simple. Moving the counters into the blocks would write sequencing per block, make chained units coordinate across blocks (the sum fires once every T beats of the multiply), and move the cost rather than remove it.

## 10. What would bring forge's control closer to HLS within D147

1. Drop the copies of the settings: ctrl reads JOBS and JOB_BEATS straight from the CSRs, CSR writes blocked while busy. 96 flops in dot 3.
2. Do not store START: the pulse already comes from the write; reading START could return 0 or STATUS. 32 flops.
3. Make COUNTER and the CSR read buffer optional (observability; HLS keeps them outside). 65 flops.
4. Size the counters from a maximum N instead of 32 bits (12 bits are enough at n2048). Helps both sides alike.

Items 1 to 3 take dot 3's control from 357 flops to about 164, near HLS's 140, without changing which block owns what. Each 32-bit register is about 0.23 pJ per cycle on nangate45.

## 11. Options to pick from

- **SYN1 view (cheap, existing data):** add the settings-against-sequencing boundary of section 9 and the three groups of section 8 to the analysis, beside the current split.
- **HLS with a CSR block:** one HLS point with `s_axilite` on the pins and on `return`, so Vitis generates its own register file (`<top>_control_s_axi`: ap_start, ap_done, ap_idle bits, loop_count, len, read-back). It puts a CSR block inside HLS's boundary too; still not equal to forge's (AXI4-Lite's five channels against forge's request/response bus, and no cycle counter).
- **HLS without the register stage:** try a latency directive on the beat loop, then synthesize and measure, to replace section 4's estimate with a number.
- **snax-forge trimming within D147:** items 1 to 3 of section 10 on a branch with a PR, then SYN1's flow again on the trimmed points.
- **Revisit D147:** the proposed boundary as RTL (counters and handshakes in the blocks). A design decision for snax-forge, with the trade-offs of section 9.
- **Streamers:** synthesize snax_cluster's streamers, so both sides' operand registers are on the same side of the boundary.

## 12. Open questions

- Which boundary should the paper's comparison use: the block as synthesized, the block plus streamers, or settings against sequencing?
- What does forge need of COUNTER, the read buffer and START's storage in a real cluster, and can they be optional per design?
- Do runs of several jobs (J > 1) need ctrl's copies, or can the CSRs be held stable while busy?
- How much do narrower counters save on each side?
- Can Vitis be made to drop its register stage, and what is HLS opt's energy then?
- What does Vitis's own CSR block (`s_axilite`) cost against forge's csr?

## Where the data is

- `results/analysis/syn1/syn1_analysis.md`: sections 9 (the split) and 10 (control by role, the register stage), figures `fig8_control_split.png` (control's share of e_run) and `fig9_energy_split.png` (e_run as stacked bars: control, datapath flops, datapath logic).
- `results/analysis/syn1/split_<tech>.csv`, `split_regs_<tech>.csv`, `split_checks_<tech>.csv`: the split per point, per register, and its checks (`report/flop_split.py`, `pixi run split pt` then `pixi run split collect`).
- `report/analysis_syn1.py` (`pixi run analysis`): the note and every figure.
- Forge's RTL per point: `rtl/forge/<point>/rtl/sv/` (`snax_forge_csr.sv`, `snax_forge_*_ctrl.sv`); HLS's: hls-exercises `rtl/done/<kernel>/<case>_w<W>/`.
- snax-forge decisions: `docs/DECISIONS.md` D146, D147; the RTL spec `docs/CONTRACTS.md` §17.
