#!/usr/bin/env python3
"""report/char_export.py - the block model snax-forge reads, results/char/<tech>/char.json, from the clock-gated rows.

  pixi run char-export

Reads results/char/<tech>/char_synth.csv and char_power.csv, char/points.json and blocks.json at the blocks'
snax-forge commit (git show in the sibling checkout) for the params, and for the control factor the tier-done forge
points' power_pt_modules.csv and synth_dc_modules.csv. Writes the flop constants (area, e_load, e_hold, from the int64
points), the control factor and per block and type pair its comb area and energy per fire with a lanes rule (copy,
interpolate, slope; X89; the stream blocks none, one point per entry, X94), and a Mac bank's two forms (X97, `bank`). The narrow points that check a rule
(char_table.check_only) are not written. The fields and the model are in results/char/README.md; a clock gate counts
as a sequential cell (X83 · X85). A block whose rows name another snax-forge commit than the first row's (FifoSlicer's)
has it as source.snax_forge_<block>; the mixed pairs (X98, a SimdLanes or Mac whose a and b differ in width, each
its own entry with its exact inTypes) as source.snax_forge_mixed.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import char_table as ct  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "char"))
import checks  # noqa: E402  the bank's forms (X97)

BLOCKS_JSON = ct.ROOT.parent / "snax-forge" / "hw" / "chisel" / "blocks.json"
RULES = {"SimdLanes": "copy", "Mac": "copy", "LinkBuffer": "copy", "TreeAccumulate": "interpolate",
         "SerialAccumulate": "interpolate", "FifoPacker": "none", "FifoSlicer": "none"}
SHAPE = ("lanes", "depth")
SLOPE_WS = (8, 32)              # a fold's int64 cost per lane is taken between these lanes (X89)
# FifoPacker and FifoSlicer are not in blocks.json (the flow places them on a packed output and a sliced input,
# snax-forge D174, D180): their params here
LANE_TYPES = {"type": "dtype", "values": [f"{u}int{w}" for u in ("", "u") for w in (8, 16, 32, 64)]}
PACKER = {"inLanes": {"type": "int", "min": 1}, "laneType": LANE_TYPES, "words": {"type": "int", "min": 1}}
SLICER = {"words": {"type": "int", "min": 1}, "laneType": LANE_TYPES, "outLanes": {"type": "int", "min": 1}}
STREAM = {"FifoPacker": PACKER, "FifoSlicer": SLICER}
COMB = ("comb_um2", "e_comb_pj")
LOAD_KINDS = ("Mac", "TreeAccumulate", "SerialAccumulate")    # busy: every flop loads every cycle
# the int64 tier-done points, every one with a gated power row (X37); the narrow ones (a types= set) are T7's check
FORGE_POINTS = 48
FORGE_LIST = ct.ROOT / "forge" / "points.json"


def forge_int64() -> set[str]:
    """forge/points.json's tier-done points at int64: no `types=` among their sets."""
    pts = json.loads(FORGE_LIST.read_text())
    return {p["point"] for p in pts if p["point"].startswith("done/")
            and not any(s.startswith("types=") for s in p.get("sets", []))}


def fail(msg: str) -> None:
    sys.exit(f"char_export: {msg}")


width = ct.width


def packer_r(params: dict) -> int:
    """A FifoPacker's in-beats per out-beat (d_out for one lane in)."""
    return params["words"] * 64 // width(params["laneType"]) // params["inLanes"]


def slicer_r(params: dict) -> int:
    """A FifoSlicer's pops per in-beat (d_in at one word in)."""
    return params["words"] * 64 // width(params["laneType"]) // params["outLanes"]


def load_bits(datapath: str, params: dict) -> float:
    """The bits that load on a fire: every register bit, but a stream block's: a FifoPacker's one held slot of r - 1
    on r - 1 of r pushes (the r-th sends) and the counter on every push; a FifoSlicer's word on one pop of r (the
    last pop's take), so 64 words / r a pop, and the counter on every pop (its full flag holds while it streams)."""
    if datapath == "FifoSlicer":
        r = slicer_r(params)
        return params["words"] * 64 / r + math.ceil(math.log2(r))
    if datapath != "FifoPacker":
        return n_bits(datapath, params)
    r = packer_r(params)
    return (r - 1) / r * params["inLanes"] * width(params["laneType"]) + math.ceil(math.log2(r))


def n_bits(datapath: str, params: dict) -> int:
    """A block's flops from its params: its registers' bits."""
    w = params.get("lanes", 1)
    if datapath == "SimdLanes":
        return 0
    if datapath == "FifoPacker":
        r = packer_r(params)
        return (r - 1) * params["inLanes"] * width(params["laneType"]) + math.ceil(math.log2(r))
    if datapath == "FifoSlicer":                    # the held word, its pop count and its full flag
        return params["words"] * 64 + math.ceil(math.log2(slicer_r(params))) + 1
    if datapath == "Mac":
        return w * width(params["outType"]) if params["accumulate"] or params["regOut"] else 0
    if datapath in ("TreeAccumulate", "SerialAccumulate"):
        return width(params["outType"])
    if datapath == "LinkBuffer":
        return w * params["depth"] * width(params["dtype"])
    fail(f"{datapath}: no register rule")


def stats(vals: list[float]) -> dict:
    mean = sum(vals) / len(vals)
    sd = (sum((x - mean) ** 2 for x in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
    return {"mean": mean, "min": min(vals), "max": max(vals), "sd": sd, "n": len(vals),
            "range_pct": 100 * (max(vals) - min(vals)) / mean}


def flop_area(d: dict) -> dict:
    """The mean of seq_area / seq_cells over the points with sequential cells (flops and clock gates), its spread."""
    a = {p: float(v["synth"]["seq_area_um2"]) / int(v["synth"]["seq_cells"]) for p, v in d.items()
         if int(v["synth"]["seq_cells"]) and ct.is64(v["params"])}
    return {**stats(list(a.values())), "points": a}


def e_load(d: dict) -> dict:
    vals = {}
    for p, v in d.items():
        if not ct.is64(v["params"]):
            continue
        if v["datapath"] in LOAD_KINDS:
            vals[p] = 1000 * ct.e(d, p, "busy", "e_bit_pj")
        elif v["datapath"] == "LinkBuffer" and v["params"]["depth"] == 1:
            vals[p] = 1000 * ct.e(d, p, "stream", "e_bit_pj")
    return {**stats(list(vals.values())), "points": vals}


def e_hold(d: dict) -> dict:
    """char_table.md's e_hold: the mean idle e_bit of the registered blocks."""
    vals = {p: 1000 * ct.e(d, p, "idle", "e_bit_pj") for p, v in d.items()
            if v["datapath"] in ct.REGISTERED and ct.is64(v["params"])}
    s = stats(list(vals.values()))
    if abs(s["mean"] - ct.ehold(d)["mean"]) > 1e-12:
        fail("e_hold differs from char_table.md's")
    return {**s, "points": vals}


def ctrl_bits(tech: str, area: float) -> dict:
    """{forge point: ctrl/ctrl's sequential cells}, seq_um2 / the mean cell area, rounded (a clock gate counts as one)."""
    return {r["point"]: round(float(r["seq_um2"]) / area)
            for r in ct.read_csv(ct.RES / "forge" / tech / "synth_dc_modules.csv") if r["path"] == "ctrl/ctrl"}


def is_ctrl(path: str) -> bool:
    """power_pt_modules.csv's ctrl/ctrl under the point's top, whatever the top's name."""
    return path.count("/") == 2 and path.endswith("/ctrl/ctrl")


def counter_factor(tech: str, area: float, hold_fj: float) -> dict:
    """f_ctrl, the mean over the int64 tier-done forge points of ctrl/ctrl's e_dyn per cycle over its cells x
    e_hold."""
    ok = {r["point"] for r in ct.read_csv(ct.RES / "forge" / tech / "power_pt.csv")
          if r["status"] == "ok" and r["size"] == f"n{ct.N}"} & forge_int64()
    e_ctrl = {r["point"]: float(r["e_dyn_pj"]) for r in ct.read_csv(ct.RES / "forge" / tech / "power_pt_modules.csv")
              if is_ctrl(r["path"]) and r["point"] in ok and r["point"].startswith("done/")}
    bits = {p: n for p, n in ctrl_bits(tech, area).items() if p in e_ctrl}
    if set(bits) != set(e_ctrl) or len(bits) != FORGE_POINTS:
        fail(f"{tech}: tier done's ctrl/ctrl in {len(bits)} synthesis and {len(e_ctrl)} power rows, {FORGE_POINTS} expected")
    per = {p: e_ctrl[p] / (bits[p] * hold_fj / 1000) for p in bits}
    s = stats(list(per.values()))
    return {**s, "value": round(s["mean"], 2), "points": per, "bits": bits, "e_ctrl": e_ctrl}


def catalogue_at(commit: str) -> dict:
    """blocks.json at snax-forge `commit` (git show in the sibling checkout, read only)."""
    done = subprocess.run(["git", "-C", str(BLOCKS_JSON.parents[2]), "show", f"{commit}:hw/chisel/blocks.json"],
                          capture_output=True, text=True)
    if done.returncode:
        fail(f"no blocks.json at snax-forge {commit} in {BLOCKS_JSON.parents[2]} (fetch that commit)")
    return json.loads(done.stdout)


def as_measured(datapath: str, params: dict, cat: dict) -> dict:
    """params without a bool the catalogue gained after the measuring commit, given false (Mac's seed): the block
    as measured, as snax-forge's char lookup drops a false seed no entry has."""
    spec = cat.get(datapath)
    if spec is None:
        return params
    return {k: v for k, v in params.items() if k in spec["params"] or v is not False}


def check_params(datapath: str, params: dict, cat: dict, where: str) -> None:
    spec = {"params": STREAM[datapath]} if datapath in STREAM else cat.get(datapath)
    if spec is None:
        fail(f"{where}: {datapath} is not in blocks.json")
    if set(params) != set(spec["params"]):
        fail(f"{where}: params {sorted(params)}, blocks.json's {datapath} has {sorted(spec['params'])}")
    for k, v in params.items():
        s = spec["params"][k]
        ok = {"dtype": lambda: v in s["values"], "op": lambda: v in s["values"],
              "dtypes": lambda: isinstance(v, list) and all(x in s["values"] for x in v),
              "int": lambda: isinstance(v, int) and v >= s.get("min", v), "bool": lambda: isinstance(v, bool),
              "const": lambda: v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))}
        if s["type"] not in ok or not ok[s["type"]]():
            fail(f"{where}: {k} = {v!r} not allowed by blocks.json ({s})")


def type_free(params: dict) -> dict:
    """params with every type at int64: the int64 entry a narrow fold takes its cost per lane from."""
    out = {}
    for k, v in params.items():
        out[k] = (["int64"] * len(v) if isinstance(v, list) else "int64") if k in ct.TYPE_KEYS else v
    return out


def blocks(d: dict, points: list[dict], cat: dict) -> dict:
    """char.json's blocks: per block one entry per params (lanes and depth aside, so one per type pair), params
    checked against blocks.json; seq_cells against the bits printed where they differ (a clock gate is a sequential
    cell). A narrow fold's entry has one point, at W0, and the slope rule: the int64 entry's cost per lane between
    SLOPE_WS times w_in / 64 (X89). The points char_table.check_only names are left out."""
    out: dict = {}
    for p in points:
        name, dp = p["point"], p["datapath"]
        params = as_measured(dp, p["params"], cat)
        check_params(dp, params, cat, name)
        if ct.check_only(dp, params):
            continue
        flops = int(d[name]["synth"]["seq_cells"])
        if flops != n_bits(dp, params):
            print(f"{name}: {flops} sequential cells, its bits are {n_bits(dp, params)}")
        key = {k: v for k, v in params.items() if k not in SHAPE}
        win = "stream" if dp == "LinkBuffer" else "busy"
        comb = {"comb_um2": float(d[name]["synth"]["comb_area_um2"]), "e_comb_pj": ct.e(d, name, win, "e_comb_pj")}
        if dp in STREAM:
            pt = {**comb, "flops": n_bits(dp, params), "load_bits": round(load_bits(dp, params), 6)}
        else:
            pt = {"lanes": params["lanes"], **({"depth": params["depth"]} if dp == "LinkBuffer" else {}), **comb}
        entries = out.setdefault(dp, [])
        entry = next((x for x in entries if x["params"] == key), None)
        if entry is None:
            rule = "slope" if dp in ct.FOLDS and not ct.is64(params) else RULES[dp]
            entry = {"params": key, "lanes_rule": rule, "points": []}
            entries.append(entry)
        entry["points"].append(pt)
    for dp, entries in out.items():
        for x in entries:
            x["points"].sort(key=lambda q: (q.get("depth", 0), q.get("lanes", 0)))
            if x["lanes_rule"] == "slope":
                base = next((y for y in entries if y["params"] == type_free(x["params"])), None)
                if base is None:
                    fail(f"{dp} {x['params']}: no int64 entry to take the cost per lane from")
                at = {q["lanes"]: q for q in base["points"]}
                lo, hi = SLOPE_WS
                if lo not in at or hi not in at:
                    fail(f"{dp} {base['params']}: the slope needs int64 points at lanes {SLOPE_WS}")
                w_in = ct.pair(x["params"])[0]
                x["slope"] = {c: round((at[hi][c] - at[lo][c]) / (hi - lo) * w_in / 64, 6) for c in COMB}
    return out


def sfe_commit(tech: str) -> str:
    return ct.git("log", "-1", "--format=%H", "--", f"results/char/{tech}/char_synth.csv",
                  f"results/char/{tech}/char_power.csv")


def build(tech: str, d: dict, points: list[dict]) -> tuple[dict, dict]:
    """(char.json, the spreads behind its constants) from the gated rows `d`."""
    commit = next(iter(d.values()))["synth"]["snax_forge_commit"]
    others = {f"snax_forge_{'mixed' if ct.mixed(v['params']) else v['datapath']}": v["synth"]["snax_forge_commit"]
              for v in d.values() if v["synth"]["snax_forge_commit"] != commit}
    area = flop_area(d)
    area_um2 = round(area["mean"], 6)
    load, hold = e_load(d), e_hold(d)
    hold_fj = round(hold["mean"], 4)
    cf = counter_factor(tech, area_um2, hold_fj)
    j = {"tech": tech, "clock_ns": float(ct.CLOCK),
         "units": {"area": "um2", "energy": "pJ", "flop_energy": "fJ per flop per cycle"},
         "source": {"snax_forge": commit, **others, "snax_forge_experiments": sfe_commit(tech),
                    "stimulus": f"rand64 seed {ct.SEED}", "clk_gate": "1"},
         "flop": {"area_um2": area_um2, "e_load_fj": round(load["mean"], 4), "e_hold_fj": hold_fj},
         "ctrl": {"counter_factor": cf["value"]}}
    bank = checks.bank_model(tech)
    if bank is not None:  # a Mac's bank of rows over its rows-1 entry (X97, snax-forge D193)
        j["bank"] = bank
    j["blocks"] = blocks(d, points, catalogue_at(commit))
    return j, {"area": area, "load": load, "hold": hold, "ctrl": cf}


# ---------------------------------------------------------------- the model, read from char.json
def table_key(j: dict, datapath: str, params: dict) -> dict:
    """params as char.json keys an entry: the shape aside, and a false bool no entry of the block has dropped (Mac's
    seed, which the table was measured before), as in as_measured."""
    have = {k for x in j["blocks"].get(datapath, []) for k in x["params"]}
    return {k: v for k, v in params.items() if k not in SHAPE and (k in have or v is not False)}


def entry_of(j: dict, datapath: str, params: dict) -> tuple[dict, float]:
    """(the entry for params, the factor its values take): a LinkBuffer at a dtype with no entry reads the int64
    entry scaled by its width over 64 (X89)."""
    key = table_key(j, datapath, params)
    for x in j["blocks"].get(datapath, []):
        if x["params"] == key:
            return x, 1.0
    if datapath == "LinkBuffer":
        k64 = {**key, "dtype": "int64"}
        for x in j["blocks"]["LinkBuffer"]:
            if x["params"] == k64:
                return x, width(key["dtype"]) / 64
    fail(f"{j['tech']}: no {datapath} entry with params {key}")


def comb_at(j: dict, datapath: str, params: dict, col: str = "e_comb_pj", rule_only: bool = False) -> float:
    """A comb column (`comb_um2` or `e_comb_pj`) at params' lanes (and depth): the point itself when char.json has
    it (unless rule_only), else the entry's lanes_rule: copy, lanes x the smallest-lanes point per lane; interpolate,
    linear in lanes; slope, the point nearest in lanes plus the entry's slope per lane; none, the one point."""
    x, scale = entry_of(j, datapath, params)
    if x["lanes_rule"] == "none":
        return x["points"][0][col]
    lanes, depth = params.get("lanes", 1), params.get("depth")
    at = {q["lanes"]: q[col] for q in x["points"] if q.get("depth") == depth}
    if not at:
        fail(f"{datapath} {params}: no point at depth {depth}")
    if lanes in at and not (rule_only and x["lanes_rule"] == "copy"):
        return scale * at[lanes]
    if x["lanes_rule"] == "copy":
        w0 = min(at)
        return scale * lanes * at[w0] / w0
    if x["lanes_rule"] == "slope":
        w0 = min(at, key=lambda w: (abs(w - lanes), w))
        return scale * (at[w0] + (lanes - w0) * x["slope"][col])
    lo = max((w for w in at if w <= lanes), default=None)
    hi = min((w for w in at if w >= lanes), default=None)
    if lo is None or hi is None:
        fail(f"{datapath} {params}: lanes {lanes} outside the points {sorted(at)}")
    return scale * (at[lo] if lo == hi else at[lo] + (at[hi] - at[lo]) * (lanes - lo) / (hi - lo))


def e_comb_at(j: dict, datapath: str, params: dict, rule_only: bool = False) -> float:
    """e_comb per fire at params' lanes (comb_at)."""
    return comb_at(j, datapath, params, "e_comb_pj", rule_only)


def e_fire(j: dict, datapath: str, params: dict, rule_only: bool = False) -> float:
    """pJ per fire: e_comb + the bits that load (e_load - e_hold)."""
    f = j["flop"]
    return e_comb_at(j, datapath, params, rule_only) + load_bits(datapath, params) * (f["e_load_fj"] - f["e_hold_fj"]) / 1000


def e_hold_pj(j: dict, bits: int) -> float:
    """pJ per cycle of `bits` held flops."""
    return bits * j["flop"]["e_hold_fj"] / 1000


def e_unit(j: dict, datapath: str, params: dict, fires: int, cycles: int, rule_only: bool = False) -> float:
    """E_unit = n_fire e_fire + C_acc n_bits e_hold, pJ."""
    return fires * e_fire(j, datapath, params, rule_only) + cycles * e_hold_pj(j, n_bits(datapath, params))


def e_ctrl(j: dict, bits: int, cycles: int) -> float:
    """E_ctrl = f_ctrl n_bits_ctrl C_acc e_hold, pJ."""
    return j["ctrl"]["counter_factor"] * cycles * e_hold_pj(j, bits)


def path(tech: str) -> Path:
    return ct.CHAR / tech / "char.json"


def dumps(j: dict) -> str:
    """indent 1, a block entry's params and each point on one line."""
    one = lambda x: json.dumps(x, separators=(", ", ": "))
    head = {k: v for k, v in j.items() if k != "blocks"}
    out = json.dumps(head, indent=1)[:-2] + ',\n "blocks": {\n'
    dps = []
    for dp, entries in j["blocks"].items():
        es = []
        for x in entries:
            pts = ",\n".join(f"     {one(q)}" for q in x["points"])
            slope = f', "slope": {one(x["slope"])}' if "slope" in x else ""
            es.append(f'   {{"params": {one(x["params"])}, "lanes_rule": {one(x["lanes_rule"])}{slope},\n'
                      f'    "points": [\n{pts}\n    ]}}')
        dps.append(f'  {one(dp)}: [\n' + ",\n".join(es) + "\n  ]")
    out += ",\n".join(dps) + "\n }\n}\n"
    if json.loads(out) != j:
        fail("dumps: the layout changed the content")
    return out


def main() -> int:
    points = ct.table_points()
    for t in ct.TECHS:
        d = ct.load(t, points)
        j, s = build(t, d, points)
        path(t).write_text(dumps(j))
        a = s["area"]
        print(f"{t}: flop area {j['flop']['area_um2']} um2, the mean of seq_area / seq_cells over {a['n']} points, "
              f"{a['min']:.4f} to {a['max']:.4f} (range {a['range_pct']:.2f} %)")
        for k, name in (("load", "e_load"), ("hold", "e_hold")):
            x = s[k]
            print(f"{t}: {name} {x['mean']:.4f} fJ over {x['n']} points, {x['min']:.4f} to {x['max']:.4f} "
                  f"(range {x['range_pct']:.2f} %, sd {x['sd']:.4f})")
        c = s["ctrl"]
        print(f"{t}: counter factor {c['value']:.2f} (mean {c['mean']:.4f} over {c['n']} forge points, "
              f"{c['min']:.4f} to {c['max']:.4f}, sd {c['sd']:.4f})")
        print(f"wrote {path(t).relative_to(ct.ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
