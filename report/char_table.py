#!/usr/bin/env python3
"""report/char_table.py - CHAR1: snax-forge's blocks alone, the table and the draft JSON (docs/DECISIONS.md X28 to X36).

  pixi run char-table

Reads, per technology (nangate45, nangate15), results/char/<tech>/char_synth.csv (R0) and char_power.csv (R2),
and char/points.json (the params as hw/chisel/blocks.json names them); writes results/char/char_table.md and
results/char/<tech>/char_draft.json. Every number is computed from those files, or, for the known limits only,
from the files they cite:

  the free first       SYN2's results/forge/<tech>/synth_dc_modules.csv (TreeAccumulate inside dot 4)
  the isolated fire    R1's char_power.csv at the pushed commit R1_COMMIT (`git show`, not a copy): duty50
                       against (busy + idle) / 2
  LinkBuffer's slope   the R2 run note's diagnostic table (results/char/runs/2026-11-03_char1_r2.md), the two
                       netlists' e_flop and e_bit
  the dot 4 to 6 Mac   SYN2's results/forge/<tech>/power_pt.csv (cycles) and power_pt_modules.csv (the Mac's
                       e_dyn per cycle): (fires E_busy + (cycles - fires) E_idle) / cycles with fires = N / W

Checks, each a failure: every point of char/points.json present on both technologies, every row ok, one
snax-forge commit, the windows R2 has (busy and idle; LinkBuffer stream).
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
RES = ROOT / "results"
CHAR = RES / "char"
OUT = CHAR / "char_table.md"
POINTS = ROOT / "char" / "points.json"
R1_COMMIT = "03b7a835eec358ceee94e3a4fc7ed82617489659"   # ry/char1 after CHAR1 R1 (tag char1-r1), pushed
R2_NOTE = CHAR / "runs" / "2026-11-03_char1_r2.md"
R1_NOTE = "results/char/runs/2026-11-03_char1_r1.md"
TECHS = ["nangate45", "nangate15"]
N = 2048                      # SYN2's task, the dot 4 to 6 Mac comparison
CLOCK, SEED, CYCLES = "10", "0", 128
BLOCKS = [("ElementwiseLanes", "lanes"), ("Mac", "mac"), ("TreeAccumulate", "tree"),
          ("SerialAccumulate", "serial"), ("LinkBuffer", "link")]
REGISTERED = ("Mac", "TreeAccumulate", "SerialAccumulate")


def fail(msg: str) -> None:
    sys.exit(f"char_table: {msg}")


def read_csv(path: Path, at: str | None = None) -> list[dict]:
    if at is None:
        with path.open(newline="") as fh:
            return list(csv.DictReader(fh))
    rel = path.relative_to(ROOT).as_posix()
    text = subprocess.run(["git", "show", f"{at}:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return list(csv.DictReader(io.StringIO(text)))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def table(head: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    return "\n".join(out + ["| " + " | ".join(str(x) for x in r) + " |" for r in rows])


def f(x: float, nd: int = 4) -> str:
    return f"{x:.{nd}f}"


def pct(a: float, b: float) -> str:
    return f"{100 * (a - b) / b:+.1f} %"


def lsq(xs: list[float], ys: list[float]) -> tuple[float, float]:
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return m, my - m * mx


def load(tech: str, points: list[dict]) -> dict:
    """{point: {datapath, params, synth row, windows: {name: power row}}} for `tech`, checked."""
    synth = {r["point"]: r for r in read_csv(CHAR / tech / "char_synth.csv")}
    power: dict = {}
    for r in read_csv(CHAR / tech / "char_power.csv"):
        power.setdefault(r["point"], {})[r["window"]] = r
    out = {}
    for p in points:
        name = p["point"]
        if name not in synth or name not in power:
            fail(f"{tech}: {name} has no synthesis or power row")
        want = ["stream"] if p["datapath"] == "LinkBuffer" else ["busy", "idle"]
        if sorted(power[name]) != sorted(want):
            fail(f"{tech}: {name} has windows {sorted(power[name])}, R2 has {want}")
        rows = [synth[name], *power[name].values()]
        bad = [r for r in rows if not r["status"].startswith("ok")]
        if bad:
            fail(f"{tech}: {name}: status {bad[0]['status']}")
        out[name] = {"datapath": p["datapath"], "params": p["params"], "synth": synth[name], "windows": power[name]}
    commits = {r["snax_forge_commit"] for v in out.values() for r in [v["synth"], *v["windows"].values()]}
    if len(commits) != 1:
        fail(f"{tech}: snax-forge commits {commits}, one expected")
    return out


def e(d: dict, p: str, w: str, col: str = "e_dyn_pj") -> float:
    return float(d[p]["windows"][w][col])


def ehold(d: dict) -> dict:
    bits = {p: 1000 * e(d, p, "idle", "e_bit_pj") for p, v in d.items() if v["datapath"] in REGISTERED}
    vals = list(bits.values())
    mean = sum(vals) / len(vals)
    sd = (sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5
    return {"mean": mean, "min": min(vals), "max": max(vals), "sd": sd, "n": len(vals)}


# ---------------------------------------------------------------- the block sections
def params_cell(v: dict) -> list[str]:
    p = v["params"]
    return [str(p.get("lanes", "")), str(p.get("depth", "-")), str(p.get("op", "-"))]


def block_rows(D: dict, prefix: str) -> tuple[list[str], list[list]]:
    windows = ["stream"] if prefix == "link" else ["busy", "idle"]
    head = ["point", "lanes", "depth", "op"]
    for t in TECHS:
        tag = t.removeprefix("nangate")
        head += [f"{tag} area", f"{tag} comb", f"{tag} seq", f"{tag} flops"]
        head += [f"{tag} {w} {g}" for w in windows for g in ("e_comb", "e_flop", "e_dyn")]
    pts = [p for p in D[TECHS[0]] if p.startswith(prefix + "/")]
    pts.sort(key=lambda p: (D[TECHS[0]][p]["params"].get("op", ""), int(D[TECHS[0]][p]["params"].get("lanes", 0)),
                            int(D[TECHS[0]][p]["params"].get("depth", 0))))
    rows = []
    for p in pts:
        row = [f"`{p}`", *params_cell(D[TECHS[0]][p])]
        for t in TECHS:
            s = D[t][p]["synth"]
            row += [f(float(s["area_um2"]), 1), f(float(s["comb_area_um2"]), 1), f(float(s["seq_area_um2"]), 1),
                    s["seq_cells"]]
            row += [f(e(D[t], p, w, c)) for w in windows for c in ("e_comb_pj", "e_flop_pj", "e_dyn_pj")]
        rows.append(row)
    return head, rows


def area(d: dict, p: str) -> float:
    return float(d[p]["synth"]["area_um2"])


def copies(D: dict, pat: str, what: str, ws=(8, 32)) -> str:
    """'area 1.000 / 1.000, busy ...' ratios of X(W) / (W X(1)) per technology."""
    parts = []
    for t in TECHS:
        d = D[t]
        def val(w):
            p = pat.format(w)
            return area(d, p) if what == "area" else e(d, p, what)
        parts.append(f"{t} " + ", ".join(f"{val(w) / (w * val(1)):.3f} at W = {w}" for w in ws))
    return f"{what}: " + "; ".join(parts)


def scaling(D: dict, prefix: str) -> list[str]:
    if prefix == "lanes":
        return [f"- **{op}**, lane copies, X(W) / (W X(1)): " + "; ".join(copies(D, f"lanes/{op}_w{{}}", what) for what in ("area", "busy"))
                + ". Idle is 0 at every W (no flop)." for op in ("add", "mul")]
    if prefix == "mac":
        return ["- Lane copies, X(W) / (W X(1)): " + "; ".join(copies(D, "mac/acc_w{}", what) for what in ("area", "busy", "idle")) + "."]
    if prefix in ("tree", "serial"):
        ws = (1, 2, 4, 8, 16, 32) if prefix == "tree" else (2, 4, 8, 16, 32)
        pat = "tree/add_w{}" if prefix == "tree" else "serial/sum_w{}"
        lines = []
        for t in TECHS:
            d = D[t]
            vals = ", ".join(f"{e(d, pat.format(w), 'busy', 'e_comb_pj'):.3f}" for w in ws)
            flop = [e(d, pat.format(w), "busy", "e_flop_pj") for w in ws]
            idle = [e(d, pat.format(w), "idle") for w in ws]
            lines.append(f"- {t}: busy e_comb at W = {', '.join(map(str, ws))}: {vals} pJ; busy e_flop {min(flop):.3f} to "
                         f"{max(flop):.3f} pJ and idle {min(idle):.4f} to {max(idle):.4f} pJ at every W (64 flops).")
        return lines
    lines = []
    for t in TECHS:
        d = D[t]
        ds = [2, 4, 8, 16]
        md, cd = lsq(ds, [e(d, f"link/d{x}_w1", "stream") for x in ds])
        mf, cf = lsq(ds, [e(d, f"link/d{x}_w1", "stream", "e_flop_pj") for x in ds])
        one = e(d, "link/d1_w1", "stream")
        w = "; ".join(f"d1 at W = {x}: {e(d, f'link/d1_w{x}', 'stream') / (x * one):.3f} of W x d1_w1" for x in (8, 32))
        lines.append(f"- {t}: stream at W = 1 over D = 2, 4, 8, 16 (least squares): e_dyn = {md:.4f} D + {cd:.4f} pJ, "
                     f"e_flop = {mf:.4f} D + {cf:.4f} pJ; D = 1 apart (no read mux): e_dyn {one:.4f} pJ, e_flop "
                     f"{e(d, 'link/d1_w1', 'stream', 'e_flop_pj'):.4f} pJ; {w}.")
    return lines


# ---------------------------------------------------------------- the known limits
def limit_first(D: dict) -> list[str]:
    rows = []
    for t in TECHS:
        mods = read_csv(RES / "forge" / t / "synth_dc_modules.csv")
        for w in (1, 2, 4, 8, 16, 32):
            top = D[t][f"tree/add_w{w}"]["synth"]["top"]
            inside = [m for m in mods if m["point"] == f"done/dot/forge4_w{w}" and re.fullmatch(rf"{top}(_\d+)?", m["design"])]
            if len(inside) != 1:
                fail(f"{t}: TreeAccumulate W = {w} inside dot 4: {len(inside)} cells")
            a, i = area(D[t], f"tree/add_w{w}"), float(inside[0]["area_um2"])
            rows.append([t, w, f(a, 1), f(i, 1), f(a - i, 1), pct(a, i)])
    return [table(["tech", "W", "alone µm²", "inside dot 4 µm²", "alone - inside µm²", "diff"], rows)]


def limit_isolated() -> list[str]:
    rows = []
    r1 = {}
    for r in read_csv(CHAR / "nangate45" / "char_power.csv", R1_COMMIT):
        r1.setdefault(r["point"], {})[r["window"]] = float(r["e_dyn_pj"])
    for p, w in sorted(r1.items()):
        if "duty50" in w and "idle" in w:
            half = (w["busy"] + w["idle"]) / 2
            rows.append([f"`{p}`", f(w["busy"]), f(w["idle"]), f(w["duty50"]), f(half), pct(w["duty50"], half)])
    return [table(["point (nangate45, R1)", "busy", "idle", "duty50", "(busy + idle) / 2", "duty50 against it"], rows)]


def limit_slope(D: dict) -> list[str]:
    rows = []
    for t in TECHS:
        d = D[t]
        h = ehold(d)["mean"] / 1000
        ds = [1, 2, 4, 8, 16]
        for col in ("e_dyn_pj", "e_flop_pj"):
            m, _ = lsq(ds, [e(d, f"link/d{x}_w1", "stream", col) for x in ds])
            rows.append([t, col.removesuffix("_pj"), f(m), f(64 * h), f"{m / (64 * h):.3f}"])
    text = R2_NOTE.read_text()
    diag = {}
    for ln in text.split("## Diagnostic", 1)[1].splitlines():
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if ln.startswith("| R0 (") or ln.startswith("| diagnostic ("):
            diag["R0" if ln.startswith("| R0") else "noinv"] = {"cell": cells[2], "e_flop": float(cells[8]),
                                                                  "e_bit": float(cells[10])}
    if set(diag) != {"R0", "noinv"}:
        fail(f"{R2_NOTE.name}: no diagnostic table")
    a, b = diag["R0"], diag["noinv"]
    return [table(["tech", "fit over D = 1 .. 16", "m pJ per D", "64 e_hold pJ", "m / (64 e_hold)"], rows),
            f"\nR2's diagnostic on nangate45 (`link/d4_w1`, [{R2_NOTE.name}](runs/{R2_NOTE.name})): synthesized again with "
            f"`-no_seq_output_inversion`, its stream window gives e_flop {b['e_flop']:.4f} pJ against {a['e_flop']:.4f} "
            f"({pct(b['e_flop'], a['e_flop'])}), {b['e_bit']:.4f} fJ per flop against {a['e_bit']:.4f} ({a['cell']}, "
            f"then {b['cell']}): turning the inversion off changes nothing, and both are below nangate45's e_hold "
            f"({ehold(D['nangate45'])['mean']:.4f} fJ)."]


def limit_mac(D: dict) -> list[str]:
    rows = []
    for t in TECHS:
        pwr = {r["point"]: r for r in read_csv(RES / "forge" / t / "power_pt.csv") if r["size"] == "n2048"}
        mods = read_csv(RES / "forge" / t / "power_pt_modules.csv")
        for k in (4, 5, 6):
            for w in (1, 8, 32):
                p = f"done/dot/forge{k}_w{w}"
                top = D[t][f"mac/acc_w{w}"]["synth"]["top"]
                inside = [float(m["e_dyn_pj"]) for m in mods if m["point"] == p and re.fullmatch(rf"{top}(_\d+)?", m["design"])]
                if len(inside) != 1:
                    fail(f"{t}: {p}: {len(inside)} Mac cells")
                cyc, fires = int(pwr[p]["cycles"]), N // w
                busy, idle = e(D[t], f"mac/acc_w{w}", "busy"), e(D[t], f"mac/acc_w{w}", "idle")
                model = (fires * busy + (cyc - fires) * idle) / cyc
                rows.append([t, f"dot {k}", w, cyc, fires, f(busy, 3), f(model, 3), f(inside[0], 3),
                             f"{busy / inside[0]:.3f}", f"{model / inside[0]:.3f}"])
    return [table(["tech", "design", "W", "cycles", "fires", "busy alone pJ", "model pJ", "inside pJ",
                   "busy / inside", "model / inside"], rows)]


# ---------------------------------------------------------------- the draft JSON
def draft(t: str, d: dict, commits: dict) -> dict:
    h = ehold(d)
    pts = []
    for p, v in d.items():
        s = v["synth"]
        windows = ["stream"] if v["datapath"] == "LinkBuffer" else ["busy", "idle"]
        pts.append({"point": p, "datapath": v["datapath"], "params": v["params"],
                    "area": {"total": float(s["area_um2"]), "comb": float(s["comb_area_um2"]), "seq": float(s["seq_area_um2"])},
                    "flops": int(s["seq_cells"]), "fmax_mhz": float(s["fmax_mhz"]),
                    "energy": {w: {"comb": e(d, p, w, "e_comb_pj"), "flop": e(d, p, w, "e_flop_pj")} for w in windows}})
    return {"status": "draft", "tech": t, "clock_ns": float(CLOCK),
            "units": {"area": "um2", "energy": "pJ per cycle of the window", "e_hold": "fJ per flop per cycle",
                      "fmax": "MHz (a lower bound at a 10 ns clock, X2)"},
            "source": {"snax_forge_commit": commits["snax_forge"], "snax_forge_experiments_commit": commits["sfe"],
                       "stimulus": f"rand64, seed {SEED}, {CYCLES} cycles per window, inputs at the rising edge, the VCD "
                                   "cut per window (docs/DECISIONS.md X31, X32)",
                       "windows": "busy and idle; LinkBuffer stream, a link not loading costing flops x e_hold (X31, X33)"},
            "e_hold_fj": round(h["mean"], 6), "points": pts}


def main() -> int:
    points = json.loads(POINTS.read_text())
    D = {t: load(t, points) for t in TECHS}
    commits = {"snax_forge": next(iter(D[TECHS[0]].values()))["synth"]["snax_forge_commit"],
               "sfe": git("log", "-1", "--format=%H", "--", *(f"results/char/{t}/char_power.csv" for t in TECHS))}
    if any(next(iter(D[t].values()))["synth"]["snax_forge_commit"] != commits["snax_forge"] for t in TECHS):
        fail("the technologies name different snax-forge commits")

    L = ["# CHAR1: snax-forge's blocks alone (int64)", "",
         "Generated by `report/char_table.py` (`pixi run char-table`) from `results/char/<tech>/char_synth.csv` and "
         "`char_power.csv`; the known limits also read the files they cite. Do not edit by hand.", "",
         f"- **Commits:** snax-forge `{commits['snax_forge']}` (every row); snax-forge-experiments `{commits['sfe']}` "
         "(the commit that wrote the power CSVs).",
         f"- **Settings:** clock {CLOCK} ns; synthesis as SYN1 and SYN2 (X1 to X4, X22; the block as top, X30); power "
         f"rand64 seed {SEED}, {CYCLES} cycles per window (SerialAccumulate's busy: {CYCLES} beats of W cycles), "
         "inputs at the rising edge, a lead-in slot before each window, the VCD cut per window (X31, X32).",
         "- **Units:** area µm²; energy pJ per cycle of the window (e_comb, e_flop = clock + register + sequential, "
         "e_dyn = the two); e_bit and e_hold fJ per flop per cycle.",
         "- **Windows:** busy (a fire every cycle) and idle (the enable at 0, every other input held) for "
         "ElementwiseLanes, Mac, TreeAccumulate and SerialAccumulate; stream for LinkBuffer (a load every cycle at "
         "full occupancy), a link that is not loading costing its flops x e_hold (X33).", "",
         "## e_hold", ""]
    rows = []
    for t in TECHS:
        h = ehold(D[t])
        rows.append([t, h["n"], f(h["mean"]), f(h["min"]), f(h["max"]), f(h["sd"]),
                     f"{100 * (h['max'] - h['min']) / h['mean']:.2f} %"])
    L += ["The mean idle e_bit of the registered blocks (Mac, TreeAccumulate, SerialAccumulate), fJ per flop per cycle:",
          "", table(["tech", "points", "e_hold", "min", "max", "sd", "range"], rows), ""]
    for dp, prefix in BLOCKS:
        head, rows = block_rows(D, prefix)
        L += [f"## {dp}", "", table(head, rows), "", "How it scales:", "", *scaling(D, prefix), ""]
    L += ["## Known limits", "",
          "**The free `first`.** A TreeAccumulate alone has its `first` driven; inside dot 4 it is tied and firtool "
          "folds it (R0, `results/char/runs/2026-11-03_char1_r0.md`), so the block alone is larger than dot 4's sum by:",
          "", *limit_first(D), "",
          f"**An isolated fire costs more than a back-to-back one.** R1's duty50 window (a fire every other cycle) against "
          f"the mean of busy and idle, from R1's `char_power.csv` at `{R1_COMMIT[:7]}` ([{Path(R1_NOTE).name}](runs/"
          f"{Path(R1_NOTE).name})): with a fire every other cycle the inputs change at one edge and the accumulator "
          "at the next, so its adders settle twice per fire. busy and idle do not model it; R2 dropped duty50 (X34).",
          "", *limit_isolated(), "",
          "**nangate45's LinkBuffer stream slope** is below one slot of held flops (64 e_hold) per depth, as PT's averaged "
          "mode gives it; kept as measured (X35):", "", *limit_slope(D), "",
          f"**The Mac inside dot 5 and 6 at W = 32.** Busy alone is well above the Mac's per-cycle energy there because "
          f"the Mac fires {N // 32} of the run's cycles (N = {N} / W), the rest being the serial sum's tail; busy and "
          "idle reproduce it: model = (fires E_busy + (cycles - fires) E_idle) / cycles, the cycles from SYN2's "
          "`power_pt.csv`, inside from its `power_pt_modules.csv`:", "", *limit_mac(D), ""]
    OUT.write_text("\n".join(L))
    for t in TECHS:
        (CHAR / t / "char_draft.json").write_text(json.dumps(draft(t, D[t], commits), indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} and results/char/<tech>/char_draft.json for {', '.join(TECHS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
