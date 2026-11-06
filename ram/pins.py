"""RAM1: Nangate 45 nm units and pin values for the SRAM macro generator -> ram/nangate45_pins.json.

    pixi run python ram/pins.py [--lib <NangateOpenCellLibrary_typical.lib>]

Reads the Liberty text next to the .db that syn/tech/nangate45.json points to and writes every value
the generator needs, each with its source (file, line, group path, attribute). The generator
(ram/ram.py) reads only the JSON, never the library.
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TECH = REPO / "syn" / "tech" / "nangate45.json"
OUT = REPO / "ram" / "nangate45_pins.json"

GROUP_RE = re.compile(r'^(\w+)\s*\(([^)]*)\)\s*\{$')
SIMPLE_RE = re.compile(r'^(\w+)\s*:\s*(.*?)\s*;$')
COMPLEX_RE = re.compile(r'^(\w+)\s*\((.*)\)\s*;$', re.S)


class Group:
    def __init__(self, kind, name, line, parent=None):
        self.kind, self.name, self.line, self.parent = kind, name, line, parent
        self.attrs = {}      # name -> (value, line)
        self.children = []

    def path(self):
        p, g = [], self
        while g is not None and g.kind != "file":
            p.append(f"{g.kind}({g.name})" if g.name else f"{g.kind}()")
            g = g.parent
        return "/".join(reversed(p))

    def find(self, kind, name=None):
        return [c for c in self.children if c.kind == kind and (name is None or c.name == name)]

    def one(self, kind, name=None):
        hits = self.find(kind, name)
        if len(hits) != 1:
            raise ValueError(f"{self.path()}: {len(hits)} groups {kind}({name})")
        return hits[0]


def statements(text):
    """Split Liberty text into (line, statement, terminator) at { } ; outside quotes, joining \\ continuations."""
    text = re.sub(r'/\*.*?\*/', lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r'\\[ \t]*\n', ' \x00', text)   # continuation: keep the newline count with a marker
    buf, line, start, quoted = [], 1, None, False
    for ch in text:
        if ch == "\n" or ch == "\x00":
            line += 1
            ch = " "
        if ch == '"':
            quoted = not quoted
        if not quoted and ch in "{};":
            yield start or line, "".join(buf).strip(), ch
            buf, start = [], None
            continue
        if start is None and not ch.isspace():
            start = line
        buf.append(ch)


def parse(text):
    root = Group("file", "", 0)
    cur = root
    for n, s, term in statements(text):
        if term == "}":
            if s:
                raise ValueError(f"line {n}: text before }}: {s[:80]!r}")
            cur = cur.parent
            if cur is None:
                raise ValueError(f"line {n}: unbalanced }}")
        elif term == "{":
            m = GROUP_RE.match(s + " {")
            if not m:
                raise ValueError(f"line {n}: cannot parse group {s[:80]!r}")
            g = Group(m.group(1), m.group(2).strip().strip('"'), n, cur)
            cur.children.append(g)
            cur = g
        elif not s:
            continue
        elif m := SIMPLE_RE.match(s + ";"):
            cur.attrs[m.group(1)] = (m.group(2).strip('"'), n)
        elif m := COMPLEX_RE.match(s + ";"):
            key = m.group(1)
            if key in cur.attrs:   # repeated complex attributes (voltage_map, fanout_length): keep each
                key = f"{key}#{n}"
            cur.attrs[key] = (m.group(2).strip(), n)
        else:
            raise ValueError(f"line {n}: cannot parse {s[:80]!r}")
    if cur is not root:
        raise ValueError("unbalanced braces")
    return root


def floats(s):
    return [float(x) for x in re.findall(r'[-+]?[0-9.]+(?:e[-+]?\d+)?', s)]


def table(g):
    i1 = floats(g.attrs["index_1"][0])
    i2 = floats(g.attrs["index_2"][0]) if "index_2" in g.attrs else None
    v = floats(g.attrs["values"][0])
    rows = [v[k * len(i2):(k + 1) * len(i2)] for k in range(len(i1))] if i2 else [v]
    return i1, i2, rows, g.attrs["values"][1]


def main():
    tech = json.loads(TECH.read_text())
    db = Path(os.environ.get(tech["lib_env"]) or REPO / tech["lib_default"]).resolve()   # as syn.py
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lib", type=Path, default=db.with_suffix(".lib"))
    args = ap.parse_args()
    lib_path = args.lib.resolve()
    rel = os.path.relpath(lib_path, REPO)
    text = lib_path.read_text()
    lib = parse(text).one("library")

    def src(g, attr, line=None, note=None):
        s = f"{rel}:{line if line is not None else g.attrs[attr][1]} {g.path()}/{attr}"
        return s + (f" ({note})" if note else "")

    def val(g, attr, conv=lambda x: x):
        return {"value": conv(g.attrs[attr][0]), "source": src(g, attr)}

    out = {
        "library": {
            "file": rel,
            "md5": hashlib.md5(lib_path.read_bytes()).hexdigest(),
            "db": os.path.relpath(db, REPO),
            "db_md5": hashlib.md5(db.read_bytes()).hexdigest() if db.exists() else None,
            "name": {"value": lib.name, "source": f"{rel}:{lib.line} library({lib.name})"},
        },
        "units": {k: val(lib, k) for k in
                  ["time_unit", "voltage_unit", "current_unit", "leakage_power_unit", "pulling_resistance_unit"]},
    }
    cap = lib.attrs["capacitive_load_unit"]
    out["units"]["capacitive_load_unit"] = {"value": cap[0].replace(" ", ""), "source": src(lib, "capacitive_load_unit")}
    for k in ["nom_process", "nom_voltage", "nom_temperature"]:
        out[k] = val(lib, k, float)
    oc = lib.one("operating_conditions")
    out["operating_conditions"] = {
        "name": {"value": oc.name, "source": f"{rel}:{oc.line} {oc.path()}"},
        **{k: val(oc, k, float) for k in ["process", "voltage", "temperature"]},
        "tree_type": val(oc, "tree_type"),
        "process_corner": val(oc, "process_corner"),
    }
    out["default_operating_conditions"] = val(lib, "default_operating_conditions")
    out["thresholds"] = {k: val(lib, k, float) for k in
                         ["slew_lower_threshold_pct_rise", "slew_lower_threshold_pct_fall",
                          "slew_upper_threshold_pct_rise", "slew_upper_threshold_pct_fall",
                          "input_threshold_pct_rise", "input_threshold_pct_fall",
                          "output_threshold_pct_rise", "output_threshold_pct_fall", "slew_derate_from_library"]}
    out["defaults"] = {k: val(lib, k, float) for k in
                       ["default_fanout_load", "default_inout_pin_cap", "default_input_pin_cap",
                        "default_output_pin_cap", "default_cell_leakage_power", "default_leakage_power_density"]}
    if any(k in lib.attrs for k in ("internal_power_unit", "dynamic_power_unit")):
        raise ValueError("library has an explicit internal power unit: read it instead of deriving one")
    cv, cu = re.match(r'([0-9.]+)\s*,\s*(\w+)', cap[0]).groups()
    vv = re.match(r'([0-9.]+)V', lib.attrs["voltage_unit"][0]).group(1)
    if (float(cv), cu.lower(), float(vv)) != (1.0, "ff", 1.0):
        raise ValueError("units other than 1 fF and 1 V: derive the internal power unit by hand")
    out["internal_power_unit"] = {
        "value": "1fJ",
        "source": (f"derived: capacitive_load_unit (1 fF, {rel}:{cap[1]}) x voltage_unit^2 (1 V, "
                   f"{rel}:{lib.attrs['voltage_unit'][1]}); the library has no internal_power_unit attribute; "
                   "dc_shell report_lib on the .db prints 'Dynamic Energy Unit : 0.001000pJ (derived from V,C units)' "
                   "(RAM1 R3)"),
    }

    # DFF_X1: D and CK capacitance, setup/hold of D against CK (largest entry), CK min pulse width (largest entry).
    dff = lib.one("cell", "DFF_X1")
    d, ck = dff.one("pin", "D"), dff.one("pin", "CK")

    def tvars(g):
        t = lib.one("lu_table_template", g.name) if lib.find("lu_table_template", g.name) else lib.one("power_lut_template", g.name)
        return [t.attrs[k][0] for k in ("variable_1", "variable_2") if k in t.attrs]

    def constraint(pin, timing_type, related):
        ts = [t for t in pin.find("timing") if t.attrs.get("timing_type", ("",))[0] == timing_type
              and t.attrs.get("related_pin", ("",))[0] == related]
        if len(ts) != 1:
            raise ValueError(f"{pin.path()}: {len(ts)} {timing_type} arcs to {related}")
        res = {}
        for kind in ("rise_constraint", "fall_constraint"):
            g = ts[0].one(kind)
            i1, i2, rows, line = table(g)
            mx = max(max(r) for r in rows)
            k1, k2 = next((a, b) for a, r in enumerate(rows) for b, x in enumerate(r) if x == mx)
            v = tvars(g)
            where = f"largest of the {len(i1)}x{len(i2) if i2 else 1} table, index_1[{k1}]={i1[k1]} ns {v[0]}"
            if i2:
                where += f", index_2[{k2}]={i2[k2]} ns {v[1]}"
            res[kind] = {"value": mx, "source": src(g, "values", line, f"{g.name} template; {where}")}
        res["max"] = {"value": max(res["rise_constraint"]["value"], res["fall_constraint"]["value"]),
                      "source": "the larger of rise_constraint and fall_constraint above"}
        return res

    out["DFF_X1"] = {
        "D": {k: val(d, k, float) for k in ["capacitance", "rise_capacitance", "fall_capacitance"]},
        "CK": {k: val(ck, k, float) for k in ["capacitance", "rise_capacitance", "fall_capacitance"]},
        "setup_rising_D_CK": constraint(d, "setup_rising", "CK"),
        "hold_rising_D_CK": constraint(d, "hold_rising", "CK"),
        "min_pulse_width_CK": constraint(ck, "min_pulse_width", "CK"),
    }
    out["DFF_X1"]["min_pulse_width_CK"]["note"] = "rise_constraint is the high pulse, fall_constraint the low pulse"

    # BUF_X4: Z max_capacitance; rise and fall transition (A -> Z) at the middle of both indices.
    buf = lib.one("cell", "BUF_X4")
    z = buf.one("pin", "Z")
    arc = [t for t in z.find("timing") if t.attrs.get("related_pin", ("",))[0] == "A"]
    if len(arc) != 1:
        raise ValueError(f"BUF_X4/Z: {len(arc)} arcs from A")
    bz = {"max_capacitance": val(z, "max_capacitance", float)}
    for kind in ("rise_transition", "fall_transition"):
        g = arc[0].one(kind)
        i1, i2, rows, line = table(g)
        m1, m2 = len(i1) // 2, len(i2) // 2
        bz[kind] = {"value": rows[m1][m2],
                    "source": src(g, "values", line, f"{g.name} template; middle entry of the {len(i1)}x{len(i2)} table, "
                                                     f"index_1[{m1}]={i1[m1]} ns {tvars(g)[0]}, "
                                                     f"index_2[{m2}]={i2[m2]} fF {tvars(g)[1]}")}
    out["BUF_X4"] = {"Z": bz}

    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(REPO)} from {rel}")


if __name__ == "__main__":
    main()
