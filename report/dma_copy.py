#!/usr/bin/env python3
"""report/dma_copy.py - the DMA's transposed copy on the gate-level cluster against snax-forge's price (X95).

    pixi run dma-copy [--tech nangate45] [--md]

Per run of results/snb/<tech>/runs.csv whose kernel is dma_transpose, with its PrimePower reports: the run window
(the copy alone) summed into cluster/groups.json's groups as report/cluster_energy.py sums a window, its total
checked against power_pt.csv within 0.01 %. Beside it snax-forge's price of the same copy (D184): N_b = M N bursts,
each a read and a write on every bank of its superbank (DMA_BITS over the bank's width; results/ram/<tech>/
ram_table.csv's bank of the config's L1 macros) and two crossbar accesses at a full crossbar's e_access on the banks
(results/strm/<tech>/xbar.csv) less the read-only and the write-only saving (xbar_kinds.json's energy at that bank
count). Then the engine's price per burst (X113): the dma group's energy less its idle floor (the group in a clock-gated
cluster's configuration window, the accelerators and the DMA idle: IDLE_POINT's IDLE_WINDOW in results/cluster/<tech>/
energy.json, the floor report/model_fit.py fits), per burst, and its mean over the runs, e_burst_pj. Writes results/snb/<tech>/dma_copy.json; --md prints the tables.
Standard library and arc/arc.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "arc"), str(ROOT / "report")]
import arc  # noqa: E402
import cluster_energy as ce  # noqa: E402

GROUPS = ROOT / "cluster" / "groups.json"
ENGINE = ("dma",)  # the DMA part a copy drives beyond D184's banks; the AXI is in the rest at gate level
IDLE_POINT, IDLE_WINDOW = "dot3_w8_cg", "4_acc_config"  # the engine's idle floor: accelerators and DMA idle
POINTS = ROOT / "cluster" / "snb_points.json"
KERNEL = "dma_transpose"
BANK = re.compile(r"sram_d(\d+)_w(\d+)")
# groups.json's groups D184 prices: the banks, and the paths a copy takes to them as the crossbar part
PRICED = {"tcdm_banks": "banks", "dma": "crossbar", "tcdm_interconnect": "crossbar"}
# The DMA's port into L1 (snax_cluster's dma_data_width): a burst reaches every bank of its superbank (D184, X96)
DMA_BITS = 512


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def l1_bank(config: dict) -> tuple[int, int, int]:
    """The config's L1 macros: (count, depth, width), the most numerous sram of its list."""
    name, n = max(config["srams"].items(), key=lambda kv: kv[1])
    m = BANK.match(name)
    if not m:
        raise SystemExit(f"{config['config']}: {name} is not sram_d<depth>_w<width>")
    return n, int(m.group(1)), int(m.group(2))


def d184_price(bursts: int, banks: int, depth: int, width: int, tech: str) -> dict:
    """D184's price of a copy of `bursts` bursts (nJ): a read and a write on each bank of a burst's superbank, and its
    crossbar accesses."""
    ram = [r for r in read_csv(ROOT / "results" / "ram" / tech / "ram_table.csv")
           if int(r["depth"]) == depth and int(r["width"]) == width]
    xbar = [r for r in read_csv(ROOT / "results" / "strm" / tech / "xbar.csv")
            if int(r["inputs"]) == banks and int(r["banks"]) == banks]
    kinds = json.loads((ROOT / "results" / "strm" / tech / "xbar_kinds.json").read_text())["energy"]["by_banks"]
    if len(ram) != 1 or len(xbar) != 1 or str(banks) not in kinds:
        raise SystemExit(f"no bank {depth} x {width} or no crossbar at {banks} banks in the {tech} tables")
    e_rd, e_wr = float(ram[0]["e_rd_pj"]), float(ram[0]["e_wr_pj"])
    e_acc = float(xbar[0]["e_access_pj"])
    e_ro, e_wo = e_acc * (1 - kinds[str(banks)]["g_ro"]), e_acc * (1 - kinds[str(banks)]["g_wo"])
    sb = DMA_BITS // width
    out = {"bursts": bursts, "superbank_banks": sb, "e_rd_pj": e_rd, "e_wr_pj": e_wr, "e_ro_pj": e_ro, "e_wo_pj": e_wo,
           "banks_nj": bursts * sb * (e_rd + e_wr) / 1e3, "crossbar_nj": bursts * (e_ro + e_wo) / 1e3}
    out["nj"] = out["banks_nj"] + out["crossbar_nj"]
    return out


def run_copy(row: dict, pts: dict, cfg: dict, tech: str) -> dict | None:
    """One run's run window in groups against D184's price; None without its reports."""
    rep = ROOT / "results" / "snb" / tech / "power_reports" / f"{row['run']}.zip"
    if not rep.is_file():
        return None
    win = next((w for w in json.loads(arc.read_text(rep, "windows.json")) if w["kind"] == "run"), None)
    if win is None:
        raise SystemExit(f"{row['run']}: no run window in its windows.json")
    pt = next((r for r in read_csv(ROOT / "results" / "snb" / tech / "power_pt.csv")
               if r["point"] == row["run"] and int(r["mark"]) == int(win["mark"])), None)
    clock_ns = float(pt["clock_ns"]) if pt else 10.0
    rows = ce.parse_hierarchy(arc.read_text(rep, f"{win['mark']}_{win['kind']}/power_hierarchy.rpt", errors="replace"))
    c = int(win["cycles"])
    groups = {k: v * c / 1e3 for k, v in ce.window_groups(rows, cfg, clock_ns).items()}
    top = ce.pj_per_cycle(rows[0]["total"], clock_ns)
    want = float(pt["e_dyn_pj"]) if pt else None
    config = next(x for x in pts["configs"] if x["config"] == row["config"])
    sizes = dict(kv.split("=") for kv in row["sizes"].split())
    n, depth, width = l1_bank(config)
    price = d184_price(int(sizes["M"]) * int(sizes["N"]), n, depth, width, tech)
    nj = top * c / 1e3
    measured = {p: sum(v for g, v in groups.items() if PRICED.get(g) == p) for p in ("banks", "crossbar")}
    return {"run": row["run"], "type": row["type"], "sizes": sizes, "cycles": c, "nj": nj,
            "check": {"power_pt_e_dyn_pj": want, "ok": want is not None and abs(top - want) <= ce.TOL_PCT / 100 * want},
            "groups": groups, "d184": price,
            "against": {"banks": {"measured_nj": measured["banks"], "d184_nj": price["banks_nj"]},
                        "crossbar": {"measured_nj": measured["crossbar"], "d184_nj": price["crossbar_nj"]},
                        "not_priced_nj": nj - measured["banks"] - measured["crossbar"],
                        "ratio": nj / price["nj"] if price["nj"] else None}}


def idle_floor(tech: str) -> dict:
    """pJ per cycle of each ENGINE group in IDLE_POINT's IDLE_WINDOW, the DMA idle."""
    e = json.loads((ROOT / "results" / "cluster" / tech / "energy.json").read_text())
    w = next(x for x in e[IDLE_POINT]["windows"] if x["name"] == IDLE_WINDOW)
    return {g: w["groups"][g] for g in ENGINE}


def e_burst(run: dict, floor: dict) -> dict:
    """The engine's pJ per burst in one run: each ENGINE group's window energy less its floor over the window."""
    n, c = run["d184"]["bursts"], run["cycles"]
    per = {g: (run["groups"][g] * 1e3 - c * floor[g]) / n for g in ENGINE}
    return {**{f"{g}_pj": v for g, v in per.items()}, "pj": sum(per.values())}


def report(tech: str) -> dict:
    pts = json.loads(POINTS.read_text())
    cfg = json.loads(GROUPS.read_text())
    out = {"tech": tech, "labels": {g["name"]: g["label"] for g in cfg["groups"]}, "runs": {}}
    for row in read_csv(ROOT / "results" / "snb" / tech / "runs.csv"):
        if row["kernel"] != KERNEL or row.get("rtl_status") != "PASS":
            continue
        r = run_copy(row, pts, cfg, tech)
        if r is not None:
            out["runs"][row["run"]] = r
    if out["runs"]:
        floor = idle_floor(tech)
        for r in out["runs"].values():
            r["e_burst"] = e_burst(r, floor)
        out["engine"] = {"groups": list(ENGINE), "idle": {"point": IDLE_POINT, "window": IDLE_WINDOW,
                                                           "pj_cycle": floor},
                         "e_burst_pj": sum(r["e_burst"]["pj"] for r in out["runs"].values()) / len(out["runs"])}
    return out


def _e(x: float | None, nd: int = 2) -> str:
    return "" if x is None else f"{x:,.{nd}f}"


def markdown(rep: dict) -> str:
    runs = list(rep["runs"].values())
    if not runs:
        return "No dma_transpose run with power reports yet.\n"
    out = ["The copy's run window (nJ, internal + switching), per group:", "",
           "| group | " + " | ".join(r["run"] for r in runs) + " |", "|---|" + "---|" * len(runs)]
    out += [f"| {lab} | " + " | ".join(_e(r["groups"][g]) for r in runs) + " |" for g, lab in rep["labels"].items()]
    out += ["| total | " + " | ".join(_e(r["nj"]) for r in runs) + " |",
            "| cycles | " + " | ".join(str(r["cycles"]) for r in runs) + " |", "",
            "Against D184's price of the same copy (nJ):", "",
            "| | " + " | ".join(r["run"] for r in runs) + " |", "|---|" + "---|" * len(runs)]
    for part, groups in (("banks", "tcdm_banks"), ("crossbar", "dma + tcdm_interconnect")):
        out += [f"| {part}, measured ({groups}) | " + " | ".join(_e(r["against"][part]["measured_nj"]) for r in runs)
                + " |", f"| {part}, D184 | " + " | ".join(_e(r["against"][part]["d184_nj"]) for r in runs) + " |"]
    out += ["| not priced (the rest) | " + " | ".join(_e(r["against"]["not_priced_nj"]) for r in runs) + " |",
            "| measured / D184 | " + " | ".join(_e(r["against"]["ratio"]) for r in runs) + " |", "",
            f"The engine per burst ({', '.join(ENGINE)} less their idle floor, pJ):", "",
            "| | " + " | ".join(r["run"] for r in runs) + " |", "|---|" + "---|" * len(runs)]
    out += [f"| {g} | " + " | ".join(_e(r["e_burst"][f"{g}_pj"]) for r in runs) + " |" for g in ENGINE]
    out += ["| e_burst | " + " | ".join(_e(r["e_burst"]["pj"]) for r in runs) + " |", "",
            f"Mean e_burst: {rep['engine']['e_burst_pj']:.2f} pJ."]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    rep = report(a.tech)
    path = ROOT / "results" / "snb" / a.tech / "dma_copy.json"
    path.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: {len(rep['runs'])} runs")
    bad = [r["run"] for r in rep["runs"].values() if not r["check"]["ok"]]
    if a.md:
        print(markdown(rep))
    if bad:
        print(f"the run window's total differs from power_pt.csv: {bad}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
