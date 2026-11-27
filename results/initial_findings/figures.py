"""CSYN2's first look: area and energy of the tier A points, ADFG static estimate against SNAX-GVSoC and the netlist.

Reads cluster/points.json, results/cluster/<tech>/{breakdown,energy}.json and ge/<point>.json, and snax-forge's
paper/data/{forms,limits}.csv (through SNAX_FORGE, default ../snax-forge). Writes, beside this file, the five
figures and numbers.csv (README.md says what each shows).

    pixi run python results/initial_findings/figures.py [--tech nangate45]
"""

import argparse
import csv
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FORGE = Path(os.environ.get("SNAX_FORGE", ROOT.parent / "snax-forge")).resolve()

# the figures' parts: datapath and control as one "accelerator"
E_PARTS = {"accelerator": ["datapath", "control"], "streamers": ["streamers"], "crossbar": ["crossbar"],
           "memory": ["memory"], "DMA": ["dma"]}
A_PARTS = {**E_PARTS, "core": ["core"], "rest": ["rest"]}
COL = dict(zip(A_PARTS, ["#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17", "#6a4ce2"]))
LEAK = "#7d7d7d"
WORK = ("run", "dma_copy")  # the windows the accelerators (or a copy) work in
SRC = ("ADFG static", "SNAX-GVSoC", "netlist")
PAIRS = [("mvt W=8", "mvt_contiguous_w8", "mvt_padded_w8", "contiguous", "padded"),
         ("bicg seq. W=8", "bicg_sequential_contiguous_w8", "bicg_sequential_padded_w8", "contiguous", "padded"),
         ("mvt column", "mvt_column", "mvt_column_pipeline", "sequential", "pipeline"),
         ("bicg two pass", "bicg_two_pass", "bicg_two_pass_pipeline", "sequential", "pipeline"),
         ("bicg contig. W=8", "bicg_sequential_contiguous_w8", "bicg_pipeline_contiguous_w8", "sequential", "pipeline"),
         ("gesummv factor out", "gesummv_factor_out", "gesummv_factor_out_pipeline", "sequential", "pipeline")]


def short(s: str) -> str:
    return (s.replace("_contiguous_w8", " contig.").replace("_padded_w8", " padded")
            .replace("bicg_sequential", "bicg seq.").replace("bicg_pipeline", "bicg pipe.").replace("_", " "))


def load(tech: str) -> tuple[list[dict], dict, dict]:
    res = ROOT / "results" / "cluster" / tech
    groups = json.loads((ROOT / "cluster" / "groups.json").read_text())["parts"]
    energy = json.loads((res / "energy.json").read_text())
    brk = json.loads((res / "breakdown.json").read_text())
    paper = {r["id"]: r for s in ("forms", "limits")
             for r in csv.DictReader(open(FORGE / "paper" / "data" / f"{s}.csv"))}
    design = [g for p in ("datapath", "control", "streamers", "crossbar", "memory", "dma") for g in groups[p]]
    points = [p for p in json.loads((ROOT / "cluster" / "points.json").read_text())["points"]
              if p["point"].removesuffix("_cg") in paper and p["point"] in energy
              and (res / "ge" / f"{p['point']}.json").is_file()]
    order = [p["point"] for p in points]
    points.sort(key=lambda p: (order.index(p.get("netlist_of", p["point"])), "netlist_of" in p))
    rows = []
    for p in points:
        pt = p["point"]; pid = pt.removesuffix("_cg"); r = paper[pid]
        ws = energy[pt]["windows"]
        ge = json.loads((res / "ge" / f"{pt}.json").read_text())
        marks = {w["mark"] for w in ws}
        area = {g["name"]: g["area_um2"] for g in brk[p.get("netlist_of", pt)]["groups"]}

        def nl_e(kinds, ws=ws):
            sel = [w for w in ws if kinds is None or w["kind"] in kinds]
            return {k: sum(sum(w["groups"][g] for p_ in ps for g in groups[p_]) * w["cycles"] / 1e3 for w in sel)
                    for k, ps in E_PARTS.items()}

        def gv_e(kinds, ge=ge, marks=marks):
            sel = [w for w in ge["windows"] if w["mark"] in marks and (kinds is None or w["kind"] in kinds)]
            return {k: sum(w["energy"]["parts"].get(p_, 0.0) for p_ in ps for w in sel) for k, ps in E_PARTS.items()}

        rows.append({
            "id": pid, "adopted": "netlist_of" in p,
            "est_e": {k: sum(float(r[f"static_{p_}_nj"]) for p_ in ps) for k, ps in E_PARTS.items()},
            "est_a": {k: sum(float(r[f"area_{p_}_um2"]) for p_ in ps) for k, ps in A_PARTS.items()},
            "nl_a": {k: sum(area[g] for p_ in ps for g in groups[p_]) for k, ps in A_PARTS.items()},
            "gv_run": gv_e(WORK), "nl_run": nl_e(WORK), "gv_all": gv_e(None), "nl_all": nl_e(None),
            "est_leak": float(r["static_leak_nj"]), "gv_leak": float(r["leak_design_nj"]),
            "nl_leak": sum(sum(w["leak_uw"][g] for g in design) * w["cycles"] * w["clock_ns"] / 1e6 for w in ws),
            "est_cycles": int(r["est_cycles"]),
            "gv_cycles": sum(w["cycles"] for w in ge["windows"] if w["mark"] in marks),
            "nl_cycles": sum(w["cycles"] for w in ws),
            "dma_io_nj": sum(sum(w["groups"][g] for g in design) * w["cycles"] / 1e3 for w in ws
                             if w["kind"] in ("dma_in", "dma_out")),
        })
    return rows, paper, {r["id"]: r for r in rows}


def stacked(ax, x, vals, parts, width, label_parts=False):
    bottom = np.zeros(len(x))
    for k in parts:
        v = np.array([d[k] for d in vals])
        ax.bar(x, v, width, bottom=bottom, color=COL[k], edgecolor="white", linewidth=1.0,
               label=k if label_parts else None)
        bottom += v
    return bottom


def ratio_panel(ax, rows, est, gv, title):
    x = np.arange(len(rows))
    ax.axhline(1.0, color="#888", linewidth=1)
    ax.plot(x, est, "o", color="#257de0", markersize=7, label="ADFG static / netlist")
    ax.plot(x, gv, "s", color="#f47230", markersize=7, mfc="none", markeredgewidth=2, label="SNAX-GVSoC / netlist")
    for xi, a, b in zip(x, est, gv):
        ax.text(xi + 0.14, a, f"{a:.2f}", fontsize=7, va="center", color="#257de0")
        if abs(a - b) > 0.02:
            ax.text(xi + 0.14, b, f"{b:.2f}", fontsize=7, va="center", color="#c4561f")
    ax.set_xticks(x, [short(r["id"]) for r in rows], rotation=20, ha="right")
    ax.set_ylabel("total / netlist"); ax.set_ylim(0, max(max(est), max(gv)) * 1.15)
    ax.legend(frameon=False, loc="lower left", ncol=2)
    ax.set_title(title, loc="left", fontsize=10)


def split(rows):
    small = [r for r in rows if sum(r["nl_run"].values()) < 150]
    return [(small, "int8 forms"), ([r for r in rows if r not in small], "int64 forms and DMA copies")]


def energy_fig(rows, key_gv, key_nl, leak, title, fname):
    fig, axes = plt.subplots(3, 1, figsize=(15, 13), gridspec_kw={"height_ratios": [1, 1, 0.75]})
    keys = (("est_e", "est_leak", "ADFG"), (key_gv, "gv_leak", "GVSoC"), (key_nl, "nl_leak", "netlist"))
    tot = lambda r, k, lk: sum(r[k].values()) + (r[lk] if leak else 0.0)  # noqa: E731
    for ax, (grp, sub) in zip(axes[:2], split(rows)):
        x = np.arange(len(grp)); w = 0.27
        for off, (ke, kl, lab) in zip((-w, 0, w), keys):
            top = stacked(ax, x + off, [r[ke] for r in grp], E_PARTS, w * 0.92, label_parts=off == -w)
            if leak:
                lv = np.array([r[kl] for r in grp])
                ax.bar(x + off, lv, w * 0.92, bottom=top, color=LEAK, edgecolor="white", linewidth=1.0, hatch="///",
                       label="leakage (six parts)" if off == -w else None)
                top = top + lv
            for xi, t in zip(x + off, top):
                ax.text(xi, t * 1.01, lab, rotation=90, ha="center", va="bottom", fontsize=6.5, color="#555")
        ax.set_xticks(x, [short(r["id"]) for r in grp], rotation=20, ha="right")
        ax.set_ylabel("energy (nJ)" if leak else "dynamic energy (nJ)")
        ax.set_ylim(0, max(tot(r, k, lk) for r in grp for k, lk, _ in keys) * 1.3)
        ax.set_title(f"{title}: {sub} (bars per design: ADFG static | SNAX-GVSoC | netlist)", loc="left", fontsize=10)
    axes[0].legend(ncol=6, frameon=False, loc="upper left")
    nl = [tot(r, key_nl, "nl_leak") for r in rows]
    ratio_panel(axes[2], rows, [tot(r, "est_e", "est_leak") / n for r, n in zip(rows, nl)],
                [tot(r, key_gv, "gv_leak") / n for r, n in zip(rows, nl)],
                "ratio of the totals to the netlist (1 = equal)")
    fig.tight_layout(); fig.savefig(HERE / fname, dpi=130); plt.close(fig)


def area_fig(rows):
    rows = [r for r in rows if not r["adopted"]]  # an adopted netlist is its twin's
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), gridspec_kw={"height_ratios": [3, 2]})
    ax = axes[0]; x = np.arange(len(rows)); w = 0.38
    for off, key, lab in ((-w / 2, "est_a", "est."), (w / 2, "nl_a", "DC")):
        t = stacked(ax, x + off, [{k: v / 1e6 for k, v in r[key].items()} for r in rows], A_PARTS, w * 0.92,
                    label_parts=off < 0)
        for xi, ti in zip(x + off, t):
            ax.text(xi, ti, lab, ha="center", va="bottom", fontsize=6.5, color="#555")
    ax.set_xticks(x, [short(r["id"]) for r in rows], rotation=20, ha="right"); ax.set_ylabel("area (mm²)")
    ax.set_title("Area of the whole cluster (bars per design: estimate | DC netlist)", loc="left", fontsize=10)
    ax.legend(ncol=7, frameon=False, loc="upper left"); ax.margins(y=0.15)
    ax = axes[1]
    for k in ("accelerator", "streamers", "crossbar"):
        ax.plot(x, [r["est_a"][k] / r["nl_a"][k] for r in rows], "o-", color=COL[k], markersize=6, linewidth=1.5,
                label=k)
    ax.plot(x, [sum(r["est_a"].values()) / sum(r["nl_a"].values()) for r in rows], "s-", color="#333", markersize=6,
            linewidth=2, label="whole cluster")
    ax.axhline(1.0, color="#888", linewidth=1)
    ax.set_xticks(x, [short(r["id"]) for r in rows], rotation=20, ha="right"); ax.set_ylabel("estimate / DC")
    ax.set_title("ratio per part (the banks, DMA and core are within 1 %)", loc="left", fontsize=10)
    ax.legend(frameon=False, ncol=4, loc="lower right")
    fig.tight_layout(); fig.savefig(HERE / "area.png", dpi=130); plt.close(fig)


def trends_fig(by_id, paper):
    def side(pid):
        r = paper[pid]; n = by_id.get(pid)
        return {"ADFG static": (float(r["static_nj"]), float(r["static_leak_nj"])),
                "SNAX-GVSoC": (float(r["dynamic_nj"]), float(r["leak_design_nj"])),
                "netlist": (sum(n["nl_all"].values()), n["nl_leak"]) if n else None}

    fig, axes = plt.subplots(2, len(PAIRS), figsize=(16, 7.2))
    for j, (title, a, b, la, lb) in enumerate(PAIRS):
        sa, sb = side(a), side(b)
        rows_ = (("dynamic", lambda t: t[0]), ("dynamic + design leakage", lambda t: t[0] + t[1]))
        for i, (row, f) in enumerate(rows_):
            ax = axes[i, j]; w = 0.38
            for k, s in enumerate(SRC):
                va = f(sa[s]) if sa[s] else None; vb = f(sb[s]) if sb[s] else None
                if va is not None:
                    ax.bar(k - w / 2 - 0.01, va, w, color="#257de0")
                if vb is not None:
                    ax.bar(k + w / 2 + 0.01, vb, w, color="#f47230")
                else:
                    ax.text(k + w / 2 + 0.01, (va or 0) * 0.5, "not\nsynthesized", ha="center", va="center",
                            fontsize=7, color="#777", rotation=90)
                if va and vb:
                    ax.text(k, max(va, vb) * 1.04, f"{(vb - va) / va * 100:+.0f} %", ha="center", fontsize=8)
            ax.set_xticks(range(3), ["ADFG", "GVSoC", "netlist"])
            ax.set_ylim(0, max(f(t) for t in (*sa.values(), *sb.values()) if t) * 1.18)
            if j == 0:
                ax.set_ylabel(f"{row} (nJ)")
            if i == 0:
                ax.set_title(f"{title}\n{la} → {lb}", fontsize=9)
    fig.suptitle("Program window energy: blue is the left of each title (before), orange the right (after); "
                 "the label is the change", x=0.01, ha="left", fontsize=10)
    fig.tight_layout(); fig.savefig(HERE / "trends.png", dpi=130); plt.close(fig)


def numbers(rows):
    cols = ["id", "est_cycles", "gv_cycles", "nl_cycles", "est_dyn_nj", "gv_dyn_nj", "nl_dyn_nj", "est_leak_nj",
            "gv_leak_nj", "nl_leak_nj", "nl_dma_io_nj", "gv_run_nj", "nl_run_nj", "est_area_um2", "nl_area_um2"]
    with open(HERE / "numbers.csv", "w", newline="") as fh:
        wr = csv.writer(fh); wr.writerow(cols)
        for r in rows:
            wr.writerow([r["id"], r["est_cycles"], r["gv_cycles"], r["nl_cycles"],
                         *(f"{sum(r[k].values()):.2f}" for k in ("est_e", "gv_all", "nl_all")),
                         *(f"{r[k]:.2f}" for k in ("est_leak", "gv_leak", "nl_leak", "dma_io_nj")),
                         *(f"{sum(r[k].values()):.2f}" for k in ("gv_run", "nl_run")),
                         *(f"{sum(r[k].values()):.0f}" for k in ("est_a", "nl_a"))])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tech", default="nangate45")
    args = ap.parse_args()
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                         "grid.color": "#e6e6e6", "grid.linewidth": 0.6, "axes.axisbelow": True})
    rows, paper, by_id = load(args.tech)
    energy_fig(rows, "gv_run", "nl_run", False, "Energy in the run windows", "energy_run_windows.png")
    energy_fig(rows, "gv_all", "nl_all", False, "Energy over the program window", "energy_program_window.png")
    energy_fig(rows, "gv_all", "nl_all", True, "Program window, dynamic + leakage of the six parts",
               "energy_program_window_leak.png")
    area_fig(rows)
    trends_fig(by_id, paper)
    numbers(rows)
    print(f"{HERE.relative_to(ROOT)}: 5 figures and numbers.csv, {len(rows)} designs")


if __name__ == "__main__":
    main()
