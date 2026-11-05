"""sim/sources: one tb.json adapter per source (hls, forge, char, bambu, xls).

The clock and reset port names of every source come from one table, syn/syn.py's SOURCES (docs X44): syn()
loads syn/syn.py once (as the module syn_driver, shared with sim/pwr.py) and ports(source) gives its
(clock, reset) pair. No adapter writes a port name of its own.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def syn():
    """syn/syn.py, loaded once per process."""
    mod = sys.modules.get("syn_driver")
    if mod is None:
        spec = importlib.util.spec_from_file_location("syn_driver", ROOT / "syn" / "syn.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules["syn_driver"] = mod
        spec.loader.exec_module(mod)
    return mod


def ports(source: str) -> tuple[str, str]:
    """(clock port, reset port) of a source, from syn/syn.py's SOURCES."""
    s = syn().SOURCES[source]
    return s["clk"], s["rst"]
