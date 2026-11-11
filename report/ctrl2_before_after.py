#!/usr/bin/env python3
"""report/ctrl2_before_after.py - results/compare/ctrl2_before_after.md: forge before and after snax-forge D168 (CTRL2 R5).

  pixi run python report/ctrl2_before_after.py OLD_REV OLD_FLOPS_JSON NEW_FLOPS_JSON

Before: OLD_REV's results/compare_done.csv and compare_untiered.csv (CSYN1 Part A, X64), the csr whole. After: the
working tree's, the csr without its <tag>_peripherals child (X65). Flops: forge/ctrl2_checks.py flops, counted in
the mapped netlists before and after the resynthesis. nangate45, n2048, W = 1 to 16, every forge case.

Per kernel, case and W, before -> after: csr (before the whole csr), ctrl area, ctrl pJ per cycle, ctrl flops,
datapath area, ctrl + datapath area and pJ per element, and which HLS cases (Vitis opt and dace, Bambu, XLS) forge's
total without csr (X63) beats or loses to on energy per element and on area at that W. Only the part between
<!-- gen:tables --> and <!-- /gen --> is generated; the text above it is hand-written and kept.
"""
from __future__ import annotations

import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "compare" / "ctrl2_before_after.md"
TECH, SIZE = "nangate45", "n2048"
KERNELS = [("done", "vecadd"), ("done", "vecmul"), ("done", "vsum"), ("done", "dot"),
           ("untiered", "matadd"), ("untiered", "relu"), ("untiered", "axpy"), ("untiered", "rowsum")]
HLS = [("opt", "Vitis opt"), ("dace", "Vitis dace"), ("bambu", "Bambu"), ("xls", "XLS")]
LABEL = {"forge": "forge", **{f"forge{k}": f"forge {k}" for k in range(2, 7)}, "forge_baked": "forge baked"}


def load(text: str) -> list[dict]:
    return [r for r in csv.DictReader(io.StringIO(text)) if r["tech"] == TECH and r["size"] == SIZE
            and r["status"] == "ok" and int(r["W"]) <= 16]


def at(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def f(r: dict, k: str) -> float:
    return float(r[k])


def figures(r: dict) -> dict:
    cyc, el = int(r["cycles"]), int(r["elements"])
    e_ctrl, e_dp, e_csr = f(r, "e_dyn_ctrl_pj"), f(r, "e_dyn_datapath_pj"), f(r, "e_dyn_csr_pj")
    return {"csr": f(r, "csr_um2"), "ctrl": f(r, "ctrl_um2"), "ctrl_pj": e_ctrl, "dp": f(r, "datapath_um2"),
            "cd_area": f(r, "ctrl_um2") + f(r, "datapath_um2"), "cd_pj": (e_ctrl + e_dp) * cyc / el,
            "nocsr_area": f(r, "area_um2") - f(r, "csr_um2"), "nocsr_pj": (f(r, "e_run_pj") - e_csr * cyc) / el}


def verdict(fg: dict, hls: dict, key_f: str, key_h) -> str:
    """'beats A, B; loses to C' of forge's total without csr against each HLS case present."""
    win = [lab for c, lab in HLS if c in hls and fg[key_f] < key_h(hls[c])]
    lose = [lab for c, lab in HLS if c in hls and fg[key_f] >= key_h(hls[c])]
    return "; ".join(x for x in (f"beats {', '.join(win)}" if win else "", f"loses to {', '.join(lose)}" if lose else "") if x)


def num(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:.3g}"


def ba(a, b, fmt=num) -> str:
    return fmt(a) if fmt(a) == fmt(b) else f"{fmt(a)} → {fmt(b)}"


def tables(old: list[dict], new: list[dict], fl_old: dict, fl_new: dict) -> tuple[list[str], dict]:
    idx = lambda rows: {(r["kernel"], r["case"], int(r["W"])): r for r in rows}  # noqa: E731
    o, n = idx(old), idx(new)
    out, stats = [], {"rows": 0, "changes": []}
    for tier, k in KERNELS:
        cases = sorted({c for (kk, c, _w) in n if kk == k and c.startswith("forge")},
                       key=lambda c: (c != "forge", c))
        out += [f"### {k} ({tier})", "",
                "| Case | W | csr µm² | ctrl µm² | ctrl pJ/cycle | ctrl flops | datapath µm² | ctrl + datapath µm² | "
                "ctrl + datapath pJ/element | energy against HLS | area against HLS |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
        for c in cases:
            for w in (1, 2, 4, 8, 16):
                if (k, c, w) not in n:
                    continue
                ro, rn = o[(k, c, w)], n[(k, c, w)]
                fo, fn = figures(ro), figures(rn)
                hls = {cc: n[(k, cc, w)] for cc, _ in HLS if (k, cc, w) in n}
                hls_o = {cc: o[(k, cc, w)] for cc, _ in HLS if (k, cc, w) in o}
                ppe = lambda r: f(r, "e_run_pj") / int(r["elements"])  # noqa: E731
                ev = (verdict(fo, hls_o, "nocsr_pj", ppe), verdict(fn, hls, "nocsr_pj", ppe))
                av = (verdict(fo, hls_o, "nocsr_area", lambda r: f(r, "area_um2")),
                      verdict(fn, hls, "nocsr_area", lambda r: f(r, "area_um2")))
                pt = rn["point"]
                cell = lambda v: v[0] if v[0] == v[1] else f"{v[0]} → **{v[1]}**"  # noqa: E731
                out.append(f"| {LABEL[c]} | {w} | {ba(fo['csr'], fn['csr'])} | {ba(fo['ctrl'], fn['ctrl'])} | "
                           f"{ba(fo['ctrl_pj'], fn['ctrl_pj'])} | {ba(fl_old[pt]['flops'], fl_new[pt]['flops'], str)} | "
                           f"{ba(fo['dp'], fn['dp'])} | {ba(fo['cd_area'], fn['cd_area'])} | "
                           f"{ba(fo['cd_pj'], fn['cd_pj'])} | {cell(ev)} | {cell(av)} |")
                stats["rows"] += 1
                for key, lab in (("csr", "csr µm²"), ("ctrl", "ctrl µm²"), ("ctrl_pj", "ctrl pJ/cycle"),
                                 ("cd_area", "ctrl + datapath µm²"), ("cd_pj", "ctrl + datapath pJ/element"),
                                 ("nocsr_area", "total without csr µm²"), ("nocsr_pj", "total without csr pJ/element"),
                                 ("dp", "datapath µm²")):
                    stats["changes"].append((pt, lab, fo[key], fn[key]))
                if ev[0] != ev[1] or av[0] != av[1]:
                    stats.setdefault("flips", []).append((pt, ev, av))
        out.append("")
    return out, stats


def main() -> int:
    rev, fo_path, fn_path = sys.argv[1:4]
    old = load(at(rev, "results/compare_done.csv")) + load(at(rev, "results/compare_untiered.csv"))
    new = load((ROOT / "results" / "compare_done.csv").read_text()) + \
        load((ROOT / "results" / "compare_untiered.csv").read_text())
    fl_old, fl_new = json.loads(Path(fo_path).read_text()), json.loads(Path(fn_path).read_text())
    body, stats = tables(old, new, fl_old, fl_new)
    head = ["# forge before and after CTRL2 (snax-forge D168)", "", "(to write)", "", "<!-- gen:tables -->",
            "<!-- /gen -->", ""]
    text = OUT.read_text() if OUT.is_file() else "\n".join(head)
    pat = re.compile(r"(<!-- gen:tables -->\n).*?(<!-- /gen -->)", re.S)
    text = pat.sub(lambda m: m.group(1) + "\n".join(body) + "\n" + m.group(2), text, count=1)
    OUT.write_text(text)
    print(f"{OUT.relative_to(ROOT)}: {stats['rows']} rows")
    # the largest relative changes, for the run note and the paragraph on top
    rel = sorted(((abs(b - a) / a if a else 0, pt, lab, a, b) for pt, lab, a, b in stats["changes"]), reverse=True)
    by_lab = {}
    for r, pt, lab, a, b in rel:
        by_lab.setdefault(lab, []).append((r, pt, a, b))
    for lab, xs in by_lab.items():
        rs = [(b - a) / a * 100 for _r, _pt, a, b in xs if a]
        print(f"  {lab:32} change {min(rs):+7.2f} % to {max(rs):+7.2f} %; largest {xs[0][1]} {xs[0][2]:.4g} -> {xs[0][3]:.4g}")
    for pt, ev, av in stats.get("flips", []):
        print(f"  flip {pt}: energy {ev[0]!r} -> {ev[1]!r}; area {av[0]!r} -> {av[1]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
