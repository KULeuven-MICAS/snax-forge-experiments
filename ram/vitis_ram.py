"""ram/vitis_ram.py - a Vitis RAM swapped for an SRAM macro (X62), shared by syn/syn.py and sim/pwr.py.

Vitis writes each memory it builds as its own module, <top>_<array>_RAM_AUTO_1R1W (hls-exercises names the file
on a '# ram:' line of the point's filelist.f): one port, address0, ce0, we0, d0, q0, plus reset and clk, read
first, sized by the parameters DataWidth, AddressRange and AddressWidth that its parent passes when it
instantiates it (the module's own defaults are not the instance's). Here:

  instances(files, ram_files)   every instance of every RAM module: its parameters from the parent's
                                instantiation, the parent's file and the instance name
  macro(depth, width)           ram.py's make_macro (pixi run ram lib <depth> <width>, no byte mask): the
                                macro's zip in ram/runs/lib/, or its CACTI status when CACTI has no such array
  wrapper(module, inst, cell)   a module with Vitis's name and ports around the macro cell, plain wiring:
                                ce0 -> req_i, we0 -> we_i, address0 -> addr_i, d0 -> wdata_i, q0 <- rdata_o;
                                reset is not used (the macro has none)
  plan(rtl_dir, files, rams)    the swap of one point: the macros (made when missing), the wrappers' text, the
                                point's files with each RAM file replaced by its wrapper; or why it cannot be
                                swapped (a RAM module instantiated with different sizes, a size CACTI refuses)

Behaviour the swap changes, and why it is safe for DaCe's buffers (CSYN1 R3, X62): Vitis's RAM reads first (on
a write, q0 takes the old word at the written address); the macro, as tc_sram, keeps the last read word on a
write. The two differ only in q0 after a write cycle; the swap is used only where the point's RTL never reads q0
after a write (dot's and axpy's __tmp0: one loop only writes it, the next only reads it).
"""
from __future__ import annotations

import importlib.util
import json
import re
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAM_FILE = re.compile(r"_RAM_\w*\.v$")
ONE_PORT = ("address0", "ce0", "d0", "we0", "q0", "reset", "clk")
_ram = None
_LOCK = threading.Lock()


def _ram_py():
    """ram/ram.py, loaded once (it imports arc itself); published only once loaded, under a lock (syn.py's DC
    threads call this at the same time)."""
    global _ram
    with _LOCK:
        if _ram is None:
            spec = importlib.util.spec_from_file_location("ram_py", ROOT / "ram" / "ram.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _ram = mod
    return _ram


def _strip(text: str) -> str:
    return re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text, flags=re.S))


def instances(rtl_dir: Path, files: list[str], ram_files: list[str]) -> list[dict]:
    """[{module, file, inst, parent, DataWidth, AddressRange, AddressWidth}] for every instance of every RAM module."""
    mods = {Path(f).stem: f for f in ram_files}
    for mod, f in mods.items():      # one port only: a second port (rowsum's address1, q1) has no 1RW macro
        m = re.search(rf"\bmodule\s+{re.escape(mod)}\s*\((.*?)\)\s*;", _strip((rtl_dir / f).read_text()), re.S)
        ports = sorted(x.strip() for x in m.group(1).split(",") if x.strip()) if m else []
        if ports != sorted(ONE_PORT):
            raise ValueError(f"{mod} has the ports {ports}, not one port {sorted(ONE_PORT)}")
    out = []
    for f in files:
        if f in ram_files or not f.endswith((".v", ".sv")):
            continue
        text = _strip((rtl_dir / f).read_text(errors="replace"))
        for mod in mods:
            for m in re.finditer(rf"\b{re.escape(mod)}\s*#\s*\((.*?)\)\s*(\w+)\s*\(", text, re.S):
                params = dict(re.findall(r"\.(\w+)\s*\(\s*(\d+)\s*\)", m.group(1)))
                need = ("DataWidth", "AddressRange", "AddressWidth")
                if any(k not in params for k in need):
                    raise ValueError(f"{f}: {mod} {m.group(2)} is instantiated without {need}: {params}")
                out.append({"module": mod, "file": mods[mod], "inst": m.group(2), "parent": f,
                            **{k: int(params[k]) for k in need}})
    missing = sorted(set(mods) - {i["module"] for i in out})
    if missing:
        raise ValueError(f"RAM modules never instantiated with parameters: {missing}")
    return out


def macro(depth: int, width: int, make: bool = True) -> dict:
    """The macro sram_d<depth>_w<width> (no mask), made if missing (only looked up with make False, a dry run):
    {name, status, zip, area_um2, e_rd_pj, ...}."""
    ram = _ram_py()
    if not make:
        name = ram.macro_name(depth, width)
        z = ram.macro_zip(name)
        if not z.is_file():
            return {"name": name, "status": "not made yet (dry run)", "zip": str(z)}
        return {**json.loads(arc_read(z, "result.json")), "zip": str(z)}
    res = ram.make_macro(depth, width)
    res["zip"] = str(ram.macro_zip(res["name"]))
    return res


def wrapper(inst: dict, cell: str) -> str:
    aw, dw = inst["AddressWidth"], inst["DataWidth"]
    return f"""// Generated by ram/vitis_ram.py (X62): Vitis's {inst['module']} as the SRAM macro {cell}, plain wiring.
// Vitis's RAM reads first; the macro keeps the last read word on a write (tc_sram). DataWidth {dw},
// AddressRange {inst['AddressRange']}, AddressWidth {aw}, as {inst['parent']} instantiates {inst['inst']}.
module {inst['module']} (address0, ce0, d0, we0, q0, reset, clk);
parameter DataWidth = {dw};
parameter AddressWidth = {aw};
parameter AddressRange = {inst['AddressRange']};
input  [AddressWidth-1:0] address0;
input                     ce0;
input  [DataWidth-1:0]    d0;
input                     we0;
output [DataWidth-1:0]    q0;
input                     reset;
input                     clk;
{cell} mem (.clk_i(clk), .req_i(ce0), .we_i(we0), .addr_i(address0), .wdata_i(d0), .rdata_o(q0));
endmodule
"""


def arc_read(z: Path, member: str) -> bytes:
    return _ram_py().arc.read(z, member)


def plan(rtl_dir: Path, files: list[str], ram_files: list[str], make: bool = True) -> dict:
    """{ok, why, macros: [{cell, zip, depth, width, area_um2, e_rd_pj, e_wr_pj, instances}], wrappers: {file: text},
    files: the point's files with each RAM file replaced by its wrapper's name}."""
    try:
        insts = instances(rtl_dir, files, ram_files)
    except ValueError as e:
        return {"ok": False, "why": str(e)}
    by_mod: dict[str, list[dict]] = {}
    for i in insts:
        by_mod.setdefault(i["module"], []).append(i)
    macros, wrappers, swapped = {}, {}, {}
    for mod, its in by_mod.items():
        sizes = {(i["AddressRange"], i["DataWidth"], i["AddressWidth"]) for i in its}
        if len(sizes) > 1:
            return {"ok": False, "why": f"{mod} is instantiated with different sizes {sorted(sizes)}"}
        (depth, width, aw), = sizes
        if (1 << aw) < depth:
            return {"ok": False, "why": f"{mod}: AddressWidth {aw} cannot address {depth} words"}
        m = macro(depth, width, make)
        if m["status"] != "ok":
            return {"ok": False, "why": f"{mod}: no macro {depth} x {width}: {m['status']}"}
        if m["name"] not in macros:
            macros[m["name"]] = {"cell": m["name"], "zip": m["zip"], "depth": depth, "width": width,
                                 "area_um2": m.get("area_um2"), "e_rd_pj": m.get("e_rd_pj"),
                                 "e_wr_pj": m.get("e_wr_pj"), "instances": []}
        macros[m["name"]]["instances"] += [f"{i['parent']}:{i['inst']}" for i in its]
        name = f"{mod}.v"
        wrappers[name] = wrapper(its[0], m["name"])
        swapped[its[0]["file"]] = name
    return {"ok": True, "why": "", "macros": list(macros.values()), "wrappers": wrappers,
            "files": [swapped.get(f, f) for f in files]}
