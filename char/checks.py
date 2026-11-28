#!/usr/bin/env python3
"""char/checks.py - the checks on the blocks alone, as Markdown tables for a run note.

  pixi run python char/checks.py [--tech T ...]            synthesis
  pixi run python char/checks.py --power [--tech T ...]    power (results/char/<tech>/char_power.csv)
  pixi run python char/checks.py --bank [--tech T ...]     the Mac bank's study (X97)

Read from the committed CSVs (char_synth.csv, char_synth_modules.csv, char_power.csv, and the forge points'
synth_dc_modules.csv and power_pt_modules.csv) and the local bundle zips; none is a gate. Synthesis: each block's
RTL against the same file in the forge bundles, each point alone against the same cell inside the forge points,
the lane copies, the flop area and each point's flops against its register bits (the packer's
(d_out - 1) w + ceil(log2 d_out)), a clock gate counted as a sequential cell. Power: the registered blocks' idle e_bit and its mean e_hold, LinkBuffer's
depth sweep against 64 e_hold, the lane copies, the folds against W, and busy alone against inside the forge
points. The bank's study: per point its area, sequential cells against lanes * 32 * rows and energy per fire, then
its extra over the rows-1 base at the same W split into the registers the flops formula counts and the rest, and
one-constant forms of the rest in R and W fitted over the 8 bank points. Standard library and arc/arc.py only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "arc"))
import arc  # noqa: E402  the bundles are zips

TECHS = ("nangate45",)
SLOPE_MIN = 0.7      # a LinkBuffer slope ratio below this calls for R2's diagnostic (not a gate)
LANE_SERIES = {"SimdLanes add": "lanes/add_w{}", "SimdLanes mul": "lanes/mul_w{}",
               "Mac acc": "mac/acc_w{}", "LinkBuffer d1": "link/d1_w{}"}


def rows(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def table(head: list[str], body: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(str(x) for x in r) + " |" for r in body]
    return "\n".join(out)


def f2(x: float) -> str:
    return f"{x:.2f}"


def rtl_table() -> str:
    body = []
    forge = sorted((ROOT / "rtl" / "forge").glob("done/*/*.zip"))
    for z in sorted((ROOT / "rtl" / "char").rglob("*.zip")):
        if not arc.has(z, "emitted.json"):
            continue
        point = z.relative_to(ROOT / "rtl" / "char").with_suffix("").as_posix()
        top = json.loads(arc.read(z, "emitted.json"))["top"]
        mine = arc.read(z, f"sv/{top}.sv")
        same, differ = [], []
        for f in forge:
            if arc.has(f, f"rtl/sv/{top}.sv"):
                b = f.relative_to(ROOT / "rtl" / "forge" / "done").with_suffix("").as_posix()
                (same if arc.read(f, f"rtl/sv/{top}.sv") == mine else differ).append(b)
        body.append([point, f"`{top}`", ", ".join(same) or "-", ", ".join(differ) or "-"])
    return table(["point", "top", "identical in", "differs in"], body)


def subtree(mods: list[dict], path: str, col: str) -> float:
    return sum(float(m[col]) for m in mods if m["path"] == path or m["path"].startswith(path + "/"))


def inside_table(tech: str, char: list[dict]) -> str:
    forge = rows(ROOT / "results" / "forge" / tech / "synth_dc_modules.csv")
    by_point: dict[str, list[dict]] = {}
    for m in forge:
        by_point.setdefault(m["point"], []).append(m)
    body, none = [], []
    for r in char:
        top, a, c, s = r["top"], float(r["area_um2"]), float(r["comb_area_um2"]), float(r["seq_area_um2"])
        hits = [m for m in forge if re.fullmatch(rf"{re.escape(top)}(_\d+)?", m["design"])]
        if not hits:
            none.append(r["point"])
            continue
        for m in hits:
            mods = by_point[m["point"]]
            ia = float(m["area_um2"])
            ic, is_ = subtree(mods, m["path"], "comb_um2"), subtree(mods, m["path"], "seq_um2")
            body.append([r["point"], m["point"].removeprefix("done/"), f2(a), f2(ia), f2(a - ia),
                         f"{100 * (a - ia) / ia:+.2f}", f2(c), f2(ic), f2(s), f2(is_)])
    head = ["point", "inside", "area alone", "area inside", "diff um2", "diff %", "comb alone", "comb inside",
            "seq alone", "seq inside"]
    return table(head, body) + "\n\nNo forge counterpart: " + (", ".join(f"`{p}`" for p in none) or "none") + "."


def lanes_table(char: list[dict]) -> str:
    area = {r["point"]: float(r["area_um2"]) for r in char}
    body = []
    for name, pat in LANE_SERIES.items():
        a1 = area.get(pat.format(1))
        cells = [name, f2(a1) if a1 else "-"]
        for w in (8, 32):
            aw = area.get(pat.format(w))
            cells += [f2(aw) if aw else "-", f"{aw / (w * a1):.4f}" if aw and a1 else "-"]
        body.append(cells)
    return table(["block", "area(1)", "area(8)", "ratio at 8", "area(32)", "ratio at 32"], body)


def flops_table(char: list[dict]) -> str:
    body, per = [], set()
    for r in char:
        n = int(r["seq_cells"] or 0)
        if n:
            x = float(r["seq_area_um2"]) / n
            per.add(round(x, 4))
            body.append([r["point"], r["seq_cells"], r["seq_area_um2"], f"{x:.4f}"])
    return (table(["point", "seq_cells", "seq_area_um2", "per flop um2"], body)
            + f"\n\nDistinct values: {', '.join(f'{x:.4f}' for x in sorted(per))}.")


def width(t: str) -> int:
    return int(t.removeprefix("u").removeprefix("int"))


def n_bits(datapath: str, params: dict) -> int:
    """A block's register bits from its params (its Chisel source's registers)."""
    w = params.get("lanes", 1)
    if datapath == "SimdLanes":
        return 0
    if datapath == "Mac":                          # a bank (D191): its R rows of sums
        reg = params["accumulate"] or params["regOut"]
        return w * width(params["outType"]) * params.get("rows", 1) if reg else 0
    if datapath in ("TreeAccumulate", "SerialAccumulate"):
        return width(params["outType"])
    if datapath == "LinkBuffer":
        return w * params["depth"] * width(params["dtype"])
    if datapath == "HaloLink":                     # H = ceil((T - 1) / W) held beats (snax-forge D206)
        return (params["taps"] + w - 2) // w * w * width(params["dtype"])
    if datapath == "FifoPacker":                   # the held slots and the slice counter
        chunk = params["inLanes"] * width(params["laneType"])
        r = params["words"] * 64 // chunk
        return (r - 1) * chunk + (r - 1).bit_length()
    if datapath == "FifoSlicer":                   # the held word, the pop counter and the full flag
        r = params["words"] * 64 // (params["outLanes"] * width(params["laneType"]))
        return params["words"] * 64 + (r - 1).bit_length() + 1
    raise KeyError(f"{datapath}: no register rule")


def gating(tech: str, r: dict) -> tuple[int, int] | None:
    """(registers, clock gates) from the row's clock_gating.rpt in its report zip, None without one."""
    z = ROOT / "results" / "char" / tech / "reports" / f"{r['point']}{'_cg' if r.get('clk_gate') == '1' else ''}.zip"
    if not z.is_file() or not arc.has(z, "clock_gating.rpt"):
        return None
    text = arc.read(z, "clock_gating.rpt")
    text = text.decode() if isinstance(text, bytes) else text
    regs = re.search(r"Total number of registers\s*\|\s*(\d+)", text)
    gates = re.search(r"Number of Clock gating elements\s*\|\s*(\d+)", text)
    return (int(regs.group(1)), int(gates.group(1))) if regs and gates else None


def bits_table(tech: str, char: list[dict]) -> str:
    """Each point's sequential cells against its register bits: DC's registers (clock_gating.rpt) equal to the bits,
    and seq_cells the registers plus the clock gates."""
    params = {p["point"]: (p["datapath"], p["params"]) for p in json.loads((ROOT / "char" / "points.json").read_text())}
    body, off = [], []
    for r in char:
        if r["point"] not in params:
            continue
        want = n_bits(*params[r["point"]])
        g = gating(tech, r)
        cells = int(r["seq_cells"] or 0)
        ok = g is not None and g[0] == want and cells == g[0] + g[1]
        if not ok:
            off.append(r["point"])
        body.append([r["point"], r.get("in_type", ""), r.get("out_type", ""), want, g[0] if g else "-",
                     g[1] if g else "-", cells, "yes" if ok else "**no**"])
    return (table(["point", "in", "out", "bits", "DC registers", "clock gates", "seq_cells", "as expected"], body)
            + "\n\nNot as expected: " + (", ".join(f"`{p}`" for p in off) or "none") + ".")


def pct(a: float, b: float) -> str:
    return f"{100 * (a - b) / b:+.2f}" if b else "-"


def fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least squares y = m x + c: (m, c, the largest residual in % of y)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    c = my - m * mx
    return m, c, max(abs(y - (m * x + c)) / y * 100 for x, y in zip(xs, ys))


BANK_BASE = {4: "mac/acc_w4_i8_i32", 8: "mac/acc_w8_i8_i32"}     # the rows-1 base at each W (X97)
BANK_RS = (2, 4, 8, 16)
BANK_MUX2 = {"mac/bank_r16_w8_i8_i32"}  # DC mapped its two read muxes to MUX2 trees, the others to AOI logic (X97)
LOG2 = lambda r: (r - 1).bit_length()  # noqa: E731  log2 R at a power of 2
BANK_FORMS = {"W R": lambda w, r: [w * r], "W (a R + b)": lambda w, r: [w * r, w],
              "W (R - 1)": lambda w, r: [w * (r - 1)], "W log2 R": lambda w, r: [w * LOG2(r)],
              "W (a log2 R + b)": lambda w, r: [w * LOG2(r), w]}


def lsq(xs: list[list[float]], ys: list[float]) -> list[float]:
    """Least squares y = k . x without an intercept, one or two terms (the normal equations)."""
    if len(xs[0]) == 1:
        return [sum(x[0] * y for x, y in zip(xs, ys)) / sum(x[0] ** 2 for x in xs)]
    a = [[sum(x[i] * x[j] for x in xs) for j in (0, 1)] for i in (0, 1)]
    b = [sum(x[i] * y for x, y in zip(xs, ys)) for i in (0, 1)]
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    return [(b[0] * a[1][1] - b[1] * a[0][1]) / det, (a[0][0] * b[1] - a[1][0] * b[0]) / det]


def bank_model(tech: str) -> dict | None:
    """The bank's two forms (X97) as char.json's `bank` (snax-forge D193), from the gated rows: the area beyond the
    extra flops per lane and row, the energy a fire over the rows-1 base per lane as a log2 R + b, and the largest
    read mux (W 32 R bits) they were fitted to (DC builds a larger one otherwise, PITFALLS DC20). None without them."""
    gated = lambda r: r.get("clk_gate", "") == "1"  # noqa: E731
    synth = {r["point"]: r for r in rows(ROOT / "results" / "char" / tech / "char_synth.csv") if gated(r)}
    busy = {r["point"]: r for r in rows(ROOT / "results" / "char" / tech / "char_power.csv")
            if gated(r) and r["window"] == "busy"}
    a_flop = json.loads((ROOT / "results" / "char" / tech / "char.json").read_text())["flop"]["area_um2"]
    pts = [(w, r, f"mac/bank_r{r}_w{w}_i8_i32") for w in BANK_BASE for r in BANK_RS]
    pts = [(w, r, q) for w, r, q in pts if q not in BANK_MUX2]
    if any(q not in synth or q not in busy for _, _, q in pts) or any(b not in busy for b in BANK_BASE.values()):
        return None
    area, energy = [], []
    for w, r, q in pts:
        b = BANK_BASE[w]
        area.append(float(synth[q]["area_um2"]) - float(synth[b]["area_um2"]) - w * 32 * (r - 1) * a_flop)
        energy.append(float(busy[q]["e_dyn_pj"]) - float(busy[b]["e_dyn_pj"]))
    (k,) = lsq([BANK_FORMS["W R"](w, r) for w, r, _ in pts], area)
    e = lsq([BANK_FORMS["W (a log2 R + b)"](w, r) for w, r, _ in pts], energy)
    return {"comb_um2_lane_row": round(k, 4), "e_pj_lane_log2_rows": round(e[0], 5), "e_pj_lane": round(e[1], 5),
            "mux_bits_max": max(w * 32 * r for w, r, _ in pts)}


def bank_tables(tech: str) -> str:
    """The Mac bank's study (X97) on the gated rows: the points, the extra over the base, the forms of the rest."""
    gated = lambda r: r.get("clk_gate", "") == "1"  # noqa: E731
    synth = {r["point"]: r for r in rows(ROOT / "results" / "char" / tech / "char_synth.csv") if gated(r)}
    power: dict = {}
    for r in rows(ROOT / "results" / "char" / tech / "char_power.csv"):
        if gated(r):
            power.setdefault(r["point"], {})[r["window"]] = r
    flop = json.loads((ROOT / "results" / "char" / tech / "char.json").read_text())["flop"]
    a_flop, e_load = flop["area_um2"], flop["e_load_fj"] / 1000
    pts = [(w, 1, BANK_BASE[w]) for w in BANK_BASE] + [(w, r, f"mac/bank_r{r}_w{w}_i8_i32")
                                                       for w in BANK_BASE for r in BANK_RS]
    missing = [p for _, _, p in pts if p not in synth or sorted(power.get(p, {})) != ["busy", "idle"]]
    if missing:
        return f"{tech}: no gated synthesis or power rows for {missing}"
    v = {}
    for w, r, p in pts:
        s, b, i = synth[p], power[p]["busy"], power[p]["idle"]
        v[w, r] = {"point": p, "area": float(s["area_um2"]), "comb": float(s["comb_area_um2"]),
                   "seq": float(s["seq_area_um2"]), "cells": int(s["seq_cells"]), "flops": w * 32 * r,
                   "e": float(b["e_dyn_pj"]), "e_flop": float(b["e_flop_pj"]), "e_comb": float(b["e_comb_pj"]),
                   "idle": float(i["e_dyn_pj"]), "status": [s["status"], b["status"], i["status"]]}
    out = [f"## {tech}: the Mac bank's points (X97; int8 in, int32 out; energy per fire = busy e_dyn)\n"]
    body = []
    for (w, r), x in sorted(v.items()):
        est_a = x["comb"] if r == 1 else v[w, 1]["comb"]
        est_e = v[w, 1]["e_comb"] + x["flops"] * e_load
        body.append([f"`{x['point']}`", w, r, f2(x["area"]), f2(x["comb"]), f2(x["seq"]), x["cells"], x["flops"],
                     x["cells"] - x["flops"], f"{x['e']:.4f}", f"{x['e_flop']:.4f}", f"{x['e_comb']:.4f}",
                     f"{x['idle']:.4f}", f2(est_a + x["flops"] * a_flop), f"{est_e:.4f}"])
    out.append(table(["point", "W", "R", "area", "comb", "seq", "seq cells", "flops W 32 R", "cells - flops",
                      "e/fire", "e_flop", "e_comb", "idle/cycle", "estimate area", "estimate e/fire"], body))
    out.append(f"\n## {tech}: the bank's extra over the rows-1 base at the same W (registers: W 32 (R - 1) x "
               f"{a_flop} um2, x e_load {flop['e_load_fj']} fJ)\n")
    body, rest = [], {"area rest": [], "comb area": [], "e/fire": [], "e_comb": [], "e_flop": []}
    for w in BANK_BASE:
        b0 = v[w, 1]
        for r in BANK_RS:
            x = v[w, r]
            df = x["flops"] - b0["flops"]
            da, de = x["area"] - b0["area"], x["e"] - b0["e"]
            ra, re_ = da - df * a_flop, de - df * e_load
            for k, y in (("area rest", ra), ("comb area", x["comb"] - b0["comb"]), ("e_comb", x["e_comb"] - b0["e_comb"]),
                         ("e_flop", x["e_flop"] - b0["e_flop"]), ("e/fire", de)):
                rest[k].append((w, r, y))
            body.append([w, r, df, f2(da), f2(df * a_flop), f2(ra), f2(x["seq"] - b0["seq"]), f2(x["comb"] - b0["comb"]),
                         f"{de:.4f}", f"{df * e_load:.4f}", f"{re_:.4f}", f"{x['e_flop'] - b0['e_flop']:.4f}",
                         f"{x['e_comb'] - b0['e_comb']:.4f}"])
    out.append(table(["W", "R", "extra flops", "d area", "registers (formula)", "rest", "d seq", "d comb",
                      "d e/fire", "registers (formula)", "rest", "d e_flop", "d e_comb"], body))
    out.append(f"\n## {tech}: forms of the extra in R and W, fitted over the bank points DC mapped to AOI logic "
               f"(all but {', '.join(sorted(BANK_MUX2))}); the largest and rms residual in % of the value, and the "
               f"MUX2 point against the form\n")
    body = []
    for k, ys in rest.items():
        fitted = [(w, r, y) for w, r, y in ys if v[w, r]["point"] not in BANK_MUX2]
        for name, f in BANK_FORMS.items():
            c = lsq([f(w, r) for w, r, _ in fitted], [y for _, _, y in fitted])
            at = lambda w, r: sum(ci * xi for ci, xi in zip(c, f(w, r)))  # noqa: E731
            res = [(y - at(w, r)) / y * 100 for w, r, y in fitted if y]
            mux = [f"{y / at(w, r):.2f}" for w, r, y in ys if v[w, r]["point"] in BANK_MUX2]
            body.append([k, name, ", ".join(f"{ci:.5g}" for ci in c), f"{max(map(abs, res)):.1f}",
                         f"{(sum(x * x for x in res) / len(res)) ** 0.5:.1f}", ", ".join(mux)])
    out.append(table(["extra", "form", "k (a, b)", "worst %", "rms %", "MUX2 point / form"], body))
    return "\n".join(out)


def power_tables(tech: str) -> tuple[str, dict]:
    """R2's check tables for `tech`, and the numbers the run note quotes (e_hold, the slope ratios)."""
    f = ROOT / "results" / "char" / tech / "char_power.csv"
    rows_of: dict = {}
    for r in rows(f):
        if r["status"] == "ok":
            rows_of.setdefault(r["point"], {})[r["window"]] = r
    synth = {r["point"]: r for r in rows(ROOT / "results" / "char" / tech / "char_synth.csv")}
    e = lambda p, w, col="e_dyn_pj": float(rows_of[p][w][col])  # noqa: E731
    out, nums = [], {}

    # hold: idle e_bit of the registered blocks
    body, bits = [], []
    for p in sorted(rows_of, key=lambda p: (synth[p]["datapath"], int(synth[p]["lanes"] or 0), p)):
        if synth[p]["datapath"] not in ("Mac", "TreeAccumulate", "SerialAccumulate"):
            continue
        b = 1000 * e(p, "idle", "e_bit_pj")
        bits.append(b)
        body.append([p, synth[p]["seq_cells"], f"{e(p, 'idle', 'e_flop_pj'):.4f}", f"{e(p, 'idle', 'e_comb_pj'):.4f}",
                     f"{b:.4f}"])
    mean = sum(bits) / len(bits)
    sd = (sum((b - mean) ** 2 for b in bits) / (len(bits) - 1)) ** 0.5
    nums["e_hold_fj"] = mean
    out += [f"### {tech}: idle e_bit of the registered blocks\n",
            table(["point", "flops", "idle e_flop pJ", "idle e_comb pJ", "idle e_bit fJ"], body),
            f"\n{len(bits)} points: mean e_hold = {mean:.4f} fJ per flop, min {min(bits):.4f}, max {max(bits):.4f}, "
            f"standard deviation {sd:.4f} fJ ({100 * sd / mean:.2f} % of the mean), range {100 * (max(bits) - min(bits)) / mean:.2f} %."]

    # depth: LinkBuffer at W = 1
    ds = [d for d in (1, 2, 4, 8, 16) if f"link/d{d}_w1" in rows_of]
    body = [[d, synth[f"link/d{d}_w1"]["seq_cells"], f"{e(f'link/d{d}_w1', 'stream', 'e_comb_pj'):.4f}",
             f"{e(f'link/d{d}_w1', 'stream', 'e_flop_pj'):.4f}", f"{e(f'link/d{d}_w1', 'stream'):.4f}",
             f"{1000 * e(f'link/d{d}_w1', 'stream', 'e_bit_pj'):.4f}"] for d in ds]
    out += [f"\n### {tech}: LinkBuffer stream against depth (W = 1)\n",
            table(["D", "flops", "e_comb pJ", "e_flop pJ", "e_dyn pJ", "e_bit fJ"], body)]
    expect = 64 * mean / 1000
    body = []
    for col in ("e_dyn_pj", "e_flop_pj"):
        m, c, res = fit([float(d) for d in ds], [e(f"link/d{d}_w1", "stream", col) for d in ds])
        nums[f"slope_ratio_{col}"] = m / expect
        body.append([col.removesuffix("_pj"), f"{m:.4f}", f"{c:.4f}", f"{res:.2f}", f"{expect:.4f}", f"{m / expect:.3f}"])
    out += ["\n" + table(["fit", "m pJ per D", "c pJ", "max residual %", "64 e_hold pJ", "m / (64 e_hold)"], body),
            f"\nA ratio below {SLOPE_MIN} calls for the diagnostic (R2's prompt, step 5)."]
    body = []
    for w in (8, 32):
        p = f"link/d1_w{w}"
        if p in rows_of and "link/d1_w1" in rows_of:
            body.append([p] + [f"{e(p, 'stream', c) / (w * e('link/d1_w1', 'stream', c)):.4f}"
                               if e("link/d1_w1", "stream", c) else "-"      # d1_w1's stream e_comb is 0 gated
                               for c in ("e_comb_pj", "e_flop_pj", "e_dyn_pj")])
    out += ["\n" + table(["point", "e_comb / (W d1_w1)", "e_flop / (W d1_w1)", "e_dyn / (W d1_w1)"], body)]

    # lanes: lane copies
    body = []
    for name, pat, win in (("SimdLanes add busy", "lanes/add_w{}", "busy"),
                           ("SimdLanes mul busy", "lanes/mul_w{}", "busy"),
                           ("Mac busy", "mac/acc_w{}", "busy"), ("Mac idle", "mac/acc_w{}", "idle")):
        one = e(pat.format(1), win)
        body.append([name, f"{one:.4f}"] + [x for w in (8, 32) for x in
                                            (f"{e(pat.format(w), win):.4f}", f"{e(pat.format(w), win) / (w * one):.4f}")])
    out += [f"\n### {tech}: lane copies\n",
            table(["block, window", "W = 1 pJ", "W = 8 pJ", "ratio at 8", "W = 32 pJ", "ratio at 32"], body)]

    # cross: the folds across W
    body = []
    for dp, pat, ws in (("TreeAccumulate", "tree/add_w{}", (1, 2, 4, 8, 16, 32)),
                        ("SerialAccumulate", "serial/sum_w{}", (2, 4, 8, 16, 32))):
        for w in ws:
            p = pat.format(w)
            body.append([dp, w, f"{e(p, 'busy', 'e_comb_pj'):.4f}", f"{e(p, 'busy', 'e_flop_pj'):.4f}", f"{e(p, 'busy'):.4f}",
                         f"{e(p, 'busy') / w:.4f}", f"{e(p, 'idle'):.4f}"])
    out += [f"\n### {tech}: TreeAccumulate and SerialAccumulate against W\n",
            table(["block", "W", "busy e_comb pJ", "busy e_flop pJ", "busy e_dyn pJ", "busy e_dyn / W pJ", "idle e_dyn pJ"],
                  body)]

    # syn2: alone against inside
    mods = rows(ROOT / "results" / "forge" / tech / "power_pt_modules.csv")
    body, none = [], []
    for p in sorted(rows_of):
        top, win = synth[p]["top"], ("stream" if "stream" in rows_of[p] else "busy")
        hits = [m for m in mods if re.fullmatch(rf"{re.escape(top)}(_\d+)?", m["design"])]
        if not hits:
            none.append(p)
        for m in hits:
            x = float(m["e_dyn_pj"])
            body.append([p, win, m["point"].removeprefix("done/"), f"{e(p, win):.4f}", f"{x:.4f}", f"{e(p, win) / x:.3f}"])
    out += [f"\n### {tech}: busy alone against inside the forge points (n2048 run, per cycle)\n",
            table(["point", "window", "inside", "alone pJ", "inside pJ", "alone / inside"], body),
            "\nNo forge counterpart: " + ", ".join(f"`{p}`" for p in none) + "."]
    return "\n".join(out), nums


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", action="append", choices=TECHS, help="only this technology (repeatable)")
    ap.add_argument("--power", action="store_true", help="R1's power checks from char_power.csv")
    ap.add_argument("--bank", action="store_true", help="the Mac bank's study (X97)")
    args = ap.parse_args()
    if args.bank:
        for tech in args.tech or TECHS:
            print(bank_tables(tech) + "\n")
        return 0
    if args.power:
        for tech in args.tech or TECHS:
            if (ROOT / "results" / "char" / tech / "char_power.csv").is_file():
                text, nums = power_tables(tech)
                print(text + "\n")
                low = {k: v for k, v in nums.items() if k.startswith("slope") and v < SLOPE_MIN}
                if low:
                    print(f"{tech}: slope ratio below {SLOPE_MIN}: {low}\n")
        return 0
    print("## RTL alone against inside\n")
    print(rtl_table())
    for tech in args.tech or TECHS:
        char = rows(ROOT / "results" / "char" / tech / "char_synth.csv")
        print(f"\n## {tech}: alone against inside (the forge points)\n")
        print(inside_table(tech, char))
        print(f"\n## {tech}: lane copies\n")
        print(lanes_table(char))
        print(f"\n## {tech}: seq area per flop\n")
        print(flops_table(char))
        print(f"\n## {tech}: flops against the register bits\n")
        print(bits_table(tech, char))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
