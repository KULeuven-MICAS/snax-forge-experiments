"""CSYN1 Part B: a cluster run's program output against the bundle's forge_expected.txt (snax-forge D123).

    pixi run python cluster/check.py FORGE_EXPECTED RUN_OUTPUT

Mirrors snax_cluster's target/snitch_cluster/snax_forge_check.sh `compare`: the run's `forge data:` line
equals the expected one; its `forge counter <task>: <c>` lines, in order, name the expected tasks, each
count within that task's `forge fill <task>: <n>` of the expected count (the group's streamer fill: the
counter counts the streamer's head start before START, which SNAX-GVSoC does not model); a file without
fill lines asks for equal counts. Also reads the run's `forge cycles:` and its `[tc_sram_impl] <path>: <macro>`
prints (cluster/mem.py's, one per instance at time 0, `<path>.gen_<macro>: <macro>`), and the macro models'
`RAMCOUNT <path> <macro> reads N writes M` lines (ram/ram.py's final block): the netlist run (R4) and the RTL macro
run, compared without the paths (they differ; the netlist's hold escaped identifiers with spaces), must give the same
reads on every instance and the same writes, but for one more write allowed on an instance of the netlist run: the
write at time 0 under +initreg+0 (PITFALLS Q8, Q14). Standard library only.
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
        if d > fill:
            ok = False
            notes.append(f"{wn}: counter {gv} against {wv}, beyond its fill {fill}")
        elif d:
            notes.append(f"{wn}: counter {gv} against {wv}, within its fill {fill}")
    return ok, notes


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


def ram_compare(want_text: str, got_text: str, srams: dict[str, int]) -> tuple[bool, list[str], list[dict]]:
    """The run's RAMCOUNT lines against the reference run's: (pass, notes, extra writes). Per macro, the instances
    are matched by their counts (the paths differ): equal (reads, writes) first, then the run's (r, w) to the
    reference's (r, w - 1), each such one an extra write ({macro, reads, rtl_writes, gls_writes}). Anything left
    unmatched (a read difference, more than one extra write, an instance missing or added) fails, as does a run
    whose instances per macro are not `srams`."""
    want, got = ramcounts(want_text), ramcounts(got_text)
    notes: list[str] = []
    per = dict(sorted(Counter(m for m, _r, _w in got).items()))
    if per != dict(sorted(srams.items())):
        notes.append(f"instances {per}, want {dict(sorted(srams.items()))}")
    left_w, left_g = Counter(want), Counter(got)
    same = left_w & left_g
    left_w, left_g = left_w - same, left_g - same
    extra = []
    for (m, r, w), n in sorted(left_g.items()):
        k = min(n, left_w[(m, r, w - 1)])
        if k:
            left_w[(m, r, w - 1)] -= k
            left_g[(m, r, w)] -= k
            extra += [{"macro": m, "reads": r, "rtl_writes": w - 1, "gls_writes": w}] * k
    only_g, only_w = sorted((+left_g).elements()), sorted((+left_w).elements())
    if only_g or only_w:
        notes.append(f"{len(got)} lines against {len(want)}; unmatched in the run {only_g[:5]}, "
                     f"unmatched in the reference {only_w[:5]}")
    return not notes, notes, extra


def ram_summary(lines: int, ok: bool, extra: list[dict]) -> str:
    """The summary's RAMCOUNT part."""
    if not ok:
        return f"RAMCOUNT {lines} differ"
    more = f" but {len(extra)} macros +1 at reset (PITFALLS Q8)" if extra else ""
    return f"RAMCOUNT {lines}: reads equal, writes equal{more}"


def success(text: str) -> bool:
    return SUCCESS in text


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
