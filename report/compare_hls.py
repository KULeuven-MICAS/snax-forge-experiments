#!/usr/bin/env python3
"""report/compare_hls.py - results/compare_hls.md: the four HLS cases side by side, per kernel (X46).

  pixi run compare-hls

Reads only results/compare_done.csv and results/compare_untiered.csv (report/compare.py, X45). Writes, for the
HLS cases Vitis opt, Vitis dace, Bambu and XLS (forge is left out until its accelerator parts are in):

  results/compare_hls/<tier>_<kernel>.png    area, energy, latency and power against W, one line per case
  results/compare_hls.md                     the generated parts between <!-- gen:NAME --> and <!-- /gen -->

Everything outside the markers is hand-written (the insights) and is kept as it is; a missing file is created
from a template with every marker in place. Main view: nangate45, int64, a 10 ns clock; tier done at n2048
(X24), untiered at each kernel's larger task size. Power is P = E_run / (cycles x T_clk), T_clk = 10 ns.
"""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
MD = RESULTS / "compare_hls.md"
FIGS = RESULTS / "compare_hls"
TECH, CHECK_TECH = "nangate45", "nangate15"
T_CLK_NS = 10.0
CASES = [("vitis", "opt"), ("vitis", "dace"), ("bambu", "bambu"), ("xls", "xls")]
LABEL = {"opt": "Vitis opt", "dace": "Vitis dace", "bambu": "Bambu", "xls": "XLS"}
STYLE = {"opt": ("#1f77b4", "o", "-"), "dace": ("#9467bd", "s", "--"), "bambu": ("#d62728", "^", "-"),
         "xls": ("#2ca02c", "D", "-")}
KERNELS = {"done": ["vecadd", "vecmul", "vsum", "dot"], "untiered": ["matadd", "relu", "axpy", "rowsum"]}
SIZE = {"done": {k: "n2048" for k in KERNELS["done"]},
        "untiered": {"matadd": "m16_n32", "relu": "n512", "axpy": "n512", "rowsum": "m8_n64"}}
WS = [1, 2, 4, 8, 16]
METRICS = [("area_um2", "Area", "µm²"), ("energy_nj", "Energy per task", "nJ"),
           ("cycles", "Latency per task", "cycles"), ("power_mw", "Power", "mW")]


def load(tier: str) -> list[dict]:
    with (RESULTS / f"compare_{tier}.csv").open(newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if r["tool"] != "forge"]
    for r in rows:
        if r["status"] == "ok":
            e = float(r["e_run_pj"])
            r["energy_nj"] = e / 1000.0
            r["power_mw"] = e / (int(r["cycles"]) * T_CLK_NS)  # pJ / ns = mW
    return rows


def pick(rows: list[dict], tech: str, tier: str, kernel: str) -> dict:
    """(case, W) -> row at the main size, ok or parked."""
    out = {}
    for r in rows:
        if r["tech"] != tech or r["kernel"] != kernel:
            continue
        if r["status"] == "ok" and r["size"] != SIZE[tier][kernel]:
            continue
        out[(r["case"], int(r["W"]))] = r
    return out


def fmt(x: float, digits: int = 4) -> str:
    if x >= 1000:
        return f"{x:,.0f}"
    return f"{x:.{digits}g}"


def figure(tier: str, kernel: str, pts: dict) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(9, 6.6))
    for ax, (key, title, unit) in zip(axes.flat, METRICS):
        for _tool, case in CASES:
            ws = [w for w in WS if (case, w) in pts and pts[(case, w)]["status"] == "ok"]
            if not ws:
                continue
            color, marker, line = STYLE[case]
            ax.plot(ws, [float(pts[(case, w)][key]) for w in ws],
                    color=color, marker=marker, linestyle=line, label=LABEL[case], markersize=5)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(WS, [str(w) for w in WS])
        ax.set_xlabel("W (lanes, int64)")
        ax.set_title(f"{title} ({unit})", fontsize=10)
        ax.grid(True, which="both", alpha=0.3)
    axes.flat[0].legend(fontsize=8)
    fig.suptitle(f"{kernel} ({tier}), {SIZE[tier][kernel]}, {TECH}, 10 ns clock", fontsize=11)
    fig.tight_layout()
    FIGS.mkdir(parents=True, exist_ok=True)
    path = FIGS / f"{tier}_{kernel}.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path.relative_to(RESULTS).as_posix()


def table(tier: str, kernel: str, pts: dict) -> list[str]:
    lines = ["| W | Case | Area (µm²) | Energy (nJ) | Latency (cycles) | Power (mW) |", "|---|---|---|---|---|---|"]
    for w in WS:
        for _tool, case in CASES:
            r = pts.get((case, w))
            if r is None:
                continue
            if r["status"] != "ok":
                lines.append(f"| {w} | {LABEL[case]} | parked: needs a RAM macro | | | |")
                continue
            lines.append(f"| {w} | {LABEL[case]} | {fmt(float(r['area_um2']))} | {fmt(r['energy_nj'])} | "
                         f"{int(r['cycles'])} | {fmt(r['power_mw'])} |")
    return lines


def setup(rows: list[dict]) -> list[str]:
    ver, commit = {}, defaultdict(set)
    for r in rows:
        if r["status"] == "ok":
            ver[r["case"]] = r["tool_version"]
            commit[r["case"]].add(r["rtl_commit"][:7])
    windows = {r["case"]: r["window"] for r in rows if r["window"]}
    lines = ["| Case | Tool version | RTL measured at | Latency window |", "|---|---|---|---|"]
    for _tool, case in CASES:
        lines.append(f"| {LABEL[case]} | {ver.get(case, '')} | {', '.join(sorted(commit[case]))} | "
                     f"{windows.get(case, '')} |")
    lines += ["", f"Main view: {TECH}, int64, every point synthesized at a 10 ns clock and scheduled at a 10 ns HLS "
              "clock, W = 1 to 16 lanes per stream. Sizes: tier done at n2048 (2048 elements per input stream, X24); "
              "untiered at each kernel's larger task size: " +
              ", ".join(f"{k} {s}" for k, s in SIZE["untiered"].items()) + ". "
              "Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is "
              "E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition."]
    return lines


def tech_check(done: list[dict], untiered: list[dict]) -> list[str]:
    """nangate45 against nangate15: values at W = 8, and how often the order of the cases is the same."""
    lines = ["Values at W = 8 (nangate45 / nangate15); latency is the same on both:", "",
             "| Kernel | Case | Area (µm²) | Energy (nJ) | Power (mW) |", "|---|---|---|---|---|"]
    same = total = 0
    for tier, rows in (("done", done), ("untiered", untiered)):
        for kernel in KERNELS[tier]:
            a, b = pick(rows, TECH, tier, kernel), pick(rows, CHECK_TECH, tier, kernel)
            for _tool, case in CASES:
                ra, rb = a.get((case, 8)), b.get((case, 8))
                if ra and rb and ra["status"] == rb["status"] == "ok":
                    lines.append(f"| {kernel} | {LABEL[case]} | {fmt(float(ra['area_um2']))} / "
                                 f"{fmt(float(rb['area_um2']))} | {fmt(ra['energy_nj'])} / {fmt(rb['energy_nj'])} | "
                                 f"{fmt(ra['power_mw'])} / {fmt(rb['power_mw'])} |")
            for w in WS:
                for key in ("area_um2", "energy_nj", "power_mw"):
                    ca = [c for _t, c in CASES if (c, w) in a and a[(c, w)]["status"] == "ok"
                          and (c, w) in b and b[(c, w)]["status"] == "ok"]
                    if len(ca) < 2:
                        continue
                    oa = sorted(ca, key=lambda c: float(a[(c, w)][key]))
                    ob = sorted(ca, key=lambda c: float(b[(c, w)][key]))
                    total += 1
                    same += oa == ob
    lines += ["", f"The order of the cases (smallest to largest) is the same on both technologies in {same} of "
              f"{total} comparisons (kernel, W and metric with at least two cases)."]
    return lines


def template() -> str:
    parts = ["# The HLS cases side by side: Vitis opt and dace, Bambu, XLS", "",
             "Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs "
             "(X45, X46); the text outside the `gen` markers is written by hand. Forge is left out until its "
             "accelerator parts are in.", "", "## 1. Setup", "", "<!-- gen:setup -->", "<!-- /gen -->", ""]
    n = 2
    for tier in ("done", "untiered"):
        parts += [f"## {n}. Tier {tier}", ""]
        for kernel in KERNELS[tier]:
            parts += [f"### {kernel}", "", f"<!-- gen:{tier}/{kernel} -->", "<!-- /gen -->", "",
                      "**Insights.**", "", "- (to write)", ""]
        n += 1
    parts += [f"## {n}. nangate15 check", "", "<!-- gen:tech -->", "<!-- /gen -->", "",
              f"## {n + 1}. Notes", "", "- Parked points (a RAM macro, X15): Vitis dace_w1 of dot, axpy and rowsum.",
              "- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.",
              ""]
    return "\n".join(parts)


def fill(text: str, name: str, body: list[str]) -> str:
    pat = re.compile(rf"(<!-- gen:{re.escape(name)} -->\n).*?(<!-- /gen -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"compare_hls.md: marker gen:{name} is missing")
    return pat.sub(lambda m: m.group(1) + "\n".join(body) + "\n" + m.group(2), text, count=1)


def main() -> int:
    done, untiered = load("done"), load("untiered")
    text = MD.read_text() if MD.is_file() else template()
    text = fill(text, "setup", setup(done + untiered))
    for tier, rows in (("done", done), ("untiered", untiered)):
        for kernel in KERNELS[tier]:
            pts = pick(rows, TECH, tier, kernel)
            fig = figure(tier, kernel, pts)
            body = [f"![{kernel}]({fig})", "", f"{SIZE[tier][kernel]}, {TECH}, int64, 10 ns.", ""]
            text = fill(text, f"{tier}/{kernel}", body + table(tier, kernel, pts))
    text = fill(text, "tech", tech_check(done, untiered))
    MD.write_text(text)
    print(f"compare-hls: {MD.relative_to(ROOT)} and {len(list(FIGS.glob('*.png')))} figures in "
          f"{FIGS.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
