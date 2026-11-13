#!/usr/bin/env python3
"""report/compare.py - the raw comparison tables: forge and the four HLS cases, one CSV per tier (X38 to X44).

  pixi run compare            # writes results/compare_done.csv and results/compare_untiered.csv
  pixi run compare --check    # checks only, writes nothing

Reads only committed CSVs in this repo (no tool, no licence, no checkout next to the repo):

  results/<source>/<tech>/synth_dc.csv          area, timing, path-class slacks, the forge and bambu splits
  results/<source>/<tech>/power_pt.csv          one row per point, size and seed: window cycles and energy
  results/<source>/<tech>/power_pt_modules.csv  energy per hierarchical cell, per point and size (X60)
  results/hls/hls_cycles.csv, results/bambu/bambu_cycles.csv, results/xls/xls_cycles.csv   provenance

for the sources forge, hls (Vitis opt and dace), bambu and xls, on nangate45 and nangate15, W <= MAX_W (X38).
Forge's W = 32 rows are left out like every other W > MAX_W; its untiered points (CSYN1) are nangate45 only
(snax-forge D159), every other point is on both technologies.

One row per tech, tier, kernel, W, tool, case and size. The data is laid out, not compared: no ratios, no
ranking (the comparison is brainstormed on top of these tables). Parked points (a RAM macro, X15) are rows
with their status and no numbers.

Columns:
  key        tech, tier, kernel, W, tool (forge, vitis, bambu, xls), case (forge, forge2..6, forge_baked, opt,
             dace, bambu, xls), point, size, status (ok, or the synthesis or power status that is not)
  task       beats (per input stream), elements (beats * W), cycles (the power window), window (how the
             window is defined for the tool: X12, X44)
  area       area_um2, comb_area_um2, seq_area_um2, buf_inv_area_um2, cells, seq_cells, and the split where
             the RTL declares it as hierarchy (X41): csr_um2 (forge), ctrl_um2, datapath_um2, glue_um2
             (forge, bambu); empty for vitis and xls; forge's csr_um2 is the csr cell without its child
             <tag>_peripherals (BUSY_COUNTER, snax-forge D168; X65), whose area is peripherals_um2 (for the
             record, in no figure: forge's total without csr is area_um2 - csr_um2 - peripherals_um2; empty
             where the bundle has none: every point before CTRL2 R5); ram_kind and ram_um2 for a Vitis point with a RAM (X62:
             an SRAM macro or flops, inside area_um2)
  timing     crit_path_ns, slack_ns, fmax_mhz, slack_in2reg_ns, slack_reg2reg_ns, slack_reg2out_ns,
             slack_in2out_ns (X40; empty on forge rows, synthesized before X40)
  energy     e_clk_pj, e_reg_pj, e_seq_pj, e_comb_pj, e_flop_pj, e_dyn_pj (per cycle of the window),
             p_dyn_uw, e_run_pj (the task), pj_per_elem (e_run_pj / elements), flop_bits, e_bit_pj,
             leak_dc_uw (DC's leakage estimate, X7); ram_reads, ram_writes, e_ram_pj (the RAM's share of
             e_run_pj, X62: counted accesses x CACTI's energies for a macro, X50; PT's for flops)
  parts      e_dyn_csr_pj, e_dyn_ctrl_pj, e_dyn_datapath_pj, e_dyn_glue_pj (per cycle, forge and bambu
             only; forge's csr without its _peripherals child, whose energy is e_dyn_peripherals_pj, for the record, X65), parts_size (the run they come from: the row's own run where power_pt_modules.csv has it
             (X60: every n2048 run; X63), else the point's default run: tier done b64 (rowsum m8_n64), forge
             n2048, untiered on nangate45 n2048 (X55), on nangate15 the default run (X61))
  provenance rtl_commit (the tool repo commit the RTL was measured at; forge: snax_forge_commit),
             tool_version, dc_version, syn_date

Checks (any failure: exit 1, nothing written): every listed point has a synthesis row on both technologies
(an untiered forge point on nangate45 only); every ok point has the same sizes as the other points of its
kernel, n2048 among them (X24; X55 on nangate45, X61), each with an ok power row; no duplicate key; the split columns (csr, ctrl, datapath, glue and, for forge since CTRL2 R5, peripherals) sum to the area where they exist; a point with parts has an ok
run at its default size. A glue energy within 1e-5 of the total (PT's rounding) is written as 0.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "syn"))
import syn  # noqa: E402  (MAX_W and the case filters live in one place)

TECHS = ("nangate45", "nangate15")
SOURCES = ("forge", "hls", "bambu", "xls")
TOOL = {"forge": "forge", "hls": "vitis", "bambu": "bambu", "xls": "xls"}
TOOL_ORDER = {"forge": 0, "vitis": 1, "bambu": 2, "xls": 3}
WINDOW = {
    "forge": "START to done (X13)",
    "vitis": "ap_start to ap_done (X12)",
    "bambu": "start_port to done_port (X44)",
    "xls": "cfg transfer to last output, last edge included (X44)",
}
CYCLES_CSV = {"hls": "hls/hls_cycles.csv", "bambu": "bambu/bambu_cycles.csv", "xls": "xls/xls_cycles.csv"}
VERSION_COL = {"hls": "vitis", "bambu": "bambu_version", "xls": "xls_version"}
# Parts by the design name of the hierarchical cell (synth_dc_modules.csv, power_pt_modules.csv): a regex on
# the design, matched among the top's children. forge: snax_forge_<part> (SYN1, SYN2), or snax_forge_<design>_<part>
# since snax-forge names modules after the design (PITFALLS E5); bambu: the controller_ and datapath_ prefixes
PARTS = {
    "forge": {"csr": r"snax_forge_(?:\w+_)?csr", "ctrl": r"snax_forge_(?:\w+_)?ctrl",
              "datapath": r"snax_forge_(?:\w+_)?datapath"},
    "bambu": {"ctrl": r"(?i)controller_.*", "datapath": r"(?i)datapath_.*"},
}
# X65: forge's csr holds <tag>_peripherals (BUSY_COUNTER, snax-forge D168), neither interface nor control and in no
# figure: the csr part is the csr cell minus this child (one level below it), kept apart for the record, and the
# total without csr (compare_hls.py) subtracts the whole csr cell, as in Part A; a bundle without it (every point
# before CTRL2 R5) subtracts nothing
PERIPHERALS = r"snax_forge_(?:\w+_)?peripherals"
# The size of a point's default run (power_pt_modules.csv has it, X60): b64 (X19), but rowsum's default is its
# m8_n64 task, and forge runs n2048 only. Untiered rows take their parts from n2048 (X55).
DEFAULT_SIZE = {"rowsum": "m8_n64"}
REF_SIZE = "n2048"
REF_TECH_UNTIERED = "nangate45"           # X61: untiered n2048 runs on nangate45 only (CSYN1)
NANGATE45_ONLY = ("untiered", "forge")
# X62: Vitis dace cases rebuilt for the n2048 task only (hls-exercises' params.json gives the case its own sizes)
N2048_ONLY = {("done", "dot", "dace"), ("untiered", "axpy", "dace"), ("untiered", "rowsum", "dace")}    # (tier, tool): CSYN1's forge points, nangate45 only (snax-forge D159)
POINT = re.compile(r"^(?P<tier>[^/]+)/(?P<kernel>[^/]+)/(?P<case>[a-z]+[0-9]*(?:_[a-z]+)?)_w(?P<w>\d+)$")

KEY = ["tech", "tier", "kernel", "W", "tool", "case", "point", "size", "status"]
TASK = ["beats", "elements", "cycles", "window"]
AREA = ["area_um2", "comb_area_um2", "seq_area_um2", "buf_inv_area_um2", "cells", "seq_cells",
        "csr_um2", "ctrl_um2", "datapath_um2", "glue_um2", "ram_kind", "ram_um2", "peripherals_um2"]
TIMING = ["crit_path_ns", "slack_ns", "fmax_mhz", "slack_in2reg_ns", "slack_reg2reg_ns", "slack_reg2out_ns",
          "slack_in2out_ns"]
ENERGY = ["e_clk_pj", "e_reg_pj", "e_seq_pj", "e_comb_pj", "e_flop_pj", "e_dyn_pj", "p_dyn_uw", "e_run_pj",
          "pj_per_elem", "flop_bits", "e_bit_pj", "leak_dc_uw", "ram_reads", "ram_writes", "e_ram_pj"]
PART_E = ["e_dyn_csr_pj", "e_dyn_ctrl_pj", "e_dyn_datapath_pj", "e_dyn_glue_pj", "parts_size",
          "e_dyn_peripherals_pj"]
PROV = ["rtl_commit", "tool_version", "dc_version", "syn_date"]
COLUMNS = KEY + TASK + AREA + TIMING + ENERGY + PART_E + PROV


def read(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(newline="") as fh:     # X79: a clock-gated row (clk_gate 1) is not part of the comparison
        return [r for r in csv.DictReader(fh) if r.get("clk_gate", "") != "1"]


def parse(point: str) -> dict | None:
    m = POINT.match(point)
    return m.groupdict() if m else None


def listed(source: str, point: str) -> bool:
    """The points HSYN1 compares: W <= MAX_W, and for the HLS sources the case filter of syn.py."""
    p = parse(point)
    if not p or int(p["w"]) > syn.MAX_W:
        return False
    cases = syn.SOURCES[source].get("cases")
    return p["case"] in cases if cases else p["case"].startswith("forge")


def provenance(source: str) -> dict:
    """(tier, kernel, case, W) -> (rtl commit, tool version), from the cycle CSVs (the last 10 ns row)."""
    out = {}
    if source not in CYCLES_CSV:
        return out
    for r in read(ROOT / "results" / CYCLES_CSV[source]):
        if r.get("clock_ns") not in ("10", "10.0") or not r.get("W"):
            continue
        out[(r["tier"], r["kernel"], r["case"], r["W"])] = (r.get("git", ""), r.get(VERSION_COL[source], ""))
    return out


def part_energy(source: str, mods: list[dict]) -> dict:
    """e_dyn per cycle of each declared part, from the point's power_pt_modules rows (X41)."""
    if source not in PARTS or not mods:
        return {}
    top = min(mods, key=lambda r: r["path"].count("/"))
    total = float(top["e_dyn_pj"])
    depth = {}
    out = {}
    for part, design in PARTS[source].items():
        hits = [r for r in mods if re.fullmatch(design, r["design"])]
        if not hits:
            raise ValueError(f"{top['point']} {top['size']}: no {design} cell in power_pt_modules.csv")
        hit = min(hits, key=lambda r: r["path"].count("/"))
        depth[part] = hit["path"].count("/")
        if source == "forge" and depth[part] != top["path"].count("/") + 1:
            raise ValueError(f"{top['point']} {top['size']}: {hit['design']} is not one of the wrapper's instances")
        out[f"e_dyn_{part}_pj"] = float(hit["e_dyn_pj"])
        if source == "forge" and part == "csr":
            csr_path = hit["path"]
    glue = total - sum(out.values())
    # PT prints about 7 significant digits, so a wrapper with nothing but its parts leaves a glue of
    # +-1e-6 of the total: that is rounding, written as 0
    out["e_dyn_glue_pj"] = 0.0 if abs(glue) <= 1e-5 * abs(total) else glue
    if source == "forge":       # X65: the glue above counts the whole csr; the csr part leaves its peripherals out
        per = peripherals(mods, csr_path, f"{top['point']} {top['size']}")
        if per is not None:
            e_per = float(per["e_dyn_pj"])
            out["e_dyn_csr_pj"] -= e_per
            out["e_dyn_peripherals_pj"] = e_per
    return {k: f"{v:.6g}" for k, v in out.items()}


def peripherals(mods: list[dict], csr_path: str, what: str) -> dict | None:
    """X65: the csr's <tag>_peripherals child (one level below the csr cell at csr_path), or None (a bundle before
    snax-forge D168)."""
    hits = [r for r in mods if re.fullmatch(PERIPHERALS, r["design"])]
    if not hits:
        return None
    kids = [r for r in hits if r["path"].startswith(csr_path + "/") and r["path"].count("/") == csr_path.count("/") + 1]
    if len(kids) != 1 or len(hits) != 1:
        raise ValueError(f"{what}: peripherals cells {[r['path'] for r in hits]}, expected one child of {csr_path}")
    return kids[0]


def rows_for(source: str, tech: str, problems: list[str]) -> list[dict]:
    base = ROOT / "results" / source / tech
    synth = {r["point"]: r for r in read(base / "synth_dc.csv")}
    power = defaultdict(list)
    for r in read(base / "power_pt.csv"):
        power[r["point"]].append(r)
    mods = defaultdict(list)
    for r in read(base / "power_pt_modules.csv"):
        mods[(r["point"], r["size"])].append(r)
    synth_mods = defaultdict(list)
    if source == "forge":
        for r in read(base / "synth_dc_modules.csv"):
            synth_mods[r["point"]].append(r)
    prov = provenance(source)
    out = []
    for point in sorted(p for p in synth if listed(source, p)):
        s = synth[point]
        p = parse(point)
        tool = TOOL[source]
        common = {"tech": tech, "tier": p["tier"], "kernel": p["kernel"], "W": p["w"], "tool": tool,
                  "case": p["case"], "point": point, "window": WINDOW[tool]}
        common.update({c: s.get(c, "") for c in AREA + TIMING})
        common["leak_dc_uw"] = s.get("leak_power_uw", "")
        if source == "forge":
            common["rtl_commit"] = s.get("snax_forge_commit", "")
        else:
            commit, version = prov.get((p["tier"], p["kernel"], p["case"], p["w"]), ("", ""))
            common["rtl_commit"], common["tool_version"] = commit, version
        common["dc_version"], common["syn_date"] = s.get("dc_version", ""), s.get("date", "")
        if s["status"] != "ok":
            row = dict(common, status=f"syn: {s['status']}")
            for c in AREA + TIMING + ["leak_dc_uw"]:
                row[c] = ""
            out.append(row)
            continue
        if source == "forge" and s.get("csr_um2"):     # X65: the csr part without its peripherals child
            csr = [r for r in synth_mods[point] if re.fullmatch(PARTS["forge"]["csr"], r["design"])]
            try:
                if len(csr) != 1:
                    raise ValueError(f"{point}: csr cells {[r['path'] for r in csr]} in synth_dc_modules.csv")
                per = peripherals(synth_mods[point], csr[0]["path"], point)
            except ValueError as e:
                problems.append(f"{tech} {e}")
                per = None
            if per is not None:
                common["peripherals_um2"] = per["area_um2"]
                common["csr_um2"] = f"{float(s['csr_um2']) - float(per['area_um2']):.4f}"
        split = [c for c in ("csr_um2", "ctrl_um2", "datapath_um2", "glue_um2", "peripherals_um2")
                 if common.get(c)]
        if split and abs(sum(float(common[c]) for c in split) - float(s["area_um2"])) > 0.01:
            problems.append(f"{tech} {point}: the split columns do not sum to area_um2")
        if source == "forge" or (p["tier"] == "untiered" and tech == REF_TECH_UNTIERED):
            psize = REF_SIZE
        else:
            psize = DEFAULT_SIZE.get(p["kernel"], "b64")
        try:
            parts = part_energy(source, mods.get((point, psize), []))
        except ValueError as e:
            problems.append(f"{tech} {e}")
            parts = {}
        if parts:
            parts["parts_size"] = psize
            if not any(r["size"] == psize and r.get("status") == "ok" for r in power[point]):
                problems.append(f"{tech} {point}: no ok run at its parts size {psize}")
        elif source in PARTS and any(r["size"] == psize and r.get("status") == "ok" for r in power[point]):
            problems.append(f"{tech} {point}: an ok run at {psize} but no module rows for it (X60)")
        runs = power.get(point, [])
        if not runs:
            problems.append(f"{tech} {point}: synthesized but no power row")
        for r in runs:
            row = dict(common)
            row.update({c: r.get(c, "") for c in ("size", "beats", "cycles", "e_clk_pj", "e_reg_pj", "e_seq_pj",
                                                    "e_comb_pj", "e_flop_pj", "e_dyn_pj", "p_dyn_uw", "e_run_pj",
                                                    "flop_bits", "e_bit_pj", "ram_reads", "ram_writes",
                                                    "e_ram_pj")})
            row["status"] = "ok" if r["status"] == "ok" else f"pwr: {r['status']}"
            if r.get("beats"):
                row["elements"] = str(int(r["beats"]) * int(p["w"]))
            if r.get("e_run_pj") and row.get("elements"):
                row["pj_per_elem"] = f"{float(r['e_run_pj']) / int(row['elements']):.6g}"
            if row["status"] == "ok":
                row.update(parts)
                # X63: a row whose own size has module rows (X60: every n2048 run) takes its parts from them
                if source in PARTS and r["size"] != psize and (point, r["size"]) in mods:
                    try:
                        row.update(part_energy(source, mods[(point, r["size"])]), parts_size=r["size"])
                    except ValueError as e:
                        problems.append(f"{tech} {e}")
            else:
                problems.append(f"{tech} {point} {r['size']}: {row['status']}")
            out.append(row)
    return out


def check_sizes(rows: list[dict], problems: list[str]) -> None:
    """Every ok point of a kernel has the same sizes; tier done has n2048 (X24)."""
    sizes = defaultdict(set)
    want = defaultdict(set)
    for r in rows:
        if r["status"].startswith("syn: "):
            continue
        sizes[(r["tech"], r["point"])].add(r["size"])
        if r["tool"] != "forge":
            want[(r["tech"], r["tier"], r["kernel"])].add(r["size"])
    for r in rows:
        if r["tier"] == "done" or r["tech"] == REF_TECH_UNTIERED:      # X24 (tier done), X55 and X61 (untiered)
            want[(r["tech"], r["tier"], r["kernel"])].add(REF_SIZE)
    for (tech, point), have in sorted(sizes.items()):
        tier, kernel = point.split("/")[:2]
        case = point.split("/")[-1].rsplit("_w", 1)[0]
        only = point.split("/")[-1].startswith("forge") or (tier, kernel, case) in N2048_ONLY
        need = {"n2048"} if only else want[(tech, tier, kernel)]
        if have != need:
            problems.append(f"{tech} {point}: sizes {sorted(have)}, expected {sorted(need)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="check only, write nothing")
    args = ap.parse_args()
    problems: list[str] = []
    rows = []
    for tech in TECHS:
        for source in SOURCES:
            got = rows_for(source, tech, problems)
            if not got:
                problems.append(f"{tech} {source}: no rows")
            rows += got
    # the same points on both technologies
    pts = defaultdict(set)
    for r in rows:
        pts[r["tech"]].add(r["point"])
    tool_of = {r["point"]: (r["tier"], r["tool"]) for r in rows}
    for a, b in ((TECHS[0], TECHS[1]), (TECHS[1], TECHS[0])):
        for point in sorted(pts[a] - pts[b]):
            if a == "nangate45" and tool_of[point] == NANGATE45_ONLY:
                continue
            problems.append(f"{point}: on {a} but not on {b}")
    check_sizes(rows, problems)
    keys = defaultdict(int)
    for r in rows:
        keys[(r["tech"], r["point"], r.get("size", ""))] += 1
    problems += [f"duplicate row: {' '.join(k)}" for k, n in keys.items() if n > 1]
    if problems:
        print("compare: not written, " + f"{len(problems)} problem(s):", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    def order(r):
        size = r.get("size", "")
        num = [int(x) for x in re.findall(r"\d+", size)] if size not in ("b64",) else [0]
        return (TECHS.index(r["tech"]), r["kernel"], int(r["W"]), TOOL_ORDER[r["tool"]], r["case"],
                size != "b64", num)

    rows.sort(key=order)
    counts = {}
    for tier in ("done", "untiered"):
        tier_rows = [r for r in rows if r["tier"] == tier]
        counts[tier] = len(tier_rows)
        if not args.check:
            out = ROOT / "results" / f"compare_{tier}.csv"
            with out.open("w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
                w.writeheader()
                w.writerows(tier_rows)
    by = defaultdict(int)
    for r in rows:
        by[(r["tier"], r["tool"])] += 1
    print("compare: " + ("checked" if args.check else "written") + ", " +
          ", ".join(f"{t} {n} rows" for t, n in counts.items()))
    for (tier, tool), n in sorted(by.items(), key=lambda x: (x[0][0], TOOL_ORDER[x[0][1]])):
        print(f"  {tier:9} {tool:6} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
