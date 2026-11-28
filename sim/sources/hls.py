"""sim/sources/hls.py - an hls-exercises point -> tb.json.

hls-exercises is not changed for this: the adapter reads what it already writes: the point's filelist.f (the top
module, its Verilog files, '# ram:'), the top's Verilog port list and bench/tier_<tier>/<kernel>/params.json (the
stream args in order, the config pins and their expressions, the scalar args, dtype, sizes, valid rule). build()
writes tb.json (its fields in build()'s docstring); docs/power.md, "Stages", has the testbench and the window.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import ports as _ports

TB_VERSION = 1
CLK, RST = _ports("hls")     # ap_clk, ap_rst_n: syn/syn.py's SOURCES
HLS = Path(os.environ.get("SIM_HLS", Path(__file__).resolve().parents[3] / "hls-exercises")).resolve()
RTL = HLS / "rtl"
BENCH = HLS / "bench"
BEATS = 64
# A stream's element widths (X119): an input carries params.json's dtype, an output its acc_dtype (else dtype);
# lanes = TDATA bits / the element's bits. int64 streams are built as before (64-bit lanes).
BITS = {"int8": 8, "int16": 16, "int32": 32, "int64": 64}
# control kinds: only ap_ctrl_hs is built; the forge kinds are reserved for sim/sources/forge.py
CONTROL_KINDS = {"ap_ctrl_hs"}
RESERVED_KINDS = {"forge_csr", "forge_datapath"}
# The reference task n2048 beyond cosim's sizes: 2048 elements, the size every forge row runs
# (sim/sources/forge.py takes the same shapes from its points' sets), by tier and kernel ("*": every kernel of
# the tier); its pins from params.json's config expressions at these values and its expected cycles from
# cosim's line (sim/pwr.py expected_cycles; the bambu and xls lines alike). Tagged n2048 whatever the
# shape, so every source's reference task has one name.
REF_TAG = "n2048"
EXTRA_SIZES = {
    "done": {"*": {"n": 2048}},
    "untiered": {"relu": {"n": 2048}, "axpy": {"n": 2048}, "matadd": {"m": 32, "n": 64}, "rowsum": {"m": 16, "n": 128}},
}


def narrow(prm: dict) -> bool:
    """A point whose inputs are narrower than int64 (X118's int8 in, int32 out): its params.json size and b64
    only, no n2048 reference task, and the reference is snax-forge's kernel at the point's types (X119)."""
    return prm.get("dtype", "int64") != "int64"


def stream_dtype(prm: dict, direction: str, arg: str | None = None, types: dict | None = None) -> str:
    """An int64 point's stream element: params.json's dtype for an input, acc_dtype (else dtype) for an output. A
    narrow point's (X120): the dtype snax-forge gives the array the port carries (its params.json streams entry's
    array, else the port's name) at the point's type preset (`types`, narrow_types): axpy's y and mvt's x1_in are
    int32 inputs at i8."""
    if types is not None:
        array = array_of(prm.get("streams", {}).get(arg, {}).get("array", arg), types["dtypes"])
        if array not in types["dtypes"]:
            raise ValueError(f"{prm.get('kernel')}: port {arg} carries {array}, no container of snax-forge's "
                             f"{types['kernel']} at {types['types']}")
        return types["dtypes"][array]
    dtype = prm.get("dtype", "int64")
    return dtype if direction == "in" else prm.get("acc_dtype", dtype)


def array_of(arg: str, dtypes: dict) -> str:
    """The forge container a port without a streams entry carries: its own name, or for <a>_out, when that is no
    container and <a> is, <a> (axpy's y_out is y, updated in place, as forge names the pair)."""
    if arg not in dtypes and arg.endswith("_out") and arg[: -len("_out")] in dtypes:
        return arg[: -len("_out")]
    return arg


def stream_array(s: dict, dtypes: dict) -> str:
    """The forge container a tb.json stream carries: its streams entry's array, else array_of its name."""
    return s["follows"]["array"] if "follows" in s else array_of(s["arg"], dtypes)


_TYPES: dict = {}


def narrow_types(prm: dict) -> dict:
    """{kernel, types, dtypes}: snax-forge's kernel (params.json's forge_kernel, its name: vecadd) at its type preset
    (forge_types), the dtypes snax-forge gives the containers and type parameters (forge/query.py types)."""
    from . import forge as _forge          # sim/sources/forge.py imports this module
    for k in ("forge_kernel", "forge_types"):
        if k not in prm:
            raise ValueError(f"{prm.get('kernel')}: params.json has no {k}; a narrow point's reference needs it")
    kernel = prm["forge_kernel"].rsplit("/", 1)[-1]       # polybench/vecadd: snax-forge's loader takes vecadd
    key = (kernel, prm["forge_types"])
    if key not in _TYPES:
        _TYPES[key] = _forge.query("types", kernel, prm["forge_types"])["dtypes"]
    return {"kernel": kernel, "types": prm["forge_types"], "dtypes": _TYPES[key]}


def follows(point: str, prm: dict, arg: str, lanes: int, w: int) -> dict | None:
    """A port's params.json streams entry (X120): the forge array it carries and the expressions of its beats a run
    and of the flat row-major index of lane l of beat b (over the size's keys, W, b and l); its lanes must be the
    port's (TDATA bits / the element's). None without an entry: the port carries its own array in turn."""
    e = prm.get("streams", {}).get(arg)
    if e is None:
        return None
    if int(_eval(str(e["lanes"]), {}, w)) != lanes:
        raise ValueError(f"{point}: port {arg} has {lanes} lanes, params.json's streams says {e['lanes']}")
    return {"array": e["array"], "beats": str(e["beats"]), "index": str(e["index"])}


def follow(s: dict, dims: dict, w: int):
    """(beats, index) of a stream with a streams entry at a size (dims: its keys and values): index[b, l] the flat
    element of its array lane l of beat b carries."""
    import numpy as np

    f = s["follows"]
    beats = int(_eval(f["beats"], dims, w))
    b, lane = np.arange(beats)[:, None], np.arange(s["lanes"])[None, :]
    idx = eval(f["index"], {"__builtins__": {}}, {**dims, "W": w, "b": b, "l": lane})  # params.json's own
    return beats, np.broadcast_to(np.asarray(idx, dtype=np.int64), (beats, s["lanes"]))


def lanes_of(point: str, port: str, bits: int, dtype: str) -> int:
    """TDATA bits / the element's bits, refused when they do not divide."""
    if dtype not in BITS:
        raise ValueError(f"{point}: {port} carries {dtype}; the streams take {sorted(BITS)}")
    if bits % BITS[dtype]:
        raise ValueError(f"{point}: {port} is {bits} bits, not a multiple of {BITS[dtype]} ({dtype})")
    return bits // BITS[dtype]


def narrow_ref(prm: dict, streams: list[dict]) -> dict:
    """tb.json's ref of a narrow point: snax-forge's kernel at its type preset and the dtypes it gives the
    containers (narrow_types); every stream's dtype must be that of the array it carries there (its streams
    entry's array, else its own name: mvt's x1_in carries x1), so HLS and forge points check against the same
    spec."""
    t = narrow_types(prm)
    for s in streams:
        array = stream_array(s, t["dtypes"])
        if t["dtypes"].get(array) != s["dtype"]:
            raise ValueError(f"{prm['kernel']}: stream {s['arg']} ({array}) is {s['dtype']}, snax-forge's "
                             f"{t['kernel']} at {t['types']} has {t['dtypes'].get(array)}")
    return t


def dims_of(point: str, prm: dict, w: int) -> dict:
    """{tag: size} of params.json's sizes valid at this W: the keys the streams entries' expressions take."""
    return {size_tag(z): z for z in prm["sizes"] if not prm.get("valid") or _eval(prm["valid"], z, w)}


def extra_sizes(point: str) -> list[tuple[str, dict]]:
    """[(tag, size)] of the point's reference task: EXTRA_SIZES by tier and kernel."""
    tier, kernel = point.split("/")[:2]
    by_kernel = EXTRA_SIZES.get(tier, {})
    size = by_kernel.get(kernel, by_kernel.get("*"))
    return [(REF_TAG, size)] if size else []


def filelist(point: str) -> dict:
    text = (RTL / point / "filelist.f").read_text()
    top = re.search(r"^#\s*top:\s*(\S+)", text, re.M)
    if not top:
        raise ValueError(f"{point}: filelist.f has no '# top:' line")
    files = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    rams = re.findall(r"^#\s*ram:\s*(\S+)", text, re.M)
    return {"top": top.group(1), "files": files, "rams": rams}


def sizes_txt(point: str) -> list[str]:
    """The sizes whose Vitis run gave this point's Verilog (rtl/<point>/sizes.txt, bench.py), in file order."""
    lines = (RTL / point / "sizes.txt").read_text().splitlines()
    return [ln.split()[0] for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


def params_of(point: str) -> dict:
    tier, kernel, _ = point.split("/")
    return json.loads((BENCH / f"tier_{tier}" / kernel / "params.json").read_text())


def case_w(point: str) -> tuple[str, int]:
    m = re.fullmatch(r"(\w+?)_w(\d+)", point.split("/")[2])
    if not m:
        raise ValueError(f"{point}: point name is not <case>_w<W>")
    return m.group(1), int(m.group(2))


def ports_of(vfile: Path, top: str) -> dict:
    """{port: (dir, bits)} of module `top`, from its input/output declarations: in the body (a DC netlist, Vitis's
    and Bambu's Verilog), or in an ANSI header (XLS's Verilog, snax-forge's SV), where a name alone takes the
    direction and width of the one before it."""
    text = re.sub(r"//.*", "", vfile.read_text())
    m = re.search(rf"^\s*module\s+{re.escape(top)}\b(.*?)^\s*endmodule", text, re.M | re.S)
    if not m:
        raise ValueError(f"{vfile}: no module {top}")
    ports = {}
    head = re.match(r"\s*\((.*?)\)\s*;", m.group(1), re.S)
    if head and re.search(r"\b(input|output)\b", head.group(1)):
        cur = None
        for item in head.group(1).split(","):
            item = " ".join(item.split())
            d = re.fullmatch(r"(input|output)\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[(\d+):(\d+)\]\s*)?(\w+)", item)
            if d:
                cur = ("in" if d.group(1) == "input" else "out",
                       int(d.group(2)) - int(d.group(3)) + 1 if d.group(2) else 1)
                ports[d.group(4)] = cur
            elif re.fullmatch(r"\w+", item) and cur:
                ports[item] = cur
            else:
                raise ValueError(f"{vfile}: module {top}'s header item {item!r} is not a port declaration")
        return ports
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


def sizes_for(point: str, sizes: list[dict], config: dict, w: int, valid: str | None = None, b64: bool = True,
              extra: bool = True) -> dict:
    """{tag: {pin: value}}: the tool's sizes valid at this W, then 'b64' (64 beats) when every config pin equals
    loop_count at those sizes (rowsum's len does not), then EXTRA_SIZES for the tier (not with extra=False: a
    narrow point, X119); values from the config expressions. Shared by the HLS tools' adapters (hls, bambu,
    xls)."""
    out = {}
    for size in sizes:
        if valid and not _eval(valid, size, w):
            continue
        out[size_tag(size)] = {k: int(_eval(e, size, w)) for k, e in config.items()}
    if b64 and all(all(v == cfg["loop_count"] for v in cfg.values()) for cfg in out.values()):
        out["b64"] = {k: BEATS for k in config}
    for tag, size in extra_sizes(point) if extra else []:
        if valid and not _eval(valid, size, w):
            continue
        elems = 1
        for v in size.values():
            elems *= v
        if elems % w:
            raise ValueError(f"{point}: size {size_tag(size)} ({elems} elements) is not a multiple of W {w}")
        out[tag] = {k: int(_eval(e, size, w)) for k, e in config.items()}
    return out


def build(point: str) -> dict:
    """tb.json describes the DUT's ports for the generated TB top (sim/pwr.py):
      tb_version, point, kernel, top, case, W
      clock   {port}
      reset   {port, active, sync}
      control {kind: "ap_ctrl_hs", start, done, ready, idle}
      streams [{arg, dir, kind: "axis", lanes, dtype, data, valid, ready}]   in params.json's axis order; dtype
               the element (an input: params.json's dtype, an output: acc_dtype, else dtype), lanes = TDATA
               bits / its bits
      pins    [{port, bits, vld, from: "config" | "data:<arg>"}]
      sizes   {tag: {pin: value}}  cosim's sizes valid at this W, and 'b64' (64 beats) when every config
                                   pin equals loop_count at cosim's sizes (rowsum's len does not, so it
                                   has no b64 and runs at a cosim size), then the reference task n2048
                                   (EXTRA_SIZES: tier done N = 2048; untiered relu and axpy
                                   n = 2048, matadd m32_n64, rowsum m16_n128), from params.json's config
                                   expressions at those values; a narrow point (dtype not int64, X119)
                                   has its params.json sizes and b64 only
      ref     {kernel, types, dtypes}  a narrow point only: snax-forge's kernel (params.json's forge_kernel, its
                                   name: vecadd) and type preset (forge_types) and the dtypes snax-forge gives the containers
    """
    fl = filelist(point)
    top = fl["top"]
    prm = params_of(point)
    case, w = case_w(point)
    ports = ports_of(RTL / point / f"{top}.v", top)
    if prm.get("iface") != "axis":
        raise ValueError(f"{point}: iface {prm.get('iface')}, only axis is built")

    for p in (CLK, RST, "ap_start", "ap_done", "ap_ready", "ap_idle"):
        if p not in ports:
            raise ValueError(f"{point}: no {p}: not ap_ctrl_hs")
    control = {"kind": "ap_ctrl_hs", "start": "ap_start", "done": "ap_done", "ready": "ap_ready", "idle": "ap_idle"}

    types = narrow_types(prm) if narrow(prm) else None
    streams = []
    for arg in prm["axis"]:
        # Vitis renames an argument that is a Verilog keyword or clashes (dot's out -> out_r)
        base = next((b for b in (arg, f"{arg}_r") if f"{b}_TDATA" in ports), None)
        if base is None:
            raise ValueError(f"{point}: no AXI-stream port for argument {arg}")
        d, bits = ports[f"{base}_TDATA"]
        dt = stream_dtype(prm, d, arg, types)
        streams.append(axis_stream(point, prm, arg, d, dt, lanes_of(point, f"{base}_TDATA", bits, dt), w,
                                   f"{base}_TDATA", f"{base}_TVALID", f"{base}_TREADY"))

    pins = []
    for name in list(prm.get("config", {})) + list(prm.get("scalars", [])):
        if name not in ports or f"{name}_ap_vld" not in ports:
            raise ValueError(f"{point}: no pin {name} with {name}_ap_vld")
        pins.append({"port": name, "bits": ports[name][1], "vld": f"{name}_ap_vld",
                     "from": "config" if name in prm.get("config", {}) else f"data:{name}",
                     **data_dtype(name, prm, types)})

    known = {CLK, RST, *control.values()}
    known |= {s[k] for s in streams for k in ("data", "valid", "ready")}
    known |= {p[k] for p in pins for k in ("port", "vld")}
    extra = sorted(set(ports) - known)
    if extra:
        raise ValueError(f"{point}: ports tb.json does not cover: {extra}")

    # a case with its own sizes (the dace case of dot, axpy and rowsum: the n2048 task only) runs those, no b64
    own = prm["cases"].get(case, {}).get("sizes")
    sizes = sizes_for(point, own or prm["sizes"], prm["config"], w, prm.get("valid"),
                      b64=not own and "streams" not in prm, extra=not narrow(prm))

    tb = {"tb_version": TB_VERSION, "point": point, "kernel": prm["kernel"], "top": top, "case": case, "W": w,
          "clock": {"port": CLK},
          "reset": {"port": RST, "active": "low", "sync": True},
          "control": control, "streams": streams, "pins": pins, "sizes": sizes}
    return with_ref(tb, point, prm, w)


def axis_stream(point: str, prm: dict, arg: str, d: str, dtype: str, lanes: int, w: int, data: str, valid: str,
                ready: str, **extra) -> dict:
    """One axis stream of tb.json (hls, bambu, xls), with its params.json streams entry where it has one."""
    s = {"arg": arg, **extra, "dir": d, "kind": "axis", "lanes": lanes, "dtype": dtype, "data": data,
         "valid": valid, "ready": ready}
    f = follows(point, prm, arg, lanes, w)
    if f:
        s["follows"] = f
    return s


def data_dtype(name: str, prm: dict, types: dict | None) -> dict:
    """A scalar pin's (or XLS cfg field's) {"dtype"} at a narrow point: snax-forge's dtype of the scalar (axpy's
    and gesummv's alpha int32 at i8), drawn at it (sim/pwr.py); nothing for a config pin or an int64 point."""
    if types is None or name in prm.get("config", {}):
        return {}
    if name not in types["dtypes"]:
        raise ValueError(f"{prm.get('kernel')}: scalar {name} is no container of snax-forge's {types['kernel']}")
    return {"dtype": types["dtypes"][name]}


def with_ref(tb: dict, point: str, prm: dict, w: int) -> dict:
    """A narrow point's ref (narrow_ref) and, where a stream follows a params.json streams entry, the sizes'
    dimensions its expressions take (dims)."""
    if narrow(prm):
        tb["ref"] = narrow_ref(prm, tb["streams"])
    if any("follows" in s for s in tb["streams"]):
        dims = dims_of(point, prm, w)
        tb["dims"] = {t: dims[t] for t in tb["sizes"]}
    return tb


def check_streams(tb: dict) -> None:
    """Axis streams of int8 to int64 elements (X119); a narrow one needs tb.json's ref."""
    for s in tb["streams"]:
        if s["kind"] != "axis" or s["dtype"] not in BITS:
            raise ValueError(f"stream {s['arg']}: {s['kind']} {s['dtype']}, only axis {sorted(BITS)} is built")
    if any(s["dtype"] != "int64" for s in tb["streams"]) and "ref" not in tb:
        raise ValueError("a narrow stream and no ref (snax-forge's kernel and types) in tb.json")


def check(tb: dict) -> None:
    """What sim/pwr.py relies on; rejects what it cannot drive."""
    kind = tb["control"]["kind"]
    if kind in RESERVED_KINDS:
        raise ValueError(f"control.kind {kind} is reserved for snax-forge (sim/sources/forge.py)")
    if kind not in CONTROL_KINDS:
        raise ValueError(f"control.kind {kind}: only ap_ctrl_hs is built")
    if tb["tb_version"] != TB_VERSION:
        raise ValueError(f"tb_version {tb['tb_version']}, expected {TB_VERSION}")
    check_streams(tb)


def default_size(tb: dict) -> str:
    """b64, else the last (largest) cosim size: rowsum runs m8_n64 as is. Never the reference task n2048 (EXTRA_SIZES),
    which comes after the cosim sizes but is not a cosim size (rowsum has no b64)."""
    if "b64" in tb["sizes"]:
        return "b64"
    rest = [z for z in tb["sizes"] if z != REF_TAG]
    return rest[-1] if rest else REF_TAG     # a dace point rebuilt for n2048 only


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
