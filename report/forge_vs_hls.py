#!/usr/bin/env python3
"""report/forge_vs_hls.py - SYN1's joined table: snax-forge's accelerators beside hls-exercises' tier done.

  pixi run table

Reads only committed CSVs, per technology (nangate45, nangate15):
  results/hls/<tech>/synth_dc.csv, synth_dc_modules.csv, power_pt.csv, power_pt_modules.csv
  results/forge/<tech>/synth_dc.csv, synth_dc_modules.csv, power_pt.csv, power_pt_modules.csv
  results/hls/hls_cycles.csv   cosim's latencies: each HLS row's cycles must lie on cosim's line (X19)
and writes results/forge_vs_hls.md and results/forge_vs_hls_<tech>.csv.

Rows: per technology and kernel (vecadd, vecmul, vsum, dot), per W = 1 to 32, per case (HLS unopt, opt,
dace; forge `forge`, or `forge2` to `forge6` for dot 2 to 6), at the reference task n2048 only (X24). The
table lays the data out: no ratios, no ranking. HLS rows leave the module columns empty (the block is flat).
Every expected row must be present and `ok`, except the parked ones (PARKED), which must carry their status.
The script fails otherwise, and prints the counts. Its output depends on the CSVs only.
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
TECHS = ["nangate45", "nangate15"]
KERNELS = ["vecadd", "vecmul", "vsum", "dot"]
WS = [1, 2, 4, 8, 16, 32]
N = 2048
SIZE = "n2048"
FORGE_CASES = {"vecadd": ["forge"], "vecmul": ["forge"], "vsum": ["forge"],
               "dot": ["forge2", "forge3", "forge4", "forge5", "forge6"]}
HLS_CASES = {k: ["unopt", "opt", "dace"] for k in KERNELS}
DACE_WS = {"vecadd": WS, "vecmul": WS, "vsum": [1], "dot": [1]}     # hls-exercises' dace sweeps
PARKED = {("dot", "dace", 1): "skipped: needs a RAM macro"}         # HLS dot dace_w1 (RAM1)
MODULES = ["csr", "ctrl", "dp"]                                      # the wrapper's three instances

COLUMNS = ["tech", "kernel", "W", "side", "case", "point", "status", "cycles",
           "area_um2", "csr_um2", "ctrl_um2", "datapath_um2", "glue_um2", "ctrl_area_pct", "csr_area_pct",
           "e_run_nj", "csr_e_run_nj", "ctrl_e_run_nj", "datapath_e_run_nj", "ctrl_e_run_pct", "csr_e_run_pct",
           "pj_per_elem", "csr_pj_per_elem", "ctrl_pj_per_elem", "datapath_pj_per_elem",
           "e_comb_share_pct", "flops", "fmax_mhz"]

NOTES = [
    "Size n2048 on both sides: one task of N = 2048 elements, 2048 / W beats (X24). e_run is the dynamic energy of the busy window (e_dyn x cycles, X13, X20), pJ per element is e_run / 2048, e_comb share is e_comb / e_dyn.",
    "forge's columns csr, ctrl and datapath are the wrapper's three instances (`snax_forge_csr`, `snax_forge_ctrl`, `snax_forge_datapath`, X22); glue is the area DC leaves at the wrapper's own level. HLS rows leave them empty: its block is flat.",
    "forge's ElementwiseLanes has no registers (its registers sit in snax_cluster's streamers), while HLS opt holds its result register.",
    "Reset is synchronous in HLS and asynchronous in forge; on nangate15 every flop has an asynchronous reset or set pin either way (PITFALLS LIB1).",
    "forge dot 1 (two groups) is not in SYN1.",
    "matadd and rowsum are the same Verilog as vecadd and vsum on the HLS side (PITFALLS DC3) and as forge's vecadd and vsum rows, so they have no section; relu and axpy have no forge counterpart.",
    "fmax is DC's at the 10 ns clock, a lower bound (X2), not discussed.",
]


def read(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def by_point(rows: list[dict], size: str | None = None) -> dict:
    out = {}
    for r in rows:
        if size is not None and r.get("size") != size:
            continue
        if r["point"] in out:
            raise SystemExit(f"two rows for {r['point']} {size or ''}")
        out[r["point"]] = r
    return out


def cosim_lines(rows: list[dict]) -> dict:
    """{(kernel, case, W): (a, b)} through cosim's two sizes, tier done."""
    pts = {}
    for r in rows:
        if r["tier"] != "done" or r["cosim_lat_avg"] in ("", None):
            continue
        lc = int(re.search(r"loop_count=(\d+)", r["config"]).group(1))
        pts.setdefault((r["kernel"], r["case"], int(r["W"])), []).append((lc, float(r["cosim_lat_avg"])))
    out = {}
    for k, v in pts.items():
        if len(v) >= 2:
            (l1, c1), (l2, c2) = sorted(v)[:2]
            a = (c2 - c1) / (l2 - l1)
            out[k] = (a, c1 - a * l1)
    return out


def f(x, nd: int) -> str:
    return "" if x is None else f"{x:.{nd}f}"


def pct(a, b):
    return None if a is None or b in (None, 0) else 100.0 * a / b


def row_for(tech, kernel, w, side, case, syn, pwr, pmods, lines, problems) -> dict:
    point = f"done/{kernel}/{case}_w{w}"
    base = {"tech": tech, "kernel": kernel, "W": w, "side": side, "case": case, "point": point}
    s, p = syn.get(point), pwr.get(point)
    parked = PARKED.get((kernel, case, w)) if side == "hls" else None
    if parked:
        st = (s or {}).get("status", "")
        if not st.startswith(parked):
            problems.append(f"{tech} {point}: expected parked ({parked}), synthesis status {st!r}")
        return {**base, "status": st}
    if s is None or p is None:
        problems.append(f"{tech} {point}: missing {'synthesis' if s is None else 'n2048 power'} row")
        return {**base, "status": "missing"}
    if s["status"] != "ok" or p["status"] != "ok":
        problems.append(f"{tech} {point}: synthesis {s['status']!r}, power {p['status']!r}")
        return {**base, "status": f"synthesis {s['status']}, power {p['status']}"}
    cyc = int(p["cycles"])
    if side == "hls":
        ab = lines.get((kernel, case, w))
        lc = int(re.search(r"loop_count=(\d+)", p["config"]).group(1))
        if ab is None or abs(ab[0] * lc + ab[1] - cyc) > 1e-9:
            problems.append(f"{tech} {point}: cycles {cyc} not on cosim's line {ab}")
    area = float(s["area_um2"])
    e_run = float(p["e_run_pj"]) / 1000.0
    out = {**base, "status": "ok", "cycles": cyc, "area_um2": f(area, 1), "e_run_nj": f(e_run, 3),
           "pj_per_elem": f(1000.0 * e_run / N, 3),
           "e_comb_share_pct": f(pct(float(p["e_comb_pj"]), float(p["e_dyn_pj"])), 1),
           "flops": int(s["seq_cells"]), "fmax_mhz": f(float(s["fmax_mhz"]), 1)}
    if side == "forge":
        a = {k: float(s[f"{k}_um2"]) for k in ("csr", "ctrl", "datapath", "glue")}
        m = pmods.get(point, {})
        if sorted(m) != MODULES:
            problems.append(f"{tech} {point}: power modules {sorted(m)}, expected {MODULES}")
            return {**base, "status": "missing modules"}
        e = {k: m[k] * cyc / 1000.0 for k in MODULES}
        out.update({"csr_um2": f(a["csr"], 1), "ctrl_um2": f(a["ctrl"], 1), "datapath_um2": f(a["datapath"], 1),
                    "glue_um2": f(a["glue"], 1), "ctrl_area_pct": f(pct(a["ctrl"], area), 1),
                    "csr_area_pct": f(pct(a["csr"], area), 1),
                    "csr_e_run_nj": f(e["csr"], 3), "ctrl_e_run_nj": f(e["ctrl"], 3),
                    "datapath_e_run_nj": f(e["dp"], 3), "ctrl_e_run_pct": f(pct(e["ctrl"], e_run), 1),
                    "csr_e_run_pct": f(pct(e["csr"], e_run), 1),
                    "csr_pj_per_elem": f(1000.0 * e["csr"] / N, 3), "ctrl_pj_per_elem": f(1000.0 * e["ctrl"] / N, 3),
                    "datapath_pj_per_elem": f(1000.0 * e["dp"] / N, 3)})
    return out


def power_modules(rows: list[dict]) -> dict:
    """{point: {csr|ctrl|dp: e_dyn_pj}} from the wrapper's direct instances."""
    out = {}
    for r in rows:
        parts = r["path"].split("/")
        if len(parts) == 2 and parts[1] in MODULES:
            out.setdefault(r["point"], {})[parts[1]] = float(r["e_dyn_pj"])
    return out


MD_COLS = [("case", "case"), ("W", "W"), ("status", "status"), ("cycles", "cycles"), ("area_um2", "area µm²"),
           ("csr_um2", "csr µm²"), ("ctrl_um2", "ctrl µm²"), ("datapath_um2", "dp µm²"), ("glue_um2", "glue µm²"),
           ("ctrl_area_pct", "ctrl % area"), ("csr_area_pct", "csr % area"), ("e_run_nj", "e_run nJ"),
           ("csr_e_run_nj", "csr nJ"), ("ctrl_e_run_nj", "ctrl nJ"), ("datapath_e_run_nj", "dp nJ"),
           ("ctrl_e_run_pct", "ctrl % e_run"), ("csr_e_run_pct", "csr % e_run"), ("pj_per_elem", "pJ/elem"),
           ("csr_pj_per_elem", "csr pJ/elem"), ("ctrl_pj_per_elem", "ctrl pJ/elem"),
           ("datapath_pj_per_elem", "dp pJ/elem"), ("e_comb_share_pct", "comb %"), ("flops", "flops"),
           ("fmax_mhz", "fmax MHz")]


def main() -> int:
    lines = cosim_lines(read(RES / "hls" / "hls_cycles.csv"))
    problems, md, counts = [], [], {}
    tables = {}
    for tech in TECHS:
        hs, fs = by_point(read(RES / "hls" / tech / "synth_dc.csv")), by_point(read(RES / "forge" / tech / "synth_dc.csv"))
        hp = by_point(read(RES / "hls" / tech / "power_pt.csv"), SIZE)
        fp = by_point(read(RES / "forge" / tech / "power_pt.csv"), SIZE)
        read(RES / "hls" / tech / "synth_dc_modules.csv")      # read for completeness: the HLS block is flat
        read(RES / "hls" / tech / "power_pt_modules.csv")
        read(RES / "forge" / tech / "synth_dc_modules.csv")    # forge's module areas are synth_dc.csv's columns
        fm = power_modules(read(RES / "forge" / tech / "power_pt_modules.csv"))
        rows = []
        for k in KERNELS:
            for w in WS:
                for c in HLS_CASES[k]:
                    if c == "dace" and w not in DACE_WS[k]:
                        continue
                    rows.append(row_for(tech, k, w, "hls", c, hs, hp, {}, lines, problems))
                for c in FORGE_CASES[k]:
                    rows.append(row_for(tech, k, w, "forge", c, fs, fp, fm, lines, problems))
        tables[tech] = rows
        for side in ("hls", "forge"):
            st = [r["status"] for r in rows if r["side"] == side]
            counts[(tech, side)] = {"ok": sum(s == "ok" for s in st),
                                    "parked": sum(s.startswith("skipped") for s in st),
                                    "failed": sum(s != "ok" and not s.startswith("skipped") for s in st)}
    for (tech, side), c in counts.items():
        print(f"{tech} {side}: {c['ok']} ok, {c['parked']} parked, {c['failed']} failed")
    if problems:
        print("\n".join(problems), file=sys.stderr)
        print(f"forge_vs_hls: {len(problems)} problems, nothing written", file=sys.stderr)
        return 1

    md.append("# SYN1: snax-forge beside HLS tier done, n2048")
    md.append("")
    md.append("Written by `report/forge_vs_hls.py` (`pixi run table`) from the committed CSVs in `results/hls/<tech>/` and `results/forge/<tech>/` and `results/hls/hls_cycles.csv`; the same rows per technology in `results/forge_vs_hls_<tech>.csv`. The table lays the data out: no ratios and no ranking.")
    md.append("")
    md.append("## Notes")
    md.append("")
    md += [f"- {n}" for n in NOTES]
    md.append("")
    md.append("## Counts")
    md.append("")
    md.append("| tech | side | ok | parked | failed |")
    md.append("|---|---|---|---|---|")
    for (tech, side), c in counts.items():
        md.append(f"| {tech} | {side} | {c['ok']} | {c['parked']} | {c['failed']} |")
    for tech in TECHS:
        md.append("")
        md.append(f"## {tech}")
        for k in KERNELS:
            md.append("")
            md.append(f"### {k}, {tech}")
            md.append("")
            md.append("| " + " | ".join(h for _, h in MD_COLS) + " |")
            md.append("|" + "---|" * len(MD_COLS))
            for r in tables[tech]:
                if r["kernel"] == k:
                    md.append("| " + " | ".join(str(r.get(c, "")) for c, _ in MD_COLS) + " |")
    (RES / "forge_vs_hls.md").write_text("\n".join(md) + "\n")
    for tech in TECHS:
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        for r in tables[tech]:
            w.writerow({c: r.get(c, "") for c in COLUMNS})
        (RES / f"forge_vs_hls_{tech}.csv").write_text(buf.getvalue())
    print(f"wrote {(RES / 'forge_vs_hls.md').relative_to(ROOT)}, "
          + ", ".join(f"results/forge_vs_hls_{t}.csv ({len(tables[t])} rows)" for t in TECHS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
