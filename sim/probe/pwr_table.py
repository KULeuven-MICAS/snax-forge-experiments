#!/usr/bin/env python3
"""sim/probe/pwr_table.py: the run note's energy table from the probe's PT and DC reports.

  pixi run python sim/probe/pwr_table.py <pt_dir> <dc_power.rpt> [<dc_uniform_power.rpt>]

<pt_dir> holds one folder per PT run (P0, U, P1q, P1s, P1v, ...), each with reports/power.rpt,
units.rpt and switching_activity.rpt (sim/probe/pt_power.tcl). Units come from the reports:
PT's report_units 'User Specified Power Unit', DC's 'Dynamic Power Units' and 'Leakage Power
Units', as syn/syn.py reads them. Energy per cycle of a group is (internal + switching) x
the clock period; leakage is in uW. Coverage is the share of nets 'From Activity File'.
"""
import re
import sys
from pathlib import Path

GROUPS = {"clock_network": "clk", "register": "reg", "sequential": "seq", "combinational": "comb"}
W = {"W": 1e6, "mW": 1e3, "uW": 1.0, "nW": 1e-3, "pW": 1e-6}


def pt_run(d):
    rep = d / "reports"
    unit = re.search(r"User Specified Power Unit\s*:\s*([0-9.eE+-]+)\s*Watt", (rep / "units.rpt").read_text())
    to_uw = float(unit.group(1)) * 1e6
    text = (rep / "power.rpt").read_text()
    g = {}
    for name in GROUPS:
        m = re.search(rf"^{name}\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
        g[name] = tuple(float(x) * to_uw for x in m.groups())
    cov = ""
    sa = rep / "switching_activity.rpt"
    if sa.is_file():
        m = re.search(r"^\s*Nets\s+(\d+)\(([\d.]+)%\).*?(\d+)\s*$", sa.read_text(), re.M)
        if m:
            cov = f"{m.group(2)}% ({m.group(1)}/{m.group(3)} nets)"
    return g, cov


def dc_run(f):
    text = Path(f).read_text()
    def unit(label):
        m = re.search(rf"{label}\s*=\s*([0-9.]+)\s*([munp]?W)\b", text)
        return float(m.group(1)) * W[m.group(2)]
    dyn, leak = unit("Dynamic Power Units"), unit("Leakage Power Units")
    g = {}
    for name in GROUPS:
        m = re.search(rf"^{name}\s+(\S+)\s+(\S+)\s+(\S+)", text, re.M)
        g[name] = (float(m.group(1)) * dyn, float(m.group(2)) * dyn, float(m.group(3)) * leak)
    return g, "(default activity)"


def energies(g, clock_ns):
    e = {GROUPS[n]: (i + s) * clock_ns / 1000.0 for n, (i, s, _) in g.items()}   # uW x ns -> pJ
    e["total"] = sum(e.values())
    e["leak_uw"] = sum(l for _, _, l in g.values())
    return e


def main():
    pt_dir, dc_rpt = Path(sys.argv[1]), sys.argv[2]
    clock_ns = 10.0   # the synthesis clock: tech.json resolved clock_ns of the probe run
    rows = {"DC": dc_run(dc_rpt)}
    if len(sys.argv) > 3:
        rows["DC_U"] = (dc_run(sys.argv[3])[0], "(uniform activity)")
    for d in sorted(pt_dir.iterdir()):
        if (d / "reports" / "power.rpt").is_file() and (d / "reports" / "units.rpt").is_file():
            rows[d.name] = pt_run(d)
    print("| run | e_clk | e_reg | e_seq | e_comb | e_total | leakage (uW) | coverage |")
    print("|---|---|---|---|---|---|---|---|")
    e = {}
    for k, (g, cov) in rows.items():
        e[k] = energies(g, clock_ns)
        r = e[k]
        print(f"| {k} | {r['clk']:.4f} | {r['reg']:.4f} | {r['seq']:.4f} | {r['comb']:.4f} | "
              f"{r['total']:.4f} | {r['leak_uw']:.3f} | {cov} |")
    def ratio(a, b, key="total"):
        return e[a][key] / e[b][key] if a in e and b in e and e[b][key] else float("nan")
    print()
    for a, b in [("P0", "DC"), ("U", "DC_U")]:
        print(f"{a}/{b}: " + ", ".join(f"{k} {ratio(a, b, k):.4f}" for k in ("clk", "reg", "comb", "total", "leak_uw")))
    for src in "qsv":
        print(f"[{src}] P1/P0 {ratio('P1' + src, 'P0'):.4f}  P2/P0 {ratio('P2' + src, 'P0'):.4f}  "
              f"forge/full busy P1/P2 {ratio('P1' + src, 'P2' + src):.4f}  idle P3/P4 {ratio('P3' + src, 'P4' + src):.4f}  "
              f"idle/busy forge P3/P1 {ratio('P3' + src, 'P1' + src):.4f}  full P4/P2 {ratio('P4' + src, 'P2' + src):.4f}")
    for p in ("P1", "P2", "P3", "P4"):
        print(f"{p}: Questa SAIF / VCD {ratio(p + 'q', p + 'v'):.4f}, vcd2saif / VCD {ratio(p + 's', p + 'v'):.4f}")


if __name__ == "__main__":
    main()
