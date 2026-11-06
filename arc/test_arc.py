#!/usr/bin/env python3
"""arc/test_arc.py - tests of arc/arc.py's pack, read and unpacked (pixi run arc-test), on seeded random trees.

  round trip     every file of a tree comes back with its bytes; keep filters by path; symlinks are not packed
  determinism    the same tree packed twice gives the same bytes, also from a copy with other times and modes
  unpacked       the folder is under tmp/ and gone on exit, also when the block raises; members pick by pattern
  write          a zip is replaced only by one that reads back; no partial file is left
  check          loose run folders, report folders, tmp/ leftovers and empty folders are found on a fake repo
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arc  # noqa: E402

SEED = 51


def make_tree(root: Path, rng: random.Random, n: int = 40) -> dict[str, bytes]:
    """A random tree of n files (text, binary, empty, nested up to 3 levels); returns {relative path: bytes}."""
    out = {}
    for i in range(n):
        depth = rng.randint(0, 3)
        parts = [f"d{rng.randint(0, 3)}" for _ in range(depth)] + [f"f{i}{rng.choice(['.rpt', '.v', '.json', ''])}"]
        rel = "/".join(parts)
        kind = rng.random()
        if kind < 0.1:
            data = b""
        elif kind < 0.5:
            data = bytes(rng.randrange(256) for _ in range(rng.randint(1, 5000)))
        else:
            data = "".join(rng.choice("abc xyz\n0123") for _ in range(rng.randint(1, 20000))).encode()
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        out[rel] = data
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="test_arc.", dir=arc.ROOT / "tmp" if (arc.ROOT / "tmp").is_dir()
                                       else None))
        self.rng = random.Random(SEED)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)
        tmp = arc.ROOT / "tmp"
        if tmp.is_dir() and not any(tmp.iterdir()):
            tmp.rmdir()


class TestRoundTrip(Base):
    def test_every_file_back(self):
        files = make_tree(self.d / "src", self.rng)
        z = self.d / "a.zip"
        got = arc.pack(self.d / "src", z)
        self.assertEqual(got, sorted(files))
        self.assertEqual(arc.names(z), sorted(files))
        for rel, data in files.items():
            self.assertEqual(arc.read(z, rel), data)
            self.assertTrue(arc.has(z, rel))
        self.assertEqual(arc.read_all(z), files)
        text = next(r for r, b in files.items() if b and all(c in b"abc xyz\n0123" for c in b))
        self.assertEqual(arc.read_text(z, text), files[text].decode())
        self.assertFalse(arc.has(z, "no/such/member"))
        self.assertFalse(arc.has(self.d / "none.zip", "x"))
        self.assertEqual(arc.read_all(self.d / "none.zip"), {})

    def test_keep_and_symlinks(self):
        files = make_tree(self.d / "src", self.rng)
        os.symlink(self.d / "src", self.d / "src" / "loop")              # a folder link: not followed, not packed
        os.symlink(next(iter(files)), self.d / "src" / "flink.rpt")      # a file link: not packed
        z = self.d / "k.zip"
        got = arc.pack(self.d / "src", z, keep=("*.rpt", "d0/*"))
        want = sorted(r for r in files if r.endswith(".rpt") or r.startswith("d0/"))
        self.assertEqual(got, want)
        self.assertEqual(arc.names(z), want)

    def test_entries(self):
        make_tree(self.d / "src", self.rng, 10)
        z = self.d / "e.zip"
        arc.pack(self.d / "src", z)
        import zipfile
        with zipfile.ZipFile(z) as zf:
            infos = zf.infolist()
        self.assertEqual([i.filename for i in infos], sorted(i.filename for i in infos))
        for i in infos:
            self.assertEqual(i.date_time, arc.EPOCH)
            self.assertEqual(i.external_attr >> 16, arc.FILE_MODE)
            self.assertEqual(i.compress_type, zipfile.ZIP_DEFLATED)


class TestDeterminism(Base):
    def test_same_bytes(self):
        make_tree(self.d / "src", self.rng)
        a, b = self.d / "a.zip", self.d / "b.zip"
        arc.pack(self.d / "src", a)
        arc.pack(self.d / "src", b)
        self.assertEqual(a.read_bytes(), b.read_bytes())
        # a copy written later, with other modification times and permissions, packs to the same bytes
        shutil.copytree(self.d / "src", self.d / "copy")
        for p in (self.d / "copy").rglob("*"):
            if p.is_file():
                os.utime(p, (time.time() - 1e6, time.time() - 1e6))
                p.chmod(0o600)
        c = self.d / "c.zip"
        arc.pack(self.d / "copy", c)
        self.assertEqual(a.read_bytes(), c.read_bytes())
        # write() of the same members in another order: the same bytes
        members = arc.read_all(a)
        rev = dict(reversed(list(members.items())))
        d = self.d / "d.zip"
        arc.write(d, rev)
        self.assertEqual(a.read_bytes(), d.read_bytes())


class TestUnpacked(Base):
    def test_cleanup_on_exit_and_exception(self):
        files = make_tree(self.d / "src", self.rng)
        z = self.d / "u.zip"
        arc.pack(self.d / "src", z)
        with arc.unpacked(z) as u:
            self.assertEqual(u.parent, arc.TMP)
            self.assertEqual(arc.files_of(u).keys(), files.keys())
            for rel, data in files.items():
                self.assertEqual((u / rel).read_bytes(), data)
        self.assertFalse(u.exists())
        with self.assertRaises(RuntimeError):
            with arc.unpacked(z) as u2:
                self.assertTrue(u2.is_dir())
                raise RuntimeError("a failing step")
        self.assertFalse(u2.exists())
        pick = [r for r in files if r.endswith(".v")][:2]
        with arc.unpacked(z, pick + ["*.json"]) as u3:
            want = set(pick) | {r for r in files if r.endswith(".json")}
            self.assertEqual(set(arc.files_of(u3)), want)
        self.assertFalse(u3.exists())
        with self.assertRaises(KeyError):
            with arc.unpacked(z, ["no/such.member"]):
                pass
        left = [p for p in arc.TMP.iterdir() if p.name.startswith("u.")] if arc.TMP.is_dir() else []
        self.assertEqual(left, [])

    def test_workdir(self):
        with self.assertRaises(ValueError):
            with arc.workdir("w") as w:
                (w / "x").write_text("x")
                raise ValueError
        self.assertFalse(w.exists())


class TestWrite(Base):
    def test_no_partial_and_bad_names(self):
        z = self.d / "w.zip"
        arc.write(z, {"a/b.txt": b"1", "c": b""})
        before = z.read_bytes()
        for bad in ("../x", "/abs", "a//b", "a/./b"):
            with self.assertRaises(ValueError):
                arc.write(z, {bad: b"x"})
        self.assertEqual(z.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.d.iterdir()), ["w.zip"])

    def test_merge_keeps_other_members(self):
        z = self.d / "m.zip"
        arc.write(z, {"tb.json": b"{}", "b64_s0/busy.saif": b"s0", "n512_s0/busy.saif": b"s1"})
        old = {m: b for m, b in arc.read_all(z).items() if not m.startswith("b64_s0/") and "/" in m}
        arc.write(z, {**old, "tb.json": b"{1}", "b64_s0/busy.saif": b"new"})
        self.assertEqual(arc.read_all(z), {"tb.json": b"{1}", "b64_s0/busy.saif": b"new", "n512_s0/busy.saif": b"s1"})


class TestCheck(Base):
    def test_leftovers(self):
        r = self.d / "repo"
        for rel in ("syn/runs/hls/nangate45/summary.csv", "syn/runs/hls/nangate45/done/v/opt_w8.zip",
                    "sim/runs/nangate45/batches.jsonl", "sim/runs/nangate45/_cells/_info",
                    "sim/runs/forge/nangate45/batches.jsonl", "rtl/char/char-rtl.log",
                    "results/hls/nangate45/reports/done/v/opt_w8.zip", "results/hls/nangate45/synth_dc.csv"):
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_bytes(b"x")
        self.assertEqual(arc.leftovers(r), {"loose": [], "reports": [], "empty": [], "tmp": []})
        for rel in ("syn/runs/hls/nangate45/done/v/opt_w4/out/x_mapped.v", "syn/runs/hls/nangate45/done/v/opt_w4/tech.json",
                    "ram/runs/cacti.zip.part1-2", "results/hls/nangate45/power_reports/done/v/opt_w8/power.rpt",
                    "tmp/cacti_d32_w8.x/cacti.out"):
            (r / rel).parent.mkdir(parents=True, exist_ok=True)
            (r / rel).write_bytes(b"x")
        (r / "rtl" / "forge" / "done").mkdir(parents=True)
        left = arc.leftovers(r)
        self.assertEqual(left["loose"], ["ram/runs", "syn/runs/hls/nangate45/done/v/opt_w4"])
        self.assertEqual(left["reports"], ["results/hls/nangate45/power_reports/done/v/opt_w8"])
        self.assertEqual(left["tmp"], ["tmp/cacti_d32_w8.x"])
        self.assertEqual(left["empty"], ["rtl/forge/done"])
        # syn runs hls nangate45 summary.csv done v opt_w8.zip opt_w4 out x_mapped.v tech.json
        self.assertEqual(arc.inodes(r / "syn"), 12)


if __name__ == "__main__":
    unittest.main(verbosity=2)
