"""sim/ref.py - numpy references per kernel, int64 with wrap-around (as the C++ int64 kernels).

ref(kernel, ins, pins) -> {output arg: int64 array}
  ins   {input stream arg: int64 array, flat, lane 0 first}
  pins  {pin: int}: the config pins (loop_count, len) and the data pins (axpy's alpha); forge's runs give the
        shape instead (rowsum's m, sim/sources/forge.py)
"""
from __future__ import annotations

import numpy as np


def _rows(a, pins):
    m = pins["m"] if "m" in pins else pins["loop_count"] // pins["len"]     # rows: forge's shape, or HLS's pins
    return a.reshape(m, a.size // m)


REF = {
    "vecadd": lambda i, p: {"C": i["A"] + i["B"]},
    "matadd": lambda i, p: {"C": i["A"] + i["B"]},
    "vecmul": lambda i, p: {"C": i["A"] * i["B"]},
    "vsum":   lambda i, p: {"out": np.array([i["A"].sum(dtype=np.int64)], dtype=np.int64)},
    "dot":    lambda i, p: {"out": np.array([(i["A"] * i["B"]).sum(dtype=np.int64)], dtype=np.int64)},
    "relu":   lambda i, p: {"B": np.maximum(i["A"], 0)},
    "rowsum": lambda i, p: {"y": _rows(i["A"], p).sum(axis=1, dtype=np.int64)},
    "axpy":   lambda i, p: {"y_out": np.int64(p["alpha"]) * i["x"] + i["y"]},
}


def ref(kernel: str, ins: dict, pins: dict) -> dict:
    if kernel not in REF:
        raise KeyError(f"sim/ref.py has no reference for {kernel}")
    with np.errstate(over="ignore"):
        out = REF[kernel]({k: np.asarray(v, dtype=np.int64) for k, v in ins.items()}, pins)
    return {k: np.asarray(v, dtype=np.int64) for k, v in out.items()}


# ---------------------------------------------------------------- the blocks alone, cycle by cycle
# snax-forge's datapaths (hw/chisel/src/main/scala/snax/forge/datapath/, stream/FifoPacker.scala and FifoSlicer.scala, at the commit
# of the point) at their types (D175), stepped one slot at a time as sim/sources/char.py's schedule() drives them. A
# value is its port's bits, unsigned; cast(x, t, u) extends x from type t to u by t's signedness (sign-extended from
# a signed t) or keeps u's low bits. A slot's inputs are applied at its rising edge, the TB samples the outputs at
# its falling edge (the registers still hold what the slots before left, the combinational outputs see the slot's
# inputs), and the next rising edge takes it.
#   SimdLanes         out_l = cast(cast(a_l, A, op) op cast(b_l, B, op) at op, op, out) (combinational); one stream
#                     (a alone): b_l is the scalar k at op, its pin's bits (kCsr) or the baked k; max and min compare
#                     by op's signedness; axpby: out_l = cast(k1 a + k2 b at op, op, out), k1 a + b without k2, each
#                     k from its pin (k1Csr, k2Csr) or baked (k1, k2); a pin's value is the slot's pins[<k>];
#                     axpbypcz (three streams): out_l = cast(fl(k1 a + k2 b + k3 c at op), op, out), an unset k
#                     the input itself, each product and the sum at op's bits; requant: cast(min(max(fl(a), lo),
#                     hi) at op, op, out); threshold: hi where a - k + 1 at op is at least 1 by op's signedness, else
#                     0; fl(x) = x // d, arithmetic at a signed op and logical at an unsigned one (d a power of 2)
#   Mac (accumulate)  p_l = cast(cast(a_l, A, op) cast(b_l, B, op) at op, op, out);
#                     on fire: s_l <- first ? p_l : s_l + p_l at out; out_l = s_l; with rows R > 1 (D191) R rows
#                     of sums: on fire s[row]_l <- first ? p_l : s[row]_l + p_l; out_l = s[drain]_l
#   TreeAccumulate    on fire: acc <- first ? beat : acc + beat, beat = sum_l cast(in_l, in, out) at out; out = acc
#   SerialAccumulate  on read: acc <- (first and lane = 0 ? 0 : acc) + cast(in_lane, in, out) at out; out = acc
#   LinkBuffer        on load: slot[wslot] <- in; out = slot[rslot] (combinational read; slot 0 at depth 1); in
#                     the stream window rslot = wslot = t mod D, so out at slot t is the beat loaded at t - D
#   HaloLink          H = ceil((T - 1) / W) held beats; e = the held beats' elements oldest first, then in's;
#                     taps_t_l = e[l + t] (combinational); on load: the held beats shift, in the newest (D206)
#   FifoPacker        r = words 64 / (width inLanes) pushes to a beat, element e at bits [w(e+1)-1 : we]; sending =
#                     count = r - 1 or last; out_valid = in_valid sending, in_ready = not sending or out_ready;
#                     out_bits: slot u the push when u = count, held[u] when u < count, zero above; on a push
#                     (in_valid in_ready): count <- 0 when sending, else held[count] <- in, count + 1; clear: count <- 0
#   FifoSlicer        r = words 64 / (width outLanes) pops to an in-beat, pop u lane l element u outLanes + l at bits
#                     [w(e+1)-1 : we] of the held beat; last = r = 1 or count = r - 1; out_valid = full, in_ready =
#                     enable (not full or out_ready last); out_bits pop count's lanes, compared through out_valid (0
#                     when not full); on a take (in_valid in_ready): data <- in, full, count <- 0, else on a pop
#                     (full out_ready): full <- 0 when last, else count + 1; clear: full <- 0, count <- 0 (wins)
# Every register starts at 0 (RegInit), as after the TB's reset; the packer's held slots and the slicer's data are
# written before read.
M64 = (1 << 64) - 1
CHAR_OPS = {"add": lambda a, b: a + b, "mul": lambda a, b: a * b}
SCALARS = ("k", "k1", "k2", "k3")     # SimdLanes' scalar slots, each baked (params[<k>]) or from its pin (params[<k>Csr])


def _width(t: str) -> int:
    return int(t.removeprefix("u").removeprefix("int"))


def _cast(x: int, frm: str, to: str) -> int:
    """x, a value of type frm (its bits), as type to: extended by frm's signedness, or wrapped to to's width."""
    wf, wt = _width(frm), _width(to)
    x &= (1 << wf) - 1
    if not frm.startswith("u") and wt > wf and x >> (wf - 1):
        x |= ((1 << wt) - 1) ^ ((1 << wf) - 1)
    return x & ((1 << wt) - 1)


def _value(x: int, t: str) -> int:
    """x, t's bits, as the number it is at t (negative for a signed t with its top bit set)."""
    w = _width(t)
    return x - (1 << w) if not t.startswith("u") and x >> (w - 1) else x


def _scalar(params: dict, name: str, pins: dict) -> int | None:
    """SimdLanes' scalar `name` as op's bits: its pin's value (params[<name>Csr]), the baked params[name], or None
    (also lo and hi, always baked)."""
    if params.get(f"{name}Csr"):
        return pins[name] & ((1 << _width(params["opType"])) - 1)
    v = params.get(name)
    return None if v is None else v & ((1 << _width(params["opType"])) - 1)


def _floor_div(x: int, params: dict) -> int:
    """x // d at op's bits (x op's bits, d a power of two): arithmetic at a signed op, logical at an unsigned one."""
    top = params["opType"]
    s = params["d"].bit_length() - 1
    return (_value(x, top) >> s) & ((1 << _width(top)) - 1)


def _lanes_out(params: dict, a: int, b: int | None, pins: dict, c: int | None = None) -> int:
    """One SimdLanes lane at op's bits: a, b and c already cast to op (b None at one stream, the scalar k in its
    place; c only at three), the result not yet cast to out."""
    top, op = params["opType"], params["op"]
    m = (1 << _width(top)) - 1
    if op == "axpbypcz":
        ks = [_scalar(params, n, pins) for n in ("k1", "k2", "k3")]
        total = sum(x if k is None else (k * x) & m for k, x in zip(ks, (a, b, c))) & m
        return _floor_div(total, params)
    if op == "requant":
        lo, hi = (_scalar(params, n, {}) for n in ("lo", "hi"))
        q = _floor_div(a, params)
        q = max(q, lo, key=lambda x: _value(x, top))
        return min(q, hi, key=lambda x: _value(x, top))
    if op == "threshold":
        delta = (a - _scalar(params, "k", pins) + 1) & m
        return _scalar(params, "hi", {}) if (_value(delta, top) > 0 if not top.startswith("u") else delta) else 0
    if op == "axpby":
        k1, k2 = _scalar(params, "k1", pins), _scalar(params, "k2", pins)
        return k1 * a + (b if k2 is None else k2 * b)
    if b is None:
        b = _scalar(params, "k", pins)
    if op in ("max", "min"):
        pick = max if op == "max" else min
        return pick(a, b, key=lambda x: _value(x, top))
    return CHAR_OPS[op](a, b)


def char_ref(datapath: str, params: dict, slots: list[dict], beats: list[list[int]]) -> list[list[int]]:
    """The expected outputs (one list of the compared outputs' values, unsigned, in tb.json's outs order) at every
    slot's falling edge. `beats` are the new data beats in the order the slots take them, each a list of the data
    inputs' values in tb.json's data_in order (already the ports' bits); a slot without new data holds the last beat
    (0 before any). A SimdLanes' scalar read from its pin is the slot's pins[<k>] (sim/pwr.py's char_stimulus
    holds one value a window)."""
    w = params.get("lanes", 1)
    cur, nb = [0] * (len(params["inTypes"]) * w if datapath in ("SimdLanes", "Mac") else
                     max(w, params.get("inLanes", 1), params.get("words", 1))), 0
    if datapath in ("SimdLanes", "Mac"):
        ins = params["inTypes"]
        ta, tb = ins[0], ins[1] if len(ins) > 1 else None   # a SimdLanes of one stream: a alone
        tc = ins[2] if len(ins) > 2 else None               # axpbypcz's c
        top, tout = params["opType"], params["outType"]
        mo = (1 << _width(tout)) - 1
        prod = lambda i: _cast(_cast(cur[i], ta, top) * _cast(cur[w + i], tb, top), top, tout)  # noqa: E731
        if datapath == "Mac":
            bank = [[0] * w for _ in range(params.get("rows", 1))]
    elif datapath in ("TreeAccumulate", "SerialAccumulate"):
        tin, tout = params["inType"], params["outType"]
        mo = (1 << _width(tout)) - 1
        acc = 0
    elif datapath == "LinkBuffer":
        depth = params["depth"]
        mem = [[0] * w for _ in range(depth)]
    elif datapath == "HaloLink":
        taps = params["taps"]
        hold = [[0] * w for _ in range((taps + w - 2) // w)]
    elif datapath == "FifoPacker":
        lw, nl = _width(params["laneType"]), params["inLanes"]
        r = params["words"] * 64 // (lw * nl)
        chunk = lw * nl
        count, held = 0, [0] * max(r - 1, 0)
    elif datapath == "FifoSlicer":
        lw, nl, nw = _width(params["laneType"]), params["outLanes"], params["words"]
        r = nw * 64 // (lw * nl)
        lm = (1 << lw) - 1
        data, full, count = 0, False, 0
    else:
        raise KeyError(f"sim/ref.py has no char reference for {datapath}")
    out = []
    for sl in slots:
        if sl["new"]:
            cur = list(beats[nb])
            nb += 1
        p = sl["pins"]
        # the falling edge: what the registers hold, the combinational outputs of this slot's inputs
        if datapath == "SimdLanes":
            out.append([_cast(_lanes_out(params, _cast(cur[i], ta, top), None if tb is None else
                                         _cast(cur[w + i], tb, top), p,
                                         None if tc is None else _cast(cur[2 * w + i], tc, top)), top, tout)
                        for i in range(w)])
        elif datapath == "Mac":
            out.append(list(bank[p.get("drain", 0)]))
        elif datapath in ("TreeAccumulate", "SerialAccumulate"):
            out.append([acc])
        elif datapath == "LinkBuffer":
            out.append(list(mem[p["rslot"] if depth > 1 else 0]))
        elif datapath == "HaloLink":
            e = [x for beat in hold for x in beat] + list(cur[:w])
            out.append([e[lane + t] for t in range(taps) for lane in range(w)])
        elif datapath == "FifoSlicer":
            last = r == 1 or count == r - 1
            ready = bool(p["enable"]) and (not full or (bool(p["out_ready"]) and last))
            bits = [(data >> (lw * (count * nl + j))) & lm if full else 0 for j in range(nl)]
            out.append(bits + [int(full), int(ready)])
        else:
            x = sum(v << (lw * i) for i, v in enumerate(cur[:nl]))
            sending = r == 1 or count == r - 1 or bool(p["last"])
            ready = (not sending) or bool(p["out_ready"])
            beat = 0
            for u in range(r):
                v = x if u == count else held[u] if u < count and u < r - 1 else 0
                beat |= v << (chunk * u)
            out.append([(beat >> (64 * k)) & M64 for k in range(params["words"])]
                       + [int(bool(p["in_valid"]) and sending), int(ready)])
        # the next rising edge takes the slot
        if datapath == "Mac" and p["fire"]:
            s = bank[p.get("row", 0)]
            bank[p.get("row", 0)] = [prod(i) if p["first"] else (s[i] + prod(i)) & mo for i in range(w)]
        elif datapath == "TreeAccumulate" and p["fire"]:
            b = sum(_cast(x, tin, tout) for x in cur[:w]) & mo
            acc = b if p["first"] else (acc + b) & mo
        elif datapath == "SerialAccumulate" and p["read"]:
            lane = p["lane"] if w > 1 else 0
            acc = ((0 if p["first"] and lane == 0 else acc) + _cast(cur[lane], tin, tout)) & mo
        elif datapath == "LinkBuffer" and p["load"]:
            mem[p["wslot"] if depth > 1 else 0] = list(cur)
        elif datapath == "HaloLink" and p["load"]:
            hold = hold[1:] + [list(cur[:w])]
        elif datapath == "FifoPacker":
            if p["in_valid"] and ready and r > 1:
                if sending:
                    count = 0
                else:
                    held[count] = x
                    count += 1
            if p["clear"]:
                count = 0
        elif datapath == "FifoSlicer":
            if p["in_valid"] and ready:
                data, full, count = sum(v << (64 * k) for k, v in enumerate(cur[:nw])), True, 0
            elif full and p["out_ready"]:
                if last:
                    full = False
                else:
                    count += 1
            if p["clear"]:
                full, count = False, 0
    if nb != len(beats):
        raise ValueError(f"char_ref: {len(beats)} beats given, the slots take {nb}")
    return out
