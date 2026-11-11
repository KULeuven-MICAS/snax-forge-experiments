#!/usr/bin/env python3
"""report/cluster_breakdown.py - a synthesized cluster's area in groups, against HWCOST and the accelerator alone (X72).

    pixi run cluster-breakdown [--tech nangate45] [--md]
    pixi run cluster-breakdown-test                 report/test_cluster_breakdown.py

For every point of cluster/points.json that has its DC reports (results/cluster/<tech>/reports/<point>.zip, X67
step 2), reads area_hierarchy.rpt (cluster/tree.py's parse) and sums it into cluster/groups.json's groups: a node
belongs to the first group with a rule it matches, else to its parent's group, and its own area (total minus its
children's) goes there, so the groups add up to the top's total. Then, where they exist:

  hwcost  snax-forge's five parts (results/cluster/<tech>/hwcost/<point>.json, cluster/hwcost.py) against the groups
          groups.json maps them to; the parts' sum against those groups' sum, and HWCOST's shares of its own total
          beside the groups' shares of theirs (the viewer's bar, D167)
  alone   the accelerator's shell inside the cluster (csr, ctrl, dp, the rest, the whole) against its point
          synthesized alone (points.json's `alone`, a row of results/forge/<tech>/synth_dc.csv, X22)

Writes results/cluster/<tech>/breakdown.json; --md also prints the tables as Markdown. The macros' area is checked
against synth_dc.csv's `macro_um2` (the TCDM banks and I-cache macros together). Standard library and arc/arc.py.
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
sys.path.insert(0, str(ROOT / "cluster"))
import arc  # noqa: E402
import tree  # noqa: E402

GROUPS = ROOT / "cluster" / "groups.json"
POINTS = ROOT / "cluster" / "points.json"
PARTS = ("datapath", "control", "streamers", "crossbar", "memory")
MACROS = ("tcdm_banks", "icache_macros")
GLUE_MIN = 100.0         # um2: below it a difference in percent says nothing (the shell's glue is a few cells)
SHELL = re.compile(r"i_snax_core_\d+_acc_\d+_\w+/i_\w+_shell_wrapper")


def compile_groups(cfg: dict) -> list[tuple[str, list[tuple[re.Pattern, re.Pattern | None]]]]:
    return [(g["name"], [(re.compile(r["path"]), re.compile(r["design"]) if "design" in r else None)
                         for r in g["rules"]]) for g in cfg["groups"]]


def assign(rows: list[dict], cfg: dict) -> dict[str, str]:
    """Each node's group, by path: the first group with a matching rule, else its parent's (the top's `others`)."""
    groups = compile_groups(cfg)
    out = {"": "others"}
    for r in rows[1:]:                      # a parent comes before its children in DC's report
        hit = next((name for name, rules in groups for p, d in rules
                    if p.fullmatch(r["path"]) and (d is None or d.fullmatch(r["design"]))), None)
        parent = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
        out[r["path"]] = hit or out[parent]
    return out


def own(rows: list[dict]) -> dict[str, float]:
    """Each node's own area: its total minus its children's."""
    kids: dict[str, float] = {}
    for r in rows[1:]:
        parent = r["path"].rsplit("/", 1)[0] if "/" in r["path"] else ""
        kids[parent] = kids.get(parent, 0.0) + r["total"]
    return {r["path"]: r["total"] - kids.get(r["path"], 0.0) for r in rows}


def groups(rows: list[dict], cfg: dict) -> dict[str, float]:
    """Area per group, in groups.json's order; they add up to the top's total."""
    g, a = assign(rows, cfg), own(rows)
    out = {x["name"]: 0.0 for x in cfg["groups"]}
    for path, area in a.items():
        out[g[path]] += area
    return out


def share(x: float, total: float) -> float:
    return 100 * x / total if total else 0.0


def diff(got: float, want: float) -> float | None:
    return None if not want else 100 * (got - want) / want


def hwcost_rows(cost: dict, areas: dict[str, float], cfg: dict) -> dict:
    """HWCOST's five parts against the groups that hold them, each with its share of its own side's total."""
    hw = {k: cost["parts"][k]["area"] for k in PARTS}
    cl = {k: sum(areas[g] for g in cfg["hwcost"][k]) for k in PARTS}
    th, tc = sum(hw.values()), sum(cl.values())
    rows = [{"part": k, "groups": cfg["hwcost"][k], "hwcost_um2": hw[k], "cluster_um2": cl[k],
             "diff_pct": diff(hw[k], cl[k]), "hwcost_share_pct": share(hw[k], th),
             "cluster_share_pct": share(cl[k], tc)} for k in PARTS]
    return {"parts": rows, "hwcost_um2": th, "cluster_um2": tc, "diff_pct": diff(th, tc),
            "not_costed_um2": sum(areas.values()) - tc}


def alone_rows(rows: list[dict], alone: dict) -> dict:
    """The shell inside the cluster against the same point synthesized alone (synth_dc.csv's X22 columns)."""
    shell = next(r for r in rows if SHELL.fullmatch(r["path"]))
    tot = {r["path"]: r["total"] for r in rows}
    sub = {k: tot.get(f"{shell['path']}/{k}", 0.0) for k in ("csr", "ctrl", "dp")}
    inside = {"csr": sub["csr"], "ctrl": sub["ctrl"], "datapath": sub["dp"],
              "glue": shell["total"] - sum(sub.values()), "total": shell["total"]}
    there = {"csr": float(alone["csr_um2"]), "ctrl": float(alone["ctrl_um2"]),
             "datapath": float(alone["datapath_um2"]), "glue": float(alone["glue_um2"]),
             "total": float(alone["area_um2"])}
    return {"point": alone["point"], "snax_forge_commit": alone["snax_forge_commit"], "shell": shell["path"],
            "rows": [{"name": k, "cluster_um2": inside[k], "alone_um2": there[k],
                      "diff_pct": diff(inside[k], there[k]) if there[k] >= GLUE_MIN else None} for k in inside]}


def csv_row(path: Path, point: str) -> dict | None:
    if not path.is_file():
        return None
    with path.open(newline="") as fh:
        return next((r for r in csv.DictReader(fh) if r["point"] == point), None)


def point_breakdown(point: dict, tech: str, cfg: dict) -> dict | None:
    name = point["point"]
    rep = ROOT / "results" / "cluster" / tech / "reports" / f"{name}.zip"
    if not rep.is_file():
        return None
    rows = tree.parse(arc.read_text(rep, "area_hierarchy.rpt", errors="replace"))
    areas = groups(rows, cfg)
    total = rows[0]["total"]
    labels = {g["name"]: g["label"] for g in cfg["groups"]}
    out: dict = {"total_um2": total,
                 "groups": [{"name": k, "label": labels[k], "area_um2": v, "share_pct": share(v, total)}
                            for k, v in areas.items()]}
    syn = csv_row(ROOT / "results" / "cluster" / tech / "synth_dc.csv", name)
    if syn is not None:
        out["snax_forge_commit"], out["snax_cluster_commit"] = syn["snax_forge_commit"], syn["snax_cluster_commit"]
        macros = sum(areas[k] for k in MACROS)
        out["macro_check"] = {"groups_um2": macros, "synth_dc_um2": float(syn["macro_um2"]),
                              "ok": abs(macros - float(syn["macro_um2"])) < 1.0}
    hw = ROOT / "results" / "cluster" / tech / "hwcost" / f"{name}.json"
    if hw.is_file():
        h = json.loads(hw.read_text())
        out["hwcost"] = {"snax_forge_commit": h["snax_forge_commit"], "snax_forge_clean": h["snax_forge_clean"],
                         "platform": h["platform"], **hwcost_rows(h["cost"], areas, cfg)}
    if point.get("alone"):
        a = csv_row(ROOT / "results" / "forge" / tech / "synth_dc.csv", point["alone"])
        if a is not None:
            out["alone"] = alone_rows(rows, a)
    return out


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _p(x: float | None) -> str:
    return "" if x is None else "0.0 %" if abs(x) < 0.05 else f"{x:+.1f} %"


def markdown(name: str, b: dict) -> str:
    out = [f"### {name}", "", f"Total {_n(b['total_um2'])} µm².", "", "| group | µm² | share |", "|---|---|---|"]
    out += [f"| {g['label']} | {_n(g['area_um2'])} | {g['share_pct']:.1f} % |" for g in b["groups"]]
    if "hwcost" in b:
        h = b["hwcost"]
        out += ["", f"HWCOST (snax-forge `{h['snax_forge_commit'][:8]}`, `{h['platform']}`) against the cluster's groups:",
                "", "| part | HWCOST µm² | cluster µm² | difference | share (HWCOST / cluster) |", "|---|---|---|---|---|"]
        out += [f"| {r['part']} | {_n(r['hwcost_um2'])} | {_n(r['cluster_um2'])} | {_p(r['diff_pct'])} | "
                f"{r['hwcost_share_pct']:.1f} % / {r['cluster_share_pct']:.1f} % |" for r in h["parts"]]
        out += [f"| the five parts | {_n(h['hwcost_um2'])} | {_n(h['cluster_um2'])} | {_p(h['diff_pct'])} | |",
                "", f"Not costed by HWCOST: {_n(h['not_costed_um2'])} µm² of the cluster "
                    f"({share(h['not_costed_um2'], b['total_um2']):.1f} %)."]
    if "alone" in b:
        a = b["alone"]
        out += ["", f"The accelerator's shell in the cluster against `{a['point']}` alone (snax-forge "
                    f"`{a['snax_forge_commit'][:8]}`):", "", "| | cluster µm² | alone µm² | difference |",
                "|---|---|---|---|"]
        out += [f"| {r['name']} | {_n(r['cluster_um2'])} | {_n(r['alone_um2'])} | {_p(r['diff_pct'])} |"
                for r in a["rows"]]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--md", action="store_true", help="also print the tables as Markdown")
    a = ap.parse_args()
    cfg = json.loads(GROUPS.read_text())
    res = {}
    for p in json.loads(POINTS.read_text())["points"]:
        b = point_breakdown(p, a.tech, cfg)
        if b is not None:
            res[p["point"]] = b
    if not res:
        print(f"no point with reports in results/cluster/{a.tech}/reports/", file=sys.stderr)
        return 1
    path = ROOT / "results" / "cluster" / a.tech / "breakdown.json"
    path.write_text(json.dumps(res, indent=1) + "\n")
    bad = [k for k, b in res.items() if not b.get("macro_check", {"ok": True})["ok"]]
    print(f"{path.relative_to(ROOT)}: {', '.join(res)}" + (f"; macro check FAILED for {bad}" if bad else ""))
    if a.md:
        print("".join(markdown(k, b) for k, b in res.items()))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
