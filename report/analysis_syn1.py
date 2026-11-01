#!/usr/bin/env python3
"""report/analysis_syn1.py - SYN1's analysis note: what the data shows, what it does not, what to ask next.

  pixi run analysis

Reads only what is committed or checked out read-only, and changes none of it:
  results/forge_vs_hls_<tech>.csv                 R4's joined table (report/forge_vs_hls.py)
  results/{hls,forge}/<tech>/synth_dc.csv         combinational and sequential area
  results/{hls,forge}/<tech>/power_pt.csv         e_comb, e_flop, e_clk, e_reg per cycle at n2048
  results/forge/<tech>/synth_dc_modules.csv       forge's module tree (area, comb, seq)
  results/forge/<tech>/power_pt_modules.csv       forge's module tree (e_dyn per cycle)
  results/hls/hls_cycles.csv                      cosim's line per HLS point
  results/hls/<tech>/reports/<point>/reference.rpt  the flop cell's unit area
  ../hls-exercises/rtl/done/<kernel>/<point>/*.v  Vitis's Verilog: which registers are flops, by name
  rtl/forge/<point>/rtl/sv/*.sv                   forge's bundles: the registers of csr and ctrl, by name
and writes results/analysis/syn1/syn1_analysis.md and its PNG figures. Every number in the note is computed
here; nothing is typed by hand. The note decides nothing: it lays out observations, explanations (with how
sure each is) and open questions for review.
"""
from __future__ import annotations

import csv
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "analysis" / "syn1"
HLS_RTL = Path(os.environ.get("SIM_HLS", ROOT.parent / "hls-exercises")) / "rtl"
FORGE_RTL = ROOT / "rtl" / "forge"
TECHS = ["nangate45", "nangate15"]
KERNELS = ["vecadd", "vecmul", "vsum", "dot"]
WS = [1, 2, 4, 8, 16, 32]
N = 2048
HLS_CASES = ["unopt", "opt", "dace"]
FORGE_CASES = {"vecadd": ["forge"], "vecmul": ["forge"], "vsum": ["forge"],
               "dot": ["forge2", "forge3", "forge4", "forge5", "forge6"]}
DOT_FORGE = FORGE_CASES["dot"]
DOT_HLS = ["unopt", "opt"]                       # dace parked (RAM), dace_w1 only
DOT_BLOCKS = {"forge2": "multiply lanes, link buffer, adder tree", "forge3": "multiply lanes, adder tree",
              "forge4": "MAC lanes, adder tree", "forge5": "MAC lanes, serial sum",
              "forge6": "MAC lanes, link buffer, serial sum"}
STYLE = {"unopt": ("tab:red", "o", "-"), "opt": ("tab:blue", "s", "-"), "dace": ("tab:purple", "^", "-"),
         "forge": ("tab:green", "D", "-"), "forge2": ("tab:olive", "v", "-"), "forge3": ("tab:green", "D", "-"),
         "forge4": ("tab:orange", "P", "-"), "forge5": ("tab:brown", "X", "-"), "forge6": ("tab:gray", "*", "-")}


# ---------------------------------------------------------------- reading
def read(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def fnum(x):
    return float(x) if x not in ("", None) else None


def load():
    D = {}       # (tech, kernel, case, W) -> merged dict, ok rows only
    status = {}  # (tech, kernel, case, W) -> status
    for tech in TECHS:
        syn = {s: {r["point"]: r for r in read(RES / s / tech / "synth_dc.csv")} for s in ("hls", "forge")}
        pwr = {s: {r["point"]: r for r in read(RES / s / tech / "power_pt.csv") if r["size"] == "n2048"}
               for s in ("hls", "forge")}
        fmod_a = defaultdict(dict)
        for r in read(RES / "forge" / tech / "synth_dc_modules.csv"):
            fmod_a[r["point"]][r["path"]] = r
        fmod_e = defaultdict(dict)
        for r in read(RES / "forge" / tech / "power_pt_modules.csv"):
            fmod_e[r["point"]][r["path"]] = float(r["e_dyn_pj"])
        for r in read(RES / f"forge_vs_hls_{tech}.csv"):
            key = (tech, r["kernel"], r["case"], int(r["W"]))
            status[key] = r["status"]
            if r["status"] != "ok":
                continue
            s, p = syn[r["side"]][r["point"]], pwr[r["side"]][r["point"]]
            d = {"tech": tech, "kernel": r["kernel"], "case": r["case"], "W": int(r["W"]), "side": r["side"],
                 "point": r["point"], "cycles": int(r["cycles"]), "area": float(r["area_um2"]),
                 "comb": float(s["comb_area_um2"]), "seq": float(s["seq_area_um2"]), "flops": int(r["flops"]),
                 "fmax": float(r["fmax_mhz"]), "e_run": float(r["e_run_nj"]), "pj_elem": float(r["pj_per_elem"]),
                 "e_dyn": float(p["e_dyn_pj"]), "e_comb": float(p["e_comb_pj"]), "e_flop": float(p["e_flop_pj"]),
                 "e_clk": float(p["e_clk_pj"]), "e_reg": float(p["e_reg_pj"])}
            if r["side"] == "forge":
                d.update({k: float(r[f"{k}_um2"]) for k in ("csr", "ctrl", "datapath", "glue")})
                top = "snax_forge_shell_wrapper"
                em = fmod_e[r["point"]]
                d.update({"e_csr": em[f"{top}/csr"], "e_ctrl": em[f"{top}/ctrl"], "e_dp": em[f"{top}/dp"]})
                d["mods"] = fmod_a[r["point"]]
                d["mods_e"] = em
            D[key] = d
    return D, status


def flop_unit_area(tech: str) -> float:
    """The library's flop area, from a committed reference.rpt (nangate15: DFFRNQ_X1 = DFFSNQ_X1)."""
    rpt = RES / "hls" / tech / "reports" / "done" / "dot" / "opt_w4" / "reference.rpt"
    m = re.search(r"^(DFF\w+)\s+\S+\s+([\d.]+)\s+(\d+)", rpt.read_text(), re.M)
    return float(m.group(2))


def hls_registers(kernel: str, case: str, w: int) -> tuple[Counter, int, dict]:
    """Bits of every name Vitis assigns on the clock edge, by class; the loop pipeline's depth; the names per class."""
    c = Counter()
    names = defaultdict(set)
    depth = 0
    for v in sorted((HLS_RTL / "done" / kernel / f"{case}_w{w}").glob("*.v")):
        t = v.read_text()
        width = {}
        for m in re.finditer(r"^\s*(?:\(\*[^*]*\*\)\s*)?reg\s+(?:signed\s+)?(?:\[(\d+):(\d+)\]\s+)?(\w+)\s*;", t, re.M):
            width[m.group(3)] = (int(m.group(1)) - int(m.group(2)) + 1) if m.group(1) else 1
        for m in re.finditer(r"^\s*(?:\(\*[^*]*\*\)\s*)?reg\s+(?:signed\s+)?\[[^\]]*[A-Za-z_][^\]]*\]\s+(\w+)\s*;", t, re.M):
            width.setdefault(m.group(1), None)        # parameterized width: counted as unknown
        flops = set()
        for m in re.finditer(r"always\s*@\s*\(\s*posedge\s+ap_clk\s*\)", t):
            k = t.index("begin", m.end())
            j, lvl = k + 5, 1
            while lvl:
                mm = re.compile(r"\bbegin\b|\bend\b").search(t, j)
                lvl += 1 if mm.group(0) == "begin" else -1
                j = mm.end()
            flops |= set(re.findall(r"(\w+)\s*<=", t[k:j]))
        for n in sorted(flops):
            b = width.get(n)
            if b is None:
                c["parameter-width names"] += 1
                continue
            base = re.sub(r"_pp\d+_iter\d+_reg$", "", n)
            if n.startswith("ap_") or n.endswith("_ap_start_reg"):
                k2 = "control (FSM, pipeline enables)"
            elif base.endswith("_preg"):
                k2 = "pins (loop_count, len)"
            elif re.search(r"_fu_\d+$", base):
                k2 = "loop state (accumulator, counters)"
            elif re.search(r"_reg_\d+$", base) and b > 1:
                k2 = "data pipeline (operands, products)"
            elif re.search(r"_reg_\d+$", base):
                k2 = "conditions"
            else:
                k2 = "other"
            c[k2] += b
            names[k2].add(re.sub(r"(_\d+)?_reg_\d+$", "", base))
        for m in re.finditer(r"ap_enable_reg_pp\d+_iter(\d+)", t):
            depth = max(depth, int(m.group(1)) + 1)
    return c, depth, names


def forge_registers(point: str, design_like: str) -> list[tuple[str, int]]:
    """(name, bits) of every reg in the bundle's module file matching design_like (Chisel: every reg is a flop)."""
    out = []
    for f in sorted((FORGE_RTL / point / "rtl" / "sv").glob("*.sv")):
        if not re.search(design_like, f.stem):
            continue
        for m in re.finditer(r"^\s*reg\s+(?:\[(\d+):(\d+)\]\s+)?(\w+)\s*;", f.read_text(), re.M):
            out.append((m.group(3), (int(m.group(1)) - int(m.group(2)) + 1) if m.group(1) else 1))
    return out


def cosim_lines():
    pts = defaultdict(list)
    for r in read(RES / "hls" / "hls_cycles.csv"):
        if r["tier"] == "done" and r["cosim_lat_avg"]:
            lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
            pts[(r["kernel"], r["case"], int(r["W"]))].append((lc, float(r["cosim_lat_avg"])))
    out = {}
    for k, v in pts.items():
        (l1, c1), (l2, c2) = sorted(v)[:2]
        a = (c2 - c1) / (l2 - l1)
        out[k] = (a, c1 - a * l1)
    return out


# ---------------------------------------------------------------- helpers
def fit(xs, ys):
    """Least squares y = slope x + intercept; R² (1 when y is constant and fitted exactly)."""
    x, y = np.asarray(xs, float), np.asarray(ys, float)
    slope, icpt = np.polyfit(x, y, 1)
    res = y - (slope * x + icpt)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    ss_res = float((res ** 2).sum())
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else (1.0 if ss_res < 1e-18 else 0.0)
    return float(slope), float(icpt), r2, float(np.abs(res).max())


def g(x, nd=1):
    if x is None:
        return ""
    if isinstance(x, int):
        return f"{x:,}"
    return f"{x:,.{nd}f}"


def pct(a, b):
    return 100.0 * a / b


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out


def cases(kernel):
    return [c for c in HLS_CASES] + FORGE_CASES[kernel]


def label(case):
    return {"forge": "forge", "forge2": "dot 2", "forge3": "dot 3", "forge4": "dot 4", "forge5": "dot 5",
            "forge6": "dot 6"}.get(case, f"HLS {case}")


def full(k, c):
    return label(c) if c.startswith("forge") and k == "dot" else f"{k} {label(c)}"


def dn(k, c):
    return label(c) if k == "dot" else k


def pt(k, c, w):
    return f"`{k}/{c}_w{w}`"


def savefig(fig, name):
    fig.savefig(OUT / name, dpi=110, metadata={"Software": None})
    plt.close(fig)


# ---------------------------------------------------------------- the analysis
def main() -> int:
    D, status = load()
    lines = cosim_lines()
    unit = {t: flop_unit_area(t) for t in TECHS}
    OUT.mkdir(parents=True, exist_ok=True)
    md: list[str] = []
    S: list[str] = []   # summary lines, filled as findings are computed
    Q: list[str] = []   # open questions
    M: list[str] = []   # candidate metrics or figures

    def get(tech, k, c, w):
        return D.get((tech, k, c, w))

    def series(tech, k, c, key):
        return [(w, get(tech, k, c, w)[key]) for w in WS if get(tech, k, c, w)]

    n_ok = Counter((k[0], D[k]["side"]) for k in D)

    # ------------------------------------------------ 1. cycles
    cyc_same = all(get("nangate45", k, c, w)["cycles"] == get("nangate15", k, c, w)["cycles"]
                   for (t, k, c, w) in D if t == "nangate45" and get("nangate15", k, c, w))
    def forge_over(k, c, w):
        return {"forge": 1 if k == "vsum" else 0, "forge2": 2, "forge3": 1, "forge4": 2,
                "forge5": w + 1, "forge6": w + 2}[c]
    forge_match = [(k, c, w) for (t, k, c, w), d in D.items() if t == "nangate45" and d["side"] == "forge"
                   and d["cycles"] - N // w == forge_over(k, c, w)]
    forge_all = [(k, c, w) for (t, k, c, w), d in D.items() if t == "nangate45" and d["side"] == "forge"]
    depth = {}
    hregs = {}
    hnames = {}
    for (t, k, c, w), d in D.items():
        if t == "nangate45" and d["side"] == "hls":
            hregs[(k, c, w)], depth[(k, c, w)], hnames[(k, c, w)] = hls_registers(k, c, w)
    opt_b = {(k, c, w): round(lines[(k, c, w)][1]) for (k, c, w) in hregs if c in ("opt", "dace")}
    unopt_a = {(k, w): lines[(k, "unopt", w)][0] for k in KERNELS for w in WS if (k, "unopt", w) in lines}

    md += ["## 1. Cycles", ""]
    md.append(f"Cycles beyond the beats, cycles − N / W, at n2048 (N / W beats per input stream). The counts are the same on both technologies ({'every' if cyc_same else 'not every'} point). Forge's window is the COUNTER read back (X23), HLS's the `ap_start` to `ap_done` window (X12). Figure `fig1_cycles_overhead.png`: the same numbers against W.")
    md.append("")
    for k in KERNELS:
        cs = [c for c in cases(k) if any(get("nangate45", k, c, w) for w in WS)]
        rows = []
        for w in WS:
            r = [w, N // w]
            for c in cs:
                d = get("nangate45", k, c, w)
                r.append(g(d["cycles"] - N // w) if d else "parked" if status.get(("nangate45", k, c, w), "").startswith("skipped") else "")
            rows.append(r)
        md.append(f"**{k}** (cycles − N / W)")
        md.append("")
        md += table(["W", "N / W"] + [label(c) for c in cs], rows)
        md.append("")
    md += ["### Observations", ""]
    md.append(f"- Forge's extra cycles are 0 (vecadd, vecmul), 1 (vsum, dot 3), 2 (dot 2, dot 4), W + 1 (dot 5) and W + 2 (dot 6): {len(forge_match)} of {len(forge_all)} forge rows (`done/*/forge*_w*`, nangate45).")
    ob = sorted(set(opt_b[x] for x in opt_b if x[1] == "opt"))
    md.append(f"- HLS opt's extra cycles are {', '.join(map(str, ob))} at every W; dace's {', '.join(map(str, sorted(set(opt_b[x] for x in opt_b if x[1] == 'dace'))))}.")
    ua = ", ".join(f"{k} {'/'.join(g(unopt_a[(k, w)], 0) for w in WS)}" for k in KERNELS)
    md.append(f"- HLS unopt takes a cycles per beat (cosim's line a x loop_count + 1), a at W = 1, 2, 4, 8, 16, 32: {ua}. So at W ≥ 2 its window is {min(get('nangate45', k, 'unopt', w)['cycles'] / N for k in KERNELS for w in WS[1:]):.2f} to {max(get('nangate45', k, 'unopt', w)['cycles'] / N for k in KERNELS for w in WS[1:]):.2f} cycles per element.")
    d5 = get("nangate45", "dot", "forge5", 32)
    md.append(f"- The largest forge overhead is dot 6 at W = 32: {get('nangate45', 'dot', 'forge6', 32)['cycles']} cycles for {N // 32} beats; dot 5: {d5['cycles']} ({pt('dot', 'forge5', 32)}).")
    md += ["", "### Explanations", ""]
    md.append(f"- **Forge: C§17's closed forms** (snax-forge `docs/CONTRACTS.md` §17, J = 1 job of T = N / W beats): C2 = T + 2, C3 = T + 1, C4 = T + 2, C5 = T + W + 1, C6 = T + W + 2; vecadd and vecmul T, vsum's tree T + 1. Sure: the formula gives every forge row exactly ({len(forge_match)} of {len(forge_all)}). dot 5 and 6 pay W cycles because their serial sum reads one lane per cycle after the MAC lanes finish; dot 4's tree adds them in one cycle.")
    md.append(f"- **HLS opt and dace: the pipeline's depth.** The extra cycles equal the loop pipeline's depth in the Verilog (the number of `ap_enable_reg_pp0_iter<k>` stages) on {sum(1 for x in opt_b if opt_b[x] == depth[x])} of {len(opt_b)} opt and dace points; where they differ: {', '.join(f'{x[0]}/{x[1]}_w{x[2]} (extra {opt_b[x]}, depth {depth[x]})' for x in sorted(opt_b) if opt_b[x] != depth[x]) or 'none'}. Fairly sure: the depth is read from the RTL, the extra cycles from cosim's line; an extra cycle for the FSM's start state may account for the differences.")
    md.append("- **HLS unopt: the lanes are not pipelined.** unopt keeps NPBench's loop structure with no directives and `pipeline_loops 0` (hls-exercises `docs/HLS_VS_FORGE.md` §1), so each beat's W lanes run one after another: a grows with W. Sure for the mechanism (it is how the case is defined); the exact a per W is cosim's.")
    md += ["", "### Questions", ""]
    md.append("- Forge's window starts at the accepted START and excludes the CSR writes and the streamers' own latency; HLS's starts at `ap_start` with the pins already set. Does the comparison need the cluster-level count (snax_cluster RTL with the streamers, BASE1) to be fair? A run of the dot variants on snax_cluster's RTL at n2048 would answer it.")
    md.append("")
    Q.append("Cycles: is the accelerator window (COUNTER) the right count for the comparison, or the cluster-level one with streamers and CSR writes? Needs snax_cluster RTL runs at n2048 (section 1).")

    fig, axs = plt.subplots(1, 4, figsize=(16, 3.8))
    for ax, k in zip(axs, KERNELS):
        for c in cases(k):
            s = [(w, get("nangate45", k, c, w)["cycles"] - N // w) for w in WS if get("nangate45", k, c, w)]
            if not s:
                continue
            col, mk, ls = STYLE[c]
            ax.plot([x for x, _ in s], [max(y, 0.5) for _, y in s], marker=mk, color=col, ls=ls, label=label(c))
        ax.set_xscale("log", base=2); ax.set_yscale("log")
        ax.set_title(k); ax.set_xlabel("W"); ax.set_xticks(WS, [str(w) for w in WS])
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=6, loc="upper left")
    axs[0].set_ylabel("cycles − N/W (0 drawn at 0.5)")
    fig.suptitle("Cycles beyond the beats at n2048 (both technologies)")
    fig.tight_layout()
    savefig(fig, "fig1_cycles_overhead.png")

    # ------------------------------------------------ 2. control overhead
    md += ["## 2. Control overhead", ""]
    md.append("Forge's csr and ctrl, the wrapper's two control instances (X22), against W. Shares are of the accelerator's total area and of e_run. Figure `fig2_control_share.png`: the shares against W, both technologies.")
    md.append("")
    designs = [(k, c) for k in KERNELS for c in FORGE_CASES[k]]
    thresh = {}
    for tech in TECHS:
        rows = []
        for k, c in designs:
            ds = [get(tech, k, c, w) for w in WS]
            ca = [d["csr"] + d["ctrl"] for d in ds]
            sa = [pct(d["csr"] + d["ctrl"], d["area"]) for d in ds]
            se = [pct((d["e_csr"] + d["e_ctrl"]) * d["cycles"] / 1000, d["e_run"]) for d in ds]
            def first_below(vals, lim):
                for w, v in zip(WS, vals):
                    if v < lim:
                        return w
                return None
            thresh[(tech, k, c)] = (first_below(sa, 10), first_below(sa, 5), first_below(se, 10), first_below(se, 5))
            rows.append([dn(k, c), f"{g(min(ca), 0)}–{g(max(ca), 0)}",
                         " / ".join(g(v, 1) for v in sa), " / ".join(g(v, 1) for v in se),
                         *(f"W = {x}" if x else "> 32" for x in thresh[(tech, k, c)])])
        md.append(f"**{tech}** (shares at W = 1 / 2 / 4 / 8 / 16 / 32; the first W below each threshold)")
        md.append("")
        md += table(["design", "csr + ctrl µm²", "area share %", "e_run share %", "area < 10 %", "area < 5 %",
                     "e_run < 10 %", "e_run < 5 %"], rows)
        md.append("")
    # what ctrl holds
    inv_rows = []
    for k, c in designs:
        p = f"done/{k}/{c}_w4"
        ctrl_regs = [x for x in forge_registers(p, r"^snax_forge_(?!ctrl$)\w+_ctrl$")]
        csr_regs = forge_registers(p, r"^snax_forge_csr$")
        w32 = sum(1 for _, b in ctrl_regs if b == 32)
        inv_rows.append([dn(k, c), sum(b for _, b in csr_regs),
                         sum(b for _, b in ctrl_regs), w32, ", ".join(n for n, b in ctrl_regs if b == 32)])
    u15 = unit["nangate15"]
    chk = []
    for k, c in designs:
        for w in WS:
            d = get("nangate15", k, c, w)
            m = d["mods"]
            n_csr = float(m["csr"]["seq_um2"]) / u15
            n_ctrl = sum(float(r["seq_um2"]) for pth, r in m.items() if pth.startswith("ctrl")) / u15
            n_dp = sum(float(r["seq_um2"]) for pth, r in m.items() if pth.startswith("dp")) / u15
            chk.append((k, c, w, n_csr, n_ctrl, n_dp, d["flops"]))
    exact = sum(1 for x in chk if abs(x[3] + x[4] + x[5] - x[6]) < 0.01 and all(abs(v - round(v)) < 0.01 for v in x[3:6]))
    md.append(f"What the control holds (registers in the bundle's SV at W = 4; Chisel declares a `reg` only for a flop). On nangate15 every flop has the same area ({u15:g} µm², `reference.rpt`), so a module's flops are its sequential area over that: csr + ctrl + datapath = DC's flop count on {exact} of {len(chk)} forge points.")
    md.append("")
    md += table(["design", "csr flop bits", "ctrl flop bits", "32-bit registers in ctrl", "their names"], inv_rows)
    md.append("")
    # fits
    fit_rows, model_rows = [], []
    model = {}
    for tech in TECHS:
        for k, c in designs:
            ds = [get(tech, k, c, w) for w in WS]
            ec = [d["e_csr"] + d["e_ctrl"] for d in ds]
            s1, i1, r1, _ = fit(WS, ec)
            edp = [d["e_dp"] * d["cycles"] / 1000 for d in ds]
            s2, i2, r2, _ = fit(WS, edp)
            cy = [d["cycles"] for d in ds]
            er = [d["e_run"] for d in ds]
            a3, b3, r3, mx3 = fit(cy, er)
            model[(tech, k, c)] = (a3, b3, r3, max(abs(a3 * x + b3 - y) / y for x, y in zip(cy, er)))
            fit_rows.append([tech, dn(k, c), g(i1, 3), g(s1, 4), g(r1, 2),
                             f"{100 * (max(ec) - min(ec)) / np.mean(ec):.1f}",
                             g(i2, 3), g(s2, 4), g(r2, 2), f"{100 * (edp[-1] - edp[0]) / edp[0]:+.1f}"])
            model_rows.append([tech, dn(k, c), g(1000 * a3, 3), g(b3, 3), f"{r3:.4f}",
                               f"{100 * model[(tech, k, c)][3]:.1f}",
                               g(1000 * a3 - np.mean(ec), 3)])
    md.append("**Fits over W** (6 points per design). (a) csr + ctrl energy per cycle (pJ) against W: intercept, slope per lane, R² and the spread (max − min over the mean). (b) the datapath's energy per task (nJ, e_dp x cycles) against W: intercept, slope, R² and the change from W = 1 to 32. R² says little where the slope is near 0; the spread and the change say whether the quantity is flat.")
    md.append("")
    md += table(["tech", "design", "(a) icpt pJ", "(a) slope pJ/lane", "(a) R²", "(a) spread %",
                 "(b) icpt nJ", "(b) slope nJ/lane", "(b) R²", "(b) W 1→32 %"], fit_rows)
    md.append("")
    md.append("**The two-term model** e_run = α C + β, fitted over W per design (x = the cycles C): α is an energy per cycle (pJ), β an energy per task (nJ). The HWCOST shape $E_{\\mathit{task}} = C \\thinspace e_{\\mathit{ctrl}} + n_{\\mathit{fire}} \\thinspace E_{\\mathit{block}}$ is this with α = e_ctrl and β = n_fire E_block. The last column compares α with the measured csr + ctrl energy per cycle (mean over W).")
    md.append("")
    md += table(["tech", "design", "α pJ/cycle", "β nJ", "R²", "max error %", "α − (csr + ctrl) pJ/cycle"], model_rows)
    md.append("")
    # the datapath's blocks: which cost per cycle, which per task
    blk_rows, blk = [], {}
    for tech in TECHS:
        for k, c in designs:
            if k == "vecadd" or k == "vecmul":
                continue
            per = defaultdict(list)
            for w in WS:
                d = get(tech, k, c, w)
                for pth, e in sorted(d["mods_e"].items()):
                    rel = pth.split("/", 1)[1] if "/" in pth else ""
                    parts = rel.split("/")
                    if len(parts) == 2 and parts[0] == "dp":
                        kind = re.sub(r"_\d+$", "", parts[1])          # blocks_0, blocks_1, bufs_0
                        design = d["mods"].get(rel, {}).get("design", "")
                        per[(kind, re.sub(r"^snax_forge_", "", design))].append((d["cycles"], e * d["cycles"] / 1000, e))
            for (kind, design), v in sorted(per.items()):
                a_, b_, r_, _ = fit([x for x, _, _ in v], [y for _, y, _ in v])
                blk[(tech, k, c, design)] = (1000 * a_, b_)
                blk_rows.append([tech, dn(k, c), design, g(v[0][2], 3), g(v[-1][2], 3), g(v[0][1], 3), g(v[-1][1], 3),
                                 g(1000 * a_, 3), g(b_, 3)])
    md.append("**The datapath's blocks**: energy per cycle (pJ) and per task (nJ) at W = 1 and W = 32, and the same two-term fit per block (α per cycle, β per task). vecadd's and vecmul's datapath is one elementwise block (fit (b): flat).")
    md.append("")
    md += table(["tech", "design", "block", "pJ/cycle W 1", "pJ/cycle W 32", "nJ/task W 1", "nJ/task W 32", "α pJ/cycle", "β nJ"], blk_rows)
    md.append("")
    hmodel, hm_rows = {}, []
    for tech in TECHS:
        for k in KERNELS:
            for c in ("opt", "dace"):
                ds = [get(tech, k, c, w) for w in WS if get(tech, k, c, w)]
                if len(ds) < 3:
                    continue
                a3, b3, r3, _ = fit([d["cycles"] for d in ds], [d["e_run"] for d in ds])
                err = max(abs(a3 * d["cycles"] + b3 - d["e_run"]) / d["e_run"] for d in ds)
                hmodel[(tech, k, c)] = (a3, b3, r3, err)
                fa = model[(tech, k, FORGE_CASES[k][0] if k != "dot" else "forge3")][0]
                hm_rows.append([tech, k, label(c), g(1000 * a3, 3), g(b3, 3), f"{r3:.4f}", f"{100 * err:.1f}",
                                f"{g(1000 * fa, 3)} ({dn(k, FORGE_CASES[k][0] if k != 'dot' else 'forge3')})"])
    md.append("**The same fit on HLS opt and dace**, for comparison: HLS's per-cycle term α holds its own fixed state (the pins, the loop's counters and accumulator, the FSM), its per-task term β the per-lane registers and the arithmetic. The last column is forge's α for the same kernel (dot: dot 3).")
    md.append("")
    md += table(["tech", "kernel", "case", "α pJ/cycle", "β nJ", "R²", "max error %", "forge α pJ/cycle"], hm_rows)
    md.append("")
    md += ["### Observations", ""]
    ctrl_fixed = {(k, c): (min(get(t, k, c, w)["ctrl"] for t in ["nangate45"] for w in WS),
                           max(get(t, k, c, w)["ctrl"] for t in ["nangate45"] for w in WS)) for k, c in designs}
    md.append(f"- ctrl's area hardly moves with W: on nangate45 it spans {', '.join(f'{dn(k, c)} {g(a, 0)}–{g(b, 0)} µm²' for (k, c), (a, b) in ctrl_fixed.items())}; csr {g(min(get('nangate45', k, c, w)['csr'] for k, c in designs for w in WS), 0)}–{g(max(get('nangate45', k, c, w)['csr'] for k, c in designs for w in WS), 0)} µm² over every design and W.")
    for tech in TECHS:
        def tw(x):
            return str(x) if x else "beyond 32"
        md.append(f"- {tech}: csr + ctrl falls below 10 % of the area at W = " + ", ".join(f"{tw(thresh[(tech, k, c)][0])} ({dn(k, c)})" for k, c in designs) + "; below 10 % of e_run at W = " + ", ".join(f"{tw(thresh[(tech, k, c)][2])} ({dn(k, c)})" for k, c in designs) + ".")
    worst_fit = max((((t, k, c), model[(t, k, c)][3]) for t in TECHS for k, c in designs), key=lambda z: z[1])
    good_fit = [(t, k, c) for t in TECHS for k, c in designs if model[(t, k, c)][3] < 0.02]
    md.append(f"- The two-term model fits {len(good_fit)} of {2 * len(designs)} design-technology pairs within 2 % at every W; the worst is {dn(worst_fit[0][1], worst_fit[0][2])} on {worst_fit[0][0]}, {100 * worst_fit[1]:.1f} %.")
    md += ["", "### Explanations", ""]
    md.append("- **ctrl and csr are fixed per accelerator, not per lane.** Their registers are 32-bit counters and CSR copies whose number depends on the group (its units, a JOB_BEATS), not on W (table above; C§17: the control keeps a register only for what changes at run time). Sure: the flop counts are read from the SV and match DC's.")
    md.append("- **Their energy is a cost per cycle.** The counters and CSR registers are clocked every cycle of the window, so csr + ctrl energy per cycle is near constant in W (spread in fit (a)) and their energy per task scales with the cycles, N / W + the overhead. The share therefore halves with each doubling of W. Sure where the spread is small; the measured per-cycle values come from PT's module rows.")
    def ex(tech, k, c):
        return 1000 * model[(tech, k, c)][0] - np.mean([get(tech, k, c, w)["e_csr"] + get(tech, k, c, w)["e_ctrl"] for w in WS])
    per_cycle = [(k, c) for k, c in designs if ex("nangate45", k, c) > 0.5]
    per_task = [(k, c) for k, c in designs if abs(ex("nangate45", k, c)) < 0.1]
    sums = {c: blk.get(("nangate45", "dot", c, "sum")) for c in DOT_FORGE}
    macs = {c: blk.get(("nangate45", "dot", c, "mac")) for c in DOT_FORGE}
    md.append("- **The datapath splits the same way, by what each block does per beat.** A block that does one 64-bit operation per beat, whatever W, costs per cycle: the accumulator of a tree that folds every beat (vsum, dot 2 and dot 3's `sum`). A block whose work is spread over the lanes costs per task: the multiply lanes, the MAC lanes (W accumulators, each updated once per beat, so N updates per task) and a link buffer of W words. On nangate45 α exceeds csr + ctrl's own per-cycle energy by more than 0.5 pJ on " + ", ".join(f"{dn(k, c)} ({ex('nangate45', k, c):.2f})" for k, c in per_cycle) + ", and by less than 0.1 pJ on " + ", ".join(f"{dn(k, c)} ({ex('nangate45', k, c):+.2f})" for k, c in per_task) + ". The block table shows it per block: dot 3's `sum` has α " + g(sums['forge3'][0], 2) + " pJ/cycle, dot 4's `sum` (folding once per job, after the MAC lanes) " + g(sums['forge4'][0], 2) + ", dot 4's `mac` " + g(macs['forge4'][0], 2) + " with β " + g(macs['forge4'][1], 2) + " nJ. Fairly sure: the per-block numbers are PT's module rows, the per-beat behaviour is C§17's (the fold reads every beat, a MAC lane fires once per beat); the fit has six points per design.")
    md.append("- **So α is not only csr + ctrl,** and the HWCOST shape holds per block: e_ctrl is csr + ctrl plus every block that works once per beat, E_block the rest per firing. dot 5 and 6's serial `sum` adds about " + g(ex('nangate45', 'dot', 'forge5'), 2) + " pJ per cycle on nangate45: it is busy only in the W-cycle tail.")
    md += ["", "### Questions", ""]
    md.append("- The counters are 32 bits because the CSRs are; at n2048 a beat count needs 12 bits. How much of ctrl's area and per-cycle energy would narrower counters save? A resynthesis with a counter width parameter in snax-forge's `GroupCtrl` would answer it (no such parameter exists today).")
    md.append("- Is csr + ctrl's cost a fixed cost per accelerator that a cluster pays once for several groups (dot 1 has two groups, not in SYN1)? A two-group design point in SYN1 would show whether csr and ctrl grow per group.")
    md.append("")
    Q.append("Control: how much would narrower counters (12 bits at n2048, today 32) save in ctrl's area and per-cycle energy? Needs a counter-width parameter and a resynthesis (section 2).")
    Q.append("Control: does csr + ctrl grow per group? Needs a two-group point such as dot 1 (section 2).")

    fig, axs = plt.subplots(2, 2, figsize=(11, 7), sharex=True)
    for j, tech in enumerate(TECHS):
        for k, c in designs:
            col, mk, _ = STYLE[c] if k == "dot" else ({"vecadd": "black", "vecmul": "tab:cyan", "vsum": "tab:pink"}[k], "o", "-")
            ds = [get(tech, k, c, w) for w in WS]
            lab = label(c) if k == "dot" else k
            axs[0][j].plot(WS, [pct(d["csr"] + d["ctrl"], d["area"]) for d in ds], marker=mk, color=col, label=lab)
            axs[1][j].plot(WS, [pct((d["e_csr"] + d["e_ctrl"]) * d["cycles"] / 1000, d["e_run"]) for d in ds], marker=mk, color=col, label=lab)
        for i in range(2):
            ax = axs[i][j]
            ax.set_xscale("log", base=2); ax.set_xticks(WS, [str(w) for w in WS])
            for lim in (10, 5):
                ax.axhline(lim, color="k", lw=0.6, ls=":")
            ax.grid(True, alpha=0.3)
        axs[0][j].set_title(f"{tech}: csr + ctrl, % of area")
        axs[1][j].set_title(f"{tech}: csr + ctrl, % of e_run")
        axs[1][j].set_xlabel("W")
    axs[0][0].legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "fig2_control_share.png")

    fig, axs = plt.subplots(2, 4, figsize=(16, 7))
    for j, tech in enumerate(TECHS):
        for i, k in enumerate(KERNELS):
            ax = axs[j][i]
            for c in FORGE_CASES[k]:
                ds = [get(tech, k, c, w) for w in WS]
                col, mk, _ = STYLE[c]
                x = [d["cycles"] for d in ds]
                ax.plot(x, [d["e_run"] for d in ds], marker=mk, ls="", color=col, label=label(c))
                a3, b3, _, _ = model[(tech, k, c)]
                xx = np.array([min(x), max(x)])
                ax.plot(xx, a3 * xx + b3, color=col, lw=0.8)
            ax.set_title(f"{k}, {tech}"); ax.set_xlabel("cycles C"); ax.grid(True, alpha=0.3)
            if i == 0:
                ax.set_ylabel("e_run nJ")
        axs[0][3].legend(fontsize=7)
    fig.suptitle("forge: e_run against cycles over W, with the fit e_run = α C + β")
    fig.tight_layout()
    savefig(fig, "fig7_two_term_fit.png")

    # ------------------------------------------------ 3. area
    md += ["## 3. Area", ""]
    md.append("Total area per kernel and W, forge against each HLS case; for forge also the datapath + ctrl (the accelerator without its CSR block). Figure `fig3_area.png`: totals against W, both technologies.")
    md.append("")
    for tech in TECHS:
        for k in KERNELS:
            cs = [c for c in cases(k) if any(get(tech, k, c, w) for w in WS)]
            rows = []
            for w in WS:
                r = [w]
                for c in cs:
                    d = get(tech, k, c, w)
                    r.append(g(d["area"], 0) if d else "parked")
                for c in FORGE_CASES[k]:
                    d = get(tech, k, c, w)
                    r.append(g(d["datapath"] + d["ctrl"], 0))
                rows.append(r)
            md.append(f"**{k}, {tech}** (µm²)")
            md.append("")
            md += table(["W"] + [label(c) for c in cs] + [f"{label(c)} dp + ctrl" for c in FORGE_CASES[k]], rows)
            md.append("")
    # linear fits of area
    afit = []
    afit_r2 = defaultdict(list)
    for tech in TECHS:
        for k in KERNELS:
            for c in FORGE_CASES[k]:
                s, i, r2, _ = fit(WS, [get(tech, k, c, w)["datapath"] for w in WS])
                afit.append([tech, k, f"{label(c)} datapath", g(s, 1), g(i, 1), f"{r2:.5f}"])
                afit_r2["dp"].append(r2)
            for c in ("opt", "unopt"):
                s, i, r2, _ = fit(WS, [get(tech, k, c, w)["area"] for w in WS])
                afit.append([tech, k, f"HLS {c} total", g(s, 1), g(i, 1), f"{r2:.5f}"])
                afit_r2[c].append(r2)
    md.append("**First-order fits of area against W** (µm² = slope W + intercept, 6 points):")
    md.append("")
    md += table(["tech", "kernel", "what", "slope µm²/lane", "intercept µm²", "R²"], afit)
    md.append("")
    # flops
    md.append("**Flops**, nangate45 (DC's `seq_cells`), and where they sit. Forge per module (nangate15's sequential area over the flop's area, the same counts on both technologies); HLS by class, from the names Vitis assigns on the clock edge in its Verilog (their bit sum next to DC's count, which differs by a few bits where DC merged or removed constant flops).")
    md.append("")
    frows = []
    for k in KERNELS:
        for w in (1, 4, 32):
            for c in FORGE_CASES[k]:
                x = next(x for x in chk if x[:3] == (k, c, w))
                frows.append([k, w, label(c), get("nangate45", k, c, w)["flops"], f"csr {round(x[3])}, ctrl {round(x[4])}, datapath {round(x[5])}"])
            for c in HLS_CASES:
                if (k, c, w) not in hregs:
                    continue
                cc = hregs[(k, c, w)]
                frows.append([k, w, label(c), get("nangate45", k, c, w)["flops"],
                              f"RTL {sum(cc.values())}: " + ", ".join(f"{n} {b}" for n, b in sorted(cc.items(), key=lambda z: -z[1]))])
    md += table(["kernel", "W", "case", "DC flops", "where"], frows)
    md.append("")
    # how much of the gap the flops explain
    gap_rows = []
    for tech in TECHS:
        for k, c in (("vecadd", "forge"), ("vecmul", "forge"), ("vsum", "forge"), ("dot", "forge3"), ("dot", "forge5")):
            for w in (1, 4, 32):
                f, h = get(tech, k, c, w), get(tech, k, "opt", w)
                da, ds = h["area"] - f["area"], h["seq"] - f["seq"]
                de = h["e_run"] - f["e_run"]
                dfl = (h["e_flop"] * h["cycles"] - f["e_flop"] * f["cycles"]) / 1000
                gap_rows.append([tech, k, label(c), w, g(da, 0), g(ds, 0), f"{pct(ds, da):.0f}" if abs(da) > 1 else "",
                                 g(de, 3), g(dfl, 3), f"{pct(dfl, de):.0f}" if abs(de) > 1e-3 else ""])
    md.append("**HLS opt minus forge**: the total area gap and the sequential area gap; the e_run gap and the flop energy gap (e_flop = e_clk + e_reg + e_seq, X11, times the cycles). A share above 100 % means the rest of the design is smaller on HLS's side.")
    md.append("")
    md += table(["tech", "kernel", "forge", "W", "Δ area µm²", "Δ seq µm²", "seq share of Δ %", "Δ e_run nJ", "Δ e_flop·C nJ", "flop share of Δ %"], gap_rows)
    md.append("")
    md += ["### Observations", ""]
    d3 = [get("nangate45", "dot", "forge3", w)["flops"] for w in WS]
    ho = [get("nangate45", "dot", "opt", w)["flops"] for w in WS]
    md.append(f"- Forge dot 3 has {d3[0]} flops at every W ({pt('dot', 'forge3', 1)} to {pt('dot', 'forge3', 32)}); HLS dot opt goes from {ho[0]:,} to {ho[-1]:,} ({pt('dot', 'opt', 1)} to {pt('dot', 'opt', 32)}). Forge vecadd and vecmul keep {get('nangate45', 'vecadd', 'forge', 1)['flops']} at every W, all in csr and ctrl.")
    md.append(f"- Forge's datapath area is close to linear in W: R² ≥ {min(r2_ for r2_ in afit_r2['dp']):.5f} over every design and technology, slope {min(float(r[3].replace(',', '')) for r in afit if 'datapath' in r[2] and r[0] == 'nangate45'):,.0f} to {max(float(r[3].replace(',', '')) for r in afit if 'datapath' in r[2] and r[0] == 'nangate45'):,.0f} µm² per lane on nangate45; HLS opt's total too (R² ≥ {min(afit_r2['opt']):.4f}).")
    va1, vo1 = get("nangate45", "vecadd", "forge", 1), get("nangate45", "vecadd", "opt", 1)
    md.append(f"- At W = 1 forge is larger than HLS opt on vecadd ({g(va1['area'], 0)} against {g(vo1['area'], 0)} µm², nangate45), where csr + ctrl ({g(va1['csr'] + va1['ctrl'], 0)} µm²) is larger than the adder; at W = 32 it is smaller ({g(get('nangate45', 'vecadd', 'forge', 32)['area'], 0)} against {g(get('nangate45', 'vecadd', 'opt', 32)['area'], 0)} µm²).")
    md += ["", "### Explanations", ""]
    lane_bits = {}
    for k in KERNELS:
        s_, i_, _, _ = fit(WS, [hregs[(k, "opt", w)]["data pipeline (operands, products)"] for w in WS])
        lane_bits[k] = (s_, sorted(hnames[(k, "opt", 1)]["data pipeline (operands, products)"]))
    dp0 = [k for k in ("vecadd", "vecmul") if all(next(x for x in chk if x[:3] == (k, "forge", w))[5] == 0 for w in WS)]
    md.append("- **The boundary differs.** Forge's ElementwiseLanes has no registers (the datapath flops of " + " and ".join(dp0) + " are 0 at every W: forge's operand registers sit in snax_cluster's streamers, which SYN1 does not synthesize), while HLS opt registers data per lane inside its block: " + "; ".join(f"{k} {lane_bits[k][0]:.0f} bits per lane (`{'`, `'.join(lane_bits[k][1])}` at W = 1)" for k in KERNELS) + ". So the per-lane sequential area is in HLS's number and outside forge's. Sure for the inventory (RTL names, DC counts); how large the streamers' registers are is not in SYN1's data.")
    md.append("- **Forge's fixed flops** are csr (129: three 32-bit CSRs, the kept answer and its flag) and ctrl (the 32-bit counters per unit plus a few flags), plus one 64-bit accumulator per sum and 64 W per MAC or link buffer. **HLS's fixed flops** are the pins (`loop_count`, `len`, 32 bits and a valid each), the loop's state (the accumulator and two 32-bit counters for dot and vsum) and the FSM.")
    md.append("- **The sequential area explains most of HLS opt's extra area at large W** (seq share of the gap above); at W = 1 forge's csr + ctrl outweighs it. Fairly sure: the shares are computed from DC's area split; the multiplexers that hold HLS's registers (DFF plus MUX2 for the enable) count as combinational area, so the register cost is somewhat larger than the sequential share alone.")
    md += ["", "### Questions", ""]
    md.append("- The like-for-like boundary: forge's accelerator plus its share of the streamers against HLS's block. snax_cluster's streamer area per port at each W would put the two on one boundary; a synthesis of the streamers alone (or of the cluster with and without the accelerator) would give it.")
    md.append("")
    Q.append("Boundary: forge's datapath registers sit in the streamers, HLS's in the block. What do the streamers cost per port and W? Needs a synthesis of snax_cluster's streamers (section 3).")

    fig, axs = plt.subplots(2, 4, figsize=(16, 7))
    for j, tech in enumerate(TECHS):
        for i, k in enumerate(KERNELS):
            ax = axs[j][i]
            for c in cases(k):
                s = series(tech, k, c, "area")
                if len(s) < 2:
                    continue
                col, mk, ls = STYLE[c]
                ax.plot([x for x, _ in s], [y for _, y in s], marker=mk, color=col, ls=ls, label=label(c))
            ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks(WS, [str(w) for w in WS])
            ax.set_title(f"{k}, {tech}"); ax.grid(True, which="both", alpha=0.3)
            if i == 0:
                ax.set_ylabel("area µm²")
            if j == 1:
                ax.set_xlabel("W")
            ax.legend(fontsize=6)
    fig.tight_layout()
    savefig(fig, "fig3_area.png")

    # ------------------------------------------------ 4. energy
    md += ["## 4. Energy", ""]
    md.append("Energy per element (e_run / 2048, pJ) per kernel and W; the combinational share of e_dyn; forge's datapath share of e_run. Figure `fig4_energy.png`: pJ per element against W.")
    md.append("")
    trend = {}
    for tech in TECHS:
        for k in KERNELS:
            cs = [c for c in cases(k) if sum(1 for w in WS if get(tech, k, c, w)) > 1]
            rows = []
            for w in WS:
                r = [w]
                for c in cs:
                    d = get(tech, k, c, w)
                    r.append(f"{d['pj_elem']:.3f} ({pct(d['e_comb'], d['e_dyn']):.0f} %)" if d else "")
                for c in FORGE_CASES[k]:
                    d = get(tech, k, c, w)
                    r.append(f"{pct(d['e_dp'] * d['cycles'] / 1000, d['e_run']):.0f}")
                rows.append(r)
            for c in cs:
                s = series(tech, k, c, "pj_elem")
                trend[(tech, k, c)] = s[-1][1] / s[0][1]
            md.append(f"**{k}, {tech}**: pJ per element (comb share of e_dyn), then forge's datapath share of e_run %")
            md.append("")
            md += table(["W"] + [label(c) for c in cs] + [f"{label(c)} dp %" for c in FORGE_CASES[k]], rows)
            md.append("")
    md += ["### Observations", ""]
    for tech in TECHS:
        md.append(f"- {tech}, pJ per element at W = 32 over W = 1: " + "; ".join(
            f"{k}: " + ", ".join(f"{label(c)} {trend[(tech, k, c)]:.2f}" for c in cases(k) if (tech, k, c) in trend)
            for k in KERNELS) + ".")
    def cls_(r):
        return "falls" if r < 0.95 else "rises" if r > 1.05 else "stays within 5 %"
    for tech in TECHS:
        grp = defaultdict(list)
        for (t_, k, c), r in sorted(trend.items()):
            if t_ == tech:
                grp[cls_(r)].append(full(k, c))
        md.append(f"- {tech}, from W = 1 to 32: " + "; ".join(f"{cl}: {', '.join(v)}" for cl, v in sorted(grp.items())) + ".")
    md += ["", "### Explanations", ""]
    def share1(m):
        a, b = m[0], m[1]
        return a * N / (a * N + b)
    md.append("- **One shape on both sides.** With e_run = α C + β (section 2) and C ≈ N / W, pJ per element = α / W + β / N: it falls with W as far as the per-cycle part α N is of e_run at W = 1. That part, from the fits, on nangate45: forge " + ", ".join(f"{dn(k, c)} {100 * share1(model[('nangate45', k, c)]):.0f} %" for k, c in designs) + "; HLS " + ", ".join(f"{k} {c} {100 * share1(hmodel[('nangate45', k, c)]):.0f} %" for (t_, k, c) in sorted(hmodel) if t_ == "nangate45") + ". The larger it is, the more the series falls (compare the W = 32 / W = 1 ratios above). Fairly sure: the fits hold within the errors in section 2 (HLS vsum opt is the loosest).")
    md.append(f"- **Forge's per-cycle part is larger** because csr + ctrl's 32-bit registers are clocked every cycle; HLS's fixed state is smaller (its pins, two counters, the FSM) and its per-lane registers cost per task ({min(v[0] for v in lane_bits.values()):.0f} to {max(v[0] for v in lane_bits.values()):.0f} bits per lane, each written once per beat: section 3), like forge's MAC lanes. vecmul's HLS opt barely falls because its multipliers' work dominates e_run; vsum's falls most because a 64-bit adder per lane is small next to the fixed state.")
    md.append("- **HLS unopt rises** because its window stays at a few cycles per element whatever W (it does the lanes one after another, section 1) while its registers grow with W: flops x cycles per task on nangate45 go " + ", ".join(f"{k} {get('nangate45', k, 'unopt', 2)['flops'] * get('nangate45', k, 'unopt', 2)['cycles'] / 1e6:.1f}M (W = 2, {get('nangate45', k, 'unopt', 2)['cycles'] / N:.2f} cycles per element) to {get('nangate45', k, 'unopt', 32)['flops'] * get('nangate45', k, 'unopt', 32)['cycles'] / 1e6:.1f}M (W = 32, {get('nangate45', k, 'unopt', 32)['cycles'] / N:.2f})" for k in KERNELS) + ". Fairly sure: the flops and cycles are measured; that the clocked registers dominate the rise is inferred from the comb share falling with W (the tables above).")
    md += ["", "### Questions", ""]
    md.append("- The energy here is the accelerator's alone. The streamers' energy per beat (forge) and the AXI-stream interface's (HLS) are outside both; a cluster-level power run would show whether they change the picture at small W, where forge's beats are many.")
    md.append("")
    Q.append("Energy: what do the streamers add per beat? A cluster-level power run (snax_cluster) would tell whether forge's lead at large W or its cost at W = 1 changes (section 4).")

    for tech in TECHS:
        fig, axs = plt.subplots(1, 4, figsize=(16, 3.8))
        for ax, k in zip(axs, KERNELS):
            for c in cases(k):
                s = series(tech, k, c, "pj_elem")
                if len(s) < 2:
                    continue
                col, mk, ls = STYLE[c]
                ax.plot([x for x, _ in s], [y for _, y in s], marker=mk, color=col, ls=ls, label=label(c))
            ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks(WS, [str(w) for w in WS])
            ax.set_title(f"{k}, {tech}"); ax.set_xlabel("W"); ax.grid(True, which="both", alpha=0.3)
            ax.legend(fontsize=6)
        axs[0].set_ylabel("pJ per element")
        fig.tight_layout()
        savefig(fig, f"fig4_energy_{tech}.png")

    # ------------------------------------------------ 5. dot's variants
    md += ["## 5. dot's variants", ""]
    md.append("dot 2 to 6 (" + "; ".join(f"{label(c)}: {DOT_BLOCKS[c]}" for c in DOT_FORGE) + ") against HLS dot unopt and opt (dace is parked: RAM). A x C in mm²·cycles (area x cycles: lower is better), E x C in nJ·cycles. Figure `fig5_dot_variants.png`.")
    md.append("")
    rank = {}
    for tech in TECHS:
        rows = []
        for w in WS:
            pts_ = [c for c in DOT_HLS + DOT_FORGE if get(tech, "dot", c, w)]
            vals = {c: get(tech, "dot", c, w) for c in pts_}
            for metric, fn in (("cycles", lambda d: d["cycles"]), ("area", lambda d: d["area"]),
                               ("e_run", lambda d: d["e_run"]), ("AxC", lambda d: d["area"] * d["cycles"]),
                               ("ExC", lambda d: d["e_run"] * d["cycles"])):
                rank[(tech, w, metric)] = sorted(pts_, key=lambda c: (fn(vals[c]), c))
            for c in pts_:
                d = vals[c]
                rows.append([w, label(c), d["cycles"], g(d["area"], 0), g(d["e_run"], 3), g(d["area"] * d["cycles"] / 1e6, 3),
                             g(d["e_run"] * d["cycles"], 0), *(rank[(tech, w, m)].index(c) + 1 for m in ("area", "e_run", "AxC", "ExC"))])
        md.append(f"**{tech}** (rank 1 = lowest, among the seven at that W)")
        md.append("")
        md += table(["W", "case", "cycles", "area µm²", "e_run nJ", "A x C mm²·cyc", "E x C nJ·cyc", "rank area", "rank e_run", "rank AxC", "rank ExC"], rows)
        md.append("")
    beat = defaultdict(list)
    for tech in TECHS:
        for w in WS:
            for m in ("cycles", "area", "e_run", "AxC", "ExC"):
                r = rank[(tech, w, m)]
                best_hls = min(r.index(c) for c in DOT_HLS)
                for c in DOT_FORGE:
                    if r.index(c) < best_hls:
                        fn = {"cycles": "cycles", "area": "area", "e_run": "e_run"}.get(m)
                        beat[(tech, m, c)].append(w)
    md += ["### Observations", ""]
    for tech in TECHS:
        for m in ("area", "e_run", "AxC", "ExC", "cycles"):
            winners = ", ".join(f"W {w}: {label(rank[(tech, w, m)][0])}" for w in WS)
            md.append(f"- {tech}, lowest {m}: {winners}.")
    for tech in TECHS:
        every = {m: [c for c in DOT_FORGE if len(beat[(tech, m, c)]) == len(WS)] for m in ("area", "e_run", "AxC", "ExC", "cycles")}
        md.append(f"- {tech}: variants below both HLS cases at every W: " + "; ".join(f"{m}: {', '.join(label(c) for c in v) or 'none'}" for m, v in every.items()) + ".")
    # dot4 vs dot5/6; W=1 equality; dot2 vs dot3
    for tech in TECHS:
        d4, d5, d6 = (get(tech, "dot", c, 1) for c in ("forge4", "forge5", "forge6"))
        md.append(f"- {tech}, W = 1: dot 5 against dot 4 area {pct(d5['area'] - d4['area'], d4['area']):+.2f} %, e_run {pct(d5['e_run'] - d4['e_run'], d4['e_run']):+.2f} %, cycles {d5['cycles']} against {d4['cycles']}; dot 6 against dot 4 area {pct(d6['area'] - d4['area'], d4['area']):+.2f} %, e_run {pct(d6['e_run'] - d4['e_run'], d4['e_run']):+.2f} % ({pt('dot', 'forge4', 1)}, {pt('dot', 'forge5', 1)}, {pt('dot', 'forge6', 1)}).")
        buf = []
        for w in WS:
            a2, a3 = get(tech, "dot", "forge2", w), get(tech, "dot", "forge3", w)
            bufa = sum(float(r["area_um2"]) for p_, r in a2["mods"].items() if p_.count("/") == 1 and p_.startswith("dp/bufs"))
            buf.append(f"W {w}: {g(a2['area'] - a3['area'], 0)} µm² ({g(bufa, 0)} in the buffer), {pct(a2['e_run'] - a3['e_run'], a3['e_run']):+.1f} % e_run")
        md.append(f"- {tech}, dot 2 minus dot 3 (the link buffer): " + "; ".join(buf) + ".")
    # crossover dot5 vs dot4
    cross = {}
    for tech in TECHS:
        for m, fn in (("area", lambda d: d["area"]), ("e_run", lambda d: d["e_run"]), ("AxC", lambda d: d["area"] * d["cycles"]),
                      ("ExC", lambda d: d["e_run"] * d["cycles"])):
            diff = [(w, fn(get(tech, "dot", "forge5", w)) - fn(get(tech, "dot", "forge4", w))) for w in WS]
            cross[(tech, m)] = diff
        md.append(f"- {tech}, dot 5 minus dot 4 per W: " + "; ".join(
            f"{m} " + " / ".join(f"{'+' if v > 0 else '−'}" for _, v in cross[(tech, m)]) for m in ("area", "e_run", "AxC", "ExC")) + " (signs at W = 1 … 32).")
    md += ["", "### Explanations", ""]
    b6 = {tech: sum(float(r["area_um2"]) for p_, r in get(tech, "dot", "forge6", 1)["mods"].items() if p_.count("/") == 1 and p_.startswith("dp/bufs")) for tech in TECHS}
    md.append("- **dot 5 at W = 1 does dot 4's work**: at one lane a serial sum and a tree both add one value per beat (snax-forge's design note `design.serial_one_lane`), and the two agree within the percentages above on both technologies. dot 6 is larger by its link buffer (" + ", ".join(f"{g(b6[t_], 0)} µm² on {t_}" for t_ in TECHS) + "), which at J = 1 saves no cycle. Sure: C§17's forms give the same cycles, the blocks are the same at lanes 1, and the buffer's area is its module row.")
    for tech in TECHS:
        sg = {m: [v > 0 for _, v in cross[(tech, m)]] for m in ("area", "e_run", "AxC", "ExC")}
        small = [w for w, big in zip(WS, sg["area"]) if not big]
        if small:
            worse = {m: [w for w in small if sg[m][WS.index(w)]] for m in ("e_run", "AxC", "ExC")}
            md.append(f"- **{tech}: dot 5 (serial sum) is smaller than dot 4 (tree) at W = {', '.join(map(str, small))}.** At those W its W-cycle tail costs more than the tree's area saves on A x C at W = {', '.join(map(str, worse['AxC'])) or 'none'}, on E x C at W = {', '.join(map(str, worse['ExC'])) or 'none'}, on e_run at W = {', '.join(map(str, worse['e_run'])) or 'none'}. Fairly sure for the mechanism (C5's W cycles against a tree of W − 1 adders, the module areas); where the two are within a fraction of a percent (W = 1, 2) the sign is noise of synthesis (PITFALLS DC3).")
    md.append("- **dot 2's buffer** adds W x 64 flops (a LinkBuffer of depth 1) and their per-cycle energy, with no cycle saved at J = 1 (C2 = T + 2 against C3 = T + 1). Sure: the module area and the cycle form.")
    md += ["", "### Questions", ""]
    md.append("- The variants were measured at one job (J = 1). C§17's forms differ at J > 1 (dot 5: J(T + W − 1) + 2; dot 6 overlaps jobs): a run with several jobs (a matvec, row 16 x 512) would show whether dot 6's buffer pays off where dot 5's tail repeats per job.")
    md.append("")
    Q.append("dot: at J > 1 dot 5's tail repeats per job and dot 6 overlaps it (C§17). Does dot 6's buffer pay off for matvec-like work? Needs SYN1-style runs of a J > 1 task (section 5).")

    fig, axs = plt.subplots(2, 2, figsize=(11, 7))
    for j, tech in enumerate(TECHS):
        for i, (m, fn, unit_) in enumerate((("A x C", lambda d: d["area"] * d["cycles"] / 1e6, "mm²·cycles"),
                                            ("E x C", lambda d: d["e_run"] * d["cycles"], "nJ·cycles"))):
            ax = axs[i][j]
            for c in DOT_HLS + DOT_FORGE:
                s = [(w, fn(get(tech, "dot", c, w))) for w in WS if get(tech, "dot", c, w)]
                col, mk, ls = STYLE[c]
                ax.plot([x for x, _ in s], [y for _, y in s], marker=mk, color=col, ls=ls, label=label(c))
            ax.set_xscale("log", base=2); ax.set_yscale("log"); ax.set_xticks(WS, [str(w) for w in WS])
            ax.set_title(f"dot, {tech}: {m}"); ax.set_ylabel(unit_); ax.grid(True, which="both", alpha=0.3)
            if i == 1:
                ax.set_xlabel("W")
    axs[0][0].legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "fig5_dot_variants.png")

    # ------------------------------------------------ 6. technologies
    md += ["## 6. Technologies", ""]
    md.append("nangate45 over nangate15 per point, for area and e_run. Figure `fig6_tech_ratio.png`: the ratios against the sequential share of the nangate45 area.")
    md.append("")
    ratios = []
    for (t, k, c, w), d in sorted(D.items()):
        if t != "nangate45":
            continue
        e = get("nangate15", k, c, w)
        if e:
            ratios.append((k, c, w, d["side"], d["area"] / e["area"], d["e_run"] / e["e_run"], d["seq"] / d["area"]))
    rrows = []
    for side in ("hls", "forge"):
        ra = [x[4] for x in ratios if x[3] == side]
        re_ = [x[5] for x in ratios if x[3] == side]
        rrows.append([side, len(ra), f"{np.mean(ra):.2f}", f"{min(ra):.2f}–{max(ra):.2f}", f"{np.mean(re_):.2f}", f"{min(re_):.2f}–{max(re_):.2f}"])
    md += table(["side", "points", "area ratio mean", "area ratio range", "e_run ratio mean", "e_run ratio range"], rrows)
    md.append("")
    sa_, ia_, ra2, _ = fit([x[6] for x in ratios], [x[4] for x in ratios])
    lo = sorted(ratios, key=lambda x: x[4])[:3]
    hi = sorted(ratios, key=lambda x: -x[4])[:3]
    same_rank = sum(1 for w in WS for m in ("area", "e_run", "AxC", "ExC") if rank[("nangate45", w, m)][0] == rank[("nangate15", w, m)][0])
    md += ["### Observations", ""]
    md.append(f"- The area ratio follows the sequential share: ratio = {sa_:.2f} x seq share + {ia_:.2f} (R² {ra2:.2f}, {len(ratios)} points). Lowest: {', '.join(f'{pt(k, c, w)} {r:.2f}' for k, c, w, _, r, _, _ in lo)}; highest: {', '.join(f'{pt(k, c, w)} {r:.2f}' for k, c, w, _, r, _, _ in hi)}.")
    md.append(f"- dot's lowest-metric variant is the same on both technologies in {same_rank} of {len(WS) * 4} (W, metric) cells of section 5.")
    md += ["", "### Explanations", ""]
    fu45 = np.mean([d["seq"] / d["flops"] for (t_, *_), d in D.items() if t_ == "nangate45" and d["side"] == "forge"])
    hu45 = np.mean([d["seq"] / d["flops"] for (t_, *_), d in D.items() if t_ == "nangate45" and d["side"] == "hls"])
    md.append(f"- **The flops shrink more than the logic, and forge's most.** On nangate45 HLS's flops average {hu45:.3f} µm² (the plain DFF, synchronous reset in logic) and forge's {fu45:.3f} µm² (with an asynchronous reset); on nangate15 both are {u15:g} µm², since every flop there has an asynchronous reset or set (PITFALLS LIB1). So a flop shrinks {hu45 / u15:.2f}x (HLS) or {fu45 / u15:.2f}x (forge) against about {ia_:.2f}x for the logic (the fit's intercept at no flops). Forge's flop-heavy points (small W, csr + ctrl) have the highest ratios. Fairly sure: the flop areas are DC's sequential area over its flop count, the logic's ratio is the fit's.")
    md.append(f"- **Consequence:** relative to HLS, forge pays about {100 * (fu45 / hu45 - 1):.0f} % more per flop on nangate45 and the same on nangate15, so forge's control overhead is relatively smaller on nangate15 (section 2's thresholds).")
    md += ["", "### Questions", ""]
    md.append("- Does a conclusion of section 5 or 8 depend on the library? Where the winners differ between the technologies (count above) it is at W = 1, where forge's flops weigh most; a library with a plain flop on both nodes (or nangate45 with only reset flops) would tell whether it is the flop cell.")
    md.append("")

    fig, axs = plt.subplots(1, 2, figsize=(11, 4))
    for side, col in (("hls", "tab:blue"), ("forge", "tab:green")):
        xs = [x for x in ratios if x[3] == side]
        axs[0].plot([x[6] for x in xs], [x[4] for x in xs], "o", color=col, ms=4, label=side)
        axs[1].plot([x[6] for x in xs], [x[5] for x in xs], "o", color=col, ms=4, label=side)
    xx = np.array([0, max(x[6] for x in ratios)])
    axs[0].plot(xx, sa_ * xx + ia_, "k", lw=0.8)
    axs[0].set_title("area nangate45 / nangate15"); axs[1].set_title("e_run nangate45 / nangate15")
    for ax in axs:
        ax.set_xlabel("sequential share of nangate45 area"); ax.grid(True, alpha=0.3); ax.legend(fontsize=7)
    fig.tight_layout()
    savefig(fig, "fig6_tech_ratio.png")

    # ------------------------------------------------ 7. odd points
    md += ["## 7. Odd points", ""]
    odd = []
    for tech in TECHS:
        for k in KERNELS:
            for c in cases(k):
                s = series(tech, k, c, "pj_elem")
                if len(s) < 3:
                    continue
                vals = [v for _, v in s]
                falling = vals[-1] < vals[0]
                for (w0, a), (w1, b) in zip(s, s[1:]):
                    if (falling and b > a * 1.005) or (not falling and b < a * 0.995):
                        odd.append([tech, full(k, c), f"W {w0} → {w1}", f"{a:.3f} → {b:.3f}"])
    md.append("Steps in W against the series' own direction (pJ per element, more than 0.5 %):")
    md.append("")
    md += table(["tech", "series", "step", "pJ per element"], odd)
    md.append("")
    fm = {(tech, side): [d["fmax"] for (t, *_), d in D.items() if t == tech and d["side"] == side] for tech in TECHS for side in ("hls", "forge")}
    md.append("- fmax (observation only: DC's lower bound at 10 ns, X2, not analysed in SYN1): " + "; ".join(
        f"{tech} {side} {min(v):.0f}–{max(v):.0f} MHz" for (tech, side), v in fm.items()) + ".")
    v1 = get("nangate45", "vecadd", "unopt", 1)
    low1 = min((c for c in cases("vecadd") if get("nangate45", "vecadd", c, 1)), key=lambda c: get("nangate45", "vecadd", c, 1)["pj_elem"])
    md.append(f"- HLS vecadd unopt at W = 1 ({pt('vecadd', 'unopt', 1)}) has {v1['flops']} flops and {v1['pj_elem']:.3f} pJ per element; the lowest pJ per element of the vecadd points at W = 1 on nangate45 is {label(low1)}'s. unopt at W = 1 registers no data (section 3's inventory: pins and loop state only) and is pipelined at one beat per cycle (a = {unopt_a[('vecadd', 1)]:.0f}).")
    md += ["", "### Explanations", ""]
    md.append("- dot 5 and dot 6 from W = 16 to 32: the serial tail of W cycles (section 1, 5). Sure.")
    md.append("- HLS unopt's dip from W = 2 to 4 (vsum, dot): its cycles per element, a / W, fall there (" + ", ".join(f"{k} {unopt_a[(k, 2)] / 2:.2f} to {unopt_a[(k, 4)] / 4:.2f}" for k in ("vsum", "dot")) + ") faster than its registers grow; from W = 4 on the registers win (section 4). Its jump from W = 1 to 2 is a / W jumping (" + ", ".join(f"{k} {unopt_a[(k, 1)]:.2f} to {unopt_a[(k, 2)] / 2:.2f}" for k in KERNELS) + "). Sure: a is cosim's line.")
    md.append("")

    # ------------------------------------------------ 8. metrics
    md += ["## 8. Metrics", ""]
    md.append("Candidate metrics side by side, per kernel and W: the lowest-energy-per-element, lowest A x C, lowest E x C and highest throughput per area (elements per cycle per mm², N / C / A) case, with forge's value next to the best HLS case's. Nothing is picked here.")
    md.append("")
    mets = (("pJ/elem", lambda d: d["pj_elem"], min), ("A x C", lambda d: d["area"] * d["cycles"], min),
            ("E x C", lambda d: d["e_run"] * d["cycles"], min), ("elem/cyc/mm²", lambda d: N / d["cycles"] / (d["area"] / 1e6), max))
    disagree = []
    for tech in TECHS:
        rows = []
        for k in KERNELS:
            for w in WS:
                cs = [c for c in cases(k) if get(tech, k, c, w)]
                r = [k, w]
                wins = []
                for name, fn, best in mets:
                    bc = best(cs, key=lambda c: fn(get(tech, k, c, w)))
                    hc = best([c for c in cs if c in HLS_CASES], key=lambda c: fn(get(tech, k, c, w)))
                    fc = best([c for c in cs if c not in HLS_CASES], key=lambda c: fn(get(tech, k, c, w)))
                    fv, hv = fn(get(tech, k, fc, w)), fn(get(tech, k, hc, w))
                    r.append(f"{label(bc)} ({label(fc)} {fv / hv:.2f}x {label(hc)})")
                    wins.append("forge" if bc not in HLS_CASES else "hls")
                if len(set(wins)) > 1:
                    disagree.append((tech, k, w, wins))
                rows.append(r)
        md.append(f"**{tech}**: the best case per metric, and (best forge / best HLS) as a ratio of their values")
        md.append("")
        md += table(["kernel", "W"] + [m[0] for m in mets], rows)
        md.append("")
    md += ["### Observations", ""]
    md.append(f"- The metrics disagree on which side is best in {len(disagree)} of {2 * len(KERNELS) * len(WS)} (tech, kernel, W) cells: " + "; ".join(
        f"{t} {k} W {w} ({'/'.join(x[0] for x in wn)})" for t, k, w, wn in disagree[:12]) + ("; …" if len(disagree) > 12 else "") + " (order: pJ/elem, A x C, E x C, throughput per area; h = HLS, f = forge).")
    md.append("- The disagreements by W: " + ", ".join(f"W = {w}: {n}" for w, n in sorted(Counter(w for _, _, w, _ in disagree).items())) + ". A x C and throughput per area always agree (one is the other's inverse times N).")
    md += ["", "### What each rewards", ""]
    md.append("- **Energy per element** rewards whatever spends least per result: it ignores area and time, so a slow, small design (HLS unopt at W = 1) can win it.")
    md.append("- **A x C** (area x cycles, the inverse of throughput per area) rewards finishing the task fast for the silicon spent: it favours wide designs whose area grows slower than their cycles fall, and penalizes a fixed overhead (csr + ctrl) at small W and a cycle tail (dot 5, 6) at large W.")
    md.append("- **E x C** (energy-delay) rewards energy and speed together; between two designs of similar energy it follows the cycles, so it separates designs by their overhead cycles (dot 5, 6's tail, HLS unopt).")
    md.append("- **Throughput per area** is A x C's inverse up to N: it ranks the same, and reads as a rate (elements per cycle per mm²).")
    md.append("")
    M.append("Energy per element against W, one panel per kernel, both sides (fig4): the simplest picture; it rewards small slow designs and hides area.")
    M.append("A x C (or throughput per area) against W for dot's variants and HLS (fig5): the area-time trade-off; it rewards width and punishes fixed overhead at W = 1 and dot 5's tail at W = 32.")
    M.append("csr + ctrl share of area and e_run against W (fig2): answers the overhead question directly; it depends on what the boundary excludes (the streamers).")
    M.append("The two-term fit e_run = α C + β per design (fig7): the HWCOST shape; it needs the per-cycle term to include the datapath's clocked registers.")

    # ------------------------------------------------ summary and lists
    best_dot = {}
    for tech in TECHS:
        for m in ("area", "e_run", "AxC", "ExC"):
            best_dot[(tech, m)] = [c for c in DOT_FORGE if len(beat[(tech, m, c)]) == len(WS)]
    def sh(tech, k, c, w):
        d = get(tech, k, c, w)
        return pct((d["e_csr"] + d["e_ctrl"]) * d["cycles"] / 1000, d["e_run"])
    cc = [get("nangate45", k, c, w)["csr"] + get("nangate45", k, c, w)["ctrl"] for k, c in designs for w in WS]
    bits = [(b, 1) for k, c in designs for _, b in forge_registers(f"done/{k}/{c}_w4", r"^snax_forge_(csr|(?!ctrl$)\w+_ctrl)$")]
    b32 = sum(b for b, _ in bits if b == 32) / sum(b for b, _ in bits)
    S.append(f"- **Control overhead.** Forge's csr + ctrl is a fixed block ({g(min(cc), 0)}–{g(max(cc), 0)} µm² on nangate45; {100 * b32:.0f} % of its flops are 32-bit counters and CSRs) with a near-constant energy per cycle, so its share of e_run halves with each doubling of W. On nangate45 at W = 1 it is " + ", ".join(f"{dn(k, c)} {sh('nangate45', k, c, 1):.0f} %" for k, c in designs) + " of e_run; at W = 32 " + ", ".join(f"{sh('nangate45', k, c, 32):.1f} %" for k, c in designs) + " (section 2, rows `done/*/forge*_w1`, `_w32`).")
    S.append("- **Against HLS's own fixed cost.** HLS opt's per-cycle term α is " + ", ".join(f"{k} {1000 * hmodel[('nangate45', k, 'opt')][0]:.2f}" for k in KERNELS) + " pJ/cycle against forge's " + ", ".join(f"{dn(k, FORGE_CASES[k][0] if k != 'dot' else 'forge3')} {1000 * model[('nangate45', k, FORGE_CASES[k][0] if k != 'dot' else 'forge3')][0]:.2f}" for k in KERNELS) + " on nangate45 (fits over W, section 2): forge's overhead is the larger per cycle, and it matters where the datapath is small (one adder: vecadd, vsum) and W is small.")
    fo = sorted({D[x]["cycles"] - N // x[3] for x in D if x[0] == "nangate45" and D[x]["side"] == "forge" and x[2] not in ("forge5", "forge6")})
    ho = sorted({D[x]["cycles"] - N // x[3] for x in D if x[0] == "nangate45" and x[2] in ("opt", "dace")})
    S.append(f"- **Latency.** Forge's window is N / W + {fo[0]} to {fo[-1]} cycles and HLS opt's and dace's N / W + {ho[0]} to {ho[-1]}, except dot 5 and 6 (N / W + W + 1, + 2: {get('nangate45', 'dot', 'forge5', 32)['cycles']} and {get('nangate45', 'dot', 'forge6', 32)['cycles']} cycles at W = 32) and HLS unopt ({min(get('nangate45', k, 'unopt', w)['cycles'] / N for k in KERNELS for w in WS[1:]):.2f} to {max(get('nangate45', k, 'unopt', w)['cycles'] / N for k in KERNELS for w in WS[1:]):.2f} cycles per element at W ≥ 2) (section 1).")
    S.append("- **Boundary.** HLS opt registers data per lane inside its block (" + ", ".join(f"{k} {lane_bits[k][0]:.0f}" for k in KERNELS) + f" bits per lane; dot opt {get('nangate45', 'dot', 'opt', 1)['flops']} to {get('nangate45', 'dot', 'opt', 32)['flops']:,} flops), forge's ElementwiseLanes none (dot 3: {get('nangate45', 'dot', 'forge3', 1)['flops']} flops at every W); forge's operand registers sit in the streamers, outside SYN1. Every area and energy comparison inherits this (section 3).")
    S.append("- **dot variants below both HLS dot cases at every W** (unopt, opt): " + "; ".join(f"{tech}: " + ", ".join(f"{m} {', '.join(label(c) for c in best_dot[(tech, m)]) or 'none'}" for m in ("area", "e_run", "AxC", "ExC")) for tech in TECHS) + ". Lowest area per W: " + "; ".join(f"{tech} " + ", ".join(sorted({label(rank[(tech, w, 'area')][0]) for w in WS})) for tech in TECHS) + "; HLS has the lowest A x C at W = " + "; ".join(f"{tech} " + ", ".join(str(w) for w in WS if rank[(tech, w, 'AxC')][0] in DOT_HLS) for tech in TECHS) + " (section 5).")
    S.append(f"- **Metrics disagree** on the winning side in {len(disagree)} of {2 * len(KERNELS) * len(WS)} (tech, kernel, W) cells, all at W = " + " and ".join(str(w) for w in sorted({w for _, _, w, _ in disagree})) + "; the patterns (pJ/elem, A x C, E x C, throughput per area; f forge, h HLS): " + ", ".join(f"{'/'.join(x[0] for x in pat)} {n}x" for pat, n in sorted(Counter(tuple(wn) for *_, wn in disagree).items())) + " (section 8).")
    S.append(f"- **HWCOST's shape** e_run = α C + β fits {len(good_fit)} of {2 * len(designs)} forge design-technology pairs within 2 % over W (worst {dn(worst_fit[0][1], worst_fit[0][2])} on {worst_fit[0][0]}, {100 * worst_fit[1]:.1f} %); α is csr + ctrl plus every datapath block that works once per beat (section 2).")
    S.append("- **Not answerable from SYN1:** the streamers' share (forge's registers), narrower counters, J > 1, the cluster-level cycles (open questions).")

    head = ["# SYN1 analysis: snax-forge beside HLS tier done", ""]
    head.append(f"Written by `report/analysis_syn1.py` (`pixi run analysis`) from the committed CSVs (R4's `results/forge_vs_hls_<tech>.csv`, `results/{{hls,forge}}/<tech>/synth_dc*.csv`, `power_pt*.csv`, `results/hls/hls_cycles.csv`), the committed `reference.rpt` (the flop's area), hls-exercises' Verilog and forge's bundles (the registers by name). Every number is computed; nothing is typed by hand. n2048 only, both technologies, W = 1 to 32: {n_ok[('nangate45', 'hls')]} HLS and {n_ok[('nangate45', 'forge')]} forge points per technology (HLS dot `dace_w1` parked). This note decides nothing: it is for review, before the comparisons are chosen. PT is the reference for energy (X25). Each section gives observations, explanations (with how sure each is and its evidence) and questions.")
    head += ["", "## Summary", ""] + S + [""]
    tail = ["## Open questions", ""] + [f"- {q}" for q in Q] + [
        "- fmax: on nangate45 forge's dot variants report " + f"{min(get('nangate45', 'dot', c, w)['fmax'] for c in DOT_FORGE for w in WS):.0f}–{max(get('nangate45', 'dot', c, w)['fmax'] for c in DOT_FORGE for w in WS):.0f} MHz against HLS dot's {min(get('nangate45', 'dot', c, w)['fmax'] for c in DOT_HLS for w in WS):.0f}–{max(get('nangate45', 'dot', c, w)['fmax'] for c in DOT_HLS for w in WS):.0f} MHz; it is DC's lower bound at 10 ns (X2), so a synthesis at a tighter clock would be needed to compare speed, and SYN1 does not.", ""]
    tail += ["## Candidate metrics or figures for the paper", ""] + [f"- {m}" for m in M] + [""]
    tail += ["## Figures", ""] + [
        "- `fig1_cycles_overhead.png`: cycles − N / W against W, per kernel and case (section 1).",
        "- `fig2_control_share.png`: csr + ctrl as a share of area and e_run against W, per forge design, both technologies (section 2).",
        "- `fig3_area.png`: total area against W, per kernel and case, both technologies (section 3).",
        "- `fig4_energy_nangate45.png`, `fig4_energy_nangate15.png`: pJ per element against W, per kernel and case (section 4).",
        "- `fig5_dot_variants.png`: A x C and E x C against W for dot 2–6 and HLS dot unopt and opt (section 5).",
        "- `fig6_tech_ratio.png`: nangate45 / nangate15 ratios of area and e_run against the sequential share (section 6).",
        "- `fig7_two_term_fit.png`: forge's e_run against the cycles over W, with the fit e_run = α C + β (section 2).", ""]
    (OUT / "syn1_analysis.md").write_text("\n".join(head + md + tail))
    print(f"wrote {(OUT / 'syn1_analysis.md').relative_to(ROOT)} and {len(list(OUT.glob('*.png')))} figures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
