#!/usr/bin/env python3
"""report/cluster_sweep.py - the cluster points of one recipe side by side over W, the netlist beside HWCOST (X78).

    pixi run cluster-sweep [--tech nangate45] [--recipe dot_3] [--md]
    pixi run cluster-sweep-test                     report/test_cluster_sweep.py

Reads what cluster-breakdown and cluster-energy already wrote (results/cluster/<tech>/breakdown.json and
energy.json, X72, X74) for every point of cluster/points.json with the recipe, in order of W, and lays out the run
window only (`5_run`, the busy section, X73) per point:

  energy  the netlist's run-window energy in HWCOST's five parts (datapath, control, streamers, crossbar, memory;
          the groups cluster/groups.json's `hwcost` maps to each), the groups HWCOST does not price as one more
          line, and HWCOST's five parts (nJ per task); shares of each side's own five-part sum, the netlist's also
          of its whole run window
  area    the same layout in um2: the cluster's groups (breakdown.json) beside HWCOST's five parts
  alone   the accelerator's shell in the run window and alone (points.json's `alone`): cycles, pJ/cycle, nJ, um2

A part's share is s_p = E_p / sum over the five parts of E_q, on each side. No normalization, no check on the
trend: the data is laid out, its reading is the user's.

Writes results/cluster/<tech>/sweep.csv in long form (point, W, source, window, group, metric, value; source
`gls` the netlist, `hwcost` snax-forge's estimate, `alone` the shell alone), and two figures beside it,
sweep_energy.png and sweep_area.png: per W the netlist's bar beside HWCOST's, stacked by part, absolute on the
left and in % of the five parts on the right. --md prints the tables as Markdown.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POINTS = ROOT / "cluster" / "points.json"
PARTS = ["datapath", "control", "streamers", "crossbar", "memory"]
REST = "not_priced"      # the netlist's groups HWCOST does not price
RUN = "5_run"
FIELDS = ["point", "W", "source", "window", "group", "metric", "value"]
# Categorical slots 1-5 of the dataviz reference palette in fixed order (validated: adjacent CVD dE >= 9.1,
# normal-vision >= 19.6 on the light surface); the not-priced rest is a neutral ink, hatched as second encoding.
COLORS = {"datapath": "#2a78d6", "control": "#eb6834", "streamers": "#1baf7a", "crossbar": "#eda100",
          "memory": "#e87ba4", REST: "#52514e"}
SURFACE = "#fcfcfb"


def pct(x: float, total: float) -> float:
    return 100.0 * x / total if total else 0.0


def point_data(p: dict, energy: dict, breakdown: dict) -> dict:
    """One point's run-window energy, area and alone row, from energy.json's and breakdown.json's entries."""
    e, b = energy[p["point"]], breakdown[p["point"]]
    run = next(w for w in e["windows"] if w["name"] == RUN)
    if len(e["run"]) != 1 or e["run"][0]["window"] != RUN:
        raise SystemExit(f"{p['point']}: one run window {RUN} expected, energy.json has {e['run']}")
    eh = {q["part"]: q for q in e["hwcost"]["parts"]}
    ah = {q["part"]: q for q in b["hwcost"]["parts"]}
    gls_e = {k: eh[k]["run_nj"] for k in PARTS}
    gls_e[REST] = run["nj"] - sum(gls_e.values())
    gls_a = {k: ah[k]["cluster_um2"] for k in PARTS}
    gls_a[REST] = b["total_um2"] - sum(gls_a.values())
    al = e["alone"]
    shell_area = {r["name"]: r for r in b["alone"]["rows"]}["total"]
    return {
        "point": p["point"], "W": int(p["W"]), "run_cycles": run["cycles"], "run_nj": run["nj"],
        "span_cycles": e["span"]["cycles"], "span_nj": e["span"]["nj"],
        "groups_pj": dict(run["groups"]),       # pJ per cycle per X72 group in the run window
        "groups_um2": {g["name"]: g["area_um2"] for g in b["groups"]},
        "gls_e": gls_e, "hw_e": {k: eh[k]["hwcost_nj"] for k in PARTS},
        "gls_a": gls_a, "hw_a": {k: ah[k]["hwcost_um2"] for k in PARTS}, "area_um2": b["total_um2"],
        "alone_point": al["point"], "shell_cluster": al["cluster"], "shell_alone": al["alone"],
        "shell_cluster_um2": shell_area["cluster_um2"], "shell_alone_um2": shell_area["alone_um2"],
        "snax_forge_commit": e["snax_forge_commit"], "hwcost_commit": e["hwcost"]["snax_forge_commit"],
    }


def load(tech: str, recipe: str) -> list[dict]:
    base = ROOT / "results" / "cluster" / tech
    energy = json.loads((base / "energy.json").read_text())
    breakdown = json.loads((base / "breakdown.json").read_text())
    pts = [p for p in json.loads(POINTS.read_text())["points"] if p["recipe"] == recipe]
    missing = [p["point"] for p in pts if p["point"] not in energy or p["point"] not in breakdown]
    if missing:
        raise SystemExit(f"no energy.json or breakdown.json entry for {missing}: run cluster-breakdown and cluster-energy")
    return sorted((point_data(p, energy, breakdown) for p in pts), key=lambda d: d["W"])


def rows(pts: list[dict]) -> list[list]:
    """sweep.csv's rows: every number of the tables, plus the run window's and the area's X72 groups."""
    out: list[list] = []
    for d in pts:
        pw = [d["point"], d["W"]]
        out += [pw + ["gls", RUN, "", "cycles", d["run_cycles"]], pw + ["gls", RUN, "", "nj", d["run_nj"]],
                pw + ["gls", "span", "", "cycles", d["span_cycles"]], pw + ["gls", "span", "", "nj", d["span_nj"]]]
        five_e, five_he = sum(d["gls_e"][k] for k in PARTS), sum(d["hw_e"].values())
        five_a, five_ha = sum(d["gls_a"][k] for k in PARTS), sum(d["hw_a"].values())
        for k in [*PARTS, REST]:
            out += [pw + ["gls", RUN, k, "nj", d["gls_e"][k]],
                    pw + ["gls", RUN, k, "share_total_pct", pct(d["gls_e"][k], d["run_nj"])],
                    pw + ["gls", "area", k, "um2", d["gls_a"][k]],
                    pw + ["gls", "area", k, "share_total_pct", pct(d["gls_a"][k], d["area_um2"])]]
            if k in PARTS:
                out += [pw + ["gls", RUN, k, "share_five_pct", pct(d["gls_e"][k], five_e)],
                        pw + ["gls", "area", k, "share_five_pct", pct(d["gls_a"][k], five_a)],
                        pw + ["hwcost", "task", k, "nj", d["hw_e"][k]],
                        pw + ["hwcost", "task", k, "share_five_pct", pct(d["hw_e"][k], five_he)],
                        pw + ["hwcost", "area", k, "um2", d["hw_a"][k]],
                        pw + ["hwcost", "area", k, "share_five_pct", pct(d["hw_a"][k], five_ha)]]
        out += [pw + ["gls", RUN, "five_parts", "nj", five_e], pw + ["hwcost", "task", "five_parts", "nj", five_he],
                pw + ["gls", "area", "five_parts", "um2", five_a], pw + ["hwcost", "area", "five_parts", "um2", five_ha],
                pw + ["gls", "area", "", "um2", d["area_um2"]]]
        for g, v in d["groups_um2"].items():
            out.append(pw + ["gls", "area_group", g, "um2", v])
        for g, v in d["groups_pj"].items():
            out += [pw + ["gls", f"{RUN}_group", g, "pj_cycle", v],
                    pw + ["gls", f"{RUN}_group", g, "nj", v * d["run_cycles"] / 1000.0]]
        for src, w, s in (("gls", RUN, d["shell_cluster"]), ("alone", "busy", d["shell_alone"])):
            out += [pw + [src, w, "shell", m, s[m]] for m in ("cycles", "pj_cycle", "nj")]
        out += [pw + ["gls", "area", "shell", "um2", d["shell_cluster_um2"]],
                pw + ["alone", "area", "shell", "um2", d["shell_alone_um2"]]]
    return out


def write_csv(path: Path, data: list[list]) -> None:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(FIELDS)
    for r in data:
        w.writerow([f"{v:.6g}" if isinstance(v, float) else v for v in r])
    path.write_text(buf.getvalue())


def f0(x: float) -> str:
    return f"{x:,.0f}"


def f2(x: float) -> str:
    return f"{x:,.2f}"


def f1(x: float) -> str:
    return f"{x:.1f} %"


def markdown(pts: list[dict]) -> str:
    out = ["Across W (run window `5_run`; span = the first mark to the end of the last DMA out, X73):", "",
           "| W | point | run cycles | run nJ | five parts nJ | HWCOST nJ | span cycles | span nJ | area µm² | five parts µm² | HWCOST µm² |",
           "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for d in pts:
        out.append(f"| {d['W']} | `{d['point']}` | {f0(d['run_cycles'])} | {f2(d['run_nj'])} | "
                   f"{f2(sum(d['gls_e'][k] for k in PARTS))} | {f2(sum(d['hw_e'].values()))} | {f0(d['span_cycles'])} | "
                   f"{f2(d['span_nj'])} | {f0(d['area_um2'])} | {f0(sum(d['gls_a'][k] for k in PARTS))} | "
                   f"{f0(sum(d['hw_a'].values()))} |")
    for d in pts:
        five_e, five_he = sum(d["gls_e"][k] for k in PARTS), sum(d["hw_e"].values())
        five_a, five_ha = sum(d["gls_a"][k] for k in PARTS), sum(d["hw_a"].values())
        out += ["", f"### W = {d['W']} (`{d['point']}`), run window {f0(d['run_cycles'])} cycles", "", "Energy:", "",
                "| part | netlist nJ | % of five | % of run | HWCOST nJ | % of five |", "|---|---:|---:|---:|---:|---:|"]
        for k in PARTS:
            out.append(f"| {k} | {f2(d['gls_e'][k])} | {f1(pct(d['gls_e'][k], five_e))} | "
                       f"{f1(pct(d['gls_e'][k], d['run_nj']))} | {f2(d['hw_e'][k])} | {f1(pct(d['hw_e'][k], five_he))} |")
        out += [f"| the five parts | {f2(five_e)} | 100 % | {f1(pct(five_e, d['run_nj']))} | {f2(five_he)} | 100 % |",
                f"| not priced by HWCOST (AXI, DMA, cores, I-cache, TCDM bank logic, ...) | {f2(d['gls_e'][REST])} | | "
                f"{f1(pct(d['gls_e'][REST], d['run_nj']))} | | |",
                f"| run window | {f2(d['run_nj'])} | | 100 % | | |", "", "Area:", "",
                "| part | netlist µm² | % of five | % of cluster | HWCOST µm² | % of five |", "|---|---:|---:|---:|---:|---:|"]
        for k in PARTS:
            out.append(f"| {k} | {f0(d['gls_a'][k])} | {f1(pct(d['gls_a'][k], five_a))} | "
                       f"{f1(pct(d['gls_a'][k], d['area_um2']))} | {f0(d['hw_a'][k])} | {f1(pct(d['hw_a'][k], five_ha))} |")
        out += [f"| the five parts | {f0(five_a)} | 100 % | {f1(pct(five_a, d['area_um2']))} | {f0(five_ha)} | 100 % |",
                f"| not priced by HWCOST | {f0(d['gls_a'][REST])} | | {f1(pct(d['gls_a'][REST], d['area_um2']))} | | |",
                f"| cluster | {f0(d['area_um2'])} | | 100 % | | |", "",
                f"The accelerator's shell (csr, control, datapath) against `{d['alone_point']}` alone:", "",
                "| shell | cycles | pJ/cycle | nJ | µm² |", "|---|---:|---:|---:|---:|"]
        for name, s, a in (("in the cluster, run window", d["shell_cluster"], d["shell_cluster_um2"]),
                           ("alone, busy window, rand64 seed 0", d["shell_alone"], d["shell_alone_um2"])):
            out.append(f"| {name} | {f0(s['cycles'])} | {f2(s['pj_cycle'])} | {f2(s['nj'])} | {f0(a)} |")
    return "\n".join(out) + "\n"


def figure(pts: list[dict], kind: str, path: Path) -> None:
    """Per W the netlist's bar beside HWCOST's, stacked by part: absolute (left), % of the five parts (right)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    gk, hk, unit = ("gls_e", "hw_e", "nJ") if kind == "energy" else ("gls_a", "hw_a", "mm²")
    scale = 1.0 if kind == "energy" else 1e-6       # area plotted in mm² (the tables keep µm²)
    what = "run-window energy" if kind == "energy" else "area"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), facecolor=SURFACE)
    width, gap = 0.36, 0.04
    xs = list(range(len(pts)))
    for ax, share in zip(axes, (False, True)):
        ax.set_facecolor(SURFACE)
        for x, d in zip(xs, pts):
            for side, key, dx in (("netlist", gk, -(width + gap) / 2), ("HWCOST", hk, (width + gap) / 2)):
                vals = d[key]
                five = sum(vals[k] for k in PARTS)
                parts = PARTS + ([REST] if side == "netlist" and not share else [])
                bottom = 0.0
                for k in parts:
                    v = pct(vals[k], five) if share else vals[k] * scale
                    ax.bar(x + dx, v, width, bottom=bottom, color=COLORS[k], edgecolor=SURFACE, linewidth=1.5,
                           hatch="//" if k == REST else None, label=k)
                    bottom += v
                ax.text(x + dx, -0.02, "GLS" if side == "netlist" else "HW", transform=ax.get_xaxis_transform(),
                        ha="center", va="top", fontsize=7.5, color="#52514e")
        ax.set_xticks(xs, [f"\n\nW = {d['W']}" for d in pts], fontsize=9)
        ax.tick_params(axis="x", length=0)
        ax.set_ylabel("% of the five parts" if share else unit, fontsize=9, color="#52514e")
        ax.set_title(f"{what}, {'shares of the five parts' if share else 'absolute'}", fontsize=10)
        ax.grid(axis="y", alpha=0.25)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        if share:
            ax.set_ylim(0, 100)
    handles, labels = axes[0].get_legend_handles_labels()
    seen = {}
    for h, lab in zip(handles, labels):
        seen.setdefault(lab, h)
    names = {REST: "not priced by HWCOST (netlist only)"}
    fig.legend([seen[k] for k in [*PARTS, REST]], [names.get(k, k) for k in [*PARTS, REST]], loc="lower center",
               ncol=6, fontsize=8.5, frameon=False)
    src = "run window 5_run" if kind == "energy" else "DC area per group"
    fig.suptitle(f"dot_3 in the one-core cluster, N = 2048, nangate45, 10 ns: {what} (GLS: netlist, {src}; HW: HWCOST)",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0.07, 1, 0.97))
    fig.savefig(path, dpi=130, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--recipe", default="dot_3")
    ap.add_argument("--md", action="store_true", help="print the tables as Markdown")
    ap.add_argument("--no-figures", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()
    pts = load(a.tech, a.recipe)
    base = ROOT / "results" / "cluster" / a.tech
    write_csv(base / "sweep.csv", rows(pts))
    if not a.no_figures:
        figure(pts, "energy", base / "sweep_energy.png")
        figure(pts, "area", base / "sweep_area.png")
    ws = ", ".join(f"W = {d['W']}" for d in pts)
    print(f"{len(pts)} points ({ws}): "
          f"results/cluster/{a.tech}/sweep.csv{'' if a.no_figures else ', sweep_energy.png, sweep_area.png'}")
    if a.md:
        print(markdown(pts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
