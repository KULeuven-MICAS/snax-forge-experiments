#!/usr/bin/env python3
"""report/control_roles.py - every register of SYN1's points, forge and HLS, given one role read from the RTL.

  pixi run control

Reads (changes none of them):
  results/analysis/control/roles.json            per side, register pattern -> role, with what the register holds,
                                                 when it loads, what reads it, and its RTL (and Chisel) file and line
  results/analysis/syn1/split_regs_<tech>.csv    SYN1's registers: flops, cone, internal and switching energy per cycle
  results/analysis/syn1/split_<tech>.csv         SYN1's per-point totals, to check the join against
  rtl/forge/<point>/accelerator.json, rtl/sv/    forge's bundles (forge/bundles.py): the CSR order and ctrl's loads,
                                                 to check the forge roles against the RTL of every point
and writes results/analysis/control/roles_<tech>.csv (split_regs' columns plus role and layer) and
results/analysis/control/control_roles.md. Fails if a register matches no entry or more than one, if a forge CSR's role
disagrees with accelerator.json, if a ctrl `_r` register's role disagrees with how ctrl loads it, or if the per-point
flop totals differ from split_<tech>.csv. Every number in the note is computed here.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / "results" / "analysis" / "syn1"
OUT = ROOT / "results" / "analysis" / "control"
FORGE_RTL = ROOT / "rtl" / "forge"
TECHS = ["nangate45", "nangate15"]
KERNELS = ["vecadd", "vecmul", "vsum", "dot"]
WS = [1, 2, 4, 8, 16, 32]
HLS_CASES = ["unopt", "opt", "dace"]
FORGE_CASES = {"vecadd": ["forge"], "vecmul": ["forge"], "vsum": ["forge"],
               "dot": ["forge2", "forge3", "forge4", "forge5", "forge6"]}
LAYERS = ["interface", "kernel", "datapath", "any"]
HLS_RTL = "hls-exercises/rtl/done/<kernel>/<case>_w<W>/"


class Fail(Exception):
    pass


def read(path: Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def label(case: str) -> str:
    return {"forge": "forge", "forge2": "dot 2", "forge3": "dot 3", "forge4": "dot 4", "forge5": "dot 5",
            "forge6": "dot 6"}.get(case, f"HLS {case}")


def cases(k: str) -> list[str]:
    return FORGE_CASES[k] + HLS_CASES


def table(head: list[str], rows: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(map(str, r)) + " |" for r in rows]


# ---------------------------------------------------------------- the join
def entries(roles: dict) -> dict:
    out = {"forge": [], "hls": []}
    for i, e in enumerate(roles["forge"]):
        out["forge"].append({**e, "id": f"forge#{i}", "rx": re.compile(e["pattern"])})
    for i, e in enumerate(roles["hls"]):
        out["hls"].append({**e, "id": f"hls#{i}", "rx": re.compile(e["pattern"])})
    return out


def match(es: dict, r: dict) -> list[dict]:
    hits = []
    for e in es[r["side"]]:
        if r["side"] == "hls":
            if r["kernel"] not in e["kernels"] or r["case"] not in e["cases"]:
                continue
            if "W" in e and int(r["W"]) not in e["W"]:
                continue
        if e["rx"].search(r["register"]):
            hits.append(e)
    return hits


def forge_checks(rows: list[dict]) -> int:
    """The forge roles against each point's bundle: a CSR register's index names START (csr_start) or a read-write
    setting (csr_setting) in accelerator.json; a ctrl `_r` register is a product of settings (derived_setting) exactly
    when ctrl loads it with a `*`. Returns the number of registers checked."""
    if not FORGE_RTL.is_dir():
        raise Fail(f"no {FORGE_RTL.relative_to(ROOT)}: build the bundles (pixi run forge-rtl, X21)")
    n = 0
    cache = {}
    for r in rows:
        if r["side"] != "forge":
            continue
        b = FORGE_RTL / r["point"]
        if b not in cache:
            acc = json.loads((b / "accelerator.json").read_text())
            csrs = {}      # offset -> CSR, the group's and its units' (regs_<i> is the CSR at offset i)
            for g in acc["groups"]:
                for c in g["csrs"] + [c for u in g.get("units", []) for c in u.get("csrs", [])]:
                    if c["offset"] in csrs:
                        raise Fail(f"{r['point']}: two CSRs at offset {c['offset']}")
                    csrs[c["offset"]] = c
            ctrl = "\n".join(p.read_text() for p in sorted((b / "rtl" / "sv").glob("snax_forge_*_ctrl.sv")))
            cache[b] = (csrs, ctrl)
        csrs, ctrl = cache[b]
        m = re.fullmatch(r"csr/regs_(\d+)", r["register"])
        if m:
            c = csrs[int(m.group(1))]
            want = "csr_start" if c["name"] == "START" else "csr_setting"
            if c.get("access") != "rw" or r["role"] != want:
                raise Fail(f"{r['point']} {r['register']}: accelerator.json says {c['name']} ({c.get('access')}), role {r['role']}")
            n += 1
        m = re.fullmatch(r"ctrl/ctrl/(\w+_r)", r["register"])
        if m:
            loads = re.findall(rf"^\s*{m.group(1)}\s*<=\s*([^;]*);", ctrl, re.M)
            loads = [x for x in loads if not re.fullmatch(r"32'h0", x.strip())]
            if len(loads) != 1:
                raise Fail(f"{r['point']} {r['register']}: {len(loads)} loads in ctrl")
            want = "derived_setting" if "*" in loads[0] else "setting_latch"
            if r["role"] != want:
                raise Fail(f"{r['point']} {r['register']}: ctrl loads `{loads[0]}`, role {r['role']}")
            n += 1
    return n


def main() -> int:
    roles = json.loads((OUT / "roles.json").read_text())
    layer_of = {role: layer for layer, rs in roles["layers"].items() for role in rs}
    es = entries(roles)
    used = defaultdict(int)
    R = {}            # tech -> rows with role and layer
    for tech in TECHS:
        rows = read(SPLIT / f"split_regs_{tech}.csv")
        for r in rows:
            hits = match(es, r)
            if len(hits) != 1:
                raise Fail(f"{tech} {r['point']} {r['register']}: {len(hits)} roles ({', '.join(h['id'] + ' ' + h['pattern'] for h in hits)})")
            e = hits[0]
            used[e["id"]] += 1
            r["role"], r["layer"], r["entry"] = e["role"], layer_of[e["role"]], e["id"]
            r["desc"] = e["description"]
            r["flops"], r["e"] = int(r["flops"]), float(r["e_int_pj"]) + float(r["e_sw_pj"])
        R[tech] = rows
    unused = [e["id"] + " " + e["pattern"] for side in es.values() for e in side if not used[e["id"]]]
    if unused:
        raise Fail(f"roles.json entries no register uses: {unused}")
    nchk = sum(forge_checks(R[t]) for t in TECHS)

    # totals against split_<tech>.csv: flops and energy per point and cone
    worst = (0.0, "")
    nflop_bad = 0
    for tech in TECHS:
        ref = defaultdict(lambda: [0, 0.0])
        for r in read(SPLIT / f"split_{tech}.csv"):
            if r["kind"] == "flop":
                ref[(r["point"], r["cone"])][0] += int(r["cells"])
                ref[(r["point"], r["cone"])][1] += float(r["e_dyn_pj"])
        got = defaultdict(lambda: [0, 0.0])
        for r in R[tech]:
            got[(r["point"], r["cone"])][0] += r["flops"]
            got[(r["point"], r["cone"])][1] += r["e"]
        for k in set(ref) | set(got):
            if ref[k][0] != got[k][0]:
                nflop_bad += 1
            d = abs(ref[k][1] - got[k][1])
            if d > worst[0]:
                worst = (d, f"{tech} {k[0]} {k[1]}")
    if nflop_bad or worst[0] > 1e-3:
        raise Fail(f"totals differ from split_<tech>.csv: {nflop_bad} flop counts, largest energy difference {worst[0]:.6f} pJ ({worst[1]})")

    OUT.mkdir(parents=True, exist_ok=True)
    cols = list(read(SPLIT / "split_regs_nangate45.csv")[0].keys()) + ["role", "layer"]
    for tech in TECHS:
        with (OUT / f"roles_{tech}.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, cols, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for r in sorted(R[tech], key=lambda r: (r["side"], r["point"], r["cone"], r["register"])):
                w.writerow({**r, "flops": r["flops"]})

    note(roles, R, layer_of, nchk, worst)
    print(f"wrote {(OUT / 'control_roles.md').relative_to(ROOT)} and roles_<tech>.csv: "
          f"{sum(len(v) for v in R.values())} registers, {nchk} forge checks, largest energy difference {worst[0]:.6f} pJ")
    return 0


# ---------------------------------------------------------------- the note
def note(roles, R, layer_of, nchk, worst):
    order = [r for rs in roles["layers"].values() for r in rs]
    by = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))     # (tech, kernel, case, W) -> role -> [flops, pJ]
    regs = defaultdict(list)
    for tech, rows in R.items():
        for r in rows:
            key = (tech, r["kernel"], r["case"], int(r["W"]))
            by[key][r["role"]][0] += r["flops"]
            by[key][r["role"]][1] += r["e"]
            regs[key].append(r)

    def cell(x):
        return f"{x[0]} · {x[1]:.2f}" if x[0] else ""

    def lay(key, layer):
        s = [0, 0.0]
        for role, x in by[key].items():
            if layer_of[role] == layer:
                s[0] += x[0]
                s[1] += x[1]
        return s

    md = ["# Control roles: every register of SYN1's points, forge and HLS", ""]
    md.append(f"Written by `report/control_roles.py` (`pixi run control`) from `roles.json` (the roles, read from the RTL) and SYN1's `results/analysis/syn1/split_regs_<tech>.csv` (each register's flops and its internal and switching energy per cycle from PrimePower, X23). Every number is computed. Forge's RTL is snax-forge {roles['snax_forge_commit'][:7]}; its control RTL at W = 8 is in `src/` (X26). HLS's Verilog is in hls-exercises, `{HLS_RTL}`.")
    md.append("")
    md.append("Each register has one role; the role's layer: **interface** (what HLS's block leaves to its driver: CSR settings, the START word, the read-back buffer, the cycle counter), **kernel** (settings latched or derived at start, progress counters, FSM state, pipeline control), **datapath** (data stages and data state). Energy is pJ per cycle (internal plus switching power of the register's flops, over the busy window); a cell reads `flops · pJ per cycle`. Flops only: the logic around the registers is in SYN1's section 9 by cone, not by role.")
    md.append("")
    nreg = sum(len(v) for v in R.values())
    md.append(f"**Checks** (all passed): each of the {nreg} register rows (both technologies) matches exactly one entry of `roles.json`, and every entry is used; {nchk} forge registers checked against their own bundle (a CSR's index against `accelerator.json`, a ctrl `_r`'s role against how ctrl loads it); the flops per point and cone equal `split_<tech>.csv`'s, and the energy within {worst[0]:.6f} pJ per cycle.")
    md.append("")

    # a
    md += ["## a. Per kernel at W = 8, nangate45", ""]
    for k in KERNELS:
        cs = [c for c in cases(k) if by.get(("nangate45", k, c, 8))]
        md.append(f"**{k}**: flops · pJ per cycle")
        md.append("")
        rows = []
        for layer in LAYERS:
            rl = [ro for ro in order if layer_of[ro] == layer]
            for ro in rl:
                vals = [by[("nangate45", k, c, 8)].get(ro, [0, 0.0]) for c in cs]
                if any(v[0] for v in vals):
                    rows.append([layer, ro] + [cell(v) for v in vals])
            vals = [lay(("nangate45", k, c, 8), layer) for c in cs]
            if any(v[0] for v in vals):
                rows.append([f"**{layer}**", "**all**"] + [f"**{cell(v)}**" if v[0] else "" for v in vals])
        tot = [[sum(x[0] for x in by[("nangate45", k, c, 8)].values()), sum(x[1] for x in by[("nangate45", k, c, 8)].values())] for c in cs]
        rows.append(["**all**", ""] + [f"**{cell(v)}**" if v[0] else "" for v in tot])
        md += table(["layer", "role"] + [label(c) for c in cs], rows)
        md.append("")

    # b
    md += ["## b. Per layer across W, both technologies", ""]
    for tech in TECHS:
        for k in KERNELS:
            md.append(f"**{k}, {tech}**: flops · pJ per cycle per layer")
            md.append("")
            rows = []
            for c in cases(k):
                if not any(by.get((tech, k, c, w)) for w in WS):
                    continue
                for layer in LAYERS[:3]:
                    vals = [lay((tech, k, c, w), layer) if by.get((tech, k, c, w)) else None for w in WS]
                    if any(v and v[0] for v in vals):
                        rows.append([label(c), layer] + [cell(v) if v else "" for v in vals])
            md += table(["case", "layer"] + [f"W = {w}" for w in WS], rows)
            md.append("")

    # c
    md += ["## c. The registers at W = 8, nangate45", ""]
    md.append(f"Per point, the registers of each `roles.json` entry together: their names, flops, cone (SYN1's), role, pJ per cycle and what they do. HLS's Verilog: `{HLS_RTL}`; forge's control: `src/<kernel>/<case>_w8/`.")
    md.append("")
    ents = {e_id: e for e_id, e in ((f"{s}#{i}", e) for s in ("forge", "hls") for i, e in enumerate(roles[s]))}
    for k in KERNELS:
        for c in cases(k):
            key = ("nangate45", k, c, 8)
            if key not in regs:
                continue
            md.append(f"**`done/{k}/{c}_w8`**")
            md.append("")
            grp = defaultdict(list)
            for r in regs[key]:
                grp[(r["entry"], r["cone"])].append(r)
            rows = []
            for (eid, cone), rr in sorted(grp.items(), key=lambda x: (LAYERS.index(layer_of[x[1][0]["role"]]), order.index(x[1][0]["role"]), x[0])):
                names = sorted(r["register"] for r in rr)
                shown = ", ".join(f"`{n}`" for n in names[:6]) + (f", … ({len(names)} registers)" if len(names) > 6 else "")
                e = ents[eid]
                rows.append([shown, sum(r["flops"] for r in rr), cone, rr[0]["role"], f"{sum(r['e'] for r in rr):.3f}",
                             e["description"] + f" ({e['rtl']}" + (f"; {e['chisel']}" if "chisel" in e else "") + ")"])
            md += table(["registers", "flops", "cone", "role", "pJ/cycle", "what it does (where)"], rows)
            md.append("")

    # d
    md += ["## d. Cone against layer, and unclear registers", ""]
    dis = [r for t in TECHS for r in R[t] if r["layer"] != "any" and (r["layer"] == "datapath") != (r["cone"] == "data")]
    md.append(f"A register disagrees when its role's layer is datapath and SYN1's cone is control, or the other way round. {len(dis)} register rows disagree" + (":" if dis else "."))
    md.append("")
    if dis:
        rows = sorted({(r["side"], r["point"], r["register"], r["cone"], r["role"]) for r in dis})
        md += table(["side", "point", "register", "cone", "role"], [list(x) for x in rows])
        md.append("")
    unc = [r for t in TECHS for r in R[t] if r["role"] == "unclear"]
    md.append(f"`unclear` registers: {len(unc)}" + ("." if not unc else ":"))
    md.append("")
    if unc:
        rows = sorted({(r["side"], r["point"], r["register"], r["desc"]) for r in unc})
        md += table(["side", "point", "register", "why"], [list(x) for x in rows])
        md.append("")
    (OUT / "control_roles.md").write_text("\n".join(md))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Fail as e:
        print(f"FAIL: {e}")
        sys.exit(1)
