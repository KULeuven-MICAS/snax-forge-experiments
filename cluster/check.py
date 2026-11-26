"""cluster/check.py - a cluster run's program output against the bundle's forge_expected.txt (snax-forge D123).

    pixi run python cluster/check.py FORGE_EXPECTED RUN_OUTPUT

Mirrors snax_cluster's snax_forge_check.sh `compare`: the run's `forge data:` line equals the expected one, and
each `forge counter <task>: <c>` is within WARN_PCT of the expected count beyond the task's streamer fill (NEAR up
to NEAR_PCT, WARNING up to WARN_PCT, FAIL beyond). Also the run's `forge cycles:`, its `[tc_sram_impl]` prints and
the macro models' RAMCOUNT lines. The netlist run's gates against the RTL run are data_compare and timing_compare
(TIMING_PCT); ram_compare and compare (D123 against SNAX-GVSoC) are reported. Standard library only.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

COUNTER = re.compile(r"forge counter (.+?): (-?\d+)")
FILL = re.compile(r"forge fill (.+?): (-?\d+)")
DATA = re.compile(r"forge data: .*")
CYCLES = re.compile(r"forge cycles: (\d+)")
SRAM_MARK = "[tc_sram_impl] "
SRAM_END = re.compile(r"\.gen_(\w+): (\w+)[ \t]*$", re.M)
SUCCESS = "[SUCCESS] Program finished successfully"
NEAR_PCT, WARN_PCT = 10, 15   # D123: a counter's gap beyond its fill, in % of its count
TIMING_PCT = 10               # the netlist run's cycles and counters against the RTL run's, in % of the RTL's
# the path may hold spaces: a netlist's escaped identifiers end in one (`\gen_banks[0].i_data_mem .\gen_...`)
RAMCOUNT = re.compile(r"RAMCOUNT (\S.*?)\s+(\w+) reads (\d+) writes (\d+)")


def parse(text: str) -> dict:
    """The forge lines of an expected file or a run's output: counters in order, fills, the data line
    (the last one, as the shell script's awk keeps it), cycles (the first)."""
    counters, fills, data, cycles = [], {}, None, None
    for line in text.splitlines():
        if m := COUNTER.search(line):
            counters.append((m.group(1), int(m.group(2))))
        elif m := FILL.search(line):
            fills[m.group(1)] = int(m.group(2))
        elif m := DATA.search(line):
            data = m.group(0).rstrip()
        elif (m := CYCLES.search(line)) and cycles is None:
            cycles = int(m.group(1))
    return {"counters": counters, "fills": fills, "data": data, "cycles": cycles}


def compare(want_text: str, got_text: str) -> tuple[bool, list[str]]:
    """D123: (pass, notes). Notes name each counter that differs within its fill (on a pass) or what failed."""
    want, got = parse(want_text), parse(got_text)
    ok, notes = True, []
    if want["data"] is None:
        ok = False
        notes.append("the expected file has no forge data line")
    elif got["data"] != want["data"]:
        ok = False
        notes.append(f"data: want '{want['data']}', got '{got['data']}'")
    if len(got["counters"]) != len(want["counters"]):
        ok = False
        notes.append(f"{len(got['counters'])} counters, want {len(want['counters'])}")
    for (wn, wv), (gn, gv) in zip(want["counters"], got["counters"]):
        if gn != wn:
            ok = False
            notes.append(f"counter {gn!r} where {wn!r} is expected")
            continue
        fill = want["fills"].get(wn, 0)
        d = abs(gv - wv)
        over = max(0, d - fill)
        e = 0.0 if over == 0 else (100 * over / wv if wv > 0 else 100.0)
        if over:
            verdict = "NEAR" if e <= NEAR_PCT else "WARNING" if e <= WARN_PCT else "FAIL"
            ok = ok and verdict != "FAIL"
            notes.append(f"{wn}: counter {gv} against {wv}, {over} beyond its fill {fill} ({e:.1f} %, {verdict})")
        elif d:
            notes.append(f"{wn}: counter {gv} against {wv}, within its fill {fill}")
    return ok, notes


def data_compare(want_text: str, rtl_text: str, got_text: str) -> tuple[bool, list[str]]:
    """The data gate: the netlist run's data line equals the expected one and the RTL run's."""
    want, rtl, got = parse(want_text)["data"], parse(rtl_text)["data"], parse(got_text)["data"]
    notes = []
    if want is None:
        notes.append("the expected file has no forge data line")
    elif got != want:
        notes.append(f"data: want '{want}', got '{got}'")
    if got != rtl:
        notes.append(f"data: the RTL run has '{rtl}', the netlist run '{got}'")
    return not notes, notes


def timing_compare(rtl_text: str, got_text: str, pct: float = TIMING_PCT) -> tuple[bool, list[str], list[dict]]:
    """The timing gate: the netlist run's cycles and each counter, in order, within pct % of the RTL run's.
    Returns (pass, notes, rows); each row names the quantity, both values and the gap in % of the RTL's."""
    rtl, got = parse(rtl_text), parse(got_text)
    rows, notes = [], []
    pairs = [("cycles", rtl["cycles"], got["cycles"])]
    if [n for n, _ in rtl["counters"]] != [n for n, _ in got["counters"]]:
        notes.append(f"counters {[n for n, _ in got['counters']]}, the RTL run has {[n for n, _ in rtl['counters']]}")
    else:
        pairs += [(f"counter {n}", rv, gv) for (n, rv), (_, gv) in zip(rtl["counters"], got["counters"])]
    for name, rv, gv in pairs:
        if rv is None or gv is None:
            notes.append(f"{name}: RTL {rv}, netlist {gv}")
            continue
        e = 100.0 * abs(gv - rv) / rv if rv else (0.0 if gv == rv else 100.0)
        rows.append({"what": name, "rtl": rv, "gls": gv, "diff_pct": round(e, 3)})
        if e > pct:
            notes.append(f"{name}: netlist {gv} against RTL {rv}, {e:.1f} % (more than {pct:g} %)")
    return not notes, notes, rows


def sram_lines(text: str) -> int:
    """The number of [tc_sram_impl] prints (their start)."""
    return text.count(SRAM_MARK)


def sram_counts(text: str) -> dict[str, int]:
    """{macro: instances} from the ends of the [tc_sram_impl] prints, `<path>.gen_<macro>: <macro>`. Read from
    the end, not as whole lines: vsim's prints and the program's output reach the log through separate
    buffers, and the program's lines can land inside a print (PITFALLS Q13)."""
    return dict(sorted(Counter(m.group(2) for m in SRAM_END.finditer(text) if m.group(1) == m.group(2)).items()))


def ramcounts(text: str) -> list[tuple[str, int, int]]:
    """The RAMCOUNT lines as (macro, reads, writes), sorted: the instance paths left out (RTL and netlist differ)."""
    return sorted((m.group(2), int(m.group(3)), int(m.group(4))) for m in RAMCOUNT.finditer(text))


# NB (X81): a netlist run may count one more read or write per instance than the RTL run, its access at time 0
def ram_compare(want_text: str, got_text: str, srams: dict[str, int]) -> tuple[bool, list[str], list[dict]]:
    """The run's RAMCOUNT lines against the reference run's: (pass, notes, extra accesses). Per macro, the instances
    are matched by their counts (the paths differ): per (macro, reads), the run's writes and the reference's
    sorted and paired in order, each pair equal or the run's one more, each such one an extra write ({macro,
    reads, rtl_writes, gls_writes}). Sorted order finds such a pairing whenever one exists (two I-cache
    sets at 235 and 236 writes, the netlist's at 236 and 237, which equal-first matching paired wrongly). A group
    with none falls back to equal first, then +1 write, then +1 read with writes equal, an extra read ({macro,
    writes, rtl_reads, gls_reads}; the clock-gated netlist's TCDM banks read once at time 0, PITFALLS
    Q14). At most one extra access per instance, a read or a write: the one edge at time 0. What is left unmatched
    (more than one extra access, fewer, an instance missing or added) fails, as does a run whose instances per
    macro are not `srams`."""
    want, got = ramcounts(want_text), ramcounts(got_text)
    notes: list[str] = []
    per = dict(sorted(Counter(m for m, _r, _w in got).items()))
    if per != dict(sorted(srams.items())):
        notes.append(f"instances {per}, want {dict(sorted(srams.items()))}")
    extra = []
    left_w, left_g = Counter(), Counter()
    for key in sorted({(m, r) for m, r, _w in want + got}):
        ws = sorted(w for m, r, w in want if (m, r) == key)
        gs = sorted(w for m, r, w in got if (m, r) == key)
        if len(ws) == len(gs) and all(g - w in (0, 1) for w, g in zip(ws, gs)):
            extra += [{"macro": key[0], "reads": key[1], "rtl_writes": w, "gls_writes": g}
                      for w, g in zip(ws, gs) if g == w + 1]
            continue
        left_w.update((*key, w) for w in ws)
        left_g.update((*key, g) for g in gs)
    same = left_w & left_g
    left_w, left_g = left_w - same, left_g - same
    for (m, r, w), n in sorted(left_g.items()):
        k = min(n, left_w[(m, r, w - 1)])
        if k:
            left_w[(m, r, w - 1)] -= k
            left_g[(m, r, w)] -= k
            extra += [{"macro": m, "reads": r, "rtl_writes": w - 1, "gls_writes": w}] * k
    for (m, r, w), n in sorted(left_g.items()):          # one more read, writes equal (time 0, Q14)
        k = min(n, left_w[(m, r - 1, w)])
        if k:
            left_w[(m, r - 1, w)] -= k
            left_g[(m, r, w)] -= k
            extra += [{"macro": m, "writes": w, "rtl_reads": r - 1, "gls_reads": r}] * k
    only_g, only_w = sorted((+left_g).elements()), sorted((+left_w).elements())
    if only_g or only_w:
        notes.append(f"{len(got)} lines against {len(want)}; unmatched in the run {only_g[:5]}, "
                     f"unmatched in the reference {only_w[:5]}")
    return not notes, notes, extra


def ram_summary(lines: int, ok: bool, extra: list[dict]) -> str:
    """The summary's RAMCOUNT part; extra holds ram_compare's extra writes and extra reads."""
    if not ok:
        return f"RAMCOUNT {lines} differ (reported)"
    n_w = sum(1 for e in extra if "rtl_writes" in e)
    n_r = sum(1 for e in extra if "rtl_reads" in e)
    reads = f"reads equal but {n_r} macros +1 at time 0 (PITFALLS Q14)" if n_r else "reads equal"
    more = f" but {n_w} macros +1 at reset (PITFALLS Q8)" if n_w else ""
    return f"RAMCOUNT {lines}: {reads}, writes equal{more}"


def success(text: str) -> bool:
    return SUCCESS in text


def data_ok(want_text: str, got_text: str) -> tuple[bool, list[str]]:
    """The rtl step's gate (X108): the run's data line equals the expected one and the run printed every counter
    the expected file names; the counters' values are D123's, reported."""
    want, got = parse(want_text), parse(got_text)
    notes = []
    if want["data"] is None:
        notes.append("the expected file has no forge data line")
    elif got["data"] != want["data"]:
        notes.append(f"data: want '{want['data']}', got '{got['data']}'")
    if [n for n, _ in got["counters"]] != [n for n, _ in want["counters"]]:
        notes.append(f"counters {[n for n, _ in got['counters']]}, want {[n for n, _ in want['counters']]}")
    return not notes, notes


# X108: a quiet window's cycles on the RTL against SNAX-GVSoC's, recorded, never a gate
QUIET_OK_PCT, QUIET_WARN_PCT = 10, 20
QUIET_SMALL = 20          # a window of at most this many cycles gets its gap in cycles, no verdict


def quiet_compare(rtl_wins: list[dict], gvsoc_wins: list[dict]) -> tuple[str, list[dict]]:
    """Each quiet window (by mark) on the RTL against SNAX-GVSoC's: rows of mark, kind, both cycles, the gap and its
    share of SNAX-GVSoC's, and the verdict: OK within QUIET_OK_PCT, WARNING within QUIET_WARN_PCT, INVESTIGATE
    beyond, SMALL for a window of at most QUIET_SMALL cycles on both, MISSING for a mark one side lacks. The worst
    verdict of the windows comes first (INVESTIGATE, MISSING, WARNING, OK; SMALL counts as OK)."""
    gv = {w["mark"]: w for w in gvsoc_wins}
    rows = []
    for w in rtl_wins:
        g = gv.get(w["mark"])
        if g is None:
            rows.append({"mark": w["mark"], "kind": w["kind"], "rtl": w["cycles"], "gvsoc": None, "diff": None,
                         "pct": None, "verdict": "MISSING"})
            continue
        d = w["cycles"] - g["cycles"]
        pct = 100.0 * d / g["cycles"] if g["cycles"] else (0.0 if d == 0 else 100.0)
        if max(w["cycles"], g["cycles"]) <= QUIET_SMALL:
            v = "SMALL"
        else:
            v = "OK" if abs(pct) <= QUIET_OK_PCT else "WARNING" if abs(pct) <= QUIET_WARN_PCT else "INVESTIGATE"
        rows.append({"mark": w["mark"], "kind": w["kind"], "rtl": w["cycles"], "gvsoc": g["cycles"], "diff": d,
                     "pct": round(pct, 2), "verdict": v})
    seen = {w["mark"] for w in rtl_wins}
    rows += [{"mark": m, "kind": g["kind"], "rtl": None, "gvsoc": g["cycles"], "diff": None, "pct": None,
              "verdict": "MISSING"} for m, g in sorted(gv.items()) if m not in seen]
    order = ("INVESTIGATE", "MISSING", "WARNING", "OK")
    got = {("OK" if r["verdict"] == "SMALL" else r["verdict"]) for r in rows}
    worst = next((v for v in order if v in got), "OK")
    return worst, rows


# X105: what a cluster's netlist is made of, in a bundle zip: the cluster file and the RTL DC reads
def hardware(members: dict[str, bytes]) -> dict[str, bytes]:
    """The bundle zip's members that make the netlist: bundle/snax_forge.hjson and everything under bundle/rtl/."""
    return {k: v for k, v in members.items() if k == "bundle/snax_forge.hjson" or k.startswith("bundle/rtl/")}


def hardware_diff(a: dict[str, bytes], b: dict[str, bytes]) -> list[str]:
    """The hardware members that differ between two bundle zips (hardware() of each), by name; empty when the
    netlist of one is the netlist of the other. Two bundles without any hardware member never match."""
    ha, hb = hardware(a), hardware(b)
    if not ha or not hb:
        return ["no bundle/snax_forge.hjson or bundle/rtl/ in one of the bundles"]
    return sorted(k for k in ha.keys() | hb.keys() if ha.get(k) != hb.get(k))


# X107: the lstp macros' .db (COST2 R1b, results/ram/runs/2026-11-26_cost2_r1b.md); DC and PT read only these
LSTP_DB_SHA256 = {
    "sram_d512_w64_m8": "334f95820c102c41648d267c9523dc3aa9db87e6f4b6e22660a270fa38eb96ce",
    "sram_d128_w256_m8": "d5015ed6be916ffde78f656389c7da8ab47a28f76a7956570e76404662b420a0",
    "sram_d128_w39": "f4b2ebfe8f5f4c0818f397f6f1355e59074e6ff5fe1185b4f710922783433e99",
}


def db_check(dbs: dict[str, bytes]) -> tuple[bool, dict[str, dict]]:
    """Each macro's .db against LSTP_DB_SHA256: (all equal, {macro: {sha256, want, ok}}); a macro not in the map
    fails."""
    import hashlib  # noqa: PLC0415
    out = {}
    for m, data in sorted(dbs.items()):
        s = hashlib.sha256(data).hexdigest()
        out[m] = {"sha256": s, "want": LSTP_DB_SHA256.get(m), "ok": s == LSTP_DB_SHA256.get(m)}
    return all(v["ok"] for v in out.values()) and bool(out), out


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ok, notes = compare(Path(sys.argv[1]).read_text(), Path(sys.argv[2]).read_text())
    print("PASS" if ok else "FAIL")
    for n in notes:
        print("  " + n)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
