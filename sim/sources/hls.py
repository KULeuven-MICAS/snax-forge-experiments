"""sim/sources/hls.py - an hls-exercises point -> tb.json (docs/DECISIONS.md X14).

hls-exercises is not changed for this: the adapter reads what it already writes.
  - rtl/<tier>/<kernel>/<point>/filelist.f   the top module ('# top:'), its Verilog files, '# ram:'
  - the top's Verilog port list               port names and widths (Vitis renames dot's out to out_r)
  - bench/tier_<tier>/<kernel>/params.json    the stream args in order, the config pins and their
                                              expressions, the scalar args, dtype, sizes, valid rule

tb.json describes the DUT's ports for the generated TB top (sim/pwr.py):
  tb_version, point, kernel, top, case, W
  clock   {port}
  reset   {port, active, sync}
  control {kind: "ap_ctrl_hs", start, done, ready, idle}
  streams [{arg, dir, kind: "axis", lanes, dtype, data, valid, ready}]   in params.json's axis order
  pins    [{port, bits, vld, from: "config" | "data:<arg>"}]
  sizes   {tag: {pin: value}}  cosim's sizes valid at this W, and 'b64' (64 beats) when every config
                               pin equals loop_count at cosim's sizes (rowsum's len does not, so it
                               has no b64 and runs at a cosim size)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

TB_VERSION = 1
HLS = Path(os.environ.get("SIM_HLS", Path(__file__).resolve().parents[3] / "hls-exercises")).resolve()
RTL = HLS / "rtl"
BENCH = HLS / "bench"
BEATS = 64
# control kinds: only ap_ctrl_hs is built; the forge kinds are reserved for sim/sources/forge.py (SYN1)
CONTROL_KINDS = {"ap_ctrl_hs"}
RESERVED_KINDS = {"forge_csr", "forge_datapath"}


def filelist(point: str) -> dict:
    text = (RTL / point / "filelist.f").read_text()
    top = re.search(r"^#\s*top:\s*(\S+)", text, re.M)
    if not top:
        raise ValueError(f"{point}: filelist.f has no '# top:' line")
    files = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    rams = re.findall(r"^#\s*ram:\s*(\S+)", text, re.M)
    return {"top": top.group(1), "files": files, "rams": rams}


def params_of(point: str) -> dict:
    tier, kernel, _ = point.split("/")
    return json.loads((BENCH / f"tier_{tier}" / kernel / "params.json").read_text())


def case_w(point: str) -> tuple[str, int]:
    m = re.fullmatch(r"(\w+?)_w(\d+)", point.split("/")[2])
    if not m:
        raise ValueError(f"{point}: point name is not <case>_w<W>")
    return m.group(1), int(m.group(2))


def ports_of(vfile: Path, top: str) -> dict:
    """{port: (dir, bits)} of module `top`, from its input/output declarations."""
    text = re.sub(r"//.*", "", vfile.read_text())
    m = re.search(rf"^\s*module\s+{re.escape(top)}\b(.*?)^\s*endmodule", text, re.M | re.S)
    if not m:
        raise ValueError(f"{vfile}: no module {top}")
    ports = {}
    for d, msb, lsb, names in re.findall(
            r"^\s*(input|output)\s+(?:wire\s+|reg\s+)?(?:\[(\d+):(\d+)\]\s*)?([^;]+);", m.group(1), re.M):
        bits = int(msb) - int(lsb) + 1 if msb else 1
        for n in names.split(","):
            ports[n.strip()] = ("in" if d == "input" else "out", bits)
    return ports


def _eval(expr: str, size: dict, w: int):
    return eval(expr, {"__builtins__": {}}, {**size, "W": w})  # params.json's own expressions


def size_tag(size: dict) -> str:
    return "_".join(f"{k}{v}" for k, v in size.items())


def build(point: str) -> dict:
    fl = filelist(point)
    top = fl["top"]
    prm = params_of(point)
    case, w = case_w(point)
    ports = ports_of(RTL / point / f"{top}.v", top)
    if prm.get("iface") != "axis":
        raise ValueError(f"{point}: iface {prm.get('iface')}, only axis is built")

    for p in ("ap_clk", "ap_rst_n", "ap_start", "ap_done", "ap_ready", "ap_idle"):
        if p not in ports:
            raise ValueError(f"{point}: no {p}: not ap_ctrl_hs")
    control = {"kind": "ap_ctrl_hs", "start": "ap_start", "done": "ap_done", "ready": "ap_ready", "idle": "ap_idle"}

    streams = []
    for arg in prm["axis"]:
        # Vitis renames an argument that is a Verilog keyword or clashes (dot's out -> out_r)
        base = next((b for b in (arg, f"{arg}_r") if f"{b}_TDATA" in ports), None)
        if base is None:
            raise ValueError(f"{point}: no AXI-stream port for argument {arg}")
        d, bits = ports[f"{base}_TDATA"]
        if bits % 64:
            raise ValueError(f"{point}: {base}_TDATA is {bits} bits, not a multiple of 64")
        streams.append({"arg": arg, "dir": d, "kind": "axis", "lanes": bits // 64, "dtype": prm["dtype"],
                        "data": f"{base}_TDATA", "valid": f"{base}_TVALID", "ready": f"{base}_TREADY"})

    pins = []
    for name in list(prm.get("config", {})) + list(prm.get("scalars", [])):
        if name not in ports or f"{name}_ap_vld" not in ports:
            raise ValueError(f"{point}: no pin {name} with {name}_ap_vld")
        pins.append({"port": name, "bits": ports[name][1], "vld": f"{name}_ap_vld",
                     "from": "config" if name in prm.get("config", {}) else f"data:{name}"})

    known = {"ap_clk", "ap_rst_n", *control.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    known |= {p[k] for p in pins for k in ("port", "vld")}
    extra = sorted(set(ports) - known)
    if extra:
        raise ValueError(f"{point}: ports tb.json does not cover: {extra}")

    sizes = {}
    for size in prm["sizes"]:
        if "valid" in prm and not _eval(prm["valid"], size, w):
            continue
        sizes[size_tag(size)] = {k: int(_eval(e, size, w)) for k, e in prm["config"].items()}
    if all(all(v == cfg["loop_count"] for v in cfg.values()) for cfg in sizes.values()):
        sizes["b64"] = {k: BEATS for k in prm["config"]}

    return {"tb_version": TB_VERSION, "point": point, "kernel": prm["kernel"], "top": top, "case": case, "W": w,
            "clock": {"port": "ap_clk"},
            "reset": {"port": "ap_rst_n", "active": "low", "sync": True},
            "control": control, "streams": streams, "pins": pins, "sizes": sizes}


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    kind = tb["control"]["kind"]
    if kind in RESERVED_KINDS:
        raise ValueError(f"control.kind {kind} is reserved for snax-forge (sim/sources/forge.py, SYN1)")
    if kind not in CONTROL_KINDS:
        raise ValueError(f"control.kind {kind}: only ap_ctrl_hs is built")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    for s in tb["streams"]:
        if s["kind"] != "axis" or s["dtype"] != "int64":
            raise ValueError(f"stream {s['arg']}: {s['kind']} {s['dtype']}, only axis int64 is built")


def default_size(tb: dict) -> str:
    """b64, else the last (largest) cosim size: rowsum runs m8_n64 as is."""
    return "b64" if "b64" in tb["sizes"] else list(tb["sizes"])[-1]


def data_h(point: str, size: str) -> Path:
    tier, kernel, _ = point.split("/")
    return BENCH / f"tier_{tier}" / kernel / "vectors" / size / "data.h"


def read_data_h(path: Path) -> dict:
    """{name: [int, ...]} of every 'static const data_t NAME[..]... = {...};', flattened."""
    out = {}
    for m in re.finditer(r"static const data_t (\w+)((?:\[\d+\])+)\s*=\s*\{(.*?)\};", path.read_text(), re.S):
        dims = [int(x) for x in re.findall(r"\d+", m.group(2))]
        vals = [int(v) for v in re.findall(r"-?\d+", m.group(3))]
        n = 1
        for d in dims:
            n *= d
        if len(vals) != n:
            raise ValueError(f"{path}: {m.group(1)} has {len(vals)} values, not {n}")
        out[m.group(1)] = vals
    return out
