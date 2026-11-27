#!/usr/bin/env python3
"""report/model_fit.py - the cost model's terms fitted at gate level: the idle floor, L2 <-> L1 transfers, refusals.

    pixi run model-fit [--tech nangate45] [--md]

From committed results only. The idle floor (X112): each CALIBRATION point's configuration window (energy.json; the
accelerators and the DMA idle) per cycle against the design's shape: the streamers k_s (movers + channels) by least
squares through 0, the crossbar a_x + b_x inputs by least squares, the DMA's mean f_dma. The transfers (X112): the
dma group in the CALIBRATION points' dma_in and dma_out windows less f_dma a cycle, over their beats (the bank
accesses SNAX-GVSoC's energy run counts beyond its priced ones, ge/<point>.json, over the superbank's banks): e_l2;
the banks' energy there over those accesses: e_bank_dma, a DMA access's bank price, a candidate beside CACTI's.
Refusals (X111): REF_PAIR's netlist difference per part less the fitted floor over the extra cycles, over SNAX-GVSoC's
difference in refused requests at the granted price: r_strm, r_xbar, clamped at 0. Checks on tier A (cluster/
points.json, the crossbar's inputs from SNAX_FORGE's paper/data/): the floor per point, e_l2 per point, the refusal pair REF_CHECK,
and the copies' crossbar above its floor (X113). Writes results/cluster/<tech>/model_fit.json; --md prints tables.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "report")]
import dma_copy as dc  # noqa: E402
import tier_check as tc  # noqa: E402

CALIBRATION = ("dot3_w2_cg", "dot3_w4_cg", "dot3_w8_cg", "dot3_w16_cg", "dot3_w32_cg")
REF_PAIR = ("mvt_contiguous_w8_cg", "mvt_padded_w8_cg")  # one netlist, equal grants, refusals the difference
REF_CHECK = ("bicg_pipeline_contiguous_w8_cg", "bicg_sequential_contiguous_w8_cg")
FLOOR_GROUPS = {"streamers": "streamers", "crossbar": "tcdm_interconnect", "dma": "dma"}
TRANSFER = ("dma_in", "dma_out")
SUPERBANK = dc.DMA_BITS // 64  # banks a DMA beat reaches: the port over the L1 bank's width (sram_d512_w64), X96


def _res(tech: str) -> Path:
    return ROOT / "results" / "cluster" / tech


def config_window(en: dict, pt: str) -> dict | None:
    """The point's first configuration window (energy.json's `run` names it), its groups in pJ a cycle; None for a
    pipelined program, whose one window is the program window (D202)."""
    name = en[pt]["run"][0]["idle_window"] if en[pt].get("run") else None
    return next((w for w in en[pt]["windows"] if w["name"] == name), None)


def shape(ge: dict, xbar_inputs: int) -> dict:
    """What the floor counts: the streamers' movers plus their channels (an address generator each, a FIFO each),
    and the crossbar's inputs."""
    mv = ge["prices"]["movers"]
    return {"streamer_units": len(mv) + sum(v["channels"] for v in mv.values()), "xbar_inputs": xbar_inputs}


def fit_floor(en: dict, tech: str) -> dict:
    pts = {}
    for pt in CALIBRATION:
        hw = json.loads((_res(tech) / "hwcost" / f"{pt}.json").read_text())["cost"]
        w = config_window(en, pt)
        pts[pt] = {"shape": shape(_ge(tech, pt), hw["xbar"]["inputs"]),
                   "pj_cycle": {p: w["groups"][g] for p, g in FLOOR_GROUPS.items()}}
    n_s = [p["shape"]["streamer_units"] for p in pts.values()]
    f_s = [p["pj_cycle"]["streamers"] for p in pts.values()]
    n_x = [p["shape"]["xbar_inputs"] for p in pts.values()]
    f_x = [p["pj_cycle"]["crossbar"] for p in pts.values()]
    k_s = sum(n * f for n, f in zip(n_s, f_s)) / sum(n * n for n in n_s)
    mx, my = sum(n_x) / len(n_x), sum(f_x) / len(f_x)
    b_x = sum((n - mx) * (f - my) for n, f in zip(n_x, f_x)) / sum((n - mx) ** 2 for n in n_x)
    f_dma = sum(p["pj_cycle"]["dma"] for p in pts.values()) / len(pts)
    return {"streamers": {"k_pj": k_s}, "crossbar": {"a_pj": my - b_x * mx, "b_pj": b_x}, "dma": {"pj": f_dma},
            "points": pts}


def floor_pj(floor: dict, sh: dict) -> dict:
    """The floor's pJ a cycle per part for a design's shape."""
    return {"streamers": floor["streamers"]["k_pj"] * sh["streamer_units"],
            "crossbar": floor["crossbar"]["a_pj"] + floor["crossbar"]["b_pj"] * sh["xbar_inputs"],
            "dma": floor["dma"]["pj"]}


def l2_accesses(w: dict) -> tuple[int, int]:
    """A SNAX-GVSoC window's bank reads and writes beyond the ones it prices (the grants and the copies' beats): the
    DMA's L2 <-> L1 transfers."""
    banks = w["counters"]["banks"]
    rd = sum(b["reads"] for b in banks) - w["energy"]["counts"]["reads"]
    wr = sum(b["writes"] for b in banks) - w["energy"]["counts"]["writes"]
    return max(rd, 0), max(wr, 0)


def transfer_windows(en: dict, ge: dict, pt: str, f_dma: float) -> dict:
    """The point's dma_in and dma_out windows: beats and the dma group's nJ above f_dma."""
    gw = {w["mark"]: w for w in ge["windows"]}
    acc = nj = banks = 0.0
    for w in en[pt]["windows"]:
        if w["kind"] in TRANSFER:
            acc += sum(l2_accesses(gw[w["mark"]]))
            nj += (w["groups"]["dma"] - f_dma) * w["cycles"] / 1e3
            banks += w["groups"]["tcdm_banks"] * w["cycles"] / 1e3
    beats = acc / SUPERBANK
    return {"beats": beats, "dma_above_floor_nj": nj, "pj": nj * 1e3 / beats if beats else None,
            "accesses": acc, "banks_nj": banks, "bank_pj": banks * 1e3 / acc if acc else None}


def fit_l2(en: dict, tech: str, f_dma: float) -> dict:
    pts = {pt: transfer_windows(en, _ge(tech, pt), pt, f_dma) for pt in CALIBRATION}
    return {"e_l2_pj": sum(p["dma_above_floor_nj"] for p in pts.values()) * 1e3 / sum(p["beats"] for p in pts.values()),
            "e_bank_dma_pj": sum(p["banks_nj"] for p in pts.values()) * 1e3 / sum(p["accesses"] for p in pts.values()),
            "points": pts}


def _ge(tech: str, pt: str) -> dict:
    return json.loads((_res(tech) / "ge" / f"{pt}.json").read_text())


def lane_prices(ge: dict) -> dict[str, tuple[float, float]]:
    """Per mover, a lane's granted price in the streamers and in the crossbar (its input kind, D178)."""
    pr = ge["prices"]
    return {m: (v["e_beat"] / v["channels"], pr["e_xbar_wo"] if v["write"] else pr["e_xbar_ro"])
            for m, v in pr["movers"].items()}


def refused(ge: dict, marks: set[int]) -> dict:
    """Refusals over the windows and their energy at the granted price, per part; grants for the pair check."""
    lp = lane_prices(ge)
    out = {"refusals": 0, "grants": 0, "streamers_nj": 0.0, "crossbar_nj": 0.0}
    for w in ge["windows"]:
        if w["mark"] not in marks:
            continue
        for name, c in w["counters"]["inputs"].items():
            mover = name.split(".lane")[0]
            if mover not in lp:
                continue
            out["refusals"] += c["stalls"]
            out["grants"] += c["grants"]
            out["streamers_nj"] += c["stalls"] * lp[mover][0] / 1e3
            out["crossbar_nj"] += c["stalls"] * lp[mover][1] / 1e3
    return out


def program(en: dict, pt: str, parts: dict) -> dict:
    """The netlist over the program window: cycles and the six parts' dynamic nJ."""
    ws = en[pt]["windows"]
    return {"cycles": sum(w["cycles"] for w in ws),
            "nj": {p: sum(sum(w["groups"][g] for g in parts[p]) * w["cycles"] / 1e3 for w in ws) for p in tc.DYN}}


def shape_of(tech: str, paper: dict, pt: str) -> dict:
    return shape(_ge(tech, pt), int(paper[pt.removesuffix("_cg")]["xbar_inputs"]))


def pair(en: dict, tech: str, a: str, b: str, floor: dict, paper: dict, parts: dict) -> dict:
    """Two points' differences a - b: the netlist's per part, the extra cycles, the floor over them, refusals."""
    na, nb = program(en, a, parts), program(en, b, parts)
    ra, rb = (refused(_ge(tech, p), {w["mark"] for w in en[p]["windows"]}) for p in (a, b))
    f = floor_pj(floor, shape_of(tech, paper, a))
    dc = na["cycles"] - nb["cycles"]
    out = {"points": [a, b], "d_cycles": dc, "d_refusals": ra["refusals"] - rb["refusals"],
           "grants": [ra["grants"], rb["grants"]], "parts": {}}
    for p in ("streamers", "crossbar"):
        d_nl = na["nj"][p] - nb["nj"][p]
        out["parts"][p] = {"d_netlist_nj": d_nl, "d_floor_nj": f[p] * dc / 1e3,
                           "d_granted_nj": ra[f"{p}_nj"] - rb[f"{p}_nj"]}
    out["d_memory_nj"] = na["nj"]["memory"] - nb["nj"]["memory"]
    return out


def fit_refusal(en: dict, tech: str, floor: dict, paper: dict, parts: dict) -> dict:
    fit = pair(en, tech, *REF_PAIR, floor, paper, parts)
    if fit["grants"][0] != fit["grants"][1]:
        raise SystemExit(f"{REF_PAIR}: the grants differ ({fit['grants']}), refusals are not the only difference")
    r = {}
    for p, v in fit["parts"].items():
        raw = (v["d_netlist_nj"] - v["d_floor_nj"]) / v["d_granted_nj"]
        v["raw"] = raw
        r[p] = max(raw, 0.0)
    chk = pair(en, tech, *REF_CHECK, floor, paper, parts)
    for p, v in chk["parts"].items():
        v["model_nj"] = r[p] * v["d_granted_nj"] + v["d_floor_nj"]
    return {"r_strm": r["streamers"], "r_xbar": r["crossbar"], "fit": fit, "check": chk}


def tier_a(en: dict) -> list[dict]:
    pts = json.loads(tc.POINTS.read_text())["points"]
    return [p for p in pts if p["point"] in en and p["point"] not in CALIBRATION]


def checks(en: dict, tech: str, floor: dict, e_l2: float, paper: dict) -> dict:
    """The floor and e_l2 on every tier A point with its own configuration and transfer windows; the copies'
    crossbar above its floor per burst against D184's two accesses."""
    out = {"floor": {}, "l2": {}, "copy_crossbar": {}}
    for p in tier_a(en):
        pt = p["point"]
        if pt.removesuffix("_cg") not in paper:
            continue
        f = floor_pj(floor, shape_of(tech, paper, pt))
        w = config_window(en, pt)
        if w is not None:
            out["floor"][pt] = {q: {"fitted": f[q], "measured": w["groups"][g]} for q, g in FLOOR_GROUPS.items()}
        ge = _ge(tech, pt)
        t = transfer_windows(en, ge, pt, floor["dma"]["pj"])
        if t["beats"]:
            out["l2"][pt] = t
        gw = {x["mark"]: x for x in ge["windows"]}
        for x in en[pt]["windows"]:
            if x["kind"] == "dma_copy":
                bursts = gw[x["mark"]]["counters"]["copies"]["reads"]
                above = (x["groups"]["tcdm_interconnect"] - f["crossbar"]) * x["cycles"]
                out["copy_crossbar"][pt] = {"bursts": bursts, "above_floor_pj_burst": above / bursts,
                                            "d184_pj_burst": ge["prices"]["e_xbar_ro"] + ge["prices"]["e_xbar_wo"]}
    return out


def report(tech: str) -> dict:
    en = json.loads((_res(tech) / "energy.json").read_text())
    parts = json.loads(tc.GROUPS.read_text())["parts"]
    paper = tc.paper_rows()
    floor = fit_floor(en, tech)
    l2 = fit_l2(en, tech, floor["dma"]["pj"])
    return {"tech": tech, "calibration": list(CALIBRATION), "floor": floor, "l2": l2,
            "refusal": fit_refusal(en, tech, floor, paper, parts),
            "check": checks(en, tech, floor, l2["e_l2_pj"], paper)}


def _pct(a: float, b: float) -> str:
    return f"{100 * (a / b - 1):+.0f} %" if b else "–"


def markdown(j: dict) -> str:
    fl, r = j["floor"], j["refusal"]
    out = ["The idle floor (pJ a cycle):", "",
           f"- streamers {fl['streamers']['k_pj']:.4f} a mover or channel; crossbar {fl['crossbar']['a_pj']:.3f} "
           f"+ {fl['crossbar']['b_pj']:.4f} an input; DMA {fl['dma']['pj']:.3f}",
           f"- e_l2 {j['l2']['e_l2_pj']:.2f} pJ a beat, e_bank_dma {j['l2']['e_bank_dma_pj']:.3f} pJ an access; r_strm {r['r_strm']:.4f}, r_xbar {r['r_xbar']:.4f} "
           f"(raw {r['fit']['parts']['crossbar']['raw']:.4f})", "",
           "| point | streamers fitted / measured | crossbar | DMA | e_l2 pJ a beat |", "|---|---|---|---|---|"]
    for pt, v in j["check"]["floor"].items():
        cells = [f"{v[q]['fitted']:.2f} / {v[q]['measured']:.2f} ({_pct(v[q]['fitted'], v[q]['measured'])})"
                 for q in ("streamers", "crossbar", "dma")]
        l2 = j["check"]["l2"].get(pt)
        out.append(f"| `{pt}` | " + " | ".join(cells) + (f" | {l2['pj']:.1f} |" if l2 else " | – |"))
    out += ["", "The refusal check (nJ, a − b):", "", "| part | netlist | model (r × granted + floor) |", "|---|---|---|"]
    for p, v in r["check"]["parts"].items():
        out.append(f"| {p} | {v['d_netlist_nj']:+.2f} | {v['model_nj']:+.2f} |")
    out += ["", "| copy | crossbar above floor, pJ a burst | D184's two accesses |", "|---|---|---|"]
    for pt, v in j["check"]["copy_crossbar"].items():
        out.append(f"| `{pt}` | {v['above_floor_pj_burst']:.2f} | {v['d184_pj_burst']:.2f} |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    rep = report(a.tech)
    path = _res(a.tech) / "model_fit.json"
    path.write_text(json.dumps(rep, indent=1) + "\n")
    print(f"wrote {path.relative_to(ROOT)}")
    if a.md:
        print(markdown(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
