#!/usr/bin/env python3
"""report/strm_table.py - STRM1: the reader and interconnect tables snax-forge's HW cost model reads, and the
reference interpolation it copies (docs/DECISIONS.md X53).

  pixi run strm-table [--tech nangate45] [--loo]
  pixi run strm-table-test                       report/test_strm_table.py

Reads results/streamer/<tech>/synth_dc.csv and power_pt.csv (syn/syn.py and sim/pwr.py --source streamer) and the
same two of results/xbar/<tech>/, and writes results/strm/<tech>/:

  streamer.csv  depth, loops, channels, area_um2, e_beat_pj, flops, slack_ns, fmax_mhz, status
                one row per grid point (FIFO depth x loops x channels): DC's total area, PT's dynamic energy over
                the busy window / beats, DC's flop count, worst slack and fmax (a lower bound, X2)
  xbar.csv      inputs, banks, area_um2, e_access_pj, flops, slack_ns, fmax_mhz, status
                one row per grid point (inputs x banks); e_access_pj is PT's energy over the window / grants and is
                empty where inputs > banks (not measured: no conflict-free stimulus, X52)
status is "ok" or the failing step's status (DC's, then PT's); a failed point keeps its row with the numbers it
has. A reader's cost also stands for a writer's (X52).

The reference interpolation (X53), for a query inside the grid:
  reader  trilinear over (depth, loops, channels), linear in each raw value between the two grid values around
          it (a grid value is matched exactly); area and energy alike
  xbar    bilinear over (inputs, banks): area linear in inputs and banks; energy linear in 1/inputs (its shape is
          a + b/inputs, a per-cycle cost shared by the grants, docs/interpolation.md) and in banks. Energy where
          inputs > banks: each bank count's row is completed with its value at inputs = banks (the most measured),
          then interpolated as the rest
  A query outside the grid's range on any axis is refused (ValueError), as is one that needs a missing value.

--loo prints the leave-one-out check (for information): each interior grid point predicted from its neighbours
with its own value on every interpolated axis left out (reader: depth 4 and 8, loops 2 to 6, channels 2, 4, 6, 8,
trilinear from the 8 surrounding points; xbar: inputs 8 to 56 at the same bank count, area linear in inputs,
energy linear in 1/inputs, only where the point and both neighbours are measured), with the mean and worst error of
area and energy. The worked steps are in docs/interpolation.md.
Standard library only.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READER_AXES = ("depth", "loops", "channels")
XBAR_AXES = ("inputs", "banks")
STREAMER_COLUMNS = ["depth", "loops", "channels", "area_um2", "e_beat_pj", "flops", "slack_ns", "fmax_mhz", "status"]
XBAR_COLUMNS = ["inputs", "banks", "area_um2", "e_access_pj", "flops", "slack_ns", "fmax_mhz", "status"]


# ---------------------------------------------------------------- the reference interpolation (X53)
# How an axis is measured for one field: "lin" (the raw value) or "inv" (1 / value). The weight between two grid
# values lo < x < hi is (g(x) - g(lo)) / (g(hi) - g(lo)), so an "inv" axis reproduces a + b / x exactly.
SCALES = {"lin": lambda x: x, "inv": lambda x: 1.0 / x}
XBAR_SCALES = {"e_access_pj": {"inputs": "inv"}}


class Table:
    """A rectilinear grid: axes (name -> sorted values), per field {coordinate tuple: value}, and per field the
    scale of each axis ("lin" unless named in scales[field][axis])."""

    def __init__(self, axes: dict[str, list[float]], fields: dict[str, dict[tuple, float]],
                 scales: dict[str, dict[str, str]] | None = None):
        self.axes = {k: sorted(v) for k, v in axes.items()}
        self.fields = fields
        self.scales = scales or {}

    def at(self, field: str, **q: float) -> float:
        """Multilinear interpolation of `field` at q (one value per axis), linear in each axis's scale."""
        names = list(self.axes)
        if set(q) != set(names):
            raise ValueError(f"query {q}: give exactly {names}")
        spans = []
        for n in names:
            vals, x = self.axes[n], q[n]
            if x < vals[0] or x > vals[-1]:
                raise ValueError(f"{n} = {x} is outside the grid [{vals[0]}, {vals[-1]}]")
            i = bisect.bisect_left(vals, x)
            if vals[i] == x:
                spans.append([(vals[i], 1.0)])
            else:
                lo, hi = vals[i - 1], vals[i]
                g = SCALES[self.scales.get(field, {}).get(n, "lin")]
                w = (g(x) - g(lo)) / (g(hi) - g(lo))
                spans.append([(lo, 1.0 - w), (hi, w)])
        total = 0.0
        for corner in itertools.product(*spans):
            key = tuple(c for c, _ in corner)
            weight = 1.0
            for _, w in corner:
                weight *= w
            v = self.fields[field].get(key)
            if v is None:
                raise ValueError(f"{field} has no value at {dict(zip(names, key))}")
            total += weight * v
        return total


def _f(x: str) -> float | None:
    return float(x) if x not in ("", None) else None


def load(path: Path, axes: tuple[str, ...], fields: tuple[str, ...],
         scales: dict[str, dict[str, str]] | None = None) -> Table:
    """A table CSV (streamer.csv or xbar.csv) as a Table; rows whose status is not ok give no values."""
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    ax = {a: sorted({int(r[a]) for r in rows}) for a in axes}
    fv: dict[str, dict[tuple, float]] = {f: {} for f in fields}
    for r in rows:
        if r["status"] != "ok":
            continue
        key = tuple(int(r[a]) for a in axes)
        for f in fields:
            v = _f(r[f])
            if v is not None:
                fv[f][key] = v
    return Table(ax, fv, scales)


def complete_xbar(t: Table) -> Table:
    """xbar's energy where inputs > banks: each bank count's value at inputs = banks (X53)."""
    e = dict(t.fields["e_access_pj"])
    for (i, b) in itertools.product(t.axes["inputs"], t.axes["banks"]):
        if i > b and (i, b) not in e and (b, b) in e:
            e[(i, b)] = e[(b, b)]
    return Table(t.axes, {**t.fields, "e_access_pj": e}, t.scales)


def reader_cost(t: Table, depth: float, loops: float, channels: float) -> tuple[float, float]:
    """(area_um2, e_beat_pj) of a reader (or a writer, X52)."""
    return (t.at("area_um2", depth=depth, loops=loops, channels=channels),
            t.at("e_beat_pj", depth=depth, loops=loops, channels=channels))


def xbar_cost(t: Table, inputs: float, banks: float) -> tuple[float, float]:
    """(area_um2, e_access_pj) of the interconnect; t completed with complete_xbar."""
    return t.at("area_um2", inputs=inputs, banks=banks), t.at("e_access_pj", inputs=inputs, banks=banks)


# ---------------------------------------------------------------- the tables from the CSVs
def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        sys.exit(f"no {path.relative_to(ROOT)}")
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def build(source: str, tech: str) -> list[dict]:
    synth = {r["point"]: r for r in read_csv(ROOT / "results" / source / tech / "synth_dc.csv")}
    power = {r["point"]: r for r in read_csv(ROOT / "results" / source / tech / "power_pt.csv")}
    out = []
    for point, s in synth.items():
        p = power.get(point)
        if source == "streamer":
            row = {"depth": s["depth"], "loops": s["loops"], "channels": s["channels"]}
            e_col = "e_beat_pj"
            measured = True
        else:
            row = {"inputs": s["inputs"], "banks": s["banks"]}
            e_col = "e_access_pj"
            measured = int(s["inputs"]) <= int(s["banks"])
        row.update({"area_um2": s["area_um2"], "flops": s["seq_cells"], "slack_ns": s["slack_ns"],
                    "fmax_mhz": s["fmax_mhz"], e_col: ""})
        status = s["status"] if not s["status"].startswith("ok") else ""
        if measured:
            if p is None:
                status = status or "failed: no power run"
            else:
                row[e_col] = p[e_col]
                if p["status"] != "ok" and not status:
                    status = p["status"]
        row["status"] = status or "ok"
        out.append(row)
    axes = READER_AXES if source == "streamer" else XBAR_AXES
    out.sort(key=lambda r: tuple(int(r[a]) for a in axes))
    return out


def write(rows: list[dict], path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------- leave-one-out (step 5 of STRM1 R1)
def _neighbours(vals: list[int], x: int) -> tuple[int, int]:
    i = vals.index(x)
    return vals[i - 1], vals[i + 1]


def loo_reader(t: Table) -> dict[str, list[tuple]]:
    """{field: [(point, actual, predicted, error %)]} for the interior points, trilinear from the 8 neighbours."""
    ax = t.axes
    out: dict[str, list[tuple]] = {"area_um2": [], "e_beat_pj": []}
    for d, lp, c in itertools.product([4, 8], range(2, 7), [2, 4, 6, 8]):
        nb = [_neighbours(ax["depth"], d), _neighbours(ax["loops"], lp), _neighbours(ax["channels"], c)]
        sub = Table({"depth": list(nb[0]), "loops": list(nb[1]), "channels": list(nb[2])}, t.fields)
        for f in out:
            actual = t.fields[f].get((d, lp, c))
            try:
                pred = sub.at(f, depth=d, loops=lp, channels=c)
            except ValueError:
                continue
            if actual is not None:
                out[f].append(((d, lp, c), actual, pred, 100.0 * (pred - actual) / actual))
    return out


def loo_xbar(t: Table) -> dict[str, list[tuple]]:
    """{field: [...]} for inputs 8 to 56 between the neighbours at the same bank count, each field in its scale
    (energy in 1/inputs); energy only where the point and both neighbours are measured (inputs <= banks)."""
    ins = t.axes["inputs"]
    out: dict[str, list[tuple]] = {"area_um2": [], "e_access_pj": []}
    for i, b in itertools.product(ins[1:-1], t.axes["banks"]):
        lo, hi = _neighbours(ins, i)
        for f in out:
            if f == "e_access_pj" and hi > b:
                continue
            vals = t.fields[f]
            if (i, b) not in vals or (lo, b) not in vals or (hi, b) not in vals:
                continue
            g = SCALES[t.scales.get(f, {}).get("inputs", "lin")]
            w = (g(i) - g(lo)) / (g(hi) - g(lo))
            pred = (1 - w) * vals[(lo, b)] + w * vals[(hi, b)]
            out[f].append(((i, b), vals[(i, b)], pred, 100.0 * (pred - vals[(i, b)]) / vals[(i, b)]))
    return out


def print_loo(name: str, axes: tuple[str, ...], res: dict[str, list[tuple]]) -> None:
    for f, rows in res.items():
        if not rows:
            print(f"{name} {f}: no interior point")
            continue
        errs = [abs(r[3]) for r in rows]
        worst = max(rows, key=lambda r: abs(r[3]))
        print(f"{name} {f}: {len(rows)} points, mean |error| {statistics.mean(errs):.2f} %, worst {worst[3]:+.2f} % at "
              f"{dict(zip(axes, worst[0]))} (actual {worst[1]:.4g}, predicted {worst[2]:.4g})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tech", default="nangate45")
    ap.add_argument("--loo", action="store_true", help="also print the leave-one-out check")
    args = ap.parse_args()
    out = ROOT / "results" / "strm" / args.tech
    for source, name, cols, axes in (("streamer", "streamer.csv", STREAMER_COLUMNS, READER_AXES),
                                     ("xbar", "xbar.csv", XBAR_COLUMNS, XBAR_AXES)):
        rows = build(source, args.tech)
        write(rows, out / name, cols)
        bad = [r for r in rows if r["status"] != "ok"]
        print(f"{(out / name).relative_to(ROOT)}: {len(rows)} rows, {len(rows) - len(bad)} ok")
        for r in bad:
            print(f"  {' '.join(f'{a} {r[a]}' for a in axes)}: {r['status']}")
    reader = load(out / "streamer.csv", READER_AXES, ("area_um2", "e_beat_pj"))
    xbar = load(out / "xbar.csv", XBAR_AXES, ("area_um2", "e_access_pj"), XBAR_SCALES)
    if args.loo:
        print_loo("reader", READER_AXES, loo_reader(reader))
        print_loo("xbar", XBAR_AXES, loo_xbar(xbar))
    return 0


if __name__ == "__main__":
    sys.exit(main())
