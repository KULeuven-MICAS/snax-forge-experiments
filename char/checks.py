#!/usr/bin/env python3
"""char/checks.py - CHAR1's checks on the blocks alone, as Markdown tables for the run note.

  pixi run python char/checks.py [--tech T ...]            R0: synthesis
  pixi run python char/checks.py --power [--tech T ...]    R1: power (results/char/<tech>/char_power.csv)

Read from the committed CSVs (results/char/<tech>/char_synth.csv and
char_synth_modules.csv; SYN2's results/forge/<tech>/synth_dc_modules.csv), and
rtl/char/ and rtl/forge/'s bundle zips (local, X51) for the RTL table. None is a gate.

  rtl      each block's top .sv against the file of the same name in SYN2's
           bundles (rtl/sv/ in rtl/forge/<point>.zip): identical or not, per bundle
  inside   each point against every hierarchical cell of SYN2's forge rows
           whose design is the block's top (DC may add _<n>): area, comb and
           seq alone (the char row) and inside (the cell's subtree: area is the
           cell's own total, comb and seq summed over the cell and every cell
           below it, as area_hierarchy.rpt gives each level's own), and the
           difference in um2 and % of inside
  lanes    area(W) / (W * area(1)) for ElementwiseLanes add and mul, Mac and
           LinkBuffer at depth 1, at W = 8 and 32
  flops    seq_area_um2 / seq_cells per point with flops, per technology

With --power (R2), from char_power.csv (and SYN2's results/forge/<tech>/power_pt_modules.csv):

  hold     idle e_bit_pj of every registered block (Mac, TreeAccumulate, SerialAccumulate), its mean (e_hold) and
           spread
  depth    LinkBuffer at W = 1: least-squares lines E_stream(D) = m D + c over D = 1 .. 16 for e_dyn and e_flop,
           and m against 64 e_hold (one more slot of 64 holding flops per depth) as a ratio; d1 at W = 8 and 32
           against W x its W = 1 value
  lanes    busy(W) / (W busy(1)) for ElementwiseLanes add and mul and Mac, idle(W) / (W idle(1)) for Mac
  cross    TreeAccumulate and SerialAccumulate busy and idle against W
  syn2     busy (link: stream) against every hierarchical cell of SYN2's forge rows whose design is the block's
           top (e_dyn_pj per cycle of the forge point's run): a check of size, the stimulus differs

Standard library and arc/arc.py only.
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
import arc  # noqa: E402  the bundles are zips (X51)

TECHS = ("nangate45", "nangate15")
SLOPE_MIN = 0.7      # a LinkBuffer slope ratio below this calls for R2's diagnostic (not a gate)
LANE_SERIES = {"ElementwiseLanes add": "lanes/add_w{}", "ElementwiseLanes mul": "lanes/mul_w{}",
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
    return table(head, body) + "\n\nNo SYN2 counterpart: " + (", ".join(f"`{p}`" for p in none) or "none") + "."


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


def pct(a: float, b: float) -> str:
    return f"{100 * (a - b) / b:+.2f}" if b else "-"


def fit(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Least squares y = m x + c: (m, c, the largest residual in % of y)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    c = my - m * mx
    return m, c, max(abs(y - (m * x + c)) / y * 100 for x, y in zip(xs, ys))


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
    for p in sorted(rows_of, key=lambda p: (synth[p]["datapath"], int(synth[p]["lanes"]))):
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
                               for c in ("e_comb_pj", "e_flop_pj", "e_dyn_pj")])
    out += ["\n" + table(["point", "e_comb / (W d1_w1)", "e_flop / (W d1_w1)", "e_dyn / (W d1_w1)"], body)]

    # lanes: lane copies
    body = []
    for name, pat, win in (("ElementwiseLanes add busy", "lanes/add_w{}", "busy"),
                           ("ElementwiseLanes mul busy", "lanes/mul_w{}", "busy"),
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
    out += [f"\n### {tech}: busy alone against inside SYN2 (n2048 run, per cycle)\n",
            table(["point", "window", "inside", "alone pJ", "inside pJ", "alone / inside"], body),
            "\nNo SYN2 counterpart: " + ", ".join(f"`{p}`" for p in none) + "."]
    return "\n".join(out), nums


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", action="append", choices=TECHS, help="only this technology (repeatable)")
    ap.add_argument("--power", action="store_true", help="R1's power checks from char_power.csv")
    args = ap.parse_args()
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
        print(f"\n## {tech}: alone against inside (SYN2)\n")
        print(inside_table(tech, char))
        print(f"\n## {tech}: lane copies\n")
        print(lanes_table(char))
        print(f"\n## {tech}: seq area per flop\n")
        print(flops_table(char))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
