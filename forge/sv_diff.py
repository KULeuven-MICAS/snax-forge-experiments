#!/usr/bin/env python3
"""forge/sv_diff.py - two sets of forge bundles compared on their RTL, snax-forge's renames masked (PITFALLS E5).

  pixi run python forge/sv_diff.py NEW_DIR [OLD_DIR] [--same FILE]

NEW_DIR and OLD_DIR (default rtl/forge) hold bundles as forge/bundles.py writes them, <point>.zip. For every
bundle in NEW_DIR, its rtl/sv/*.sv and the file lists (rtl/files.f, rtl/sv/filelist.f) are compared with
OLD_DIR's bundle of the same point after masking what snax-forge renamed without changing the hardware:
  - the tag: snax-forge names modules and files <slot>_<design>_* since D157 (snax_forge_dot_4_ctrl), the
    SYN1 and SYN2 bundles <slot>_* (snax_forge_ctrl); the new bundle's tag (bundle.json) becomes snax_forge_
  - ElementwiseLanes became SimdLanes
  - the generator's "// Generated" header lines; a file list's order (sorted by name, so a rename reorders it)
A bundle that failed (a zip with the log only) is reported and skipped. --same FILE writes the points that are
identical, one per line (CSYN1 R2 installed those into rtl/forge/). Exit 1 when any point differs.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "arc"))
import arc  # noqa: E402


def norm(z: Path, tag: str | None) -> dict[str, str]:
    out = {}
    for n in arc.names(z):
        if not n.startswith("rtl/") or not (n.endswith(".sv") or n.endswith(".f")):
            continue
        t = arc.read_text(z, n)
        if tag and tag != "snax_forge":
            t, n = t.replace(f"{tag}_", "snax_forge_"), n.replace(f"{tag}_", "snax_forge_")
        t, n = t.replace("SimdLanes", "ElementwiseLanes"), n.replace("SimdLanes", "ElementwiseLanes")
        lines = [ln for ln in t.splitlines() if not ln.startswith("// Generated")]
        out[n] = "\n".join(sorted(lines) if n.endswith(".f") else lines)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("new", type=Path)
    ap.add_argument("old", type=Path, nargs="?", default=ROOT / "rtl" / "forge")
    ap.add_argument("--same", type=Path, help="write the identical points here")
    args = ap.parse_args()
    same, diff, failed = [], [], []
    for nz in sorted(args.new.rglob("*.zip")):
        pt = nz.relative_to(args.new).with_suffix("").as_posix()
        oz = args.old / f"{pt}.zip"
        if not arc.has(nz, "point.json"):
            failed.append(pt)
            print(f"failed  {pt}: not bundled (the zip holds the log only)")
            continue
        if not oz.is_file():
            diff.append(pt)
            print(f"DIFF    {pt}: no {oz}")
            continue
        a = norm(oz, json.loads(arc.read_text(oz, "bundle.json")).get("tag"))
        b = norm(nz, json.loads(arc.read_text(nz, "bundle.json")).get("tag"))
        bad = sorted(set(a) ^ set(b)) + [n for n in sorted(set(a) & set(b)) if a[n] != b[n]]
        commits = [json.loads(arc.read_text(z, "point.json"))["snax_forge_commit"][:7] for z in (oz, nz)]
        (diff if bad else same).append(pt)
        print(f"{'same' if not bad else 'DIFF':<7} {pt}: {len(a)} files, {commits[0]} -> {commits[1]}"
              + (f"  {bad[:6]}" if bad else ""))
    print(f"\n{len(same)} identical once masked, {len(diff)} differ, {len(failed)} not bundled")
    if args.same:
        args.same.write_text("".join(f"{p}\n" for p in same))
    return 1 if diff else 0


if __name__ == "__main__":
    sys.exit(main())
