#!/usr/bin/env python3
"""report/test_refusal_fit.py - refusal_fit.py on synthetic rows with a known refusal price."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import refusal_fit as rf  # noqa: E402

BASE = {"tech": "nangate45", "clock_ns": "10", "clk_gate": "1", "seed": "0", "status": "ok"}


def write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = sorted({k for r in rows for k in r})
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def reader(name: str, c: int, r: float, idle: float = 2.0) -> tuple[dict, dict, dict]:
    """A reader point whose refused request-cycle costs r of a lane's granted price above an idle cycle."""
    e_beat = 4.0 * c
    g = {**BASE, "point": name, "depth": 4, "loops": 2, "channels": c, "cycles": 1027, "beats": 1024,
         "e_beat_pj": e_beat, "e_window_pj": e_beat * 1024 + 30.0}
    n, cyc = 1000 * c, 2100
    i = {**BASE, "point": name, "depth": 4, "loops": 2, "channels": c, "cycles": 1024, "mode": "idle",
         "e_cycle_pj": idle, "e_window_pj": idle * 1024, "refused": 0}
    e_r = g["e_window_pj"] + (cyc - 1027) * idle + n * r * 4.0
    f = {**BASE, "point": name, "depth": 4, "loops": 2, "channels": c, "cycles": cyc, "mode": "refused",
         "refused": n, "e_window_pj": e_r, "e_cycle_pj": e_r / cyc}
    return g, i, f


def xbar(name: str, n_in: int, r: float, idle: float = 3.0) -> tuple[dict, dict, dict]:
    g = {**BASE, "point": name, "inputs": n_in, "banks": 32, "cycles": 1025, "grants": n_in * 1024,
         "e_access_pj": 2.0, "e_window_pj": 2.0 * n_in * 1024}
    i = {**BASE, "point": name, "inputs": n_in, "banks": 32, "cycles": 1025, "mode": "idle", "e_cycle_pj": idle,
         "e_window_pj": idle * 1025, "refused": 0}
    n, cyc = n_in // 2 * 1024, 2049
    e_r = g["e_window_pj"] + (cyc - 1025) * idle + n * r * 2.0
    f = {**BASE, "point": name, "inputs": n_in, "banks": 32, "cycles": cyc, "mode": "refused", "refused": n,
         "e_window_pj": e_r, "e_cycle_pj": e_r / cyc}
    return g, i, f


def test_fit() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        rf.ROOT = root
        (root / "results" / "cluster" / "nangate45").mkdir(parents=True)
        (root / "results" / "cluster" / "nangate45" / "model_fit.json").write_text(json.dumps(
            {"floor": {"streamers": {"k_pj": 0.5}, "crossbar": {"a_pj": 1.0, "b_pj": 0.125}}}))
        pts = [reader("d4_l2_c2", 2, 0.10), reader("d4_l2_c4", 4, 0.12), reader("d4_l2_c8", 8, 0.11)]
        xs = [xbar("i8_b32", 8, 0.05), xbar("i16_b32", 16, 0.30)]
        res = root / "results"
        for kind, rows in (("streamer", pts), ("xbar", xs)):
            write(res / kind / "nangate45" / "power_pt.csv", [g for g, _, _ in rows])
            write(res / kind / "nangate45" / "power_pt_idle.csv", [i for _, i, _ in rows])
            write(res / kind / "nangate45" / "power_pt_refused.csv", [f for _, _, f in rows[:-1] if kind == "xbar"]
                  + ([f for _, _, f in rows] if kind == "streamer" else []))
        f = rf.fit("nangate45")
        s = f["sets"]["streamer"]
        assert [round(p["r"], 9) for p in s["points"].values()] == [0.10, 0.12, 0.11]
        assert abs(s["mean"] - 0.11) < 1e-9 and s["within"] and s["by"]["channels"]["4"] == s["points"]["d4_l2_c4"]["r"]
        assert abs(s["idle_over_floor"]["mean"] - 2.0 / 0.5 * (1 / 3 + 1 / 5 + 1 / 9) / 3) < 1e-9
        x = f["sets"]["xbar"]
        assert x["n"] == 1 and f["missing"]["xbar"] == ["i16_b32"] and abs(x["points"]["i8_b32"]["r"] - 0.05) < 1e-9
        assert f["sets"]["xbar_mix"]["n"] == 0
        assert abs(f["r_strm"] - 0.11) < 1e-9 and abs(f["r_xbar"] - 0.05) < 1e-9
        md = rf.markdown(f)
        assert "| streamer | 3 | 0.1100 |" in md and "Missing" in md and "| xbar_mix | 0 |" in md


def test_spread() -> None:
    pts = {"a": {"r": -0.2, "channels": 1}, "b": {"r": -0.1, "channels": 2}}
    s = rf.summary(pts, ("channels",))
    assert not s["within"] and s["mean"] < 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
