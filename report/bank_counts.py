#!/usr/bin/env python3
"""report/bank_counts.py - the TCDM banks' reads and writes counted from each window's SAIF, at CACTI's prices.

    pixi run bank-counts [--tech nangate45] [--points A,B,...] [--md]

Averaged PrimePower takes a macro's req_i and we_i as independent and under-counts its writes (PITFALLS PT7). A bank
writes only with req_i high (tc_sram), so per bank and window the SAIF's time at 1 counts exactly: writes =
T1(we_i) / t_clk, reads = (T1(req_i) - T1(we_i)) / t_clk (X114). Per point of energy.json, every window's SAIF
(pwr/<mark>_<kind>/w.saif of sim/runs/cluster/<tech>/<point>.zip, read from the zip): the bank instances are the
innermost instances under BANK_PATH with both nets, as many as the point's TCDM macros (cluster/points.json). Their
energy is reads x e_rd + writes x e_wr of the bank's ram_table.csv row, beside PT's tcdm_banks group. Writes
results/cluster/<tech>/bank_counts.json; --md prints a table. Needs the run zips (the server).
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

BANK_PATH = re.compile(r"(^|/)i_snitch_data_mem/")  # groups.json's tcdm_banks rule
BANK_MACRO = re.compile(r"sram_d(\d+)_w(\d+)(_m\d+)?$")
CLOCK_NS = 10.0
NETS = {"req_i": ("req_i", "req_i[0]"), "we_i": ("we_i", "we_i[0]")}
TOL_CYCLES = 0.01  # a count off an integer number of cycles by more than this is a broken SAIF


def saif_t1(text: str) -> tuple[float, dict[str, dict[str, int]]]:
    """The SAIF's time unit (s) and per instance path (from its top, escapes dropped) the T1 of req_i and we_i."""
    ts = re.search(r"\(TIMESCALE\s+(\d+)\s*(\w+)\)", text)
    unit = int(ts.group(1)) * {"s": 1, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}[ts.group(2).lower()]
    want = {alias: name for name, aliases in NETS.items() for alias in aliases}
    toks = re.findall(r"\(|\)|[^\s()]+", text)
    out: dict[str, dict[str, int]] = {}
    path: list[str] = []
    stack: list[str | None] = []
    i = 0
    while i < len(toks):
        tk = toks[i]
        if tk == "(":
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            if nxt == "INSTANCE":
                path.append(toks[i + 2].replace("\\", ""))
                stack.append("inst")
                i += 3
                continue
            name = nxt.replace("\\", "")
            if name in want and i + 2 < len(toks) and toks[i + 2] == "(":
                j = i + 2
                while j + 3 < len(toks) and toks[j] == "(" and toks[j + 1] in ("T0", "T1", "TX", "TZ", "TC", "IG"):
                    if toks[j + 1] == "T1":
                        out.setdefault("/".join(path), {})[want[name]] = int(toks[j + 2])
                    j += 4
            stack.append(None)
        elif tk == ")":
            if stack and stack.pop() == "inst":
                path.pop()
        i += 1
    return unit, out


def banks(t1: dict[str, dict[str, int]]) -> dict[str, dict[str, int]]:
    """The innermost instances under BANK_PATH with both nets: one per macro (the wrappers above pass the nets on)."""
    both = {p: v for p, v in t1.items() if BANK_PATH.search(p + "/") and set(v) == set(NETS)}
    return {p: v for p, v in both.items() if not any(q != p and q.startswith(p + "/") for q in both)}


def count(text: str) -> dict:
    """One window's reads, writes and bank count."""
    unit, t1 = saif_t1(text)
    per = banks(t1)
    cyc = CLOCK_NS * 1e-9 / unit
    reads = writes = 0
    for p, v in per.items():
        wr, rq = v["we_i"] / cyc, v["req_i"] / cyc
        for n in (wr, rq):
            if abs(n - round(n)) > TOL_CYCLES:
                raise SystemExit(f"{p}: {n} cycles is not a whole number; check the SAIF's clock and timescale")
        if round(wr) > round(rq):
            raise SystemExit(f"{p}: we_i high on {round(wr)} cycles, req_i on {round(rq)}: we_i is not gated by req_i")
        writes += round(wr)
        reads += round(rq) - round(wr)
    return {"banks": len(per), "reads": reads, "writes": writes}


def bank_price(macro: str, tech: str) -> tuple[float, float]:
    d, w, _ = BANK_MACRO.search(macro).groups()
    for r in csv.DictReader((ROOT / "results" / "ram" / tech / "ram_table.csv").open()):
        if r["depth"] == d and r["width"] == w:
            return float(r["e_rd_pj"]), float(r["e_wr_pj"])
    raise SystemExit(f"{macro}: no {d} x {w} row in ram_table.csv")


def tcdm_macro(point: dict) -> tuple[str, int]:
    """The point's TCDM bank macro and its count: the most numerous of its srams."""
    name, n = max(point["srams"].items(), key=lambda kv: kv[1])
    return name, n


def report(tech: str, only: set[str] | None = None) -> dict:
    res = ROOT / "results" / "cluster" / tech
    en = json.loads((res / "energy.json").read_text())
    pts = {p["point"]: p for p in json.loads((ROOT / "cluster" / "points.json").read_text())["points"]}
    out = {"tech": tech, "clock_ns": CLOCK_NS, "points": {}}
    for pt in sorted(en):
        if (only and pt not in only) or pt not in pts:
            continue
        z = ROOT / "sim" / "runs" / "cluster" / tech / f"{pt}.zip"
        if not z.is_file():
            print(f"  {pt}: no {z.relative_to(ROOT)}, skipped", flush=True)
            continue
        macro, n_banks = tcdm_macro(pts[pt])
        e_rd, e_wr = bank_price(macro, tech)
        wins, tot = {}, {"reads": 0, "writes": 0, "counted_nj": 0.0, "pt_nj": 0.0}
        for w in en[pt]["windows"]:
            name = f"{w['mark']}_{w['kind']}"
            c = count(arc.read_text(z, f"pwr/{name}/w.saif"))
            if c["banks"] != n_banks:
                raise SystemExit(f"{pt} {name}: {c['banks']} bank instances in the SAIF, {n_banks} {macro} in points.json")
            c["counted_nj"] = (c["reads"] * e_rd + c["writes"] * e_wr) / 1e3
            c["pt_nj"] = w["groups"]["tcdm_banks"] * w["cycles"] / 1e3
            wins[name] = c
            for k in tot:
                tot[k] += c[k]
        out["points"][pt] = {"macro": macro, "e_rd_pj": e_rd, "e_wr_pj": e_wr, "windows": wins, "total": tot}
        print(f"  {pt}: {tot['reads']} reads, {tot['writes']} writes, {tot['counted_nj']:.2f} nJ counted, "
              f"{tot['pt_nj']:.2f} nJ PT", flush=True)
    return out


def markdown(j: dict) -> str:
    out = ["| point | reads | writes | counted nJ | PT nJ | PT / counted |", "|---|---|---|---|---|---|"]
    for pt, v in j["points"].items():
        t = v["total"]
        out.append(f"| `{pt}` | {t['reads']} | {t['writes']} | {t['counted_nj']:.2f} | {t['pt_nj']:.2f} | "
                   f"{t['pt_nj'] / t['counted_nj']:.3f} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--points", help="comma-separated points (default: every point of energy.json)")
    ap.add_argument("--md", action="store_true", help="also print the table as Markdown")
    a = ap.parse_args()
    rep = report(a.tech, set(a.points.split(",")) if a.points else None)
    path = ROOT / "results" / "cluster" / a.tech / "bank_counts.json"
    old = json.loads(path.read_text()) if path.is_file() else {"points": {}}
    if a.points:  # a partial run adds to what is there
        rep["points"] = {**old["points"], **rep["points"]}
    path.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}: {len(rep['points'])} points")
    if a.md:
        print(markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
