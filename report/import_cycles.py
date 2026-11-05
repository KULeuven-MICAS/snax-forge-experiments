#!/usr/bin/env python3
"""report/import_cycles.py - the Bambu and XLS cycle CSVs, copied with their provenance (docs/DECISIONS.md X42).

  pixi run import-cycles

Copies, byte for byte,

  ../dslx-exercises/results/xls_cycles.csv            -> results/xls/xls_cycles.csv
  ../hls-exercises/results_staging/bambu_cycles.csv   -> results/bambu/bambu_cycles.csv

(both checkouts next to this repo) and writes a SOURCE file next to each copy: the source repo's URL, its
commit (HEAD of the checkout), the last commit that changed the file, the file's path in that repo, its sha256
and the date of the import. It refuses a file that is missing, not tracked by git, or with uncommitted
changes in its checkout, before it copies anything. The rows stay exactly as produced (W = 32 and failed rows
included): readers filter W <= MAX_W (syn/syn.py, X38). Standard library only.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# (source checkout, path of the CSV in it, destination in this repo)
IMPORTS = [
    (ROOT.parent / "dslx-exercises", "results/xls_cycles.csv", ROOT / "results" / "xls" / "xls_cycles.csv"),
    (ROOT.parent / "hls-exercises", "results_staging/bambu_cycles.csv",
     ROOT / "results" / "bambu" / "bambu_cycles.csv"),
]


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if done.returncode:
        sys.exit(f"git {' '.join(args)} in {repo}: {done.stderr.strip()}")
    return done.stdout.strip()


def https_url(url: str) -> str:
    """git@github.com:owner/repo.git -> https://github.com/owner/repo"""
    m = re.fullmatch(r"git@([^:]+):(.+?)(\.git)?", url)
    return f"https://{m.group(1)}/{m.group(2)}" if m else url.removesuffix(".git")


def check(repo: Path, rel: str) -> str:
    """'' if the file can be imported, else why not."""
    if not (repo / rel).is_file():
        return f"{repo / rel}: missing"
    if not git(repo, "ls-files", "--", rel):
        return f"{repo / rel}: not tracked by git in {repo.name}"
    if git(repo, "status", "--porcelain", "--", rel):
        return f"{repo / rel}: uncommitted changes in {repo.name}; commit them first"
    return ""


def main() -> int:
    errors = [e for repo, rel, _ in IMPORTS if (e := check(repo, rel))]
    if errors:
        sys.exit("import-cycles: nothing copied\n  " + "\n  ".join(errors))
    for repo, rel, dst in IMPORTS:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, dst)
        if dst.read_bytes() != (repo / rel).read_bytes():
            sys.exit(f"import-cycles: {dst} differs from {repo / rel} after the copy")
        source = {
            "repo": https_url(git(repo, "remote", "get-url", "origin")),
            "commit": git(repo, "rev-parse", "HEAD"),
            "file_commit": git(repo, "log", "-1", "--format=%H", "--", rel),
            "path": rel,
            "sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
            "date": dt.datetime.now().isoformat(timespec="seconds"),
        }
        (dst.parent / "SOURCE").write_text(
            f"# {dst.name}: copied byte for byte by report/import_cycles.py (pixi run import-cycles)\n"
            + "".join(f"{k}: {v}\n" for k, v in source.items()))
        rows = len(dst.read_text().splitlines()) - 1
        print(f"{rel} ({repo.name} {source['commit'][:7]}) -> {dst.relative_to(ROOT)}: {rows} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
