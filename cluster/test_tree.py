"""cluster/tree.py's tests (pure Python): pixi run python cluster/test_tree.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tree  # noqa: E402

REPORT = """
Hierarchical area distribution
------------------------------

                                  Global cell area             Local cell area
                                  --------------------  ------------------------------
Hierarchical cell                 Absolute     Percent  Combi-       Noncombi-  Black-
                                  Total        Total    national     national   boxes   Design
--------------------------------  -----------  -------  -----------  ---------  ------  ---------------------------------
top_w                              1000.0000    100.0       1.0000     0.0000  0.0000  top_w
a                                   600.0000     60.0      10.0000     0.0000  0.0000  A
a/b                                 400.0000     40.0       0.0000     0.0000 400.0000  B
a/b/c                               100.0000     10.0     100.0000     0.0000  0.0000  C
a/b/c/d                              50.0000      5.0      50.0000     0.0000  0.0000  D
a_x                                 399.0000     39.9     399.0000     0.0000  0.0000  AX
--------------------------------  -----------  -------  -----------  ---------  ------  ---------------------------------
Total                                                    560.0000     0.0000 400.0000
"""


def test_parse():
    rows = tree.parse(REPORT)
    assert [r["path"] for r in rows] == ["", "a", "a/b", "a/b/c", "a/b/c/d", "a_x"]
    assert rows[0]["total"] == 1000.0 and rows[2]["design"] == "B"


def test_tree_depth_and_order():
    lines = tree.tree(tree.parse(REPORT), depth=2)
    names = [ln.split()[0] for ln in lines]
    assert names == ["top_w", "a", "b", "a_x"]           # c (depth 3) cut; a_x after a's subtree
    assert lines[1].startswith("  a ") and lines[2].startswith("    b ")
    assert "60.00 %" in lines[1] and lines[1].rstrip().endswith("A")


def test_full_depth():
    lines = tree.tree(tree.parse(REPORT), depth=4)
    assert [ln.split()[0] for ln in lines] == ["top_w", "a", "b", "c", "d", "a_x"]
    assert lines[4].startswith("        d ") and "5.00 %" in lines[4]


def test_empty():
    assert tree.tree(tree.parse("no table here")) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok {name}")
