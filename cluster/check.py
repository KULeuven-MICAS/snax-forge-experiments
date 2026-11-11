"""CSYN1 Part B: a cluster run's program output against the bundle's forge_expected.txt (snax-forge D123).

    pixi run python cluster/check.py FORGE_EXPECTED RUN_OUTPUT

Mirrors snax_cluster's target/snitch_cluster/snax_forge_check.sh `compare`: the run's `forge data:` line
equals the expected one; its `forge counter <task>: <c>` lines, in order, name the expected tasks, each
count within that task's `forge fill <task>: <n>` of the expected count (the group's streamer fill: the
counter counts the streamer's head start before START, which SNAX-GVSoC does not model); a file without
fill lines asks for equal counts. Also reads the run's `forge cycles:` and its `[tc_sram_impl] <path>: <macro>`
lines (cluster/mem.py's print, one per instance at time 0). Standard library only.
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
SRAM = re.compile(r"\[tc_sram_impl\] (\S+): (\w+)")
SUCCESS = "[SUCCESS] Program finished successfully"


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


def srams(text: str) -> dict[str, str]:
    """{instance path: macro} from the run's [tc_sram_impl] lines."""
    return {m.group(1): m.group(2) for m in SRAM.finditer(text)}


def sram_counts(text: str) -> dict[str, int]:
    return dict(sorted(Counter(srams(text).values()).items()))


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
