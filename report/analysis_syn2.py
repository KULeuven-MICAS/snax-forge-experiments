#!/usr/bin/env python3
"""report/analysis_syn2.py - SYN2: SYN1's forge points before and after snax-forge's CTRL1, and against HLS.

  pixi run syn2

Reads, per technology (nangate45, nangate15):
  before  SYN1's forge CSVs at the pinned commit PIN, through `git show PIN:<path>` (not copies):
          results/forge/<tech>/synth_dc.csv, power_pt.csv, power_pt_modules.csv
  after   the same files in the working tree (SYN2, docs/DECISIONS.md X27)
  HLS     results/hls/<tech>/synth_dc.csv and power_pt.csv (tier done, size n2048, seed 0)
and writes results/analysis/syn2/syn2_before_after.md. Every number is computed from those files.

Section 1, forge before and after: per point and technology, rows csr, ctrl, datapath and total (the
total is the whole wrapper, glue included). Area from synth_dc.csv (csr_um2, ctrl_um2, datapath_um2,
area_um2); pJ per cycle from power_pt_modules.csv's e_dyn_pj at snax_forge_shell_wrapper/<csr|ctrl|dp>
and power_pt.csv's e_dyn_pj for the total; e_run = pJ per cycle x cycles (power_pt.csv's e_run_pj for the
total). Section 2, forge against HLS: forge's csr, its kernel (ctrl + datapath) and its total, before and
after, beside HLS unopt, opt and dace (the whole block), for area, e_run and pJ per cycle.

Checks, each a failure: every expected row present and ok on both sides; every before row names
snax-forge BEFORE_FORGE and every after row one other commit; the size, seed and clock as SYN1's.
Warnings, listed in the md: a point whose cycles differ before and after by more than CYCLE_WARN, and
a module sum (csr + ctrl + datapath) that differs from the top by more than SUM_WARN, area or energy.
"""
from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
OUT = RES / "analysis" / "syn2" / "syn2_before_after.md"
PIN = "f99c4238e4653b82ed4bded7344b5c48be4516f7"       # snax-forge-experiments main with SYN1's results
BEFORE_FORGE = "32dbcc6112eccb8a4943029a61a99220ec206f88"  # snax-forge commit of every SYN1 row
TECHS = ["nangate45", "nangate15"]
WS = [1, 2, 4, 8, 16, 32]
HEAD_TECH, HEAD_W = "nangate45", 8
SIZE, SEED, CLOCK = "n2048", "0", "10"
FORGE = [("vecadd", "forge", "vecadd"), ("vecmul", "forge", "vecmul"), ("vsum", "forge", "vsum"),
         *[("dot", f"forge{k}", f"dot {k}") for k in range(2, 7)]]
KERNELS = ["vecadd", "vecmul", "vsum", "dot"]
HLS_CASES = ["unopt", "opt", "dace"]
DACE_WS = {"vecadd": WS, "vecmul": WS, "vsum": [1], "dot": [1]}   # hls-exercises' dace sweeps
PARKED = {("dot", "dace", 1)}                                       # needs a RAM macro (RAM1)
MODULES = [("csr", "csr_um2", "csr"), ("ctrl", "ctrl_um2", "ctrl"), ("datapath", "datapath_um2", "dp")]
CYCLE_WARN = 10
SUM_WARN = 0.01
NOTE_DACE = "dace-not-built"
NOTE_RAM = "dace-parked"
FOOTNOTES = {
    NOTE_DACE: "hls-exercises builds dace for vsum and dot at W = 1 only; at this W there is no dace point.",
    NOTE_RAM: "HLS dot `dace_w1` is parked: it needs a RAM macro (RAM1), so it has no synthesis or power row.",
}


def read_csv(path: Path, at: str | None = None) -> list[dict]:
    if at is None:
        with path.open(newline="") as fh:
            return list(csv.DictReader(fh))
    rel = path.relative_to(ROOT).as_posix()
    text = subprocess.run(["git", "show", f"{at}:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(text)))


def fail(msg: str) -> None:
    sys.exit(f"analysis_syn2: {msg}")


def forge_side(tech: str, at: str | None) -> dict:
    """{point: {cycles, commit, area: {csr, ctrl, datapath, total}, pj: {...}, e_run_nj: {...}}}."""
    base = RES / "forge" / tech
    syn = {r["point"]: r for r in read_csv(base / "synth_dc.csv", at)}
    pwr = {r["point"]: r for r in read_csv(base / "power_pt.csv", at)}
    mods = {(r["point"], r["path"]): float(r["e_dyn_pj"]) for r in read_csv(base / "power_pt_modules.csv", at)}
    out = {}
    for kernel, case, _ in FORGE:
        for w in WS:
            p = f"done/{kernel}/{case}_w{w}"
            s, q = syn.get(p), pwr.get(p)
            if s is None or q is None:
                fail(f"{tech} {'before' if at else 'after'}: no row for {p}")
            if s["status"] != "ok" or q["status"] != "ok":
                fail(f"{tech} {p}: status {s['status']!r} / {q['status']!r}")
            if (q["size"], q["seed"], q["clock_ns"], s["clock_ns"]) != (SIZE, SEED, CLOCK, CLOCK):
                fail(f"{tech} {p}: size {q['size']}, seed {q['seed']}, clock {q['clock_ns']}/{s['clock_ns']}")
            if s["snax_forge_commit"] != q["snax_forge_commit"]:
                fail(f"{tech} {p}: synthesis and power name different snax-forge commits")
            cyc = int(q["cycles"])
            area = {m: float(s[col]) for m, col, _ in MODULES}
            area["total"] = float(s["area_um2"])
            pj = {}
            for m, _, path in MODULES:
                key = (p, f"snax_forge_shell_wrapper/{path}")
                if key not in mods:
                    fail(f"{tech} {p}: no power_pt_modules row for {key[1]}")
                pj[m] = mods[key]
            pj["total"] = float(q["e_dyn_pj"])
            e_run = {m: pj[m] * cyc / 1000 for m in pj}
            e_run["total"] = float(q["e_run_pj"]) / 1000
            out[p] = {"cycles": cyc, "commit": s["snax_forge_commit"], "area": area, "pj": pj, "e_run": e_run}
    return out


def hls_side(tech: str) -> dict:
    """{(kernel, case, W): {area, pj, e_run} or None (the reason)}."""
    syn = {r["point"]: r for r in read_csv(RES / "hls" / tech / "synth_dc.csv")}
    pwr = {r["point"]: r for r in read_csv(RES / "hls" / tech / "power_pt.csv")
           if r["size"] == SIZE and r["seed"] == SEED}
    out = {}
    for k in KERNELS:
        for c in HLS_CASES:
            for w in WS:
                p = f"done/{k}/{c}_w{w}"
                if c == "dace" and w not in DACE_WS[k]:
                    out[(k, c, w)] = NOTE_DACE
                    continue
                if (k, c, w) in PARKED:
                    if not syn.get(p, {}).get("status", "").startswith("skipped"):
                        fail(f"{tech} {p}: expected parked, synth_dc.csv says {syn.get(p, {}).get('status')!r}")
                    out[(k, c, w)] = NOTE_RAM
                    continue
                s, q = syn.get(p), pwr.get(p)
                if s is None or q is None or s["status"] != "ok" or q["status"] != "ok":
                    fail(f"{tech} {p}: HLS row missing or not ok")
                if s["clock_ns"] != CLOCK or q["clock_ns"] != CLOCK:
                    fail(f"{tech} {p}: clock {s['clock_ns']}/{q['clock_ns']}")
                out[(k, c, w)] = {"area": float(s["area_um2"]), "pj": float(q["e_dyn_pj"]),
                                  "e_run": float(q["e_run_pj"]) / 1000, "cycles": int(q["cycles"])}
    return out


def f(x: float, nd: int) -> str:
    return f"{x:.{nd}f}"


def delta(b: float, a: float, nd: int) -> list[str]:
    d = a - b
    return [f(d, nd) if abs(d) >= 0.5 * 10 ** -nd else f(0.0, nd),
            f"{100 * d / b:+.1f} %" if b else ""]


def table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


S1_HEAD = ["design", "W", "module", "area µm² before", "after", "Δ", "Δ %", "e_run nJ before", "after", "Δ", "Δ %",
           "pJ/cycle before", "after", "cycles before", "after"]


def s1_rows(B: dict, A: dict, points: list[tuple[str, str, int]]) -> list[list[str]]:
    rows = []
    for p, label, w in points:
        b, a = B[p], A[p]
        for m in ["csr", "ctrl", "datapath", "total"]:
            cyc = [str(b["cycles"]), str(a["cycles"])] if m == "total" else ["", ""]
            name = f"**{m}**" if m == "total" else m
            rows.append([label if m == "csr" else "", str(w) if m == "csr" else "", name,
                         f(b["area"][m], 1), f(a["area"][m], 1), *delta(b["area"][m], a["area"][m], 1),
                         f(b["e_run"][m], 3), f(a["e_run"][m], 3), *delta(b["e_run"][m], a["e_run"][m], 3),
                         f(b["pj"][m], 3), f(a["pj"][m], 3), *cyc])
    return rows


METRICS = [("area", "area µm²", 1), ("e_run", "e_run nJ", 3), ("pj", "pJ per cycle", 3)]


def s2_rows(B: dict, A: dict, H: dict, metric: str, nd: int, points: list[tuple[str, str, str, int]],
            used: set) -> list[list[str]]:
    rows = []
    for p, kernel, label, w in points:
        cells = [label, str(w)]
        for part in ("csr", "kernel", "total"):
            for side in (B[p], A[p]):
                v = side[metric]
                x = v["ctrl"] + v["datapath"] if part == "kernel" else v[part]
                cells.append(f(x, nd))
        for c in HLS_CASES:
            h = H[(kernel, c, w)]
            if isinstance(h, str):
                used.add(h)
                cells.append(f"—[^{h}]")
            else:
                cells.append(f(h[metric], nd))
        rows.append(cells)
    return rows


S2_HEAD = ["design", "W", "forge csr before", "after", "forge ctrl + dp before", "after", "forge total before", "after",
           "HLS unopt", "HLS opt", "HLS dace"]


def warnings(tech: str, B: dict, A: dict) -> list[str]:
    out = []
    for p in A:
        d = A[p]["cycles"] - B[p]["cycles"]
        if abs(d) > CYCLE_WARN:
            out.append(f"{tech} `{p}`: cycles {B[p]['cycles']} before, {A[p]['cycles']} after ({d:+d})")
    for when, S in (("before", B), ("after", A)):
        for p, v in S.items():
            for what, key in (("area", "area"), ("pJ per cycle", "pj")):
                s = sum(v[key][m] for m in ("csr", "ctrl", "datapath"))
                if abs(s / v[key]["total"] - 1) > SUM_WARN:
                    out.append(f"{tech} `{p}` {when}: {what} csr + ctrl + datapath {s:.3f} against the top "
                               f"{v[key]['total']:.3f} ({100 * (s / v[key]['total'] - 1):+.2f} %)")
    return out


def sum_extremes(tech: str, B: dict, A: dict) -> str:
    worst = {}
    for when, S in (("before", B), ("after", A)):
        for key in ("area", "pj"):
            worst[(when, key)] = max(abs(sum(v[key][m] for m in ("csr", "ctrl", "datapath")) / v[key]["total"] - 1)
                                     for v in S.values())
    cyc = max(abs(A[p]["cycles"] - B[p]["cycles"]) for p in A)
    return (f"{tech}: largest cycle difference {cyc}; largest module-sum gap, area {100 * worst[('before', 'area')]:.3f} % "
            f"before and {100 * worst[('after', 'area')]:.3f} % after, pJ per cycle {100 * worst[('before', 'pj')]:.3f} % "
            f"before and {100 * worst[('after', 'pj')]:.3f} % after.")


def main() -> int:
    B, A, H = {}, {}, {}
    for t in TECHS:
        B[t], A[t], H[t] = forge_side(t, PIN), forge_side(t, None), hls_side(t)
    before_c = {v["commit"] for t in TECHS for v in B[t].values()}
    after_c = {v["commit"] for t in TECHS for v in A[t].values()}
    if before_c != {BEFORE_FORGE}:
        fail(f"before rows name snax-forge {sorted(before_c)}, not {BEFORE_FORGE}")
    if len(after_c) != 1 or after_c == before_c:
        fail(f"after rows name snax-forge {sorted(after_c)}: expected one commit other than the before's")
    after_forge = after_c.pop()

    pts1 = lambda ws: [(f"done/{k}/{c}_w{w}", lab, w) for k, c, lab in FORGE for w in ws]  # noqa: E731
    pts2 = lambda ws: [(f"done/{k}/{c}_w{w}", k, lab, w) for k, c, lab in FORGE for w in ws]  # noqa: E731
    used: set = set()
    md = []
    md.append("# SYN2: forge before and after CTRL1, and against HLS\n")
    md.append("Generated by `report/analysis_syn2.py` (`pixi run syn2`); every number is computed from the CSVs below, none typed by hand.\n")
    md.append("| | |\n|---|---|")
    md.append(f"| before | SYN1: snax-forge-experiments `{PIN}`, read with `git show` (`results/forge/<tech>/`); snax-forge `{BEFORE_FORGE}` |")
    md.append(f"| after | SYN2: this tree's `results/forge/<tech>/`; snax-forge `{after_forge}` (CTRL1: D152, D153) |")
    md.append("| HLS | this tree's `results/hls/<tech>/`, tier done, not rerun |")
    md.append(f"| technologies | {', '.join(TECHS)} |")
    md.append(f"| settings | clock {CLOCK} ns; one task of N = 2048 (`{SIZE}`), rand64 stimulus, seed {SEED}; dynamic energy of the busy window (X13, X23, X24) |")
    md.append("")
    md.append("Units: area in µm²; e_run in nJ per task (the busy window's dynamic energy); pJ per cycle is e_dyn, the same window's energy per cycle. Δ is after minus before, Δ % against before. Forge's modules are the wrapper's three instances, csr, ctrl and datapath (dp); the total is the whole wrapper, its glue included. Forge's kernel is ctrl + datapath, the part an HLS block holds; forge's csr is the interface, which HLS leaves to its driver (D152).\n")

    md.append("## 1. Forge before and after\n")
    md.append(f"### {HEAD_TECH}, W = {HEAD_W}\n")
    md.append(table(S1_HEAD, s1_rows(B[HEAD_TECH], A[HEAD_TECH], pts1([HEAD_W]))))
    for t in TECHS:
        md.append(f"### {t}, every W\n")
        md.append(table(S1_HEAD, s1_rows(B[t], A[t], pts1(WS))))

    md.append("## 2. Forge against HLS\n")
    md.append("Per kernel and W; each dot variant is its own row, beside the same HLS dot points. Forge before and after; HLS's whole block (unopt, opt, dace), which CTRL1 does not change.\n")
    md.append(f"### {HEAD_TECH}, W = {HEAD_W}\n")
    for metric, name, nd in METRICS:
        md.append(f"**{name}**\n")
        md.append(table(S2_HEAD, s2_rows(B[HEAD_TECH], A[HEAD_TECH], H[HEAD_TECH], metric, nd, pts2([HEAD_W]), used)))
    for t in TECHS:
        md.append(f"### {t}, every W\n")
        for metric, name, nd in METRICS:
            md.append(f"**{name}**\n")
            md.append(table(S2_HEAD, s2_rows(B[t], A[t], H[t], metric, nd, pts2(WS), used)))

    md.append("## Warnings\n")
    md.append(f"Cycle differences above {CYCLE_WARN} between before and after, and module sums (csr + ctrl + datapath) more than {100 * SUM_WARN:g} % from the top, in area or pJ per cycle.\n")
    ws = [w for t in TECHS for w in warnings(t, B[t], A[t])]
    md.append("\n".join(f"- {w}" for w in ws) if ws else "- None.")
    md.append("")
    md.append("For the record: " + " ".join(sum_extremes(t, B[t], A[t]) for t in TECHS) + "\n")

    for key in (NOTE_DACE, NOTE_RAM):
        if key in used:
            md.append(f"[^{key}]: {FOOTNOTES[key]}")
    md.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(md))
    n = sum(len(A[t]) for t in TECHS)
    print(f"wrote {OUT.relative_to(ROOT)}: {n} forge points before and after ({', '.join(TECHS)}), "
          f"snax-forge {BEFORE_FORGE[:7]} -> {after_forge[:7]}; warnings: {len(ws)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
