#!/usr/bin/env python3
"""report/char_table.py - the blocks alone at every type pair, the table: results/char/char_table.md.

  pixi run char-table          (after pixi run char-export)

Reads results/char/<tech>/char_synth.csv and char_power.csv and char/points.json; for the model and the known
limits, char.json, the forge points' power_pt.csv, power_pt_modules.csv and synth_dc_modules.csv, the duty50 rows
at R1_COMMIT and a run note's diagnostic table. Every number is computed from those files, on the clock-gated rows
(the duty50 rows, from before clock gating, are ungated). Checks, each a failure: every point present, every row
ok, one snax-forge commit, the windows each block has, char.json current.
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
R1_COMMIT = "03b7a835eec358ceee94e3a4fc7ed82617489659"   # the commit holding the duty50 rows, pushed
R1_NOTE = "results/char/runs/2026-11-03_char1_r1.md"
TECHS = ["nangate45"]
N = 2048                      # the forge points' task, the dot 4 to 6 Mac comparison
CLOCK, SEED, CYCLES = "10", "0", 128
BLOCKS = [("SimdLanes", "lanes"), ("Mac", "mac"), ("TreeAccumulate", "tree"),
          ("SerialAccumulate", "serial"), ("LinkBuffer", "link"), ("FifoPacker", "pack")]
REGISTERED = ("Mac", "TreeAccumulate", "SerialAccumulate")
FOLDS = ("TreeAccumulate", "SerialAccumulate")
TYPE_KEYS = ("inTypes", "opType", "outType", "inType", "dtype", "laneType")
W0 = {"SimdLanes": 1, "Mac": 8, "TreeAccumulate": 8, "SerialAccumulate": 8}   # the lanes each pair is measured at
PAIRS = [(i, o) for i in (8, 16, 32, 64) for o in (8, 16, 32, 64) if o >= i]


def fail(msg: str) -> None:
    sys.exit(f"char_table: {msg}")


def width(dtype: str) -> int:
    m = re.fullmatch(r"u?int(\d+)", dtype)
    if not m:
        fail(f"dtype {dtype}: not an integer type")
    return int(m.group(1))


def types(params: dict) -> list[str]:
    """Every type a block's params name (inputs, op, output, a buffer's or a packer's lane)."""
    out = []
    for k in TYPE_KEYS:
        v = params.get(k)
        out += v if isinstance(v, list) else [v] if v else []
    return out


def is64(params: dict) -> bool:
    """A point of the int64 set: every type int64 (the set the flop constants and the lanes rules come from)."""
    return all(t == "int64" for t in types(params))


def pair(params: dict) -> tuple[int, int]:
    """(w_in, w_out): the widest input and the output (LinkBuffer: its dtype twice; FifoPacker: its laneType)."""
    if "dtype" in params or "laneType" in params:
        w = width(params.get("dtype") or params["laneType"])
        return w, w
    ins = params.get("inTypes") or [params["inType"]]
    return max(width(t) for t in ins), width(params["outType"])


def check_only(datapath: str, params: dict) -> bool:
    """A narrow point measured to check a rule, not a char.json point: a narrow LinkBuffer (its comb scales with
    its dtype's width), or a narrow point of a block at other lanes than the pair's measured W0."""
    if is64(params) or datapath == "FifoPacker":
        return False
    return datapath == "LinkBuffer" or params.get("lanes") != W0[datapath]


def read_csv(path: Path, at: str | None = None, gate: str = "1") -> list[dict]:
    """The CSV's rows whose clk_gate is `gate` (empty reads as 0): the clock-gated rows, unless an older commit's
    ungated rows are asked for."""
    keep = lambda r: ("1" if r.get("clk_gate", "") == "1" else "0") == gate  # noqa: E731
    if at is None:
        with path.open(newline="") as fh:
            return [r for r in csv.DictReader(fh) if keep(r)]
    rel = path.relative_to(ROOT).as_posix()
    text = subprocess.run(["git", "show", f"{at}:{rel}"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [r for r in csv.DictReader(io.StringIO(text)) if keep(r)]


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


def load(tech: str, points: list[dict], gate: str = "1") -> dict:
    """{point: {datapath, params, synth row, windows: {name: power row}}} for `tech`, checked; the rows whose
    clk_gate is `gate`."""
    synth = {r["point"]: r for r in read_csv(CHAR / tech / "char_synth.csv", gate=gate)}
    power: dict = {}
    for r in read_csv(CHAR / tech / "char_power.csv", gate=gate):
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
    bits = {p: 1000 * e(d, p, "idle", "e_bit_pj") for p, v in d.items()
            if v["datapath"] in REGISTERED and is64(v["params"])}
    vals = list(bits.values())
    mean = sum(vals) / len(vals)
    sd = (sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5
    return {"mean": mean, "min": min(vals), "max": max(vals), "sd": sd, "n": len(vals)}


# ---------------------------------------------------------------- the block sections
def params_cell(v: dict) -> list[str]:
    p = v["params"]
    w_in, w_out = pair(p)
    return [str(p.get("lanes", "-")), str(p.get("depth", "-")), str(p.get("op", "-")), f"i{w_in}", f"i{w_out}"]


def block_rows(D: dict, prefix: str) -> tuple[list[str], list[list]]:
    windows = ["stream"] if prefix == "link" else ["busy", "idle"]
    head = ["point", "lanes", "depth", "op", "in", "out"]
    for t in TECHS:
        tag = t.removeprefix("nangate")
        head += [f"{tag} area", f"{tag} comb", f"{tag} seq", f"{tag} flops"]
        head += [f"{tag} {w} {g}" for w in windows for g in ("e_comb", "e_flop", "e_dyn")]
    pts = [p for p in D[TECHS[0]] if p.startswith(prefix + "/")]
    pts.sort(key=lambda p: (not is64(D[TECHS[0]][p]["params"]), D[TECHS[0]][p]["params"].get("op", ""),
                            pair(D[TECHS[0]][p]["params"]), int(D[TECHS[0]][p]["params"].get("lanes", 0)),
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
    if prefix == "pack":
        lines = []
        for t in TECHS:
            d = D[t]
            per = ", ".join(f"d_out {r} ({t_}) {e(d, f'pack/d{r}_{t_}', 'busy'):.4f}"
                            for r, t_ in ((2, "i32"), (4, "i16"), (8, "i8")))
            lines.append(f"- {t}: busy e_dyn a push: {per} pJ; idle is its clock gates' (and at d_out 2 its "
                         "ungated 1-bit counter's).")
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
    for r in read_csv(CHAR / "nangate45" / "char_power.csv", R1_COMMIT, gate="0"):
        r1.setdefault(r["point"], {})[r["window"]] = float(r["e_dyn_pj"])
    for p, w in sorted(r1.items()):
        if "duty50" in w and "idle" in w:
            half = (w["busy"] + w["idle"]) / 2
            rows.append([f"`{p}`", f(w["busy"]), f(w["idle"]), f(w["duty50"]), f(half), pct(w["duty50"], half)])
    return [table(["point (nangate45, R1)", "busy", "idle", "duty50", "(busy + idle) / 2", "duty50 against it"], rows)]


def limit_mac(D: dict) -> list[str]:
    rows = []
    for t in TECHS:
        pwr = {r["point"]: r for r in read_csv(RES / "forge" / t / "power_pt.csv") if r["size"] == "n2048"}
        mods = read_csv(RES / "forge" / t / "power_pt_modules.csv")
        for k in (4, 5, 6):
            for w in LIMIT_MAC_WS:
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



# ---------------------------------------------------------------- the type axis (X89)
def point_name(prefix: str, case: str, w: int, i: int, o: int) -> str:
    return f"{prefix}/{case}_w{w}" if (i, o) == (64, 64) else f"{prefix}/{case}_w{w}_i{i}_i{o}"


def rule_of(datapath: str) -> str:
    return "width" if datapath == "LinkBuffer" else "slope" if datapath in FOLDS else "copy"


def types_section(D: dict, J: dict) -> list[str]:
    """The pairs per block, the bits each computes (SimdLanes), each rule against the points that check it, and the
    narrow registers' load energy."""
    import char_export as ce
    out = []
    for t in TECHS:
        d, j = D[t], J[t]
        comb = lambda p, w="busy": (float(d[p]["synth"]["comb_area_um2"]), e(d, p, w, "e_comb_pj"))  # noqa: E731
        rows = []
        for i, o in PAIRS:
            wp = min(2 * i, o)
            (aa, ea), (am, em) = comb(point_name("lanes", "add", 1, i, o)), comb(point_name("lanes", "mul", 1, i, o))
            rows.append([f"i{i}", f"i{o}", wp, f(aa, 1), f(aa / i, 2), f(ea, 4), f(am, 1), f(am / (i * wp), 3), f(em, 4)])
        trend = table(["in", "out", "w_p", "add comb µm²", "add µm² / w_in", "add e_comb pJ", "mul comb µm²",
                       "mul µm² / (w_in w_p)", "mul e_comb pJ"], rows)
        rows = []
        for i, o in PAIRS:
            r = [f"i{i}", f"i{o}"]
            for prefix, case in (("mac", "acc"), ("tree", "add"), ("serial", "sum")):
                a, en = comb(point_name(prefix, case, 8, i, o))
                r += [f(a, 1), f(en, 4)]
            rows.append(r)
        folds = table(["in", "out", "Mac comb µm²", "Mac e_comb pJ", "TreeAccumulate comb µm²", "TreeAccumulate e_comb pJ",
                       "SerialAccumulate comb µm²", "SerialAccumulate e_comb pJ"], rows)
        slopes = []
        for dp, prefix, case in (("TreeAccumulate", "tree", "add"), ("SerialAccumulate", "serial", "sum")):
            lo, hi = ce.SLOPE_WS
            (a8, e8), (a32, e32) = comb(f"{prefix}/{case}_w{lo}"), comb(f"{prefix}/{case}_w{hi}")
            slopes.append(f"{dp} {(a32 - a8) / (hi - lo):.2f} µm² and {(e32 - e8) / (hi - lo):.4f} pJ a lane")
        rows = []
        for p in sorted(x for x, v in d.items() if check_only(v["datapath"], v["params"])):
            v = d[p]
            a, en = comb(p, "stream" if v["datapath"] == "LinkBuffer" else "busy")
            ma, me = (ce.comb_at(j, v["datapath"], v["params"], c) for c in ("comb_um2", "e_comb_pj"))
            rows.append([f"`{p}`", rule_of(v["datapath"]), f(a, 1), f(ma, 1), f"{a / ma:.3f}", f(en, 4), f(me, 4),
                         f"{en / me:.3f}"])
        checks = table(["point", "rule", "comb µm²", "rule µm²", "ratio", "e_comb pJ", "rule pJ", "ratio"], rows)
        bits = {p: 1000 * e(d, p, "busy", "e_bit_pj") for p, v in d.items()
                if v["datapath"] in REGISTERED and not is64(v["params"]) and not check_only(v["datapath"], v["params"])}
        same = [x for p, x in bits.items() if pair(d[p]["params"])[0] == pair(d[p]["params"])[1]]
        wider = [x for p, x in bits.items() if pair(d[p]["params"])[0] < pair(d[p]["params"])[1]]
        out += [f"**{t}: what SimdLanes computes at each pair** (W = 1). DC removes the logic on an input's copied sign "
                "bits, so an add costs about its input width and a multiply about w_in x w_p, w_p = min(2 w_in, w_out) "
                "the product bits it keeps; a wider output only copies the sign. 8 → 16 is the one outlier: its 16-bit "
                "multiplier is built larger than 8 → 32's 32-bit one, for the same product. This is a finding, not the "
                "model: the model reads each pair's own point.", "", trend, "",
                f"**{t}: the Mac and the folds at each pair** (W = 8):", "", folds, "",
                f"**{t}: the rules against the points that check them.** copy: W / W0 x the pair's point; slope: the "
                "pair's point at W0 = 8 plus (W - 8) x the int64 cost per lane between W = 8 and 32 x w_in / 64 "
                f"({'; '.join(slopes)}): a lane is a leaf or a mux input at the input's width, while the accumulator's "
                "adder and register stay at the output's; width: the int64 LinkBuffer x w / 64.", "", checks, "",
                f"**{t}: narrow registers load fewer toggling bits.** The busy e_bit of the narrow Mac and folds is "
                f"{min(same):.1f} to {max(same):.1f} fJ where in = out and {min(wider):.1f} to {max(wider):.1f} fJ where "
                f"in < out (the upper bits copy the sign), against e_load {j['flop']['e_load_fj']:.1f} fJ: the model "
                "prices those registers high by up to "
                f"{j['flop']['e_load_fj'] / min(wider):.1f}x, a pessimistic price as the rand64 data's.", ""]
    return out

# ---------------------------------------------------------------- the model (char.json against the forge points)
MODEL_DESIGNS = [("vecmul", "done/vecmul/forge_w{}"), ("vsum", "done/vsum/forge_w{}"), ("dot 4", "done/dot/forge4_w{}"),
                 ("dot 5", "done/dot/forge5_w{}")]
MODEL_WS = (8,)                 # W = 32's vecmul, vsum, dot 4 and dot 5 have no gated power (bundles before D168)
LIMIT_MAC_WS = (1, 8)


def unit_of(design: str, top: str) -> str:
    """A unit's name from its cell's design: the top's tag (snax_forge_ or snax_forge_<design>_) removed."""
    return design.removeprefix(top.removesuffix("shell_wrapper"))


def model_json(D: dict, points: list[dict]) -> tuple[dict, dict]:
    """{tech: char.json}, {tech: spreads}: built again from the CSVs and checked equal to the files."""
    import char_export as ce
    J, S = {}, {}
    for t in TECHS:
        J[t], S[t] = ce.build(t, D[t], points)
        p = ce.path(t)
        if not p.is_file() or p.read_text() != ce.dumps(J[t]):
            fail(f"{p.relative_to(ROOT)} is not current: pixi run char-export")
    return J, S


def model_constants(J: dict, S: dict) -> list[str]:
    rows = []
    for t in TECHS:
        j, s = J[t], S[t]
        for name, k, val in (("flop.e_load_fj", "load", j["flop"]["e_load_fj"]),
                             ("flop.e_hold_fj", "hold", j["flop"]["e_hold_fj"])):
            x = s[k]
            rows.append([t, f"`{name}`", f(val), x["n"], f(x["min"]), f(x["max"]), f(x["sd"]), f"{x['range_pct']:.2f} %"])
        c = s["ctrl"]
        rows.append([t, "`ctrl.counter_factor`", f"{j['ctrl']['counter_factor']:.2f}", c["n"], f(c["min"]), f(c["max"]),
                     f(c["sd"]), f"{c['range_pct']:.2f} %"])
    area = "; ".join(f"{t} {J[t]['flop']['area_um2']} µm²" for t in TECHS)
    spread = "; ".join(f"{t} {S[t]['area']['min']:.4f} to {S[t]['area']['max']:.4f}" for t in TECHS)
    return [f"`flop.area_um2` is the mean of `seq_area_um2 / seq_cells` over the 21 registered points (flops and clock "
            f"gates): {area} ({spread}).", "",
            table(["tech", "constant", "value", "points", "min", "max", "sd", "range"], rows), "",
            "e_load is the mean busy e_bit of the points whose flops all load every cycle (Mac, TreeAccumulate and "
            "SerialAccumulate busy, LinkBuffer depth 1 stream); e_hold the mean idle e_bit (as above); the counter "
            "factor, per tier-done forge point ctrl/ctrl's e_dyn per cycle (`power_pt_modules.csv`) over its sequential "
            f"cells x e_hold, the mean over the {S[TECHS[0]]['ctrl']['n']} points with a power row rounded to two "
            "decimals (tier done's 48 but the 7 W = 32 bundles made before snax-forge D168, which have none). "
            "`synth_dc_modules.csv` has no per-module `seq_cells`: ctrl's cells are its `seq_um2` / `flop.area_um2`, "
            "rounded. The factor spreads widely: a gated control unit's energy follows its counters' activity more than "
            "its cell count."]


def model_points(D: dict, J: dict) -> list[str]:
    import char_export as ce
    head = ["point", "n_bits"]
    for t in TECHS:
        tag = t.removeprefix("nangate")
        head += [f"{tag} e_comb", f"{tag} e_fire", f"{tag} n_bits e_hold"]
    rows = []
    for dp, prefix in BLOCKS:
        _, brows = block_rows(D, prefix)
        for br in brows:
            p = br[0].strip("`")
            v = D[TECHS[0]][p]
            if check_only(dp, v["params"]):
                continue
            row = [br[0], ce.n_bits(dp, v["params"])]
            for t in TECHS:
                j = J[t]
                row += [f(ce.e_comb_at(j, dp, v["params"])), f(ce.e_fire(j, dp, v["params"])),
                        f(ce.e_hold_pj(j, ce.n_bits(dp, v["params"])))]
            rows.append(row)
    return [table(head, rows)]


def syn2_units(t: str, D: dict, point: str, w: int, mods: list[dict], top: str) -> list[dict]:
    """The forge point's units of `point` in block order: {name (the unit), design (the block module), char (the char point at
    W whose top it is), datapath, params, e (pJ per cycle)}."""
    out = []
    for m in mods:
        mm = re.fullmatch(rf"{top}/dp/blocks_(\d+)_\d+", m["path"])
        if m["point"] != point or not mm:
            continue
        unit = unit_of(m["design"], top)
        blk = [x for x in mods if x["point"] == point and x["path"] == m["path"] + "/m"]
        if len(blk) != 1:
            fail(f"{t}: {point}: {m['path']}: {len(blk)} block cells")
        chars = [p for p, v in D[t].items() if v["params"].get("lanes") == w
                 and re.fullmatch(rf"{v['synth']['top']}(_\d+)?", blk[0]["design"])]
        if len(chars) != 1:
            fail(f"{t}: {point}: {blk[0]['design']}: {len(chars)} char points at W = {w}")
        v = D[t][chars[0]]
        out.append({"k": int(mm.group(1)), "name": unit, "design": blk[0]["design"], "char": chars[0],
                    "datapath": v["datapath"], "params": v["params"], "e": float(blk[0]["e_dyn_pj"])})
    return sorted(out, key=lambda u: u["k"])


def fires(t: str, point: str, w: int, config: str, units: list[dict], cat: dict) -> list[int]:
    """n_fire per unit along the chain: the sink gives JOBS results, a unit before s gives R_s T_s, and fires R T
    span times (T its JOB_BEATS, else 1; span blocks.json's, `lanes` = W). The head must fire N / W."""
    kv = dict(x.split("=") for x in config.split())
    jobs = int(kv.pop("JOBS"))
    T = {u["name"]: int(kv.pop(f"{u['name']}.JOB_BEATS", 1)) for u in units}
    if kv:
        fail(f"{t}: {point}: config {config}: {sorted(kv)} not a unit's")
    out, r = [], jobs
    for u in reversed(units):
        span = cat[u["datapath"]]["span"]
        span = w if span == "lanes" else int(span)
        out.append(r * T[u["name"]] * span)
        r *= T[u["name"]]
    out.reverse()
    if out[0] != N // w:
        fail(f"{t}: {point}: the head fires {out[0]}, N / W = {N // w}")
    return out


def model_syn2(D: dict, J: dict) -> tuple[list[str], list[str]]:
    import char_export as ce
    cat = ce.catalogue_at(next(iter(D[TECHS[0]].values()))["synth"]["snax_forge_commit"])
    drows, urows = [], []
    for t in TECHS:
        j = J[t]
        pwr = {r["point"]: r for r in read_csv(RES / "forge" / t / "power_pt.csv") if r["size"] == f"n{N}"}
        mods = read_csv(RES / "forge" / t / "power_pt_modules.csv")
        bits = ce.ctrl_bits(t, j["flop"]["area_um2"])
        for name, pat in MODEL_DESIGNS:
            for w in MODEL_WS:
                p = pat.format(w)
                cyc = int(pwr[p]["cycles"])
                top = pwr[p]["top"]
                units = syn2_units(t, D, p, w, mods, top)
                nf = fires(t, p, w, pwr[p]["config"], units, cat)
                per = {m["path"]: float(m["e_dyn_pj"]) for m in mods if m["point"] == p}
                dp_s, ctrl_s = per[f"{top}/dp"] * cyc, per[f"{top}/ctrl/ctrl"] * cyc
                dp_m = dp_r = 0.0
                for u, n in zip(units, nf):
                    nb = ce.n_bits(u["datapath"], u["params"])
                    fire_part = n * ce.e_fire(j, u["datapath"], u["params"])
                    hold_part = cyc * ce.e_hold_pj(j, nb)
                    um, us = fire_part + hold_part, u["e"] * cyc
                    dp_m += um
                    dp_r += ce.e_unit(j, u["datapath"], u["params"], n, cyc, rule_only=True)
                    urows.append([t, name, w, f"{u['name']}: {u['datapath']}", n, nb, cyc, f(fire_part / 1000, 3),
                                  f(hold_part / 1000, 3), f(um / 1000, 3), f(us / 1000, 3), f"{um / us:.3f}"])
                cm = ce.e_ctrl(j, bits[p], cyc)
                km, ks, kr = dp_m + cm, dp_s + ctrl_s, dp_r + cm
                drows.append([t, name, w, ", ".join(f"{u['datapath']} {n}" for u, n in zip(units, nf)), cyc, bits[p],
                              f(dp_m / 1000, 3), f(dp_s / 1000, 3), f"{dp_m / dp_s:.3f}",
                              f(cm / 1000, 3), f(ctrl_s / 1000, 3), f"{cm / ctrl_s:.3f}",
                              f(km / 1000, 3), f(ks / 1000, 3), f"{km / ks:.3f}", f"{kr / ks:.3f}"])
    dt = table(["tech", "design", "W", "units, n_fire", "C_acc", "ctrl bits", "datapath model", "datapath forge", "ratio",
                "ctrl model", "ctrl forge", "ratio", "kernel model", "kernel forge", "ratio", "ratio, rules only"], drows)
    ut = table(["tech", "design", "W", "unit", "n_fire", "n_bits", "C_acc", "n_fire e_fire", "C_acc n_bits e_hold",
                "model", "forge", "ratio"], urows)
    return [dt], [ut]


def main() -> int:
    points = json.loads(POINTS.read_text())
    D = {t: load(t, points) for t in TECHS}
    commits = {"snax_forge": next(iter(D[TECHS[0]].values()))["synth"]["snax_forge_commit"],
               "sfe": git("log", "-1", "--format=%H", "--", *(f"results/char/{t}/char_power.csv" for t in TECHS))}
    if any(next(iter(D[t].values()))["synth"]["snax_forge_commit"] != commits["snax_forge"] for t in TECHS):
        fail("the technologies name different snax-forge commits")

    L = ["# The blocks alone, int8 to int64", "",
         "Generated by `report/char_table.py` (`pixi run char-table`) from `results/char/<tech>/char_synth.csv` and "
         "`char_power.csv`; the known limits also read the files they cite. Do not edit by hand.", "",
         f"- **Commits:** snax-forge `{commits['snax_forge']}` (every row); snax-forge-experiments `{commits['sfe']}` "
         "(the commit that wrote the power CSVs).",
         f"- **Settings:** clock {CLOCK} ns; synthesis as SYN1 and SYN2 (X1 to X4, X22; the block as top, X30), clock-gated "
         "(X79 · X87 · X88; a clock gate is a sequential cell, X83); power "
         f"rand64 seed {SEED}, {CYCLES} cycles per window (SerialAccumulate's busy: {CYCLES} beats of W cycles), "
         "inputs at the rising edge, a lead-in slot before each window, the VCD cut per window (X31, X32).",
         "- **Units:** area µm²; energy pJ per cycle of the window (e_comb, e_flop = clock + register + sequential, "
         "e_dyn = the two); e_bit and e_hold fJ per sequential cell per cycle.",
         "- **Windows:** busy (a fire every cycle; FifoPacker a push every cycle, its output always ready) and idle "
         "(the enable at 0, every other input held) for SimdLanes, Mac, TreeAccumulate, SerialAccumulate and "
         "FifoPacker; stream for LinkBuffer (a load every cycle at full occupancy), a link that is not loading costing "
         "its flops x e_hold (X33).",
         "- **Types:** the int64 set (CHAR1's 27 points) gives the flop constants and the lanes rules; every compute "
         "block has its 10 (in, out) pairs, out at least in, the op at out, at one lane count W0 (SimdLanes 1, the "
         "others 8), each input port at its own width with rand64's low bits (X89).", "",
         "## e_hold", ""]
    rows = []
    for t in TECHS:
        h = ehold(D[t])
        rows.append([t, h["n"], f(h["mean"]), f(h["min"]), f(h["max"]), f(h["sd"]),
                     f"{100 * (h['max'] - h['min']) / h['mean']:.2f} %"])
    L += ["The mean idle e_bit of the registered int64 blocks (Mac, TreeAccumulate, SerialAccumulate), fJ per sequential cell "
          "per cycle. A gated register holds at its clock gate's cost, shared by the bits behind it, so the spread follows "
          "the bits per gate (X83):",
          "", table(["tech", "points", "e_hold", "min", "max", "sd", "range"], rows), ""]
    for dp, prefix in BLOCKS:
        head, rows = block_rows(D, prefix)
        L += [f"## {dp}", "", table(head, rows), "", "How it scales:", "", *scaling(D, prefix), ""]
    J, S = model_json(D, points)
    L += ["## The type axis", "", *types_section(D, J)]
    designs, units = model_syn2(D, J)
    L += ["## Model", "",
          "The table snax-forge reads is `results/char/<tech>/char.json` (`report/char_export.py`, `pixi run "
          "char-export`; X37). Registers are bits: a flop that loads costs e_load per cycle, one that holds e_hold; a "
          "block keeps its comb part per fire (its busy window's e_comb; LinkBuffer's stream, per load); ctrl is its "
          "flops x e_hold x a counter factor. Per unit and task, with C_acc the task's cycles:", "",
          "$$E_{\\mathit{unit}} = n_{\\mathit{fire}}\\thinspace\\big(e_{\\mathit{comb}} + n_{\\mathit{bits}}\\thinspace"
          "(e_{\\mathit{load}} - e_{\\mathit{hold}})\\big) + C_{\\mathit{acc}}\\thinspace n_{\\mathit{bits}}\\thinspace "
          "e_{\\mathit{hold}}, \\qquad E_{\\mathit{ctrl}} = f_{\\mathit{ctrl}}\\thinspace n_{\\mathit{bits}}^{\\mathit{ctrl}}"
          "\\thinspace C_{\\mathit{acc}}\\thinspace e_{\\mathit{hold}}$$", "",
          "### The constants", "", *model_constants(J, S), "",
          "### Per block point", "",
          "e_fire = e_comb + n_bits (e_load - e_hold), pJ per fire, and the hold term n_bits e_hold, pJ per cycle, "
          "from char.json at each measured point. n_bits is the block's register bits from its params (lanes x depth "
          "x the output's width; SimdLanes none; FifoPacker its held slots and counter, of which (r - 1) / r of a slot "
          "and the counter load per push, r = d_out); `seq_cells` adds the block's clock gates, one per register "
          "enable (`pixi run char-export` prints each). A lanes value "
          "char.json does not hold takes the entry's `lanes_rule`: `copy`, W / W0 x the point at W0 (SimdLanes, "
          "Mac, LinkBuffer, whose W = 8 and 32 points are the copy's checks above); `interpolate`, linear in lanes "
          "(the int64 TreeAccumulate and SerialAccumulate); `slope`, a narrow fold's point at W0 = 8 plus its slope per "
          "lane (the type axis, above); a LinkBuffer at a narrower dtype is the int64 one x w / 64.", "",
          *model_points(D, J), "",
          "### Against the forge points", "",
          f"vecmul, vsum, dot 4 and dot 5 at W = {', '.join(map(str, MODEL_WS))} (their W = 32 points have no gated power), "
          f"n = {N}, energy per task in nJ. Per design its units in "
          "block order, each firing along the chain from `power_pt.csv`'s config: the sink gives JOBS results, a unit "
          "before it the sink's T per result, and a unit fires its results x its T x its span (blocks.json's; "
          f"SerialAccumulate's is lanes): the streaming unit N / W, a T = 1 TreeAccumulate sum once, a SerialAccumulate "
          "sum W times. C_acc is the run's cycles (`power_pt.csv`), ctrl's bits its sequential cells (`synth_dc_modules.csv`, "
          "seq_um2 / flop area). forge is `power_pt_modules.csv`'s e_dyn per cycle x cycles: datapath `dp`, ctrl "
          "`ctrl/ctrl`, kernel the two, each unit its block cell. Model uses char.json's point at the design's W; "
          "the last column, \"ratio, rules only\", takes every e_comb from the lanes rule instead (W x the lanes-1 point for "
          "SimdLanes and Mac).", "",
          *designs, "",
          "Per unit:", "", *units, "",
          "The model leaves out the csr, the memory and the streamers. A sum that fires once (dot 4's) or W times "
          "(dot 5's) costs, inside its design, its inputs' toggling every cycle, which a per-fire model does not see; "
          "it is under 3 % of the kernel. dot 4's sum alone keeps the feedback adder its tied `first` removes inside "
          "dot 4 (the free `first`, below): it costs area, which this check does not compare.", ""]
    L += ["## Known limits", "",
          "**The free `first`.** A TreeAccumulate alone has its `first` driven; inside dot 4 it is tied and firtool "
          "folds it (R0, `results/char/runs/2026-11-03_char1_r0.md`), so the block alone is larger than dot 4's sum by:",
          "", *limit_first(D), "",
          f"**An isolated fire costs more than a back-to-back one.** R1's duty50 window (a fire every other cycle) against "
          f"the mean of busy and idle, from R1's `char_power.csv` at `{R1_COMMIT[:7]}` ([{Path(R1_NOTE).name}](runs/"
          f"{Path(R1_NOTE).name})): with a fire every other cycle the inputs change at one edge and the accumulator "
          "at the next, so its adders settle twice per fire. busy and idle do not model it; R2 dropped duty50 (X34).",
          "", *limit_isolated(), "",
          "**The Mac inside dot 4 to 6.** The Mac fires N / W of the run's cycles, the rest being the sum's tail "
          f"(N = {N}), so its energy per cycle inside sits below busy alone; busy and idle reproduce the tail: model = "
          "(fires E_busy + (cycles - fires) E_idle) / cycles, the cycles from the forge point's `power_pt.csv`, inside "
          "from its `power_pt_modules.csv`. What is left is the Mac alone against inside, at W = "
          f"{', '.join(map(str, LIMIT_MAC_WS))} (W = 32 has no gated power):", "", *limit_mac(D), ""]
    OUT.write_text("\n".join(L))
    print(f"wrote {OUT.relative_to(ROOT)} for {', '.join(TECHS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
