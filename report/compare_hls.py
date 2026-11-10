#!/usr/bin/env python3
"""report/compare_hls.py - results/compare/: forge and the four HLS cases side by side, one page per kernel (X46, X64).

  pixi run compare-hls

Reads only results/compare_done.csv and results/compare_untiered.csv (report/compare.py, X45). Writes, for the
HLS cases Vitis opt, Vitis dace, Bambu and XLS, and forge's cases of the kernel (forge, forge2 to forge6,
forge_baked; X61):

  results/compare/README.md                  the setup, the summary across kernels, the index, the nangate15 check
  results/compare/<tier>/<kernel>.md         one kernel: its figure and table, the insights, the parts at n2048
  results/compare/<tier>/<kernel>.png        area, energy, latency and power against W, one line per case

Only the parts between <!-- gen:NAME --> and <!-- /gen --> are generated. Everything outside the markers is
hand-written (the summary and the insights) and is kept as it is; a missing page is created from a template
with every marker in place. Main view: nangate45, int64, a 10 ns clock; tier done at n2048
(X24) and untiered at n2048 too (X55, X61); the nangate15 check compares untiered at each kernel's larger cosim
size, the only one both technologies have. Power is P = E_run / (cycles x T_clk), T_clk = 10 ns.
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
OUT = RESULTS / "compare"
README = OUT / "README.md"
TECH, CHECK_TECH = "nangate45", "nangate15"
T_CLK_NS = 10.0
HLS_CASES = [("vitis", "opt"), ("vitis", "dace"), ("bambu", "bambu"), ("xls", "xls")]
FORGE_CASES = [("forge", c) for c in ("forge", "forge2", "forge3", "forge4", "forge5", "forge6", "forge_baked")]
CASES = FORGE_CASES + HLS_CASES        # forge first, as compare.py orders the tools
LABEL = {"opt": "Vitis opt", "dace": "Vitis dace", "bambu": "Bambu", "xls": "XLS", "forge": "forge",
         **{f"forge{k}": f"forge {k}" for k in range(2, 7)}, "forge_baked": "forge baked"}
STYLE = {"opt": ("#1f77b4", "o", "-"), "dace": ("#9467bd", "s", "--"), "bambu": ("#d62728", "^", "-"),
         "xls": ("#2ca02c", "D", "-"), "forge": ("#000000", "*", "-"), "forge2": ("#7f7f7f", "v", ":"),
         "forge3": ("#8c564b", "<", ":"), "forge4": ("#e377c2", ">", ":"), "forge5": ("#bcbd22", "p", ":"),
         "forge6": ("#17becf", "h", ":"), "forge_baked": ("#7f7f7f", "x", "--")}
KERNELS = {"done": ["vecadd", "vecmul", "vsum", "dot"], "untiered": ["matadd", "relu", "axpy", "rowsum"]}
SIZE = {"done": {k: "n2048" for k in KERNELS["done"]}, "untiered": {k: "n2048" for k in KERNELS["untiered"]}}
# the nangate15 check: untiered has no n2048 there (X61), so it compares the larger cosim size
CHECK_SIZE = {"done": SIZE["done"],
              "untiered": {"matadd": "m16_n32", "relu": "n512", "axpy": "n512", "rowsum": "m8_n64"}}
WS = [1, 2, 4, 8, 16]
METRICS = [("area_um2", "Area", "µm²"), ("energy_nj", "Energy per task", "nJ"),
           ("cycles", "Latency per task", "cycles"), ("power_mw", "Power", "mW")]


def load(tier: str) -> list[dict]:
    with (RESULTS / f"compare_{tier}.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        if r["status"] == "ok":
            e = float(r["e_run_pj"])
            r["energy_nj"] = e / 1000.0
            r["power_mw"] = e / (int(r["cycles"]) * T_CLK_NS)  # pJ / ns = mW
    return rows


def pick(rows: list[dict], tech: str, tier: str, kernel: str, sizes: dict = SIZE) -> dict:
    """(case, W) -> row at the main size, ok or parked."""
    out = {}
    for r in rows:
        if r["tech"] != tech or r["kernel"] != kernel:
            continue
        if r["status"] == "ok" and r["size"] != sizes[tier][kernel]:
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
    path = OUT / tier / f"{kernel}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path.name  # the kernel's page sits beside it


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
        if case not in commit:
            continue
        lines.append(f"| {LABEL[case]} | {ver.get(case, '')} | {', '.join(sorted(commit[case]))} | "
                     f"{windows.get(case, '')} |")
    lines += ["", f"Main view: {TECH}, int64, every point synthesized at a 10 ns clock (the HLS tools scheduled at a "
              "10 ns HLS clock), W = 1 to 16 lanes per stream. Size: n2048 everywhere, 2048 elements per input "
              "stream (X24, X55): tier done N = 2048, untiered relu and axpy n = 2048, matadd m32_n64, rowsum "
              "m16_n128. Energy is the dynamic energy of one task (PrimePower on simulated activity, X7); power is "
              "E_run / (cycles x 10 ns). The latency windows differ by a cycle or two by definition. forge's cases: "
              "dot 2 to 6 (forge2 to forge6), axpy with alpha baked to 3 (forge baked), rowsum 2 (forge2)."]
    return lines


def tech_check(done: list[dict], untiered: list[dict]) -> list[str]:
    """nangate45 against nangate15: values at W = 8, and how often the order of the cases is the same."""
    lines = ["Values at W = 8 (nangate45 / nangate15); latency is the same on both. Tier done at n2048, untiered at "
             "each kernel's larger cosim size (" + ", ".join(f"{k} {s}" for k, s in CHECK_SIZE["untiered"].items())
             + "): untiered has no n2048 on nangate15, and forge's untiered points are nangate45 only.", "",
             "| Kernel | Case | Area (µm²) | Energy (nJ) | Power (mW) |", "|---|---|---|---|---|"]
    same = total = 0
    for tier, rows in (("done", done), ("untiered", untiered)):
        for kernel in KERNELS[tier]:
            a, b = pick(rows, TECH, tier, kernel, CHECK_SIZE), pick(rows, CHECK_TECH, tier, kernel, CHECK_SIZE)
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


# X65: the line on top of the README and of every kernel page (hand-written text, outside the markers)
PERIPHERALS_LINE = "csr excludes `<tag>_peripherals` (BUSY_COUNTER), snax-forge D168."
PARTS_BASIS = (
    "Every point at n2048 on nangate45 (2048 elements per input stream), per kernel and W. A part's energy per task "
    "is its energy per cycle (PT's hierarchical report of that run, `power_pt_modules.csv`, X60) times the window's "
    "cycles; pJ per element divides it by 2048. forge: csr, ctrl and datapath (the wrapper's three instances), the "
    "total (glue included), and the total without csr; the csr is the csr cell without its `<tag>_peripherals` "
    "child (BUSY_COUNTER, snax-forge D168, X65), which the totals hold. Bambu: ctrl and datapath (X41), the total (glue included). "
    "Vitis dace with a RAM: the RAM apart (X62: the macro's area and its counted accesses x CACTI's energies, or its "
    "flops' area and PT energy) and the logic without it. Vitis opt and XLS: totals only. **Basis (X63):** the HLS "
    "tools take their sizes on plain pins (`loop_count`, `len`, axpy's `alpha`) and have no CSR file, while forge "
    "holds them in `<tag>_csr`, its interface to the cluster; so forge's total without csr is the like-for-like "
    "figure against an HLS total. Integrating any HLS block into the cluster would need a register interface of its "
    "own, which none of these totals contains.")


def parts_table(rows: list[dict], tier: str, kernel: str) -> list[str]:
    """X63: the parts at n2048 of every tool and case of one kernel, W by W."""
    pts = [r for r in rows if r["tech"] == TECH and r["kernel"] == kernel and r["status"] == "ok"
           and r["size"] == "n2048"]
    order = {c: i for i, (_t, c) in enumerate(CASES)}
    lines = ["| W | Case | Part | Area (µm²) | Energy (nJ) | pJ per element |", "|---|---|---|---|---|---|"]

    def add(w, case, part, area, e_pj):
        lines.append(f"| {w} | {LABEL[case]} | {part} | {fmt(area) if area is not None else ''} | "
                     f"{fmt(e_pj / 1000.0) if e_pj is not None else ''} | {fmt(e_pj / 2048.0) if e_pj is not None else ''} |")

    for r in sorted(pts, key=lambda r: (int(r["W"]), order.get(r["case"], 99))):
        w, case, cyc = int(r["W"]), r["case"], int(r["cycles"])
        area, e_run = float(r["area_um2"]), float(r["e_run_pj"])
        num = lambda k: float(r[k]) if r.get(k) not in (None, "") else None  # noqa: E731
        if r["tool"] == "forge":
            parts = {k: (num(f"{k}_um2"), num(f"e_dyn_{k}_pj")) for k in ("csr", "ctrl", "datapath")}
            for k, (a, e) in parts.items():
                add(w, case, k, a, e * cyc if e is not None else None)
            add(w, case, "total", area, e_run)
            a_csr, e_csr = parts["csr"]
            add(w, case, "total without csr", area - a_csr if a_csr is not None else None,
                e_run - e_csr * cyc if e_csr is not None else None)
        elif r["tool"] == "bambu":
            for k in ("ctrl", "datapath"):
                e = num(f"e_dyn_{k}_pj")
                add(w, case, k, num(f"{k}_um2"), e * cyc if e is not None else None)
            add(w, case, "total", area, e_run)
        elif case == "dace" and r.get("ram_kind"):
            a_ram, e_ram = num("ram_um2"), num("e_ram_pj")
            add(w, case, f"RAM ({r['ram_kind']})", a_ram, e_ram)
            add(w, case, "logic without the RAM", area - a_ram, e_run - e_ram)
            add(w, case, "total", area, e_run)
        else:
            add(w, case, "total", area, e_run)
    return lines


def page(tier: str, kernel: str) -> Path:
    return OUT / tier / f"{kernel}.md"


def index() -> list[str]:
    lines = ["| Tier | Kernels |", "|---|---|"]
    for tier in ("done", "untiered"):
        lines.append(f"| {tier} | " + ", ".join(f"[{k}]({tier}/{k}.md)" for k in KERNELS[tier]) + " |")
    return lines


def template_readme() -> str:
    parts = ["# forge and the HLS cases side by side: Vitis opt and dace, Bambu, XLS", "", PERIPHERALS_LINE, "",
             "Generated parts come from `report/compare_hls.py` (`pixi run compare-hls`) and the two tier CSVs "
             "(X45, X46, X61, X64); the text outside the `gen` markers is written by hand. One page per kernel.", "",
             "<!-- gen:index -->", "<!-- /gen -->", "", "## 1. Setup", "", "<!-- gen:setup -->", "<!-- /gen -->", "",
             "## 2. Across all kernels", "", "- (to write)", "", "## 3. Parts at n2048", "",
             "<!-- gen:parts-basis -->", "<!-- /gen -->", "", "## 4. nangate15 check", "", "<!-- gen:tech -->",
             "<!-- /gen -->", "", "## 5. Notes", "",
             "- The rows behind every number are in `results/compare_done.csv` and `results/compare_untiered.csv`.", ""]
    return "\n".join(parts)


def template_page(tier: str, kernel: str) -> str:
    return "\n".join([f"# {kernel} (tier {tier})", "", PERIPHERALS_LINE, "", "Part of [the comparison](../README.md): setup, summary across "
                      "kernels and the parts' basis are there.", "", "<!-- gen:main -->", "<!-- /gen -->", "",
                      "## Insights", "", "- (to write)", "", "## Parts at n2048", "", "<!-- gen:parts -->",
                      "<!-- /gen -->", ""])


def fill(text: str, name: str, body: list[str], where: Path) -> str:
    pat = re.compile(rf"(<!-- gen:{re.escape(name)} -->\n).*?(<!-- /gen -->)", re.S)
    if not pat.search(text):
        raise SystemExit(f"{where.relative_to(ROOT)}: marker gen:{name} is missing")
    return pat.sub(lambda m: m.group(1) + "\n".join(body) + "\n" + m.group(2), text, count=1)


def main() -> int:
    done, untiered = load("done"), load("untiered")
    OUT.mkdir(parents=True, exist_ok=True)
    text = README.read_text() if README.is_file() else template_readme()
    text = fill(text, "index", index(), README)
    text = fill(text, "setup", setup(done + untiered), README)
    text = fill(text, "parts-basis", [PARTS_BASIS], README)
    text = fill(text, "tech", tech_check(done, untiered), README)
    README.write_text(text)
    n = 0
    for tier, rows in (("done", done), ("untiered", untiered)):
        for kernel in KERNELS[tier]:
            md = page(tier, kernel)
            md.parent.mkdir(parents=True, exist_ok=True)
            body = md.read_text() if md.is_file() else template_page(tier, kernel)
            pts = pick(rows, TECH, tier, kernel)
            fig = figure(tier, kernel, pts)
            main_part = [f"![{kernel}]({fig})", "", f"{SIZE[tier][kernel]}, {TECH}, int64, 10 ns.", ""]
            body = fill(body, "main", main_part + table(tier, kernel, pts), md)
            body = fill(body, "parts", parts_table(rows, tier, kernel), md)
            md.write_text(body)
            n += 1
    print(f"compare-hls: {README.relative_to(ROOT)} and {n} kernel pages with their figures in {OUT.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
