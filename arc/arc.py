#!/usr/bin/env python3
"""arc/arc.py - outputs zipped one per point (docs X51, CLAUDE.md "Files are zipped").

  pixi run arc check                 unpacked run folders, report folders not zipped, tmp/ leftovers, inodes
  pixi run arc migrate [KIND ...]    convert what is on disk to zips (rtl syn sim ram results; default all)
  pixi run arc ls ZIP                a zip's members and sizes
  pixi run arc cat ZIP MEMBER        one member on stdout
  pixi run arc-test                  arc/test_arc.py

The helpers every script imports (none of them calls zipfile itself):

  write(zip_path, {name: bytes})     a deterministic zip: entries sorted, deflated, timestamps 1980-01-01,
                                     permissions 0644; written to a temporary name next to it, test-read
                                     (every member read back and compared), then renamed into place
  pack(src_dir, zip_path, keep=None) a folder's regular files (or those whose relative path matches one of
                                     the fnmatch patterns in keep) through write(); symlinks are not packed
  names(), read(), read_text(), read_all(), has()       reading in place
  unpacked(zip_path, members=None)   a context manager: the members (fnmatch patterns, default all) in a
                                     new folder under tmp/, deleted on exit, also on an exception
  workdir(prefix)                    a context manager: an empty folder under tmp/, deleted on exit

tmp/ is git-ignored and on the repo's filesystem. Standard library only.
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import importlib.util
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

if __name__ == "__main__":         # pixi run arc: the flows' `import arc` gets this module, not a second copy
    sys.modules.setdefault("arc", sys.modules[__name__])

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
EPOCH = (1980, 1, 1, 0, 0, 0)
FILE_MODE = 0o100644                  # a regular file, rw-r--r--
LEVEL = 6                             # zlib's default; fixed so a rerun gives the same bytes

# Run folders hold only zips, but for these plain files and caches (paths relative to the repo, fnmatch)
RUN_ROOTS = ("syn/runs", "sim/runs", "ram/runs", "rtl")
ALLOWED = ("syn/runs/*/*/summary.csv",          # syn.py's summary per source and technology
           "sim/runs/*batches.jsonl",           # pwr.py's batch log per technology
           "sim/runs/*/_cells/*",               # Questa's cell models, compiled once per technology
           "sim/runs/*/_cells.vlog.log",
           "rtl/char/gen-block.json",           # char/blocks.py's list and log of its one gen-block call
           "rtl/char/char-rtl.log")
REPORT_DIRS = ("reports", "power_reports")      # results/<source>/<tech>/<these>/ hold zips only
KINDS = ("rtl", "syn", "sim", "ram", "results")  # what migrate converts, in this order


class ArcError(Exception):
    """A zip that does not read back as written."""


_tmp_lock = threading.Lock()


# ---------------------------------------------------------------- writing
def _info(name: str) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, date_time=EPOCH)
    zi.compress_type = zipfile.ZIP_DEFLATED
    zi.create_system = 3              # Unix, so external_attr is read as a mode everywhere
    zi.external_attr = FILE_MODE << 16
    return zi


def _check_name(name: str) -> None:
    if not name or name.startswith("/") or "\\" in name or any(p in ("", ".", "..") for p in name.split("/")):
        raise ValueError(f"zip member name {name!r}: relative, '/'-separated, no '.' or '..'")


def test_read(zip_path: Path, members: dict[str, bytes]) -> None:
    """Every member read back: the same names, count, sizes and bytes (zipfile checks each CRC)."""
    with zipfile.ZipFile(zip_path) as zf:
        got = [i.filename for i in zf.infolist()]
        if got != sorted(members):
            raise ArcError(f"{zip_path}: {len(got)} members, expected {len(members)}")
        for i in zf.infolist():
            data = zf.read(i)
            if i.file_size != len(members[i.filename]) or data != members[i.filename]:
                raise ArcError(f"{zip_path}: {i.filename} reads back {len(data)} B, expected "
                               f"{len(members[i.filename])} B")


def write(zip_path, members: dict[str, bytes]) -> Path:
    """Write a deterministic zip of `members` (name -> bytes) at zip_path, test-read before it replaces anything."""
    zip_path = Path(zip_path)
    for n in members:
        _check_name(n)
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    part = zip_path.with_name(f"{zip_path.name}.part{os.getpid()}-{threading.get_ident()}")
    try:
        with zipfile.ZipFile(part, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=LEVEL) as zf:
            for name in sorted(members):
                zf.writestr(_info(name), members[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=LEVEL)
        test_read(part, members)
        os.replace(part, zip_path)
    finally:
        if part.exists():
            part.unlink()
    return zip_path


def files_of(src_dir, keep=None) -> dict[str, Path]:
    """{relative posix path: file} of the regular files under src_dir (symlinks skipped), filtered by keep."""
    src_dir = Path(src_dir)
    out = {}
    for dp, dns, fns in os.walk(src_dir, followlinks=False):
        dns.sort()
        for f in sorted(fns):
            p = Path(dp) / f
            if p.is_symlink() or not p.is_file():
                continue
            rel = p.relative_to(src_dir).as_posix()
            if keep is None or any(fnmatch.fnmatchcase(rel, k) for k in keep):
                out[rel] = p
    return out


def pack(src_dir, zip_path, keep=None, extra: dict[str, bytes] | None = None) -> list[str]:
    """Zip src_dir's files (all, or those matching keep) plus `extra` members; returns the member names."""
    members = {rel: p.read_bytes() for rel, p in files_of(src_dir, keep).items()}
    members.update(extra or {})
    write(zip_path, members)
    return sorted(members)


# ---------------------------------------------------------------- reading
def names(zip_path) -> list[str]:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.namelist()


def has(zip_path, member: str) -> bool:
    zip_path = Path(zip_path)
    return zip_path.is_file() and member in names(zip_path)


def read(zip_path, member: str) -> bytes:
    with zipfile.ZipFile(zip_path) as zf:
        return zf.read(member)


def read_text(zip_path, member: str, errors: str = "strict") -> str:
    return read(zip_path, member).decode("utf-8", errors=errors)


def read_all(zip_path, prefix: str = "") -> dict[str, bytes]:
    """{name: bytes} of every member (whose name starts with prefix); {} if there is no zip."""
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        return {}
    with zipfile.ZipFile(zip_path) as zf:
        return {n: zf.read(n) for n in zf.namelist() if n.startswith(prefix)}


def _new_tmp(prefix: str) -> Path:
    with _tmp_lock:
        TMP.mkdir(exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=prefix.replace("/", "_") + ".", dir=TMP))


@contextlib.contextmanager
def workdir(prefix: str = "work"):
    """An empty folder under tmp/, deleted when the block ends, also on an exception."""
    d = _new_tmp(prefix)
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


@contextlib.contextmanager
def unpacked(zip_path, members=None):
    """The zip's members (fnmatch patterns; default all) in a new folder under tmp/, deleted on exit."""
    zip_path = Path(zip_path)
    with workdir(zip_path.stem) as d:
        with zipfile.ZipFile(zip_path) as zf:
            all_names = zf.namelist()
            if members is None:
                pick = all_names
            else:
                pick = []
                for pat in members:
                    hit = [n for n in all_names if fnmatch.fnmatchcase(n, pat)]
                    if not hit:
                        raise KeyError(f"{zip_path}: no member matches {pat!r}")
                    pick += [n for n in hit if n not in pick]
            for n in pick:
                zf.extract(n, d)
        yield d


# ---------------------------------------------------------------- check
def inodes(path: Path) -> int:
    """Inodes of path and everything below it (folders count), never following symlinks."""
    if path.is_symlink() or not path.is_dir():
        return 1
    n = 1
    for dp, dns, fns in os.walk(path, followlinks=False):
        n += len(dns) + len(fns)
    return n


def _top_folders(paths: list[Path]) -> list[Path]:
    """The given folders without those below another one of them."""
    out = []
    for p in sorted(set(paths)):
        if not any(q in p.parents for q in out):
            out.append(p)
    return out


def leftovers(root: Path = ROOT) -> dict[str, list[str]]:
    """{'loose': folders holding unzipped run files, 'reports': report folders not zipped, 'empty': empty
    folders, 'tmp': entries in tmp/}; paths relative to root."""
    loose_dirs, report_dirs, empty = [], [], []

    def rel(p: Path) -> str:
        return p.relative_to(root).as_posix()

    for r in RUN_ROOTS:
        base = root / r
        if not base.is_dir():
            continue
        for dp, dns, fns in os.walk(base, followlinks=False):
            d = Path(dp)
            if not dns and not fns:
                empty.append(d)
            for f in fns:
                p = d / f
                if p.suffix == ".zip" and not p.is_symlink():
                    continue
                if any(fnmatch.fnmatchcase(rel(p), a) for a in ALLOWED):
                    continue
                loose_dirs.append(d)
    res = root / "results"
    if res.is_dir():
        for src in sorted(res.iterdir()):
            for tech in sorted(src.iterdir()) if src.is_dir() else []:
                for kind in REPORT_DIRS:
                    base = tech / kind
                    if not base.is_dir():
                        continue
                    for dp, dns, fns in os.walk(base, followlinks=False):
                        d = Path(dp)
                        if not dns and not fns:
                            empty.append(d)
                        if any(not f.endswith(".zip") for f in fns):
                            report_dirs.append(d)
    tmp = [rel(p) for p in sorted((root / "tmp").iterdir())] if (root / "tmp").is_dir() else []
    return {"loose": [rel(p) for p in _top_folders(loose_dirs)],
            "reports": [rel(p) for p in _top_folders(report_dirs)],
            "empty": [rel(p) for p in sorted(set(empty))], "tmp": tmp}


def check(root: Path = ROOT, show: int = 20) -> int:
    """Print what is left over and the inodes per top-level folder; 1 if anything is left over."""
    left = leftovers(root)
    titles = {"loose": "run folders not zipped (syn/runs, sim/runs, ram/runs, rtl)",
              "reports": "report folders not zipped (results/*/<tech>/reports, power_reports)",
              "empty": "empty folders", "tmp": "left in tmp/"}
    for k, title in titles.items():
        items = left[k]
        print(f"{title}: {len(items) or 'none'}")
        for x in items[:show]:
            print(f"  {x}")
        if len(items) > show:
            print(f"  ... and {len(items) - show} more")
    print("\ninodes per top-level folder (folders count, symlinks not followed):")
    total = 1
    rows = []
    for p in sorted(root.iterdir()):
        n = inodes(p)
        total += n
        rows.append((n, p.name + ("/" if p.is_dir() and not p.is_symlink() else "")))
    for n, name in sorted(rows, reverse=True):
        print(f"  {n:9d}  {name}")
    print(f"  {total:9d}  total")
    bad = sum(len(v) for v in left.values())
    print(f"\narc check: {'nothing left over' if not bad else f'{bad} left over'}")
    return 1 if bad else 0


# ---------------------------------------------------------------- migrate
def _load(name: str, path: Path):
    """A repo script as a module, loaded once (syn/syn.py is the module syn_driver, as sim/sources loads it)."""
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def prune_empty(base: Path) -> int:
    """Remove the empty folders below base (not base); returns how many."""
    n = 0
    for dp, dns, fns in os.walk(base, topdown=False, followlinks=False):
        d = Path(dp)
        if d != base and not any(d.iterdir()):
            d.rmdir()
            n += 1
    return n


def point_dirs(base: Path, marker) -> list[Path]:
    """The outermost folders below base holding a file that `marker(names)` accepts; a point's own folder
    is not searched further."""
    out = []
    for dp, dns, fns in os.walk(base, followlinks=False):
        if Path(dp) != base and marker(set(fns), set(dns)):
            out.append(Path(dp))
            dns[:] = []
        else:
            dns.sort()
    return sorted(out)


INVENTORY: list[dict] = []        # one row per converted point: what was there, what the zip keeps


def inventory_row(kind: str, folder: str, files: int, n_inodes: int, z: Path, members: int | None = None) -> None:
    """members: the point's members in z (default: all of z's)."""
    INVENTORY.append({"kind": kind, "folder": folder, "files_before": files, "inodes_before": n_inodes,
                      "zip": z.relative_to(ROOT).as_posix(), "members": len(names(z)) if members is None else members,
                      "zip_bytes": z.stat().st_size})


def _files(d: Path) -> int:
    return sum(len(fns) for _, _, fns in os.walk(d, followlinks=False))


def _convert(label: str, base: Path, dirs: list[Path], fn, report: list) -> None:
    """Convert each point folder with fn(folder) -> its zip; a point that fails keeps its folder, with the reason."""
    before = inodes(base) if base.exists() else 0
    done, failed = 0, []
    for d in dirs:
        try:
            files, n = _files(d), inodes(d)
            z = fn(d)
            inventory_row(label, d.relative_to(ROOT).as_posix(), files, n, z)
            done += 1
        except Exception as e:  # noqa: BLE001  reported per point, the folder kept as it is
            failed.append((d.relative_to(ROOT).as_posix(), f"{type(e).__name__}: {e}"))
    prune_empty(base) if base.exists() else None
    after = inodes(base) if base.exists() else 0
    report.append({"folder": label, "points": done, "failed": failed, "before": before, "after": after})
    print(f"{label}: {done} points converted, {len(failed)} kept; inodes {before} -> {after}", flush=True)
    for p, why in failed:
        print(f"  kept {p}: {why}", flush=True)


def migrate(kinds: list[str]) -> list[dict]:
    """Every existing run folder, bundle and committed report folder to its zip, as the flows write them (X51).
    Rerunnable: a folder whose zip exists is packed again (the same contents give the same bytes)."""
    report: list[dict] = []
    syn = _load("syn_driver", ROOT / "syn" / "syn.py")
    if "rtl" in kinds:
        for s in ("forge", "forge_syn1"):
            base = ROOT / "rtl" / s
            if base.is_dir():
                _convert(f"rtl/{s}", base, point_dirs(base, lambda f, d: "bundle.json" in f or "forge-rtl.log" in f),
                         pack_bundle, report)
        base = ROOT / "rtl" / "char"
        if base.is_dir():
            _convert("rtl/char", base, point_dirs(base, lambda f, d: "emitted.json" in f), pack_bundle, report)
    if "syn" in kinds:
        for src in sorted((ROOT / "syn" / "runs").iterdir()):
            if src.is_dir():
                _convert(f"syn/runs/{src.name}", src,
                         point_dirs(src, lambda f, d: "tech.json" in f or ("logs" in d and "WORK" in d)),
                         syn.pack_run, report)
    if "sim" in kinds:
        pwr = _load("sim_pwr", ROOT / "sim" / "pwr.py")
        for top in sorted((ROOT / "sim" / "runs").iterdir()):
            if top.is_dir():
                _convert(f"sim/runs/{top.name}", top,
                         point_dirs(top, lambda f, d: "tb.json" in f or "check.json" in f), pwr.pack_point, report)
    if "ram" in kinds:
        ram = _load("ram_flow", ROOT / "ram" / "ram.py")
        cacti = ROOT / "ram" / "runs" / "cacti"
        if cacti.is_dir():
            before = inodes(cacti) + (1 if ram.CACTI_ZIP.exists() else 0)
            n, failed = ram.migrate_cacti(inventory_row)
            after = inodes(cacti) if cacti.exists() else 0
            report.append({"folder": "ram/runs/cacti", "points": n, "failed": failed, "before": before,
                           "after": after + 1})
            print(f"ram/runs/cacti -> ram/runs/cacti.zip: {n} points, {len(failed)} kept; inodes {before} -> "
                  f"{after + 1}", flush=True)
            for p, why in failed:
                print(f"  kept {p}: {why}", flush=True)
        lib = ROOT / "ram" / "runs" / "lib"
        if lib.is_dir():
            _convert("ram/runs/lib", lib, point_dirs(lib, lambda f, d: "key.json" in f), ram.pack_macro, report)
        probe = ROOT / "ram" / "runs" / "probe"
        if probe.is_dir():
            before = inodes(probe)

            def one(d):
                z = d.with_suffix(".zip")
                pack(d, z)
                shutil.rmtree(d)
                return z
            _convert("ram/runs/probe", ROOT / "ram" / "runs", [probe], one, report)
            report[-1].update({"before": before, "after": 1})
    if "results" in kinds:
        for src in sorted((ROOT / "results").iterdir()):
            for tech in sorted(src.iterdir()) if src.is_dir() else []:
                for kind in REPORT_DIRS:
                    base = tech / kind
                    if base.is_dir():
                        _convert(base.relative_to(ROOT).as_posix(), base,
                                 point_dirs(base, lambda f, d: bool(f) and not all(x.endswith(".zip") for x in f)),
                                 pack_report, report)
    return report


def pack_bundle(d: Path) -> Path:
    """A bundle folder (rtl/<set>/<point>/) to rtl/<set>/<point>.zip, every file; then the folder goes."""
    z = d.with_name(d.name + ".zip")
    pack(d, z)
    shutil.rmtree(d)
    return z


def pack_report(d: Path) -> Path:
    """A committed report folder (results/.../reports/<point>/, power_reports/<point>/) to <point>.zip."""
    z = d.with_name(d.name + ".zip")
    pack(d, z)
    shutil.rmtree(d)
    return z


# ---------------------------------------------------------------- CLI
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="what is left unzipped, and the inodes per top-level folder")
    p.add_argument("--show", type=int, default=20, help="paths listed per kind (default 20)")
    p = sub.add_parser("migrate", help="convert the folders on disk to zips (rerunnable)")
    p.add_argument("--inventory", type=Path, help="write one CSV row per converted point here")
    p.add_argument("kinds", nargs="*", help=f"some of {' '.join(KINDS)} (default all)")
    p = sub.add_parser("ls", help="a zip's members")
    p.add_argument("zip")
    p = sub.add_parser("cat", help="one member on stdout")
    p.add_argument("zip")
    p.add_argument("member")
    args = ap.parse_args()
    if args.cmd == "check":
        return check(show=args.show)
    if args.cmd == "migrate":
        bad = [k for k in args.kinds if k not in KINDS]
        if bad:
            ap.error(f"migrate: unknown kind {bad}: some of {' '.join(KINDS)}")
        kinds = args.kinds or list(KINDS)
        report = migrate(kinds)
        if args.inventory:
            import csv
            new = not args.inventory.is_file()
            with args.inventory.open("a", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["kind", "folder", "files_before", "inodes_before", "zip", "members",
                                                   "zip_bytes"], lineterminator="\n")
                if new:
                    w.writeheader()
                w.writerows(INVENTORY)
            print(f"inventory: {len(INVENTORY)} rows appended to {args.inventory}")
        print("\nfolder | points | kept | inodes before | after")
        for r in report:
            print(f"{r['folder']} | {r['points']} | {len(r['failed'])} | {r['before']} | {r['after']}")
        return 1 if any(r["failed"] for r in report) else 0
    if args.cmd == "ls":
        with zipfile.ZipFile(args.zip) as zf:
            for i in zf.infolist():
                print(f"{i.file_size:10d}  {i.filename}")
        return 0
    sys.stdout.buffer.write(read(args.zip, args.member))
    return 0


if __name__ == "__main__":
    sys.exit(main())
