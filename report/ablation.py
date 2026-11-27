#!/usr/bin/env python3
"""report/ablation.py - SNAX-GVSoC's dynamic energy against the netlist, one term of the cost model at a time.

    pixi run ablation [--tech nangate45] [--md]

Re-prices each tier A point's committed energy run (ge/<point>.json) over the program window with model_fit.json's
terms, adding one per STEPS: refusals at r_strm and r_xbar of the granted price (D203), the idle floor of the
streamers, crossbar and DMA (D205), the L2 <-> L1 transfers' bank accesses and e_l2 (D204), the copy at the dma
group's e_burst (dma_copy.json) with no crossbar access (X113). Per step, the six parts' total over the netlist's
(energy.json), the pairs PAIRS' changes at both levels, and per kernel the dynamic top-1 and tau-a against the
netlist (tier_check's rules). An energy run already priced with the terms is step `run`: re-pricing it must add
nothing. Writes results/cluster/<tech>/ablation.json; --md prints the tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import model_fit as mf  # noqa: E402
import tier_check as tc  # noqa: E402

STEPS = ("committed", "refusals", "floor", "transfers", "copy")
PAIRS = (("mvt_contiguous_w8", "mvt_padded_w8"), ("bicg_sequential_contiguous_w8", "bicg_pipeline_contiguous_w8"),
         ("mvt_column", "mvt_column_pipeline"), ("bicg_two_pass", "bicg_two_pass_pipeline"))


def steps(ge: dict, marks: set[int], fit: dict, e_burst: float, sh: dict) -> dict[str, dict[str, float]]:
    """The six parts' nJ after each step, cumulative."""
    ws = [w for w in ge["windows"] if w["mark"] in marks]
    e = {p: sum(w["energy"]["parts"].get(p, 0.0) for w in ws) for p in tc.DYN}
    out = {"committed": dict(e)}
    ref = mf.refused(ge, marks)
    e["streamers"] -= (1 - fit["refusal"]["r_strm"]) * ref["streamers_nj"]
    e["crossbar"] -= (1 - fit["refusal"]["r_xbar"]) * ref["crossbar_nj"]
    out["refusals"] = dict(e)
    f = mf.floor_pj(fit["floor"], sh)
    cycles = sum(w["cycles"] for w in ws)
    for p in ("streamers", "crossbar", "dma"):
        e[p] += f[p] * cycles / 1e3
    out["floor"] = dict(e)
    pr = ge["prices"]
    rd, wr = (sum(x) for x in zip(*(mf.l2_accesses(w) for w in ws)))
    e["memory"] += (rd * pr["e_rd"] + wr * pr["e_wr"]) / 1e3
    e["dma"] += (rd + wr) / mf.SUPERBANK * fit["l2"]["e_l2_pj"] / 1e3
    out["transfers"] = dict(e)
    bursts = sum(w["counters"].get("copies", {"reads": 0})["reads"] for w in ws)
    e["dma"] -= bursts * (pr.get("e_dma_burst", 0.0) - e_burst) / 1e3
    e["crossbar"] -= bursts * (pr["e_xbar_ro"] + pr["e_xbar_wo"]) / 1e3
    out["copy"] = dict(e)
    return out


def report(tech: str) -> dict:
    res = ROOT / "results" / "cluster" / tech
    en = json.loads((res / "energy.json").read_text())
    fit = json.loads((res / "model_fit.json").read_text())
    e_burst = json.loads((ROOT / "results" / "snb" / tech / "dma_copy.json").read_text())["engine"]["e_burst_pj"]
    parts = json.loads(tc.GROUPS.read_text())["parts"]
    paper = tc.paper_rows()
    rows = {}
    for p in mf.tier_a(en):
        pt, pid = p["point"], p["point"].removesuffix("_cg")
        if pid not in paper:
            continue
        ge = mf._ge(tech, pt)
        marks = {w["mark"] for w in en[pt]["windows"]}
        nl = mf.program(en, pt, parts)
        st = steps(ge, marks, fit, e_burst, mf.shape_of(tech, paper, pt))
        rows[pid] = {"kernel": tc.kernel_of(pid), "netlist_nj": sum(nl["nj"].values()), "netlist_parts": nl["nj"],
                     "steps": {s: {"nj": sum(v.values()), "parts": v} for s, v in st.items()}}
        for s in rows[pid]["steps"].values():
            s["ratio"] = s["nj"] / rows[pid]["netlist_nj"]
    pairs = {}
    for a, b in PAIRS:
        if a in rows and b in rows:
            pairs[f"{a} -> {b}"] = {"netlist_pct": 100 * (rows[b]["netlist_nj"] / rows[a]["netlist_nj"] - 1),
                                    **{s: 100 * (rows[b]["steps"][s]["nj"] / rows[a]["steps"][s]["nj"] - 1)
                                       for s in STEPS}}
    kernels = {}
    for k in sorted({r["kernel"] for r in rows.values()}):
        ids = [i for i, r in rows.items() if r["kernel"] == k]
        nl = [rows[i]["netlist_nj"] for i in ids]
        kernels[k] = {"netlist_top1": [ids[i] for i in tc.best(nl)]}
        for s in STEPS:
            gv = [rows[i]["steps"][s]["nj"] for i in ids]
            kernels[k][s] = {"top1": [ids[i] for i in tc.best(gv)], "tau": tc.kendall(gv, nl)[0]}
    return {"tech": tech, "steps": list(STEPS), "rows": rows, "pairs": pairs, "kernels": kernels}


def markdown(j: dict) -> str:
    st = j["steps"]
    out = ["SNAX-GVSoC over the netlist, the six parts' dynamic energy over the program window:", "",
           "| design | netlist nJ | " + " | ".join(st) + " |", "|---|---|" + "---|" * len(st)]
    for pid, r in j["rows"].items():
        out.append(f"| `{pid}` | {r['netlist_nj']:.1f} | "
                   + " | ".join(f"{r['steps'][s]['ratio']:.2f}" for s in st) + " |")
    rs = {s: [r["steps"][s]["ratio"] for r in j["rows"].values()] for s in st}
    out.append("| range | | " + " | ".join(f"{min(v):.2f}–{max(v):.2f}" for v in rs.values()) + " |")
    out += ["", "| pair, change % | netlist | " + " | ".join(st) + " |", "|---|---|" + "---|" * len(st)]
    for name, v in j["pairs"].items():
        out.append(f"| {name} | {v['netlist_pct']:+.1f} | " + " | ".join(f"{v[s]:+.1f}" for s in st) + " |")
    out += ["", "| kernel | netlist top-1 | " + " | ".join(f"{s} top-1, τ" for s in st) + " |",
            "|---|---|" + "---|" * len(st)]
    for k, v in j["kernels"].items():
        cells = [f"{', '.join(v[s]['top1'])}, {v[s]['tau']:.2f}" for s in st]
        out.append(f"| {k} | {', '.join(v['netlist_top1'])} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    rep = report(a.tech)
    path = ROOT / "results" / "cluster" / a.tech / "ablation.json"
    path.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: {len(rep['rows'])} designs")
    if a.md:
        print(markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
