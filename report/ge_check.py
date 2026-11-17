#!/usr/bin/env python3
"""report/ge_check.py - snax-forge's dynamic energy (GE1) beside the static estimate and the netlist, over W.

    pixi run ge-check [--tech nangate45] [--recipe dot_3] [--md]

Per point of the recipe in cluster/points.json, in order of W, the run window's energy in HWCOST's five parts
from three sources: the gated netlist (energy.json's `run`, the groups cluster/groups.json's `hwcost` maps to
each part), the static estimate (hwcost/<point>.json) and the dynamic one (ge/<point>.json's `run` window,
snax-forge's `pixi run flow ... --energy`, D177). Each estimate's ratio to the netlist per part, and Kendall's
tau over W of each estimate's totals against the netlist's (tau-a: concordant minus discordant pairs over all
pairs). The crossbar is also given at the read-write price (every request at `e_access`, before snax-forge D178)
from the same counts. Writes results/cluster/<tech>/ge/ge_check.csv (long form: point, W, part, source,
energy_nj) and ge_energy_five.png (per W the three bars stacked by part); --md prints the tables. No check on
the trend: the data is laid out, its reading is the user's. Standard library and matplotlib.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "report"))
from cluster_sweep import COLORS, PARTS, STACK, SURFACE  # noqa: E402

SOURCES = ("netlist", "static", "ge")
LABELS = {"netlist": "GLS", "static": "static", "ge": "GE1"}


def tau(a: list[float], b: list[float]) -> float:
    """Kendall's tau-a of two equally long series: (concordant - discordant) / pairs; a tie in either is
    neither."""
    pairs = list(combinations(range(len(a)), 2))
    if not pairs:
        return 0.0
    s = sum((a[i] - a[j]) * (b[i] - b[j]) > 0 for i, j in pairs) - sum(
        (a[i] - a[j]) * (b[i] - b[j]) < 0 for i, j in pairs)
    return s / len(pairs)


def run_window(ge: dict) -> dict:
    """The `run` window of a ge file; exactly one is expected."""
    runs = [w for w in ge["windows"] if w["kind"] == "run"]
    if len(runs) != 1:
        raise ValueError(f"{len(runs)} run windows, expected one")
    return runs[0]


def point_data(p: dict, energy: dict, groups: dict, hwcost: dict, ge: dict) -> dict:
    """The run window's five parts from the three sources, and the counts beside them."""
    (win,) = energy["run"]    # one run window (dot_3's 5_run)
    run = {g["group"]: g["run_nj"] for g in win["groups"]}
    net = {k: sum(run[g] for g in groups[k]) for k in PARTS}
    cost = hwcost["cost"]
    static = {k: cost["parts"][k]["energy"] for k in PARTS}
    w = run_window(ge)
    dyn = {k: w["energy"]["parts"][k] for k in PARTS}
    e_rw = cost["xbar"]["e_access"]
    return {"point": p["point"], "W": p["W"], "cycles": {"netlist": win["cycles"], "ge": w["cycles"]},
            "netlist": net, "static": static, "ge": dyn,
            "requests": {"static": ge["static"]["counts"]["requests"], "ge": w["energy"]["counts"]["requests"]},
            "busy": {"static": ge["static"]["counts"]["cycles"], "ge": w["energy"]["counts"]["cycles"]},
            "xbar_rw": {"static": ge["static"]["counts"]["requests"] * e_rw / 1000,
                        "ge": w["energy"]["counts"]["requests"] * e_rw / 1000}}


def load(tech: str, recipe: str) -> list[dict]:
    res = ROOT / "results" / "cluster" / tech
    pts = [p for p in json.loads((ROOT / "cluster" / "points.json").read_text())["points"]
           if p.get("recipe") == recipe and (res / "ge" / f"{p['point']}.json").is_file()]
    energy = json.loads((res / "energy.json").read_text())
    groups = json.loads((ROOT / "cluster" / "groups.json").read_text())["hwcost"]
    out = [point_data(p, energy[p["point"]], groups, json.loads((res / "hwcost" / f"{p['point']}.json").read_text()),
                      json.loads((res / "ge" / f"{p['point']}.json").read_text())) for p in pts]
    return sorted(out, key=lambda d: d["W"])


def taus(pts: list[dict]) -> dict:
    """Kendall's tau over W of each estimate against the netlist: per part and of the five parts' total."""
    out = {}
    for k in [*PARTS, "five"]:
        def v(d: dict, s: str, k: str = k) -> float:
            return sum(d[s].values()) if k == "five" else d[s][k]
        net = [v(d, "netlist") for d in pts]
        out[k] = {s: tau([v(d, s) for d in pts], net) for s in ("static", "ge")}
    return out


def write_csv(path: Path, pts: list[dict]) -> None:
    with path.open("w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["point", "W", "part", "source", "energy_nj"])
        for d in pts:
            for s in SOURCES:
                for k in PARTS:
                    w.writerow([d["point"], d["W"], k, s, f"{d[s][k]:.6f}"])
            for s in ("static", "ge"):
                w.writerow([d["point"], d["W"], "crossbar_rw", s, f"{d['xbar_rw'][s]:.6f}"])


def markdown(pts: list[dict]) -> str:
    def r(x: float, y: float) -> str:
        return f"{x / y:.2f}" if y else "–"
    out = ["| W | cycles (GLS / GVSoC) | GLS five parts (nJ) | static | GE1 | static / GLS | GE1 / GLS |",
           "|---|---|---|---|---|---|---|"]
    for d in pts:
        n, s, g = (sum(d[x].values()) for x in SOURCES)
        out.append(f"| {d['W']} | {d['cycles']['netlist']} / {d['cycles']['ge']} | {n:.2f} | {s:.2f} | {g:.2f} | "
                   f"{r(s, n)} | {r(g, n)} |")
    out += ["", "| W | " + " | ".join(f"{k} static / GE1" for k in PARTS) + " |", "|---" * (len(PARTS) + 1) + "|"]
    for d in pts:
        out.append(f"| {d['W']} | " + " | ".join(f"{r(d['static'][k], d['netlist'][k])} / "
                                                 f"{r(d['ge'][k], d['netlist'][k])}" for k in PARTS) + " |")
    out += ["", "| W | requests static / GE1 | busy cycles static / GE1 | crossbar at the read-write price, static / GE1 "
            "(nJ) |", "|---|---|---|---|"]
    for d in pts:
        out.append(f"| {d['W']} | {d['requests']['static']} / {d['requests']['ge']} | {d['busy']['static']} / "
                   f"{d['busy']['ge']} | {d['xbar_rw']['static']:.3f} / {d['xbar_rw']['ge']:.3f} |")
    t = taus(pts)
    out += ["", "| Kendall tau over W against GLS | " + " | ".join([*PARTS, "five parts"]) + " |",
            "|---" * (len(PARTS) + 2) + "|"]
    for s in ("static", "ge"):
        out.append(f"| {LABELS[s]} | " + " | ".join(f"{t[k][s]:+.1f}" for k in [*PARTS, "five"]) + " |")
    return "\n".join(out) + "\n"


def figure(pts: list[dict], path: Path) -> None:
    """Per W three bars, the netlist's, the static estimate's and GE1's, stacked in STACK's order, each total
    above its bar."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8.5, 4.8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    width, gap = 0.26, 0.03
    for x, d in enumerate(pts):
        for i, s in enumerate(SOURCES):
            dx = (i - 1) * (width + gap)
            bottom = 0.0
            for k in STACK:
                ax.bar(x + dx, d[s][k], width, bottom=bottom, color=COLORS[k], edgecolor=SURFACE, linewidth=1.5,
                       label=k)
                bottom += d[s][k]
            ax.text(x + dx, bottom, f"{bottom:,.0f}", ha="center", va="bottom", fontsize=7.5, color="#0b0b0b")
            ax.text(x + dx, -0.02, LABELS[s], transform=ax.get_xaxis_transform(), ha="center", va="top",
                    fontsize=7.5, color="#52514e")
    ax.set_xticks(range(len(pts)), [f"\n\nW = {d['W']}" for d in pts], fontsize=9)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("nJ", fontsize=9, color="#52514e")
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    handles, labels = ax.get_legend_handles_labels()
    seen = dict(zip(labels, handles))
    fig.legend([seen[k] for k in STACK], STACK, loc="lower center", ncol=len(STACK), fontsize=8.5, frameon=False)
    fig.suptitle("dot_3 in the one-core cluster, clock-gated, N = 2048, nangate45: run-window energy, five parts\n"
                 "GLS: netlist; static: HWCOST on the graph; GE1: HWCOST's prices on SNAX-GVSoC's counts",
                 fontsize=10.5)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    fig.savefig(path, dpi=130, facecolor=SURFACE, metadata={"Software": None})
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--recipe", default="dot_3")
    ap.add_argument("--md", action="store_true", help="print the tables as Markdown")
    a = ap.parse_args()
    pts = load(a.tech, a.recipe)
    if not pts:
        print(f"ge-check: no {a.recipe} point with a ge/ file", file=sys.stderr)
        return 1
    out = ROOT / "results" / "cluster" / a.tech / "ge"
    write_csv(out / "ge_check.csv", pts)
    figure(pts, out / "ge_energy_five.png")
    t = taus(pts)["five"]
    print(f"ge-check: {len(pts)} points; Kendall tau of the five parts over W against GLS: static {t['static']:+.1f}, "
          f"GE1 {t['ge']:+.1f}; wrote {(out / 'ge_check.csv').relative_to(ROOT)}, "
          f"{(out / 'ge_energy_five.png').relative_to(ROOT)}")
    if a.md:
        print(markdown(pts), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
