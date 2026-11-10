#!/usr/bin/env python3
"""forge/ctrl2_checks.py - CTRL2 R5's checks of the forge points rebuilt on snax-forge D168 (run note, step 5).

  pixi run python forge/ctrl2_checks.py flops OUT_JSON [--tech T]
      the flops of every forge point's control (the <tag>_ctrl instance and its children) counted in its mapped
      netlist (syn/runs/forge/<tech>/<point>.zip), per point; run before the points are resynthesized to keep
      the old counts (the netlists are overwritten)
  pixi run python forge/ctrl2_checks.py table OLD_FLOPS_JSON OLD_REV [--tech T] [--md OUT_MD]
      per point of W <= 16: the power status (an ok row means every output matched sim/ref.py), the window
      against BUSY_COUNTER read back and Part A's window (OLD_REV's power_pt.csv), the datapath area against
      Part A's, the ctrl's flops in the new netlist against snax-forge's estimate/bits.py count
      (forge/query.py ctrl_bits on the bundle's accelerator.json) and against OLD_FLOPS_JSON, and the csr's area
      whole and without its peripherals (X65, results/compare_*.csv). Exit 1 when a hard check fails
      (status, window = BUSY_COUNTER, window = Part A's, flops = bits.py); a datapath shift over 1 % is reported.

A flop is a Nangate cell whose name starts DFF or SDFF; a latch (DLH, DLL) is counted apart and must be 0.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arc"))
sys.path.insert(0, str(ROOT / "sim"))
import arc  # noqa: E402

WS = (1, 2, 4, 8, 16)
INST = re.compile(r"^\s*(\\?[\w$]+)\s+(\\?\S+)\s*\(", re.M)
KEYWORDS = {"module", "input", "output", "inout", "wire", "assign", "reg", "endmodule", "supply0", "supply1", "tri"}


def points() -> list[str]:
    return [p["point"] for p in json.loads((ROOT / "forge" / "points.json").read_text())
            if int(p["W"]) in WS]


def netlist(tech: str, point: str) -> tuple[str, str]:
    z = ROOT / "syn" / "runs" / "forge" / tech / f"{point}.zip"
    (v,) = [n for n in arc.names(z) if n.startswith("out/") and n.endswith("_mapped.v")]
    return v[len("out/"):-len("_mapped.v")], arc.read_text(z, v)


def modules(text: str) -> dict[str, list[str]]:
    """module -> the cell or module names it instantiates, one entry per instance."""
    out = {}
    for m in re.finditer(r"^module\s+(\S+)\s*\((.*?)^endmodule", text, re.S | re.M):
        body = m.group(2).split(";", 1)[1] if ";" in m.group(2) else ""
        out[m.group(1)] = [ref for ref, _ in INST.findall(body) if ref not in KEYWORDS]
    return out


def count(mods: dict, top: str, kind) -> int:
    return sum(count(mods, r, kind) if r in mods else int(kind(r)) for r in mods[top])


def ctrl_flops(tech: str, point: str) -> dict:
    top, text = netlist(tech, point)
    mods = modules(text)
    tag = top[: -len("_shell_wrapper")]
    ctrl = [m for m in mods if re.fullmatch(rf"{re.escape(tag)}_ctrl", m)]
    if len(ctrl) != 1:
        raise SystemExit(f"{point}: ctrl modules {ctrl} (tag {tag})")
    groups = {m: count(mods, m, lambda r: r.startswith(("DFF", "SDFF")))
              for m in mods if re.fullmatch(rf"{re.escape(tag)}_\w+_ctrl", m) and m != ctrl[0]}
    return {"top": top, "ctrl": ctrl[0],
            "flops": count(mods, ctrl[0], lambda r: r.startswith(("DFF", "SDFF"))),
            "latches": count(mods, ctrl[0], lambda r: r.startswith(("DLH", "DLL"))),
            "groups": groups}


def rows(path_or_text, text: bool = False) -> dict:
    fh = io.StringIO(path_or_text) if text else open(path_or_text, newline="")
    with fh:
        return {r["point"]: r for r in csv.DictReader(fh)}


def at(rev: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{rev}:{path}"], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def bits_of(point: str) -> dict:
    """forge/query.py ctrl_bits on the bundle's accelerator.json, in snax-forge's environment."""
    from sources import forge as fsrc  # sim/sources/forge.py: query() runs forge/query.py there

    z = ROOT / "rtl" / "forge" / f"{point}.zip"
    with arc.unpacked(z, ["accelerator.json"]) as d:
        return fsrc.query("ctrl_bits", str(Path(d) / "accelerator.json"))


def cmd_flops(args) -> int:
    out = {p: ctrl_flops(args.tech, p) for p in points()}
    Path(args.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"{len(out)} points, flops {min(v['flops'] for v in out.values())} to "
          f"{max(v['flops'] for v in out.values())}, latches {sum(v['latches'] for v in out.values())}")
    return 0


def cmd_table(args) -> int:
    t = args.tech
    old_flops = json.loads(Path(args.old_flops).read_text())
    base = f"results/forge/{t}"
    pw_new, syn_new = rows(ROOT / base / "power_pt.csv"), rows(ROOT / base / "synth_dc.csv")
    pw_old, syn_old = rows(at(args.rev, f"{base}/power_pt.csv"), True), rows(at(args.rev, f"{base}/synth_dc.csv"), True)
    cmp = {}
    for tier in ("done", "untiered"):
        for r in csv.DictReader(open(ROOT / "results" / f"compare_{tier}.csv", newline="")):
            if r["tech"] == t and r["tool"] == "forge" and r["size"] == "n2048":
                cmp[r["point"]] = r
    head = ["point", "status", "window", "BUSY_COUNTER", "Part A window", "expected", "datapath µm² (Part A)",
            "shift", "ctrl flops (Part A)", "bits.py", "csr µm² whole", "csr without peripherals", "peripherals µm²"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    hard, soft = [], []
    for p in points():
        n, o, s, so = pw_new.get(p, {}), pw_old[p], syn_new.get(p, {}), syn_old[p]
        fl = ctrl_flops(t, p)
        b = bits_of(p)
        est = sum(v["bits"] for v in b.values())
        dp_new, dp_old = float(s.get("datapath_um2") or "nan"), float(so["datapath_um2"])
        shift = (dp_new - dp_old) / dp_old * 100
        c = cmp.get(p, {})
        ok = n.get("status") == "ok"
        if not ok:
            hard.append(f"{p}: power {n.get('status')}")
        if n.get("cycles") != n.get("counter"):
            hard.append(f"{p}: window {n.get('cycles')} != BUSY_COUNTER {n.get('counter')}")
        if n.get("cycles") != o["cycles"]:
            hard.append(f"{p}: window {n.get('cycles')} != Part A's {o['cycles']}")
        if fl["flops"] != est or fl["latches"]:
            hard.append(f"{p}: ctrl flops {fl['flops']} (latches {fl['latches']}), bits.py {est} {b}")
        if abs(shift) > 1:
            soft.append(f"{p}: datapath {dp_old:.1f} -> {dp_new:.1f} µm² ({shift:+.2f} %)")
        lines.append(f"| {p} | {n.get('status', 'missing')} | {n.get('cycles', '')} | {n.get('counter', '')} | "
                     f"{o['cycles']} | {n.get('expected_cycles', '')} | {dp_new:,.1f} ({dp_old:,.1f}) | {shift:+.2f} % | "
                     f"{fl['flops']} ({old_flops[p]['flops']}) | {est} | {float(s.get('csr_um2') or 'nan'):,.1f} | "
                     f"{float(c.get('csr_um2') or 'nan'):,.1f} | {float(c.get('peripherals_um2') or 'nan'):,.1f} |")
    text = "\n".join(lines) + "\n"
    if args.md:
        Path(args.md).write_text(text)
    else:
        print(text)
    print(f"{len(points())} points; hard failures {len(hard)}; datapath shifts over 1 %: {len(soft)}")
    for x in hard + soft:
        print("  " + x)
    return 1 if hard else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("flops")
    p.add_argument("out")
    p.add_argument("--tech", default="nangate45")
    p.set_defaults(fn=cmd_flops)
    p = sub.add_parser("table")
    p.add_argument("old_flops")
    p.add_argument("rev")
    p.add_argument("--tech", default="nangate45")
    p.add_argument("--md")
    p.set_defaults(fn=cmd_table)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
