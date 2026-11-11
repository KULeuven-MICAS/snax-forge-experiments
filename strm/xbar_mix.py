"""strm/xbar_mix.py - the TCDM sparse interconnect as the cluster drives it: read-only and write-only inputs (CSYN1 R3c).

STRM1's xbar points (strm/gen.py) synthesize SparseInterconnect alone, every input a full read-write port. In the
cluster most inputs are streamer channels that only read or only write (snax_cluster's DataRequestor ties a reader's
write and data to 0; a writer drives write 1 and never reads its response data; no streamer drives amo), and
sparse_interconnect_wrapper.sv.tpl ties every response ready to 1 and every bank response valid to 1. DC drops what
those constants make dead. This module writes the wrapper that puts the same constants on a point's
SparseInterconnect, so a point can be synthesized with R read-only inputs, W write-only inputs and the rest read-write:

    inputs 0 .. R-1        read-only:  bits_write = 0, bits_data = 0, bits_amo = 0 (not ports of the wrapper)
    inputs R .. R+W-1      write-only: bits_write = 1, bits_amo = 0; the response data not connected
    inputs R+W .. N-1      read-write: every field a port (the cores and the AXI port in the cluster)
    every input            tcdmRsps ready = 1 (the template's 1'b1)
    every bank             memRsps valid = 1, memRsps ready and memReqs priority not connected (the template's)

The order follows the cluster's: snax_cluster.sv connects {axi, cores, snax ports} to inputs N-1 .. 0, and a forge
accelerator's channels come in its streamer's order (the readers', then the writer's).

    wrapper(sv_text, ro, wo, top="xbar_mix") -> str   the wrapper module for the SparseInterconnect in sv_text
    ports(sv_text, module="SparseInterconnect")      [(direction, msb, name)] of the module, as emitted

Standard library only.
"""

from __future__ import annotations

import re

PORT = re.compile(r"^\s*(input|output)\s+(?:wire\s+|logic\s+|reg\s+)?(?:\[(\d+):0\]\s*)?(\w+)\s*,?\s*(?://.*)?$")
# firtool groups ports of one direction and width: `input  [16:0] a,` then a bare `b,` on the next line
MORE = re.compile(r"^\s*(\w+)\s*,?\s*(?://.*)?$")
REQ = re.compile(r"^io_tcdmReqs_(\d+)_(\w+)$")
RSP = re.compile(r"^io_tcdmRsps_(\d+)_(\w+)$")
MEMRSP = re.compile(r"^io_memRsps_(\d+)_(\w+)$")
MEMREQ = re.compile(r"^io_memReqs_(\d+)_(\w+)$")


def ports(sv_text: str, module: str = "SparseInterconnect") -> list[tuple[str, int, str]]:
    """The module's ports in order: (input|output, msb or -1 for one bit, name). Raises if the module is missing."""
    m = re.search(rf"^module\s+{module}\s*\((.*?)\);", sv_text, re.M | re.S)
    if not m:
        raise ValueError(f"no module {module}( ... ); in the text")
    out: list[tuple[str, int, str]] = []
    for ln in m.group(1).splitlines():
        if not ln.strip() or ln.strip().startswith("//"):
            continue
        if (p := PORT.match(ln)):
            out.append((p.group(1), int(p.group(2)) if p.group(2) is not None else -1, p.group(3)))
        elif (q := MORE.match(ln)) and out:
            out.append((out[-1][0], out[-1][1], q.group(1)))
        else:
            raise ValueError(f"port line not understood: {ln.strip()!r}")
    return out


def n_inputs(ps: list[tuple[str, int, str]]) -> int:
    return 1 + max(int(m.group(1)) for _d, _w, n in ps if (m := REQ.match(n)))


def tie(name: str, ro: int, wo: int) -> str | None:
    """What the port is tied to in the wrapper ('' for left open), or None when it stays a port."""
    if (m := REQ.match(name)):
        i, f = int(m.group(1)), m.group(2)
        if i < ro and f in ("bits_write", "bits_data", "bits_amo"):
            return "'0"
        if ro <= i < ro + wo and f == "bits_write":
            return "1'b1"
        if ro <= i < ro + wo and f == "bits_amo":
            return "'0"
        return None
    if (m := RSP.match(name)):
        i, f = int(m.group(1)), m.group(2)
        if f == "ready":
            return "1'b1"
        if ro <= i < ro + wo and f == "bits_data":
            return ""
        return None
    if (m := MEMRSP.match(name)):
        return {"valid": "1'b1", "ready": ""}.get(m.group(2))
    if (m := MEMREQ.match(name)):
        return "" if m.group(2) == "bits_priority" else None
    return None


def wrapper(sv_text: str, ro: int, wo: int, top: str = "xbar_mix", module: str = "SparseInterconnect") -> str:
    """The wrapper module `top` around `module` with ro read-only and wo write-only inputs (the module doc)."""
    ps = ports(sv_text, module)
    n = n_inputs(ps)
    if ro < 0 or wo < 0 or ro + wo > n:
        raise ValueError(f"ro {ro} + wo {wo} inputs of {n}")
    kept, conns = [], []
    for d, msb, name in ps:
        t = tie(name, ro, wo)
        if t is None:
            kept.append(f"  {d:6s} {'' if msb < 0 else f'[{msb}:0] '}{name}")
            conns.append(f"    .{name}({name})")
        else:
            conns.append(f"    .{name}({t})")
    head = (f"// {top}: {module} with inputs 0..{ro - 1} read-only, {ro}..{ro + wo - 1} write-only, "
            f"{ro + wo}..{n - 1} read-write, and snax_cluster's sparse_interconnect_wrapper ties\n"
            f"// (strm/xbar_mix.py, CSYN1 R3c). Generated; never edited by hand.\n")
    if ro == 0:
        head = head.replace("inputs 0..-1 read-only, ", "no read-only input, ")
    if wo == 0:
        head = head.replace(f"{ro}..{ro - 1} write-only, ", "no write-only input, ")
    return (head + f"module {top} (\n" + ",\n".join(kept) + "\n);\n"
            f"  {module} i_xbar (\n" + ",\n".join(conns) + "\n  );\nendmodule\n")
