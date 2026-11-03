#!/usr/bin/env python3
"""char/checks.py - CHAR1's checks on the blocks alone, as Markdown tables for the run note.

  pixi run python char/checks.py [--tech T ...]            R0: synthesis
  pixi run python char/checks.py --power [--tech T ...]    R1: power (results/char/<tech>/char_power.csv)

Read from the committed CSVs (results/char/<tech>/char_synth.csv and
char_synth_modules.csv; SYN2's results/forge/<tech>/synth_dc_modules.csv), and
rtl/char/ and rtl/forge/ (local) for the RTL table. None is a gate.

  rtl      each block's top .sv against the file of the same name in SYN2's
           bundles (rtl/forge/<point>/rtl/sv/): identical or not, per bundle
  inside   each point against every hierarchical cell of SYN2's forge rows
           whose design is the block's top (DC may add _<n>): area, comb and
           seq alone (the char row) and inside (the cell's subtree: area is the
           cell's own total, comb and seq summed over the cell and every cell
           below it, as area_hierarchy.rpt gives each level's own), and the
           difference in um2 and % of inside
  lanes    area(W) / (W * area(1)) for ElementwiseLanes add and mul, Mac and
           LinkBuffer at depth 1, at W = 8 and 32
  flops    seq_area_um2 / seq_cells per point with flops, per technology

With --power (R1), from char_power.csv and SYN2's results/forge/<tech>/power_pt_modules.csv:

  idle     each point's idle e_bit_pj and e_dyn_pj against SYN1's ~7 fJ per flop and the expected idle e_dyn
           (IDLE_EXPECTED)
  duty50   duty50 against (busy + idle) / 2, per group (comb, flop, dyn), in %
  syn2     busy against every hierarchical cell of SYN2's forge rows whose design is the block's top
           (e_dyn_pj per cycle of the forge point's run): a check of size, the stimulus differs
  t1       busy_t1 against busy for the fold and serial kinds, per group, in %

Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TECHS = ("nangate45", "nangate15")
# The expected idle e_dyn per cycle (pJ), from SYN1's ~7 fJ per flop and idle clock: R1's prompt
IDLE_EXPECTED = {"tree/add_w8": 0.45, "mac/acc_w8": 3.6, "link/d4_w1": 1.8, "lanes/add_w8": 0.0}
GROUPS = (("comb", "e_comb_pj"), ("flop", "e_flop_pj"), ("dyn", "e_dyn_pj"))
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
    for e in sorted((ROOT / "rtl" / "char").rglob("emitted.json")):
        point = str(e.parent.relative_to(ROOT / "rtl" / "char"))
        top = json.loads(e.read_text())["top"]
        same, differ = [], []
        for f in sorted((ROOT / "rtl" / "forge").glob(f"done/*/*/rtl/sv/{top}.sv")):
            b = "/".join(f.parts[-5:-3])
            (same if f.read_bytes() == (e.parent / "sv" / f"{top}.sv").read_bytes() else differ).append(b)
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


def power_tables(tech: str) -> str:
    f = ROOT / "results" / "char" / tech / "char_power.csv"
    table_rows = [r for r in rows(f) if r["status"] == "ok"]
    rows_of = {}
    for r in table_rows:
        rows_of.setdefault(r["point"], {})[r["window"]] = r
    synth = {r["point"]: r for r in csv.DictReader((ROOT / "results" / "char" / tech / "char_synth.csv").open())}
    out = []
    body = []
    for p, w in rows_of.items():
        i = w.get("idle")
        if not i:
            continue
        exp = IDLE_EXPECTED.get(p)
        e = float(i["e_dyn_pj"])
        body.append([p, synth[p]["seq_cells"], f"{1000 * float(i['e_bit_pj']):.3f}" if i["e_bit_pj"] else "-",
                     f"{e:.4f}", f"{exp:g}" if exp is not None else "-",
                     pct(e, exp) if exp else "-", f"{float(i['e_comb_pj']):.4f}"])
    out += [f"### {tech}: idle\n", table(["point", "flops", "idle e_bit fJ", "idle e_dyn pJ", "expected pJ",
                                          "diff %", "idle e_comb pJ"], body)]
    body = []
    for p, w in rows_of.items():
        if not all(k in w for k in ("busy", "idle", "duty50")):
            continue
        cells = [p]
        for _, col in GROUPS:
            b, i, d = (float(w[k][col]) for k in ("busy", "idle", "duty50"))
            half = (b + i) / 2
            cells += [f"{d:.4f}", f"{half:.4f}", pct(d, half)]
        body.append(cells)
    head = ["point"] + [f"{g} {x}" for g, _ in GROUPS for x in ("duty50", "half", "diff %")]
    out += [f"\n### {tech}: duty50 against (busy + idle) / 2\n", table(head, body)]
    mods = list(csv.DictReader((ROOT / "results" / "forge" / tech / "power_pt_modules.csv").open(newline="")))
    body = []
    for p, w in rows_of.items():
        top = synth[p]["top"]
        hits = [m for m in mods if re.fullmatch(rf"{re.escape(top)}(_\d+)?", m["design"])]
        b = float(w["busy"]["e_dyn_pj"])
        if not hits:
            body.append([p, f"`{top}`", "-", f"{b:.4f}", "-", "-"])
        for m in hits:
            x = float(m["e_dyn_pj"])
            body.append([p, f"`{top}`", m["point"].removeprefix("done/"), f"{b:.4f}", f"{x:.4f}", f"{b / x:.3f}"])
    out += [f"\n### {tech}: busy alone against inside SYN2 (n2048 run, per cycle)\n",
            table(["point", "top", "inside", "busy alone pJ", "inside pJ", "alone / inside"], body)]
    body = []
    for p, w in rows_of.items():
        if "busy_t1" not in w:
            continue
        cells = [p]
        for _, col in GROUPS:
            b, t = float(w["busy"][col]), float(w["busy_t1"][col])
            cells += [f"{b:.4f}", f"{t:.4f}", pct(t, b)]
        body.append(cells)
    head = ["point"] + [f"{g} {x}" for g, _ in GROUPS for x in ("busy", "busy_t1", "diff %")]
    out += [f"\n### {tech}: busy_t1 against busy\n", table(head, body)]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", action="append", choices=TECHS, help="only this technology (repeatable)")
    ap.add_argument("--power", action="store_true", help="R1's power checks from char_power.csv")
    args = ap.parse_args()
    if args.power:
        for tech in args.tech or TECHS:
            if (ROOT / "results" / "char" / tech / "char_power.csv").is_file():
                print(power_tables(tech) + "\n")
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
