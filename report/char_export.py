#!/usr/bin/env python3
"""report/char_export.py - the block model snax-forge reads, results/char/<tech>/char.json, from the clock-gated rows.

  pixi run char-export

Reads results/char/<tech>/char_synth.csv and char_power.csv, char/points.json and blocks.json at the blocks'
snax-forge commit (git show in the sibling checkout) for the params, and for the control factor the tier-done forge
points' power_pt_modules.csv and synth_dc_modules.csv. Writes the flop constants (area, e_load, e_hold), the control
factor and per block its comb area and energy per fire with a lanes rule (copy or interpolate). The fields and the
model are in results/char/README.md; a clock gate counts as a sequential cell (X83 · X85).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import char_table as ct  # noqa: E402

BLOCKS_JSON = ct.ROOT.parent / "snax-forge" / "hw" / "chisel" / "blocks.json"
RULES = {"ElementwiseLanes": "copy", "Mac": "copy", "LinkBuffer": "copy", "TreeAccumulate": "interpolate",
         "SerialAccumulate": "interpolate"}
SHAPE = ("lanes", "depth")
LOAD_KINDS = ("Mac", "TreeAccumulate", "SerialAccumulate")    # busy: every flop loads every cycle
# the tier-done points with a gated power row: 48 but the 7 W = 32 bundles made before snax-forge D168 (X37)
FORGE_POINTS = 41


def fail(msg: str) -> None:
    sys.exit(f"char_export: {msg}")


def width(dtype: str) -> int:
    m = re.fullmatch(r"u?int(\d+)", dtype)
    if not m:
        fail(f"dtype {dtype}: not an integer type")
    return int(m.group(1))


def n_bits(datapath: str, params: dict) -> int:
    """A block's flops from its params: its registers' bits."""
    w = params.get("lanes", 1)
    if datapath == "ElementwiseLanes":
        return 0
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
         if int(v["synth"]["seq_cells"])}
    return {**stats(list(a.values())), "points": a}


def e_load(d: dict) -> dict:
    vals = {}
    for p, v in d.items():
        if v["datapath"] in LOAD_KINDS:
            vals[p] = 1000 * ct.e(d, p, "busy", "e_bit_pj")
        elif v["datapath"] == "LinkBuffer" and v["params"]["depth"] == 1:
            vals[p] = 1000 * ct.e(d, p, "stream", "e_bit_pj")
    return {**stats(list(vals.values())), "points": vals}


def e_hold(d: dict) -> dict:
    """char_table.md's e_hold: the mean idle e_bit of the registered blocks."""
    vals = {p: 1000 * ct.e(d, p, "idle", "e_bit_pj") for p, v in d.items() if v["datapath"] in ct.REGISTERED}
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
    """f_ctrl, the mean over the tier-done forge points with a power row of ctrl/ctrl's e_dyn per cycle over its
    cells x e_hold."""
    ok = {r["point"] for r in ct.read_csv(ct.RES / "forge" / tech / "power_pt.csv")
          if r["status"] == "ok" and r["size"] == f"n{ct.N}"}
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


def check_params(datapath: str, params: dict, cat: dict, where: str) -> None:
    spec = cat.get(datapath)
    if spec is None:
        fail(f"{where}: {datapath} is not in blocks.json")
    if set(params) != set(spec["params"]):
        fail(f"{where}: params {sorted(params)}, blocks.json's {datapath} has {sorted(spec['params'])}")
    for k, v in params.items():
        s = spec["params"][k]
        ok = {"dtype": lambda: v in s["values"], "op": lambda: v in s["values"],
              "dtypes": lambda: isinstance(v, list) and all(x in s["values"] for x in v),
              "int": lambda: isinstance(v, int) and v >= s.get("min", v), "bool": lambda: isinstance(v, bool)}
        if s["type"] not in ok or not ok[s["type"]]():
            fail(f"{where}: {k} = {v!r} not allowed by blocks.json ({s})")


def blocks(d: dict, points: list[dict], cat: dict) -> dict:
    """char.json's blocks: params checked against blocks.json; seq_cells against the bits printed where they differ
    (a clock gate is a sequential cell)."""
    out: dict = {}
    for p in points:
        name, dp, params = p["point"], p["datapath"], p["params"]
        check_params(dp, params, cat, name)
        flops = int(d[name]["synth"]["seq_cells"])
        if flops != n_bits(dp, params):
            print(f"{name}: {flops} sequential cells, its bits are {n_bits(dp, params)}")
        key = {k: v for k, v in params.items() if k not in SHAPE}
        win = "stream" if dp == "LinkBuffer" else "busy"
        pt = {"lanes": params["lanes"], **({"depth": params["depth"]} if dp == "LinkBuffer" else {}),
              "comb_um2": float(d[name]["synth"]["comb_area_um2"]), "e_comb_pj": ct.e(d, name, win, "e_comb_pj")}
        entries = out.setdefault(dp, [])
        entry = next((x for x in entries if x["params"] == key), None)
        if entry is None:
            entry = {"params": key, "lanes_rule": RULES[dp], "points": []}
            entries.append(entry)
        entry["points"].append(pt)
    for dp, entries in out.items():
        for x in entries:
            x["points"].sort(key=lambda q: (q.get("depth", 0), q["lanes"]))
            have = {(q["lanes"], q.get("depth", 1)) for q in x["points"]}
            need = {(1, q.get("depth", 1)) for q in x["points"]} if x["lanes_rule"] == "copy" else set()
            if not need <= have:
                fail(f"{dp} {x['params']}: copy without its lanes-1 points {sorted(need - have)}")
    return out


def sfe_commit(tech: str) -> str:
    return ct.git("log", "-1", "--format=%H", "--", f"results/char/{tech}/char_synth.csv",
                  f"results/char/{tech}/char_power.csv")


def build(tech: str, d: dict, points: list[dict]) -> tuple[dict, dict]:
    """(char.json, the spreads behind its constants) from the gated rows `d`."""
    commit = next(iter(d.values()))["synth"]["snax_forge_commit"]
    area = flop_area(d)
    area_um2 = round(area["mean"], 6)
    load, hold = e_load(d), e_hold(d)
    hold_fj = round(hold["mean"], 4)
    cf = counter_factor(tech, area_um2, hold_fj)
    j = {"tech": tech, "clock_ns": float(ct.CLOCK),
         "units": {"area": "um2", "energy": "pJ", "flop_energy": "fJ per flop per cycle"},
         "source": {"snax_forge": commit, "snax_forge_experiments": sfe_commit(tech),
                    "stimulus": f"rand64 seed {ct.SEED}", "clk_gate": "1"},
         "flop": {"area_um2": area_um2, "e_load_fj": round(load["mean"], 4), "e_hold_fj": hold_fj},
         "ctrl": {"counter_factor": cf["value"]},
         "blocks": blocks(d, points, catalogue_at(commit))}
    return j, {"area": area, "load": load, "hold": hold, "ctrl": cf}


# ---------------------------------------------------------------- the model, read from char.json
def entry_of(j: dict, datapath: str, params: dict) -> dict:
    key = {k: v for k, v in params.items() if k not in SHAPE}
    for x in j["blocks"].get(datapath, []):
        if x["params"] == key:
            return x
    fail(f"{j['tech']}: no {datapath} entry with params {key}")


def e_comb_at(j: dict, datapath: str, params: dict, rule_only: bool = False) -> float:
    """e_comb at params' lanes (and depth): the point itself when char.json has it (unless rule_only), else the
    entry's lanes_rule: copy, lanes x the lanes-1 point at that depth; interpolate, linear in lanes."""
    x = entry_of(j, datapath, params)
    lanes, depth = params.get("lanes", 1), params.get("depth")
    pts = [q for q in x["points"] if q.get("depth") == depth]
    at = {q["lanes"]: q["e_comb_pj"] for q in pts}
    if lanes in at and not (rule_only and x["lanes_rule"] == "copy"):
        return at[lanes]
    if x["lanes_rule"] == "copy":
        if 1 not in at:
            fail(f"{datapath} {params}: no lanes-1 point to copy")
        return lanes * at[1]
    lo = max((w for w in at if w <= lanes), default=None)
    hi = min((w for w in at if w >= lanes), default=None)
    if lo is None or hi is None:
        fail(f"{datapath} {params}: lanes {lanes} outside the points {sorted(at)}")
    return at[lo] if lo == hi else at[lo] + (at[hi] - at[lo]) * (lanes - lo) / (hi - lo)


def e_fire(j: dict, datapath: str, params: dict, rule_only: bool = False) -> float:
    """pJ per fire: e_comb + n_bits (e_load - e_hold)."""
    f = j["flop"]
    return e_comb_at(j, datapath, params, rule_only) + n_bits(datapath, params) * (f["e_load_fj"] - f["e_hold_fj"]) / 1000


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
            es.append(f'   {{"params": {one(x["params"])}, "lanes_rule": {one(x["lanes_rule"])},\n'
                      f'    "points": [\n{pts}\n    ]}}')
        dps.append(f'  {one(dp)}: [\n' + ",\n".join(es) + "\n  ]")
    out += ",\n".join(dps) + "\n }\n}\n"
    if json.loads(out) != j:
        fail("dumps: the layout changed the content")
    return out


def main() -> int:
    points = json.loads(ct.POINTS.read_text())
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
